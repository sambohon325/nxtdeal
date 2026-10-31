"""Editable operating budgets and auditable task-time hypotheses (per rooftop)."""
import copy
import re
from .catalogue import CATALOG

SOURCES = [
    {'name':'NADA workforce research', 'url':'https://www.nada.org/nada/research-data/nada-dealership-workforce-study', 'checked':'2026-09-15', 'description':'Compensation and benefits research exists, but detailed study tables were not imported. Small/medium/large are planning archetypes, not official size classifications.'},
    {'name':'BLS employer compensation, December 2025', 'url':'https://www.bls.gov/news.release/archives/ecec_03202026.htm', 'checked':'2026-09-15', 'description':'US retail wages were $20.27/hour and benefits $6.14/hour (about 30.3% of wages). Broad retail context only; not dealership-role pay or Canadian benefit rates. Our editable 25% burden is a guess, not this statistic.'},
    {'name':'ENERGY STAR vehicle dealerships', 'url':'https://www.energystar.gov/buildings/resources-audience/small-biz/vehicle-dealers', 'checked':'2026-09-15', 'description':'Lighting, HVAC and vehicle washing are controllable energy/water uses. Model consumption and tariffs are editable guesses, not a utility quote.'},
    {'name':'ENERGY STAR energy-use intensity', 'url':'https://www.energystar.gov/buildings/benchmark/understand-metrics/what-eui', 'checked':'2026-09-15', 'description':'Area-normalized energy use provides a calibration method. Electricity, gas and water remain separate input quantities; no old dollar benchmark is imported.'},
    {'name':'RouteOne contracting workflow', 'url':'https://www.routeone.com/dealers/contracting/econtracting', 'checked':'2026-09-15', 'description':'Prefilling contract data removes duplicate entry. Advertised up-to savings are not an average time study and are not imported.'},
    {'name':'Xtime inspection workflow', 'url':'https://xtime.com/inspect/', 'checked':'2026-09-15', 'description':'Digital inspections and approvals support a service workflow hypothesis; customer approval elapsed time is not the same as employee labor time.'},
]

# Percent of HANDS-ON task time saved at full adoption/readiness. Analyst guesses.
TASK_PRIORS = {
 'crm': {'followup':15,'entry':20}, 'dms': {'entry':15,'accounting':20,'parts':10},
 'website': {'listing':20}, 'digital': {'deal':15,'contract':10},
 'retention': {'campaign':25,'followup':10}, 'ads': {'campaign':35,'listing':10},
 'ai': {'followup':30,'booking':20}, 'inventory': {'pricing':25},
 'recon': {'recon':25}, 'service': {'booking':20,'approval':25},
 'fi': {'deal':15,'contract':10}, 'contract': {'contract':30},
 'analytics': {'reporting':40}, 'marketplace': {'listing':10},
}
ROLE_NAMES = ['Management','Sales','BDC','F&I','Service advisors','Technicians','Parts','Administration','Porters / detail']
ROLE_IDS = ['management','sales','bdc','fi','advisors','technicians','parts','admin','porters']
TASKS = [
 ('followup','Lead follow-up','bdc','leads',1,12),('entry','Customer / deal data entry','admin','sales',1,25),
 ('deal','Desking and F&I preparation','fi','sales',1,45),('contract','Contract preparation / checking','fi','sales',1,30),
 ('listing','Vehicle listing / merchandising','sales','arrivals',1,30),('pricing','Inventory pricing review','sales','inventory',1,10),
 ('recon','Recon coordination (not repair labor)','porters','arrivals',1,25),('booking','Service booking / check-in','advisors','service_ros',1,12),
 ('approval','Inspection communication / approvals','advisors','service_ros',1,15),('parts','Parts handling / ordering','parts','service_ros',1,12),
 ('repair','Hands-on repair labor','technicians','service_ros',1,90),('campaign','Campaign production','bdc','fixed',12,120),
 ('accounting','Reconciliation / accounting','admin','fixed',26,90),('reporting','Management reporting','management','fixed',20,90),
]

