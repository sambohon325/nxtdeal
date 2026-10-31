"""
Thin ACL layer for core/service_overview.py, same "no service layer
indirection" convention as every other `*_api.py` module, and the same
shape as core/sales_overview_api.py. Role rule matches service_menu.py's
own dashboard access: ADMIN/OPERATIONS/SERVICE.
"""

from core.service_overview import get_service_my_day
from core.permissions import ADMIN, OPERATIONS, SERVICE

_OVERVIEW_ROLES = (ADMIN, OPERATIONS, SERVICE)


def get_service_my_day_api(role, employee_id):

    if role not in _OVERVIEW_ROLES:
        return {"error": "You don't have access to the Service Overview"}

    if not employee_id:
        return {"error": "employee_id is required"}

    return get_service_my_day(role, employee_id)
