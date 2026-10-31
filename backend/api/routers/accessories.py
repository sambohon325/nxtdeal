"""Accessories Accelerator router (2026-07-23) -- core/accessories.py's
graph-native accessory upsell motion (Vehicle Sold -> Recommend -> Install ->
Track Revenue), stored directly as attributes on the Customer entity. See that
module's own docstring for the "why graph-native, not a separate store"
reasoning and the honest catalog/attach-rate simulated-vs-real disclosure.

Follows api/routers/customer_journey.py's / api/routers/communications_hub.py's
own established pattern exactly: a self-contained api/routers/<domain>.py module
with its own APIRouter(), importing the shared _authenticate helper from
api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.accessories_api import (
    create_accessory_sale_api,
    generate_accessory_pitch_api,
    get_accessories_overview_api,
    list_accessory_catalog_api,
    mark_installed_api,
    recommend_accessories_api,
)


router = APIRouter()


class CreateAccessorySaleRequest(BaseModel):

    item_ids: list[str]


@router.get("/accessories/catalog")
def accessories_catalog_route(category: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_accessory_catalog_api(payload["role"], category=category)


@router.get("/accessories/overview")
def accessories_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_accessories_overview_api(payload["role"])


@router.get("/accessories/customer/{customer_id}/recommendations")
def accessories_recommendations_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return recommend_accessories_api(payload["role"], customer_id)


@router.post("/accessories/customer/{customer_id}/sale")
def accessories_create_sale_route(
    customer_id: str, request: CreateAccessorySaleRequest, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_accessory_sale_api(payload["role"], customer_id, request.item_ids)


@router.post("/accessories/customer/{customer_id}/sale/{sale_id}/install")
def accessories_install_route(customer_id: str, sale_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_installed_api(payload["role"], customer_id, sale_id)


@router.post("/accessories/customer/{customer_id}/pitch")
def accessories_pitch_route(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_accessory_pitch_api(payload["role"], customer_id)