def plan(size='medium'):
    index=['small','medium','large'].index(size)
    counts=[[1,3,1,1,1,3,1,2,2],[3,10,3,2,4,12,4,5,5],[6,20,6,4,8,24,8,10,10]][index]
    rates=[55,22,24,35,30,34,25,26,20]  # nominal CAD/USD, no FX conversion
    roles=[]
    for rid,name,count,wage in zip(ROLE_IDS,ROLE_NAMES,counts,rates):
        roles.append(dict(id=rid,name=name,scope="rooftop",people=count,shifts=1,shift_hours=8.5,unpaid_break=.5,days_week=5,
                          wage=wage,salary=0,commission=0,burden=25,ot_threshold=40,ot_multiplier=1.5,
                          unavailable=15,embedded=100 if rid=='technicians' else 0,cash_realization=0))
    multiplier=[.4,1,2][index]
    expense_specs=[('Rent / occupancy',18000),('Property tax',4000),('Insurance',4500),('Maintenance',2500),
                   ('Cleaning / snow / landscaping',2200),('Internet / phones',1200),('Security',600),
                   ('Training / recruiting',1500),('Professional fees',2000),('Supplies / waste',1000),
                   ('Equipment leases',2000),('Other operating costs',0)]
    expenses=[dict(name=name,quantity=1,rate=round(value*multiplier),scope='rooftop') for name,value in expense_specs]
    expenses += [dict(name='Electricity · kWh',quantity=round(18000*multiplier),rate=.15,scope='rooftop'),
                 dict(name='Natural gas · billing units',quantity=round(1800*multiplier),rate=.65,scope='rooftop'),
                 dict(name='Water / sewer · m³',quantity=round(160*multiplier),rate=4,scope='rooftop')]
    tasks=[dict(id=tid,name=name,role=role,driver=driver,volume=round(volume*multiplier,2) if driver=='fixed' else volume,minutes=minutes) for tid,name,role,driver,volume,minutes in TASKS]
    return dict(size=size,open_days=26,open_hours=10,roles=roles,expenses=expenses,tasks=tasks)

SIZE_PROFILES = {
 'small':dict(organic_leads=250,inventory=60,replenishment=35,lead_capacity=450,sales_capacity=45,service_requests=250,service_capacity=300),
 'medium':dict(organic_leads=750,inventory=180,replenishment=100,lead_capacity=1400,sales_capacity=140,service_requests=1000,service_capacity=1200),
 'large':dict(organic_leads=1500,inventory=360,replenishment=200,lead_capacity=2800,sales_capacity=280,service_requests=2000,service_capacity=2400),
}

def task_estimates(vendor,case='working'):
    product=next((x for x in CATALOG if x['id']==vendor),{})
    factor={'downside':-.5,'no-benefit':0,'cautious':.5,'working':1,'optimistic':2}.get(case,1)
    return {key:value*factor for key,value in TASK_PRIORS.get(product.get('template'),{}).items()}

