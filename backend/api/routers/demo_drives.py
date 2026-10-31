"""Demo Drive router -- the fourth of Sam's ~10 "completely missing"
dealership workflows (core/demo_drive.py / core/demo_drive_api.py, session
102 follow-up).

A real test-drive log (which prospect drove which vehicle, with which
salesperson, driver's-license capture/verification, out/in odometer,
out -> returned lifecycle).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/demo-drives/statuses",
"/demo-drives/interest-levels", "/demo-drives/active", and
"/demo-drives/dashboard" are all registered before the dynamic
"/demo-drives/{demo_id}" siblings, matching the original file's own
route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.demo_drive_api import (
    list_demo_statuses_api,
    list_interest_levels_api,
    start_demo_drive_api,
    return_demo_drive_api,
    cancel_demo_drive_api,
    list_active_demo_drives_api,
    list_demo_drives_api,
    get_demo_drive_dashboard_api,
)


router = APIRouter()


class StartDemoDriveRequest(BaseModel):

    linked_entity_id: str
    vehicle_id: str
    salesperson_id: str
    license_number: str = ""
    license_verified: bool = False
    odometer_out: int | None = None
    notes: str = ""


class ReturnDemoDriveRequest(BaseModel):

    odometer_in: int | None = None
    interest_level: str | None = None
    feedback: str = ""


@router.get("/demo-drives/statuses")
def demo_drive_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_demo_statuses_api()


@router.get("/demo-drives/interest-levels")
def demo_drive_interest_levels(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_interest_levels_api()


@router.get("/demo-drives/active")
def demo_drive_active(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_active_demo_drives_api(payload["role"])


@router.get("/demo-drives/dashboard")
def demo_drive_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_demo_drive_dashboard_api(payload["role"])


@router.post("/demo-drives")
def demo_drive_start(request: StartDemoDriveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_demo_drive_api(
        payload["role"],
        request.linked_entity_id,
        request.vehicle_id,
        request.salesperson_id,
        license_number=request.license_number,
        license_verified=request.license_verified,
        odometer_out=request.odometer_out,
        notes=request.notes,
    )


@router.get("/demo-drives")
def demo_drive_list(status: str = None, salesperson_id: str = None, vehicle_id: str = None,
                    authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_demo_drives_api(payload["role"], status=status, salesperson_id=salesperson_id, vehicle_id=vehicle_id)


@router.post("/demo-drives/{demo_id}/return")
def demo_drive_return(demo_id: str, request: ReturnDemoDriveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return return_demo_drive_api(
        payload["role"], demo_id,
        odometer_in=request.odometer_in,
        interest_level=request.interest_level,
        feedback=request.feedback,
    )


@router.post("/demo-drives/{demo_id}/cancel")
def demo_drive_cancel(demo_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_demo_drive_api(payload["role"], demo_id)
