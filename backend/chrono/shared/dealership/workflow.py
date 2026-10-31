"""Explicit data origins and a user-reviewed baseline, separate from forecast outputs."""
import copy
import json
import math
from datetime import datetime, timezone
LABELS={'simulation':'Full simulation','real':'Real dealership + scenarios','hybrid':'Hybrid: real + synthetic'}
def baseline(e):
    return {**{k:copy.deepcopy(e[k]) for k in ('profile','segments','baseline','regional','rooftops','dealership','operating_enabled','staffing_capacity_enabled')},'finance':copy.deepcopy(e['finance']['baseline'])}
def normalize(raw):
    if raw is None:raw=dict(mode='simulation',selected=False)
    if not isinstance(raw,dict) or raw.get('mode') not in LABELS:raise ValueError('Choose full simulation, real dealership or hybrid.')
    review=raw.get('review');calibration=raw.get('calibration',[])
    if review is not None:
        if not isinstance(review,dict) or not isinstance(review.get('baseline'),dict) or len(json.dumps(review))>150000 or not isinstance(review.get('note'),str) or not 1<=len(review['note'])<=1000:raise ValueError('Invalid baseline review.')
        review=copy.deepcopy(review)
    if not isinstance(calibration,list) or len(calibration)>100:raise ValueError('Invalid data-source register.')
    for r in calibration:
        if not isinstance(r,dict) or any(not isinstance(r.get(k),str) or len(r[k])>1000 for k in ('field','basis','month','revision')) or type(r.get('value')) not in (int,float) or not math.isfinite(r['value']):raise ValueError('Invalid calibrated source.')
    allowed={'rooftops','profile.new_share','profile.service_gross_per_ro','profile.organic_leads','profile.response_rate','profile.appointment_rate','profile.show_rate','profile.close_rate'}|{'segments.'+s+'.'+k for s in ('new','used') for k in ('inventory','price','gross','fi','replenishment')}
    if any(r['field'] not in allowed for r in calibration):raise ValueError('Unsupported source-register field.')
    if raw['mode']=='simulation' and (calibration or review):raise ValueError('This model includes recorded-data lineage. Keep Real dealership or Hybrid; create a fresh Full simulation to start without dealership records.')
    steps=raw.get('setup_steps',[])
    if not isinstance(steps,list) or any(k not in ('path','identity','operations','data','review') for k in steps):raise ValueError('Invalid setup checklist.')
    objective=raw.get('objective','')
    if not isinstance(objective,str) or len(objective)>300:raise ValueError('Keep the scenario question under 300 characters.')
    builder=raw.get('builder_reviews',{})
    if not isinstance(builder,dict) or any(k not in ('identity','inventory','team','facility','software','campaigns','work','economics') or not isinstance(v,str) or len(v)!=16 or any(c not in '0123456789abcdef' for c in v) for k,v in builder.items()):raise ValueError('Invalid builder milestone review.')
    game=raw.get('card_game',dict(deck=['host','caller','analyst'],wins=[]))
    cards={'host','caller','analyst','principal','inventory','people','service','systems','marketing','technician','finance','champion'}
    challenges={'lead-rush','aged-stock','service-peak','month-end'}
    if not isinstance(game,dict):raise ValueError('Invalid card collection.')
    for key,allowed,limit in [('deck',cards,3),('wins',challenges,4)]:
        values=game.get(key)
        if not isinstance(values,list) or len(values)>limit or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):raise ValueError('Invalid card game '+key+'.')
    return dict(card_game=copy.deepcopy({k:game[k] for k in ('deck','wins')}),builder_reviews=copy.deepcopy(builder),setup_steps=list(dict.fromkeys(steps)),setup_complete=raw.get('setup_complete') is True,objective=objective,mode=raw['mode'],selected=raw.get('selected') is True,review=review,calibration=copy.deepcopy(calibration))
def ready(e):
    w=e['workflow'];r=w.get('review')
    return bool(r and r['baseline']==baseline(e) and not e['mix']['inventory'] and not e['mix']['people'])
def require_ready(e):
    if e['workflow']['mode']=='real' and not ready(e):raise ValueError('Review your real-dealership baseline in Data sources & path before running scenarios. Use Hybrid if any baseline inputs are synthetic or estimated.')
def require_synthetic(e):
    if e['workflow']['mode']=='real':raise ValueError('Synthetic data belongs in Full simulation or Hybrid. Change your data path before generating or applying synthetic inputs.')
def review(raw):
    from .model import validate
    e=validate(raw.get('input'));note=raw.get('note','').strip()
    if raw.get('confirmed') is not True or not 10<=len(note)<=1000:raise ValueError('Confirm the baseline review and describe the records and period used (10–1,000 characters).')
    if e['workflow']['mode']!='real':raise ValueError('Baseline confirmation is for the real-dealership path.')
    if e['mix']['inventory'] or e['mix']['people']:raise ValueError('This workspace contains generated populations. Use Hybrid, or remove the synthetic samples before confirming a real-only baseline.')
    e['workflow']['review']=dict(baseline=baseline(e),note=note,at=datetime.now(timezone.utc).isoformat())
    return validate(e)
def source_summary(e):
    w=e.get('workflow',{});return LABELS.get(w.get('mode'),'Legacy simulation assumptions')+' — all scenario outputs are modeled, not actual results.'

def setup(raw):
    from .model import validate
    e=validate(raw.get('input'));w=e['workflow'];step=raw.get('step')
    if step=='finish':
        if not w['selected'] or set(w['setup_steps'])!=set(('path','identity','operations','data','review')):raise ValueError('Review all five setup steps before finishing.')
        require_ready(e)
        w['setup_complete']=True
    elif step in ('path','identity','operations','data','review'):
        if step=='path' and not w['selected']:raise ValueError('Choose and confirm a data path first.')
        if step=='review':require_ready(e)
        if step not in w['setup_steps']:w['setup_steps'].append(step)
    else:raise ValueError('Choose a setup step.')
    return validate(e)
