"""Inventory Advertising Engine router -- core/inventory_advertising.py's
inventory-driven auto ad campaigns (rule-based campaign specs across meta/google/
retargeting/price_drop/aged_inventory, plus a real, kill-switched AI ad-copy
call). See that module's own docstring for the full "real qualification /
simulated ad-platform output" reasoning.

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.inventory_advertising_api import (
    aged_inventory_campaigns_api,
    generate_ad_copy_api,
    generate_campaign_api,
    get_advertising_overview_api,
    list_campaigns_api,
    price_drop_campaigns_api,
)


router = APIRouter()


@router.get("/inventory-advertising/overview")
def inventory_advertising_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_advertising_overview_api(payload["role"])


@router.get("/inventory-advertising/campaigns")
def inventory_advertising_campaigns_route(
    channel: str = None, vehicle_id: str = None, limit: int = 500, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_campaigns_api(payload["role"], channel=channel, vehicle_id=vehicle_id, limit=limit)


@router.post("/inventory-advertising/vehicle/{vehicle_id}/campaign")
def inventory_advertising_generate_campaign_route(
    vehicle_id: str, channel: str, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_campaign_api(payload["role"], vehicle_id, channel)


@router.get("/inventory-advertising/price-drops")
def inventory_advertising_price_drops_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return price_drop_campaigns_api(payload["role"])


@router.get("/inventory-advertising/aged")
def inventory_advertising_aged_route(days_threshold: int = 60, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return aged_inventory_campaigns_api(payload["role"], days_threshold=days_threshold)


@router.post("/inventory-advertising/vehicle/{vehicle_id}/ad-copy")
def inventory_advertising_ad_copy_route(
    vehicle_id: str, channel: str, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_ad_copy_api(payload["role"], vehicle_id, channel)
