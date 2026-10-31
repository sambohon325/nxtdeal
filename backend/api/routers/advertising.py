"""Advertising routes, extracted from api/app.py (CAF-00120, god_file_app_py --
splitting the monolithic app.py into per-domain routers).

Advertising -- Meta/Google ad campaigns (session 83). An AdCampaign is an ordinary
graph entity (core/advertising.py), distinct from core/campaigns.py's own Campaign
engine. Any role can draft/request an AI recommendation; only MARKETING/ADMIN can
launch/pause/complete it (simulated -- no real Meta/Google Ads API access in this
sandbox). See core/advertising_api.py's module docstring.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.advertising_api import (
    list_platforms_api as list_ad_platforms_api,
    list_objectives_api as list_ad_objectives_api,
    generate_ad_recommendation_api,
    create_ad_campaign_api,
    get_ad_campaign_api,
    update_ad_campaign_api,
    launch_ad_campaign_api,
    pause_ad_campaign_api,
    complete_ad_campaign_api,
    cancel_ad_campaign_api,
    list_ad_campaigns_api,
)

router = APIRouter()


class AdRecommendationRequest(BaseModel):

    platform: str = "meta"
    objective: str = "traffic"
    audience_description: str = None
    vehicle_description: str = None


class CreateAdCampaignRequest(BaseModel):

    platform: str
    objective: str
    name: str = None
    fields: dict = {}
    linked_vehicle_ids: list = []


class UpdateAdCampaignRequest(BaseModel):

    patch: dict = {}


@router.get("/advertising/platforms")
def advertising_platforms(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_ad_platforms_api()


@router.get("/advertising/objectives")
def advertising_objectives(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_ad_objectives_api()


@router.post("/advertising/recommend")
def advertising_recommend(
    request: AdRecommendationRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_ad_recommendation_api(payload["role"], request.dict())


@router.post("/advertising/campaigns")
def advertising_create_campaign(
    request: CreateAdCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_ad_campaign_api(
        payload["role"],
        payload["employee_id"],
        request.platform,
        request.objective,
        request.name,
        request.fields,
        request.linked_vehicle_ids,
    )


@router.get("/advertising/campaigns")
def advertising_list_campaigns(
    platform: str = None,
    status: str = None,
    mine_only: bool = False,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_ad_campaigns_api(payload["role"], payload["employee_id"], platform, status, mine_only)


@router.get("/advertising/campaigns/{ad_id}")
def advertising_get_campaign(ad_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ad_campaign_api(payload["role"], payload["employee_id"], ad_id)


@router.put("/advertising/campaigns/{ad_id}")
def advertising_update_campaign(
    ad_id: str,
    request: UpdateAdCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_ad_campaign_api(payload["role"], payload["employee_id"], ad_id, request.patch)


@router.post("/advertising/campaigns/{ad_id}/launch")
def advertising_launch_campaign(ad_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return launch_ad_campaign_api(payload["role"], payload["employee_id"], ad_id)


@router.post("/advertising/campaigns/{ad_id}/pause")
def advertising_pause_campaign(ad_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return pause_ad_campaign_api(payload["role"], payload["employee_id"], ad_id)


@router.post("/advertising/campaigns/{ad_id}/complete")
def advertising_complete_campaign(ad_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_ad_campaign_api(payload["role"], payload["employee_id"], ad_id)


@router.post("/advertising/campaigns/{ad_id}/cancel")
def advertising_cancel_campaign(ad_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_ad_campaign_api(payload["role"], payload["employee_id"], ad_id)
