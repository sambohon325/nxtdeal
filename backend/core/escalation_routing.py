"""Rewritten 2026-07-13 to use core/lead_assignment.py's graph-backed
get_assigned_employee_ids() instead of the old flat `assignments` dict — see CLAUDE.md's
"one graph" note."""

from core.lead_assignment import (
    assign_lead,
    get_assigned_employee_ids
)

from core.lead_routing import (
    get_active_workload
)


def reassign_escalated_lead(
    lead_id
):

    employees = get_assigned_employee_ids()

    if not employees:

        raise ValueError(
            "No employees available"
        )

    workloads = {}

    for employee_id in employees:

        workloads[
            employee_id
        ] = get_active_workload(
            employee_id
        )

    employee_id = min(
        workloads,
        key=workloads.get
    )

    assign_lead(
        lead_id,
        employee_id
    )

    return {
        "lead_id": lead_id,
        "assigned_to": employee_id,
        "status": "REASSIGNED"
    }
