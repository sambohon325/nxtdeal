"""Lost Sale Recovery routes, extracted from api/app.py (CAF-00120,
god_file_app_py -- splitting the monolithic app.py into per-domain routers).

Sales' Lost Sale Recovery workflow -- a combined recovery queue unifying
Lead.PipelineState == "LOST" and Deal.status == "cancelled", with reason-code
capture, reactivation, outreach logging, and save-as-list win-back tooling.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.lost_sale_recovery_api import (
    get_lost_reason_codes_api,
    get_lost_leads_api,
    get_cancelled_deals_api,
    mark_lead_lost_api,
    record_deal_lost_reason_api,
    reactivate_lost_lead_api,
    log_recovery_attempt_api,
    list_recovery_attempts_api,
    save_recovery_pool_as_list_api,
    get_lost_sale_stats_api,
    get_lost_sale_recovery_dashboard_api,
)

router = APIRouter()


class MarkLeadLostRequest(BaseModel):

    reason: str


class RecordDealLostReasonRequest(BaseModel):

    reason: str


class ReactivateLostLeadRequest(BaseModel):

    note: str | None = None


class LogRecoveryAttemptRequest(BaseModel):

    entity_id: str
    entity_type: str
    note: str


class SaveRecoveryPoolAsListRequest(BaseModel):

    name: str
    source: str
    description: str = ""


@router.get("/lost-sale-recovery/dashboard")
def lost_sale_recovery_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lost_sale_recovery_dashboard_api(payload["role"])


@router.get("/lost-sale-recovery/reason-codes")
def lost_sale_recovery_reason_codes(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lost_reason_codes_api(payload["role"])


@router.get("/lost-sale-recovery/lost-leads")
def lost_sale_recovery_lost_leads(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lost_leads_api(payload["role"], limit=limit)


@router.get("/lost-sale-recovery/cancelled-deals")
def lost_sale_recovery_cancelled_deals(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_cancelled_deals_api(payload["role"], limit=limit)


@router.get("/lost-sale-recovery/stats")
def lost_sale_recovery_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lost_sale_stats_api(payload["role"])


@router.post("/lost-sale-recovery/leads/{lead_id}/mark-lost")
def lost_sale_recovery_mark_lead_lost(lead_id: str, request: MarkLeadLostRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_lead_lost_api(payload["role"], payload["employee_id"], lead_id, request.reason)


@router.post("/lost-sale-recovery/leads/{lead_id}/reactivate")
def lost_sale_recovery_reactivate_lead(lead_id: str, request: ReactivateLostLeadRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reactivate_lost_lead_api(payload["role"], payload["employee_id"], lead_id, note=request.note)


@router.post("/lost-sale-recovery/deals/{deal_id}/lost-reason")
def lost_sale_recovery_record_deal_reason(deal_id: str, request: RecordDealLostReasonRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_deal_lost_reason_api(payload["role"], payload["employee_id"], deal_id, request.reason)


@router.post("/lost-sale-recovery/log-attempt")
def lost_sale_recovery_log_attempt(request: LogRecoveryAttemptRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_recovery_attempt_api(payload["role"], payload["employee_id"], request.entity_id, request.entity_type, request.note)


@router.get("/lost-sale-recovery/{entity_id}/attempts")
def lost_sale_recovery_list_attempts(entity_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_recovery_attempts_api(payload["role"], entity_id)


@router.post("/lost-sale-recovery/save-as-list")
def lost_sale_recovery_save_as_list(request: SaveRecoveryPoolAsListRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return save_recovery_pool_as_list_api(payload["role"], payload["employee_id"], request.name, request.source, description=request.description)
