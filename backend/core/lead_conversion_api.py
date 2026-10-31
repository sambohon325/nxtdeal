"""Thin ACL layer for core/lead_conversion.py. Same role set as lead_tasks_api.py --
converting a lead is a normal sales action, not a financial one (funding a deal is
where the narrower F&I gate applies, unchanged in core/deals_api.py)."""

from core.lead_conversion import convert_lead_to_customer
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING

_CONVERT_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)


def convert_lead_to_customer_api(role, employee_id, lead_id):

    if role not in _CONVERT_ROLES:
        return {"error": "You don't have access to convert this lead"}

    result = convert_lead_to_customer(lead_id, employee_id)

    if isinstance(result, dict):
        return result

    return {"id": result.id, **result.attributes}
