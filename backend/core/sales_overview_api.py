"""
Thin ACL layer for core/sales_overview.py, same "no service layer indirection"
convention as every other `*_api.py` module. Role rule matches sales_menu.py's own
dashboard access: ADMIN/OPERATIONS/SALES.
"""

from core.sales_overview import get_my_day
from core.permissions import ADMIN, OPERATIONS, SALES

_OVERVIEW_ROLES = (ADMIN, OPERATIONS, SALES)


def get_my_day_api(role, employee_id):

    if role not in _OVERVIEW_ROLES:
        return {"error": "You don't have access to the Sales Overview"}

    if not employee_id:
        return {"error": "employee_id is required"}

    return get_my_day(role, employee_id)
