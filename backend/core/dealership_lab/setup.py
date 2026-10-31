"""Versioned setup actions using the canonical Composite/Chrono definitions."""
from fastapi import HTTPException
from chrono.shared.dealership import configuration, workflow, earnings
from . import analysis, service as lab


CUSTOMER_FIELDS = [
    ('organic_leads', 'Organic leads per month', 0, 10000, 1, 'Demand & capacity'),
    ('lead_capacity', 'Lead-handling capacity per month', 0, 10000, 1, 'Demand & capacity'),
    ('sales_capacity', 'Vehicle deliveries capacity per month', 0, 10000, 1, 'Demand & capacity'),
    ('market_index', 'Market index (100 = neutral)', 0, 300, 0.1, 'Demand & capacity'),
    ('seasonality', 'Seasonal variation %', 0, 80, 0.1, 'Demand & capacity'),
    ('demand_volatility', 'Demand volatility %', 0, 50, 0.1, 'Demand & capacity'),
    ('response_rate', 'Lead response %', 0, 100, 0.1, 'Sales funnel'),
    ('appointment_rate', 'Appointments from responses %', 0, 100, 0.1, 'Sales funnel'),
    ('show_rate', 'Visits from appointments %', 0, 100, 0.1, 'Sales funnel'),
    ('close_rate', 'Sales from visits %', 0, 100, 0.1, 'Sales funnel'),
    ('new_share', 'New-vehicle demand share %', 0, 100, 0.1, 'Sales funnel'),
    ('service_requests', 'Service requests per month', 0, 100000, 1, 'Service'),
    ('service_capacity', 'Repair-order capacity per month', 0, 100000, 1, 'Service'),
    ('service_gross_per_ro', 'Gross per repair order', 0, 100000, 0.01, 'Service'),
]
SEGMENT_FIELDS = [
    ('inventory', 'Opening vehicles in stock', 0, 10000, 1),
    ('replenishment', 'Monthly vehicle arrivals', 0, 10000, 1),
    ('price', 'Average selling price', 0, 1000000, 0.01),
    ('gross', 'Vehicle gross per sale', -100000, 100000, 0.01),
    ('fi', 'F&I gross per sale', 0, 1000000, 0.01),
    ('holding', 'Monthly carrying cost per vehicle', 0, 1000000, 0.01),
]


FINANCE_LABELS = {
    'opening_cash': ('Opening cash balance', 'Cash & earnings'),
    'other_expense': ('Other monthly expense', 'Cash & earnings'),
    'depreciation': ('Monthly depreciation', 'Cash & earnings'),
    'capex': ('Monthly capital spending', 'Cash & earnings'),
    'debt_principal': ('Monthly debt principal payment', 'Cash & earnings'),
    'owner_draw': ('Monthly owner distributions', 'Cash & earnings'),
    'tax_rate': ('Planning tax rate %', 'Cash & earnings'),
    'opening_receivables': ('Opening loan receivables', 'Existing BHPH portfolio'),
    'existing_term': ('Remaining term on existing loans · months', 'Existing BHPH portfolio'),
    'financed_share': ('Sales financed in-house %', 'New BHPH originations'),
    'down_payment': ('Down payment per financed vehicle', 'New BHPH originations'),
    'apr': ('Customer annual interest rate %', 'New BHPH originations'),
    'term': ('New loan term · months', 'New BHPH originations'),
    'collection_rate': ('Scheduled payments collected %', 'Collections & losses'),
    'monthly_default': ('Monthly principal default %', 'Collections & losses'),
    'recovery_rate': ('Defaulted principal recovered %', 'Collections & losses'),
    'recovery_lag': ('Recovery delay · months', 'Collections & losses'),
    'funding_apr': ('Annual funding interest rate %', 'Collections & losses'),
    'repo_share': ('Defaults involving repossession %', 'Repossession assumptions'),
    'repo_balance': ('Average balance per repossession', 'Repossession assumptions'),
    'repo_cost': ('Cost per repossession', 'Repossession assumptions'),
    'repo_recon': ('Reconditioning per recovered vehicle', 'Repossession assumptions'),
    'repo_sale_fee': ('Sale fees per recovered vehicle', 'Repossession assumptions'),
}


