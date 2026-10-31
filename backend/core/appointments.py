"""
core/appointments.py -- the real Appointment/calendar entity (session 96 follow-up).

This closes the single most-repeated "not_yet_tracked" gap in this codebase: every
Sales/Service/Marketing dashboard built across sessions 60-95 (sales_menu.py's
overview()/appointments(), sales_overview.py's My Tasks Widget/Daily Sales
Dashboard, service_menu.py's overview()/appointments(), marketing_menu.py's
reporting()/website()) has independently and honestly flagged "no Appointment/
calendar entity exists" rather than fabricate one. This is that entity, built once
and shared -- not a per-department model, since Sales and Service both book the same
real-world thing (a customer/lead, a time, an assigned employee, a status lifecycle),
distinguished by a `department` attribute the same way core/field_notes.py's
FieldNote already is.

Deliberately NOT the same thing as core/dealership_events.py's Event/EventRSVP --
those are one-to-many scheduled dealership events (a sale, a test-drive day) with an
invited audience; an Appointment is a one-to-one booking between one employee and one
customer/lead at one specific time. Different real-world objects, not a naming
accident.
"""

from datetime import datetime, timezone, timedelta
from copy import deepcopy
import hashlib
import threading
from functools import wraps

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import APPOINTMENT, CUSTOMER, LEAD
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

APPOINTMENT_TYPES = {
    "Sales": ["showroom_visit", "test_drive", "delivery", "credit_app", "paperwork", "trade_appraisal", "other"],
    "Service": ["service", "waiter", "drop_off", "recall", "other"],
}

STATUSES = ["scheduled", "confirmed", "arrived", "completed", "no_show", "cancelled"]
_TERMINAL_STATUSES = ("completed", "cancelled", "no_show")
_OPEN_STATUSES = ("scheduled", "confirmed", "arrived")

# Bounded same-process lifecycle coordination; not a storage transaction.
_APPOINTMENT_LOCKS = tuple(threading.RLock() for _ in range(128))


def appointment_lock(appointment_id):
    index = hashlib.sha256(str(appointment_id).encode("utf-8")).digest()[0] % len(_APPOINTMENT_LOCKS)
    return _APPOINTMENT_LOCKS[index]


def _serialized_appointment(function):
    @wraps(function)
    def wrapped(appointment_id, *args, **kwargs):
        with appointment_lock(appointment_id):
            return function(appointment_id, *args, **kwargs)
    return wrapped


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _time_range_error(start, end):
    """Validate times without guessing a timezone for legacy local timestamps."""
    try:
        def parse(value):
            if not isinstance(value, str) or not any(sep in value for sep in ("T", " ")):
                raise ValueError
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        start_time = parse(start)
        if end is not None:
            end_time = parse(end)
            if (start_time.utcoffset() is None) != (end_time.utcoffset() is None):
                return "Start and end must use consistent timezone information"
            if end_time <= start_time:
                return "Appointment end must be after its start"
    except (ValueError, TypeError, OverflowError):
        return "Appointment times must be valid ISO date-times"
    return None


def create_appointment(
    department,
    appointment_type,
    scheduled_start,
    created_by,
    assigned_to=None,
    customer_id=None,
    lead_id=None,
    vehicle_id=None,
    scheduled_end=None,
    notes="",
    _persist=True,
    *,
    loyalty_booking_key=None,
    location_id=None,
    confirmation_required=False,
):

    if department not in APPOINTMENT_TYPES:
        return {"error": f"department must be one of {list(APPOINTMENT_TYPES.keys())}"}

    if appointment_type not in APPOINTMENT_TYPES[department]:
        return {"error": f"appointment_type for {department} must be one of {APPOINTMENT_TYPES[department]}"}

    if not scheduled_start:
        return {"error": "scheduled_start is required"}

    time_error = _time_range_error(scheduled_start, scheduled_end)
    if time_error:
        return {"error": time_error}

    if customer_id:
        customer = ledger.get_entity(customer_id)
        if not customer or customer.entity_type != CUSTOMER:
            return {"error": f"Customer '{customer_id}' not found"}

    if lead_id:
        lead = ledger.get_entity(lead_id)
        if not lead or lead.entity_type != LEAD:
            return {"error": f"Lead '{lead_id}' not found"}

    appt_id = id_generator.generate("APPT")

    entity = Entity(
        id=appt_id,
        entity_type=APPOINTMENT,
        attributes={
            "department": department,
            "appointment_type": appointment_type,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "vehicle_id": vehicle_id,
            "assigned_to": assigned_to,
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "status": "scheduled",
            "notes": notes or "",
            "loyalty_booking_key": loyalty_booking_key,
            "location_id": location_id,
            "confirmation_required": confirmation_required,
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "status_history": [{"status": "scheduled", "at": _now_iso(), "by": created_by}],
        },
    )

    previous = ledger.get_entity(appt_id)
    ledger.add_entity(entity)
    try:
        if _persist:
            save_graph(GRAPH_PATH)
    except Exception:
        # A rejected create must not remain visible as a confirmed booking.
        # Keep the consumed ID; rewinding shared counters would risk reuse.
        if ledger.get_entity(appt_id) is entity:
            if previous is None:
                ledger.entities.pop(appt_id, None)
            else:
                ledger.add_entity(previous)
        raise

    return entity


