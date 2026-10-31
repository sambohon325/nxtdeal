"""Dealer monthly CSV and unit-economics transforms; no forecast runner.
Adapted from the owned DealerComposite source. Imported values need source review.
"""
import csv, io, re, math, json, hashlib, copy
from datetime import date
from .configuration import USED_ONLY

SPECS=[
('new_units','New retail units','units','Sales'),('used_units','Used retail units','units','Sales'),
('new_revenue','New vehicle revenue','money','Sales'),('used_revenue','Used vehicle revenue','money','Sales'),
('new_gross','New vehicle gross, excluding F&I','signed','Sales'),('used_gross','Used vehicle gross, excluding F&I','signed','Sales'),
('fi_gross','F&I gross, net of chargebacks','signed','F&I'),('finance_deals','Finance contracts','units','F&I'),('service_contracts','Service contracts sold','units','F&I'),
('service_revenue','Service revenue','money','Fixed operations'),('service_gross','Service gross after direct labor','signed','Fixed operations'),
('parts_gross','Parts gross','signed','Fixed operations'),('repair_orders','Repair orders','units','Fixed operations'),
('labor_sales','Labor sales','money','Fixed operations'),('billed_hours','Billed technician hours','number','Fixed operations'),('worked_hours','Technician hours worked','number','Fixed operations'),
('payroll','Payroll including employer burden','money','Expenses'),('operating_expenses','Total operating expenses, including payroll and marketing','money','Expenses'),
('marketing_spend','Marketing spend','money','Expenses'),('pretax_profit','Reported pre-tax profit','signed','Financials'),('cash','Month-end cash','money','Financials'),('staff_fte','Average full-time-equivalent employees','number','Expenses'),('debt','Month-end debt','money','Financials'),
('leads','Unique leads','units','CRM'),('responded_leads','Leads responded to','units','CRM'),('appointments','Appointments set','units','CRM'),('shows','Appointments attended','units','CRM'),
('inventory_units','Month-end inventory units','units','Inventory'),('inventory_value','Month-end inventory at cost','money','Inventory'),('aged_units','Inventory units aged over 60 days','units','Inventory'),
('receivables','Month-end BHPH principal receivables','money','BHPH'),('delinquent_balance','Principal 30+ days past due','money','BHPH'),('chargeoffs','Monthly principal charge-offs','money','BHPH'),('collections','Monthly cash collections','money','BHPH')]

FIELDS={k:dict(key=k,label=label,unit=unit,department=department) for k,label,unit,department in SPECS}

META=['month','rooftop','currency']

def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalize(value): return re.sub(r'[^a-z0-9]','',value.lower())

