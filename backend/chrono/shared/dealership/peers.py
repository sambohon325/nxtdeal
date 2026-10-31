"""Public aggregate comparison matrix. No customer records or synthetic peer observations."""
import json
from pathlib import Path
from .configuration import KINDS
DATA=json.loads(Path(__file__).with_name('peer_data.json').read_text())
# Standard Census state FIPS; names match the app's jurisdiction catalogue.
from .jurisdictions import US
CODES='01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56'.split()
FIPS=dict(zip(sorted(US),CODES))
REGIONS={'Northeast':'09 23 25 33 44 50 34 36 42','Midwest':'17 18 26 39 55 19 20 27 29 31 38 46','South':'10 11 12 13 24 37 45 51 54 01 21 28 47 05 22 40 48','West':'04 08 16 30 32 35 49 56 02 06 15 41 53'}

def aggregate(rows):
    if not rows:return None
    if any(r['emp_nf'] not in ('G','H','J') or r['ap_nf'] not in ('G','H','J') for r in rows):return None
    totals={k:sum(int(r[k]) for r in rows) for k in ('emp','ap','est')}
    if totals['est']<10 or totals['emp']<=0 or totals['ap']<=0:return None
    return totals

def describe(name,raw,weight):
    if not raw:return dict(name=name,available=False,weight=0,reason='Unavailable, suppressed or fewer than 10 establishments.')
    return dict(name=name,available=True,weight=weight,establishments=raw['est'],employees_per_store=round(raw['emp']/raw['est'],1),annual_pay_per_employee=round(raw['ap']*1000/raw['emp']),monthly_pay_per_store=round(raw['ap']*1000/raw['est']/12))

def comparison(inputs):
    p=inputs['profile'];kind=inputs['dealership']['kind'];code='441120' if kind in (KINDS[1],KINDS[3]) else '441110' if kind==KINDS[0] else None
    answer=dict(period=DATA['period'],source=DATA['source'],checked=DATA['checked'],industry=code,rows=[],blend=None,notes=['Public employer aggregates, not participating-dealer financial composites. All establishment sizes; BHPH is included with used-car dealers.','2023 historical USD values, not inflation-adjusted. Employment is a March snapshot; annual payroll divided by employment is a proxy, not a salary survey.','Published values include Census noise adjustments. A minimum of 10 establishments is required. Missing or suppressed observations are not zero.','Vehicle inventory, sales gross, credit losses and profitability are not in this source. No size-matched profit average is inferred.'])
    if p['country']!='United States' or not code:
        answer['notes'].insert(0,'A comparable public aggregate series is not loaded for this country or dealership classification. No peer average is shown.');return answer
    state=FIPS[p['region']];region=next(k for k,v in REGIONS.items() if state in v.split())
    states=[r for r in DATA['states'] if r['naics']==code]
    localrows=[r for r in DATA['counties'] if r['naics']==code and r['fipstate']==state and r['fipscty']=='439'] if state=='48' and p['city'].strip().lower() in ('fort worth','ft worth','ft. worth') else []
    local=aggregate(localrows);state_total=aggregate([r for r in states if r['fipstate']==state])
    # Disjoint geography components avoid counting the same establishments twice.
    remainder=state_total
    if local and state_total:
        remainder={k:state_total[k]-local[k] for k in ('emp','ap','est')}
        if remainder['est']<10 or remainder['emp']<=0 or remainder['ap']<=0:remainder=None
    regional=aggregate([r for r in states if r['fipstate'] in REGIONS[region].split() and r['fipstate']!=state])
    answer['rows']=[describe('Local: Tarrant County proxy for Fort Worth' if localrows else 'Local: county mapping not loaded',local,.5),describe(p['region']+(' excluding local county' if local else ''),remainder,.3),describe(region+' excluding '+p['region'],regional,.2)]
    total=sum(r['weight'] for r in answer['rows'])
    if total:
        for r in answer['rows']:r['weight']=round(r['weight']/total,6)
        pay=sum(r['annual_pay_per_employee']*r['weight'] for r in answer['rows'] if r['available'])
        people=sum(r['people'] for r in inputs['baseline']['operating']['roles'])*inputs['rooftops']
        inventory=p['inventory']*inputs['rooftops']
        answer['blend']=dict(annual_pay_per_employee=round(pay),people=people,inventory=inventory,monthly_payroll_proxy=round(pay*people/12),monthly_payroll_per_vehicle=round(pay*people/12/inventory,2) if inventory else None)
    answer['notes']+=['Blend weights are model design assumptions: local 50%, state remainder 30%, region remainder 20%; available weights are renormalized. These are not statistical confidence weights.','Fort Worth spans several counties. Tarrant County is a local-market proxy, not an exact city boundary. Other cities currently fall back to state and region.','The inventory-normalized payroll is an estimate using your entered staff and vehicle count. It excludes benefits, payroll taxes and credit losses; it is not an observed average for 70-car BHPH stores.']
    return answer
