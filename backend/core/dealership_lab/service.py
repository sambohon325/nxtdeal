"""Canonical-graph dealership learning workspace.

Reviews record learning activity, never verified facts. Only an authenticated
analysis provider may eventually award run milestones; no client run/XP endpoint.
"""
import hashlib
import json
import secrets
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from fastapi import HTTPException
from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
LOCK = RLock()
WORKSPACE, VERSION, PROFILE = 'DealershipLabWorkspace', 'DealershipLabVersion', 'DealershipLabProfile'
SECTIONS = {
    'identity': {'title': 'Plant your flag', 'description': 'Define the dealership, location and objective.', 'fields': {'name': ['Dealership name', 'text', 'My dealership'], 'kind': ['Business type', 'choice', 'Independent used', ['Independent used', 'Franchised new & used', 'BHPH / subprime', 'OEM direct', 'Commercial / fleet']], 'currency': ['Currency', 'choice', 'USD', ['USD', 'CAD']], 'country': ['Country', 'choice', 'United States', ['United States', 'Canada']], 'region': ['State / province (full name)', 'text', 'Texas'], 'city': ['City', 'text', ''], 'rooftops': ['Rooftops', 'number', 1, 1, 100]}},
    'inventory': {'title': 'Stock the lot', 'description': 'Separate new and used stock, arrivals, gross and carrying costs.', 'fields': {'new_units': ['New stock', 'number', 0, 0, 10000], 'used_units': ['Used stock', 'number', 0, 0, 10000], 'new_arrivals': ['New arrivals / month', 'number', 0, 0, 10000], 'used_arrivals': ['Used arrivals / month', 'number', 0, 0, 10000], 'new_gross': ['New gross / unit', 'number', 0, -100000, 100000], 'used_gross': ['Used gross / unit', 'number', 0, -100000, 100000], 'holding': ['Holding cost / unit / month', 'number', 0, 0, 10000]}},
    'team': {'title': 'Build the team', 'description': 'Plan coverage before adding demand.', 'fields': {'salespeople': ['Salespeople', 'number', 0, 0, 1000], 'bdc': ['BDC staff', 'number', 0, 0, 1000], 'technicians': ['Technicians', 'number', 0, 0, 1000], 'advisors': ['Advisors', 'number', 0, 0, 1000], 'payroll': ['Monthly payroll', 'number', 0, 0, 10000000], 'hours': ['Productive hours / person / month (five-day week)', 'number', 0, 0, 520]}},
    'facility': {'title': 'Open the doors', 'description': 'Record physical constraints and overhead.', 'fields': {'bays': ['Service bays', 'number', 0, 0, 1000], 'rent': ['Monthly rent / occupancy', 'number', 0, 0, 10000000], 'overhead': ['Other monthly overhead', 'number', 0, 0, 10000000], 'days': ['Open days / month', 'number', 22, 1, 31]}},
    'software': {'title': 'Choose the toolkit', 'description': 'Time saved is not automatically cash saved.', 'fields': {'stack': ['Systems and assumptions', 'text', ''], 'cost': ['Monthly software cost', 'number', 0, 0, 1000000], 'adoption': ['Adoption %', 'number', 0, 0, 100], 'integration': ['Integration coverage %', 'number', 0, 0, 100], 'cash_realization': ['Time savings realized as cash %', 'number', 0, 0, 100]}},
    'campaigns': {'title': 'Bring in shoppers', 'description': 'Track the funnel, not just lead volume.', 'fields': {'budget': ['Monthly advertising spend', 'number', 0, 0, 10000000], 'leads': ['Monthly inquiries', 'number', 0, 0, 100000], 'response': ['Response %', 'number', 0, 0, 100], 'appointment': ['Appointments / responses %', 'number', 0, 0, 100], 'show': ['Shows / appointments %', 'number', 0, 0, 100], 'close': ['Sales / shows %', 'number', 0, 0, 100]}},
    'work': {'title': 'Work the day', 'description': 'Find the workload and capacity constraints.', 'fields': {'sales_capacity': ['Sales capacity / month', 'number', 0, 0, 10000], 'service_requests': ['Service requests / month', 'number', 0, 0, 100000], 'service_capacity': ['RO capacity / month', 'number', 0, 0, 100000], 'recon_days': ['Recon days / vehicle', 'number', 0, 0, 365], 'bottleneck': ['Constraint to test', 'text', '']}},
    'economics': {'title': 'Balance the plan', 'description': 'Keep gross, profit and cash distinct.', 'fields': {'fi': ['F&I gross / delivered unit', 'number', 0, 0, 100000], 'service_gross': ['Service gross / RO', 'number', 0, 0, 100000], 'cash': ['Starting cash', 'number', 0, -100000000, 100000000], 'debt_service': ['Monthly debt principal payment', 'number', 0, 0, 10000000], 'objective': ['Decision and success criterion', 'text', '']}}
}


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def items(kind):
    return [e for e in list(ledger.get_all().values()) if e.entity_type == kind]


