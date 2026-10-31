"""
Thin ACL layer for core/lead_assignment.py's manual transfer path (Sales Overview /
Prospects "Transfer Lead" Action Center button, session 94 follow-up). Distinct from
the existing `POST /lead/assign/{lead_id}` route, which calls a different function
(`assign_new_lead` -- auto/round-robin assignment, core/routing.py) -- this wraps the
real, previously-unrouted `assign_lead(lead_id, employee_id)` for an explicit,
salesperson-or-manager-initiated hand-off to a specific employee.

Also fixes a real drift risk flagged during Prospects (session 93): Lead's own
`AssignedSalesperson` attribute (read by sales_menu.py's `needing_assignment` bucket
and displayed on the Lead Record) and the graph-native ASSIGNED_TO relationship
(documented as authoritative, CLAUDE.md's "One Graph Unification" note) could
silently disagree, since `assign_lead()` only ever wrote the relationship. Transfers
made through this function now update both -- the relationship stays the real source
of truth, the attribute is kept as an honest mirror of it rather than a stale copy.
"""

from core.dealeros import ledger
from core.entity_types import LEAD
from core.lead_assignment import assign_lead
from core.permissions import ADMIN, OPERATIONS, SALES
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

_TRANSFER_ROLES = (ADMIN, OPERATIONS, SALES)

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# assign_lead() (core/lead_assignment.py) already saves internally, but that save runs
# BEFORE this function's own subsequent `lead.attributes["AssignedSalesperson"] = ...`
# mutation -- meaning the "keep the attribute mirror in sync with the relationship"
# fix this module's own docstring describes was itself silently losing that second
# write on every restart. Fixed below with an explicit second save after the
# attribute update.


def transfer_lead_api(role, employee_id, lead_id, new_employee_id):

    if role not in _TRANSFER_ROLES:
        return {"error": "You don't have access to transfer leads"}

    lead = ledger.get_entity(lead_id)
    if not lead or lead.entity_type != LEAD:
        return {"error": f"Lead '{lead_id}' not found"}

    new_employee = ledger.get_entity(new_employee_id)
    if not new_employee or new_employee.entity_type != "Employee":
        return {"error": f"Employee '{new_employee_id}' not found"}

    assign_lead(lead_id, new_employee_id)

    lead.attributes["AssignedSalesperson"] = new_employee_id

    save_graph(GRAPH_PATH)

    return {
        "lead_id": lead_id,
        "transferred_from": employee_id,
        "transferred_to": new_employee_id,
    }


def list_sales_employees_api(role):
    """A plain Sales-department roster for the "Transfer Lead" picker -- Employee has
    no ENTITY_ACCESS entry (core/security.py defaults non-admin roles to denied for
    unlisted entity types), so the generic role-filtered search can't be reused here
    for a non-ADMIN caller. Deliberately narrow (id/name/title only, no PII beyond
    name) rather than exposing the full Employee record to every Sales-role caller."""

    if role not in _TRANSFER_ROLES:
        return {"error": "You don't have access to the employee roster"}

    employees = [
        e for e in ledger.get_all().values()
        if e.entity_type == "Employee"
        and (e.attributes.get("Department") or "").strip().lower() == "sales"
    ]

    return [
        {
            "id": e.id,
            "name": f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip(),
            "title": e.attributes.get("Title"),
        }
        for e in employees
    ]
