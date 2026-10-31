"""Appointments router -- the real Appointment/calendar entity closing the
single most-repeated "not_yet_tracked" gap in this codebase (see
core/appointments.py's module docstring for the full list of dashboards that
flagged it). Department-agnostic -- Sales and Service both book the same
real-world thing, distinguished by a `department` attribute, same convention
as core/field_notes.py's FieldNote. Also carries Appointments' smart-
scheduling upgrades (Capacity Planning/Suggested Assignee/Reminders/
Pre-Visit Check-In, session 111 follow-up), the genuinely public
/public/checkin/* routes that same feature's check-in link backs, and the
small, tightly-coupled /service/employees roster route (the Service
Appointments Dash's "Assign to..." picker's data source).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static /appointment-scheduling/* paths registered
before the dynamic /appointments/{appointment_id}/* paths, matching the
original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field

from api.deps import _authenticate

from core.appointments_api import (
    list_appointment_types_api,
    list_appointment_statuses_api,
    create_appointment_api,
    get_appointment_api,
    update_appointment_status_api,
    reschedule_appointment_api,
    list_appointments_api,
    list_service_employees_api,
)
from core.appointment_scheduling_api import (
    get_capacity_planning_api,
    suggest_assignee_api,
    send_appointment_reminder_api,
    get_reminder_history_api,
    generate_checkin_link_api,
    get_checkin_link_status_api,
    revoke_checkin_link_api,
)
from core.appointment_scheduling import (
    get_public_checkin_view, record_public_checkin,
    MAX_CHECKIN_CONTACT_LENGTH, MAX_CHECKIN_NOTES_LENGTH,
)


router = APIRouter()


class CreateAppointmentRequest(BaseModel):

    department: str
    appointment_type: str
    scheduled_start: str
    assigned_to: str | None = None
    customer_id: str | None = None
    lead_id: str | None = None
    vehicle_id: str | None = None
    scheduled_end: str | None = None
    notes: str = ""


class UpdateAppointmentStatusRequest(BaseModel):

    status: str


class RescheduleAppointmentRequest(BaseModel):

    new_start: str
    new_end: str | None = None


class SendAppointmentReminderRequest(BaseModel):

    channel: str


class PublicCheckinRequest(BaseModel):

    drop_off_or_wait: str
    contact_preference: str = Field(default="", max_length=MAX_CHECKIN_CONTACT_LENGTH)
    notes: str = Field(default="", max_length=MAX_CHECKIN_NOTES_LENGTH)


@router.get("/appointments/types")
def appointments_types(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_appointment_types_api()


@router.get("/appointments/statuses")
def appointments_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_appointment_statuses_api()


@router.post("/appointments")
def appointments_create(request: CreateAppointmentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_appointment_api(
        payload["role"], payload["employee_id"],
        request.department, request.appointment_type, request.scheduled_start,
        assigned_to=request.assigned_to, customer_id=request.customer_id,
        lead_id=request.lead_id, vehicle_id=request.vehicle_id,
        scheduled_end=request.scheduled_end, notes=request.notes,
    )


@router.get("/appointments")
def appointments_list(
    department: str = None,
    assigned_to: str = None,
    status: str = None,
    appointment_type: str = None,
    linked_entity_id: str = None,
    date: str = None,
    scope: str = None,
    hours: int = None,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_appointments_api(
        payload["role"], department=department, assigned_to=assigned_to, status=status,
        appointment_type=appointment_type, linked_entity_id=linked_entity_id, date=date,
        scope=scope, hours=hours,
    )


@router.get("/appointments/{appointment_id}")
def appointments_get(appointment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_appointment_api(payload["role"], appointment_id)


@router.post("/appointments/{appointment_id}/status")
def appointments_update_status(appointment_id: str, request: UpdateAppointmentStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_appointment_status_api(payload["role"], payload["employee_id"], appointment_id, request.status)


@router.post("/appointments/{appointment_id}/reschedule")
def appointments_reschedule(appointment_id: str, request: RescheduleAppointmentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reschedule_appointment_api(payload["role"], payload["employee_id"], appointment_id, request.new_start, new_end=request.new_end)


# --- Appointments' smart-scheduling upgrades (last item from Service's
# original spec, session 111 follow-up) --- static /appointment-scheduling/*
# paths registered before the dynamic /appointments/{appointment_id}/*
# paths below.

@router.get("/appointment-scheduling/capacity")
def appointment_scheduling_capacity(department: str, date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_capacity_planning_api(payload["role"], department, date=date)


@router.get("/appointment-scheduling/suggest-assignee")
def appointment_scheduling_suggest_assignee(department: str, date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return suggest_assignee_api(payload["role"], department, date=date)


@router.post("/appointments/{appointment_id}/reminder")
def appointments_send_reminder(appointment_id: str, body: SendAppointmentReminderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_appointment_reminder_api(payload["role"], payload["employee_id"], appointment_id, body.channel)


@router.get("/appointments/{appointment_id}/reminder")
def appointments_get_reminder_history(appointment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_reminder_history_api(payload["role"], appointment_id)


@router.post("/appointments/{appointment_id}/checkin-link")
def appointments_generate_checkin_link(appointment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_checkin_link_api(payload["role"], payload["employee_id"], appointment_id)


@router.get("/appointments/{appointment_id}/checkin-link")
def appointments_get_checkin_link_status(appointment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_checkin_link_status_api(payload["role"], appointment_id)


@router.post("/appointments/{appointment_id}/checkin-link/revoke")
def appointments_revoke_checkin_link(appointment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_checkin_link_api(payload["role"], payload["employee_id"], appointment_id)


@router.get("/public/checkin/{token}")
def public_checkin_view(token: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return get_public_checkin_view(token)


@router.post("/public/checkin/{token}/submit")
def public_checkin_submit(token: str, body: PublicCheckinRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return record_public_checkin(token, body.drop_off_or_wait, contact_preference=body.contact_preference, notes=body.notes)


@router.get("/service/employees")
def service_employees(authorization: str = Header(None)):
    """A plain Service-department roster -- the dedicated Service Appointments
    Dash's "Assign to..." picker's data source, same shape/reasoning as the
    existing "/sales/employees" route."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_service_employees_api(payload["role"])
