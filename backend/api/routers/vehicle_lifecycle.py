"""Operations: Vehicle Lifecycle Management routes, extracted from api/app.py
(CAF-00120, god_file_app_py).

Session 106 follow-up -- the flagship build of Operations' rebuild -- Sam's
own framing: "Sales should manage the customer lifecycle. Operations should
manage the vehicle lifecycle... This should be one of the largest
operational modules." Additive attributes on the existing Vehicle entity
(lifecycle_status, recon_checklist, vendor_assignments), same convention as
core/deals.py's trade_in/delivery_checklist. See core/vehicle_lifecycle.py's
module docstring for the honest scope notes (no acquisition-date/source/
buyer field exists on most Vehicles, no real Vendor roster).

Also includes Inventory's Master Vehicle Workspace (Inventory department
rebuild, first slice -- Sam picked "Inventory" over Acquisitions/Pricing/
Overview as the centerpiece screen): Cost Breakdown, Ownership, and a
composed Activity Feed on top of the same Vehicle entity. /workspace is the
one-call payload the frontend's main vehicle detail view uses; the
individual /cost-breakdown, /ownership, and /activity endpoints exist for
targeted refetches after a single mutation.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate
from core.vehicle_lifecycle_api import (
    list_lifecycle_catalog_api,
    get_vehicle_lifecycle_api,
    update_lifecycle_status_api,
    update_recon_item_api,
    assign_vendor_api,
    update_vendor_status_api,
    list_lifecycle_board_api,
    get_vehicle_workspace_api,
    get_cost_breakdown_api,
    update_cost_breakdown_api,
    get_ownership_api,
    assign_ownership_api,
    get_vehicle_activity_feed_api,
)

router = APIRouter()


class UpdateLifecycleStatusRequest(BaseModel):

    new_status: str


class UpdateReconItemRequest(BaseModel):

    item: str
    complete: bool
    notes: str = ""


class AssignVendorRequest(BaseModel):

    vendor_type: str
    vendor_name: str
    notes: str = ""


class UpdateVendorStatusRequest(BaseModel):

    new_status: str


# Inventory's Master Vehicle Workspace (Inventory department rebuild, first
# slice) request models. All fields optional -- a caller only sends the ones
# they're actually changing, same partial-update convention as
# UpdateDeliveryChecklistRequest.
class UpdateCostBreakdownRequest(BaseModel):

    acquisition_cost: float = None
    transport_cost: float = None
    recon_cost: float = None
    floorplan_interest: float = None
    marketing_cost: float = None


class AssignOwnershipRequest(BaseModel):

    buyer: str = None
    inventory_manager: str = None
    recon_manager: str = None
    sales_manager: str = None


@router.get("/vehicle-lifecycle/catalog")
def vehicle_lifecycle_catalog():
    """Open, unauthenticated catalog lookup -- same treatment as
    /appointments/types -- the stage/recon-item/vendor-type/vendor-status
    vocabularies aren't sensitive."""

    return list_lifecycle_catalog_api()


@router.get("/vehicle-lifecycle/board")
def vehicle_lifecycle_board(stage: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_lifecycle_board_api(payload["role"], stage=stage)


# Phase 6 recon analytics. Static paths registered before the dynamic /{vehicle_id}.
@router.get("/vehicle-lifecycle/recon-metrics")
def vehicle_lifecycle_recon_metrics(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from core.vehicle_lifecycle_api import get_recon_metrics_api
    return get_recon_metrics_api(payload["role"])


@router.get("/vehicle-lifecycle/recon-alerts")
def vehicle_lifecycle_recon_alerts(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from core.vehicle_lifecycle_api import get_recon_sla_alerts_api
    return get_recon_sla_alerts_api(payload["role"])


@router.get("/vehicle-lifecycle/{vehicle_id}")
def vehicle_lifecycle_get(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_lifecycle_api(payload["role"], vehicle_id)


@router.get("/vehicle-lifecycle/{vehicle_id}/recon-timeline")
def vehicle_lifecycle_recon_timeline(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from core.vehicle_lifecycle_api import get_vehicle_recon_timeline_api
    return get_vehicle_recon_timeline_api(payload["role"], vehicle_id)


@router.post("/vehicle-lifecycle/{vehicle_id}/status")
def vehicle_lifecycle_update_status(vehicle_id: str, request: UpdateLifecycleStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_lifecycle_status_api(payload["role"], payload["employee_id"], vehicle_id, request.new_status)


@router.post("/vehicle-lifecycle/{vehicle_id}/recon")
def vehicle_lifecycle_update_recon(vehicle_id: str, request: UpdateReconItemRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_recon_item_api(payload["role"], payload["employee_id"], vehicle_id, request.item, request.complete, notes=request.notes)


@router.post("/vehicle-lifecycle/{vehicle_id}/vendor")
def vehicle_lifecycle_assign_vendor(vehicle_id: str, request: AssignVendorRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_vendor_api(payload["role"], payload["employee_id"], vehicle_id, request.vendor_type, request.vendor_name, notes=request.notes)


@router.post("/vehicle-lifecycle/{vehicle_id}/vendor/{assignment_id}/status")
def vehicle_lifecycle_update_vendor_status(vehicle_id: str, assignment_id: str, request: UpdateVendorStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_vendor_status_api(payload["role"], payload["employee_id"], vehicle_id, assignment_id, request.new_status)


@router.get("/vehicle-lifecycle/{vehicle_id}/workspace")
def vehicle_lifecycle_workspace(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_workspace_api(payload["role"], vehicle_id)


@router.get("/vehicle-lifecycle/{vehicle_id}/cost-breakdown")
def vehicle_lifecycle_get_cost_breakdown(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_cost_breakdown_api(payload["role"], vehicle_id)


@router.post("/vehicle-lifecycle/{vehicle_id}/cost-breakdown")
def vehicle_lifecycle_update_cost_breakdown(vehicle_id: str, request: UpdateCostBreakdownRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    fields = {k: v for k, v in request.dict().items() if v is not None}
    return update_cost_breakdown_api(payload["role"], payload["employee_id"], vehicle_id, **fields)


@router.get("/vehicle-lifecycle/{vehicle_id}/ownership")
def vehicle_lifecycle_get_ownership(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ownership_api(payload["role"], vehicle_id)


@router.post("/vehicle-lifecycle/{vehicle_id}/ownership")
def vehicle_lifecycle_assign_ownership(vehicle_id: str, request: AssignOwnershipRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    roles = {k: v for k, v in request.dict().items() if v is not None}
    return assign_ownership_api(payload["role"], payload["employee_id"], vehicle_id, **roles)


@router.get("/vehicle-lifecycle/{vehicle_id}/activity")
def vehicle_lifecycle_get_activity(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_activity_feed_api(payload["role"], vehicle_id)
