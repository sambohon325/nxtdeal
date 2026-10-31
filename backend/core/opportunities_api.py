"""
Thin ACL layer for core/opportunities_actions.py (session 82), imported directly into
api/app.py's route handlers.

Role rule: any authenticated role can list the Sales roster (read-only, names/titles
only). Saving a pool as a List or assigning a Lead to a salesperson is scoped to
MARKETING/ADMIN, matching core/campaigns_api.py's "who can activate a campaign" split
-- turning a computed opportunity into a real, actionable list or a real handoff is a
marketing decision, not something every role should be able to trigger.
"""

from core.opportunities_actions import (
    list_sales_employees,
    save_opportunity_pool_as_list,
    assign_opportunity_to_sales,
)
from core.permissions import ADMIN, MARKETING


def _can_act(role):
    return role == ADMIN or role == MARKETING


def list_sales_employees_api():
    return list_sales_employees()


def save_opportunity_pool_as_list_api(role, employee_id, name, campaign_type_key, params, description=""):

    if not _can_act(role):
        return {"error": "Only marketing/admin can save an opportunity pool as a list"}

    if not (name or "").strip():
        return {"error": "A list needs a name."}

    return save_opportunity_pool_as_list(name.strip(), employee_id, campaign_type_key, params or {}, description or "")


def assign_opportunity_to_sales_api(role, lead_id, assign_to_employee_id):

    if not _can_act(role):
        return {"error": "Only marketing/admin can assign an opportunity to sales"}

    return assign_opportunity_to_sales(lead_id, assign_to_employee_id)
