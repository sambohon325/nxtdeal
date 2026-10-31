"""
Thin ACL layer for core/social_posts.py (session 83), imported directly into
api/app.py's route handlers -- same "no service layer indirection" convention every
other `*_api.py` module in this codebase follows.

Role rule, matching the asset/campaign/website workflow precedent: any authenticated
role can draft a post; only MARKETING/ADMIN can publish/schedule it or see the full
cross-employee feed -- turning a draft into something that actually posts (even
simulated) is a marketing decision, same split core/campaigns_api.py already
established for "who can activate a campaign."
"""

from core.social_posts import (
    list_platforms,
    create_post,
    get_post,
    update_post,
    publish_post,
    cancel_post,
    list_posts,
    get_calendar,
    resolve_linked_vehicles,
    search_inventory_for_post,
    get_vehicle_brief,
)
from core.social_caption_wizard import generate_caption, fallback_caption
from core.permissions import ADMIN, MARKETING


def _can_publish(role):
    return role == ADMIN or role == MARKETING


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def list_platforms_api():
    return list_platforms()


def create_post_api(employee_id, platform, content, media_url=None, linked_vehicle_ids=None, scheduled_time=None, target_date=None):

    result = create_post(employee_id, platform, content, media_url, linked_vehicle_ids, scheduled_time, target_date)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def get_post_api(role, employee_id, post_id):

    post = get_post(post_id)

    if not post:
        return {"error": "Post not found"}

    return {**_serialize(post), "linked_vehicles": resolve_linked_vehicles(post_id)}


def update_post_api(role, employee_id, post_id, patch):

    post = get_post(post_id)

    if not post:
        return {"error": "Post not found"}

    if post.attributes.get("created_by") != employee_id and not _can_publish(role):
        return {"error": "Only the creator (or marketing/admin) can edit this post"}

    updated = update_post(post_id, patch or {})

    return _serialize(updated)


def publish_post_api(role, employee_id, post_id):

    if not _can_publish(role):
        return {"error": "Only marketing/admin can publish a post"}

    post = get_post(post_id)

    if not post:
        return {"error": "Post not found"}

    result = publish_post(post_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def cancel_post_api(role, employee_id, post_id):

    post = get_post(post_id)

    if not post:
        return {"error": "Post not found"}

    if post.attributes.get("created_by") != employee_id and not _can_publish(role):
        return {"error": "Only the creator (or marketing/admin) can cancel this post"}

    result = cancel_post(post_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def list_posts_api(role, employee_id, platform=None, status=None, mine_only=False):

    posts = list_posts(platform=platform, status=status, created_by=employee_id if mine_only else None)

    return [_serialize(p) for p in posts]


def get_calendar_api(role, employee_id, start_date=None, end_date=None):
    return get_calendar(start_date, end_date)


def search_inventory_for_post_api(role, employee_id, query=None):
    return search_inventory_for_post(query)


def generate_caption_api(role, employee_id, platform, goal=None, tone=None, vehicle_id=None):
    """AI caption generation (session 113 follow-up) -- any authenticated role can
    draft, same 'anyone can draft, only marketing/admin can publish' split the rest of
    this module already follows. `vehicle_id`, if given, is resolved live against a
    real Vehicle so the AI is grounded in real attributes rather than inventing them."""

    if platform not in list_platforms():
        return {"error": f"Unknown platform '{platform}'"}

    vehicle = get_vehicle_brief(vehicle_id) if vehicle_id else None

    result = generate_caption(platform, goal=goal, tone=tone, vehicle=vehicle)

    if "error" in result:
        return {**fallback_caption(platform, goal=goal, vehicle=vehicle), "ai_generated": False}

    return {**result, "ai_generated": True}
