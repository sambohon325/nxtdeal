"""
Opportunities workflow actions (session 82) -- Sam: "in opportunities... each module
needs to be a workable process, not just an information dash. We have to include how
someone would create this in the first place, and how it would flow not only through
the marketing department, but what parts would be accessible to sales."

core/marketing_menu.py's _opportunities() was read-only: real counts/samples, no
action. This gives the CRM's Opportunities tab two real actions that close the actual
Marketing -> Sales loop instead of just describing it:

1. save_opportunity_pool_as_list() -- turns a pool into a real, curatable
   core/marketing_lists.py MarketingList (reuses build_audience() server-side so the
   full matching set is captured, not just the on-screen 5-item sample).
2. assign_opportunity_to_sales() -- for Lead-typed opportunities only (the
   inventory_ads/Conquest pool -- the only opportunity pool whose members are Leads,
   not Customers, per core/campaigns.py's audience_entity_type()), hands the Lead to
   a real salesperson via the exact same core/lead_assignment.py ASSIGNED_TO
   mechanism the Sales pipeline already uses, not a parallel handoff model.
   Customer-typed pools (retention/finance_renewal/equity) have no lead-assignment
   concept in this data model -- "Save as List" is the real, honest handoff mechanism
   for those, since Lists are broadly readable including by SALES (see
   core/permissions.py's ENTITY_ACCESS[MARKETING_LIST]).
"""

from core.dealeros import ledger
from core.entity_types import EMPLOYEE, LEAD
from core.campaigns import get_campaign_type
from core.marketing_lists import build_list_from_pool
from core.lead_assignment import assign_lead


def list_sales_employees():
    """Real Sales-department Employee roster for the "Assign to Sales" picker -- same
    Employee.Department string-match convention core/employee_value.py's
    _department_of() already established. Names/titles only (no compensation/
    performance data), same low-sensitivity bar as an org chart -- open to any role
    unlike core/employee_value_api.py's ADMIN/OPERATIONS-gated $ data."""

    employees = []

    for e in ledger.get_all().values():

        if e.entity_type != EMPLOYEE:
            continue

        if (e.attributes.get("Department") or "").strip().lower() != "sales":
            continue

        name = f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip()

        employees.append({
            "id": e.id,
            "name": name or e.id,
            "title": e.attributes.get("Title"),
        })

    employees.sort(key=lambda e: e["name"])

    return employees


def save_opportunity_pool_as_list(name, created_by, campaign_type_key, params, description=""):

    if not get_campaign_type(campaign_type_key):
        return {"error": f"Unknown campaign type '{campaign_type_key}'"}

    entity = build_list_from_pool(name, created_by, campaign_type_key, params or {}, description)

    return {"id": entity.id, **entity.attributes}


def assign_opportunity_to_sales(lead_id, employee_id):

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {
            "error": (
                f"'{lead_id}' is not a Lead -- only Lead-typed opportunities (the "
                "Conquest pool) can be assigned to a salesperson. Customer-typed "
                "opportunities have no lead-assignment concept in this data model -- "
                "use 'Save as List' instead."
            )
        }

    employee = ledger.get_entity(employee_id)

    if (
        not employee
        or employee.entity_type != EMPLOYEE
        or (employee.attributes.get("Department") or "").strip().lower() != "sales"
    ):
        return {"error": f"'{employee_id}' is not a Sales-department employee."}

    assign_lead(lead_id, employee_id)

    return {"lead_id": lead_id, "assigned_to": employee_id}
