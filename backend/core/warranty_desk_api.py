"""
core/warranty_desk_api.py -- ACL layer for core/warranty_desk.py. Viewing
(claims queue, eligibility, recall management) matches the RO Workflow
Engine's own broad view set (ADMIN/OPERATIONS/SALES/SERVICE/FINANCE --
Finance cares about warranty cost/reimbursement, Sales cares about
eligibility when discussing repairs with a customer). Mutating (submitting
a claim, recording a decision or payment, marking a recall completed)
is narrower, ADMIN/OPERATIONS/SERVICE only, matching the RO Workflow
Engine's own mutate set -- this is Service's own operational workflow.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.warranty_desk import (
    get_warranty_claim,
    submit_warranty_claim,
    record_warranty_decision,
    record_warranty_payment,
    get_claims_queue,
    get_rejected_claims_queue,
    get_warranty_eligibility,
    mark_recall_completed,
    get_recall_management_queue,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the Warranty Desk"}


def get_warranty_claim_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_warranty_claim(ro_id)


def submit_warranty_claim_api(role, ro_id, submitted_by, oem_claim_number=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return submit_warranty_claim(ro_id, submitted_by, oem_claim_number=oem_claim_number)


def record_warranty_decision_api(role, ro_id, approved, decided_by, rejection_reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_warranty_decision(ro_id, approved, decided_by, rejection_reason=rejection_reason)


def record_warranty_payment_api(role, ro_id, paid_amount, paid_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_warranty_payment(ro_id, paid_amount, paid_by)


def get_claims_queue_api(role, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_claims_queue(status=status)


def get_rejected_claims_queue_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_rejected_claims_queue()


def get_warranty_eligibility_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_warranty_eligibility(vehicle_id)


def mark_recall_completed_api(role, vehicle_id, recall_id, ro_id, completed_by):
    if role not in _MUTATE_ROLES:
        return _denied()
    return mark_recall_completed(vehicle_id, recall_id, ro_id, completed_by)


def get_recall_management_queue_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_recall_management_queue()