def validate_plan(raw, number, string):
    if not isinstance(raw,dict): raise ValueError('Operating plan must be an object.')
    out={key:number(raw,key,1,31 if key=='open_days' else 24) for key in ['open_days','open_hours']}
    out['size']=string(raw,'size')
    if 'facility' in raw:
        f=raw['facility']
        if not isinstance(f,dict): raise ValueError('Facility must be an object.')
        if f.get('tenure') not in ['leased','owned','mixed']: raise ValueError('Choose leased, owned or mixed premises.')
        out['facility']={'tenure':f['tenure'],'notes':string(f,'notes',1000,True)}
        for k,maximum in [('building_sqft',10000000),('lot_sqft',100000000),('service_bays',10000),('detail_bays',10000),('parking_spaces',100000)]:
            out['facility'][k]=number(f,k,0,maximum,k.endswith('bays') or k=='parking_spaces')
    for key,limit in [('roles',80),('tasks',200),('expenses',120)]:
        if not isinstance(raw.get(key),list) or len(raw[key])>limit: raise ValueError(f'Use up to {limit} {key}.')
        out[key]=[]
        for item in raw[key]:
            if not isinstance(item,dict): raise ValueError(f'Invalid {key} row.')
            row={'name':string(item,'name')}
            if 'department' in item: row['department']=string(item,'department',60)
            if key=='roles':
                row['id']=string(item,'id')
                row['scope']=item.get('scope','rooftop')
                if row['scope'] not in ['rooftop','group']: raise ValueError('Choose rooftop or group staffing scope.')
                for k,lo,hi in [('people',0,500),('shifts',1,3),('shift_hours',0,24),('unpaid_break',0,8),('days_week',0,7),('wage',0,1000),('salary',0,100000),('commission',0,10000),('burden',0,100),('ot_threshold',0,168),('ot_multiplier',1,3),('unavailable',0,100),('embedded',0,100),('cash_realization',0,100)]:
                    row[k]=number(item,k,lo,hi,k in ['people','shifts'])
                if row['unpaid_break']>row['shift_hours']: raise ValueError('Unpaid break exceeds shift length.')
                if row['shift_hours']*row['shifts']>24: raise ValueError('Shifts exceed 24 hours per day.')
            elif key=='expenses':
                row.update(quantity=number(item,'quantity',0,10000000),rate=number(item,'rate',0,1000000),scope=string(item,'scope'))
                if row['scope'] not in ['rooftop','group']: raise ValueError('Choose rooftop or group expense scope.')
            else:
                for k in ['id','role','driver']: row[k]=string(item,k)
                if row['driver'] not in ['fixed','leads','sales','arrivals','inventory','service_ros']: raise ValueError('Unknown task volume driver.')
                row.update(volume=number(item,'volume',0,100000),minutes=number(item,'minutes',0,10000))
            out[key].append(row)
    for key in ['roles','tasks']:
        if any(not re.fullmatch(r'[A-Za-z0-9_-]+', r['id']) for r in out[key]): raise ValueError('Role and job IDs may contain only letters, numbers, hyphens and underscores.')
        if len({r['id'] for r in out[key]})!=len(out[key]): raise ValueError(f'Duplicate {key} IDs.')
    if any(t['role'] not in {r['id'] for r in out['roles']} for t in out['tasks']): raise ValueError('Each task needs an existing role.')
    return out

def task_shares(modules, task, month):
    """Allocation sums exactly to combined effect, including ties and adverse effects."""
    categories={p['id']:p['category'] for p in CATALOG}
    groups={}; shares=[0.0]*len(modules)
    for i,m in enumerate(modules):
        if not m['enabled']: continue
        effect=m.get('task_savings',{}).get(task,0)*m['adoption']/100*m['integration']/100*min(1,(month+1)/m['ramp_months'])
        if effect<0: shares[i]=effect
        elif effect>0: groups.setdefault(categories.get(m['vendor'],'Custom') if m['vendor']!='custom' else f'custom-{i}',[]).append((i,effect))
    ranked=sorted(groups.items(),key=lambda pair:(-max(x[1] for x in pair[1]),pair[0]))
    for rank,(_,group) in enumerate(ranked):
        best=max(v for _,v in group); winners=[i for i,v in group if v==best]
        for i in winners: shares[i]+=best*.5**rank/len(winners)
    total=sum(shares)
    if abs(total)>100: shares=[v*100/abs(total) for v in shares]
    return shares

