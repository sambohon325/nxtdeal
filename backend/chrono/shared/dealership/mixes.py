"""Editable synthetic customer and inventory populations. No real-person underwriting."""
import copy
import math
import random

BODIES=['Sedan','Hatchback','SUV','Crossover','Pickup','Van','Coupe','Convertible','Wagon','Commercial','Other']

def num(d,k,lo,hi,integer=False):
    v=d.get(k)
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (integer and int(v)!=v):raise ValueError(k.replace('_',' ')+' is outside its allowed range.')
    return int(v) if integer else v

def text(d,k):
    v=d.get(k)
    if not isinstance(v,str) or not 1<=len(v.strip())<=100:raise ValueError('Enter '+k+' (up to 100 characters).')
    return v.strip()

def defaults(e):
    total=sum(s['inventory'] for s in e['segments'].values());templates=[]
    for segment,s in e['segments'].items():
        share=s['inventory']/total*100 if total else (100 if segment=='used' else 0)
        if not share:continue
        for make,model,body,w in [('Toyota','Camry','Sedan',40),('Honda','CR-V','SUV',35),('Ford','F-150','Pickup',25)]:
            templates.append(dict(make=make,model=model,body=body,condition=segment,share=round(share*w/100,4),locked=False,year_min=2026 if segment=='new' else 2015,year_max=2026 if segment=='new' else 2022,mileage_min=0 if segment=='new' else 25000,mileage_max=100 if segment=='new' else 120000,price=s['price'],cost=max(0,s['price']-s['gross'])))
    # Rounding does not change the requested total.
    templates[-1]['share']+=100-sum(r['share'] for r in templates)
    p=e['finance']['baseline']
    customers=[dict(label=label,share=share,locked=False,credit_min=lo,credit_max=hi,income_min=inc1,income_max=inc2,collection_rate=p['collection_rate'],monthly_default=p['monthly_default']) for label,share,lo,hi,inc1,inc2 in [('Profile A',40,450,579,24000,42000),('Profile B',40,580,669,36000,65000),('Profile C',20,670,850,55000,110000)]]
    return dict(seed=e['seed'],vehicle_count=max(1,min(1000,total)),customer_count=200,customers=customers,templates=templates,inventory=[],people=[])

def validate_mix(raw,e):
    m=copy.deepcopy(defaults(e) if raw is None else raw)
    if not isinstance(m,dict):raise ValueError('Invalid customer / inventory mix.')
    out={k:num(m,k,0 if k=='seed' else 1,2147483647 if k=='seed' else 1000,True) for k in ('seed','vehicle_count','customer_count')}
    for key in ('customers','templates'):
        rows=m.get(key)
        if not isinstance(rows,list) or not 1<=len(rows)<=30:raise ValueError('Use 1 to 30 mix rows.')
        out[key]=[]
        for r in rows:
            if not isinstance(r,dict):raise ValueError('Invalid mix row.')
            item=dict(share=num(r,'share',0,100),locked=r.get('locked',False))
            if type(item['locked']) is not bool:raise ValueError('Lock must be on or off.')
            if key=='customers':
                item['label']=text(r,'label')
                for k,lo,hi in [('credit_min',300,900),('credit_max',300,900),('income_min',0,1000000),('income_max',0,1000000),('collection_rate',0,100),('monthly_default',0,100)]:item[k]=num(r,k,lo,hi)
                if item['credit_min']>item['credit_max'] or item['income_min']>item['income_max']:raise ValueError('Customer range minimum must not exceed maximum.')
                if any(int(item[k])!=item[k] for k in ('credit_min','credit_max')):raise ValueError('Credit score limits must be whole numbers.')
            else:
                item.update(vehicle(r,ranges=True))
            out[key].append(item)
    # Allow an unfinished percentage mix to be saved; generation requires exactly 100%.
    inventory=m.get('inventory',[])
    if not isinstance(inventory,list) or len(inventory)>1000:raise ValueError('Use up to 1,000 generated vehicles per rooftop.')
    out['inventory']=[dict(id='SYN-STOCK-'+str(i+1).zfill(4),**vehicle(r)) for i,r in enumerate(inventory)]
    people=m.get('people',[])
    if not isinstance(people,list) or len(people)>1000:raise ValueError('Use up to 1,000 synthetic customer profiles.')
    out['people']=[]
    for i,r in enumerate(people):
        if not isinstance(r,dict):raise ValueError('Invalid synthetic customer.')
        out['people'].append(dict(id='SYN-CUSTOMER-'+str(i+1).zfill(4),profile=text(r,'profile'),credit=num(r,'credit',300,900,True),income=num(r,'income',0,1000000)))
    return out

