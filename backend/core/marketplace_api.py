"""
core/marketplace_api.py -- API layer for the NXTDeal Marketplace (2026-07-24).
Browsing the catalog and every listing's install state is open to any authenticated role.
Installing / uninstalling a listing is ADMIN -- it changes what the dealership has connected.
"""

from core.permissions import ADMIN
from core.marketplace import (
    get_marketplace,
    get_listing,
    install_listing,
    uninstall_listing,
)


def get_marketplace_api(role):
    from core.administration_access import system_admin_context
    return {**get_marketplace(role=role), "can_manage": role == ADMIN and system_admin_context.get()}


def get_listing_api(role, listing_id):
    return get_listing(listing_id)


def install_listing_api(admin_role, admin_id, listing_id):
    if admin_role != ADMIN:
        return {"error": "Admin role required to install a Marketplace listing"}
    return install_listing(listing_id, admin_id=admin_id)


def uninstall_listing_api(admin_role, admin_id, listing_id):
    if admin_role != ADMIN:
        return {"error": "Admin role required to remove a Marketplace listing"}
    return uninstall_listing(listing_id, admin_id=admin_id)
