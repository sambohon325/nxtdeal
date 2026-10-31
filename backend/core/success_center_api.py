"""Thin ACL layer for core/success_center.py -- same "no service-layer
indirection" convention as every other *_api.py module in this codebase.

Success Center is a NXTDeal-INTERNAL client-success / account-management
platform, NOT a dealership department (see core/success_center.py's own module
docstring). Because it manages the NXTDeal staff's portfolio of dealer
accounts -- not the dealership's own operational data -- its VIEW_ROLES are
deliberately restricted to ADMIN + OPERATIONS only, the same GM/principal-level
oversight tier core/permissions.py's EMPLOYEE_VALUE_SNAPSHOT / COMPLIANCE_ALERT
/ the "executive" DASHBOARD_ACCESS entry already reserve for whole-platform,
non-department-scoped views. Sales/Marketing/Service/Finance have no reason to
see or act on another dealer account's success records, so they're excluded --
narrower than the broad six-role tuple the cross-department Communications Hub
/ Customer Journey screens use.

core/success_center.py raises ValueError on an unknown dealer / unknown
recommendation / invalid input; this layer catches that and returns the same
{"error": ...} dict shape every other *_api.py module surfaces, so routers and
callers get one uniform error contract.
"""

from core.success_center import (
    add_initiative,
    add_objective,
    add_recommendation,
    create_dealer,
    create_qbr,
    generate_qbr_insights,
    get_success_overview,
    list_dealers,
    list_open_recommendations,
    resolve_recommendation,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS")


def list_dealers_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view Success Center dealer accounts."}

    return list_dealers()


def create_dealer_api(role, name, notes=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to create a Success Center dealer account."}

    try:
        return create_dealer(name, notes=notes)
    except ValueError as exc:
        return {"error": str(exc)}


def get_success_overview_api(role, dealer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the Success Center overview."}

    try:
        return get_success_overview(dealer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def create_qbr_api(role, dealer_id, period, notes=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to create a QBR."}

    try:
        return create_qbr(dealer_id, period, notes=notes)
    except ValueError as exc:
        return {"error": str(exc)}


def add_objective_api(role, dealer_id, title, target=""):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to add an objective."}

    try:
        return add_objective(dealer_id, title, target=target)
    except ValueError as exc:
        return {"error": str(exc)}


def add_initiative_api(role, dealer_id, title, status="planned"):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to add an initiative."}

    try:
        return add_initiative(dealer_id, title, status=status)
    except ValueError as exc:
        return {"error": str(exc)}


def add_recommendation_api(role, dealer_id, text, priority="medium"):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to add a recommendation."}

    try:
        return add_recommendation(dealer_id, text, priority=priority)
    except ValueError as exc:
        return {"error": str(exc)}


def list_open_recommendations_api(role, dealer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view recommendations."}

    try:
        return list_open_recommendations(dealer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def resolve_recommendation_api(role, dealer_id, rec_id, resolved_by=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to resolve a recommendation."}

    try:
        return resolve_recommendation(dealer_id, rec_id, resolved_by=resolved_by)
    except ValueError as exc:
        return {"error": str(exc)}


def generate_qbr_insights_api(role, dealer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate QBR insights."}

    try:
        return generate_qbr_insights(dealer_id)
    except ValueError as exc:
        return {"error": str(exc)}
