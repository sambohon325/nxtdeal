"""
Employee <-> lead assignment, stored as ASSIGNED_TO relationships on the graph — replaces
the old flat `assignments = {lead_id: employee_id}` dict (previously persisted separately
to storage/assignments.json). See CLAUDE.md's "one graph" note (2026-07-13).

core/queries.py's get_employee_360() already reads ASSIGNED_TO relationships this same
way, so this was already the graph's native representation for assignment — the flat dict
was a parallel, disconnected copy of the same fact.

Relationships are append-only (core/ledger.py has no remove_relationship), so "current
assignment" is defined as the *last* ASSIGNED_TO relationship targeting a given lead, in
insertion order — i.e. reassigning a lead adds a new relationship rather than mutating one,
and readers always take the most recent. This preserves the old dict's overwrite-on-
reassign semantics without needing a schema change.
"""

from core.dealeros import ledger
from core.relationships import Relationship
from core.relationship_types import ASSIGNED_TO
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def assign_lead(lead_id, employee_id):

    ledger.add_relationship(
        Relationship(
            source_id=employee_id,
            target_id=lead_id,
            relationship_type=ASSIGNED_TO
        )
    )

    save_graph(GRAPH_PATH)

    return employee_id


def get_assigned_employee(lead_id):

    employee_id = None

    for relationship in ledger.get_relationships():

        if (
            relationship.relationship_type == ASSIGNED_TO
            and relationship.target_id == lead_id
        ):
            employee_id = relationship.source_id

    return employee_id


def get_employee_leads(employee_id):
    """All leads currently assigned to this employee (i.e. their most recent ASSIGNED_TO
    relationship points back to them — excludes leads that were reassigned away)."""

    seen = []

    for relationship in ledger.get_relationships():

        if (
            relationship.relationship_type == ASSIGNED_TO
            and relationship.source_id == employee_id
            and relationship.target_id not in seen
        ):
            seen.append(relationship.target_id)

    return [
        lead_id for lead_id in seen
        if get_assigned_employee(lead_id) == employee_id
    ]


def get_assigned_employee_ids():
    """Every employee_id with at least one lead currently assigned to them — replaces the
    old `set(assignments.values())` pattern used throughout the workload/leaderboard/
    manager dashboards."""

    lead_ids = set()

    for relationship in ledger.get_relationships():

        if relationship.relationship_type == ASSIGNED_TO:
            lead_ids.add(relationship.target_id)

    employee_ids = set()

    for lead_id in lead_ids:

        employee_id = get_assigned_employee(lead_id)

        if employee_id:
            employee_ids.add(employee_id)

    return employee_ids
