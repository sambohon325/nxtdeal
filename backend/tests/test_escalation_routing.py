"""
Tests for core/escalation_routing.py / core/escalation_routing_api.py -- real,
least-busy-first reassignment of a stuck lead (reused by the escalation dashboard's
own real reassign action), plus the API layer's own real audit-logging wrapper on
top of it.

core/escalation_routing.reassign_escalated_lead() itself already has direct
coverage in test_lead_routing_escalation.py -- this file's own
TestReassignEscalatedLead class re-confirms that same behavior directly against
this module (not just transitively via the shared cluster test), and
TestEscalationRoutingApi is what actually gives the audit-logging API wrapper its
first direct coverage.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD
from core.audit import audit_log

from core import lead_assignment
from core import pipeline_state
from core.lead_assignment import assign_lead, get_assigned_employee

from core import escalation_routing
from core import escalation_routing_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)
    monkeypatch.setattr(pipeline_state, "save_graph", lambda filepath: None)
    monkeypatch.setattr(escalation_routing_api, "save_audit_log", lambda filepath: None)


def _add_lead(lead_id):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))


def _assigned_lead(lead_id, employee_id, state="NEW"):
    # A real active (non-SOLD/LOST) pipeline state is what actually makes a lead
    # count toward get_active_workload() -- without one, every lead reads as 0
    # workload regardless of how many are assigned, and a "least busy" comparison
    # between two employees who both show 0 becomes a genuine tie decided only by
    # set-iteration/hash-seed order, not by the real counts the test means to prove.
    _add_lead(lead_id)
    assign_lead(lead_id, employee_id)
    pipeline_state.start_pipeline(lead_id, initial_state=state)


class TestReassignEscalatedLead:

    def test_raises_when_no_employees_are_assigned_to_anything(self):
        _add_lead("STUCK")

        with pytest.raises(ValueError):
            escalation_routing.reassign_escalated_lead("STUCK")

    def test_reassigns_to_the_real_least_busy_employee(self):
        _assigned_lead("A1", "EMP-1", state="NEW")
        _assigned_lead("A2", "EMP-1", state="CONTACTED")
        _assigned_lead("B1", "EMP-2", state="NEW")
        _add_lead("STUCK")

        result = escalation_routing.reassign_escalated_lead("STUCK")

        assert result == {"lead_id": "STUCK", "assigned_to": "EMP-2", "status": "REASSIGNED"}
        assert get_assigned_employee("STUCK") == "EMP-2"

    def test_ignores_terminal_leads_when_measuring_busyness(self):
        # EMP-1 has 3 assigned leads but 2 are terminal -> effective workload 1.
        # EMP-2 has 2 active leads -> workload 2. The stuck lead should go to EMP-1.
        _assigned_lead("A1", "EMP-1", state="NEW")
        _assigned_lead("A2", "EMP-1", state="SOLD")
        _assigned_lead("A3", "EMP-1", state="LOST")
        _assigned_lead("B1", "EMP-2", state="NEW")
        _assigned_lead("B2", "EMP-2", state="CONTACTED")
        _add_lead("STUCK")

        result = escalation_routing.reassign_escalated_lead("STUCK")

        assert result["assigned_to"] == "EMP-1"


class TestEscalationRoutingApi:

    def test_reassign_returns_the_same_real_result_as_the_underlying_function(self):
        _add_lead("A1")
        assign_lead("A1", "EMP-1")
        _add_lead("STUCK")

        result = escalation_routing_api.reassign("STUCK")

        assert result == {"lead_id": "STUCK", "assigned_to": "EMP-1", "status": "REASSIGNED"}

    def test_reassign_records_a_real_audit_event(self):
        _add_lead("A1")
        assign_lead("A1", "EMP-1")
        _add_lead("STUCK")

        before = len(audit_log.events)
        escalation_routing_api.reassign("STUCK")

        assert len(audit_log.events) == before + 1
        event = audit_log.events[-1]
        assert event.event_type == "lead_escalated"
        assert event.entity_id == "STUCK"
        assert event.actor == "escalation_engine"
        assert "STUCK" in event.summary

    def test_reassign_propagates_the_real_value_error_when_no_employees_exist(self):
        _add_lead("STUCK")

        with pytest.raises(ValueError):
            escalation_routing_api.reassign("STUCK")
