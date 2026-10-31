"""Workforce router -- Directory, Shift Scheduling, Time-Off Requests, and
Workforce Performance (Operations' "Workforce" Top Menu item).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,500+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. api/app.py now just does `app.include_router(router)`
for this module instead of defining these 14 routes inline.

core/workforce_api.py's own module docstring covers the ACL reasoning:
viewing is broad (every real department), scheduling/completing/no-showing/
cancelling a shift is ADMIN/OPERATIONS-only, submitting a time-off request is
broad, and approving/denying is real-tier-gated (manager/executive) inside
core/workforce.py itself.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.workforce_api import (
    get_workforce_overview_api,
    get_directory_api,
    get_coverage_api,
    get_performance_api,
    list_shifts_api,
    schedule_shift_api,
    complete_shift_api,
    mark_no_show_api,
    cancel_shift_api,
    list_time_off_api,
    request_time_off_api,
    approve_time_off_api,
    deny_time_off_api,
    cancel_time_off_api,
)


router = APIRouter()


class ScheduleShiftRequest(BaseModel):

    employee_id: str
    shift_date: str
    start_time: str
    end_time: str
    department: str = None
    notes: str = ""


class RequestTimeOffRequest(BaseModel):

    employee_id: str
    start_date: str
    end_date: str
    reason: str = ""


class DecideTimeOffRequest(BaseModel):

    note: str = None


@router.get("/workforce/overview")
def workforce_overview(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_workforce_overview_api(payload["role"])


@router.get("/workforce/directory")
def workforce_directory(department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_directory_api(payload["role"], department=department)


@router.get("/workforce/coverage")
def workforce_coverage(on_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_coverage_api(payload["role"], on_date=on_date)


@router.get("/workforce/performance")
def workforce_performance(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_performance_api(payload["role"])


@router.get("/workforce/shifts")
def workforce_shifts_list(
    employee_id: str = None,
    department: str = None,
    date_from: str = None,
    date_to: str = None,
    status: str = None,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_shifts_api(
        payload["role"],
        employee_id=employee_id,
        department=department,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )


@router.post("/workforce/shifts")
def workforce_schedule_shift(request: ScheduleShiftRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return schedule_shift_api(
        payload["role"],
        request.employee_id,
        request.shift_date,
        request.start_time,
        request.end_time,
        request.department,
        payload["employee_id"],
        notes=request.notes,
    )


@router.post("/workforce/shifts/{shift_id}/complete")
def workforce_complete_shift(shift_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_shift_api(payload["role"], shift_id, payload["employee_id"])


@router.post("/workforce/shifts/{shift_id}/no-show")
def workforce_no_show_shift(shift_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_no_show_api(payload["role"], shift_id, payload["employee_id"])


@router.post("/workforce/shifts/{shift_id}/cancel")
def workforce_cancel_shift(shift_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_shift_api(payload["role"], shift_id, payload["employee_id"])


@router.get("/workforce/time-off")
def workforce_time_off_list(employee_id: str = None, status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_time_off_api(payload["role"], employee_id=employee_id, status=status)


@router.post("/workforce/time-off")
def workforce_request_time_off(request: RequestTimeOffRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_time_off_api(
        payload["role"],
        request.employee_id,
        request.start_date,
        request.end_date,
        request.reason,
        created_by=payload["employee_id"],
    )


@router.post("/workforce/time-off/{request_id}/approve")
def workforce_approve_time_off(request_id: str, request: DecideTimeOffRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_time_off_api(payload["role"], request_id, payload["employee_id"], note=request.note)


@router.post("/workforce/time-off/{request_id}/deny")
def workforce_deny_time_off(request_id: str, request: DecideTimeOffRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return deny_time_off_api(payload["role"], request_id, payload["employee_id"], note=request.note)


@router.post("/workforce/time-off/{request_id}/cancel")
def workforce_cancel_time_off(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_time_off_api(payload["role"], request_id, payload["employee_id"])
