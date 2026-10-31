"""
Tests for core/routing_api.py -- the thin wrapper connecting an auto-assigned lead
(core/lead_routing.py, exercised elsewhere -- see test_lead_routing_escalation.py)
to a real, persisted audit-log event (core/audit.py).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import audit as audit_module
import core.routing_api as routing_api
from core.routing_api import assign_new_lead


@pytest.fixture(autouse=True)
def fresh_audit_log():
    audit_module.audit_log.reset()
    yield
    audit_module.audit_log.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(routing_api, "save_audit_log", lambda filepath: None)


class TestAssignNewLead:

    def test_delegates_to_auto_assign_lead(self, monkeypatch):
        monkeypatch.setattr(routing_api, "auto_assign_lead", lambda lead_id: "EMP-00001")
        result = assign_new_lead("LEAD-00001")
        assert result == {"lead_id": "LEAD-00001", "assigned_to": "EMP-00001"}

    def test_records_a_real_audit_event(self, monkeypatch):
        monkeypatch.setattr(routing_api, "auto_assign_lead", lambda lead_id: "EMP-00002")
        assign_new_lead("LEAD-00002")

        events = audit_module.audit_log.events
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "lead_assigned"
        assert event.entity_id == "LEAD-00002"
        assert event.actor == "routing_engine"
        assert event.details == {"assigned_to": "EMP-00002"}
        assert "LEAD-00002" in event.summary
        assert "EMP-00002" in event.summary

    def test_handles_a_lead_with_no_available_assignee(self, monkeypatch):
        monkeypatch.setattr(routing_api, "auto_assign_lead", lambda lead_id: None)
        result = assign_new_lead("LEAD-00003")
        assert result == {"lead_id": "LEAD-00003", "assigned_to": None}

    def test_each_call_records_its_own_event(self, monkeypatch):
        monkeypatch.setattr(routing_api, "auto_assign_lead", lambda lead_id: "EMP-00001")
        assign_new_lead("LEAD-00001")
        assign_new_lead("LEAD-00002")
        assert len(audit_module.audit_log.events) == 2
