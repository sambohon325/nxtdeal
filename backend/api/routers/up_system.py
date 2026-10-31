"""Up System routes, extracted from api/app.py (CAF-00120, god_file_app_py --
splitting the monolithic app.py into per-domain routers).

The first of Sam's ~10 "completely missing" dealership workflows -- a real
walk-in/phone-up log with a genuine round-robin floor rotation. See
core/up_system.py's module docstring for why this is deliberately distinct
from lead_routing.py's least-busy auto-assignment, and why a logged Up is a
real Lead rather than a new entity type.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.up_system_api import (
    list_up_types_api,
    list_up_statuses_api,
    get_rotation_api,
    set_board_active_api,
    set_board_order_api,
    log_up_api,
    update_up_status_api,
    list_ups_api,
    get_be_back_board_api,
)

router = APIRouter()


class LogUpRequest(BaseModel):

    up_type: str
    first_name: str
    last_name: str = ""
    phone: str | None = None
    email: str | None = None
    notes: str = ""


class UpdateUpStatusRequest(BaseModel):

    status: str


class SetBoardActiveRequest(BaseModel):

    employee_id: str
    active: bool


class SetBoardOrderRequest(BaseModel):

    employee_ids: list[str]


@router.get("/up-system/types")
def up_system_types(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_up_types_api()


@router.get("/up-system/statuses")
def up_system_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_up_statuses_api()


@router.get("/up-system/rotation")
def up_system_rotation_get(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_rotation_api(payload["role"])


@router.post("/up-system/rotation/active")
def up_system_rotation_active(request: SetBoardActiveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_board_active_api(payload["role"], request.employee_id, request.active)


@router.post("/up-system/rotation/order")
def up_system_rotation_order(request: SetBoardOrderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_board_order_api(payload["role"], request.employee_ids)


@router.post("/up-system/log")
def up_system_log(request: LogUpRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_up_api(
        payload["role"], payload["employee_id"], request.up_type,
        request.first_name, request.last_name,
        phone=request.phone, email=request.email, notes=request.notes,
    )


@router.get("/up-system/ups")
def up_system_list(status: str = None, up_type: str = None, assigned_to: str = None, date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_ups_api(payload["role"], status=status, up_type=up_type, assigned_to=assigned_to, date=date)


@router.post("/up-system/ups/{lead_id}/status")
def up_system_update_status(lead_id: str, request: UpdateUpStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_up_status_api(payload["role"], payload["employee_id"], lead_id, request.status)


@router.get("/up-system/be-back-board")
def up_system_be_back_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_be_back_board_api(payload["role"])
