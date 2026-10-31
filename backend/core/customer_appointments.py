"""Customer appointment projection; no public routes until identity is ready.

Uses canonical appointments, not a second booking calendar. Listing an appointment
does not imply available booking slots, delivery of reminders, or a queue ETA.
"""
from datetime import datetime
from core.appointments import list_appointments, get_appointment, update_status, appointment_lock, APPOINTMENT_TYPES, STATUSES
from core.customer_identity import resolve_customer as _resolve_customer


def _public_time(value):
    if not isinstance(value, str) or len(value) > 64 or "T" not in value:
        return None, "invalid"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None, "invalid"
    return value, "timezone_known" if parsed.utcoffset() is not None else "timezone_unknown"


def _projection(appointment):
    attributes = appointment.attributes
    department = attributes.get("department")
    if not isinstance(department, str) or department not in APPOINTMENT_TYPES:
        department = None
    kind = attributes.get("appointment_type")
    if not isinstance(kind, str) or kind not in APPOINTMENT_TYPES.get(department, ()):
        kind = None
    status = attributes.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        status = None
    start, time_status = _public_time(attributes.get("scheduled_start"))
    end, _ = _public_time(attributes.get("scheduled_end"))
    return {"id": appointment.id, "department": department, "appointment_type": kind,
            "scheduled_start": start, "scheduled_end": end, "status": status,
            "time_status": time_status}


def get_my_appointments(token, *, offset=0, limit=100):
    customer_id, error = _resolve_customer(token)
    if error:
        return error
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        return {"error": "Use a nonnegative integer offset and a limit from 1 to 100"}
    # Explicit customer check prevents a legacy lead link from granting access.
    appointments = [
        appointment
        for appointment in list_appointments(linked_entity_id=customer_id)
        if appointment.attributes.get("customer_id") == customer_id
    ]
    # Bounded response only: canonical storage still scans/sorts in memory.
    # Each request is a live read, not a frozen cross-page snapshot.
    page = [_projection(appointment) for appointment in appointments[offset:offset + limit]]
    next_offset = offset + len(page) if offset + len(page) < len(appointments) else None
    return {"appointments": page, "count": len(page), "total_count": len(appointments),
            "next_offset": next_offset}


def cancel_my_appointment(token, appointment_id):
    """Cancel an owned pending visit via the canonical lifecycle; still unrouted.

    No notification is sent or implied. Arrived/closed visits need staff handling.
    A repeated cancellation succeeds without appending another history event.
    """
    return _change_my_appointment(token, appointment_id, "cancelled", ("scheduled", "confirmed"))


def confirm_my_appointment(token, appointment_id):
    """Confirm an existing scheduled visit; creates no booking or notification."""
    return _change_my_appointment(token, appointment_id, "confirmed", ("scheduled",))


def _change_my_appointment(token, appointment_id, target_status, allowed_statuses):
    if not isinstance(appointment_id, str) or not 0 < len(appointment_id) <= 128:
        return {"error": "Appointment not found"}
    with appointment_lock(appointment_id):
        return _change_my_appointment_locked(token, appointment_id, target_status, allowed_statuses)


def _change_my_appointment_locked(token, appointment_id, target_status, allowed_statuses):
    customer_id, error = _resolve_customer(token)
    if error:
        return error
    appointment = get_appointment(appointment_id)
    if appointment is None or appointment.attributes.get("customer_id") != customer_id:
        return {"error": "Appointment not found"}
    status = appointment.attributes.get("status")
    if status == target_status:
        return {"appointment": _projection(appointment), "notification_sent": False}
    if status not in allowed_statuses:
        return {"error": "Contact the dealership to change this appointment"}
    result = update_status(appointment_id, target_status, updated_by="customer:" + customer_id)
    if isinstance(result, dict) and "error" in result:
        return result
    return {"appointment": _projection(result), "notification_sent": False}
