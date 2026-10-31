"""
Tests for core/manager_dashboard.py -- get_manager_dashboard(), a trivial
2-call composition: every distinct assigned-to employee id
(core.lead_assignment.get_assigned_employee_ids()) mapped through
core.manager_analytics.get_employee_metrics(). Added per BUILD_QUEUE.md's
standing "convert to a real pytest suite as each module gets touched" rule
(CAF-00123 missing_test_coverage work) -- closes out the
manager_dashboard -> manager_analytics -> lead_aging/employee_performance
dependency chain.

No save_graph stubbing needed -- same precedent tests/test_pipeline_state.py/
tests/test_lead_aging.py/tests/test_employee_performance.py/
tests/test_manager_analytics.py already establish, relying on conftest.py's
isolated tempdir DEALEROS_STORAGE_DIR.
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
from core.entity_types import LEAD, EMPLOYEE

from core.pipeline_state import start_pipeline
from core.lead_assignment import assign_lead
from core.manager_dashboard import get_manager_dashboard


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _add_lead(entity_id, state=None):
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes={}))
    if state:
        start_pipeline(entity_id, initial_state=state)


def _add_employee(entity_id):
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes={}))
    return entity_id


class TestGetManagerDashboard:
    def test_no_assignments_returns_empty_list(self):
        assert get_manager_dashboard() == []

    def test_one_employee_with_leads_returns_one_real_metrics_dict(self):
        _add_employee("EMP-1")
        _add_lead("LEAD-1", state="SOLD")
        _add_lead("LEAD-2", state="CONTACTED")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-1")

        result = get_manager_dashboard()

        assert len(result) == 1
        assert result[0]["employee_id"] == "EMP-1"
        assert result[0]["assigned_leads"] == 2
        assert result[0]["closed_leads"] == 1
        assert result[0]["active_leads"] == 1
        assert result[0]["conversion_rate"] == 50.0

    def test_multiple_employees_each_get_their_own_real_entry(self):
        _add_employee("EMP-1")
        _add_employee("EMP-2")
        _add_lead("LEAD-1", state="SOLD")
        _add_lead("LEAD-2", state="LOST")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-2", "EMP-2")

        result = get_manager_dashboard()

        by_id = {row["employee_id"]: row for row in result}
        assert set(by_id.keys()) == {"EMP-1", "EMP-2"}
        assert by_id["EMP-1"]["conversion_rate"] == 100.0
        assert by_id["EMP-2"]["conversion_rate"] == 0.0

    def test_only_employees_with_a_current_assignment_are_included(self):
        # get_assigned_employee_ids() is derived from ASSIGNED_TO relationships --
        # an employee entity that was never assigned a lead has no entry at all,
        # confirming this dashboard doesn't walk the full employee roster.
        _add_employee("EMP-1")
        _add_employee("EMP-2")  # never assigned anything
        _add_lead("LEAD-1", state="NEW")
        assign_lead("LEAD-1", "EMP-1")

        result = get_manager_dashboard()

        employee_ids = {row["employee_id"] for row in result}
        assert employee_ids == {"EMP-1"}

    def test_reassignment_drops_the_old_owner_from_the_dashboard_entirely(self):
        # get_assigned_employee_ids() only includes an employee whose CURRENT
        # (most-recent) ASSIGNED_TO relationship still points back to them --
        # once LEAD-1 is reassigned away from EMP-1, EMP-1 has zero currently-
        # assigned leads and drops out of the id set (and this dashboard)
        # entirely, rather than showing up with a zeroed-out entry.
        _add_employee("EMP-1")
        _add_employee("EMP-2")
        _add_lead("LEAD-1", state="NEW")
        assign_lead("LEAD-1", "EMP-1")
        assign_lead("LEAD-1", "EMP-2")

        result = get_manager_dashboard()

        employee_ids = {row["employee_id"] for row in result}
        assert employee_ids == {"EMP-2"}

        by_id = {row["employee_id"]: row for row in result}
        assert by_id["EMP-2"]["assigned_leads"] == 1