def operating_month(e,side,row,month):
    """Costs here are per-rooftop. Group-wide costs are apportioned before rollup."""
    p=e[side]['operating']; modules=e[side]['software']; n=e['rooftops']
    roles=[]
    for r in p['roles']:
        people=r['people']*r['shifts']/(n if r.get('scope')=='group' else 1); weekly=(r['shift_hours']-r['unpaid_break'])*r['days_week']
        hours=people*weekly*52/12; overtime=people*max(0,weekly-r['ot_threshold'])*52/12
        reg=e.get('regional',{})
        wage=max(r['wage'],reg.get('wage_floor',0)) if reg.get('apply_wage_floor') else r['wage']
        base=r['salary']*people if r['salary'] else (hours-overtime)*wage+overtime*wage*r['ot_multiplier']
        loaded=(base+(r['commission']*row['sales'] if people else 0))*(1+r['burden']/100)
        roles.append(dict(id=r['id'],name=r['name'],people=people,paid_hours=hours,productive_hours=hours*(1-r['unavailable']/100),overtime_hours=overtime,
                          payroll=loaded,additional_payroll=loaded*(1-r['embedded']/100),hourly_value=base*(1+r['burden']/100)/hours if hours else 0,
                          task_hours=0,saved_hours=0,required_hours=0,cash_savings=0,overload_hours=0))
    byrole={r['id']:r for r in roles}; tasks=[]
    for t in p['tasks']:
        driver={'fixed':1,'leads':row['leads'],'sales':row['sales'],'arrivals':e['profile']['inventory'] if month==0 else e['profile']['replenishment'],'inventory':(row['opening_inventory']+row['ending_inventory'])/2,'service_ros':row['service_ros']}[t['driver']]
        volume=driver*t['volume']; hours=volume*t['minutes']/60
        shares=task_shares(modules,t['id'],month); saved=hours*sum(shares)/100
        r=byrole[t['role']];r['task_hours']+=hours;r['saved_hours']+=saved;r['required_hours']+=hours-saved
        tasks.append(dict(id=t['id'],name=t['name'],role=t['role'],volume=volume,minutes_before=t['minutes'],minutes_after=t['minutes']*(1-sum(shares)/100),cost_per_job_before=t['minutes']/60*r['hourly_value'],cost_per_job_after=t['minutes']*(1-sum(shares)/100)/60*r['hourly_value'],hours_before=hours,hours_saved=saved,hours_after=hours-saved,labor_value=saved*r['hourly_value'],shares=shares))
    # Value only labor time supportable by the paid productive-hours budget.
    for r,inputs in zip(roles,p['roles']):
        factor=min(1,r['productive_hours']/r['task_hours']) if r['task_hours'] else 0
        r['valued_hours_saved']=r['saved_hours']*factor
        r['cash_savings']=min(r['additional_payroll'],max(0,r['valued_hours_saved'])*r['hourly_value']*inputs['cash_realization']/100*(1-inputs['embedded']/100))
        r['overload_hours']=max(0,r['required_hours']-r['productive_hours'])
        for t in tasks:
            if t['role']==r['id']: t['labor_value']*=factor
    products=[]
    for i,m in enumerate(modules):
        hours=sum(t['hours_before']*t['shares'][i]/100 for t in tasks)
        value=sum(t['hours_before']*t['shares'][i]/100*byrole[t['role']]['hourly_value']*min(1,byrole[t['role']]['productive_hours']/byrole[t['role']]['task_hours']) for t in tasks if byrole[t['role']]['task_hours'])
        cost=(m['monthly_cost']+(m['setup_cost'] if month==0 else 0))/(n if m.get('cost_scope')=='group' else 1) if m['enabled'] else 0
        products.append(dict(name=m['name'],vendor=m['vendor'],hours_saved=hours,labor_value=value,software_cost=cost))
    for t in tasks: del t['shares']
    expenses=[dict(name=x['name'],cost=x['quantity']*x['rate']/(n if x['scope']=='group' else 1)) for x in p['expenses']]
    payroll=sum(r['payroll'] for r in roles); additional=sum(r['additional_payroll'] for r in roles); cash=sum(r['cash_savings'] for r in roles); overhead=sum(x['cost'] for x in expenses)
    return dict(roles=roles,tasks=tasks,products=products,expenses=expenses,payroll=payroll,additional_payroll=additional,cash_savings=cash,overhead=overhead,
                task_hours_saved=sum(t['hours_saved'] for t in tasks),labor_value=sum(t['labor_value'] for t in tasks),paid_hours=sum(r['paid_hours'] for r in roles),
                overload_hours=sum(r['overload_hours'] for r in roles),operating_cost=additional+overhead-cash)
