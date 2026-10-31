"""Data Health router -- Readiness' "Data Health" Top Menu item, GREATLY
EXPANDED (core/data_health.py / _api.py). Deliberately ADMIN/OPERATIONS-only,
matching this item's own historical gate (core/data_connections_api.py's
CONNECTION_ROLES) -- see core/data_health_api.py's own docstring.

No route is needed for the base/merged view (it's served by the existing
generic GET /menu/data?department=Readiness&item_key=data_health path via
core/menu_data.py's unchanged readiness_data_health alias, which returns
core/readiness_menu.py's enriched data_health() including all 4 new
sections) -- these 5 routes back the dedicated board's own on-demand fetch
(bypassing the generic dispatcher, same as every other bespoke board) and
per-section drill-down fetches.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. All 5 routes here are static (no path-param routes in
this block), same ordering discipline as every other extracted router.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.data_health_api import (
    get_data_health_overview_api,
    get_integration_monitoring_api,
    get_data_completeness_api,
    get_data_accuracy_api,
    get_data_freshness_api,
)


router = APIRouter()


@router.get("/data-health/overview")
def data_health_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_data_health_overview_api(payload["role"])


@router.get("/data-health/integration-monitoring")
def data_health_integration_monitoring_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_integration_monitoring_api(payload["role"])


@router.get("/data-health/completeness")
def data_health_completeness_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_data_completeness_api(payload["role"])


@router.get("/data-health/accuracy")
def data_health_accuracy_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_data_accuracy_api(payload["role"])


@router.get("/data-health/freshness")
def data_health_freshness_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_data_freshness_api(payload["role"])
