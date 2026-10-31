"""Thin ACL layer for core/inventory_advertising.py's inventory-driven auto ad
campaigns -- same "no service-layer indirection" convention as every other
*_api.py module in this codebase.

VIEW_ROLES is narrower than the cross-department Communications Hub / Customer
Journey tuple: advertising is a Marketing capability (with Operations for the
cross-department command center and Admin for full oversight), so only ADMIN,
OPERATIONS, and MARKETING can view or build inventory ad campaigns -- Sales/
Service/Finance have no reason to spin up ad spend against inventory. Same
tier the Marketing dashboards use.

core/inventory_advertising.py raises ValueError on an unknown vehicle / invalid
channel; this layer catches that and returns the same {"error": ...} dict shape
every other *_api.py module surfaces, so routers and callers get one uniform
error contract.
"""

from core.inventory_advertising import (
    CHANNELS,
    aged_inventory_campaigns,
    generate_ad_copy,
    generate_campaign,
    get_advertising_overview,
    list_campaigns,
    price_drop_campaigns,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "MARKETING")


def get_advertising_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the inventory advertising overview."}

    return get_advertising_overview()


def list_campaigns_api(role, channel=None, vehicle_id=None, limit=500):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view inventory ad campaigns."}

    return list_campaigns(channel=channel, vehicle_id=vehicle_id, limit=limit)


def generate_campaign_api(role, vehicle_id, channel):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate an inventory ad campaign."}

    try:
        return generate_campaign(vehicle_id, channel)
    except ValueError as exc:
        return {"error": str(exc)}


def price_drop_campaigns_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to build price-drop campaigns."}

    return price_drop_campaigns()


def aged_inventory_campaigns_api(role, days_threshold=60):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to build aged-inventory campaigns."}

    return aged_inventory_campaigns(days_threshold=days_threshold)


def generate_ad_copy_api(role, vehicle_id, channel):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate inventory ad copy."}

    try:
        return generate_ad_copy(vehicle_id, channel)
    except ValueError as exc:
        return {"error": str(exc)}
