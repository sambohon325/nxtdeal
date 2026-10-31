"""
core/merchandising_api.py -- ACL layer for core/merchandising.py. Viewing is
broad, same set used across this Inventory rebuild. Mutating (photos,
description, featured flag, feed publish) is ADMIN/OPERATIONS/MARKETING --
digital inventory presentation is genuinely Marketing-adjacent work, unlike
Lot Management's physical handling (which granted SERVICE instead). No
department here needs a narrower split than that.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.merchandising import (
    add_vehicle_image, list_vehicle_images,
    update_description, set_featured, get_featured_vehicles,
    get_vdp_health, get_feed_status, publish_to_feed,
    get_merchandising_view, get_merchandising_queue,
    FEED_PLATFORMS,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, MARKETING)


def _denied():
    return {"error": "You don't have access to Merchandising"}


def get_catalog_api():
    return {"feed_platforms": list(FEED_PLATFORMS)}


def add_vehicle_image_api(role, employee_id, vehicle_id, image_url, caption=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return add_vehicle_image(vehicle_id, image_url, employee_id, caption=caption)


def list_vehicle_images_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_vehicle_images(vehicle_id)


def update_description_api(role, employee_id, vehicle_id, description):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_description(vehicle_id, description, employee_id)


def set_featured_api(role, employee_id, vehicle_id, featured):
    if role not in _MUTATE_ROLES:
        return _denied()
    return set_featured(vehicle_id, featured, employee_id)


def get_featured_vehicles_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_featured_vehicles()


def get_vdp_health_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_vdp_health(vehicle_id)


def get_feed_status_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_feed_status(vehicle_id)


def publish_to_feed_api(role, employee_id, vehicle_id, platform):
    if role not in _MUTATE_ROLES:
        return _denied()
    return publish_to_feed(vehicle_id, platform, employee_id)


def get_merchandising_view_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_merchandising_view(vehicle_id)


def get_merchandising_queue_api(role, limit=25, offset=0):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_merchandising_queue(limit=limit, offset=offset)
