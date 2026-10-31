"""
Thin ACL layer for core/vehicle_lifecycle.py (session 106 follow-up), same "no
service layer indirection" convention as every other `*_api.py` module.

Role rule: viewing a vehicle's lifecycle (status/recon checklist/vendor
assignments/acquisition data) is broad -- ADMIN/OPERATIONS/SALES/SERVICE/
MARKETING -- since every one of those departments genuinely cares about where a
given unit is in the pipeline (Sales needs to know a promised vehicle isn't ready,
Service is often the one doing the recon work, Marketing needs Front-Line-Ready
units for merchandising). Mutating the lifecycle (advancing status, checking off
recon items, assigning/updating vendor work) is narrower -- ADMIN/OPERATIONS/
SERVICE -- since those are the departments that actually move a vehicle through
recon, matching core/appointments_api.py's own Sales/Service split precedent but
without Sales, since desking a sold car doesn't move it through recon.
"""

from core.vehicle_lifecycle import (
    get_vehicle_lifecycle,
    update_lifecycle_status,
    update_recon_item,
    assign_vendor,
    update_vendor_status,
    list_by_stage,
    get_cost_breakdown,
    update_cost_breakdown,
    get_ownership,
    assign_ownership,
    get_vehicle_activity_feed,
    get_vehicle_workspace,
    LIFECYCLE_STAGES,
    RECON_ITEMS,
    VENDOR_TYPES,
    VENDOR_STATUSES,
    COST_FIELDS,
    OWNERSHIP_ROLES,
)
from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)

# Inventory department's Master Vehicle Workspace additions (cost breakdown,
# ownership, composed activity feed/workspace): viewing stays the same broad set
# as the rest of this module (now including FINANCE, since Cost Breakdown/
# Floorplan Interest are genuinely finance-relevant real dollar figures).
# Mutating splits narrower than the recon/vendor _MUTATE_ROLES above: editing
# dollar figures is ADMIN/OPERATIONS/FINANCE (not SERVICE -- Service does recon
# work, not cost accounting), assigning ownership/managers is ADMIN/OPERATIONS
# only (not SERVICE or FINANCE -- deciding who owns a vehicle problem is an
# Inventory-management call).
_COST_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)
_OWNERSHIP_MUTATE_ROLES = (ADMIN, OPERATIONS)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def list_lifecycle_catalog_api():
    return {
        "stages": LIFECYCLE_STAGES,
        "recon_items": list(RECON_ITEMS),
        "vendor_types": list(VENDOR_TYPES),
        "vendor_statuses": list(VENDOR_STATUSES),
        "cost_fields": list(COST_FIELDS),
        "ownership_roles": list(OWNERSHIP_ROLES),
    }


def get_vehicle_lifecycle_api(role, vehicle_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to vehicle lifecycle data"}

    return get_vehicle_lifecycle(vehicle_id)


# Phase 6: reconditioning cycle-time + SLA analytics (view-tier).
def get_recon_metrics_api(role):
    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to recon analytics"}
    from core.recon_analytics import get_recon_metrics
    return get_recon_metrics()


def get_recon_sla_alerts_api(role):
    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to recon analytics"}
    from core.recon_analytics import get_recon_sla_alerts
    return get_recon_sla_alerts()


def get_vehicle_recon_timeline_api(role, vehicle_id):
    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to recon analytics"}
    from core.recon_analytics import get_vehicle_recon_timeline
    return get_vehicle_recon_timeline(vehicle_id)


def update_lifecycle_status_api(role, employee_id, vehicle_id, new_status):

    if role not in _MUTATE_ROLES:
        return {"error": "You don't have access to advance a vehicle's lifecycle status"}

    return update_lifecycle_status(vehicle_id, new_status, employee_id)


def update_recon_item_api(role, employee_id, vehicle_id, item, complete, notes=""):

    if role not in _MUTATE_ROLES:
        return {"error": "You don't have access to update the recon checklist"}

    return update_recon_item(vehicle_id, item, complete, employee_id, notes=notes)


def assign_vendor_api(role, employee_id, vehicle_id, vendor_type, vendor_name, notes=""):

    if role not in _MUTATE_ROLES:
        return {"error": "You don't have access to assign vendor work"}

    return assign_vendor(vehicle_id, vendor_type, vendor_name, employee_id, notes=notes)


def update_vendor_status_api(role, employee_id, vehicle_id, assignment_id, new_status):

    if role not in _MUTATE_ROLES:
        return {"error": "You don't have access to update vendor work status"}

    return update_vendor_status(vehicle_id, assignment_id, new_status, employee_id)


def list_lifecycle_board_api(role, stage=None):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to the vehicle lifecycle board"}

    return list_by_stage(stage=stage)


def get_vehicle_workspace_api(role, vehicle_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to the vehicle workspace"}

    return get_vehicle_workspace(vehicle_id)


def get_cost_breakdown_api(role, vehicle_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to vehicle cost data"}

    return get_cost_breakdown(vehicle_id)


def update_cost_breakdown_api(role, employee_id, vehicle_id, **fields):

    if role not in _COST_MUTATE_ROLES:
        return {"error": "You don't have access to edit vehicle cost data"}

    return update_cost_breakdown(vehicle_id, employee_id, **fields)


def get_ownership_api(role, vehicle_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to vehicle ownership data"}

    return get_ownership(vehicle_id)


def assign_ownership_api(role, employee_id, vehicle_id, **roles):

    if role not in _OWNERSHIP_MUTATE_ROLES:
        return {"error": "You don't have access to assign vehicle ownership"}

    return assign_ownership(vehicle_id, employee_id, **roles)


def get_vehicle_activity_feed_api(role, vehicle_id, limit=100):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to vehicle activity data"}

    return get_vehicle_activity_feed(vehicle_id, limit=limit)
