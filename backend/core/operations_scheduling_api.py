"""
core/operations_scheduling_api.py -- ACL layer for core/operations_scheduling.py.
Viewing is broad (Recon/Delivery/Transport scheduling data is relevant to
Operations/Sales/Service/Inventory-adjacent roles alike); mutating (scheduling
recon, scheduling a delivery, updating transport status) is ADMIN/OPERATIONS/
SALES -- Sales legitimately schedules deliveries (it's their customer), unlike
Inventory Aging's pricing/disposition actions which stayed Operations-only.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.operations_scheduling import (
    get_recon_schedule, schedule_recon,
    get_delivery_risk_board, schedule_delivery,
    get_transport_schedule, update_transport_status,
)
from core.operations_tasks import serialize_task

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SALES)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize_entity(result):
    """schedule_delivery() returns a raw Appointment Entity (from
    core/appointments.py's create_appointment()) rather than going through
    core/appointments_api.py's own _serialize() -- same bare-Entity-across-
    the-wire bug class as operations_tasks_api.py, flattened the same way
    here since appointments.py has no shared serializer of its own to
    import."""

    if _is_error(result):
        return result
    return {"id": result.id, **result.attributes}


def _denied():
    return {"error": "You don't have access to Operations Scheduling"}


def get_recon_schedule_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_recon_schedule(role)


def schedule_recon_api(role, employee_id, vehicle_id, target_date, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = schedule_recon(vehicle_id, target_date, employee_id, notes=notes)
    return result if _is_error(result) else serialize_task(result)


def get_delivery_risk_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_delivery_risk_board(role)


def schedule_delivery_api(role, employee_id, deal_id, scheduled_start, assigned_to=None, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = schedule_delivery(deal_id, scheduled_start, employee_id, assigned_to=assigned_to, notes=notes)
    return _serialize_entity(result)


def get_transport_schedule_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_transport_schedule(role)


def update_transport_status_api(role, employee_id, transaction_id, new_status):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_transport_status(transaction_id, new_status, employee_id)
