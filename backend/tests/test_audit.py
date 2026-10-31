"""
Tests for the Phase 8 audit logging module (core/audit.py, core/audit_storage.py,
core/audit_api.py). Run from backend/ with `pytest`.

Unlike the loose test_*.py scripts at the repo root, this is a real pytest suite with
assertions, per the testing convention documented in CLAUDE.md.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.audit_storage import save_audit_log, load_audit_log
from core import audit as audit_module
from core import audit_api


@pytest.fixture(autouse=True)
def fresh_audit_log():
    """Every test starts with a clean singleton so tests don't leak state into each
    other. Resets the existing AuditLog instance in place (AuditLog.reset()) rather than
    swapping in a new object — core/audit_storage.py already holds a direct reference to
    the singleton via `from core.audit import audit_log`, so replacing the object identity
    here would make load_audit_log() write into an instance this test can no longer see."""

    audit_module.audit_log.reset()

    yield

    audit_module.audit_log.reset()


def test_record_creates_event_with_expected_fields():

    event = audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="Lead LEAD-00001 assigned to EMP-00001",
        entity_id="LEAD-00001",
        actor="routing_engine",
        details={"assigned_to": "EMP-00001"}
    )

    assert event.id == "AUDIT-00001"
    assert event.event_type == "lead_assigned"
    assert event.entity_id == "LEAD-00001"
    assert event.actor == "routing_engine"
    assert event.details == {"assigned_to": "EMP-00001"}
    assert event.timestamp


def test_record_ids_increment():

    first = audit_module.audit_log.record("a", "first")
    second = audit_module.audit_log.record("b", "second")

    assert first.id == "AUDIT-00001"
    assert second.id == "AUDIT-00002"


def test_query_helpers_filter_correctly():

    audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="assigned",
        entity_id="LEAD-1",
        actor="routing_engine"
    )

    audit_module.audit_log.record(
        event_type="lead_escalated",
        summary="escalated",
        entity_id="LEAD-2",
        actor="escalation_engine"
    )

    assert len(audit_module.audit_log.get_for_entity("LEAD-1")) == 1
    assert len(audit_module.audit_log.get_by_actor("escalation_engine")) == 1
    assert len(audit_module.audit_log.get_by_type("lead_assigned")) == 1
    assert len(audit_module.audit_log.get_all()) == 2


def test_audit_api_list_and_dashboard():

    audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="assigned",
        entity_id="LEAD-1",
        actor="routing_engine"
    )

    audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="assigned again",
        entity_id="LEAD-2",
        actor="routing_engine"
    )

    results = audit_api.list_audit_events(event_type="lead_assigned")
    assert len(results) == 2

    dashboard = audit_api.get_audit_dashboard()
    assert dashboard["total_events"] == 2
    assert dashboard["by_type"] == {"lead_assigned": 2}
    assert len(dashboard["recent"]) == 2


def test_save_and_load_round_trip(tmp_path):

    audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="assigned",
        entity_id="LEAD-1",
        actor="routing_engine",
        details={"assigned_to": "EMP-1"}
    )

    filepath = str(tmp_path / "audit.json")

    save_audit_log(filepath)

    # Simulate a fresh process: clear the in-memory log, then load from disk.
    audit_module.audit_log.reset()

    load_audit_log(filepath)

    events = audit_module.audit_log.get_all()

    assert len(events) == 1
    assert events[0].entity_id == "LEAD-1"
    assert events[0].details == {"assigned_to": "EMP-1"}

    # Counter should continue from the restored id, not restart at 1.
    next_event = audit_module.audit_log.record("x", "next")
    assert next_event.id == "AUDIT-00002"


def test_load_audit_log_missing_file_is_noop(tmp_path):

    missing_path = str(tmp_path / "does_not_exist.json")

    load_audit_log(missing_path)

    assert audit_module.audit_log.get_all() == []
