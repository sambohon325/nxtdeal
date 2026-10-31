"""Staff-only learning and scenario workspaces; no execution or delivery side effects."""
from typing import Literal
import math
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from api.deps import _authenticate
from core.dealership_lab import service as lab
from core.dealership_lab import analysis, notebooks, reports, policy, setup, mix, goals, references, experiment_import
from chrono.shared.dealership import decisions, workflow

router = APIRouter(prefix='/dealership-lab', tags=['Dealership lab'])


extras_router = APIRouter(prefix='/extras', tags=['Extras'])


def actor(authorization, require_lab=True):
    payload, error = _authenticate(authorization)
    if error:
        raise HTTPException(401, 'Staff sign-in required')
    if payload.get('role') not in {'ADMIN', 'OPERATIONS', 'SALES', 'MARKETING', 'SERVICE', 'FINANCE', 'BDC'} or not payload.get('employee_id'):
        raise HTTPException(403, 'Staff access required')
    if require_lab:
        policy.require_enabled()
    return payload['employee_id']


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Create(Body):
    name: str = Field(min_length=1, max_length=100)
    source_id: str | None = None


class ExperimentPreview(Body):
    content: str = Field(min_length=2, max_length=1_000_000)


class ExperimentImport(Body):
    preview_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)


@router.post('/experiment-import/preview')
def experiment_preview(body: ExperimentPreview, authorization: str | None = Header(default=None)):
    return experiment_import.preview(actor(authorization), body.content)


@router.post('/experiment-import/save')
def experiment_save(body: ExperimentImport, authorization: str | None = Header(default=None)):
    return experiment_import.adopt(actor(authorization), body.preview_id, body.name)


class Section(Body):
    revision: int = Field(ge=1, strict=True)
    values: dict = Field(max_length=12)
    basis: Literal['assumed', 'user_reported'] = 'assumed'
    note: str = Field(max_length=1000)
    reviewed: bool = False


class Equip(Body):
    item: str = Field(max_length=80)


class Deck(Body):
    cards: list[str] = Field(min_length=3, max_length=3)


class Pack(Body):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9-]{16,80}$')


class Revision(Body):
    revision: int = Field(ge=1, strict=True)


class RecoverVersion(Revision):
    name: str = Field(min_length=1, max_length=100)
    request_id: str = Field(pattern=r'^[a-zA-Z0-9-]{16,80}$')


class Game(Body):
    checkpoint: dict | None = None


class DetailedModel(Revision):
    definition: dict | None


class GoalPreview(Revision):
    metric: Literal['vehicle_revenue','contribution']
    target: float = Field(gt=0, le=100000000, allow_inf_nan=False)
    months: int = Field(default=12, ge=1, le=36, strict=True)
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)
    sales_per_person: float = Field(default=10, ge=1, le=100, allow_inf_nan=False)


class GoalAdopt(Revision):
    preview_id: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=100)


@router.post('/workspaces/{key}/goals/preview')
def goal_preview(key: str, body: GoalPreview, authorization: str | None = Header(default=None)):
    return goals.preview(key, actor(authorization), **body.model_dump())


@router.get('/workspaces/{key}/goals')
def goal_history(key: str, authorization: str | None = Header(default=None)):
    return goals.history(key, actor(authorization))


@router.get('/workspaces/{key}/goals/{preview_id}')
def goal_read(key: str, preview_id: str, authorization: str | None = Header(default=None)):
    return goals.read(key, actor(authorization), preview_id)


@router.post('/workspaces/{key}/goals/adopt')
def goal_adopt(key: str, body: GoalAdopt, authorization: str | None = Header(default=None)):
    return goals.adopt(key, actor(authorization), **body.model_dump())


class MixChange(Revision):
    draft: dict
    action: Literal['save-draft','generate','random-unlocked','random-all','apply-inventory','apply-customers']
    scope: Literal['both','customers','inventory'] = 'both'
    token: str | None = Field(default=None, max_length=64)


@router.get('/workspaces/{key}/mix')
def mix_state(key: str, authorization: str | None = Header(default=None)):
    return mix.describe(key, actor(authorization))


@router.post('/workspaces/{key}/mix/preview')
def mix_preview(key: str, body: MixChange, authorization: str | None = Header(default=None)):
    return mix.change(key, actor(authorization), **body.model_dump())


