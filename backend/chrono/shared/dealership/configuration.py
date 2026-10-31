"""One configuration pipeline for a dealership, independent of experiment software."""
import copy
from .operating import plan, SIZE_PROFILES
from .jurisdictions import reference, regional_defaults

KINDS=['Franchised New & Used Dealerships','Independent Used-Car Dealerships','Direct-to-Consumer (DTC) Retailers','Buy Here Pay Here (BHPH) / Subprime Lots','Commercial, Fleet, & Specialty Vehicle Dealerships']
ALIASES=dict(zip(['Franchised new & used','Independent used','Luxury franchise','Retail new & pre-owned'],[KINDS[0],KINDS[1],KINDS[0],KINDS[0]]))
USED_ONLY=[KINDS[1],KINDS[3]]
TYPE_NOTES={
 KINDS[0]:'OEM-franchised new and pre-owned sales. CPO, warranty repairs and OEM parts are represented within vehicle/service gross; their individual workflows are not yet separated.',
 KINDS[1]:'Pre-owned only. Auction, trade-in and private-seller acquisition costs belong in vehicle gross and recon budgets.',
 KINDS[2]:'OEM-owned retail and delivery operations. New-focused stock, no third-party finance reserve by default. This models the retail location contribution, not consolidated manufacturer profit. State-specific selling and delivery eligibility must be confirmed.',
 KINDS[3]:'Pre-owned sales with in-house credit. F&I reserve defaults to zero. The financial outlook models aggregate loan-book collections, credit losses and repossession assumptions. These are planning estimates, not loan-level underwriting or accounting profit. Review Financial assumptions for the existing portfolio and losses.',
 KINDS[4]:'Commercial and fleet preset with higher vehicle prices and lower volume. Edit stock, gross and service assumptions for heavy trucks, luxury/exotics or consignment; consignment proceeds are not automatically separated from owned-inventory revenue.'}


def segments_from_profile(p):
    share=p['new_share']/100
    new_stock=round(p['inventory']*share); new_arrivals=round(p['replenishment']*share)
    return {key:dict(inventory=stock,replenishment=arrivals,price=45000 if key=='new' else 28000,
                     gross=p['gross_per_sale'],fi=p.get('fi_gross_per_sale',0),holding=p.get('holding_cost_per_vehicle',0))
            for key,stock,arrivals in [('new',new_stock,new_arrivals),('used',p['inventory']-new_stock,p['replenishment']-new_arrivals)]}

def configure(raw, choices, reset=False):
    from .model import validate
    e=validate(raw); p=e['profile']; old=e['dealership']
    kind=choices.get('kind',old['kind']); kind=ALIASES.get(kind,kind); size=choices.get('size',old['size'])
    country=choices.get('country',p['country']); region=choices.get('region',p['region'])
    if kind not in KINDS or size not in SIZE_PROFILES: raise ValueError('Choose a supported dealership type and size.')
    reference(country,region)
    moved=(country,region)!=(p['country'],p['region'])
    if reset or (kind,size)!=(old['kind'],old['size']):
        e.pop('mix',None)  # Type/size preset changes also rebuild the synthetic mix.
        p.update(copy.deepcopy(SIZE_PROFILES[size]))
        factor=.55 if kind in USED_ONLY else .65 if kind==KINDS[4] else .8 if kind==KINDS[2] else 1
        for k in SIZE_PROFILES[size]: p[k]=round(p[k]*factor)
        p['new_share']=0 if kind in USED_ONLY else 90 if kind==KINDS[2] else 70 if kind==KINDS[4] else 60
        p['gross_per_sale']=5500 if kind==KINDS[4] else 3200
        p['fi_gross_per_sale']=1200; p['holding_cost_per_vehicle']=150
        p['service_gross_per_ro']=220
        e['segments']=segments_from_profile(p)
        luxury=kind==KINDS[4]; canadian=country=='Canada'
        for key,s in e['segments'].items():
            s['price']=(80000 if luxury else 50000) if key=='new' else (50000 if luxury else 30000)
            if not canadian: s['price']=round(s['price']*.8)
            s['gross']=(6000 if luxury else 3000) if key=='new' else (4500 if luxury else 3500)
            s['fi']=0 if kind in [KINDS[2],KINDS[3]] else 1400 if key=='new' else 1100
            if kind==KINDS[3] and key=='used': s.update(price=18000 if canadian else 15000,gross=3500)
        for side in ['baseline','scenario']:
            e[side]['operating']=plan(size)
            if kind in USED_ONLY:
                for r in e[side]['operating']['roles']: r['people']=max(1,round(r['people']*.55))
            e[side].pop('campaigns',None)  # Explicit preset reset replaces the media plan too.
            e[side]['spend']={'small':7000,'medium':18000,'large':36000}[size]*factor
        e['operating_enabled']=True
    if reset or moved or (kind,size)!=(old['kind'],old['size']) or choices.get('apply_wages'):
        from .wages import apply_wages
        apply_wages(e,country,region)
    if moved:
        e['regional']=regional_defaults(country,region)
        p['city']=''
    p.update(type=kind,country=country,region=region,currency='CAD' if country=='Canada' else 'USD')
    e['dealership']=dict(kind=kind,size=size)
    e['rooftops']=choices.get('rooftops',e['rooftops'])
    if 'city' in choices:
        city=choices['city']
        if not isinstance(city,str) or len(city)>100:raise ValueError('Enter a city up to 100 characters.')
        p['city']=city.strip()
    if 'inventory' in choices:
        stock=choices['inventory']
        if type(stock) is not int or not 0<=stock<=10000:raise ValueError('Enter 0–10,000 vehicles per rooftop.')
        new_stock=round(stock*p['new_share']/100)
        e['segments']['new']['inventory']=new_stock
        e['segments']['used']['inventory']=stock-new_stock
        e.pop('mix',None)  # Build the sample settings from the selected opening inventory.

    if 'mix' not in raw: e.pop('mix',None)  # Initialize from the final dealership type.
    return validate(e)
