"""
core/wholesale_desk_api.py -- ACL layer for core/wholesale_desk.py. Viewing
is broad, same set used across this Inventory rebuild. Mutating (submitting/
deciding offers, marking a unit sold wholesale, recording funds collected)
is ADMIN/OPERATIONS only, matching core/inventory_aging_api.py's own mutate
set -- disposition and settlement decisions are an Inventory Manager/
Operations call, not a Sales or Marketing one, same reasoning that module
already established.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.wholesale_desk import (
    submit_offer, accept_offer, reject_offer, counter_offer, withdraw_offer, list_offers,
    mark_wholesale_sold, get_sold_wholesale_units,
    record_funds_collected, get_fund_collection_status,
    get_wholesale_desk_summary,
    OFFER_STATUSES,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS)


def _denied():
    return {"error": "You don't have access to the Wholesale Desk"}


def get_catalog_api():
    return {"offer_statuses": list(OFFER_STATUSES)}


def submit_offer_api(role, employee_id, vehicle_id, buyer_name, offer_amount, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return submit_offer(vehicle_id, buyer_name, offer_amount, employee_id, notes=notes)


def accept_offer_api(role, employee_id, offer_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return accept_offer(offer_id, employee_id)


def reject_offer_api(role, employee_id, offer_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return reject_offer(offer_id, employee_id, notes=notes)


def counter_offer_api(role, employee_id, offer_id, counter_amount):
    if role not in _MUTATE_ROLES:
        return _denied()
    return counter_offer(offer_id, counter_amount, employee_id)


def withdraw_offer_api(role, employee_id, offer_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return withdraw_offer(offer_id, employee_id)


def list_offers_api(role, vehicle_id=None, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_offers(vehicle_id=vehicle_id, status=status)


def mark_wholesale_sold_api(role, employee_id, vehicle_id, buyer_name, sale_price, offer_id=None, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return mark_wholesale_sold(vehicle_id, buyer_name, sale_price, employee_id, offer_id=offer_id, notes=notes)


def get_sold_wholesale_units_api(role, limit=50):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_sold_wholesale_units(limit=limit)


def record_funds_collected_api(role, employee_id, vehicle_id, amount, method="", notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_funds_collected(vehicle_id, amount, employee_id, method=method, notes=notes)


def get_fund_collection_status_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_fund_collection_status()


def get_wholesale_desk_summary_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_wholesale_desk_summary()
