"""
Thin API-layer wrapper around core/lead_workflows.py's advance_lead_workflow() (2026-07-15,
session 79). advance_lead_workflow() has existed since the "One Graph Unification"
session (17) -- Lead pipeline state has lived as real attributes on the Lead entity
itself, validated against the real core/workflows.py LEAD_WORKFLOW state machine, this
whole time -- but it had zero live callers anywhere in this codebase until now (grep-
confirmed before writing this file): nothing ever exposed a route to actually move a
lead through its pipeline. The CRM Pipeline kanban board (Marketing's new "CRM" Top
Menu item, core/marketing_menu.py's crm()) is the first real UI to expose this, via
drag-and-drop between real pipeline-state columns.

Role rule: any authenticated role can advance a lead -- Sales, Marketing, and
Operations all legitimately touch lead status day to day (matching the existing
LEAD entity-read ACL in core/permissions.py, which already grants ADMIN/OPERATIONS/
SALES/MARKETING read access), so this isn't gated any narrower than that.
"""

from core.lead_workflows import create_lead_workflow, advance_lead_workflow
from core.pipeline_state import get_pipeline_state
from core.workflows import LEAD_WORKFLOW, get_next_states
from core.dealeros import ledger
from core.entity_types import LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING


_PIPELINE_ROLES = {ADMIN, OPERATIONS, SALES, MARKETING}


def list_pipeline_states_api():
    """The real, ordered LEAD_WORKFLOW state list -- the CRM Pipeline board's column
    set, straight from core/workflows.py rather than a duplicated constant."""

    return list(LEAD_WORKFLOW.keys())


def advance_lead_pipeline_api(role, employee_id, lead_id, next_state):

    if role not in _PIPELINE_ROLES:
        return {"error": "You don't have access to move leads through the pipeline"}

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {"error": "Lead not found"}

    current_state = get_pipeline_state(lead_id)

    if current_state is None:
        current_state = create_lead_workflow(lead_id)

    if next_state == current_state:
        return {"lead_id": lead_id, "previous_state": current_state, "state": current_state}

    try:
        new_state = advance_lead_workflow(lead_id, next_state)
    except ValueError as exc:
        return {
            "error": str(exc),
            "current_state": current_state,
            "valid_next_states": get_next_states(current_state),
        }

    return {"lead_id": lead_id, "previous_state": current_state, "state": new_state}