def finance_fields(model):
    eligible = 'BHPH' in model['dealership']['kind']
    return [(key, label, *earnings.LIMITS[key], 1 if key in ('term', 'existing_term', 'recovery_lag') else 0, group)
            for key, (label, group) in FINANCE_LABELS.items() if eligible or group == 'Cash & earnings']


def describe(key, actor):
    with lab.LOCK:
        workspace = lab.serial(lab.workspace(key, actor))
        model = analysis.compile_inputs(workspace)
    return dict(workspace=workspace, input=model, modes=workflow.LABELS,
                kinds=configuration.KINDS, sizes=list(configuration.SIZE_PROFILES),
                baseline_ready=workflow.ready(model),
                source_summary=workflow.source_summary(model), finance_fields=finance_fields(model), customer_fields=CUSTOMER_FIELDS, segment_fields=SEGMENT_FIELDS, used_only=model["dealership"]["kind"] in configuration.USED_ONLY)


def apply(key, actor, revision, action, values):
    with lab.transaction():
        entity = lab.workspace(key, actor)
        if entity.attributes['revision'] != revision or entity.attributes['archived']:
            raise HTTPException(409, 'Reload an active workspace before changing setup')
        model = analysis.compile_inputs(lab.serial(entity))
        try:
            if action == 'path':
                if set(values) != {'mode'} or values['mode'] not in workflow.LABELS:
                    raise ValueError('Choose a supported data path')
                # normalize rejects relabeling recorded lineage as simulation.
                model['workflow'].update(mode=values['mode'], selected=True, setup_complete=False, setup_steps=[])
                model = analysis.validate(model)
            elif action == 'configure':
                allowed = {'kind', 'size', 'country', 'region', 'city', 'rooftops', 'inventory', 'apply_wages', 'reset_confirmed'}
                if set(values) - allowed:
                    raise ValueError('Unsupported dealership setup field')
                reset = any(values.get(k, model['dealership'][k]) != model['dealership'][k] for k in ('kind', 'size'))
                if reset and values.get('reset_confirmed') is not True:
                    raise ValueError('Confirm replacement of preset staffing, stock, campaigns and mix before changing type or size')
                choices = {k: v for k, v in values.items() if k != 'reset_confirmed'}
                model = configuration.configure(model, choices)
                model['workflow']['setup_complete'] = False
                model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s == 'path']
            elif action == 'baseline_review':
                if set(values) != {'note', 'confirmed'} or not isinstance(values['note'], str):
                    raise ValueError('Supply the baseline source note and confirmation')
                model = workflow.review(dict(input=model, **values))
            elif action == 'software':
                if set(values) != {'modules'} or not isinstance(values['modules'], list) or len(values['modules']) > 12:
                    raise ValueError('Supply up to 12 software modules')
                allowed = set(analysis.software())
                if any(not isinstance(m, dict) or set(m) - allowed for m in values['modules']):
                    raise ValueError('Unsupported software assumption field')
                if len(lab.json.dumps(values, allow_nan=False)) > 150000:
                    raise ValueError('Software assumptions exceed the supported size')
                for side in (('baseline', 'scenario') if not entity.attributes.get('parent_id') else ('scenario',)):
                    model[side]['software'] = lab.deepcopy(values['modules'])
                model['workflow']['setup_complete'] = False
                model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('operations', 'review')]
            elif action == 'campaigns':
                if set(values) != {'campaigns', 'saturation_budget'} or not isinstance(values['campaigns'], list):
                    raise ValueError('Supply campaigns and the advertising saturation budget')
                if len(values['campaigns']) > 20 or any(not isinstance(c, dict) or set(c) != {'name', 'budget', 'cpl'} for c in values['campaigns']):
                    raise ValueError('Use up to 20 campaigns with name, monthly budget and cost per lead')
                for side in (('baseline', 'scenario') if not entity.attributes.get('parent_id') else ('scenario',)):
                    model[side]['campaigns'] = lab.deepcopy(values['campaigns'])
                    model[side]['saturation_budget'] = values['saturation_budget']
                model['workflow']['setup_complete'] = False
                model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('operations', 'review')]
            elif action == 'finance':
                allowed = {field[0] for field in finance_fields(model)}
                if set(values) != {'assumptions'} or not isinstance(values['assumptions'], dict) or set(values['assumptions']) != allowed:
                    raise ValueError('Supply only the financial assumptions supported by this dealership type')
                model['finance']['scenario'].update(values['assumptions'])
                if not entity.attributes.get('parent_id'):
                    model['finance']['baseline'] = lab.deepcopy(model['finance']['scenario'])
                model['workflow']['setup_complete'] = False
                model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('data', 'review')]
            elif action == 'customers':
                if set(values) != {'profile', 'segments'} or not isinstance(values['profile'], dict):
                    raise ValueError('Supply customer assumptions and both inventory segments')
                if set(values['profile']) != {f[0] for f in CUSTOMER_FIELDS}:
                    raise ValueError('Supply the supported customer and service assumptions')
                segments = values['segments']
                if not isinstance(segments, dict) or set(segments) != {'new', 'used'} or any(not isinstance(v, dict) or set(v) != {f[0] for f in SEGMENT_FIELDS} for v in segments.values()):
                    raise ValueError('Supply complete new and used inventory assumptions')
                model['profile'].update(values['profile'])
                model['segments'] = lab.deepcopy(segments)
                model['workflow']['setup_complete'] = False
                model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('data', 'review')]
            elif action == 'operating':
                model = operating_model(model, values, not entity.attributes.get('parent_id'))
            elif action == 'step':
                if set(values) != {'step'} or not isinstance(values['step'], str):
                    raise ValueError('Choose a setup step')
                model = workflow.setup(dict(input=model, step=values['step']))
            else:
                raise ValueError('Unsupported setup action')
            model = analysis.validate(model)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if entity.attributes.get('model_definition') != model:
            entity.attributes.update(model_definition=model, setup_managed=True, revision=revision + 1, updated_at=lab.now().isoformat())
            lab.save_version(entity)
        return lab.serial(entity)


