"""
Thin ACL layer for core/dealership_events.py (session 84), imported directly into
api/app.py's route handlers.

Role rule mirrors the asset/campaign/website workflow precedent: any authenticated
role can draft an event and log an RSVP (a receptionist/salesperson logging a walk-in
at the front desk); publish/start/complete/cancel and promoting an RSVP to a Lead are
scoped to ADMIN/MARKETING/SALES -- same broader-than-usual split as
core/trigger_alerts_api.py, since this dash is explicitly a Sales tool as much as a
Marketing one.
"""

from core.dealership_events import (
    list_event_types,
    create_event,
    get_event,
    update_event,
    publish_event,
    start_event,
    complete_event,
    cancel_event,
    list_events,
    create_rsvp,
    update_rsvp_status,
    list_event_rsvps,
    get_event_detail,
    promote_rsvp_to_lead,
    RSVP_STATUSES,
)
from core.permissions import ADMIN, MARKETING, SALES


def _can_act(role):
    return role in (ADMIN, MARKETING, SALES)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def list_event_types_api():
    return list_event_types()


def list_rsvp_statuses_api():
    return list(RSVP_STATUSES)


def create_event_api(role, employee_id, name, event_type, start_time, end_time=None, location="", capacity=None, description="", linked_list_id=None):

    result = create_event(employee_id, name, event_type, start_time, end_time, location, capacity, description, linked_list_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def get_event_api(role, employee_id, event_id):
    return get_event_detail(event_id)


def update_event_api(role, employee_id, event_id, patch):

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if event.attributes.get("created_by") != employee_id and not _can_act(role):
        return {"error": "Only the creator (or admin/marketing/sales) can edit this event"}

    result = update_event(event_id, patch or {})

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def publish_event_api(role, employee_id, event_id):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can publish an event"}

    result = publish_event(event_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return {"event": _serialize(result["event"]), "invited_count": result["invited_count"]}


def start_event_api(role, employee_id, event_id):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can start an event"}

    result = start_event(event_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def complete_event_api(role, employee_id, event_id):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can complete an event"}

    result = complete_event(event_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def cancel_event_api(role, employee_id, event_id):

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if event.attributes.get("created_by") != employee_id and not _can_act(role):
        return {"error": "Only the creator (or admin/marketing/sales) can cancel this event"}

    result = cancel_event(event_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def list_events_api(role, employee_id, status=None, event_type=None, mine_only=False):

    events = list_events(status=status, event_type=event_type, created_by=employee_id if mine_only else None)

    return [_serialize(e) for e in events]


def create_rsvp_api(role, employee_id, event_id, name, phone=None, email=None, customer_id=None, lead_id=None, source="walk_in"):

    result = create_rsvp(event_id, name, phone, email, customer_id, lead_id, source)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def update_rsvp_status_api(role, employee_id, rsvp_id, status):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can update an RSVP's status"}

    result = update_rsvp_status(rsvp_id, status)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def list_event_rsvps_api(role, employee_id, event_id, status=None):

    rsvps = list_event_rsvps(event_id, status=status)

    return [_serialize(r) for r in rsvps]


def promote_rsvp_to_lead_api(role, employee_id, rsvp_id, assign_to_employee_id=None):

    if not _can_act(role):
        return {"error": "Only admin/marketing/sales can promote an RSVP to a Lead"}

    result = promote_rsvp_to_lead(rsvp_id, employee_id, assign_to_employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return {"rsvp": _serialize(result["rsvp"]), "lead": _serialize(result["lead"])}
