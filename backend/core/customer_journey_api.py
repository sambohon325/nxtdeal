"""Thin ACL layer for core/customer_journey.py's graph-native journey stage
tracking -- same "no service-layer indirection" convention as every other
*_api.py module in this codebase.

Viewing (overview/get/list) and the two mutating actions that move a customer
along their lifecycle (advance, set stage) both use the same broad VIEW_ROLES
tuple core/communications_hub_api.py already established for a cross-department
staff-facing view -- every real role can see and act on a customer's journey,
since a customer's lifecycle stage is the same class of everyday, cross-
department operational state (Marketing owns Awareness/Lead, Sales owns
Appointment/Sale, Service owns Service, everyone shares Loyalty/Repeat) that
the Communications Hub already exposes broadly, no new sensitive data beyond
what CUSTOMER read-access (core/permissions.py ENTITY_ACCESS) already grants
every one of these roles.

core/customer_journey.py raises ValueError on an unknown customer / invalid
stage / advance-past-final; this layer catches that and returns the same
{"error": ...} dict shape every other *_api.py module surfaces, so routers and
callers get one uniform error contract.
"""

from core.customer_journey import (
    STAGES,
    advance_journey,
    generate_journey_recommendation,
    get_customer_journey,
    get_journey_overview,
    list_customers_in_stage,
    set_journey_stage,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def get_journey_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the customer journey overview."}

    return get_journey_overview()


def get_customer_journey_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view a customer journey."}

    try:
        return get_customer_journey(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def advance_journey_api(role, customer_id, note=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to advance a customer journey."}

    try:
        return advance_journey(customer_id, note=note)
    except ValueError as exc:
        return {"error": str(exc)}


def set_journey_stage_api(role, customer_id, stage, note=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to set a customer journey stage."}

    try:
        return set_journey_stage(customer_id, stage, note=note)
    except ValueError as exc:
        return {"error": str(exc)}


def list_customers_in_stage_api(role, stage):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to list customers by journey stage."}

    try:
        return list_customers_in_stage(stage)
    except ValueError as exc:
        return {"error": str(exc)}


def generate_journey_recommendation_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate a customer journey recommendation."}

    try:
        return generate_journey_recommendation(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}