def create(prefix, kind, attrs):
    entity = Entity(id_generator.generate(prefix), kind, deepcopy(attrs))
    ledger.add_entity(entity)
    return entity


@contextmanager
def transaction():
    with LOCK:
        entities, relationships = deepcopy(ledger.entities), deepcopy(ledger.relationships)
        try:
            yield
            save_graph(GRAPH_PATH)
        except Exception:
            ledger.entities, ledger.relationships = entities, relationships
            raise


def workspace(key, actor):
    e = ledger.get_entity(key)
    if not e or e.entity_type != WORKSPACE or e.attributes['owner'] != actor:
        raise HTTPException(404, 'Dealership workspace not found')
    return e


def serial(e):
    return {'id': e.id, **deepcopy(e.attributes)}


def profile(actor, create_missing=False):
    if create_missing:
        from .engagement import require_enabled
        require_enabled(actor)
    e = next((e for e in items(PROFILE) if e.attributes['owner'] == actor), None)
    if not e and create_missing:
        e = create('LABP', PROFILE, {'owner': actor, 'events': [], 'rewards': {}, 'equipped': {'skin': 'glacier', 'frame': 'silver', 'logo': 'auto'}, 'packs': [], 'variants': {}, 'deck': ['host', 'caller', 'analyst']})
    return e


def periods(at):
    day = at.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)
    following = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {'daily': (day, day + timedelta(days=1)), 'weekly': (week, week + timedelta(days=7)), 'monthly': (month, following)}


def count(p, kind, start=None, end=None):
    return len({e['identity'] for e in p['events'] if e['kind'] == kind and (start is None or start.isoformat() <= e['at'] < end.isoformat())})


def record(p, kind, identity):
    at = now()
    event = {'kind': kind, 'identity': identity, 'at': at.isoformat(), 'day': at.date().isoformat()}
    if not any(e['kind'] == kind and e['identity'] == identity and e['day'] == event['day'] for e in p['events']):
        p['events'].append(event)
    def reward(key, period, title, xp):
        p['rewards'].setdefault(key + ':' + period, {'id': key, 'period': period, 'title': title, 'xp': xp, 'created': at.isoformat()})
    if kind == 'review':
        reward('builder-' + identity, 'lifetime', 'Builder milestone: ' + SECTIONS[identity]['title'], 100)
    for key, cadence, title, event_kind, target, xp, _ in CATALOG['quests']:
        start, end = periods(at)[cadence]
        if count(p, event_kind, start, end) >= target:
            reward(key, start.date().isoformat(), title, xp)
    for key, title, event_kind, target, xp in CATALOG['achievements']:
        if count(p, event_kind) >= target:
            reward(key, 'lifetime', title, xp)


