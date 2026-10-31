"""NXTDeal graph adapter for the hash-pinned, shared Chrono domain model.

No remote data export, historical observations, or second probability calculator.
"""
from copy import deepcopy
import json
from pathlib import Path
from fastapi import HTTPException

from chrono.shared.assumptions import AssumptionEngine
from chrono.shared.dealership.adapter import DealershipModel
from chrono.shared.dealership.model import default_experiment, validate, software
from chrono.shared.dealership.configuration import KINDS, USED_ONLY
from chrono.shared.dealership.jurisdictions import regional_defaults
from chrono.shared.domain import SimulationRequest
from chrono.shared.compute_admission import ComputeBusy
from . import service as lab

MODEL, RUN = 'DealershipLabModel', 'DealershipLabRun'
SHARED_VERSION = json.loads((Path(__file__).parents[2] / 'chrono/shared/MANIFEST.json').read_text())['commit']


def decision_source(model):
    """Promote the saved proposal without certifying modeled figures as actuals."""
    from chrono.shared.dealership import workflow
    promoted = deepcopy(model)
    name = promoted['baseline']['name']
    promoted['baseline'] = deepcopy(promoted['scenario'])
    promoted['baseline']['name'] = name
    promoted['finance']['baseline'] = deepcopy(promoted['finance']['scenario'])
    requires_hybrid = model['workflow']['mode'] == 'real' and workflow.ready(model) and not workflow.ready(promoted)
    return promoted, requires_hybrid


def compile_inputs(w):
    if w.get('model_definition'):
        return validate(deepcopy(w['model_definition']))
    sections = {key: row['values'] for key, row in w['sections'].items()}
    i, stock, team, site, stack, campaign, work, money = [sections[k] for k in lab.SECTIONS]
    e = validate(default_experiment())
    kind = dict(zip(['Franchised new & used','Independent used','OEM direct','BHPH / subprime','Commercial / fleet'], KINDS))[i['kind']]
    country, region = i.get('country','United States'), i.get('region','Texas')
    e['name'] = w['name']
    e['notes'] = 'Compiled from user-reviewed NXTDeal builder assumptions. Full model defaults remain explicit and reviewable.'
    e['profile'].update(name=i['name'], type=kind, country=country, region=region, city=i['city'], currency=i['currency'],
        organic_leads=campaign['leads'], inventory=stock['new_units']+stock['used_units'], replenishment=stock['new_arrivals']+stock['used_arrivals'],
        lead_capacity=10000, sales_capacity=work['sales_capacity'], gross_per_sale=stock['used_gross'],
        response_rate=campaign['response'], appointment_rate=campaign['appointment'], show_rate=campaign['show'], close_rate=campaign['close'],
        new_share=0 if kind in USED_ONLY else (100*stock['new_units']/(stock['new_units']+stock['used_units']) if stock['new_units']+stock['used_units'] else 0),
        service_requests=work['service_requests'], service_capacity=work['service_capacity'], service_gross_per_ro=money['service_gross'])
    e['rooftops'] = i['rooftops']
    e['dealership'] = dict(kind=kind, size='medium')
    e['regional'] = regional_defaults(country, region)
    e['regional'].update(apply_wage_floor=False, tax_enabled=False)
    e['operating_enabled'] = True
    e['staffing_capacity_enabled'] = False
    for side in ('new','used'):
        e['segments'][side].update(inventory=stock[side+'_units'], replenishment=stock[side+'_arrivals'], gross=stock[side+'_gross'], fi=money['fi'], holding=stock['holding'])
    people = dict(sales=team['salespeople'], bdc=team['bdc'], technicians=team['technicians'], advisors=team['advisors'])
    total = sum(people.values())
    if team['payroll'] and not total:
        raise ValueError('Enter staff counts before allocating a payroll budget')
    for side in ('baseline','scenario'):
        e[side]['spend'] = campaign['budget']
        # The media CPL, seasonality and demand volatility remain explicit model
        # assumptions. They are shown in the full calculation-input review.
        e[side]['software'] = [{**software(), 'monthly_cost':stack['cost'], 'adoption':stack['adoption'], 'integration':stack['integration'], 'rationale':stack['stack'] or 'User-entered software budget; no performance lift assumed.'}]
        op = e[side]['operating']
        op['open_days'] = site['days']
        for role in op['roles']:
            role.update(people=people.get(role['id'],0), wage=0, salary=team['payroll']/total if total else 0, commission=0, burden=0, embedded=0,
                        shifts=1, shift_hours=team['hours']/(52/12*5), unpaid_break=0, unavailable=0, cash_realization=stack['cash_realization'])
        op['expenses'] = [dict(name=label,quantity=1,rate=value,scope='rooftop') for label,value in [('Occupancy',site['rent']),('Other overhead',site['overhead'])]]
        e['finance'][side].update(opening_cash=money['cash']*i['rooftops'], debt_principal=money['debt_service']*i['rooftops'], tax_rate=0)
    e.pop('mix',None)
    return validate(e)


