"""
Thin ACL layer for core/advertising.py (session 83), imported directly into
api/app.py's route handlers.

Role rule, matching core/social_posts_api.py's precedent: any authenticated role can
draft an ad campaign and request an AI recommendation; only MARKETING/ADMIN can
launch/pause/complete it or see the full cross-employee list -- turning a draft into
something that actually "runs" (even simulated) is a marketing/budget decision.

Every response also carries an explicit not_yet_tracked note on performance metrics
(impressions/clicks/CPC/spend/ROAS) -- this sandbox has no real ad-delivery path, so
these are never fabricated, matching this codebase's honest-gap convention
(prediction.py/network_benchmark.py/employee_value.py all do the same).
"""

from core.advertising import (
    list_platforms,
    list_objectives,
    generate_ad_recommendation,
    fallback_recommendation,
    create_ad_campaign,
    get_ad_campaign,
    update_ad_campaign,
    launch_ad_campaign,
    pause_ad_campaign,
    complete_ad_campaign,
    cancel_ad_campaign,
    list_ad_campaigns,
    resolve_linked_vehicles,
)
from core.permissions import ADMIN, MARKETING

PERFORMANCE_NOT_YET_TRACKED = (
    "impressions/clicks/CPC/spend/ROAS are not_yet_tracked -- this sandbox has no real "
    "connection to the Meta or Google Ads APIs, so no real ad delivery or spend occurs. "
    "Launching a campaign here is a real, tracked graph action (status/timestamps), not "
    "a real ad buy."
)


def _can_manage(role):
    return role == ADMIN or role == MARKETING


def _serialize(entity):
    return {"id": entity.id, **entity.attributes, "performance_note": PERFORMANCE_NOT_YET_TRACKED}


def list_platforms_api():
    return list_platforms()


def list_objectives_api():
    return list_objectives()


def generate_ad_recommendation_api(role, brief):

    result = generate_ad_recommendation(brief or {})

    if isinstance(result, dict) and "error" in result:
        return {**fallback_recommendation(brief or {}), "ai_generated": False, "ai_error": result["error"]}

    return {**result, "ai_generated": True}


def create_ad_campaign_api(role, employee_id, platform, objective, name, fields, linked_vehicle_ids=None):

    result = create_ad_campaign(employee_id, platform, objective, name, fields or {}, linked_vehicle_ids)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def get_ad_campaign_api(role, employee_id, ad_id):

    ad = get_ad_campaign(ad_id)

    if not ad:
        return {"error": "Ad campaign not found"}

    return {**_serialize(ad), "linked_vehicles": resolve_linked_vehicles(ad_id)}


def update_ad_campaign_api(role, employee_id, ad_id, patch):

    ad = get_ad_campaign(ad_id)

    if not ad:
        return {"error": "Ad campaign not found"}

    if ad.attributes.get("created_by") != employee_id and not _can_manage(role):
        return {"error": "Only the creator (or marketing/admin) can edit this campaign"}

    updated = update_ad_campaign(ad_id, patch or {})

    return _serialize(updated)


def launch_ad_campaign_api(role, employee_id, ad_id):

    if not _can_manage(role):
        return {"error": "Only marketing/admin can launch an ad campaign"}

    ad = get_ad_campaign(ad_id)

    if not ad:
        return {"error": "Ad campaign not found"}

    result = launch_ad_campaign(ad_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def pause_ad_campaign_api(role, employee_id, ad_id):

    if not _can_manage(role):
        return {"error": "Only marketing/admin can pause an ad campaign"}

    result = pause_ad_campaign(ad_id)

    if result is None:
        return {"error": "Ad campaign not found"}

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def complete_ad_campaign_api(role, employee_id, ad_id):

    if not _can_manage(role):
        return {"error": "Only marketing/admin can complete an ad campaign"}

    result = complete_ad_campaign(ad_id)

    if result is None:
        return {"error": "Ad campaign not found"}

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def cancel_ad_campaign_api(role, employee_id, ad_id):

    ad = get_ad_campaign(ad_id)

    if not ad:
        return {"error": "Ad campaign not found"}

    if ad.attributes.get("created_by") != employee_id and not _can_manage(role):
        return {"error": "Only the creator (or marketing/admin) can cancel this campaign"}

    result = cancel_ad_campaign(ad_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def list_ad_campaigns_api(role, employee_id, platform=None, status=None, mine_only=False):

    campaigns = list_ad_campaigns(platform=platform, status=status, created_by=employee_id if mine_only else None)

    return [_serialize(c) for c in campaigns]
