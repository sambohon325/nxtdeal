"""Warranty Desk router -- the sixth slice of Service's rebuild
(core/warranty_desk.py / core/warranty_desk_api.py).

Sam's spec: Warranty Eligibility Check, a Submission Workflow, a Rejected
Claims Queue, and Recall Management.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/warranty-desk/claims",
"/warranty-desk/claims/rejected", "/warranty-desk/recalls", and
"/warranty-desk/recalls/mark-completed" are all registered before the
dynamic "/warranty-desk/eligibility/{vehicle_id}" sibling, matching the
original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.warranty_desk_api import (
    get_warranty_claim_api,
    submit_warranty_claim_api,
    record_warranty_decision_api,
    record_warranty_payment_api,
    get_claims_queue_api,
    get_rejected_claims_queue_api,
    get_warranty_eligibility_api,
    mark_recall_completed_api,
    get_recall_management_queue_api,
)


router = APIRouter()


class SubmitWarrantyClaimRequest(BaseModel):

    oem_claim_number: str | None = None


class RecordWarrantyDecisionRequest(BaseModel):

    approved: bool
    rejection_reason: str = ""


class RecordWarrantyPaymentRequest(BaseModel):

    paid_amount: float


class MarkRecallCompletedRequest(BaseModel):

    vehicle_id: str
    recall_id: str
    ro_id: str


@router.get("/warranty-desk/claims")
def warranty_desk_claims(status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_claims_queue_api(payload["role"], status=status)


@router.get("/warranty-desk/claims/rejected")
def warranty_desk_rejected_claims(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_rejected_claims_queue_api(payload["role"])


@router.get("/warranty-desk/recalls")
def warranty_desk_recall_management(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_recall_management_queue_api(payload["role"])


@router.post("/warranty-desk/recalls/mark-completed")
def warranty_desk_mark_recall_completed(body: MarkRecallCompletedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_recall_completed_api(payload["role"], body.vehicle_id, body.recall_id, body.ro_id, payload["employee_id"])


@router.get("/warranty-desk/eligibility/{vehicle_id}")
def warranty_desk_eligibility(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_warranty_eligibility_api(payload["role"], vehicle_id)


@router.get("/repair-orders/{ro_id}/warranty-claim")
def repair_order_get_warranty_claim(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_warranty_claim_api(payload["role"], ro_id)


@router.post("/repair-orders/{ro_id}/warranty-claim/submit")
def repair_order_submit_warranty_claim(ro_id: str, body: SubmitWarrantyClaimRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_warranty_claim_api(payload["role"], ro_id, payload["employee_id"], oem_claim_number=body.oem_claim_number)


@router.post("/repair-orders/{ro_id}/warranty-claim/decision")
def repair_order_record_warranty_decision(ro_id: str, body: RecordWarrantyDecisionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_warranty_decision_api(payload["role"], ro_id, body.approved, payload["employee_id"], rejection_reason=body.rejection_reason)


@router.post("/repair-orders/{ro_id}/warranty-claim/payment")
def repair_order_record_warranty_payment(ro_id: str, body: RecordWarrantyPaymentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_warranty_payment_api(payload["role"], ro_id, body.paid_amount, payload["employee_id"])
