"""
core/shop_control_api.py -- ACL layer for core/shop_control.py. Viewing
(dispatch board, utilization, stalled ROs, bottlenecks) is broad, same set
as the RO Workflow Engine's own view roles -- Sales/Finance legitimately
care about shop-floor status too. Technician assignment itself (the actual
mutation) reuses core/repair_orders_api.py's assign_technician_api, gated
to that module's own narrower mutate set (ADMIN/OPERATIONS/SERVICE).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.shop_control import (
    get_dispatch_board, get_technician_utilization, get_stalled_ros, get_bottlenecks,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to Shop Control"}


def get_dispatch_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_dispatch_board()


def get_technician_utilization_api(role, date=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_technician_utilization(date=date)


def get_stalled_ros_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_stalled_ros()


def get_bottlenecks_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_bottlenecks()
