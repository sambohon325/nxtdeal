"""
Thin ACL layer for core/audit_center.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: ADMIN/OPERATIONS-only across every function here, matching
core/administration_menu.py's own established `_ADMIN_ONLY_ERROR` convention
for this whole department (security()/systems()/governance() all use the
same gate) -- the audit log itself carries the kind of detail (who logged in
from where, who overrode a compliance alert, who was granted elevated
permissions) that shouldn't be broadly readable.
"""

from core.audit_center import (
    get_audit_center_overview,
    search_audit_log,
    get_actor_activity,
    get_actor_timeline,
    get_suspicious_activity,
    get_event_catalog,
    export_audit_events_csv,
)
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_audit_center_overview_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_audit_center_overview()


def get_event_catalog_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_event_catalog()


def search_audit_log_api(
    role,
    entity_id=None,
    actor=None,
    event_type=None,
    category=None,
    date_from=None,
    date_to=None,
    query=None,
    limit=200,
):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return search_audit_log(
        entity_id=entity_id, actor=actor, event_type=event_type,
        category=category, date_from=date_from, date_to=date_to,
        query=query, limit=limit,
    )


def get_actor_activity_api(role, limit=50):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_actor_activity(limit=limit)


def get_actor_timeline_api(role, actor, limit=100):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_actor_timeline(actor, limit=limit)


def get_suspicious_activity_api(role, off_hours_lookback_days=7):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_suspicious_activity(off_hours_lookback_days=off_hours_lookback_days)


def export_audit_events_csv_api(
    role,
    entity_id=None,
    actor=None,
    event_type=None,
    category=None,
    date_from=None,
    date_to=None,
    query=None,
):
    if role not in _ADMIN_ROLES:
        return None, _ADMIN_ONLY_ERROR
    return export_audit_events_csv(
        entity_id=entity_id, actor=actor, event_type=event_type,
        category=category, date_from=date_from, date_to=date_to,
        query=query,
    )
