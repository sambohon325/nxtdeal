"""Inventory Syndication router -- a dealership-wide composition over
merchandising.py's per-vehicle simulated feed status (Cars.com/AutoTrader/
CarGurus/CarFax, rolled up) plus a real cross-platform lead/revenue channel
mix (marketing_attribution.py's get_channel_mix(), filtered to syndication
platforms) and a real "Listing Completeness Risk" cross-reference. Inventory's
9th Top Menu item.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.

core/inventory_syndication_api.py's own module docstring covers the ACL
reasoning: viewing matches core/merchandising_api.py's own established role
set verbatim (ADMIN/OPERATIONS/SALES/SERVICE/MARKETING/FINANCE), bulk
republish is narrower (ADMIN/OPERATIONS/MARKETING). Static
/inventory-syndication/* paths only -- no dynamic {id}-shaped path here to
worry about shadowing.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.inventory_syndication_api import (
    get_catalog_api as syndication_catalog_api,
    get_syndication_overview_api,
    get_feed_health_rollup_api,
    get_syndication_lead_performance_api,
    republish_platform_api,
)


router = APIRouter()


class RepublishPlatformRequest(BaseModel):

    platform: str


@router.get("/inventory-syndication/catalog")
def inventory_syndication_catalog():
    return syndication_catalog_api()


@router.get("/inventory-syndication/overview")
def inventory_syndication_overview(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_syndication_overview_api(payload["role"])


@router.get("/inventory-syndication/feed-health")
def inventory_syndication_feed_health(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_feed_health_rollup_api(payload["role"])


@router.get("/inventory-syndication/lead-performance")
def inventory_syndication_lead_performance(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_syndication_lead_performance_api(payload["role"])


@router.post("/inventory-syndication/republish")
def inventory_syndication_republish(request: RepublishPlatformRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return republish_platform_api(payload["role"], payload["employee_id"], request.platform)
