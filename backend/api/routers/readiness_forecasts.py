"""Readiness Forecasts router -- Readiness reframe item #5, "predictive
analytics engine" (core/readiness_forecasts.py / _api.py): Sales Units/
Gross/Closing Ratio/Revenue, Service Labor Sales/Parts Sales/RO Count/
Capacity, Inventory Units Likely To Sell/Age + Wholesale Candidates, Finance
Funding/Collections/Delinquencies/Portfolio Performance -- plus the Readiness
Timeline capstone (Last 7 Days/30 Days/90 Days/Year To Date, "to spot trends
before competitors do"). Deliberately open to every real role, same
"everyone can see tomorrow, a week, a month, a quarter" precedent as
/performance-readiness/* and /business-health/*. Individual sub-signals
(Collections/Portfolio Performance) keep their own narrower ADMIN/OPERATIONS/
FINANCE gate at their own layer and degrade gracefully, not re-gated here.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/readiness-forecasts/overview" and
"/readiness-timeline/overview" registered before their respective dynamic
"/{department}" paths, matching the original file's own route-shadowing-
avoidance ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.readiness_forecasts_api import (
    get_forecasts_overview_api,
    get_forecasts_department_api,
    get_readiness_timeline_overview_api,
    get_readiness_timeline_department_api,
)


router = APIRouter()


@router.get("/readiness-forecasts/overview")
def readiness_forecasts_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_forecasts_overview_api(payload["role"])


@router.get("/readiness-forecasts/{department}")
def readiness_forecasts_department_route(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_forecasts_department_api(payload["role"], department)


@router.get("/readiness-timeline/overview")
def readiness_timeline_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_readiness_timeline_overview_api(payload["role"])


@router.get("/readiness-timeline/{department}")
def readiness_timeline_department_route(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_readiness_timeline_department_api(payload["role"], department)
