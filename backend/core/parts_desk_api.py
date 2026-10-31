"""
core/parts_desk_api.py -- ACL layer for core/parts_desk.py. Viewing (the
queue, special orders, inventory recommendations) is broad, matching the RO
Workflow Engine's own view set -- Sales/Finance both have a legitimate reason
to check part-delay status on a customer's RO. Marking a special order is
narrower, ADMIN/OPERATIONS/SERVICE only, matching the RO Workflow Engine's
own mutate set (this is Service's own operational workflow).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.parts_desk import (
    get_parts_request_queue,
    mark_special_order,
    get_special_orders,
    get_inventory_recommendations,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the Parts Desk"}


def get_parts_request_queue_api(role, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_parts_request_queue(status=status)


def mark_special_order_api(role, ro_id, request_id, vendor, eta, updated_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return mark_special_order(ro_id, request_id, vendor, eta, updated_by)


def get_special_orders_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_special_orders()


def get_inventory_recommendations_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_inventory_recommendations()