def get_appointment(appointment_id):

    entity = ledger.get_entity(appointment_id)

    if entity and entity.entity_type == APPOINTMENT:
        return entity

    return None


@_serialized_appointment
def update_status(appointment_id, new_status, updated_by):
    """scheduled -> confirmed -> arrived -> completed is the normal happy path;
    no_show and cancelled are terminal off-ramps from any open state. Once
    completed/cancelled/no_show, an appointment is a closed historical record --
    same append-only-decision convention as core/trigger_alerts.py's alerts."""

    appt = get_appointment(appointment_id)

    if not appt:
        return {"error": "Appointment not found"}

    if new_status not in STATUSES:
        return {"error": f"status must be one of {STATUSES}"}

    if appt.attributes.get("status") in _TERMINAL_STATUSES:
        return {"error": f"Appointment is already '{appt.attributes.get('status')}' -- a closed record"}

    if "status_history" in appt.attributes and not isinstance(appt.attributes["status_history"], list):
        return {"error": "Appointment history needs repair before it can be changed"}

    previous = deepcopy(appt.attributes)
    appt.attributes["status"] = new_status
    appt.attributes["updated_at"] = _now_iso()
    appt.attributes.setdefault("status_history", []).append({"status": new_status, "at": _now_iso(), "by": updated_by})

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return appt


@_serialized_appointment
def reschedule_appointment(appointment_id, new_start, updated_by, new_end=None):

    appt = get_appointment(appointment_id)

    if not appt:
        return {"error": "Appointment not found"}

    if appt.attributes.get("status") in _TERMINAL_STATUSES:
        return {"error": f"Appointment is already '{appt.attributes.get('status')}' -- can't reschedule a closed record"}

    if not new_start:
        return {"error": "new_start is required"}

    if "status_history" in appt.attributes and not isinstance(appt.attributes["status_history"], list):
        return {"error": "Appointment history needs repair before it can be changed"}

    time_error = _time_range_error(new_start, new_end if new_end is not None else appt.attributes.get("scheduled_end"))
    if time_error:
        return {"error": time_error}

    previous = deepcopy(appt.attributes)
    appt.attributes["scheduled_start"] = new_start

    if new_end is not None:
        appt.attributes["scheduled_end"] = new_end

    appt.attributes["status"] = "scheduled"
    appt.attributes["updated_at"] = _now_iso()
    appt.attributes.setdefault("status_history", []).append({"status": "rescheduled", "at": _now_iso(), "by": updated_by})

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return appt


def _scheduled_order(appointment):
    """Known instants first; legacy local times separate; invalid times last.

    Never assign a timezone to legacy data. The entity ID breaks equal-time ties
    deterministically without rewriting the original timestamp.
    """
    value = appointment.attributes.get("scheduled_start")
    if isinstance(value, str) and len(value) <= 64:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return (0, parsed.astimezone(timezone.utc), appointment.id)
            return (1, parsed.isoformat(), appointment.id)
        except (ValueError, TypeError, OverflowError):
            pass
    return (2, "", appointment.id)


def list_appointments(department=None, assigned_to=None, status=None, appointment_type=None, linked_entity_id=None, date=None):

    appts = [e for e in ledger.get_all().values() if e.entity_type == APPOINTMENT]

    if department:
        appts = [a for a in appts if a.attributes.get("department") == department]

    if assigned_to:
        appts = [a for a in appts if a.attributes.get("assigned_to") == assigned_to]

    if status:
        appts = [a for a in appts if a.attributes.get("status") == status]

    if appointment_type:
        appts = [a for a in appts if a.attributes.get("appointment_type") == appointment_type]

    if linked_entity_id:
        appts = [
            a for a in appts
            if a.attributes.get("customer_id") == linked_entity_id or a.attributes.get("lead_id") == linked_entity_id
        ]

    if date:
        appts = [a for a in appts if str(a.attributes.get("scheduled_start") or "").startswith(date)]

    appts.sort(key=_scheduled_order)

    return appts


def list_todays(department=None, assigned_to=None):

    today = _now().date().isoformat()

    return list_appointments(department=department, assigned_to=assigned_to, date=today)


def list_this_week(department=None, assigned_to=None):

    today = _now().date()
    week_end = today + timedelta(days=7)

    appts = list_appointments(department=department, assigned_to=assigned_to)

    return [
        a for a in appts
        if a.attributes.get("scheduled_start")
        and today.isoformat() <= str(a.attributes["scheduled_start"])[:10] <= week_end.isoformat()
    ]


def list_upcoming_within(hours, department=None, assigned_to=None):
    """Open (not yet arrived/completed/cancelled/no_show) appointments whose
    scheduled_start falls within the next `hours` -- the real signal behind
    sales_overview.py's "Appointments arriving within 2 hours"."""

    now = _now()
    horizon = now + timedelta(hours=hours)

    appts = list_appointments(department=department, assigned_to=assigned_to)
    result = []

    for a in appts:

        if a.attributes.get("status") not in _OPEN_STATUSES:
            continue

        start = a.attributes.get("scheduled_start")

        if not start:
            continue

        try:
            dt = datetime.fromisoformat(start)
        except ValueError:
            continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if now <= dt <= horizon:
            result.append(a)

    return result
