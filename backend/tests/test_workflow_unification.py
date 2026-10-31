"""
End-to-end coverage for the 2026-07-13 "one graph" unification (see CLAUDE.md): lead
assignment (core/lead_assignment.py) and pipeline state (core/pipeline_state.py) both now
live on storage/graph.json instead of the separate storage/assignments.json /
storage/workflows.json stores that used to back the Workflow Engine. This exercises the
whole chain — create a lead, auto-assign it, advance its pipeline state, and check that
every dashboard built on top (workload, leaderboard, manager, escalation, pipeline
metrics) reflects it, all from the same ledger. Monkeypatches disk writes so this doesn't
touch real files. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD
from core.audit import audit_log

from core import lead_assignment
from core import lead_workflows

from core.lead_workflows import create_lead_workflow, advance_lead_workflow
from core.lead_routing import auto_assign_lead
from core.workload_dashboard import get_workload_dashboard
from core.leaderboard import get_sales_leaderboard
from core.manager_dashboard import get_manager_dashboard
from core.escalation_dashboard import get_escalation_dashboard
from core.pipeline_analytics import get_pipeline_metrics


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):

    ledger.reset()
    audit_log.reset()

    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_workflows, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_workflows, "save_audit_log", lambda filepath: None)

    yield

    ledger.reset()
    audit_log.reset()


def _add_lead(entity_id):

    ledger.add_entity(
        Entity(id=entity_id, entity_type=LEAD, attributes={})
    )


def test_full_lead_lifecycle_reflected_across_dashboards():

    # auto_assign_lead() only picks among employees who already have at least one
    # ASSIGNED_TO relationship (matches the old dict-based system's exact bootstrap
    # requirement — see core/lead_routing.py's docstring-equivalent note in CLAUDE.md).
    # Seed the pool with a throwaway assignment before exercising auto-assignment.
    _add_lead("LEAD-SEED")
    create_lead_workflow("LEAD-SEED")
    advance_lead_workflow("LEAD-SEED", "CONTACTED")
    advance_lead_workflow("LEAD-SEED", "LOST")
    lead_assignment.assign_lead("LEAD-SEED", "EMP-1")
    lead_assignment.assign_lead("LEAD-SEED-2", "EMP-2")

    _add_lead("LEAD-1")
    _add_lead("LEAD-2")

    create_lead_workflow("LEAD-1")
    create_lead_workflow("LEAD-2")

    employee_1 = auto_assign_lead("LEAD-1")
    employee_2 = auto_assign_lead("LEAD-2")

    assert employee_1 in {"EMP-1", "EMP-2"}
    assert employee_2 in {"EMP-1", "EMP-2"}

    advance_lead_workflow("LEAD-1", "CONTACTED")
    advance_lead_workflow("LEAD-1", "APPOINTMENT_SET")

    # Audit log recorded the transitions (this is now the durable history, replacing the
    # old WorkflowInstance.history list).
    events = audit_log.get_for_entity("LEAD-1")
    event_types = [event.event_type for event in events]
    assert event_types == [
        "workflow_created",
        "workflow_transition",
        "workflow_transition",
    ]

    workload = {row["employee_id"]: row["active_workload"] for row in get_workload_dashboard()}
    assert workload[employee_1] >= 1

    # Every employee_id shown on the leaderboard/manager dashboards must trace back to a
    # real ASSIGNED_TO relationship on the graph — no separate assignments store to drift
    # out of sync with.
    leaderboard_ids = {row["employee_id"] for row in get_sales_leaderboard()}
    manager_ids = {row["employee_id"] for row in get_manager_dashboard()}
    assert leaderboard_ids == manager_ids
    assert leaderboard_ids.issubset({employee_1, employee_2})
    assert leaderboard_ids


def test_escalated_lead_shows_up_on_escalation_dashboard():

    _add_lead("LEAD-STUCK")

    create_lead_workflow("LEAD-STUCK")
    advance_lead_workflow("LEAD-STUCK", "CONTACTED")

    # Back-date PipelineStateSince so the lead reads as stuck for 30 days.
    entity = ledger.get_entity("LEAD-STUCK")
    entity.attributes["PipelineStateSince"] = "2020-01-01T00:00:00"

    escalated = get_escalation_dashboard()

    assert any(row["lead_id"] == "LEAD-STUCK" for row in escalated)


def test_pipeline_metrics_aggregate_from_the_graph():

    _add_lead("LEAD-A")
    _add_lead("LEAD-B")
    _add_lead("LEAD-C")

    create_lead_workflow("LEAD-A")
    create_lead_workflow("LEAD-B")
    create_lead_workflow("LEAD-C")

    advance_lead_workflow("LEAD-B", "CONTACTED")
    advance_lead_workflow("LEAD-B", "APPOINTMENT_SET")
    advance_lead_workflow("LEAD-B", "VISITED")
    advance_lead_workflow("LEAD-B", "PROPOSAL")
    advance_lead_workflow("LEAD-B", "NEGOTIATION")
    advance_lead_workflow("LEAD-B", "SOLD")

    advance_lead_workflow("LEAD-C", "CONTACTED")
    advance_lead_workflow("LEAD-C", "LOST")

    metrics = get_pipeline_metrics()

    assert metrics["pipeline"]["NEW"] == 1
    assert metrics["pipeline"]["SOLD"] == 1
    assert metrics["pipeline"]["LOST"] == 1
    assert metrics["closed_leads"] == 2
    assert metrics["active_leads"] == 1
    assert metrics["conversion_rate"] == pytest.approx(100 / 3, rel=0.01)


def test_advance_without_create_raises():

    _add_lead("LEAD-NEVER-STARTED")

    with pytest.raises(ValueError):
        advance_lead_workflow("LEAD-NEVER-STARTED", "CONTACTED")


def test_auto_assign_with_no_employees_raises():

    _add_lead("LEAD-ORPHAN")

    with pytest.raises(ValueError):
        auto_assign_lead("LEAD-ORPHAN")
