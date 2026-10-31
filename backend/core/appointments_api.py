"""
Thin ACL layer for core/appointments.py, same "no service layer indirection"
convention as every other `*_api.py` module. Role rule: ADMIN/OPERATIONS/SALES/
SERVICE/MARKETING can create/act on appointments -- broader than a single
department's own dashboard ACL, since Sales and Service both book real appointments
against the same shared entity (see core/appointments.py's module docstring), and
Marketing's Events/CRM surfaces occasionally need to schedule one too (e.g. a
promoted trigger alert's "call to schedule a service appointment" next step).
"""

from core.dealeros import ledger
from core.appointments import (
    create_appointment,
    get_appointment,
    update_status,
    reschedule_appointment,
    list_appointments,
    list_todays,
    list_this_week,
    list_upcoming_within,
    APPOINTMENT_TYPES,
    STATUSES,
)
from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING

_APPT_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING)
_ROSTER_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def list_appointment_types_api():
    return APPOINTMENT_TYPES


def list_appointment_statuses_api():
    return STATUSES


def create_appointment_api(role, employee_id, department, appointment_type, scheduled_start, assigned_to=None, customer_id=None, lead_id=None, vehicle_id=None, scheduled_end=None, notes=""):

    if role not in _APPT_ROLES:
        return {"error": "You don't have access to schedule appointments"}

    result = create_appointment(
        department, appointment_type, scheduled_start, employee_id,
        assigned_to=assigned_to, customer_id=customer_id, lead_id=lead_id,
        vehicle_id=vehicle_id, scheduled_end=scheduled_end, notes=notes,
    )

    if _is_error(result):
        return result

    return _serialize(result)


def get_appointment_api(role, appointment_id):

    if role not in _APPT_ROLES:
        return {"error": "You don't have access to appointments"}

    appt = get_appointment(appointment_id)

    if not appt:
        return {"error": "Appointment not found"}

    return _serialize(appt)


def update_appointment_status_api(role, employee_id, appointment_id, new_status):

    if role not in _APPT_ROLES:
        return {"error": "You don't have access to update appointments"}

    result = update_status(appointment_id, new_status, employee_id)

    if _is_error(result):
        return result

    return _serialize(result)


def reschedule_appointment_api(role, employee_id, appointment_id, new_start, new_end=None):

    if role not in _APPT_ROLES:
        return {"error": "You don't have access to reschedule appointments"}

    result = reschedule_appointment(appointment_id, new_start, employee_id, new_end=new_end)

    if _is_error(result):
        return result

    return _serialize(result)


def list_appointments_api(role, department=None, assigned_to=None, status=None, appointment_type=None, linked_entity_id=None, date=None, scope=None, hours=None):
    """`scope` is an optional shorthand ("today"/"this_week"/"upcoming") layered on
    top of the plain filtered list -- `hours` is only used when scope="upcoming"."""

    if role not in _APPT_ROLES:
        return {"error": "You don't have access to appointments"}

    if scope == "today":
        appts = list_todays(department=department, assigned_to=assigned_to)
    elif scope == "this_week":
        appts = list_this_week(department=department, assigned_to=assigned_to)
    elif scope == "upcoming":
        appts = list_upcoming_within(hours or 2, department=department, assigned_to=assigned_to)
    else:
        appts = list_appointments(department=department, assigned_to=assigned_to, status=status, appointment_type=appointment_type, linked_entity_id=linked_entity_id, date=date)

    return [_serialize(a) for a in appts]


def list_service_employees_api(role):
    """A plain Service-department roster (technicians/advisors) -- the Service
    Appointments Dash's "Assign to..." picker's data source. Same narrow shape and
    same reasoning as `lead_assignment_api.py`'s `list_sales_employees_api` (Employee
    has no ENTITY_ACCESS entry, so the generic role-filtered search can't be reused
    for a non-ADMIN caller here either) -- id/name/title only, no PII beyond name."""

    if role not in _ROSTER_ROLES:
        return {"error": "You don't have access to the employee roster"}

    employees = [
        e for e in ledger.get_all().values()
        if e.entity_type == "Employee"
        and (e.attributes.get("Department") or "").strip().lower() == "service"
    ]

    return [
        {
            "id": e.id,
            "name": f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip(),
            "title": e.attributes.get("Title"),
        }
        for e in employees
    ]
