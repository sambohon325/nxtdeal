"""Devices router -- GPS & Starter Interrupt Device Management (Finance's
"GPS & Devices" and "Starter Interrupt" Top Menu items). One real
InstalledDevice entity backing both capabilities.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static /devices/dashboard, /devices/starter-interrupt/
dashboard, /devices paths registered before the dynamic /devices/{device_id}/*
paths, same route-shadowing-avoidance precedent as elsewhere in this codebase.

core/device_management_api.py's own module docstring covers the ACL
reasoning: ADMIN/OPERATIONS/FINANCE for both viewing and mutating -- this is
sensitive loan-collateral-tracking data, not broad department-visible
reporting.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.device_management_api import (
    register_device_api,
    remove_device_api,
    list_devices_api,
    get_simulated_location_api,
    get_location_history_api,
    arm_starter_interrupt_api,
    send_warning_api,
    disable_starter_api,
    enable_starter_api,
    get_device_detail_api,
    get_device_management_dashboard_api,
    get_starter_interrupt_dashboard_api,
)


router = APIRouter()


class RegisterDeviceRequest(BaseModel):

    loan_id: str
    device_type: str
    serial_number: str
    install_date: str | None = None


class RemoveDeviceRequest(BaseModel):

    reason: str = ""


class SendDeviceWarningRequest(BaseModel):

    message: str = ""


class StarterCommandRequest(BaseModel):

    reason: str = ""


@router.get("/devices/dashboard")
def devices_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_device_management_dashboard_api(payload["role"])


@router.get("/devices/starter-interrupt/dashboard")
def devices_starter_interrupt_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_starter_interrupt_dashboard_api(payload["role"])


@router.get("/devices")
def devices_list(status: str | None = None, loan_id: str | None = None, device_type: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_devices_api(payload["role"], status=status, loan_id=loan_id, device_type=device_type)


@router.post("/devices")
def devices_register(body: RegisterDeviceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return register_device_api(payload["role"], payload["employee_id"], body.loan_id, body.device_type, body.serial_number, install_date=body.install_date)


@router.get("/devices/{device_id}")
def devices_get_detail(device_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_device_detail_api(payload["role"], device_id)


@router.post("/devices/{device_id}/remove")
def devices_remove(device_id: str, body: RemoveDeviceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_device_api(payload["role"], payload["employee_id"], device_id, reason=body.reason)


@router.get("/devices/{device_id}/location")
def devices_location(device_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_simulated_location_api(payload["role"], device_id)


@router.get("/devices/{device_id}/location-history")
def devices_location_history(device_id: str, days: int = 7, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_location_history_api(payload["role"], device_id, days=days)


@router.post("/devices/{device_id}/arm")
def devices_arm(device_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return arm_starter_interrupt_api(payload["role"], payload["employee_id"], device_id)


@router.post("/devices/{device_id}/warning")
def devices_send_warning(device_id: str, body: SendDeviceWarningRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_warning_api(payload["role"], payload["employee_id"], device_id, message=body.message)


@router.post("/devices/{device_id}/disable")
def devices_disable(device_id: str, body: StarterCommandRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return disable_starter_api(payload["role"], payload["employee_id"], device_id, reason=body.reason)


@router.post("/devices/{device_id}/enable")
def devices_enable(device_id: str, body: StarterCommandRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return enable_starter_api(payload["role"], payload["employee_id"], device_id, reason=body.reason)
