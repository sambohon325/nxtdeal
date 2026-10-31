"""Performance Readiness router -- Readiness reframe item #4, "Goal Tracking
against real pace" (core/performance_readiness.py / _api.py). Deliberately
open to every real role (see core/performance_readiness_api.py's own
docstring) -- read-only, non-sensitive forward-looking performance data,
same precedent as /business-health/*. Goal-SETTING itself lives at
/system-config/department-goals (ADMIN/OPERATIONS-only), not duplicated
here.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/performance-readiness/overview" registered
before the dynamic "/performance-readiness/{department}" path, matching the
original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.performance_readiness_api import (
    get_performance_readiness_overview_api,
    get_performance_readiness_department_api,
)


router = APIRouter()


@router.get("/performance-readiness/overview")
def performance_readiness_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_performance_readiness_overview_api(payload["role"])


@router.get("/performance-readiness/{department}")
def performance_readiness_department_route(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_performance_readiness_department_api(payload["role"], department)
