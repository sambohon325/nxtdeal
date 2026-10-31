"""
Least-busy-employee auto-assignment. Rewritten 2026-07-13 to read assignment/pipeline
state from the graph (core/lead_assignment.py + core/pipeline_state.py) instead of the old
`assignments` dict + workflow_repository — see CLAUDE.md's "one graph" note.
"""

from core.lead_assignment import (
    assign_lead,
    get_employee_leads,
    get_assigned_employee_ids
)

from core.pipeline_state import get_pipeline_state


def get_active_workload(employee_id):

    workload = 0

    for lead_id in get_employee_leads(employee_id):

        state = get_pipeline_state(lead_id)

        if state is None:

            continue

        if state not in ["SOLD", "LOST"]:

            workload += 1

    return workload


def auto_assign_lead(lead_id):

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

    return employee_id