class PendingRepository:
    """Collect exact Chrono artifacts; commit to the canonical graph atomically."""
    def __init__(self):
        self.models = {}
        self.runs = []

    def save_model(self, model):
        self.models[model.id] = model.model_dump(mode='json')

    def save_run(self, key, kind, payload):
        self.runs.append(dict(external_id=key, kind=kind, payload=payload))


def run_comparison(actor, baseline_id, proposed_id, baseline_revision, proposed_revision, months, seed, target, request_id, reviewed_inputs=None):
    with lab.LOCK:
        before = lab.serial(lab.workspace(baseline_id, actor))
        after = lab.serial(lab.workspace(proposed_id, actor))
        prior = next((e for e in lab.items(RUN) if e.attributes['owner'] == actor and e.attributes.get('request_id') == request_id), None)
        intent = dict(baseline_id=baseline_id, proposed_id=proposed_id, baseline_revision=baseline_revision, proposed_revision=proposed_revision, months=months, seed=seed, target=target)
        if reviewed_inputs:
            intent['reviewed_inputs'] = deepcopy(reviewed_inputs)
        if prior:
            if prior.attributes['intent'] != intent:
                raise HTTPException(409, 'Request identity was already used for a different comparison')
            return lab.serial(prior)
        if before['revision'] != baseline_revision or after['revision'] != proposed_revision:
            raise HTTPException(409, 'Workspace changed. Reload and review the inputs again.')
        if before['archived'] or after['archived']:
            raise HTTPException(409, 'Restore the workspaces before running a comparison')
        for side, workspace in (('baseline', before), ('proposed', after)):
            if workspace.get('setup_managed') and workspace.get('model_definition'):
                if (reviewed_inputs or {}).get(side) != lab.digest(compile_inputs(workspace)):
                    raise HTTPException(422, 'Load and review the current complete calculation inputs for both plans')
            elif any(not section['reviewed_hash'] for section in workspace['sections'].values()):
                raise HTTPException(422, 'Review all eight builder sections before running scenarios')
    try:
        base, proposed = compile_inputs(before), compile_inputs(after)
        if base['profile']['currency'] != proposed['profile']['currency']:
            raise ValueError('Compare the same currency; no currency conversion is performed')
        at = lab.now()
        request = SimulationRequest.model_validate(dict(entity=proposed_id,as_of=at,known_at=at,horizon=months,paths=100,seed=seed,
            goal=dict(name='Cumulative profit target',target=dict(conditions=[dict(metric='profit',op='gte',value=target)]),
                      outperformance=dict(conditions=[dict(metric='profit',op='gte',value=target+max(1,abs(target)*.2))]),
                      failure=dict(conditions=[dict(metric='cash',op='lt',value=0)]))))
        repo = PendingRepository()
        result = AssumptionEngine(repo,DealershipModel()).compare_assumptions(request,base,proposed)
    except ComputeBusy as exc:
        raise HTTPException(503, str(exc), headers={'Retry-After':'5'}) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with lab.transaction():
        # A concurrent retry may have finished while this computation was running.
        prior = next((e for e in lab.items(RUN) if e.attributes['owner'] == actor and e.attributes.get('request_id') == request_id), None)
        if prior:
            if prior.attributes['intent'] != intent:
                raise HTTPException(409, 'Request identity conflict')
            return lab.serial(prior)
        if lab.workspace(baseline_id,actor).attributes['revision'] != baseline_revision or lab.workspace(proposed_id,actor).attributes['revision'] != proposed_revision:
            raise HTTPException(409, 'Inputs changed during execution. No results saved; review and rerun.')
        for artifact in repo.models.values():
            lab.create('LABM',MODEL,dict(owner=actor,created_at=at.isoformat(),payload=artifact,shared_engine_commit=SHARED_VERSION))
        record = lab.create('LABR',RUN,dict(owner=actor,request_id=request_id,intent=intent,created_at=at.isoformat(),currency=base['profile']['currency'],
            baseline=before,proposed=after,calculation_inputs=dict(baseline=base,proposed=proposed),payload=result,artifacts=repo.runs,shared_engine_commit=SHARED_VERSION))
        # Content differences only; cosmetic names, notes, periods and seeds do
        # not manufacture additional scenario configurations for run quests.
        def substantive(w):
            def clean(value):
                if isinstance(value, dict):
                    return {k:clean(v) for k,v in value.items() if k not in {'name','notes','note','rationale','city','objective','bottleneck','stack','seed','trials','months','workflow'}}
                if isinstance(value, list):
                    return [clean(v) for v in value]
                return value
            return clean(compile_inputs(w))
        if substantive(before) != substantive(after):
            from .engagement import enabled
            if enabled(actor):
                lab.record(lab.profile(actor,True).attributes,'run',lab.digest([substantive(before),substantive(after)]))
        return lab.serial(record)
