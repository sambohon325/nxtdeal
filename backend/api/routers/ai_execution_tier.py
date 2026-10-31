"""AI Execution-Tier router -- security-hardening initiative (Task #8).
Backs core/ai_execution_tier.py's Informational/Assisted/Autonomous
classification of every real AI/automation surface in this codebase,
surfaced as a natural sibling screen to Administration's own AI Management
Top Menu item (core/ai_management.py).

New module, not part of the CAF-00120 (god_file_app_py) router-extraction
effort -- there is no pre-existing inline app.py route to extract, since
this whole feature is new. Registered directly as its own router from the
start, matching the shape every extracted router already uses.

ADMIN/OPERATIONS-only throughout, matching core/ai_management_api.py's own
established gate for the screen this classification layer directly extends.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.ai_execution_tier_api import (
    get_execution_tier_overview_api,
    get_execution_tier_for_feature_api,
)


router = APIRouter()


@router.get("/ai-execution-tier/overview")
def ai_execution_tier_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_execution_tier_overview_api(payload["role"])


@router.get("/ai-execution-tier/features/{feature_key}")
def ai_execution_tier_for_feature_route(feature_key: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_execution_tier_for_feature_api(payload["role"], feature_key)