def inspect_csv(text):
    if not isinstance(text,str) or not text.strip() or len(text.encode())>750000: raise ValueError('Choose a CSV export under 750 KB.')
    try:
        sample=text.lstrip('\ufeff'); dialect=csv.Sniffer().sniff(sample[:8192],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    reader=csv.reader(io.StringIO(text.lstrip('\ufeff')),dialect)
    try: headers=next(reader)
    except StopIteration: raise ValueError('The CSV is empty.')
    headers=[h.strip() for h in headers]
    if not headers or len(headers)>150 or any(not h for h in headers) or len(set(headers))!=len(headers): raise ValueError('Use unique, non-empty column headings (up to 150).')
    rows=[]
    for line,row in enumerate(reader,2):
        if not any(x.strip() for x in row):continue
        if len(row)!=len(headers):raise ValueError(f'CSV line {line}: number of values differs from the headings.')
        rows.append(dict(zip(headers,row)))
        if len(rows)>1200:raise ValueError('Import at most 1,200 rooftop-month rows at once.')
    if not rows:raise ValueError('Add at least one completed month.')
    aliases={'period':'month','store':'rooftop','storeid':'rooftop','rooftopid':'rooftop'}
    lookup={normalize(k):k for k in META+list(FIELDS)}
    lookup.update({normalize(v['label']):k for k,v in FIELDS.items()});lookup.update(aliases)
    mapping={}
    for h in headers:
        key=lookup.get(normalize(h))
        if key and key not in mapping:mapping[key]=h
    return dict(headers=headers,mapping=mapping,row_count=len(rows)),rows

def parse_import(raw, profile):
    if not isinstance(raw,dict):raise ValueError('Choose an export and map its columns.')
    info,rows=inspect_csv(raw.get('csv'))
    mapping=raw.get('mapping',info['mapping'])
    if not isinstance(mapping,dict) or any(k not in META+list(FIELDS) for k in mapping):raise ValueError('Invalid column mapping.')
    mapping={k:v for k,v in mapping.items() if v}
    if any(k not in mapping for k in META):raise ValueError('Map Month, Rooftop and Currency columns.')
    if any(not isinstance(v,str) for v in mapping.values()):raise ValueError('Column mappings must refer to heading text.')
    if any(v not in info['headers'] for v in mapping.values()) or len(set(mapping.values()))!=len(mapping):raise ValueError('Map each source column only once.')
    if not any(k in FIELDS for k in mapping):raise ValueError('Map at least one performance metric.')
    clean=[];seen=set();today=date.today().strftime('%Y-%m')
    for line,row in enumerate(rows,2):
        m=row[mapping['month']].strip(); roof=row[mapping['rooftop']].strip(); currency=row[mapping['currency']].strip().upper()
        if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])',m) or m>=today:raise ValueError(f'Line {line}: use a completed month as YYYY-MM, before {today}.')
        if not roof or len(roof)>80 or any(ord(c)<32 for c in roof):raise ValueError(f'Line {line}: rooftop must be a short store identifier.')
        if currency!=profile['currency']:raise ValueError(f'Line {line}: currency must match the dealership ({profile["currency"]}). No currency conversion is performed.')
        if (m,roof) in seen:raise ValueError(f'Line {line}: duplicate month and rooftop. Aggregate transactions before importing.')
        seen.add((m,roof));values={}
        for key in FIELDS:
            if key not in mapping:continue
            value=row[mapping[key]].strip()
            if value=='':continue
            # A decimal point is required; thousands separators and currency symbols must be removed upstream.
            if not re.fullmatch(r'-?\d+(?:\.\d+)?',value):raise ValueError(f'Line {line}, {FIELDS[key]["label"]}: use plain numbers (example 12500.50), with no commas, symbols or formulas.')
            n=float(value);unit=FIELDS[key]['unit']
            if not math.isfinite(n) or abs(n)>1e12 or (unit!='signed' and n<0) or (unit=='units' and not n.is_integer()):raise ValueError(f'Line {line}: invalid {FIELDS[key]["label"]}.')
            values[key]=n
        if not values:raise ValueError(f'Line {line}: no mapped numeric values.')
        clean.append(dict(month=m,rooftop=roof,currency=currency,values=values))
    return sorted(clean,key=lambda x:(x['month'],x['rooftop']))

def validate_relationships(rows,kind):
    for row in rows:
        v=row['values'];where=row['month']+' / '+row['rooftop']
        for child,parent in [('responded_leads','leads'),('appointments','responded_leads'),('shows','appointments'),('aged_units','inventory_units'),('delinquent_balance','receivables')]:
            if child in v and parent in v and v[child]>v[parent]:raise ValueError(f"{where}: {FIELDS[child]['label']} cannot exceed {FIELDS[parent]['label']}. Check that both cover the same scope.")
        if kind in USED_ONLY and v.get('new_units',0)>0:raise ValueError(f'{where}: this dealership type is pre-owned only.')

def template():
    out=io.StringIO();writer=csv.writer(out);writer.writerow(META+list(FIELDS));return out.getvalue()

def add_month(month,offset):
    y,m=map(int,month.split('-'));i=y*12+m-1+offset;return f'{i//12:04d}-{i%12+1:02d}'

def aggregate(rows,roof=None):
    selected=[r for r in rows if roof is None or r['rooftop']==roof]
    roofs=sorted({r['rooftop'] for r in selected});monthly=[]
    for month in sorted({r['month'] for r in selected}):
        group=[r for r in selected if r['month']==month]
        complete=len(group)==len(roofs)
        values={k:sum(r['values'][k] for r in group) for k in FIELDS if complete and all(k in r['values'] for r in group)}
        monthly.append(dict(month=month,values=values,rooftops=len(group),complete=complete))
    return roofs,monthly

def ratio(v,num,den,scale=1):
    if not all(k in v for k in num+den):return None
    d=sum(v[k] for k in den)
    return sum(v[k] for k in num)/d*scale if d else None