@router.post('/workspaces/{key}/mix/save')
def mix_save(key: str, body: MixChange, authorization: str | None = Header(default=None)):
    return mix.change(key, actor(authorization), commit=True, **body.model_dump())


class SetupAction(Revision):
    action: Literal['path', 'configure', 'baseline_review', 'step', 'operating', 'customers', 'finance', 'campaigns', 'software']
    values: dict = Field(max_length=12)


@router.get('/workspaces/{key}/setup')
def setup_view(key: str, authorization: str | None = Header(default=None)):
    return setup.describe(key, actor(authorization))


@router.post('/workspaces/{key}/setup')
def setup_action(key: str, body: SetupAction, authorization: str | None = Header(default=None)):
    return setup.apply(key, actor(authorization), body.revision, body.action, body.values)


class OperatingPreview(Revision):
    values: dict = Field(max_length=3)


@router.post('/workspaces/{key}/operating-preview')
def operating_preview(key: str, body: OperatingPreview, authorization: str | None = Header(default=None)):
    return setup.operating_preview(key, actor(authorization), body.revision, body.values)


@router.get('/workspaces/{key}/references')
def public_references(key: str, revision: int, authorization: str | None = Header(default=None)):
    return references.describe(key, actor(authorization), revision)


@router.get('/software-catalog')
def software_catalog(authorization: str | None = Header(default=None)):
    actor(authorization)
    from chrono.shared.dealership import catalogue
    return dict(products=catalogue.CATALOG, effects=catalogue.EFFECT_LABELS,
                version=catalogue.CATALOGUE_VERSION, checked=catalogue.RESEARCH_DATE,
                templates={p['id']: analysis.software(p['id']) for p in catalogue.CATALOG})


class SoftwareEstimate(Body):
    vendor: str = Field(max_length=100)
    case: Literal['downside', 'no-benefit', 'cautious', 'working', 'optimistic']


@router.post('/software-estimate')
def software_estimate(body: SoftwareEstimate, authorization: str | None = Header(default=None)):
    actor(authorization)
    from chrono.shared.dealership import catalogue
    if not any(p['id'] == body.vendor for p in catalogue.CATALOG):
        raise HTTPException(422, 'Choose a catalogue product')
    try:
        return catalogue.estimated_module(body.vendor, body.case)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class Run(Body):
    baseline_id: str = Field(max_length=100)
    proposed_id: str = Field(max_length=100)
    baseline_revision: int = Field(ge=1, strict=True)
    proposed_revision: int = Field(ge=1, strict=True)
    months: int = Field(default=12, ge=1, le=36, strict=True)
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)
    target: float = Field(default=0, ge=-1e9, le=1e9, allow_inf_nan=False)
    request_id: str = Field(pattern=r'^[a-zA-Z0-9-]{16,80}$')
    reviewed_inputs: dict[Literal['baseline', 'proposed'], str] = Field(default_factory=dict, max_length=2)


class Decision(Revision):
    acknowledge_hybrid: bool = Field(default=False, strict=True)
    name: str = Field(min_length=1,max_length=100)
    decision: str = Field(max_length=40)
    values: dict = Field(max_length=10)
    implementation_cost: float = Field(default=0,ge=0,le=1000000,allow_inf_nan=False)
    request_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9-]{16,80}$')


@router.get('/decisions')
def decision_catalog(authorization: str | None = Header(default=None)):
    actor(authorization)
    return {'decisions':decisions.catalog()}


