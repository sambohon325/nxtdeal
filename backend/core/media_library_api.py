"""Thin ACL layer for core/media_library.py's shared image asset library -- same
"no service-layer indirection" convention as every other *_api.py module.

VIEW_ROLES is all six real employee roles: the shared library is meant to be reachable
from every marketing-adjacent tool (email builder, website builder, social, asset
design), and any of them can be opened by any department, so reads are open to all
authenticated roles -- same broad tier as the Communications Hub / Customer Journey
views. WRITE_ROLES (add/remove a dealership-wide asset) is the narrower
ADMIN/OPERATIONS/MARKETING tier, matching who curates brand/marketing assets everywhere
else (core/system_config_api.py's brand settings, core/assets.py's approval workflow).
Inventory images are never written through here (they belong to the vehicle).
"""

from core.media_library import (
    list_library_images,
    list_categories,
    add_library_image,
    remove_library_image,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")
WRITE_ROLES = ("ADMIN", "OPERATIONS", "MARKETING")


def list_media_categories_api(role):
    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the media library."}
    return {"categories": list_categories()}


def list_media_api(role, category=None, query=None):
    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the media library."}
    result = list_library_images(category=category, query=query)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"images": result}


def add_media_api(role, url, name, category, uploaded_by, tags=None):
    if role not in WRITE_ROLES:
        return {"error": f"Role '{role}' is not permitted to add a shared media asset."}
    result = add_library_image(url, name, category, uploaded_by, tags=tags)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"image": result}


def remove_media_api(role, image_id):
    if role not in WRITE_ROLES:
        return {"error": f"Role '{role}' is not permitted to remove a shared media asset."}
    return remove_library_image(image_id)
