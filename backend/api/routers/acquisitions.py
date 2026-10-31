"""Inventory: Acquisitions routes, extracted from api/app.py (CAF-00120, god_file_app_py).

Pure extraction -- every route below preserves its original path, HTTP method,
auth handling, and body-passing logic verbatim. No behavior change.

Sam's own framing: "probably one of the most important modules... an entire
buying center." A real AcquisitionRequest entity (auction/trade/direct-
purchase sourcing) moves through Evaluate -> Price Risk -> Estimate Recon ->
Review Market -> Approve, backed by a real 2-step Purchase Approval chain
(Inventory Manager -> GM/Admin). The Buy Recommendation Engine and Factory
Allocations feed are SIMULATED per Sam's direct instruction (2026-07-17:
"when a lack of data is a problem, lets simply make up simulated data to
accommodate it") -- see core/acquisitions.py's module docstring for the full
disclosure convention. Static paths (/catalog, /summary, /buy-recommendation,
/factory-allocations) registered before the dynamic /{request_id} path, same
route-shadowing-avoidance precedent as /operations-tasks/* and
/vehicle-lifecycle/*.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.acquisitions_api import (
    get_catalog_api as acquisitions_catalog_api,
    create_acquisition_request_api,
    get_acquisition_request_api,
    list_acquisition_requests_api,
    record_price_risk_api,
    record_recon_estimate_api,
    record_market_review_api,
    submit_for_approval_api,
    approve_by_inventory_manager_api,
    approve_by_gm_api,
    reject_request_api,
    mark_purchased_api,
    get_acquisitions_summary_api,
    get_buy_recommendation_api,
    get_factory_allocations_api,
    decode_and_prefill_acquisition_vin_api,
)

router = APIRouter()


# Inventory's "Acquisitions" item (Inventory rebuild, second slice) request models.
class CreateAcquisitionRequestRequest(BaseModel):

    source_type: str
    year: str = None
    make: str = None
    model: str = None
    trim: str = None
    mileage: str = None
    vin: str = None
    estimated_acv: float = None
    direct_purchase_channel: str = None
    linked_deal_id: str = None
    linked_auction_transaction_id: str = None
    notes: str = ""


class RecordPriceRiskRequest(BaseModel):

    risk_level: str
    notes: str = ""


class RecordReconEstimateRequest(BaseModel):

    recon_estimate: float
    notes: str = ""


class RecordMarketReviewRequest(BaseModel):

    notes: str = ""


class ApprovalNotesRequest(BaseModel):

    notes: str = ""


class RejectAcquisitionRequestRequest(BaseModel):

    reason: str


class MarkPurchasedRequest(BaseModel):

    vehicle_id: str = None


class ApplyVinDecodeRequest(BaseModel):

    attempt_live: bool = True


@router.get("/acquisitions/catalog")
def acquisitions_catalog():
    """Open, unauthenticated vocabulary lookup -- same treatment as
    /vehicle-lifecycle/catalog."""
    return acquisitions_catalog_api()


@router.get("/acquisitions/summary")
def acquisitions_summary(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_acquisitions_summary_api(payload["role"])


@router.get("/acquisitions/buy-recommendation")
def acquisitions_buy_recommendation(make: str = None, model: str = None, year: str = None, estimated_acv: float = None, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_buy_recommendation_api(payload["role"], make, model, year, estimated_acv=estimated_acv)


@router.get("/acquisitions/factory-allocations")
def acquisitions_factory_allocations(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_factory_allocations_api(payload["role"])


@router.get("/acquisitions")
def acquisitions_list(source_type: str = None, stage: str = None, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return list_acquisition_requests_api(payload["role"], source_type=source_type, stage=stage)


@router.post("/acquisitions")
def acquisitions_create(request: CreateAcquisitionRequestRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return create_acquisition_request_api(
        payload["role"], payload["employee_id"], request.source_type, year=request.year, make=request.make,
        model=request.model, trim=request.trim, mileage=request.mileage, vin=request.vin,
        estimated_acv=request.estimated_acv, direct_purchase_channel=request.direct_purchase_channel,
        linked_deal_id=request.linked_deal_id, linked_auction_transaction_id=request.linked_auction_transaction_id,
        notes=request.notes,
    )


@router.get("/acquisitions/{request_id}")
def acquisitions_get(request_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_acquisition_request_api(payload["role"], request_id)


@router.post("/acquisitions/{request_id}/price-risk")
def acquisitions_price_risk(request_id: str, request: RecordPriceRiskRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return record_price_risk_api(payload["role"], payload["employee_id"], request_id, request.risk_level, notes=request.notes)


@router.post("/acquisitions/{request_id}/recon-estimate")
def acquisitions_recon_estimate(request_id: str, request: RecordReconEstimateRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return record_recon_estimate_api(payload["role"], payload["employee_id"], request_id, request.recon_estimate, notes=request.notes)


@router.post("/acquisitions/{request_id}/market-review")
def acquisitions_market_review(request_id: str, request: RecordMarketReviewRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return record_market_review_api(payload["role"], payload["employee_id"], request_id, notes=request.notes)


@router.post("/acquisitions/{request_id}/decode-vin")
def acquisitions_decode_vin(request_id: str, request: ApplyVinDecodeRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return decode_and_prefill_acquisition_vin_api(
        payload["role"], payload["employee_id"], request_id, attempt_live=request.attempt_live,
    )


@router.post("/acquisitions/{request_id}/submit-for-approval")
def acquisitions_submit_for_approval(request_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return submit_for_approval_api(payload["role"], payload["employee_id"], request_id)


@router.post("/acquisitions/{request_id}/approve/inventory-manager")
def acquisitions_approve_im(request_id: str, request: ApprovalNotesRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return approve_by_inventory_manager_api(payload["role"], payload["employee_id"], request_id, notes=request.notes)


@router.post("/acquisitions/{request_id}/approve/gm")
def acquisitions_approve_gm(request_id: str, request: ApprovalNotesRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return approve_by_gm_api(payload["role"], payload["employee_id"], request_id, notes=request.notes)


@router.post("/acquisitions/{request_id}/reject")
def acquisitions_reject(request_id: str, request: RejectAcquisitionRequestRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return reject_request_api(payload["role"], payload["employee_id"], request_id, request.reason)


@router.post("/acquisitions/{request_id}/mark-purchased")
def acquisitions_mark_purchased(request_id: str, request: MarkPurchasedRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return mark_purchased_api(payload["role"], payload["employee_id"], request_id, vehicle_id=request.vehicle_id)
