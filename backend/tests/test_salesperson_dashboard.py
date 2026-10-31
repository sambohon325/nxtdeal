"""
Tests for core/salesperson_dashboard.py + core/salesperson_dashboard_api.py -- a real,
small per-employee rollup composing two already-deeply-tested modules:
core.lead_assignment.get_employee_leads (which lead ids are CURRENTLY assigned to this
employee, per that module's own most-recent-ASSIGNED_TO-relationship-wins semantics) and
core.pipeline_state.get_pipeline_state (each lead's current pipeline state).

core/schema.py, core/validation.py, and core/indexes.py are deliberately NOT covered
anywhere in this test suite -- confirmed via a full repo-wide grep to have zero real
importers anywhere in core/, api/, or hub/ (core/validation.py is the only thing that
imports core/schema.py, and nothing imports core/validation.py itself; core/indexes.py's
RelationshipIndex is never imported anywhere either, despite the repository.py module it
depends on being very much alive elsewhere). All three are orphaned/dead code, the same
class of finding already established for core/bumper_bi.py -- no real behavior to test.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, EMPLOYEE
from core import salesperson_dashboard
from core import salesperson_dashboard_api
from core import lead_assignment
from core import pipeline_state


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)
    monkeypatch.setattr(pipeline_state, "save_graph", lambda filepath: None)


def _make_lead(lead_id, **attrs):
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _make_employee(employee_id, **attrs):
    entity = Entity(id=employee_id, entity_type=EMPLOYEE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


class TestGetSalespersonDashboard:

    def test_employee_with_no_assigned_leads_returns_all_zeros(self):
        _make_employee("EMP-1")

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result == {
            "employee_id": "EMP-1",
            "assigned_leads": 0,
            "active_leads": 0,
            "closed_leads": 0,
        }

    def test_a_lead_with_an_open_pipeline_state_counts_as_active(self):
        _make_employee("EMP-1")
        lead = _make_lead("LEAD-1")
        lead_assignment.assign_lead(lead.id, "EMP-1")
        pipeline_state.start_pipeline(lead.id, initial_state="NEW")

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result["assigned_leads"] == 1
        assert result["active_leads"] == 1
        assert result["closed_leads"] == 0

    @pytest.mark.parametrize("terminal_state", ["SOLD", "LOST"])
    def test_a_lead_in_a_terminal_state_counts_as_closed_not_active(self, terminal_state):
        _make_employee("EMP-1")
        lead = _make_lead("LEAD-1")
        lead_assignment.assign_lead(lead.id, "EMP-1")
        pipeline_state.start_pipeline(lead.id, initial_state=terminal_state)

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result["assigned_leads"] == 1
        assert result["active_leads"] == 0
        assert result["closed_leads"] == 1

    def test_a_lead_with_no_pipeline_state_is_counted_in_assigned_but_neither_bucket(self):
        _make_employee("EMP-1")
        lead = _make_lead("LEAD-1")
        lead_assignment.assign_lead(lead.id, "EMP-1")
        # Never put into the pipeline at all -- get_pipeline_state returns None.

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result["assigned_leads"] == 1
        assert result["active_leads"] == 0
        assert result["closed_leads"] == 0

    def test_mixed_bucket_of_leads_counts_correctly(self):
        _make_employee("EMP-1")
        active_lead = _make_lead("LEAD-ACTIVE")
        closed_lead = _make_lead("LEAD-CLOSED")
        untracked_lead = _make_lead("LEAD-UNTRACKED")

        lead_assignment.assign_lead(active_lead.id, "EMP-1")
        lead_assignment.assign_lead(closed_lead.id, "EMP-1")
        lead_assignment.assign_lead(untracked_lead.id, "EMP-1")

        pipeline_state.start_pipeline(active_lead.id, initial_state="CONTACTED")
        pipeline_state.start_pipeline(closed_lead.id, initial_state="SOLD")

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result["assigned_leads"] == 3
        assert result["active_leads"] == 1
        assert result["closed_leads"] == 1

    def test_a_lead_reassigned_away_no_longer_counts_for_the_original_employee(self):
        # Exercises lead_assignment.get_employee_leads' own most-recent-relationship-wins
        # semantics through this real dashboard composition, not just in isolation.
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        lead = _make_lead("LEAD-1")

        lead_assignment.assign_lead(lead.id, "EMP-1")
        pipeline_state.start_pipeline(lead.id, initial_state="NEW")
        lead_assignment.assign_lead(lead.id, "EMP-2")

        original = salesperson_dashboard.get_salesperson_dashboard("EMP-1")
        new_owner = salesperson_dashboard.get_salesperson_dashboard("EMP-2")

        assert original["assigned_leads"] == 0
        assert new_owner["assigned_leads"] == 1
        assert new_owner["active_leads"] == 1

    def test_leads_assigned_to_a_different_employee_are_not_counted(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        own_lead = _make_lead("LEAD-OWN")
        other_lead = _make_lead("LEAD-OTHER")

        lead_assignment.assign_lead(own_lead.id, "EMP-1")
        lead_assignment.assign_lead(other_lead.id, "EMP-2")

        result = salesperson_dashboard.get_salesperson_dashboard("EMP-1")

        assert result["assigned_leads"] == 1

    def test_result_always_includes_the_employee_id_even_if_the_employee_entity_does_not_exist(self):
        # get_salesperson_dashboard never looks up an Employee entity at all -- it's a
        # pure composition over lead_assignment + pipeline_state, keyed by employee_id.
        result = salesperson_dashboard.get_salesperson_dashboard("EMP-NONEXISTENT")

        assert result["employee_id"] == "EMP-NONEXISTENT"
        assert result["assigned_leads"] == 0


class TestSalespersonDashboardApi:

    def test_get_dashboard_delegates_to_the_real_module_function(self, monkeypatch):
        sentinel = {"employee_id": "EMP-1", "assigned_leads": 5}
        monkeypatch.setattr(
            salesperson_dashboard_api, "get_salesperson_dashboard", lambda employee_id: sentinel
        )
        assert salesperson_dashboard_api.get_dashboard("EMP-1") is sentinel

    def test_get_dashboard_reaches_the_real_live_module_end_to_end(self):
        _make_employee("EMP-1")
        lead = _make_lead("LEAD-1")
        lead_assignment.assign_lead(lead.id, "EMP-1")
        pipeline_state.start_pipeline(lead.id, initial_state="NEW")

        result = salesperson_dashboard_api.get_dashboard("EMP-1")

        assert result["assigned_leads"] == 1
        assert result["active_leads"] == 1
