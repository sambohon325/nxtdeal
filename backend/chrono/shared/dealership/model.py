"""Dealership stock/flow mechanics, executed through the shared Chrono engine."""
import copy
import math
import random
import statistics

MODEL_VERSION = "5.4.0"
SCHEMA_VERSION = 5

from .catalogue import CATALOG, CATALOGUE_VERSION, EFFECT_LABELS, OPERATING_DEFAULTS
from .operating import plan, validate_plan, operating_month, SOURCES as OPERATING_SOURCES
from .configuration import KINDS, ALIASES, USED_ONLY, TYPE_NOTES, segments_from_profile
from .jurisdictions import reference, regional_defaults, SOURCES as REGIONAL_SOURCES

REFERENCES = [
    {"name": "Statistics Canada • monthly new motor vehicle sales", "url": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010008501&request_locale=en", "description": "Reference for future provincial calibration. No values from this table are imported into the starter profiles.", "checked": "2026-09-13"},
    {"name": "NADA • dealership publications", "url": "https://www.nada.org/nada/publications", "description": "Reference for U.S. franchised dealership research. Starter profiles are illustrative, not NADA benchmarks.", "checked": "2026-09-13"},
]

PROFILES = {
    "franchise": {"name": "Lakeside Motors", "type": "Franchised new & used", "brand": "Multi-brand", "country": "Canada", "region": "Ontario", "city": "London", "currency": "CAD", "organic_leads": 500, "inventory": 120, "replenishment": 65, "lead_capacity": 900, "sales_capacity": 85, "gross_per_sale": 3200, "response_rate": 78, "appointment_rate": 45, "show_rate": 70, "close_rate": 32, "market_index": 100, "seasonality": 12, "demand_volatility": 12, "new_share": 60},
    "independent": {"name": "Parkway Auto", "type": "Independent used", "brand": "Multi-brand", "country": "Canada", "region": "Alberta", "city": "Calgary", "currency": "CAD", "organic_leads": 220, "inventory": 55, "replenishment": 28, "lead_capacity": 450, "sales_capacity": 40, "gross_per_sale": 2800, "response_rate": 75, "appointment_rate": 42, "show_rate": 65, "close_rate": 30, "market_index": 100, "seasonality": 12, "demand_volatility": 15, "new_share": 0},
    "luxury": {"name": "Summit Automotive", "type": "Luxury franchise", "brand": "Luxury brand", "country": "United States", "region": "Colorado", "city": "Denver", "currency": "USD", "organic_leads": 300, "inventory": 80, "replenishment": 38, "lead_capacity": 600, "sales_capacity": 50, "gross_per_sale": 5500, "response_rate": 82, "appointment_rate": 48, "show_rate": 75, "close_rate": 28, "market_index": 100, "seasonality": 10, "demand_volatility": 12, "new_share": 70},
}

def software(vendor="custom"):
    name = next(x["name"] for x in CATALOG if x["id"] == vendor)
    return {**{k: 0 for k in EFFECT_LABELS}, "integration": 100, "enabled": True, "estimate_case": "manual", "task_savings": {}, "cost_scope": "rooftop", "vendor": vendor, "name": name, "monthly_cost": 0, "setup_cost": 0, "adoption": 100, "ramp_months": 1, "capture_lift": 0, "response_lift": 0, "appointment_lift": 0, "show_lift": 0, "close_lift": 0, "rationale": "User hypothesis; validate costs and effects before use."}

def default_experiment():
    baseline = {"name": "Current approach", "spend": 18000, "cpl": 70, "saturation_budget": 60000, "software": [], "operating": plan()} 
    proposal = copy.deepcopy(baseline)
    proposal["name"] = "Proposed approach"
    return {"schema_version": SCHEMA_VERSION, "operating_enabled": False, "rooftops": 1, "name": "My first dealership experiment", "notes": "", "profile": {**OPERATING_DEFAULTS, **copy.deepcopy(PROFILES["franchise"])}, "months": 12, "trials": 100, "seed": 42, "start_month": 1, "baseline": baseline, "scenario": proposal}

def number(data, key, lo, hi, integer=False):
    x = data.get(key)
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi or (integer and x != int(x)):
        raise ValueError(f"{key.replace('_', ' ')} must be {'a whole number ' if integer else ''}between {lo} and {hi}.")
    return int(x) if integer else float(x)

def string(data, key, maximum=200, empty=False):
    x = data.get(key)
    if not isinstance(x, str) or len(x) > maximum or (not empty and not x.strip()):
        raise ValueError(f"{key.replace('_', ' ')} must be text {'(optional) ' if empty else ''}up to {maximum} characters.")
    return x.strip()

def validate(raw):
    if not isinstance(raw, dict) or raw.get("schema_version") not in [1, 2, 3, 4, SCHEMA_VERSION]:
        raise ValueError("Unsupported experiment format. Expected schema version 1 through 5.")
    p = raw.get("profile")
    if not isinstance(p, dict):
        raise ValueError("A dealership profile is required.")
    p = {**OPERATING_DEFAULTS, **p}
    result = {"schema_version": SCHEMA_VERSION, "name": string(raw, "name"), "notes": string(raw, "notes", 5000, True)}
    for k, lo, hi in [("months", 1, 36), ("trials", 10, 200), ("seed", 0, 2147483647), ("start_month", 1, 12)]:
        result[k] = number(raw, k, lo, hi, True)
    result["rooftops"] = number({"rooftops":raw.get("rooftops",1)}, "rooftops", 1, 100, True)
    from .earnings import settings
    result['finance']=settings(raw.get('finance'))
    result['staffing_capacity_enabled']=raw.get('staffing_capacity_enabled',False)
    if not isinstance(result['staffing_capacity_enabled'],bool):raise ValueError('Staff capacity option must be true or false.')
    result["operating_enabled"] = raw.get("operating_enabled",False)
    if not isinstance(result["operating_enabled"],bool): raise ValueError("Operating budget must be enabled or disabled.")
    result["profile"] = q = {}
    for k in ["name", "type", "brand", "country", "region", "city", "currency"]:
        q[k] = string(p, k, empty=k=='city')
    if q["country"] not in ["Canada", "United States"] or q["currency"] not in ["CAD", "USD"]:
        raise ValueError("Choose Canada or United States, and CAD or USD.")
    for k in ["organic_leads", "inventory", "replenishment", "lead_capacity", "sales_capacity"]:
        q[k] = number(p, k, 0, 10000, True)
    q["gross_per_sale"] = number(p, "gross_per_sale", 0, 100000)
    q["market_index"] = number(p, "market_index", 0, 300)
    for key in OPERATING_DEFAULTS:
        q[key] = number(p, key, 0, 100000, key in ["service_requests", "service_capacity"])
    for k in ["response_rate", "appointment_rate", "show_rate", "close_rate", "new_share"]:
        q[k] = number(p, k, 0, 100)
    q["seasonality"] = number(p, "seasonality", 0, 80)
    q["demand_volatility"] = number(p, "demand_volatility", 0, 50)
    setup=copy.deepcopy(raw.get('dealership',{'kind':ALIASES.get(q['type'],q['type']) if q['type'] in KINDS or q['type'] in ALIASES else KINDS[0],'size':'medium'}))
    if isinstance(setup,dict): setup['kind']=ALIASES.get(setup.get('kind'),setup.get('kind'))
    if not isinstance(setup,dict) or setup.get('kind') not in KINDS or setup.get('size') not in ['small','medium','large']:
        raise ValueError('Choose a supported dealership type and size.')
    result['dealership']={'kind':setup['kind'],'size':setup['size'],'notes':TYPE_NOTES[setup['kind']]}
    q['type']=setup['kind']
    ref=reference(q['country'],q['region'])
    q['currency']=ref['currency']
    regional=raw.get('regional',regional_defaults(q['country'],q['region']))
    if not isinstance(regional,dict): raise ValueError('Regional assumptions must be an object.')
    result['regional']={k:number(regional,k,0,hi) for k,hi in [('wage_floor',1000),('tax_rate',100),('extra_monthly_cost',1000000),('extra_cost_per_sale',100000)]}
    for key in ['apply_wage_floor','tax_enabled']:
        if not isinstance(regional.get(key),bool): raise ValueError('Regional options must be on or off.')
        result['regional'][key]=regional[key]
    result['regional']['notes']=string(regional,'notes',5000,True)
    if result['regional']['tax_enabled']:
        for side in ('baseline','scenario'):
            if 'tax_rate' not in (raw.get('finance') or {}).get(side,{}):
                result['finance'][side]['tax_rate']=result['regional']['tax_rate']
    result['jurisdiction_reference']=ref
    segments=raw.get('segments',segments_from_profile(q))
    if not isinstance(segments,dict) or set(segments)!={'new','used'}: raise ValueError('New and pre-owned inventory are required.')
    result['segments']={}
    for key in ['new','used']:
        item=segments[key]
        if not isinstance(item,dict): raise ValueError('Invalid inventory segment.')
        result['segments'][key]={k:number(item,k,0,10000,True) for k in ['inventory','replenishment']}
        result['segments'][key].update({k:number(item,k,0,1000000) for k in ['price','fi','holding']})
        result['segments'][key]['gross']=number(item,'gross',-100000,100000)
        if item['gross']>item['price']: raise ValueError('Vehicle gross cannot exceed its selling price.')
    if setup['kind'] in USED_ONLY and (q['new_share'] or segments['new']['inventory'] or segments['new']['replenishment']):
        raise ValueError('Independent used dealerships require zero new-vehicle demand, stock and arrivals. Choose a new-and-pre-owned type for mixed retail.')
    for key in ['inventory','replenishment']:
        q[key]=sum(s[key] for s in result['segments'].values())
        if q[key]>10000: raise ValueError('Combined inventory and monthly arrivals must each be at most 10,000 per rooftop.')
    for side in ["baseline", "scenario"]:
        s = raw.get(side)
        if not isinstance(s, dict):
            raise ValueError(f"Missing {side}.")
        result[side] = dest = {"name": string(s, "name")}
        for k, lo, hi in [("spend", 0, 1000000), ("cpl", 1, 10000), ("saturation_budget", 1, 10000000)]:
            dest[k] = number(s, k, lo, hi)
        campaigns=s.get('campaigns')
        if campaigns is not None:
            if not isinstance(campaigns,list) or len(campaigns)>20:raise ValueError('Use up to 20 campaigns.')
            dest['campaigns']=[]
            for c in campaigns:
                if not isinstance(c,dict):raise ValueError('Invalid campaign.')
                dest['campaigns'].append(dict(name=string(c,'name'),budget=number(c,'budget',0,1000000),cpl=number(c,'cpl',1,10000)))
            spend=sum(c['budget'] for c in dest['campaigns'])
            if spend>1000000:raise ValueError('Combined campaign budget cannot exceed 1,000,000 per month.')
            leads=sum(c['budget']/c['cpl'] for c in dest['campaigns'])
            dest['spend']=spend
            dest['cpl']=spend/leads if leads else 70
        dest["operating"] = validate_plan(s.get("operating",plan()),number,string)
        items = s.get("software")
        if not isinstance(items, list) or len(items) > 12:
            raise ValueError("Use up to 12 software modules per approach.")
        dest["software"] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid software module.")
            module = {"vendor": string(item, "vendor"), "name": string(item, "name"), "rationale": string(item, "rationale", 2000, True)}
            if module["vendor"] not in {x["id"] for x in CATALOG}:
                raise ValueError("Unknown catalogue product. Use a custom solution instead.")
            for k in ["monthly_cost", "setup_cost"]:
                module[k] = number(item, k, 0, 1000000)
            module["adoption"] = number(item, "adoption", 0, 100)
            module["ramp_months"] = number(item, "ramp_months", 1, 36, True)
            for k in EFFECT_LABELS:
                module[k] = number({k: item.get(k, 0)}, k, -1000 if k == "admin_hours_saved" else -100, 1000 if k == "admin_hours_saved" else 100)
            module["integration"] = number({"integration": item.get("integration", 100)}, "integration", 0, 100)
            module["enabled"] = item.get("enabled", True)
            if not isinstance(module["enabled"], bool):
                raise ValueError("Enabled must be true or false.")
            module["estimate_case"] = string({"estimate_case": item.get("estimate_case", "manual")}, "estimate_case", 40)
            module['cost_scope']=item.get('cost_scope','rooftop')
            if module['cost_scope'] not in ['rooftop','group']: raise ValueError('Choose rooftop or group software pricing.')
            savings=item.get('task_savings',{})
            if not isinstance(savings,dict) or len(savings)>40: raise ValueError('Invalid task savings.')
            module['task_savings']={string({'id':k},'id'):number({'value':v},'value',-100,100) for k,v in savings.items()}
            dest["software"].append(module)
    from .mixes import validate_mix
    result['mix']=validate_mix(raw.get('mix'),result)
    from .workflow import normalize
    result['workflow']=normalize(raw.get('workflow'))
    return result

def staff_capacity_factor(e,side,role_ids):
    if not e.get('staffing_capacity_enabled'):return 1
    def hours(which):
        return sum(r['people']*r['shifts']*(r['shift_hours']-r['unpaid_break'])*r['days_week']*(1-r['unavailable']/100)/(e['rooftops'] if r['scope']=='group' else 1) for r in e[which]['operating']['roles'] if r['id'] in role_ids)
    base,current=hours('baseline'),hours(side)
    return current/base if base else (1 if current else 0)

def rng(seed, trial, month, stage):
    # Streams are independent by stage and shared across both approaches.
    return random.Random(f"{MODEL_VERSION}:{seed}:{trial}:{month}:{stage}")

def binomial(n, probability, generator):
    return sum(generator.random() < probability for _ in range(n))



def combined_effects(modules, month):
    categories = {x['id']: x['category'] for x in CATALOG}
    result = {}
    for metric in EFFECT_LABELS:
        groups = {}
        for i, module in enumerate(modules):
            if not module.get('enabled', True):
                continue
            group = categories.get(module['vendor'], 'Custom')
            if group == 'Custom':
                group = f'custom-{i}'
            factor = module['adoption'] / 100 * module.get('integration', 100) / 100 * min(1, (month + 1) / module['ramp_months'])
            groups.setdefault(group, []).append(module.get(metric, 0) * factor)
        positive = sorted([max([0] + values) for values in groups.values()], reverse=True)
        negative = sum(min(0, v) for values in groups.values() for v in values)
        result[metric] = sum(v * .5 ** i for i, v in enumerate(positive)) + negative
    return result


def stack_notes(e, side):
    modules = [x for x in e[side]['software'] if x['enabled']]
    notes = []
    categories = {x['id']: x['category'] for x in CATALOG}
    for category in sorted({categories[x['vendor']] for x in modules} - {'Custom'}):
        if sum(categories[x['vendor']] == category for x in modules) > 1:
            notes.append(f'{category}: overlapping products charge separately; only the strongest positive effect per metric within this category applies. Consider replacement instead of adding both.')
    p = e['profile']
    if any(any(x[k] for k in ['service_demand_lift','service_capacity_lift','service_value_lift']) for x in modules) and (not p['service_requests'] or not p['service_capacity'] or not p['service_gross_per_ro']):
        notes.append('Service effects cannot produce meaningful contribution until service demand, capacity and gross per RO are entered.')
    if any(x['fi_lift'] for x in modules) and not p['fi_gross_per_sale']:
        notes.append('F&I effects need a separate F&I gross-per-sale input. Remove that amount from vehicle gross to avoid double counting.')
    if any(x['holding_reduction'] for x in modules) and not p['holding_cost_per_vehicle']:
        notes.append('Inventory carrying-cost effects are inactive until a carrying-cost input is entered.')
    if not e['operating_enabled'] and any(x['admin_hours_saved'] for x in modules) and not p['admin_hours']:
        notes.append('Admin-hours effects are inactive until baseline admin hours are entered; released hours are never booked as cash savings.')
    return notes


def simulate_one(e, side, trial):
    p, s = e["profile"], e[side]
    rooftops = e["rooftops"]
    segments=e.get('segments',segments_from_profile(p))
    stock={k:s['inventory'] for k,s in segments.items()}
    inventory = sum(stock.values())
    rows = []
    for m in range(e["months"]):
        calendar_month = (e["start_month"] - 1 + m) % 12 + 1
        # Illustrative annual cycle: summer peak, winter trough. Mean factor is 1.
        seasonal = 1 + p["seasonality"] / 100 * math.cos(2 * math.pi * (calendar_month - 6) / 12)
        shock = max(0, rng(e["seed"], trial, m, "demand").gauss(1, p["demand_volatility"] / 100))
        market = p["market_index"] / 100 * seasonal * shock
        raw_effects = combined_effects(s['software'], m)
        effects = {stage: max(0, min(2, 1 + raw_effects[stage + '_lift'] / 100)) for stage in ['capture','response','appointment','show','close','lead_capacity','sales_capacity','gross','fi','service_demand','service_capacity','service_value','paid_efficiency']}
        paid = s["spend"] / s["cpl"] / (1 + s["spend"] / s["saturation_budget"]) * effects["paid_efficiency"]
        expected = min(20000, (p["organic_leads"] + paid) * market * effects["capture"])
        lead_rng = rng(e["seed"], trial, m, "lead-rounding")
        leads = math.floor(expected) + int(lead_rng.random() < expected % 1)
        handled = min(leads, math.floor(p["lead_capacity"] * staff_capacity_factor(e,side,{'bdc','sales'}) * effects["lead_capacity"]))
        count = handled
        funnel = {}
        for stage in ["response", "appointment", "show", "close"]:
            rate = min(1, p[stage + "_rate"] / 100 * effects[stage])
            count = binomial(count, rate, rng(e["seed"], trial, m, stage))
            funnel[stage] = count
        # Opening stock is available in month 1; replenishment arrives in months 2+.
        if m:
            for key in stock: stock[key]+=segments[key]['replenishment']
        openings=stock.copy()
        opening = sum(stock.values())
        staffed_sales = min(count, math.floor(p["sales_capacity"] * staff_capacity_factor(e,side,{'sales'}) * effects["sales_capacity"]))
        new_demand=binomial(staffed_sales,p['new_share']/100,rng(e['seed'],trial,m,'new-used-demand'))
        demand={'new':new_demand,'used':staffed_sales-new_demand}
        sold={key:min(demand[key],stock[key]) for key in stock}
        for key in stock: stock[key]-=sold[key]
        sales=sum(sold.values()); inventory=sum(stock.values())
        software_cost = sum((x["monthly_cost"] + (x["setup_cost"] if m == 0 else 0))/(rooftops if x.get("cost_scope")=="group" else 1) for x in s["software"] if x["enabled"])
        gross = sum(sold[k]*s['gross'] for k,s in segments.items()) * effects['gross']
        fi_gross = sum(sold[k]*s['fi'] for k,s in segments.items()) * effects['fi']
        service_demand = max(0, round(p["service_requests"] * seasonal * shock * effects["service_demand"]))
        service_ros = min(service_demand, math.floor(p["service_capacity"] * staff_capacity_factor(e,side,{'technicians'}) * effects["service_capacity"]))
        service_gross = service_ros * p["service_gross_per_ro"] * effects["service_value"]
        holding_cost = sum((openings[k]+stock[k])/2*s['holding'] for k,s in segments.items()) * max(0, min(2, 1 - raw_effects["holding_reduction"] / 100))
        admin_hours = max(-p["admin_hours"], min(p["admin_hours"], raw_effects["admin_hours_saved"]))
        rows.append({"fi_gross": fi_gross, "service_ros": service_ros, "service_gross": service_gross, "service_lost_ros": service_demand - service_ros, "holding_cost": holding_cost, "admin_hours_saved": admin_hours, "month": m + 1, "calendar_month": calendar_month, "leads": leads, "handled": handled, "responded": funnel["response"], "appointments": funnel["appointment"], "visits": funnel["show"], "potential_sales": count, "sales": sales, "new_sales": sales * p["new_share"] / 100, "used_sales": sales * (1 - p["new_share"] / 100), "unhandled_leads": leads - handled, "staff_lost_sales": count - staffed_sales, "stock_lost_sales": staffed_sales - sales, "opening_inventory": opening, "ending_inventory": inventory, "gross": gross, "marketing_cost": s["spend"], "software_cost": software_cost, "cost": s["spend"] + software_cost + holding_cost, "contribution": gross + fi_gross + service_gross - s["spend"] - software_cost - holding_cost})
        row=rows[-1]
        for key,spec in segments.items():
            row.update({key+'_sales':sold[key],key+'_opening_inventory':openings[key],key+'_ending_inventory':stock[key],
                        key+'_arrivals':spec['replenishment'] if m else 0,key+'_stock_lost_sales':demand[key]-sold[key],
                        key+'_revenue':sold[key]*spec['price'],key+'_gross':sold[key]*spec['gross']*effects['gross'],
                        key+'_fi_gross':sold[key]*spec['fi']*effects['fi']})
        row['vehicle_revenue']=row['new_revenue']+row['used_revenue']
        extra={k:0 for k in ['payroll','additional_payroll','cash_savings','overhead','task_hours_saved','labor_value','paid_hours','overload_hours','operating_cost']}
        if e['operating_enabled']:
            work=operating_month(e,side,row,m)
            extra={k:work[k] for k in extra}
            row['_work']=work
            row['admin_hours_saved']=0
        row.update(extra)
        row['cost']+=extra['operating_cost']
        row['contribution']-=extra['operating_cost']
        regional=e.get('regional',{})
        row['regional_cost']=regional.get('extra_monthly_cost',0)+sales*regional.get('extra_cost_per_sale',0)
        row['cost']+=row['regional_cost']; row['contribution']-=row['regional_cost']
        # Period-level positive contribution is a planning tax base, not taxable income.
        # Cumulative accrual permits reversals when a later month offsets earlier gains.
        prior=sum(r['contribution'] for r in rows[:-1])/rooftops
        prior_tax=sum(r.get('estimated_income_tax',0) for r in rows[:-1])/rooftops
        row['estimated_income_tax']=(max(0,prior+row['contribution'])*regional.get('tax_rate',0)/100-prior_tax) if regional.get('tax_enabled') else 0
        row['after_tax_contribution']=row['contribution']-row['estimated_income_tax']
        row['resource_cost']=row['marketing_cost']+row['software_cost']+row['holding_cost']+extra['payroll']+extra['overhead']-extra['cash_savings']+row['regional_cost']
        for key in list(row):
            if key not in ['month','calendar_month','_work']: row[key]*=rooftops
    return rows

