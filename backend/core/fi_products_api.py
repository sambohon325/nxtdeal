"""
Thin API-layer functions for the F&I Workflow (session 105 follow-up), imported
directly into api/app.py's route handlers -- same convention as every other
`*_api.py` module in this codebase.

Role rule: viewing a deal's F&I menu is board-wide (same _BOARD_VIEW_ROLES as
core/deals_api.py -- ADMIN/OPERATIONS/SALES/FINANCE, matching sales.pdf's "Deal
Collaboration: Salesperson Manager F&I all work on same record"). Presenting
products, adjusting pricing, and recording a decision are F&I-specific actions --
gated to ADMIN/OPERATIONS/FINANCE only, the exact same _FI_ROLES set
core/deals_api.py already uses to gate "move financing forward, generate the
contract, or fund it." SALES can desk a deal but doesn't run the F&I menu, per
core/deals_api.py's own stated rule.
"""

from core.fi_products import (
    get_fi_product_catalog,
    get_fi_menu,
    present_fi_products,
    update_fi_product_pricing,
    decide_fi_product,
    get_product_penetration_stats,
    list_deals_needing_fi_menu,
    recommend_fi_products,
)
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE


_FI_ROLES = (ADMIN, OPERATIONS, FINANCE)
_BOARD_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize_deal_brief(deal):
    from core.deals_api import _customer_brief, _vehicle_brief

    return {
        "id": deal.id,
        "status": deal.attributes.get("status"),
        "customer": _customer_brief(deal.attributes.get("customer_id")),
        "vehicle": _vehicle_brief(deal.attributes.get("vehicle_id")),
        "updated_at": deal.attributes.get("updated_at"),
    }


def get_fi_product_catalog_api(role):

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to the F&I product catalog"}

    return get_fi_product_catalog()


def get_fi_menu_api(role, deal_id):

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to this deal's F&I menu"}

    return get_fi_menu(deal_id)


def recommend_fi_products_api(role, deal_id):
    """Personalized menu recommendation for a deal (Phase 4). View-tier -- it computes, but
    doesn't mutate; presenting the recommended products still goes through present_fi_products
    (F&I/admin only)."""
    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to this deal's F&I menu"}

    return recommend_fi_products(deal_id)


def present_fi_products_api(role, deal_id, product_keys, presented_by):

    if role not in _FI_ROLES:
        return {"error": "Only F&I/admin can present products on a deal's menu"}

    return present_fi_products(deal_id, product_keys, presented_by)


def update_fi_product_pricing_api(role, deal_id, product_key, cost=None, price=None):

    if role not in _FI_ROLES:
        return {"error": "Only F&I/admin can adjust F&I product pricing"}

    return update_fi_product_pricing(deal_id, product_key, cost=cost, price=price)


def decide_fi_product_api(role, deal_id, product_key, decision, declined_reason=None):

    if role not in _FI_ROLES:
        return {"error": "Only F&I/admin can record a customer's F&I product decision"}

    return decide_fi_product(deal_id, product_key, decision, declined_reason=declined_reason)


def get_product_penetration_stats_api(role):

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to F&I product penetration reporting"}

    return get_product_penetration_stats()


def list_deals_needing_fi_menu_api(role, limit=25):

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to the F&I deal queue"}

    return [_serialize_deal_brief(d) for d in list_deals_needing_fi_menu(limit=limit)]


def get_fi_products_dashboard_api(role):

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to the F&I Workflow dashboard"}

    return {
        "catalog": get_fi_product_catalog(),
        "queue": [_serialize_deal_brief(d) for d in list_deals_needing_fi_menu(limit=10)],
        "penetration": get_product_penetration_stats(),
    }
