"""Business Health router -- Readiness' new executive-layer Top Menu item
(core/business_health.py / _api.py). Deliberately open to every real role
(see core/business_health_api.py's own docstring).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/business-health/overview" registered before
the dynamic "/business-health/{department}" path, matching the original
file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.business_health_api import (
    get_business_health_overview_api,
    get_business_health_department_api,
)


router = APIRouter()


@router.get("/business-health/overview")
def business_health_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_business_health_overview_api(payload["role"])


@router.get("/business-health/{department}")
def business_health_department_route(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_business_health_department_api(payload["role"], department)
