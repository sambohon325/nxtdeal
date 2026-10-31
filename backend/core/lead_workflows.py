"""
Lead pipeline state transitions. Rewritten 2026-07-13 to write directly onto the graph via
core/pipeline_state.py instead of a separate WorkflowInstance kept in workflow_repository
(and persisted to storage/workflows.json) — see CLAUDE.md's "one graph" note. The state
machine rules themselves (core/workflows.py's LEAD_WORKFLOW/can_transition) are unchanged;
only where the current state lives has changed.

create_lead_workflow()/advance_lead_workflow() keep their original names, arguments, and
audit-logging behavior — callers (core/lead_lifecycle.py, core/escalation_routing.py,
api/app.py, tests) don't need to change. The one visible difference: they now return the
state string instead of a WorkflowInstance object (nothing outside the old loose test
scripts relied on the object's .history/.entity_id — updated alongside this).
"""

from core.pipeline_state import (
    start_pipeline,
    set_pipeline_state,
    get_pipeline_state
)

from core.workflows import can_transition

from core.storage import save_graph

from core.audit import audit_log

from core.audit_storage import save_audit_log

from core.storage_paths import GRAPH_PATH, AUDIT_PATH


def create_lead_workflow(lead_id):

    state = start_pipeline(
        lead_id,
        initial_state="NEW"
    )

    save_graph(
        GRAPH_PATH
    )

    audit_log.record(
        event_type="workflow_created",
        summary=f"Lead workflow created for {lead_id} at NEW",
        entity_id=lead_id,
        actor="workflow_engine",
        details={"workflow_name": "Lead Workflow", "state": "NEW"}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return state


def advance_lead_workflow(lead_id, next_state):

    previous_state = get_pipeline_state(lead_id)

    if previous_state is None:

        raise ValueError(
            f"No workflow found for {lead_id}"
        )

    if not can_transition(previous_state, next_state):

        raise ValueError(
            f"Invalid transition: {previous_state} -> {next_state}"
        )

    state = set_pipeline_state(
        lead_id,
        next_state
    )

    save_graph(
        GRAPH_PATH
    )

    audit_log.record(
        event_type="workflow_transition",
        summary=f"Lead {lead_id} moved {previous_state} -> {next_state}",
        entity_id=lead_id,
        actor="workflow_engine",
        details={"from": previous_state, "to": next_state}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return state