@router.post('/workspaces/{key}/decisions')
def decision_option(key: str, body: Decision, authorization: str | None = Header(default=None)):
    who=actor(authorization)
    with lab.transaction():
        source=lab.workspace(key,who)
        intent = dict(source_id=key, **body.model_dump(exclude={'request_id', 'acknowledge_hybrid'}))
        if body.acknowledge_hybrid:
            intent['acknowledge_hybrid'] = True
        if body.request_id:
            previous = next((w for w in lab.items(lab.WORKSPACE) if w.attributes['owner'] == who
                             and w.attributes.get('decision_request_id') == body.request_id), None)
            if previous:
                if previous.attributes.get('decision_intent') != intent:
                    raise HTTPException(409, 'Decision request already used for different inputs')
                return lab.serial(previous)
        if source.attributes['revision']!=body.revision or source.attributes['archived']:
            raise HTTPException(409,'Reload an active workspace before creating an option')
        try:
            e=analysis.compile_inputs(lab.serial(source))
            workflow.require_ready(e)
            e, requires_hybrid = analysis.decision_source(e)
            if requires_hybrid:
                if not body.acknowledge_hybrid:
                    raise ValueError('This starting option contains modeled changes. Confirm a separate Hybrid option to continue; its source review cannot certify those changes as actual records.')
                e['workflow'] = workflow.normalize({**e['workflow'], 'mode':'hybrid', 'setup_complete':False,
                    'setup_steps':[s for s in e['workflow']['setup_steps'] if s not in ('data','review')]})
            definition=decisions.prepare(dict(input=e,**body.model_dump(exclude={'request_id', 'acknowledge_hybrid'})))
            if body.decision == 'advertising' and 'campaigns' in e['baseline']:
                # The template edits spend, while canonical validation derives it
                # from campaigns. Express the requested total as one explicitly
                # combined campaign using the source's canonical blended CPL.
                definition['scenario']['campaigns'] = [dict(
                    name='Decision advertising budget (combined source lead cost)',
                    budget=body.values['spend'], cpl=e['baseline']['cpl'])]
                definition = analysis.validate(definition)
        except (ValueError,TypeError) as exc:
            raise HTTPException(422,str(exc)) from exc
        attrs=lab.deepcopy(source.attributes)
        for field in ('decision_request_id', 'decision_intent', 'recovery_request_id', 'recovery_intent', 'recovered_from', 'import_preview_id', 'import_name'):
            attrs.pop(field, None)
        attrs.update(name=body.name,parent_id=key,revision=1,archived=False,model_definition=definition,created_at=lab.now().isoformat(),updated_at=lab.now().isoformat())
        if body.request_id:
            attrs.update(decision_request_id=body.request_id, decision_intent=intent)
        option=lab.create('LABW',lab.WORKSPACE,attrs)
        lab.save_version(option)
        return lab.serial(option)


