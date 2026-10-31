"""
Thin ACL layer for core/credit_app.py -- same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows (mirrors
core/deals_api.py/core/demo_drive_api.py directly).

Role rule: broader than Deal Desk's financing-forward gate on purpose. A credit
application is desking-adjacent work a salesperson does directly with a customer
(same "SALES can desk a deal" role core/deals_api.py already grants for the desking
half of a Deal) -- not the same as a Deal's outside-lender financing decision, which
stays F&I-only. ADMIN/OPERATIONS/SALES/FINANCE can all create/edit/submit/withdraw an
application; there's no narrower "F&I only" step here since the decision itself is a
simulated, instant rules engine, not a human underwriter approval to gate behind a
role.
"""

from core.credit_app import (
    create_credit_application,
    get_credit_application,
    update_applicant,
    set_ssn_last4,
    give_fcra_consent,
    submit_credit_application,
    withdraw_credit_application,
    link_to_deal,
    list_credit_applications,
    get_stats,
    STATUSES,
    DECISIONS,
    EMPLOYMENT_STATUSES,
    HOUSING_STATUSES,
)
from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE

_CREDIT_APP_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _customer_brief(customer_id):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return None

    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
        "email": customer.attributes.get("Email"),
        "phone": customer.attributes.get("Phone"),
        "credit_score": customer.attributes.get("CreditScore"),
    }


def _serialize(app):
    a = app.attributes
    return {
        "id": app.id,
        "customer_id": a.get("customer_id"),
        "customer": _customer_brief(a.get("customer_id")),
        "linked_deal_id": a.get("linked_deal_id"),
        "status": a.get("status"),
        "applicant": a.get("applicant"),
        "co_applicant": a.get("co_applicant"),
        "requested_amount": a.get("requested_amount"),
        "ssn_last4": a.get("ssn_last4"),
        "fcra_consent": a.get("fcra_consent"),
        "fcra_consent_at": a.get("fcra_consent_at"),
        "decision": a.get("decision"),
        "created_by": a.get("created_by"),
        "created_at": a.get("created_at"),
        "updated_at": a.get("updated_at"),
        "withdrawn_at": a.get("withdrawn_at"),
    }


def list_credit_app_statuses_api():
    return STATUSES


def list_credit_app_decisions_api():
    return DECISIONS


def list_credit_app_field_options_api():
    return {"employment_statuses": EMPLOYMENT_STATUSES, "housing_statuses": HOUSING_STATUSES}


def create_credit_application_api(role, employee_id, customer_id, linked_deal_id=None, requested_amount=None):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to start a credit application"}

    result = create_credit_application(customer_id, employee_id, linked_deal_id=linked_deal_id, requested_amount=requested_amount)

    if _is_error(result):
        return result

    return _serialize(result)


def update_applicant_api(role, app_id, applicant_patch=None, co_applicant_patch=None, requested_amount=None):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to edit this application"}

    result = update_applicant(app_id, applicant_patch=applicant_patch, co_applicant_patch=co_applicant_patch, requested_amount=requested_amount)

    if _is_error(result):
        return result

    return _serialize(result)


def set_ssn_last4_api(role, app_id, ssn_last4):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to edit this application"}

    result = set_ssn_last4(app_id, ssn_last4)

    if _is_error(result):
        return result

    return _serialize(result)


def give_fcra_consent_api(role, app_id):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to this application"}

    result = give_fcra_consent(app_id)

    if _is_error(result):
        return result

    return _serialize(result)


def submit_credit_application_api(role, app_id):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to submit this application"}

    result = submit_credit_application(app_id)

    if _is_error(result):
        return result

    return _serialize(result)


def withdraw_credit_application_api(role, app_id):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to this application"}

    result = withdraw_credit_application(app_id)

    if _is_error(result):
        return result

    return _serialize(result)


def link_credit_application_to_deal_api(role, app_id, deal_id):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to this application"}

    result = link_to_deal(app_id, deal_id)

    if _is_error(result):
        return result

    return _serialize(result)


def get_credit_application_api(role, app_id, employee_id=None):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to this application"}

    app = get_credit_application(app_id)

    if not app:
        return {"error": "Credit application not found"}

    serialized = _serialize(app)

    # Field-level security (Administration's Roles & Permissions slice,
    # core/permissions_registry.py) -- ssn_last4 is the other genuinely sensitive
    # field this codebase already surfaces broadly today (this codebase never
    # stores a full SSN anywhere, see core/credit_app.py's set_ssn_last4()).
    from core.permissions_registry import filter_sensitive_fields
    return filter_sensitive_fields(role, employee_id, "CreditApplication", serialized)


def list_credit_applications_api(role, customer_id=None, status=None, linked_deal_id=None):

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to credit applications"}

    return [_serialize(a) for a in list_credit_applications(customer_id=customer_id, status=status, linked_deal_id=linked_deal_id)]


def get_credit_app_dashboard_api(role):
    """One call backing the workflow modal's LiveDataPanel + the bespoke board: the
    most recent applications plus real stats, same shape as
    core/demo_drive_api.py's get_demo_drive_dashboard_api()."""

    if role not in _CREDIT_APP_ROLES:
        return {"error": "You don't have access to credit applications"}

    return {
        "recent": [_serialize(a) for a in list_credit_applications()[:25]],
        "stats": get_stats(),
    }
