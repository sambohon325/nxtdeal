"""Explicit, reproducible decision templates; no free-text inference or live-system writes."""
import copy
import math

TEMPLATES={
 'software':dict(title='Test a software investment',roles=['gm','marketing','bdc','service','controller'],fields=[('monthly_cost','New software fee per rooftop / month',0,1000000,0),('response_lift','Assumed response-rate change (%)',-90,100,0),('lead_capacity_lift','Assumed lead-handling capacity change (%)',-90,100,0)],help='Tests entered costs and hypothetical effects, not measured vendor ROI or a live integration. Existing software stays in the baseline; use the detailed software editor for replacements, adoption and ramp-up.'),
 'margin':dict(title='Trade margin for more sales',roles=['gm','sales'],fields=[('gross_lift','Vehicle gross per sale change (%)',-90,100,0),('close_lift','Closing-rate change (%)',-90,100,0)],help='Relative changes, not percentage points. Sales still depend on demand, inventory and capacity. This does not simulate vehicle-level markdown schedules or a guaranteed change in days to sell.'),
 'staffing':dict(title='Change staffing',roles=['gm','bdc','service','controller'],fields=[('role','Staff role index',0,79,0),('people','People per shift',0,500,1)],help='Uses the selected role’s existing pay, shifts and scope. Payroll changes; sales/service capacity changes only if the staffing-capacity model is already enabled.'),
 'advertising':dict(title='Change advertising spend',roles=['marketing','gm'],fields=[('spend','Monthly advertising per rooftop',0,1000000,0),('paid_efficiency_lift','Paid leads per dollar change (%)',-90,100,0)],help='Uses the existing lead-cost and saturation assumptions. It does not send leads, validate attribution, or exercise CRM routing.'),
 'followup':dict(title='Improve lead follow-up',roles=['bdc','marketing'],fields=[('response_lift','Response-rate change (%)',-90,100,0),('appointment_lift','Appointment-rate change (%)',-90,100,0),('show_lift','Show-rate change (%)',-90,100,0)],help='Relative rate changes are assumptions; rates are capped by the engine. This tests funnel outcomes, not an AI agent or SMS conversation.'),
 'fi':dict(title='Change F&I gross per sale',roles=['fi','gm'],fields=[('fi_lift','F&I gross per retail sale change (%)',-90,100,0)],help='Requires a nonzero separate F&I gross baseline. It does not predict lender approval, product penetration or regulatory compliance.'),
 'portfolio':dict(title='Stress-test BHPH collections',roles=['fi','controller','gm'],fields=[('down_payment','Down payment per financed vehicle',0,100000,2500),('collection_rate','Scheduled payment collected (%)',0,100,95),('monthly_default','Monthly principal default (%)',0,100,1)],help='BHPH only. Down payment, collection and default assumptions are independent inputs; changing down payment does not automatically predict credit risk.'),
 'service':dict(title='Test service demand and capacity',roles=['service','gm'],fields=[('service_demand_lift','Service demand change (%)',-90,100,0),('service_capacity_lift','Service capacity change (%)',-90,100,0),('service_value_lift','Gross per repair order change (%)',-90,100,0)],help='Monthly demand and capacity model. It does not model Tuesday appointment queues, advisor wait times or parts obsolescence. Add any extra labor cost below.'),
 'cost':dict(title='Test an additional monthly expense',roles=['controller','gm'],fields=[('monthly_cost','Additional monthly expense per rooftop',0,1000000,0)],help='Adds a transparent planning cost. Use the detailed facilities editor to reduce or replace existing expenses; this is not a normalized accounting composite.'),
}

def catalog():return [dict(id=k,**v) for k,v in TEMPLATES.items()]

def prepare(raw):
    from .model import validate, software
    if not isinstance(raw,dict):raise ValueError('Choose a decision to test.')
    e=validate(raw.get('input'));key=raw.get('decision');t=TEMPLATES.get(key) if isinstance(key,str) else None
    if not t:raise ValueError('Choose a supported decision.')
    from .workflow import require_ready
    require_ready(e)
    values=raw.get('values')
    if not isinstance(values,dict) or set(values)!={f[0] for f in t['fields']}:raise ValueError('Complete the decision inputs.')
    for name,label,lo,hi,_ in t['fields']:
        n=values[name]
        if type(n) not in (int,float) or not math.isfinite(n) or not lo<=n<=hi:raise ValueError('Enter a valid '+label+'.')
    cost=raw.get('implementation_cost',0)
    if type(cost) not in (int,float) or not math.isfinite(cost) or not 0<=cost<=1000000:raise ValueError('Enter a valid monthly implementation cost.')
    # Start each experiment from the baseline, avoiding hidden stacking with an old proposal.
    e['scenario']=copy.deepcopy(e['baseline']);e['scenario']['name']=t['title']
    e['finance']['scenario']=copy.deepcopy(e['finance']['baseline'])
    mod=software('custom');mod.update(name=t['title'],monthly_cost=cost,rationale=t['help'])
    if key=='staffing':
        index=values['role'];people=values['people']
        if int(index)!=index or int(people)!=people or index>=len(e['scenario']['operating']['roles']):raise ValueError('Choose an existing staff role and whole people count.')
        if not e['operating_enabled']:raise ValueError('Enable payroll and operating costs in Setup first.')
        e['scenario']['operating']['roles'][int(index)]['people']=people
    elif key=='cost':
        if not e['operating_enabled']:raise ValueError('Enable operating costs in Setup first.')
        if values['monthly_cost']:
            e['scenario']['operating']['expenses'].append(dict(name='Decision test: additional monthly expense',quantity=1,rate=values['monthly_cost'],scope='rooftop'))
    elif key=='portfolio':
        if 'BHPH' not in e['dealership']['kind']:raise ValueError('Use a BHPH dealership for this decision.')
        e['finance']['scenario'].update(values)
    else:
        for k,v in values.items():
            if k=='spend':e['scenario']['spend']=v
            elif k=='monthly_cost':mod['monthly_cost']+=v
            else:mod[k]=v
    if key=='fi' and not any(s['fi'] and (s['inventory'] or s['replenishment']) for s in e['segments'].values()):raise ValueError('Add a separate F&I gross baseline in Setup before testing its change.')
    if key=='service' and (not e['profile']['service_requests'] or not e['profile']['service_capacity']):raise ValueError('Enter service demand and capacity in Setup first.')
    # Name differs by design; detect actual economic change before appending a hypothesis module.
    changed=any(mod[k] for k in values if k in mod) or mod['monthly_cost'] or e['scenario']['operating']!=e['baseline']['operating'] or e['scenario']['spend']!=e['baseline']['spend'] or e['finance']['scenario']!=e['finance']['baseline']
    if not changed:raise ValueError('Change at least one value from the baseline to create a useful experiment.')
    if any(mod[k] for k in ('monthly_cost','gross_lift','close_lift','paid_efficiency_lift','response_lift','lead_capacity_lift','appointment_lift','show_lift','fi_lift','service_demand_lift','service_capacity_lift','service_value_lift')):e['scenario']['software'].append(mod)
    description=t['title']+': '+', '.join(f'{label} = {values[k]:g}' for k,label,*_ in t['fields'])+f'; added implementation cost = {cost:g}/month/rooftop'
    e['workflow']['objective']=description[:300]
    e['notes']=(e['notes']+'\nDECISION TEST: '+description+'\n'+t['help'])[-4000:]
    return validate(e)
