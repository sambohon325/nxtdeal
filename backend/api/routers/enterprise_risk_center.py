"""Enterprise Risk Center router -- Readiness' reimagined "Exceptions" Top
Menu item, which is ALSO Sam's separately-named "Enterprise Risk Center"
capstone feature (core/enterprise_risk_center.py / _api.py) -- confirmed the
same real feature before building, so built once. Deliberately open to every
real role (see core/enterprise_risk_center_api.py's own docstring).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/enterprise-risk/overview" registered before
the dynamic "/enterprise-risk/{category}" path, matching the original file's
own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.enterprise_risk_center_api import (
    get_risk_center_overview_api,
    get_risk_center_category_api,
)


router = APIRouter()


@router.get("/enterprise-risk/overview")
def enterprise_risk_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_risk_center_overview_api(payload["role"])


@router.get("/enterprise-risk/{category}")
def enterprise_risk_category_route(category: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_risk_center_category_api(payload["role"], category)
