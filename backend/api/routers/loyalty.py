"""Loyalty / VIP Rewards router -- core/loyalty.py's graph-native points/tier/
visit/referral/reward engine (loyalty state stored as attributes on the
existing Customer entity). See that module's own docstring for the full
graph-native reasoning and the documented tier thresholds.

Follows api/routers/customer_journey.py / api/routers/communications_hub.py's
own established pattern exactly: a self-contained api/routers/<domain>.py
module with its own APIRouter(), importing the shared _authenticate helper from
api/deps.py, full paths per route.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.loyalty_api import (
    award_points_api,
    get_loyalty_overview_api,
    get_member_api,
    list_rewards_catalog_api,
    record_referral_api,
    record_visit_api,
    redeem_reward_api,
)


router = APIRouter()


class AwardPointsRequest(BaseModel):

    points: int
    reason: str = ""
    department: str = ""


class RecordVisitRequest(BaseModel):

    department: str = ""


class RecordReferralRequest(BaseModel):

    referred_name: str


class RedeemRewardRequest(BaseModel):

    reward_id: str


@router.get("/loyalty/overview")
def loyalty_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loyalty_overview_api(payload["role"])


@router.get("/loyalty/rewards")
def loyalty_rewards_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_rewards_catalog_api(payload["role"])


@router.get("/loyalty/member/{customer_id}")
def loyalty_get_member_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_member_api(payload["role"], customer_id)


@router.post("/loyalty/member/{customer_id}/points")
def loyalty_award_points_route(
    customer_id: str, request: AwardPointsRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return award_points_api(
        payload["role"], customer_id, request.points, request.reason, request.department
    )


@router.post("/loyalty/member/{customer_id}/visit")
def loyalty_record_visit_route(
    customer_id: str, request: RecordVisitRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_visit_api(payload["role"], customer_id, request.department)


@router.post("/loyalty/member/{customer_id}/referral")
def loyalty_record_referral_route(
    customer_id: str, request: RecordReferralRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_referral_api(payload["role"], customer_id, request.referred_name)


@router.post("/loyalty/member/{customer_id}/redeem")
def loyalty_redeem_reward_route(
    customer_id: str, request: RedeemRewardRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return redeem_reward_api(payload["role"], customer_id, request.reward_id)
