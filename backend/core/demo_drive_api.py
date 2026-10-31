"""
Thin ACL layer for core/demo_drive.py. Logging/starting, returning and cancelling a
demo drive is gated to ADMIN/OPERATIONS/SALES -- the same roles that touch Lead
assignment and the Up System elsewhere in this codebase (core/up_system_api.py /
core/lead_assignment_api.py). Viewing the board is the same gate (a demo drive is
Sales-floor operational data, not cross-department).
"""

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, VEHICLE
from core.demo_drive import (
    start_demo_drive,
    return_demo_drive,
    cancel_demo_drive,
    list_demo_drives,
    list_active_demo_drives,
    get_stats,
    STATUSES,
    INTEREST_LEVELS,
)
from core.permissions import ADMIN, OPERATIONS, SALES

_DEMO_ROLES = (ADMIN, OPERATIONS, SALES)


def _employee_name(employee_id):
    if not employee_id:
        return None
    e = ledger.get_entity(employee_id)
    if not e:
        return employee_id
    return f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip() or employee_id


def _driver_label(entity_id, entity_type):
    entity = ledger.get_entity(entity_id)
    if not entity:
        return entity_id
    if entity_type in (LEAD, CUSTOMER):
        return f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip() or entity_id
    return entity_id


def _vehicle_label(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v:
        return vehicle_id
    year = v.attributes.get("Year") or ""
    make = v.attributes.get("Make") or ""
    model = v.attributes.get("Model") or ""
    label = f"{year} {make} {model}".strip()
    return label or vehicle_id


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize(demo):
    a = demo.attributes
    return {
        "id": demo.id,
        "linked_entity_id": a.get("linked_entity_id"),
        "linked_entity_type": a.get("linked_entity_type"),
        "driver_label": _driver_label(a.get("linked_entity_id"), a.get("linked_entity_type")),
        "vehicle_id": a.get("vehicle_id"),
        "vehicle_label": _vehicle_label(a.get("vehicle_id")),
        "salesperson_id": a.get("salesperson_id"),
        "salesperson_name": _employee_name(a.get("salesperson_id")),
        "license_number": a.get("license_number", ""),
        "license_verified": a.get("license_verified", False),
        "status": a.get("status"),
        "odometer_out": a.get("odometer_out"),
        "odometer_in": a.get("odometer_in"),
        "miles_driven": a.get("miles_driven"),
        "start_at": a.get("start_at"),
        "end_at": a.get("end_at"),
        "duration_minutes": a.get("duration_minutes"),
        "interest_level": a.get("interest_level"),
        "notes": a.get("notes", ""),
        "feedback": a.get("feedback", ""),
    }


def list_demo_statuses_api():
    return STATUSES


def list_interest_levels_api():
    return INTEREST_LEVELS


def start_demo_drive_api(role, linked_entity_id, vehicle_id, salesperson_id,
                         license_number="", license_verified=False, odometer_out=None, notes=""):

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to log a demo drive"}

    result = start_demo_drive(
        linked_entity_id, vehicle_id, salesperson_id,
        license_number=license_number, license_verified=license_verified,
        odometer_out=odometer_out, notes=notes,
    )

    if _is_error(result):
        return result

    return _serialize(result)


def return_demo_drive_api(role, demo_id, odometer_in=None, interest_level=None, feedback=""):

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to update a demo drive"}

    result = return_demo_drive(demo_id, odometer_in=odometer_in, interest_level=interest_level, feedback=feedback)

    if _is_error(result):
        return result

    return _serialize(result)


def cancel_demo_drive_api(role, demo_id):

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to update a demo drive"}

    result = cancel_demo_drive(demo_id)

    if _is_error(result):
        return result

    return _serialize(result)


def list_active_demo_drives_api(role):

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to the demo drive board"}

    return [_serialize(d) for d in list_active_demo_drives()]


def list_demo_drives_api(role, status=None, salesperson_id=None, vehicle_id=None):

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to the demo drive board"}

    return [_serialize(d) for d in list_demo_drives(status=status, salesperson_id=salesperson_id, vehicle_id=vehicle_id)]


def get_demo_drive_dashboard_api(role):
    """One call backing the workflow modal's LiveDataPanel + the bespoke board:
    active-out list plus real stats."""

    if role not in _DEMO_ROLES:
        return {"error": "You don't have access to the demo drive board"}

    return {
        "active": [_serialize(d) for d in list_active_demo_drives()],
        "stats": get_stats(),
    }
