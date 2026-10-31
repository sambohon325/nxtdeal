"""
Thin ACL layer for core/esignature.py -- same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows (mirrors
core/credit_app_api.py/core/demo_drive_api.py directly).

Role rule: same broad desking-adjacent set core/credit_app_api.py already
established -- ADMIN/OPERATIONS/SALES/FINANCE can all create/edit/send/void an
envelope and record a signer's consent/signature/decline. In a real dealership this
usually plays out as an employee handing a tablet to the customer to sign in
person, so the acting "role" in most of these calls is still the employee
facilitating it, not the customer -- there's no separate unauthenticated
customer-facing signing surface in this pass (flagged as a natural next step, same
as the public /site/[id] page's own unauthenticated-surface precedent, but not
built here).
"""

from core.esignature import (
    create_signature_request,
    get_signature_request,
    add_signer,
    remove_signer,
    send_signature_request,
    capture_signer_consent,
    sign,
    decline_signer,
    void_signature_request,
    list_signature_requests,
    get_stats,
    STATUSES,
    SIGNER_STATUSES,
    SIGNER_ROLES,
)
from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE

_ESIGN_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _customer_brief(customer_id):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return None

    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
    }


def _serialize(req):
    a = req.attributes
    contract = a.get("contract_snapshot") or {}
    return {
        "id": req.id,
        "linked_deal_id": a.get("linked_deal_id"),
        "customer": _customer_brief(contract.get("customer_id")),
        "contract_snapshot": contract,
        "status": a.get("status"),
        "signers": a.get("signers"),
        "created_by": a.get("created_by"),
        "created_at": a.get("created_at"),
        "sent_at": a.get("sent_at"),
        "completed_at": a.get("completed_at"),
        "voided_at": a.get("voided_at"),
        "updated_at": a.get("updated_at"),
    }


def list_esignature_statuses_api():
    return STATUSES


def list_esignature_signer_statuses_api():
    return SIGNER_STATUSES


def list_esignature_signer_roles_api():
    return SIGNER_ROLES


def create_signature_request_api(role, employee_id, linked_deal_id, signers):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to start a signature envelope"}

    result = create_signature_request(linked_deal_id, employee_id, signers or [])

    if _is_error(result):
        return result

    return _serialize(result)


def add_signer_api(role, request_id, name, signer_role, email=None, phone=None):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = add_signer(request_id, name, signer_role, email=email, phone=phone)

    if _is_error(result):
        return result

    return _serialize(result)


def remove_signer_api(role, request_id, signer_index):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = remove_signer(request_id, signer_index)

    if _is_error(result):
        return result

    return _serialize(result)


def send_signature_request_api(role, request_id):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to send this envelope"}

    result = send_signature_request(request_id)

    if _is_error(result):
        return result

    return _serialize(result)


def capture_signer_consent_api(role, request_id, signer_index):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = capture_signer_consent(request_id, signer_index)

    if _is_error(result):
        return result

    return _serialize(result)


def sign_api(role, request_id, signer_index, typed_signature):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = sign(request_id, signer_index, typed_signature)

    if _is_error(result):
        return result

    return _serialize(result)


def decline_signer_api(role, request_id, signer_index, reason):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = decline_signer(request_id, signer_index, reason)

    if _is_error(result):
        return result

    return _serialize(result)


def void_signature_request_api(role, request_id):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    result = void_signature_request(request_id)

    if _is_error(result):
        return result

    return _serialize(result)


def get_signature_request_api(role, request_id):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to this envelope"}

    req = get_signature_request(request_id)

    if not req:
        return {"error": "Signature request not found"}

    return _serialize(req)


def list_signature_requests_api(role, linked_deal_id=None, status=None):

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to signature envelopes"}

    return [_serialize(r) for r in list_signature_requests(linked_deal_id=linked_deal_id, status=status)]


def get_esignature_dashboard_api(role):
    """One call backing the workflow modal's LiveDataPanel + the bespoke board: the
    most recent envelopes plus real stats, same shape as
    core/credit_app_api.py's get_credit_app_dashboard_api()."""

    if role not in _ESIGN_ROLES:
        return {"error": "You don't have access to signature envelopes"}

    return {
        "recent": [_serialize(r) for r in list_signature_requests()[:25]],
        "stats": get_stats(),
    }
