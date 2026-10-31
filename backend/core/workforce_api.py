"""Thin ACL layer for core/workforce.py's Workforce Management module.

Viewing (directory/shifts/time-off list/coverage) is broad -- every department
legitimately wants to know who's scheduled and who's out, same precedent every
other cross-department Operations module in this codebase (Business Health,
Enterprise Risk Center, the Unified Communications Hub) already established.
Scheduling/cancelling/completing a shift is ADMIN/OPERATIONS-only, matching
Vehicle Lifecycle's/Inventory Aging's own narrower mutate set for dispatch-
style actions. Submitting a time-off request is broad (any real role can log
one on an employee's behalf, same convention core/lead_tasks.py/
core/field_notes.py already use). Approving/denying one is real-tier-gated
INSIDE core/workforce.py itself (the deciding employee's own Title must
resolve to manager-or-above via infer_tier) -- this layer only adds the
coarser ADMIN/OPERATIONS role check on top, matching core/manager_to_api.py's
own two-layer (role + tier) precedent.
"""

from core.workforce import (
    get_directory,
    schedule_shift,
    complete_shift,
    mark_no_show,
    cancel_shift,
    list_shifts,
    request_time_off,
    approve_time_off,
    deny_time_off,
    cancel_time_off,
    list_time_off,
    get_coverage_for_date,
    get_workforce_performance,
    get_workforce_overview,
    _shift_brief,
    _time_off_brief,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")
MUTATE_ROLES = ("ADMIN", "OPERATIONS")

_VIEW_DENIED = {"error": "You don't have access to Workforce data with your current role."}
_MUTATE_DENIED = {"error": "Scheduling/cancelling a shift requires Admin or Operations."}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _serialize_shift(result):
    if _is_error(result):
        return result
    return _shift_brief(result)


def _serialize_time_off(result):
    if _is_error(result):
        return result
    return _time_off_brief(result)


def get_workforce_overview_api(role):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return get_workforce_overview(role)


def get_directory_api(role, department=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return get_directory(department=department)


def get_coverage_api(role, on_date=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return get_coverage_for_date(on_date)


def get_performance_api(role):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return get_workforce_performance(role)


def list_shifts_api(role, employee_id=None, department=None, date_from=None, date_to=None, status=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    shifts = list_shifts(employee_id=employee_id, department=department, date_from=date_from, date_to=date_to, status=status)
    return {"shifts": [_shift_brief(s) for s in shifts]}


def schedule_shift_api(role, employee_id, shift_date, start_time, end_time, department, created_by, notes=""):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_shift(schedule_shift(employee_id, shift_date, start_time, end_time, department, created_by, notes))


def complete_shift_api(role, shift_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_shift(complete_shift(shift_id, by))


def mark_no_show_api(role, shift_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_shift(mark_no_show(shift_id, by))


def cancel_shift_api(role, shift_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_shift(cancel_shift(shift_id, by))


def list_time_off_api(role, employee_id=None, status=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    requests = list_time_off(employee_id=employee_id, status=status)
    return {"requests": [_time_off_brief(r) for r in requests]}


def request_time_off_api(role, employee_id, start_date, end_date, reason, created_by=None):
    if role not in VIEW_ROLES:
        return _VIEW_DENIED
    return _serialize_time_off(request_time_off(employee_id, start_date, end_date, reason, created_by))


def approve_time_off_api(role, request_id, decided_by, note=None):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_time_off(approve_time_off(request_id, decided_by, note))


def deny_time_off_api(role, request_id, decided_by, note=None):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_time_off(deny_time_off(request_id, decided_by, note))


def cancel_time_off_api(role, request_id, by):
    if role not in MUTATE_ROLES:
        return _MUTATE_DENIED
    return _serialize_time_off(cancel_time_off(request_id, by))
