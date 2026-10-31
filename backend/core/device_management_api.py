"""
core/device_management_api.py -- ACL layer for core/device_management.py. Same
narrow role set as the rest of this arc (core/loan_servicing_api.py/
core/payments_api.py/core/collections_api.py/core/repossessions_api.py):
ADMIN/OPERATIONS/FINANCE for both viewing and mutating -- device/starter-interrupt
control touches the same sensitive borrower/collateral detail those modules already
gate this way.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.device_management import (
    register_device,
    remove_device,
    list_devices,
    get_simulated_location,
    get_location_history,
    arm_starter_interrupt,
    send_warning,
    disable_starter,
    enable_starter,
    get_device_detail,
    get_device_management_dashboard,
    get_starter_interrupt_dashboard,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Device Management"}


def _serialize(result):
    if isinstance(result, dict):
        return result
    return {"id": result.id, **result.attributes}


def register_device_api(role, employee_id, loan_id, device_type, serial_number, install_date=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(register_device(loan_id, device_type, serial_number, employee_id, install_date=install_date))


def remove_device_api(role, employee_id, device_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(remove_device(device_id, employee_id, reason=reason))


def list_devices_api(role, status=None, loan_id=None, device_type=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_devices(status=status, loan_id=loan_id, device_type=device_type)


def get_simulated_location_api(role, device_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_simulated_location(device_id)


def get_location_history_api(role, device_id, days=7):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_location_history(device_id, days=days)


def arm_starter_interrupt_api(role, employee_id, device_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(arm_starter_interrupt(device_id, employee_id))


def send_warning_api(role, employee_id, device_id, message=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(send_warning(device_id, employee_id, message=message))


def disable_starter_api(role, employee_id, device_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(disable_starter(device_id, employee_id, reason=reason))


def enable_starter_api(role, employee_id, device_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(enable_starter(device_id, employee_id, reason=reason))


def get_device_detail_api(role, device_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_device_detail(device_id)


def get_device_management_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_device_management_dashboard()


def get_starter_interrupt_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_starter_interrupt_dashboard()
