"""
core/inventory_syndication_api.py -- ACL layer for core/inventory_syndication.py.
Viewing is broad, matching core/merchandising_api.py's own _VIEW_ROLES exactly
(this is the same digital-inventory-presentation ground, just rolled up
dealership-wide instead of per-vehicle). Bulk republish is ADMIN/OPERATIONS/
MARKETING, matching that same module's own _MUTATE_ROLES exactly -- a bulk
action reusing the identical per-vehicle publish_to_feed() mechanism should
carry the identical gate.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE
from core.inventory_syndication import (
    get_feed_health_rollup,
    get_syndication_lead_performance,
    republish_platform,
    get_syndication_overview,
)
from core.merchandising import FEED_PLATFORMS

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, MARKETING)


def _denied():
    return {"error": "You don't have access to Inventory Syndication"}


def get_catalog_api():
    return {"feed_platforms": list(FEED_PLATFORMS)}


def get_syndication_overview_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_syndication_overview()


def get_feed_health_rollup_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_feed_health_rollup()


def get_syndication_lead_performance_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_syndication_lead_performance()


def republish_platform_api(role, employee_id, platform):
    if role not in _MUTATE_ROLES:
        return _denied()
    return republish_platform(platform, employee_id)
