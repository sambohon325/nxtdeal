"""Reverse dealership requirements, evaluated by the caller's canonical Chrono engine.

The evaluator returns lists of average monthly revenue/contribution/sales outcomes.
It must use paired seeds and canonical admission; this module never runs a second
Monte Carlo executor. Derived requirements are hypotheses, not acquired demand.
Adapted from Dealer Composite deployed commit263e1c77223ab9f70ad1ce4fd055be00ec5fea7a.
"""
import copy
import math
import statistics
from .model import validate

def requirements(raw, evaluate):
    if not isinstance(raw,dict):raise ValueError('Enter a planning goal.')
    e=validate(raw.get('input'));metric=raw.get('metric');target=raw.get('target');action=raw.get('action','reverse')
    from .workflow import require_ready, require_synthetic
    require_ready(e)
    if action=='reverse':require_synthetic(e)
    if metric not in ('vehicle_revenue','contribution'):raise ValueError('Choose revenue or operating contribution.')
    if type(target) not in (int,float) or not math.isfinite(target) or not 0<target<=100000000:raise ValueError('Enter a monthly target above zero and at most 100 million.')
    if action not in ('forecast','reverse'):raise ValueError('Choose a planning action.')
    if not e['operating_enabled']:raise ValueError('Enable payroll and running costs before planning a profit target.')
    e['trials']=100
    original=copy.deepcopy(e);changes=[]
    if action=='reverse':
        if e['staffing_capacity_enabled']:raise ValueError('Turn off relative staffing capacity in the goal planner. It uses explicit per-person productivity instead.')
        productivity=raw.get('sales_per_person',10)
        if type(productivity) not in (int,float) or not math.isfinite(productivity) or not 1<=productivity<=100:raise ValueError('Enter 1–100 sales per salesperson per month.')
        mix=e['profile']['new_share']/100
        price=sum(e['segments'][k]['price']*share for k,share in [('new',mix),('used',1-mix)])
        margin=sum((e['segments'][k]['gross']+e['segments'][k]['fi'])*share for k,share in [('new',mix),('used',1-mix)])-e['regional']['extra_cost_per_sale']
        if price<=0 or (metric=='contribution' and margin<=0):raise ValueError('A positive selling price and per-vehicle margin are needed for this target.')
        funnel=math.prod(e['profile'][k+'_rate']/100 for k in ('response','appointment','show','close'))
        if funnel<=0 or e['profile']['market_index']<=0:raise ValueError('Demand and every conversion stage must be above zero.')
        roof=e['rooftops']
        vals=evaluate(copy.deepcopy(e))
        desired=target/price if metric=='vehicle_revenue' else max(1,(target-statistics.mean(vals['contribution'])+statistics.mean(vals['sales'])*margin)/margin)
        for iteration in range(4):
            units=max(1,math.ceil(desired/roof));p=e['profile']
            if units>2000:raise ValueError('This target exceeds the planner limit of 2,000 monthly sales per rooftop. Adjust target, margins or rooftops.')
            # Requirements, not a claim that extra organic demand is available.
            s=e['scenario']
            paid=s['spend']/s['cpl']/(1+s['spend']/s['saturation_budget'])
            required_leads=max(0,math.ceil(units/funnel/(p['market_index']/100)-paid))
            if required_leads>10000:raise ValueError('This target needs more than 10,000 leads per rooftop. Improve conversion or reduce the target.')
            p['organic_leads']=required_leads;p['lead_capacity']=min(10000,math.ceil((required_leads+paid)*1.3));p['sales_capacity']=math.ceil(units*1.3)
            for k,share in [('new',mix),('used',1-mix)]:
                e['segments'][k]['inventory']=math.ceil(units*share*2)
                e['segments'][k]['replenishment']=math.ceil(units*share*1.15)
            salesroles=[r for r in e['scenario']['operating']['roles'] if r['id']=='sales']
            if not salesroles:raise ValueError('Add a Sales role before calculating required staffing.')
            for r in salesroles:r['people']=math.ceil(units/productivity/(r['shifts'] or 1)*(roof if r['scope']=='group' else 1))
            e=validate(e)
            vals=evaluate(copy.deepcopy(e));achieved=statistics.mean(vals[metric])
            if achieved>=target:break
            desired+=max(1,(target-achieved)/(price if metric=='vehicle_revenue' else margin))
        for k,label in [('organic_leads','Required organic leads / rooftop'),('lead_capacity','Lead-handling capacity / rooftop'),('sales_capacity','Delivery capacity / rooftop')]:
            changes.append(dict(label=label,before=original['profile'][k],after=e['profile'][k]))
        for k in ('new','used'):
            for field in ('inventory','replenishment'):changes.append(dict(label=f'{k.title()} {field} / rooftop',before=original['segments'][k][field],after=e['segments'][k][field]))
        for a,b in zip(original['scenario']['operating']['roles'],e['scenario']['operating']['roles']):
            if a['people']!=b['people']:changes.append(dict(label=b['name']+' people / shift ('+b['scope']+')',before=a['people'],after=b['people']))
    return dict(input=e, changes=changes, metric=metric, target=target)