def operating_model(model, values, current):
    """Shared draft/save transform; deletion also removes dangling software job assumptions."""
    if set(values) != {'operating', 'operating_enabled', 'staffing_capacity_enabled'}:
        raise ValueError('Supply the operating plan and its two calculation settings')
    if any(type(values[k]) is not bool for k in ('operating_enabled', 'staffing_capacity_enabled')):
        raise ValueError('Calculation settings must be true or false')
    if len(lab.json.dumps(values, allow_nan=False)) > 200000:
        raise ValueError('Operating plan exceeds the supported size')
    for side in (('baseline', 'scenario') if current else ('scenario',)):
        previous = {t['id'] for t in model[side]['operating']['tasks']}
        model[side]['operating'] = lab.deepcopy(values['operating'])
        # Validate row shape and references before examining task IDs.
        model = analysis.validate(model)
        removed = previous - {t['id'] for t in model[side]['operating']['tasks']}
        for module in model[side]['software']:
            for task in removed:
                module.get('task_savings', {}).pop(task, None)
    for setting in ('operating_enabled', 'staffing_capacity_enabled'):
        model[setting] = values[setting]
    model['workflow']['setup_complete'] = False
    model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('operations', 'review')]
    return analysis.validate(model)


def operating_preview(key, actor, revision, values):
    from chrono.shared.dealership.model import simulate_one
    with lab.LOCK:
        workspace = lab.serial(lab.workspace(key, actor))
        if workspace['revision'] != revision or workspace['archived']:
            raise HTTPException(409, 'Reload an active workspace before previewing')
        saved = analysis.compile_inputs(workspace)
    try:
        draft = operating_model(lab.deepcopy(saved), values, not workspace.get('parent_id'))
        # This is one illustrative month using canonical mechanics, never a
        # probabilistic comparison or an independently calculated browser total.
        previews = {}
        for name, inputs in [('saved', saved), ('draft', draft)]:
            workflow.require_ready(inputs)
            model = lab.deepcopy(inputs)
            model.update(months=1, operating_enabled=True)
            # _work is the canonical per-rooftop detail before output rollup.
            # Reusing the rolled-up activity row would double group workloads.
            previews[name] = simulate_one(model, 'scenario', 0)[0]['_work']
        return dict(**previews, currency=draft['profile']['currency'], rooftops=draft['rooftops'],
                    revision=revision, input_hash=lab.digest(draft), shared_engine_commit=analysis.SHARED_VERSION,
                    operating_enabled=draft['operating_enabled'],
                    basis='One illustrative month, per rooftop (group costs apportioned). Not a forecast or saved comparison. Costs shown even when operating costs are disabled.')
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
