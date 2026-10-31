"""
core/pricing_desk_api.py -- ACL layer for core/pricing_desk.py. Viewing is
broad, the same set used across this Inventory rebuild -- Sales/Marketing
both legitimately want to see market position and recommendations when
talking to a customer. Applying a price change is narrower, matching
core/inventory_aging_api.py's own mutate set (ADMIN/OPERATIONS) -- pricing
decisions are an Inventory Manager/Operations call, not a Sales one, same
reasoning that module already established.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.pricing_desk import (
    get_market_pricing, get_competitor_comparisons, get_age_based_adjustment,
    get_pricing_recommendation, get_pricing_view, get_pricing_queue,
    apply_price_recommendation,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS)


def _denied():
    return {"error": "You don't have access to the Pricing Desk"}


def get_market_pricing_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_market_pricing(vehicle_id)


def get_competitor_comparisons_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_competitor_comparisons(vehicle_id)


def get_age_based_adjustment_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_age_based_adjustment(vehicle_id)


def get_pricing_recommendation_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_pricing_recommendation(vehicle_id)


def get_pricing_view_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_pricing_view(vehicle_id)


def get_pricing_queue_api(role, limit=25):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_pricing_queue(limit=limit)


def apply_price_recommendation_api(role, employee_id, vehicle_id, new_price, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return apply_price_recommendation(vehicle_id, employee_id, new_price, reason=reason)
