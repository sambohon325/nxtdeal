"""Thin ACL layer for core/equity_center.py's graph-native equity / trade-up
opportunity engine -- same "no service-layer indirection" convention as every
other *_api.py module in this codebase.

VIEW_ROLES is deliberately NARROWER than the cross-department Communications
Hub / Customer Journey tuple: equity mining, lease-maturity trade-up, and
upgrade offers are a Sales + Finance (F&I) motion, overseen by Operations and
ADMIN -- Marketing and Service don't work an equity/payoff trade-up desk, and a
customer's estimated payoff is F&I-adjacent data, so this mirrors
core/permissions.py's DASHBOARD_ACCESS['finance'] tier (ADMIN/OPERATIONS/
FINANCE) plus SALES, who own the upgrade conversation.

core/equity_center.py raises ValueError on an unknown / non-customer id; this
layer catches that and returns the same {"error": ...} dict shape every other
*_api.py module surfaces, so routers and callers get one uniform error
contract.
"""

from core.equity_center import (
    create_upgrade_offer,
    generate_upgrade_offer,
    get_equity_overview,
    get_equity_position,
    list_equity_opportunities,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "FINANCE")


def get_equity_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the equity overview."}

    return get_equity_overview()


def list_equity_opportunities_api(role, horizon_days=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view equity opportunities."}

    if horizon_days is None:
        return list_equity_opportunities()

    return list_equity_opportunities(horizon_days=horizon_days)


def get_equity_position_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view a customer equity position."}

    try:
        return get_equity_position(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def create_upgrade_offer_api(role, customer_id, note=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to create an upgrade offer."}

    try:
        return create_upgrade_offer(customer_id, note=note)
    except ValueError as exc:
        return {"error": str(exc)}


def generate_upgrade_offer_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate an upgrade offer."}

    try:
        return generate_upgrade_offer(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}
