"""Social media post builder + content calendar routes, extracted from
api/app.py (CAF-00120, god_file_app_py -- splitting the monolithic app.py
into per-domain routers).

A SocialPost is an ordinary graph entity (core/social_posts.py). Any role can
draft; only MARKETING/ADMIN can publish (simulated -- no real platform API
access in this sandbox). See core/social_posts_api.py's module docstring.

/social/posts/generate-caption is registered before the dynamic
/social/posts/{post_id} path so 'generate-caption' is never swallowed as a
post_id.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.social_posts_api import (
    list_platforms_api as list_social_platforms_api,
    create_post_api,
    get_post_api,
    update_post_api,
    publish_post_api,
    cancel_post_api,
    list_posts_api,
    get_calendar_api,
    search_inventory_for_post_api,
    generate_caption_api,
)

router = APIRouter()


class CreateSocialPostRequest(BaseModel):

    platform: str
    content: str = ""
    media_url: str | None = None
    linked_vehicle_ids: list = []
    scheduled_time: str | None = None
    target_date: str | None = None


class UpdateSocialPostRequest(BaseModel):

    patch: dict = {}


class GenerateCaptionRequest(BaseModel):

    platform: str
    goal: str | None = None
    tone: str | None = None
    vehicle_id: str | None = None


@router.get("/social/platforms")
def social_platforms(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_social_platforms_api()


@router.post("/social/posts")
def social_create_post(
    request: CreateSocialPostRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_post_api(
        payload["employee_id"],
        request.platform,
        request.content,
        request.media_url,
        request.linked_vehicle_ids,
        request.scheduled_time,
        request.target_date,
    )


@router.get("/social/posts")
def social_list_posts(
    platform: str = None,
    status: str = None,
    mine_only: bool = False,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_posts_api(payload["role"], payload["employee_id"], platform, status, mine_only)


@router.get("/social/posts/calendar")
def social_calendar(
    start_date: str = None,
    end_date: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_calendar_api(payload["role"], payload["employee_id"], start_date, end_date)


@router.get("/social/inventory-search")
def social_inventory_search(query: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return search_inventory_for_post_api(payload["role"], payload["employee_id"], query)


@router.post("/social/posts/generate-caption")
def social_generate_caption(request: GenerateCaptionRequest, authorization: str = Header(None)):
    """AI caption generation (session 113 follow-up) -- registered before the dynamic
    /social/posts/{post_id} path below so 'generate-caption' is never swallowed as a
    post_id."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_caption_api(
        payload["role"], payload["employee_id"],
        request.platform, request.goal, request.tone, request.vehicle_id,
    )


@router.get("/social/posts/{post_id}")
def social_get_post(post_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_post_api(payload["role"], payload["employee_id"], post_id)


@router.put("/social/posts/{post_id}")
def social_update_post(
    post_id: str,
    request: UpdateSocialPostRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_post_api(payload["role"], payload["employee_id"], post_id, request.patch)


@router.post("/social/posts/{post_id}/publish")
def social_publish_post(post_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return publish_post_api(payload["role"], payload["employee_id"], post_id)


@router.post("/social/posts/{post_id}/cancel")
def social_cancel_post(post_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_post_api(payload["role"], payload["employee_id"], post_id)