def vehicle(r,ranges=False):
    if not isinstance(r,dict):raise ValueError('Invalid vehicle.')
    v={k:text(r,k) for k in ('make','model','body','condition')}
    if v['body'] not in BODIES or v['condition'] not in ('new','used'):raise ValueError('Choose a supported body type and new / used condition.')
    for k,lo,hi in [('price',0,1000000),('cost',0,1000000)]:v[k]=num(r,k,lo,hi)
    if not -100000<=v['price']-v['cost']<=100000:raise ValueError('Vehicle gross must be between -100,000 and 100,000.')
    for base,lo,hi in [('year',1900,2100),('mileage',0,1000000)]:
        for k in ([base+'_min',base+'_max'] if ranges else [base]):v[k]=num(r,k,lo,hi,True)
        if ranges and v[base+'_min']>v[base+'_max']:raise ValueError(base+' minimum must not exceed maximum.')
    return v

def allocate(rows,n):
    if abs(sum(r['share'] for r in rows)-100)>.001:raise ValueError('Percentages must total 100 before generating or applying customer assumptions.')
    total=sum(r['share'] for r in rows)
    exact=[r['share']*n/total for r in rows];counts=[math.floor(v) for v in exact]
    for i in sorted(range(len(rows)),key=lambda i:exact[i]-counts[i],reverse=True)[:n-sum(counts)]:counts[i]+=1
    return counts

def randomize(rows,rng,all_rows=False):
    ids=[i for i,r in enumerate(rows) if all_rows or not r['locked']]
    locked=sum(r['share'] for i,r in enumerate(rows) if i not in ids)
    if locked>100:raise ValueError('Locked percentages exceed 100.')
    if not ids:
        allocate(rows,100);return
    weights=[rng.random()+.01 for _ in ids];remaining=round((100-locked)*10000)
    values=[int(remaining*w/sum(weights)) for w in weights];values[-1]+=remaining-sum(values)
    for i,v in zip(ids,values):rows[i]['share']=v/10000

def action(raw):
    from .model import validate
    if not isinstance(raw,dict):raise ValueError('Expected a mix request.')
    e=validate(raw.get('input'));m=e['mix'];kind=raw.get('action');scope=raw.get('scope','both')
    if scope not in ('both','customers','inventory'):raise ValueError('Choose customers or inventory.')
    from .workflow import require_synthetic
    require_synthetic(e)
    rng=random.Random(m['seed'])
    if kind in ('generate','random-unlocked','random-all'):
        for key in ('customers','templates'):
            if scope!='both' and (scope=='customers')!=(key=='customers'):continue
            if kind!='generate':randomize(m[key],random.Random(str(m['seed'])+key+'weights'),kind=='random-all')
            rng=random.Random(str(m['seed'])+key+'records')
            count=m['customer_count'] if key=='customers' else m['vehicle_count'];counts=allocate(m[key],count);records=[]
            for r,n in zip(m[key],counts):
                for _ in range(n):
                    if key=='customers':records.append(dict(profile=r['label'],credit=rng.randint(int(r['credit_min']),int(r['credit_max'])),income=round(rng.uniform(r['income_min'],r['income_max']))))
                    else:records.append(dict(**{k:r[k] for k in ('make','model','body','condition','price','cost')},year=rng.randint(r['year_min'],r['year_max']),mileage=rng.randint(r['mileage_min'],r['mileage_max'])))
            rng.shuffle(records);m['people' if key=='customers' else 'inventory']=records
    elif kind=='apply-inventory':
        if not m['inventory']:raise ValueError('Generate inventory first.')
        if e['dealership']['kind'] in ('Independent Used-Car Dealerships','Buy Here Pay Here (BHPH) / Subprime Lots') and any(r['condition']=='new' for r in m['inventory']):raise ValueError('This dealership type only sells used vehicles. Change the mix to used before applying.')
        for key,s in e['segments'].items():
            rows=[r for r in m['inventory'] if r['condition']==key];s['inventory']=len(rows)
            if rows:s['price']=sum(r['price'] for r in rows)/len(rows);s['gross']=sum(r['price']-r['cost'] for r in rows)/len(rows)
        # Demand share and replenishment remain explicit, independent decisions.
    elif kind=='apply-customers':
        side=raw.get('side')
        if side not in ('baseline','scenario'):raise ValueError('Choose current or proposed financing assumptions.')
        if 'BHPH' not in e['dealership']['kind']:raise ValueError('Collection / default assumptions apply to BHPH models only.')
        allocate(m['customers'],100)
        for k in ('collection_rate','monthly_default'):e['finance'][side][k]=sum(r[k]*r['share']/100 for r in m['customers'])
    else:raise ValueError('Choose a supported mix action.')
    return validate(e)