def snapshot(actor):
    e = profile(actor)
    p = e.attributes if e else {'events': [], 'rewards': {}, 'equipped': {'skin': 'glacier', 'frame': 'silver', 'logo': 'auto'}, 'packs': [], 'variants': {}, 'deck': ['host', 'caller', 'analyst']}
    at = now()
    xp = sum(r['xp'] for r in p['rewards'].values())
    quests = []
    for key, cadence, title, kind, target, points, description in CATALOG['quests']:
        start, end = periods(at)[cadence]
        quests.append(dict(id=key, cadence=cadence, title=title, kind=kind, target=target, xp=points, description=description, progress=min(target, count(p, kind, start, end)), complete=key + ':' + start.date().isoformat() in p['rewards'], resets=end.isoformat()))
    unlocked = ['host', 'caller', 'analyst'] + [c['id'] for c in CATALOG['cards'] if c.get('mission') and 'builder-' + c['mission'] + ':lifetime' in p['rewards']]
    if len(p.get('game_wins', [])) == 4:
        unlocked.append('champion')
    owned = {}
    for pack in p['packs']:
        for card in pack['cards']:
            owned[card] = owned.get(card, 0) + 1
    from .engagement import enabled
    return dict(enabled=enabled(actor), xp=xp, level=1 + xp // 500, level_xp=xp % 500, quests=quests,
                achievements=[dict(id=k, title=t, target=n, xp=x, progress=min(n, count(p, kind)), complete=k + ':lifetime' in p['rewards']) for k, t, kind, n, x in CATALOG['achievements']],
                rewards=sorted(p['rewards'].values(), key=lambda r: r['created'], reverse=True)[:30],
                equipped=deepcopy(p['equipped']), deck=list(p['deck']), unlocked=unlocked,
                game_wins=list(p.get('game_wins', [])), game_checkpoint=deepcopy(p.get('game_checkpoint')),
                packs=dict(available=xp // 500 - len(p['packs']), opened=len(p['packs']), next_pack_in=500 - xp % 500, owned=owned, equipped=deepcopy(p['variants']), history=deepcopy(p['packs'][-20:])),
                timezone='UTC', server_time=at.isoformat())


def new_workspace(actor, name, source=None):
    with transaction():
        base = workspace(source, actor).attributes if source else None
        sections = deepcopy(base['sections']) if base else {k: {'values': {f: rule[2] for f, rule in s['fields'].items()}, 'basis': 'assumed', 'note': '', 'reviewed_hash': None} for k, s in SECTIONS.items()}
        e = create('LABW', WORKSPACE, dict(owner=actor, name=name, parent_id=(base.get('parent_id') or source) if base else None, sections=sections, model_definition=deepcopy(base.get('model_definition')) if base else None, revision=1, archived=False, created_at=now().isoformat(), updated_at=now().isoformat()))
        if base and base.get('setup_managed'):
            e.attributes['setup_managed'] = True
        if base and base.get('imported_from'):
            e.attributes['imported_from'] = deepcopy(base['imported_from'])
        save_version(e)
        return serial(e)


def save_version(e):
    create('LABV', VERSION, dict(workspace_id=e.id, **deepcopy(e.attributes)))


def copy_version(key, actor, version_id, revision, name, request_id):
    """Recover historical inputs as an independent plan; never rewrite history."""
    with transaction():
        source = workspace(key, actor)
        intent = dict(workspace_id=key, version_id=version_id, revision=revision, name=name)
        previous = next((e for e in items(WORKSPACE) if e.attributes['owner'] == actor
                         and e.attributes.get('recovery_request_id') == request_id), None)
        if previous:
            if previous.attributes.get('recovery_intent') != intent:
                raise HTTPException(409, 'Recovery request already used for different inputs')
            return serial(previous)
        if source.attributes['revision'] != revision:
            raise HTTPException(409, 'Workspace changed. Reload before recovering a version.')
        version = ledger.get_entity(version_id)
        if not version or version.entity_type != VERSION or version.attributes.get('workspace_id') != key or version.attributes.get('owner') != actor:
            raise HTTPException(404, 'Saved version not found')
        saved = version.attributes
        # Only model inputs and setup status travel; execution, request and
        # archive metadata must not be inherited into the new editable record.
        attrs = {field: deepcopy(saved[field]) for field in
                 ('sections', 'model_definition', 'setup_managed', 'parent_id', 'imported_from') if field in saved}
        attrs.update(owner=actor, name=name, revision=1, archived=False,
                     created_at=now().isoformat(), updated_at=now().isoformat(),
                     recovered_from=dict(workspace_id=key, version_id=version_id, revision=saved['revision']),
                     recovery_request_id=request_id, recovery_intent=intent)
        recovered = create('LABW', WORKSPACE, attrs)
        save_version(recovered)
        return serial(recovered)


def save_section(key, actor, section, revision, values, basis, note, reviewed):
    if section not in SECTIONS:
        raise HTTPException(422, 'Unknown builder section')
    rules = SECTIONS[section]['fields']
    if set(values) != set(rules):
        raise HTTPException(422, 'Save all fields in this section')
    for field, rule in rules.items():
        value = values[field]
        if rule[1] == 'number':
            if type(value) not in (int, float) or not rule[3] <= value <= rule[4]:
                raise HTTPException(422, 'Invalid value for ' + rule[0])
        elif not isinstance(value, str) or len(value.strip()) > 500 or (rule[1] == 'choice' and value not in rule[3]):
            raise HTTPException(422, 'Invalid value for ' + rule[0])
    if reviewed and len(note.strip()) < 10:
        raise HTTPException(422, 'Describe the assumptions or records reviewed (at least 10 characters)')
    with transaction():
        e = workspace(key, actor)
        if e.attributes['revision'] != revision:
            raise HTTPException(409, 'Workspace changed. Reload before saving.')
        if e.attributes['archived']:
            raise HTTPException(409, 'Restore the workspace before editing')
        if e.attributes.get('model_definition') is not None:
            raise HTTPException(409, 'This workspace uses a detailed calculation model. Edit that model or explicitly reset it before changing compact builder inputs.')
        value = dict(values=values, basis=basis, note=note, reviewed_hash=digest([values, basis, note]) if reviewed else None)
        if e.attributes['sections'][section] != value:
            e.attributes['sections'][section] = deepcopy(value)
            e.attributes.update(revision=revision + 1, updated_at=now().isoformat())
            save_version(e)
        from .engagement import enabled
        if reviewed and enabled(actor):
            record(profile(actor, True).attributes, 'review', section)
        return serial(e)


def open_pack(actor, request_id):
    with transaction():
        p = profile(actor, True).attributes
        prior = next((r for r in p['packs'] if r['request_id'] == request_id), None)
        if prior:
            return {**deepcopy(prior), 'replayed': True}
        xp = sum(r['xp'] for r in p['rewards'].values())
        if len(p['packs']) >= xp // 500:
            raise HTTPException(409, 'Earn 500 Progress Score per pack. Score is never spent.')
        selected = []
        weights = {'Common': 60, 'Uncommon': 25, 'Rare': 12, 'Legendary': 3}
        for slot in range(5):
            pool = [v for v in CATALOG['variants'] if v['id'] not in selected and (slot != 0 or v['rarity'] in {'Rare', 'Legendary'})]
            draw = secrets.randbelow(sum(weights[v['rarity']] for v in pool))
            for card in pool:
                draw -= weights[card['rarity']]
                if draw < 0:
                    selected.append(card['id'])
                    break
        receipt = dict(request_id=request_id, number=len(p['packs']) + 1, cards=selected[1:] + selected[:1], created=now().isoformat())
        p['packs'].append(receipt)
        return {**deepcopy(receipt), 'replayed': False}
