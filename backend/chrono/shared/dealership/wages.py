"""Offline wage observations. Missing regional observations are never invented."""
import json
from pathlib import Path

DATA=json.loads(Path(__file__).with_name('wage_data.json').read_text(encoding='utf-8'))
NAMES={'management':'Management','sales':'Sales','bdc':'BDC','fi':'F&I','advisors':'Service advisors','technicians':'Technicians','parts':'Parts','admin':'Administration','porters':'Porters / detail'}

def benchmarks(country,region):
    rows=[]
    for role,name in NAMES.items():
        occupation=DATA.get(country,{}).get(role,{})
        value=occupation.get('regions',{}).get(region)
        rows.append(dict(role=role,name=name,occupation=occupation.get('occupation','No source loaded'),
                         source=occupation.get('source',''),period=(value or {}).get('period',occupation.get('period','')),
                         median=value['median'] if value else None,
                         status='Published occupation median / role proxy' if value else 'Unavailable; retain editable planning assumption'))
    return rows

def apply_wages(experiment,country,region):
    from .jurisdictions import reference
    floor=reference(country,region)['minimum_wage']
    rates={r['role']:r['median'] for r in benchmarks(country,region)}
    for side in ['baseline','scenario']:
        for role in experiment[side]['operating']['roles']:
            rate=rates.get(role['id'])
            if rate is not None:
                role.update(wage=max(rate,floor),salary=0,commission=0)
