"""Marketing Studio router -- AI-generated marketing content drafts across
7 content types (email/SMS copy, website section/SEO copy, vehicle
description, social caption, ad recommendation), Marketing's "AI Studio"
Top Menu item.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.

core/marketing_studio_api.py's own module docstring covers the ACL reasoning:
ADMIN/MARKETING for both viewing and mutating -- a generated draft can carry
unreleased marketing copy, matching core/email_templates_api.py's/
core/social_posts_api.py's own content-creation precedent.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.marketing_studio_api import (
    get_studio_overview_api,
    list_content_drafts_api,
    generate_content_api,
    mark_applied_api,
    mark_discarded_api,
)


router = APIRouter()


class GenerateContentRequest(BaseModel):

    content_type: str
    params: dict = None


@router.get("/marketing-studio/overview")
def marketing_studio_overview(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_studio_overview_api(payload["role"])


@router.get("/marketing-studio/drafts")
def marketing_studio_drafts_list(
    content_type: str = None,
    status: str = None,
    created_by: str = None,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_content_drafts_api(
        payload["role"], content_type=content_type, status=status, created_by=created_by
    )


@router.post("/marketing-studio/generate")
def marketing_studio_generate(request: GenerateContentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_content_api(
        payload["role"], request.content_type, request.params or {}, payload["employee_id"]
    )


@router.post("/marketing-studio/drafts/{draft_id}/apply")
def marketing_studio_apply_draft(draft_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_applied_api(payload["role"], draft_id, payload["employee_id"])


@router.post("/marketing-studio/drafts/{draft_id}/discard")
def marketing_studio_discard_draft(draft_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_discarded_api(payload["role"], draft_id, payload["employee_id"])
