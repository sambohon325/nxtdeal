from core.audit import audit_log
from core.audit_integrity import full_integrity_report


def _serialize(event):

    return {
        "id": event.id,
        "event_type": event.event_type,
        "entity_id": event.entity_id,
        "actor": event.actor,
        "summary": event.summary,
        "details": event.details,
        "timestamp": event.timestamp,
        # Tamper-evidence hash-chain fields (security-hardening pass,
        # 2026-07-20) -- both "" on any event recorded before this feature
        # shipped, a real, honest "predates verification" signal rather than
        # a bug. See core/audit_integrity.py for the actual verification.
        "prev_hash": event.prev_hash,
        "hash": event.hash
    }


def list_audit_events(entity_id=None, actor=None, event_type=None):

    events = audit_log.get_all()

    if entity_id:
        events = [e for e in events if e.entity_id == entity_id]

    if actor:
        events = [e for e in events if e.actor == actor]

    if event_type:
        events = [e for e in events if e.event_type == event_type]

    # Most recent first.
    events = sorted(
        events,
        key=lambda e: e.timestamp,
        reverse=True
    )

    return [_serialize(event) for event in events]


def get_audit_dashboard():

    events = audit_log.get_all()

    by_type = {}

    for event in events:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

    recent = sorted(
        events,
        key=lambda e: e.timestamp,
        reverse=True
    )[:25]

    return {
        "total_events": len(events),
        "by_type": by_type,
        "recent": [_serialize(event) for event in recent]
    }


def get_audit_integrity_api():
    """Thin pass-through to core/audit_integrity.py's full_integrity_report()
    -- ADMIN-gated at the route layer (api/app.py), same as every other
    /audit* endpoint in this module."""

    return full_integrity_report()
