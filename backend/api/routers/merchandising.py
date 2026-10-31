"""Inventory: Merchandising routes, extracted from api/app.py (CAF-00120,
god_file_app_py -- splitting the monolithic app.py into per-domain routers).

Inventory rebuild, sixth slice. Static /merchandising/catalog,
/merchandising/queue, /merchandising/featured registered before the dynamic
/merchandising/{vehicle_id} path, same route-shadowing-avoidance precedent as
/acquisitions/*, /pricing-desk/*, /lot-control/*.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.merchandising_api import (
    get_catalog_api as merchandising_catalog_api,
    add_vehicle_image_api,
    list_vehicle_images_api,
    update_description_api,
    set_featured_api,
    get_featured_vehicles_api,
    get_vdp_health_api,
    get_feed_status_api,
    publish_to_feed_api,
    get_merchandising_view_api,
    get_merchandising_queue_api,
)

router = APIRouter()


class AddVehicleImageRequest(BaseModel):

    image_url: str
    caption: str = ""


class UpdateDescriptionRequest(BaseModel):

    description: str


class SetFeaturedRequest(BaseModel):

    featured: bool


class PublishToFeedRequest(BaseModel):

    platform: str


@router.get("/merchandising/catalog")
def merchandising_catalog():
    return merchandising_catalog_api()


@router.get("/merchandising/queue")
def merchandising_queue(limit: int = 25, offset: int = 0, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_merchandising_queue_api(payload["role"], limit=limit, offset=offset)


@router.get("/merchandising/featured")
def merchandising_featured(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_featured_vehicles_api(payload["role"])


@router.get("/merchandising/{vehicle_id}")
def merchandising_view(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_merchandising_view_api(payload["role"], vehicle_id)


@router.get("/merchandising/{vehicle_id}/images")
def merchandising_list_images(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_vehicle_images_api(payload["role"], vehicle_id)


@router.post("/merchandising/{vehicle_id}/images")
def merchandising_add_image(vehicle_id: str, request: AddVehicleImageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_vehicle_image_api(payload["role"], payload["employee_id"], vehicle_id, request.image_url, caption=request.caption)


@router.post("/merchandising/{vehicle_id}/description")
def merchandising_update_description(vehicle_id: str, request: UpdateDescriptionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_description_api(payload["role"], payload["employee_id"], vehicle_id, request.description)


@router.post("/merchandising/{vehicle_id}/featured")
def merchandising_set_featured(vehicle_id: str, request: SetFeaturedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_featured_api(payload["role"], payload["employee_id"], vehicle_id, request.featured)


@router.get("/merchandising/{vehicle_id}/vdp-health")
def merchandising_vdp_health(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vdp_health_api(payload["role"], vehicle_id)


@router.get("/merchandising/{vehicle_id}/feed-status")
def merchandising_feed_status(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_feed_status_api(payload["role"], vehicle_id)


@router.post("/merchandising/{vehicle_id}/feed-status/publish")
def merchandising_publish_to_feed(vehicle_id: str, request: PublishToFeedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return publish_to_feed_api(payload["role"], payload["employee_id"], vehicle_id, request.platform)
