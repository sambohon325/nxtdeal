"""
core/inventory_aging_api.py -- ACL layer for core/inventory_aging.py. Viewing the
board is broad, same set as most Inventory-adjacent data; mutating (price
reduction, wholesale/manager/auction review requests, marketing tie-in) is
narrower -- pricing and disposition decisions are an Inventory Manager/Operations
call, not a Sales or Marketing one, matching Vehicle Lifecycle's own mutate set
(ADMIN/OPERATIONS) rather than the broader 3-role set used elsewhere.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.inventory_aging import (
    get_aging_board, get_vehicle_aging_brief, reduce_price, request_wholesale_review,
    request_manager_review, request_auction_assignment, create_marketing_tie_in,
)
from core.operations_tasks import serialize_task

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _denied():
    return {"error": "You don't have access to Inventory Aging Management"}


def get_aging_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_aging_board()


def get_vehicle_aging_brief_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_vehicle_aging_brief(vehicle_id)


def reduce_price_api(role, employee_id, vehicle_id, new_price, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return reduce_price(vehicle_id, new_price, employee_id, reason=reason)


def request_wholesale_review_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = request_wholesale_review(vehicle_id, employee_id, notes=notes)
    return result if _is_error(result) else serialize_task(result)


def request_manager_review_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = request_manager_review(vehicle_id, employee_id, notes=notes)
    return result if _is_error(result) else serialize_task(result)


def request_auction_assignment_api(role, employee_id, vehicle_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = request_auction_assignment(vehicle_id, employee_id, notes=notes)
    return result if _is_error(result) else serialize_task(result)


def create_marketing_tie_in_api(role, employee_id, vehicle_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return create_marketing_tie_in(vehicle_id, employee_id)
