"""
Thin ACL layer for core/vehicle_holds.py, same "no service layer indirection"
convention as every other `*_api.py` module. Placing/releasing a hold is gated to
ADMIN/OPERATIONS/SALES (the roles that actually desk deals) -- but *viewing* active
holds is opened much wider (any role that can already see Vehicle data), since the
whole point of a hold is visibility: a Service or Finance employee glancing at
inventory should also see "this one's spoken for."
"""

from core.vehicle_holds import place_hold, release_hold, get_active_hold, list_active_holds, list_my_holds
from core.permissions import ADMIN, OPERATIONS, SALES
from core.security import can_access_entity
from core.entity_types import VEHICLE

_HOLD_ROLES = (ADMIN, OPERATIONS, SALES)


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def place_hold_api(role, employee_id, vehicle_id, customer_id=None, lead_id=None, notes="", duration_hours=None):

    if role not in _HOLD_ROLES:
        return {"error": "You don't have access to place a hold on a vehicle"}

    result = place_hold(vehicle_id, employee_id, customer_id=customer_id, lead_id=lead_id, notes=notes, duration_hours=duration_hours)

    if _is_error(result):
        return result

    return _serialize(result)


def release_hold_api(role, employee_id, hold_id):

    if role not in _HOLD_ROLES:
        return {"error": "You don't have access to release a hold"}

    result = release_hold(hold_id, employee_id)

    if _is_error(result):
        return result

    return _serialize(result)


def list_active_holds_api(role):

    if not can_access_entity(role, VEHICLE):
        return {"error": "You don't have access to inventory data"}

    return [_serialize(h) for h in list_active_holds()]


def list_my_holds_api(role, employee_id, include_inactive=False):

    if role not in _HOLD_ROLES:
        return {"error": "You don't have access to holds"}

    return [_serialize(h) for h in list_my_holds(employee_id, include_inactive=include_inactive)]
