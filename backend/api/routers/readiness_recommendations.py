"""Readiness Recommendations router -- Readiness' reimagined
"Recommendations" Top Menu item (core/readiness_recommendations.py /
_api.py), item #8 of Sam's 10-item Enterprise Readiness & Intelligence
structure. A real, transparent rules engine (same standing convention as
core/network_audit.py) composed from core/business_health.py +
core/enterprise_risk_center.py + core/marketing_attribution.py + two
genuinely new real signals (service-type revenue trend, marketing
channel-conversion comparison). Deliberately open to every real role (see
core/readiness_recommendations_api.py's own docstring).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/readiness-recommendations/overview"
registered before the dynamic "/readiness-recommendations/{category}" path,
matching the original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.readiness_recommendations_api import (
    get_recommendations_overview_api,
    get_recommendations_category_api,
)


router = APIRouter()


@router.get("/readiness-recommendations/overview")
def readiness_recommendations_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_recommendations_overview_api(payload["role"])


@router.get("/readiness-recommendations/{category}")
def readiness_recommendations_category_route(category: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_recommendations_category_api(payload["role"], category)
