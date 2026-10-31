"""
core/document_workflows_api.py -- ACL layer for core/document_workflows.py.
Viewing is broad; mutating (requesting a document, approving/rejecting) is
ADMIN/OPERATIONS -- document completeness and approval is an Operations/
back-office call, matching Vehicle Lifecycle's and Inventory Aging's own
Operations-only mutate sets rather than Scheduling's broader one (Sales
doesn't approve deal jackets).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.entity_types import DEAL, VEHICLE, CUSTOMER
from core.document_workflows import (
    get_deal_jacket_status, get_title_status, request_document,
    get_document_packet, approve_document, reject_document, list_pending_approvals,
)
from core.operations_tasks import serialize_task

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS)

_ENTITY_TYPE_MAP = {"Deal": DEAL, "Vehicle": VEHICLE, "Customer": CUSTOMER}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _denied():
    return {"error": "You don't have access to Document Workflows"}


def get_deal_jacket_status_api(role, deal_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_deal_jacket_status(deal_id)


def get_title_status_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_title_status(vehicle_id)


def request_document_api(role, employee_id, entity_type, entity_id, document_type, notes="", _skip_save=False):
    if role not in _MUTATE_ROLES:
        return _denied()
    real_type = _ENTITY_TYPE_MAP.get(entity_type)
    if not real_type:
        return {"error": f"entity_type must be one of {list(_ENTITY_TYPE_MAP.keys())}"}
    result = request_document(real_type, entity_id, document_type, employee_id, notes=notes, _skip_save=_skip_save)
    if _is_error(result):
        return result
    return serialize_task(result)


def get_document_packet_api(role, entity_type, entity_id):
    if role not in _VIEW_ROLES:
        return _denied()
    real_type = _ENTITY_TYPE_MAP.get(entity_type)
    if not real_type:
        return {"error": f"entity_type must be one of {list(_ENTITY_TYPE_MAP.keys())}"}
    return get_document_packet(real_type, entity_id)


def approve_document_api(role, employee_id, document_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return approve_document(document_id, employee_id, notes=notes)


def reject_document_api(role, employee_id, document_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return reject_document(document_id, employee_id, reason=reason)


def list_pending_approvals_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_pending_approvals()
