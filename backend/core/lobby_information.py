"""Dealer-authored lobby information; no invented amenities or public settings dump."""
from copy import deepcopy
from core import system_config
from core.permissions import ADMIN, OPERATIONS

FIELDS = ('welcome', 'lounge', 'refreshments', 'transport', 'accessibility', 'guest_wifi')
MAX_LENGTH = 1000


def _stored():
    entity = system_config.ledger.get_entity(system_config._CONFIG_ID)
    value = entity.attributes.get('lobby_information', {}) if entity else {}
    return value if isinstance(value, dict) else {}


def _content(record):
    return {key: record[key] for key in FIELDS if isinstance(record.get(key), str) and record[key].strip()}


def get_public_lobby():
    # Do not create/backfill SystemConfig on anonymous reads.
    record = _stored()
    if record.get('published') is not True:
        return {'published': False, 'content': {}}
    return {'published': True, 'content': _content(record)}


def get_lobby_settings(role):
    if role not in (ADMIN, OPERATIONS):
        return {'error': 'Admin/Operations role required.'}
    record = _stored()
    return {'published': record.get('published') is True, 'content': _content(record),
            'updated_at': record.get('updated_at'), 'updated_by': record.get('updated_by')}


def update_lobby_settings(role, employee_id, content, published):
    if role not in (ADMIN, OPERATIONS):
        return {'error': 'Admin/Operations role required.'}
    if not isinstance(content, dict) or set(content) - set(FIELDS):
        return {'error': 'Unsupported lobby information fields.'}
    if type(published) is not bool:
        return {'error': 'Publication choice must be true or false.'}
    if any(not isinstance(value, str) or len(value) > MAX_LENGTH for value in content.values()):
        return {'error': 'Lobby information must be text of at most 1000 characters per field.'}
    clean = {key: value.strip() for key, value in content.items() if value.strip()}
    if published and not clean:
        return {'error': 'Add lobby information before publishing.'}
    entity = system_config._get_or_create()
    previous = deepcopy(entity.attributes)
    entity.attributes['lobby_information'] = {**clean, 'published': published,
        'updated_by': employee_id, 'updated_at': system_config._now()}
    try:
        system_config.save_graph(system_config.GRAPH_PATH)
    except Exception:
        entity.attributes.clear()
        entity.attributes.update(previous)
        raise
    return get_lobby_settings(role)
