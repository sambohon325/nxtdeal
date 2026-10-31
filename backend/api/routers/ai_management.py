"""AI Management router -- Administration Control Center's "AI Management"
Top Menu item (core/ai_management.py). Real per-feature kill switches
across every OpenAI-backed feature in this codebase (AI_FEATURE_CATALOG),
plus real in-memory call-attempt counters (attempted/succeeded/fell_back/
blocked) -- no fabricated usage/cost/token numbers, since this sandbox has
no real OpenAI network access and no per-call cost/token tracking model
exists anywhere in this codebase.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static paths registered before the dynamic
/ai-management/features/{feature_key} path, matching the original file's own
route-shadowing-avoidance ordering.

ADMIN/OPERATIONS-only throughout, matching this whole department's
established gate.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.ai_management_api import (
    get_ai_management_overview_api,
    get_ai_feature_catalog_api,
    get_ai_call_stats_api,
    set_ai_feature_enabled_api,
)


router = APIRouter()


class SetAiFeatureEnabledRequest(BaseModel):

    enabled: bool


@router.get("/ai-management/overview")
def ai_management_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ai_management_overview_api(payload["role"])


@router.get("/ai-management/catalog")
def ai_management_catalog_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ai_feature_catalog_api(payload["role"])


@router.get("/ai-management/stats")
def ai_management_stats_route(feature_key: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ai_call_stats_api(payload["role"], feature_key=feature_key)


@router.post("/ai-management/features/{feature_key}")
def set_ai_feature_enabled_route(feature_key: str, request: SetAiFeatureEnabledRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_ai_feature_enabled_api(payload["role"], payload["employee_id"], feature_key, request.enabled)
