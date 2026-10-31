"""
core/employee_value_api.py — ACL layer for employee $ value/effectiveness (session
37). ADMIN/OPERATIONS only, per Sam's explicit scoping answer -- this is
compensation-adjacent data, gated one tier tighter than the leaderboard/workload
dashboards a SALES manager can already see.
"""

from core.permissions import ADMIN, OPERATIONS

from core.employee_value import (
    compute_employee_value,
    list_employee_values,
    EFFECTIVENESS_DISCLAIMER,
)

VALUE_ROLES = (ADMIN, OPERATIONS)

_FORBIDDEN = {
    "error": "You don't have access to employee value data with your current role -- "
    "Admin or Operations can view this."
}


def list_employee_values_api(role, department=None):

    if role not in VALUE_ROLES:
        return _FORBIDDEN

    return {
        "employees": list_employee_values(department),
        "disclaimer": EFFECTIVENESS_DISCLAIMER,
    }


def get_employee_value_api(role, employee_id):

    if role not in VALUE_ROLES:
        return _FORBIDDEN

    value = compute_employee_value(employee_id)

    if not value:
        return {"error": f"Employee '{employee_id}' not found"}

    return value