@router.get('/workspaces/{key}/model')
def model_inputs(key: str, authorization: str | None = Header(default=None)):
    with lab.LOCK:
        w = lab.serial(lab.workspace(key,actor(authorization)))
    try:
        compiled = analysis.compile_inputs(w)
        return dict(decision_requires_hybrid=analysis.decision_source(compiled)[1],input=compiled,input_hash=lab.digest(compiled),shared_engine_commit=analysis.SHARED_VERSION,custom=w.get('model_definition') is not None,
                    limits=['Explicit assumptions, not a historical forecast or verified peer benchmark.',
                            'Compact builder budgets and counts are per rooftop. Detailed role/expense scopes can be group-wide; detailed finance balances and cash payments are group totals. No FX conversion.',
                            'The compact builder keeps source model defaults for vehicle prices, paid-media CPL, seasonality, demand volatility and task durations. Review them before executing.',
                            'City, bay count, recon days, narrative objectives and software descriptions are descriptive; explicit sales and RO capacity drive throughput. No unverified software lift is assumed.',
                            'A detailed model overrides compact builder calculations until explicitly reset.'])
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.put('/workspaces/{key}/model')
def set_model(key: str, body: DetailedModel, authorization: str | None = Header(default=None)):
    who = actor(authorization)
    try:
        if body.definition and len(lab.json.dumps(body.definition, allow_nan=False)) > 250000:
            raise ValueError('Model input exceeds the supported size')
        value = analysis.validate(body.definition) if body.definition else None
    except (ValueError, TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc
    with lab.transaction():
        e = lab.workspace(key,who)
        if e.attributes['revision'] != body.revision or e.attributes['archived']:
            raise HTTPException(409,'Reload an active workspace before editing')
        e.attributes.update(model_definition=value,revision=body.revision+1,updated_at=lab.now().isoformat())
        lab.save_version(e)
        return lab.serial(e)


@router.post('/runs')
def run(body: Run, authorization: str | None = Header(default=None)):
    return analysis.run_comparison(actor(authorization), **body.model_dump())


@router.get('/runs')
def runs(authorization: str | None = Header(default=None)):
    who = actor(authorization)
    with lab.LOCK:
        return {'runs':[{'id':e.id,**{k:lab.deepcopy(e.attributes[k]) for k in ['intent','created_at','currency','shared_engine_commit']}} for e in lab.items(analysis.RUN) if e.attributes['owner']==who]}


@router.get('/runs/{key}')
def saved_run(key: str, authorization: str | None = Header(default=None)):
    who = actor(authorization)
    with lab.LOCK:
        e = lab.ledger.get_entity(key)
        if not e or e.entity_type != analysis.RUN or e.attributes['owner'] != who:
            raise HTTPException(404,'Run not found')
        return lab.serial(e)


@router.get('/runs/{key}/finance-detail')
def finance_detail(key: str, authorization: str | None = Header(default=None), include_register: bool = False):
    """One reproducible illustrative path; never substitute for saved run bands."""
    from chrono.shared.dealership.model import simulate_one
    from chrono.shared.dealership.earnings import cashflow
    who = actor(authorization)
    with lab.LOCK:
        entity = lab.ledger.get_entity(key)
        if not entity or entity.entity_type != analysis.RUN or entity.attributes['owner'] != who:
            raise HTTPException(404, 'Run not found')
        run = lab.serial(entity)
        from core.dealership_lab.replay import unchanged_bundle
        compatible = run['shared_engine_commit'] != analysis.SHARED_VERSION
        if compatible and not unchanged_bundle(run['shared_engine_commit']):
            raise HTTPException(409, 'This historical engine version is unavailable for detail replay. Use the saved result export.')
        inputs = {side: lab.deepcopy(notebooks.frozen_input(run, side)) for side in ('baseline', 'proposed')}
    result = {}
    for side, model in inputs.items():
        model.update(months=run['intent']['months'], seed=run['intent']['seed'], trials=100)
        model = analysis.validate(model)
        rows = simulate_one(model, 'scenario', 0)
        result[side] = dict(monthly=cashflow(rows, model, 'scenario'),
                            assumptions=model['finance']['scenario'], input_hash=lab.digest(model))
        if include_register:
            from chrono.shared.dealership.register import sample_register
            register = sample_register(model, rows, 'scenario')
            # Monthly cash flows already appear alongside this register. Reuse the same path.
            register.pop('monthly')
            result[side]['register'] = register
    return dict(run_id=key, currency=run['currency'], shared_engine_commit=run['shared_engine_commit'], replay_engine_commit=analysis.SHARED_VERSION, compatibility='verified unchanged prior bundle' if compatible else 'exact commit',
                seed=run['intent']['seed'], trial=0, months=run['intent']['months'], sides=result,
                basis='Illustrative trial 0 replay from frozen inputs using saved engine mechanics; any cross-commit replay requires all prior bundled source files to match their recorded SHA-256 hashes. Monthly flows and ending balances are group totals. Not the median, expected result, accounting statement, or actual collections.')


@extras_router.put('/game')
@router.put('/game')
def save_game(body: Game, authorization: str | None = Header(default=None)):
    """Personal cosmetic game checkpoint, explicitly not an analysis or XP award.

Like the source game's browser saves, completion is client-reported. No operational
record, permission, forecast or progress XP can be changed through this endpoint.
"""
    who = actor(authorization, require_lab=False)
    state = body.checkpoint
    if state is not None:
        try:
            encoded = lab.json.dumps(state, allow_nan=False)
        except (ValueError, TypeError):
            raise HTTPException(422, 'Invalid game checkpoint')
        if not isinstance(state.get('id'),str) or not isinstance(state.get('status'),str):
            raise HTTPException(422, 'Invalid game checkpoint')
        if len(encoded) > 40000 or state.get('version') != 2 or state.get('id') not in {c['id'] for c in lab.CATALOG['challenges']} or state.get('status') not in {'playing', 'won', 'lost'}:
            raise HTTPException(422, 'Invalid game checkpoint')
        if not isinstance(state.get('team'), list) or len(state['team']) != 3 or any(not isinstance(c, dict) or not isinstance(c.get('id'),str) or c.get('id') not in lab.snapshot(who)['unlocked'] for c in state['team']):
            raise HTTPException(422, 'Use three unlocked crew cards')
        def invalid():
            raise HTTPException(422, 'Invalid game checkpoint')
        def number(obj, key, low, high):
            v = obj.get(key)
            if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
                invalid()
        for key, hi in [('active', 2), ('turns', 36), ('round', 37), ('tutorial', 4), ('repeat', 36), ('guardChain', 36), ('cover', 2)]:
            number(state, key, 0, hi)
            if type(state[key]) is not int:
                invalid()
        if type(state.get('practice')) is not bool or not isinstance(state.get('foes'), list) or len(state['foes']) != (1 if state['practice'] else 3):
            invalid()
        number(state, 'enemy', 0, len(state['foes']) if state['status'] == 'won' else len(state['foes']) - 1)
        if type(state['enemy']) is not int or len({c['id'] for c in state['team']}) != 3:
            invalid()
        if not isinstance(state.get('log'), list) or len(state['log']) > 250 or any(not isinstance(s, str) or len(s) > 1000 for s in state['log']):
            invalid()
        if state.get('last') is not None and (not isinstance(state['last'], dict) or not isinstance(state['last'].get('id'), str) or not isinstance(state['last'].get('kind'), str)):
            invalid()
        for card in state['team']:
            canonical = next(c for c in lab.CATALOG['cards'] if c['id'] == card['id'])
            for key in ['name', 'job', 'dept', 'role', 'cost', 'move', 'lesson', 'rarity']:
                if card.get(key) != canonical.get(key):
                    invalid()
            if not isinstance(card.get('stats'), list) or len(card['stats']) != 3 or any(type(v) is not int or not 0 <= v <= 20 for v in card['stats']):
                invalid()
            for key, hi in [('hp', 100), ('max', 100), ('stamina', 5), ('cooldown', 4)]:
                number(card, key, 0, hi)
        for foe in state['foes']:
            if not isinstance(foe, dict):
                invalid()
            for key in ['id', 'name', 'type', 'story', 'dept']:
                if not isinstance(foe.get(key), str) or len(foe[key]) > 500:
                    invalid()
            for key, hi in [('hp', 200), ('max', 200), ('power', 100), ('weak', 2), ('step', 36), ('heals', 36)]:
                number(foe, key, 0, hi)
            if type(foe['weak']) is not int or not isinstance(foe.get('pattern'), list) or not 1 <= len(foe['pattern']) <= 4 or any(x not in ['pressure', 'recover', 'break', 'drain', 'fortify'] for x in foe['pattern']):
                invalid()
            if foe.get('exposed') is not None:
                if not isinstance(foe['exposed'], dict) or not isinstance(foe['exposed'].get('owner'), str):
                    invalid()
                number(foe['exposed'], 'ttl', 0, 3)
    with lab.transaction():
        p = lab.profile(who, True).attributes
        p['game_checkpoint'] = lab.deepcopy(state)
        if state and state['status'] == 'won' and state.get('practice') is False:
            p['game_wins'] = list(dict.fromkeys([*p.get('game_wins', []), state['id']]))
        return lab.snapshot(who)


@router.get('')
def overview(authorization: str | None = Header(default=None)):
    who = actor(authorization)
    with lab.LOCK:
        return dict(catalog=lab.CATALOG, sections=lab.SECTIONS, progress=lab.snapshot(who), workspaces=[lab.serial(e) for e in lab.items(lab.WORKSPACE) if e.attributes['owner'] == who], analysis=dict(status='assumption_scenarios', reason='Dealership scenarios use the shared Chrono engine. Monthly report scenarios and reviewed unit-economics calibration share that engine. Connected peer benchmarks are not available.',shared_engine_commit=analysis.SHARED_VERSION))


@router.post('/workspaces')
def create(body: Create, authorization: str | None = Header(default=None)):
    return lab.new_workspace(actor(authorization), body.name, body.source_id)


@router.put('/workspaces/{key}/sections/{section}')
def save_section(key: str, section: str, body: Section, authorization: str | None = Header(default=None)):
    return lab.save_section(key, actor(authorization), section, **body.model_dump())


@router.get('/workspaces/{key}/versions')
def versions(key: str, authorization: str | None = Header(default=None)):
    with lab.LOCK:
        lab.workspace(key, actor(authorization))
        return {'versions': [lab.serial(e) for e in lab.items(lab.VERSION) if e.attributes['workspace_id'] == key]}


@router.post('/workspaces/{key}/archive')
def archive(key: str, body: Revision, authorization: str | None = Header(default=None)):
    with lab.transaction():
        e = lab.workspace(key, actor(authorization))
        if e.attributes['revision'] != body.revision:
            raise HTTPException(409, 'Workspace changed. Reload before saving.')
        e.attributes['archived'] = not e.attributes['archived']
        e.attributes['revision'] += 1
        e.attributes['updated_at'] = lab.now().isoformat()
        lab.save_version(e)
        return lab.serial(e)


@router.post('/workspaces/{key}/versions/{version_id}/copy')
def recover_version(key: str, version_id: str, body: RecoverVersion, authorization: str | None = Header(default=None)):
    return lab.copy_version(key, actor(authorization), version_id, **body.model_dump())


@extras_router.post('/progress/equip')
@router.post('/progress/equip')
def equip(body: Equip, authorization: str | None = Header(default=None)):
    who = actor(authorization, require_lab=False)
    with lab.transaction():
        item = next((x for x in lab.CATALOG['cosmetics'] if x['id'] == body.item), None)
        if not item or item['level'] > lab.snapshot(who)['level']:
            raise HTTPException(409, 'Reach the required level before equipping this cosmetic')
        lab.profile(who, True).attributes['equipped'][item['kind']] = item['id']
        return lab.snapshot(who)


@extras_router.post('/progress/deck')
@router.post('/progress/deck')
def deck(body: Deck, authorization: str | None = Header(default=None)):
    who = actor(authorization, require_lab=False)
    with lab.transaction():
        unlocked = lab.snapshot(who)['unlocked']
        cards = [c for c in lab.CATALOG['cards'] if c['id'] in body.cards]
        if len(cards) != 3 or any(k not in unlocked for k in body.cards) or sum(c['cost'] for c in cards) > 8:
            raise HTTPException(422, 'Choose three different unlocked cards with at most 8 team points')
        lab.profile(who, True).attributes['deck'] = body.cards
        return lab.snapshot(who)


@extras_router.post('/packs/open')
@router.post('/packs/open')
def open_pack(body: Pack, authorization: str | None = Header(default=None)):
    return lab.open_pack(actor(authorization, require_lab=False), body.request_id)


@extras_router.post('/packs/equip')
@router.post('/packs/equip')
def equip_variant(body: Equip, authorization: str | None = Header(default=None)):
    who = actor(authorization, require_lab=False)
    with lab.transaction():
        variant = next((x for x in lab.CATALOG['variants'] if x['id'] == body.item), None)
        if not variant or body.item not in lab.snapshot(who)['packs']['owned']:
            raise HTTPException(409, 'Collect the edition before equipping it')
        lab.profile(who, True).attributes['variants'][variant['base']] = body.item
        return lab.snapshot(who)


class NotebookCreate(Body):
    run_id: str = Field(max_length=100)
    department: str = Field(max_length=40)
    kind: Literal['workbook','procedure']


class NotebookSave(Revision):
    action: Literal['save','lock','revise','upgrade-checkpoints']='save'
    fields: dict


@router.get('/notebooks')
def notebook_list(authorization: str | None = Header(default=None)):
    who=actor(authorization)
    with lab.LOCK:
        owned=[e for e in lab.items(notebooks.BOOK) if e.attributes['owner']==who]
        return dict(catalog=notebooks.CATALOG,notebooks=[lab.serial(e) for e in owned],review_states={e.id:notebooks.review_state(e,who) for e in owned})


@router.post('/notebooks')
def notebook_create(body: NotebookCreate,authorization: str | None = Header(default=None)):
    return notebooks.create(actor(authorization),**body.model_dump())


@router.put('/notebooks/{key}')
def notebook_save(key: str,body: NotebookSave,authorization: str | None = Header(default=None)):
    return notebooks.save(actor(authorization),key,**body.model_dump())


@router.get('/notebooks/{key}/export')
def notebook_export(key: str, revision: int, authorization: str | None = Header(default=None)):
    from core.dealership_lab.notebook_export import document
    return document(key,actor(authorization),revision)


@router.get('/notebooks/{key}/history')
def notebook_history(key: str,authorization: str | None = Header(default=None)):
    who=actor(authorization)
    with lab.LOCK:
        notebooks.get(key,who)
        return {'versions':[lab.serial(e) for e in lab.items(notebooks.HISTORY) if e.attributes['notebook_id']==key and e.attributes['owner']==who]}


class ReportPreview(Body):
    revision: int = Field(ge=0)
    workspace_revision: int = Field(ge=1)
    csv: str = Field(min_length=1,max_length=750000)
    mapping: dict[str,str] | None = None
    source: str = Field(min_length=10,max_length=500)


class ReportCommit(ReportPreview):
    token: str = Field(min_length=64,max_length=64)
    acknowledge: bool
    request_id: str = Field(min_length=10,max_length=100)


class ReportOutlook(Body):
    revision: int = Field(ge=1)
    metric: str = Field(max_length=60)
    rooftop: str | None = Field(default=None,max_length=80)
    months: int = Field(default=6,ge=1,le=12)
    seed: int = Field(default=42,ge=0,le=4294967295)
    target: float = Field(ge=-1e12,le=1e12,allow_inf_nan=False)
    failure: float = Field(ge=-1e12,le=1e12,allow_inf_nan=False)
    request_id: str = Field(min_length=10,max_length=100)


@router.get('/workspaces/{key}/reports')
def report_view(key: str,authorization: str | None = Header(default=None)):
    return reports.view(key,actor(authorization))


@router.post('/workspaces/{key}/reports/preview')
def report_preview(key: str,body: ReportPreview,authorization: str | None = Header(default=None)):
    return reports.preview(key,actor(authorization),**body.model_dump())


@router.post('/workspaces/{key}/reports/import')
def report_import(key: str,body: ReportCommit,authorization: str | None = Header(default=None)):
    return reports.commit(key,actor(authorization),**body.model_dump())


@router.post('/workspaces/{key}/reports/outlook')
def report_outlook(key: str,body: ReportOutlook,authorization: str | None = Header(default=None)):
    return reports.outlook(key,actor(authorization),**body.model_dump())


class Calibration(Body):
    revision: int = Field(ge=1)
    workspace_revision: int = Field(ge=1)
    rooftop: str | None = Field(default=None,max_length=80)


class CalibrationSave(Calibration):
    token: str = Field(min_length=64,max_length=64)
    name: str = Field(min_length=1,max_length=100)


@router.post('/workspaces/{key}/reports/calibration')
def report_calibration(key: str,body: Calibration,authorization: str | None = Header(default=None)):
    return reports.calibration(key,actor(authorization),**body.model_dump())


@router.post('/workspaces/{key}/reports/calibrated-option')
def report_calibrated_option(key: str,body: CalibrationSave,authorization: str | None = Header(default=None)):
    return reports.calibrated_option(key,actor(authorization),**body.model_dump())


class ReportInspect(Body):
    csv: str = Field(min_length=1,max_length=750000)


@router.post('/workspaces/{key}/reports/inspect')
def report_inspect(key: str,body: ReportInspect,authorization: str | None = Header(default=None)):
    with lab.LOCK:lab.workspace(key,actor(authorization))
    try:return reports.reported.inspect_csv(body.csv)[0]
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc


@extras_router.get('')
def extras_index(authorization: str | None = Header(default=None)):
    who=actor(authorization, require_lab=False)
    with lab.LOCK:
        return dict(catalog=lab.CATALOG, sections=lab.SECTIONS, progress=lab.snapshot(who), workspaces=[], analysis={})


class LearningAnswer(Body):
    answer: int = Field(ge=0, le=2, strict=True)


@extras_router.get('/progress')
def shared_progress(authorization: str | None = Header(default=None)):
    with lab.LOCK:
        return lab.snapshot(actor(authorization, require_lab=False))


@extras_router.get('/learning')
def learning_catalog(authorization: str | None = Header(default=None)):
    from core.dealership_lab import learning
    with lab.LOCK:
        return learning.catalog(actor(authorization, require_lab=False))


@extras_router.post('/learning/{key}')
def complete_learning(key: str, body: LearningAnswer, authorization: str | None = Header(default=None)):
    from core.dealership_lab import learning
    return learning.complete(actor(authorization, require_lab=False), key, body.answer)


@extras_router.get('/work-milestones')
def work_milestones(authorization: str | None = Header(default=None)):
    from core.dealership_lab import learning
    with lab.LOCK:
        return learning.work_milestones(actor(authorization, require_lab=False))


@extras_router.post('/work-milestones/claim')
def claim_work_milestones(body: Body, authorization: str | None = Header(default=None)):
    from core.dealership_lab import learning
    who = actor(authorization, require_lab=False)
    with lab.transaction():
        return learning.work_milestones(who, claim=True)

class PeriodPrepare(Revision):
    report_revision: int = Field(ge=0,strict=True)

class PeriodUpdate(Revision):
    action: Literal['save','publish']
    notes: str = Field(max_length=12000)
    reviewed: bool = False

def review_actor(authorization, required=False):
    who=actor(authorization)
    payload,_=_authenticate(authorization)
    manage=payload.get('role') in {'ADMIN','OPERATIONS'}
    if required and not manage:raise HTTPException(403,'Admin or operations role required to prepare and publish reviews')
    return who,manage

@router.get('/workspaces/{key}/period-reviews')
def period_reviews(key: str,authorization: str | None = Header(default=None)):
    from core.dealership_lab import reviews
    who,manage=review_actor(authorization)
    return reviews.listing(key,who,manage)

@router.post('/workspaces/{key}/period-reviews/prepare')
def period_prepare(key: str,body: PeriodPrepare,authorization: str | None = Header(default=None)):
    from core.dealership_lab import reviews
    who,_=review_actor(authorization,True)
    return reviews.prepare(key,who,**body.model_dump())

@router.put('/period-reviews/{key}')
def period_update(key: str,body: PeriodUpdate,authorization: str | None = Header(default=None)):
    from core.dealership_lab import reviews
    who,_=review_actor(authorization,True)
    return reviews.update(key,who,**body.model_dump())

@router.get('/period-reviews/{key}/history')
def period_history(key: str,authorization: str | None = Header(default=None)):
    from core.dealership_lab import reviews
    who,_=review_actor(authorization,True)
    return reviews.versions(key,who)


# Rewards policy is independent of the optional scenario Lab switch.
class RewardsPolicy(Body):
    enabled: bool = Field(strict=True)
    disabled_users: list[str] = Field(max_length=5000)
    revision: int = Field(ge=0, strict=True)


class Exploration(Body):
    area: str = Field(max_length=40)


def rewards_admin(authorization):
    from core.auth import credential_store
    who = actor(authorization, require_lab=False)
    payload, _ = _authenticate(authorization)
    record = credential_store.get_record(who) or {}
    if payload.get('role') != 'ADMIN' or record.get('role') != 'ADMIN':
        raise HTTPException(403, 'Full platform administrator required')
    return who


@extras_router.get('/policy')
def rewards_policy(authorization: str | None = Header(default=None)):
    from core.dealership_lab import engagement
    from core.auth import credential_store
    rewards_admin(authorization)
    with lab.LOCK:
        users = []
        for key, record in credential_store.credentials.items():
            entity = lab.ledger.get_entity(key)
            users.append(dict(id=key, name=(entity.attributes.get('name') if entity else None) or key, role=record.get('role')))
        return dict(**engagement.policy(), users=users)


@extras_router.put('/policy')
def save_rewards_policy(body: RewardsPolicy, authorization: str | None = Header(default=None)):
    from core.dealership_lab import engagement
    who = rewards_admin(authorization)
    return engagement.update(who, body.enabled, body.disabled_users, body.revision)


@extras_router.get('/journey')
def rewards_journey(authorization: str | None = Header(default=None)):
    from core.dealership_lab import engagement
    with lab.LOCK:
        return engagement.journey(actor(authorization, require_lab=False))


@extras_router.post('/exploration')
def record_exploration(body: Exploration, authorization: str | None = Header(default=None)):
    from core.dealership_lab import engagement
    from core.security import can_access_dashboard
    who = actor(authorization, require_lab=False)
    payload, _ = _authenticate(authorization)
    dashboards = {'Operations':['workload','escalations','manager'], 'Sales':['leaderboard','pipeline','followup','salesperson'],
                  'BDC':['bdc','leaderboard','pipeline','followup','salesperson','service'], 'Marketing':['pipeline','followup'],
                  'Service':['service'], 'Finance':['finance']}
    keys = dashboards.get(body.area, [])
    if (body.area == 'Administration' and payload['role'] != 'ADMIN') or (keys and not any(can_access_dashboard(payload['role'], key) for key in keys)):
        raise HTTPException(403, 'Department access required')
    return engagement.visit(who, body.area)


@extras_router.post('/work-milestones/reconcile')
def reconcile_work_milestones(body: Body, authorization: str | None = Header(default=None)):
    from core.dealership_lab import learning
    who = actor(authorization, require_lab=False)
    with lab.transaction():
        return learning.work_milestones(who, claim=True, recurring=True)
