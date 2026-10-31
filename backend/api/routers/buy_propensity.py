"""
Buy-Propensity router (Phase 1, 2026-07-25): the 0-100 buy-propensity score, the ranking
leaderboard, AI outreach drafts, and third-party enrichment. Scoring/ranking open to any
authed role; enrichment is ADMIN/OPERATIONS/MARKETING.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.buy_propensity_api import (
    compute_propensity_api,
    rank_api,
    draft_outreach_api,
    enrich_customer_api,
    get_enrichment_api,
)


router = APIRouter()


class DraftOutreachRequest(BaseModel):

    channel: str = "email"


@router.get("/propensity/rank")
def propensity_rank(limit: int = 50, segment: str = "customers", authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return rank_api(payload["role"], limit=limit, segment=segment)


@router.get("/propensity/{entity_id}")
def propensity_score(entity_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return compute_propensity_api(payload["role"], entity_id)


@router.post("/propensity/{entity_id}/outreach")
def propensity_outreach(entity_id: str, request: DraftOutreachRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return draft_outreach_api(payload["role"], entity_id, channel=request.channel)


@router.post("/enrichment/{customer_id}")
def enrichment_run(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return enrich_customer_api(payload["role"], payload["employee_id"], customer_id)


@router.get("/enrichment/{customer_id}")
def enrichment_get(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_enrichment_api(payload["role"], customer_id)