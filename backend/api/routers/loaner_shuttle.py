"""Loaner & Shuttle Management router -- the third of Service's "completely
missing" features (core/loaner_shuttle.py / core/loaner_shuttle_api.py,
session 111 follow-up).

Covers loaner-vehicle fleet management (add/list/board/get/status), loaner
checkout/checkin assignments (plus per-RO and per-customer assignment
lookups), shuttle requests (create/list/queue/get/assign-driver/status), and
a composed per-RO transportation summary.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/loaner-fleet", "/loaner-fleet/
board", "/loaner-assignments/checkout", "/shuttle-requests", and
"/shuttle-requests/queue" are all registered before their own dynamic
"/{loaner_id}"/"/{assignment_id}"/"/{request_id}" siblings, matching the
original file's own route-shadowing-avoidance ordering.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.loaner_shuttle_api import (
    add_loaner_vehicle_api,
    update_loaner_status_api,
    get_loaner_vehicle_api,
    list_loaner_fleet_api,
    get_loaner_board_api,
    checkout_loaner_api,
    checkin_loaner_api,
    get_assignment_api,
    get_assignments_for_ro_api,
    get_assignments_for_customer_api,
    request_shuttle_api,
    assign_shuttle_driver_api,
    update_shuttle_status_api,
    get_shuttle_request_api,
    list_shuttle_requests_api,
    get_shuttle_requests_for_ro_api,
    get_shuttle_queue_api,
    get_ro_transportation_summary_api,
)


router = APIRouter()


class AddLoanerVehicleRequest(BaseModel):

    make: str
    model: str
    year: str | int | None = None
    vin: str = ""
    mileage: int | None = None
    notes: str = ""


class UpdateLoanerStatusRequest(BaseModel):

    status: str
    notes: str = ""


class CheckoutLoanerRequest(BaseModel):

    loaner_vehicle_id: str
    customer_id: str
    odometer_out: int
    fuel_out: str = "Full"
    ro_id: str | None = None
    expected_return_at: str | None = None
    agreement_signed: bool = False
    notes: str = ""


class CheckinLoanerRequest(BaseModel):

    odometer_in: int
    fuel_in: str = "Full"
    send_to_maintenance: bool = False
    notes: str = ""


class RequestShuttleRequest(BaseModel):

    customer_id: str
    direction: str
    pickup_location: str = ""
    dropoff_location: str = ""
    requested_time: str = ""
    ro_id: str | None = None
    notes: str = ""


class AssignShuttleDriverRequest(BaseModel):

    driver_id: str


class UpdateShuttleStatusRequest(BaseModel):

    status: str
    notes: str = ""


@router.post("/loaner-fleet")
def loaner_fleet_add(body: AddLoanerVehicleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_loaner_vehicle_api(payload["role"], payload["employee_id"], body.make, body.model, body.year, body.vin, body.mileage, notes=body.notes)


@router.get("/loaner-fleet")
def loaner_fleet_list(status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_loaner_fleet_api(payload["role"], status=status)


@router.get("/loaner-fleet/board")
def loaner_fleet_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loaner_board_api(payload["role"])


@router.get("/loaner-fleet/{loaner_id}")
def loaner_fleet_get(loaner_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loaner_vehicle_api(payload["role"], loaner_id)


@router.post("/loaner-fleet/{loaner_id}/status")
def loaner_fleet_update_status(loaner_id: str, body: UpdateLoanerStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_loaner_status_api(payload["role"], payload["employee_id"], loaner_id, body.status, notes=body.notes)


@router.post("/loaner-assignments/checkout")
def loaner_assignments_checkout(body: CheckoutLoanerRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return checkout_loaner_api(
        payload["role"], payload["employee_id"], body.loaner_vehicle_id, body.customer_id, body.odometer_out,
        fuel_out=body.fuel_out, ro_id=body.ro_id, expected_return_at=body.expected_return_at,
        agreement_signed=body.agreement_signed, notes=body.notes,
    )


@router.post("/loaner-assignments/{assignment_id}/checkin")
def loaner_assignments_checkin(assignment_id: str, body: CheckinLoanerRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return checkin_loaner_api(
        payload["role"], payload["employee_id"], assignment_id, body.odometer_in,
        fuel_in=body.fuel_in, send_to_maintenance=body.send_to_maintenance, notes=body.notes,
    )


@router.get("/loaner-assignments/{assignment_id}")
def loaner_assignments_get(assignment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_assignment_api(payload["role"], assignment_id)


@router.get("/repair-orders/{ro_id}/loaner-assignments")
def repair_order_loaner_assignments(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_assignments_for_ro_api(payload["role"], ro_id)


@router.get("/customers/{customer_id}/loaner-assignments")
def customer_loaner_assignments(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_assignments_for_customer_api(payload["role"], customer_id)


@router.post("/shuttle-requests")
def shuttle_requests_create(body: RequestShuttleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_shuttle_api(
        payload["role"], payload["employee_id"], body.customer_id, body.direction,
        body.pickup_location, body.dropoff_location, body.requested_time,
        ro_id=body.ro_id, notes=body.notes,
    )


@router.get("/shuttle-requests")
def shuttle_requests_list(status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_shuttle_requests_api(payload["role"], status=status)


@router.get("/shuttle-requests/queue")
def shuttle_requests_queue(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_shuttle_queue_api(payload["role"])


@router.get("/shuttle-requests/{request_id}")
def shuttle_requests_get(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_shuttle_request_api(payload["role"], request_id)


@router.post("/shuttle-requests/{request_id}/assign-driver")
def shuttle_requests_assign_driver(request_id: str, body: AssignShuttleDriverRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_shuttle_driver_api(payload["role"], payload["employee_id"], request_id, body.driver_id)


@router.post("/shuttle-requests/{request_id}/status")
def shuttle_requests_update_status(request_id: str, body: UpdateShuttleStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_shuttle_status_api(payload["role"], payload["employee_id"], request_id, body.status, notes=body.notes)


@router.get("/repair-orders/{ro_id}/shuttle-requests")
def repair_order_shuttle_requests(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_shuttle_requests_for_ro_api(payload["role"], ro_id)


@router.get("/repair-orders/{ro_id}/transportation")
def repair_order_transportation_summary(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ro_transportation_summary_api(payload["role"], ro_id)