KPI=[('vehicle_gross_per_unit','Vehicle gross / retail unit',['new_gross','used_gross'],['new_units','used_units'],1,'currency'),
('fi_pvr','F&I gross / retail unit',['fi_gross'],['new_units','used_units'],1,'currency'),
('marketing_per_sale','Marketing cost / retail unit',['marketing_spend'],['new_units','used_units'],1,'currency'),
('hours_per_ro','Billed hours / repair order',['billed_hours'],['repair_orders'],1,'hours'),
('effective_labor_rate','Effective labor rate',['labor_sales'],['billed_hours'],1,'currency'),
('shop_productivity','Billed / worked technician hours',['billed_hours'],['worked_hours'],100,'percent'),
('fixed_coverage','Service + parts gross / total operating expenses',['service_gross','parts_gross'],['operating_expenses'],100,'percent'),
('aged_share','Inventory over 60 days',['aged_units'],['inventory_units'],100,'percent'),
('response_rate','Lead response rate',['responded_leads'],['leads'],100,'percent'),
('show_rate','Appointment show rate',['shows'],['appointments'],100,'percent'),
('gross_per_fte','Total department gross / FTE',['new_gross','used_gross','fi_gross','service_gross','parts_gross'],['staff_fte'],1,'currency'),
('delinquency_rate','BHPH principal 30+ days past due',['delinquent_balance'],['receivables'],100,'percent')]

def calibrate(raw,rows,roof=None):
    from .model import validate
    e=validate(raw);roofs,monthly=aggregate(rows,roof)
    if not monthly or not monthly[-1]['complete']:raise ValueError('Complete the most recent month before calibrating.')
    if rows[0]['currency']!=e['profile']['currency']:raise ValueError('Actuals and simulation currencies must match.')
    latest=monthly[-1];v=latest['values'];changes=[];sources=[]
    labels={'rooftops':'Rooftop count','profile.new_share':'New vehicles: share of demand (%)','profile.service_gross_per_ro':'Service gross per repair order'}
    for segment in ['new','used']:
        for key,label in [('price','selling price'),('gross','vehicle gross per sale'),('fi','F&I gross per sale')]:labels['segments.'+segment+'.'+key]=('New' if segment=='new' else 'Pre-owned')+' '+label
    def change(path,value,basis):
        target=e;parts=path.split('.')
        for p in parts[:-1]:target=target[p]
        old=target[parts[-1]]
        sources.append(dict(field=path,value=value,basis=basis,month=latest['month'],revision=digest(rows)[:16]))
        if old!=value:changes.append(dict(field=path,label=labels.get(path,path),before=old,after=value,basis=basis));target[parts[-1]]=value
    change('rooftops',len(roofs),'Number of selected actual rooftops; group simulation uses identical average locations.')
    units=sum(v.get(k,0) for k in ['new_units','used_units'])
    if all(k in v for k in ['new_units','used_units']) and units:
        change('profile.new_share',round(v['new_units']/units*100,2),'Observed sales mix used as a demand-mix assumption.')
    for segment in ['new','used']:
        count=v.get(segment+'_units',0)
        if count:
            for metric,field in [('revenue','price'),('gross','gross')]:
                if segment+'_'+metric in v:change('segments.'+segment+'.'+field,round(v[segment+'_'+metric]/count,2),'Latest-month total divided by retail units.')
            if 'fi_gross' in v and all(k in v for k in ['new_units','used_units']) and v['fi_gross']>=0:change('segments.'+segment+'.fi',round(v['fi_gross']/units,2),'Blended net F&I / retail unit, allocated equally to new and used; review mix.')
    if v.get('repair_orders') and v.get('service_gross',-1)>=0:
        change('profile.service_gross_per_ro',round(v['service_gross']/v['repair_orders'],2),'Service gross divided by repair orders; check direct-labor definition.')
    e['notes']=(e['notes']+'\nActual-data calibration revision '+digest(rows)[:16]+': '+latest['month']+'; rooftops '+', '.join(roofs)+'. Only reviewed unit economics and mix updated. Demand, capacity, payroll, expenses and inventory remain assumptions; this is not a fitted P&L.')[-5000:]
    e['workflow']['calibration']=sources
    e['workflow']['review']=None
    return dict(input=validate(e),changes=changes,month=latest['month'],limitations='Only unit economics, sales mix and roof count are calibrated. Forecasts of actuals remain separate from the stochastic scenario model. Imported payroll, expenses, demand and stock are not silently replaced by assumed allocations.')
