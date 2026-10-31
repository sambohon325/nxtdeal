"""Thin ACL layer for core/loyalty.py's graph-native Loyalty / VIP Rewards
engine -- same "no service-layer indirection" convention as every other
*_api.py module in this codebase.

Viewing (overview/member/catalog) and the mutating actions that move a
member's loyalty state (award points, record visit, record referral, redeem
reward) all use the same broad VIEW_ROLES tuple core/customer_journey_api.py /
core/communications_hub_api.py already established for a cross-department,
staff-facing view -- every real role that touches a customer (ADMIN,
OPERATIONS, SALES, MARKETING, SERVICE) can see and act on loyalty, since
points are earned across Sales/Service/Parts/Accessories and the loyalty state
lives on the existing CUSTOMER entity, which already grants these roles read
access in core/permissions.py ENTITY_ACCESS. FINANCE is deliberately excluded
here (unlike the Communications Hub / Customer Journey view) -- F&I has no
loyalty-program responsibility, matching this module's spec.

core/loyalty.py raises ValueError on an unknown customer / unknown reward /
insufficient points / bad input; this layer catches that and returns the same
{"error": ...} dict shape every other *_api.py module surfaces, so routers and
callers get one uniform error contract.
"""

from core.loyalty import (
    award_points,
    get_loyalty_overview,
    get_member,
    list_rewards_catalog,
    record_referral,
    record_visit,
    redeem_reward,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE")


def get_loyalty_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the loyalty overview."}

    return get_loyalty_overview()


def list_rewards_catalog_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the rewards catalog."}

    return list_rewards_catalog()


def get_member_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view a loyalty member."}

    try:
        return get_member(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def award_points_api(role, customer_id, points, reason, department):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to award loyalty points."}

    try:
        return award_points(customer_id, points, reason, department)
    except ValueError as exc:
        return {"error": str(exc)}


def record_visit_api(role, customer_id, department):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to record a loyalty visit."}

    try:
        return record_visit(customer_id, department)
    except ValueError as exc:
        return {"error": str(exc)}


def record_referral_api(role, customer_id, referred_name):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to record a loyalty referral."}

    try:
        return record_referral(customer_id, referred_name)
    except ValueError as exc:
        return {"error": str(exc)}


def redeem_reward_api(role, customer_id, reward_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to redeem a loyalty reward."}

    try:
        return redeem_reward(customer_id, reward_id)
    except ValueError as exc:
        return {"error": str(exc)}
