"""
ACL layer for core/marketing_attribution.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: this is a dealership-wide Marketing report (Channel Mix, ROI, and
Vehicle Attribution aren't scoped to one creator's own campaign the way
core/campaign_analytics_api.py's per-campaign functions are), so it's gated
to ADMIN/OPERATIONS/MARKETING -- the same ADMIN/OPERATIONS base
core/department_intelligence_api.py's DEPT_INTEL_ROLES uses for its own
cross-department aggregate reports (which swaps in FINANCE for its own
domain), swapped here for MARKETING since this report belongs to that
department specifically.
"""

from core.permissions import ADMIN, OPERATIONS, MARKETING
from core.marketing_attribution import (
    get_channel_mix,
    get_marketing_roi_dashboard,
    get_vehicle_attribution,
)

ATTRIBUTION_ROLES = (ADMIN, OPERATIONS, MARKETING)


def _can_view(role):
    return role in ATTRIBUTION_ROLES


def get_channel_mix_api(role):
    if not _can_view(role):
        return {"error": "You don't have access to marketing attribution data"}
    return get_channel_mix()


def get_marketing_roi_dashboard_api(role):
    if not _can_view(role):
        return {"error": "You don't have access to marketing attribution data"}
    return get_marketing_roi_dashboard()


def get_vehicle_attribution_api(role):
    if not _can_view(role):
        return {"error": "You don't have access to marketing attribution data"}
    return get_vehicle_attribution()
