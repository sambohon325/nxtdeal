"""
Tests for core/lead_record.py / core/lead_record_api.py -- the Lead Record's
next_best_action() rules engine plus the get_lead_record() composition (Activity
Timeline, Communication Hub, Customer Notes, Task Management) and its thin ACL
passthrough.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import LEAD, LEAD_TASK, CUSTOMER, VEHICLE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import lead_tasks
from core import field_notes
from core.lead_record import next_best_action, get_lead_record
from core.lead_record_api import get_lead_record_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_tasks, "save_graph", lambda filepath: None)
    monkeypatch.setattr(field_notes, "save_graph", lambda filepath: None)


def _iso(delta_days=0):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


def _add_lead(lead_id="LEAD-00001", **overrides):
    attrs = {
        "PipelineState": "NEW",
        "FirstName": "Jordan",
        "LastName": "Ramirez",
        "Source": "Website",
    }
    attrs.update(overrides)
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


_task_counter = [0]


def _task(task_type="call", description="Call back", due_at=None, completed=False):
    _task_counter[0] += 1
    return Entity(
        id=f"LTASK-TEST-{_task_counter[0]:05d}",
        entity_type=LEAD_TASK,
        attributes={
            "task_type": task_type,
            "description": description,
            "due_at": due_at,
            "completed": completed,
        },
    )


# ---------------------------------------------------------------------------
# next_best_action() -- pure rules engine, tested directly with lightweight
# Entity fixtures so every branch/priority order can be exercised precisely.
# ---------------------------------------------------------------------------

class TestNextBestActionTerminalStates:

    def test_sold_state_returns_none_action(self):
        lead = _add_lead("LEAD-SOLD", PipelineState="SOLD")
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "None"
        assert "sold" in result["reason"].lower()

    def test_lost_state_returns_none_action(self):
        lead = _add_lead("LEAD-LOST", PipelineState="LOST")
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "None"
        assert "lost" in result["reason"].lower()

    def test_terminal_state_wins_even_with_overdue_tasks_and_no_comms(self):
        lead = _add_lead("LEAD-SOLD-2", PipelineState="SOLD")
        overdue = [_task(description="Should be ignored", due_at=_iso(-5))]
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=overdue)
        assert result["action"] == "None"


class TestNextBestActionOverdueTasks:

    def test_overdue_task_takes_priority_over_open_tasks_and_comms(self):
        lead = _add_lead("LEAD-1", PipelineState="CONTACTED")
        overdue = [_task(description="Call about pricing", due_at=_iso(-3))]
        open_tasks = [_task(description="Send brochure", due_at=_iso(5))]
        result = next_best_action(lead, communications=["x"], open_tasks=open_tasks, overdue_tasks=overdue)
        assert result["action"] == "Overdue: Call about pricing"
        assert "1 task(s) past due" in result["reason"]
        assert result["basis"] == "real_task_data"

    def test_overdue_reason_uses_count_and_oldest_task(self):
        lead = _add_lead("LEAD-2", PipelineState="NEW")
        t1 = _task(description="First overdue", due_at=_iso(-5))
        t2 = _task(description="Second overdue", due_at=_iso(-1))
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[t1, t2])
        assert result["action"] == "Overdue: First overdue"
        assert "2 task(s) past due" in result["reason"]

    def test_overdue_falls_back_to_task_type_when_no_description(self):
        lead = _add_lead("LEAD-3", PipelineState="NEW")
        overdue = [_task(task_type="schedule_appraisal", description="", due_at=_iso(-1))]
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=overdue)
        assert result["action"] == "Overdue: schedule_appraisal"

    def test_overdue_wins_even_with_no_communications_logged(self):
        lead = _add_lead("LEAD-4", PipelineState="NEW")
        overdue = [_task(description="Call back", due_at=_iso(-1))]
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=overdue)
        assert result["action"] == "Overdue: Call back"


class TestNextBestActionNoCommunications:

    def test_no_communications_returns_call_now_with_no_days_when_created_at_missing(self):
        lead = _add_lead("LEAD-5", PipelineState="NEW", PipelineCreatedAt=None)
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "Call now"
        assert "days since" not in result["reason"]
        assert result["basis"] == "real_communication_log"

    def test_no_communications_includes_days_since_pipeline_created(self):
        lead = _add_lead("LEAD-6", PipelineState="NEW", PipelineCreatedAt=_iso(-4))
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "Call now"
        assert "4 days since it entered the pipeline" in result["reason"]

    def test_no_communications_ignores_unparseable_created_at(self):
        lead = _add_lead("LEAD-7", PipelineState="NEW", PipelineCreatedAt="not-a-real-timestamp")
        result = next_best_action(lead, communications=[], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "Call now"
        assert "days since" not in result["reason"]


class TestNextBestActionStalePipelineState:

    def test_stale_state_triggers_at_exactly_2_days(self):
        lead = _add_lead("LEAD-8", PipelineState="CONTACTED", PipelineStateSince=_iso(-2))
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "Follow up today"
        assert "CONTACTED" in result["reason"]
        assert "2 day(s)" in result["reason"]
        assert result["basis"] == "real_pipeline_state_data"

    def test_stale_state_not_triggered_under_2_days(self):
        lead = _add_lead("LEAD-9", PipelineState="CONTACTED", PipelineStateSince=_iso(-1))
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "On track"

    def test_stale_state_yields_to_open_tasks_when_one_exists(self):
        lead = _add_lead("LEAD-10", PipelineState="CONTACTED", PipelineStateSince=_iso(-10))
        open_tasks = [_task(description="Send quote", due_at=_iso(3))]
        result = next_best_action(lead, communications=["x"], open_tasks=open_tasks, overdue_tasks=[])
        assert result["action"] == "Upcoming: Send quote"
        assert result["basis"] == "real_task_data"

    def test_stale_check_does_not_apply_to_states_outside_the_list(self):
        lead = _add_lead("LEAD-11", PipelineState="NEW", PipelineStateSince=_iso(-30))
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "On track"

    @pytest.mark.parametrize(
        "state",
        ["CONTACTED", "APPOINTMENT_SET", "VISITED", "PROPOSAL", "NEGOTIATION"],
    )
    def test_every_documented_stale_eligible_state_triggers(self, state):
        lead = _add_lead(f"LEAD-STALE-{state}", PipelineState=state, PipelineStateSince=_iso(-5))
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "Follow up today"


class TestNextBestActionOpenTasks:

    def test_open_tasks_returns_upcoming_action(self):
        lead = _add_lead("LEAD-12", PipelineState="NEW")
        open_tasks = [_task(description="Send brochure", due_at=_iso(3))]
        result = next_best_action(lead, communications=["x"], open_tasks=open_tasks, overdue_tasks=[])
        assert result["action"] == "Upcoming: Send brochure"
        assert "Due" in result["reason"]
        assert result["basis"] == "real_task_data"

    def test_upcoming_falls_back_to_task_type_when_no_description(self):
        lead = _add_lead("LEAD-13", PipelineState="NEW")
        open_tasks = [_task(task_type="call", description="", due_at=_iso(3))]
        result = next_best_action(lead, communications=["x"], open_tasks=open_tasks, overdue_tasks=[])
        assert result["action"] == "Upcoming: call"


class TestNextBestActionDefault:

    def test_default_on_track_when_no_signal_fires(self):
        lead = _add_lead("LEAD-14", PipelineState="NEW")
        result = next_best_action(lead, communications=["x"], open_tasks=[], overdue_tasks=[])
        assert result["action"] == "On track"
        assert result["basis"] == "real_pipeline_state_data"


# ---------------------------------------------------------------------------
# get_lead_record() -- the full composed record.
# ---------------------------------------------------------------------------

class TestGetLeadRecordLookup:

    def test_unknown_lead_id_returns_error(self):
        result = get_lead_record(ADMIN, "LEAD-DOES-NOT-EXIST")
        assert "error" in result

    def test_wrong_entity_type_returns_lead_not_found(self):
        customer = Entity(id="CUST-NOT-A-LEAD", entity_type=CUSTOMER, attributes={"FirstName": "Alex"})
        ledger.add_entity(customer)
        result = get_lead_record(ADMIN, "CUST-NOT-A-LEAD")
        assert result == {"error": "Lead not found"}


class TestGetLeadRecordAcl:

    def test_service_role_denied(self):
        _add_lead("LEAD-ACL-1")
        result = get_lead_record(SERVICE, "LEAD-ACL-1")
        assert "error" in result

    def test_finance_role_denied(self):
        _add_lead("LEAD-ACL-2")
        result = get_lead_record(FINANCE, "LEAD-ACL-2")
        assert "error" in result

    @pytest.mark.parametrize("role", [ADMIN, SALES, OPERATIONS, MARKETING])
    def test_lead_visible_roles_all_succeed(self, role):
        _add_lead("LEAD-ACL-3")
        result = get_lead_record(role, "LEAD-ACL-3")
        assert "error" not in result
        assert result["lead"]["id"] == "LEAD-ACL-3"


class TestGetLeadRecordComposition:

    def test_communications_and_notes_split_by_category(self):
        _add_lead("LEAD-C1")
        field_notes.create_field_note("Sales", "call", "Talked about pricing", "EMP-1", linked_entity_id="LEAD-C1")
        field_notes.create_field_note("Sales", "email", "Sent brochure", "EMP-1", linked_entity_id="LEAD-C1")
        field_notes.create_field_note("Sales", "objection", "Worried about payment", "EMP-1", linked_entity_id="LEAD-C1")
        field_notes.create_field_note("Sales", "family", "Has 3 kids, needs 3rd row", "EMP-1", linked_entity_id="LEAD-C1")
        # A note for a different lead should never leak in.
        _add_lead("LEAD-C1-OTHER")
        field_notes.create_field_note("Sales", "call", "Unrelated call", "EMP-1", linked_entity_id="LEAD-C1-OTHER")

        result = get_lead_record(ADMIN, "LEAD-C1")

        assert len(result["communications"]) == 2
        assert {c["category"] for c in result["communications"]} == {"call", "email"}
        assert len(result["notes"]) == 2
        assert {n["category"] for n in result["notes"]} == {"objection", "family"}

    def test_notes_omit_categories_outside_comm_and_note_sets(self):
        _add_lead("LEAD-C2")
        field_notes.create_field_note("Sales", "recon", "not a lead-record category", "EMP-1", linked_entity_id="LEAD-C2")

        result = get_lead_record(ADMIN, "LEAD-C2")

        assert result["communications"] == []
        assert result["notes"] == []

    def test_open_and_overdue_task_counts(self):
        _add_lead("LEAD-C3")
        lead_tasks.create_task("LEAD-C3", "call", "Overdue call", _iso(-2), "EMP-1")
        lead_tasks.create_task("LEAD-C3", "send_pricing", "Send pricing", _iso(3), "EMP-1")
        done = lead_tasks.create_task("LEAD-C3", "schedule_appraisal", "Old completed task", _iso(-10), "EMP-1")
        lead_tasks.complete_task(done.id, "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-C3")

        assert len(result["tasks"]) == 3
        assert result["open_task_count"] == 2
        assert result["overdue_task_count"] == 1

    def test_completed_task_never_counted_as_overdue_even_if_due_date_passed(self):
        _add_lead("LEAD-C4")
        task = lead_tasks.create_task("LEAD-C4", "call", "Call back", _iso(-5), "EMP-1")
        lead_tasks.complete_task(task.id, "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-C4")

        assert result["open_task_count"] == 0
        assert result["overdue_task_count"] == 0

    def test_next_best_action_reflects_real_signals_for_a_fresh_lead(self):
        _add_lead("LEAD-C5", PipelineState="NEW")
        result = get_lead_record(ADMIN, "LEAD-C5")
        assert result["next_best_action"]["action"] == "Call now"

    def test_next_best_action_reflects_real_overdue_task(self):
        _add_lead("LEAD-C6", PipelineState="NEW")
        field_notes.create_field_note("Sales", "call", "Talked once", "EMP-1", linked_entity_id="LEAD-C6")
        lead_tasks.create_task("LEAD-C6", "call", "Follow up call", _iso(-1), "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-C6")
        assert result["next_best_action"]["action"] == "Overdue: Follow up call"

    def test_not_yet_tracked_has_exactly_the_three_documented_keys(self):
        _add_lead("LEAD-C7")
        result = get_lead_record(ADMIN, "LEAD-C7")
        assert set(result["not_yet_tracked"].keys()) == {
            "preferred_communication_method",
            "trade_information",
            "credit_status",
        }

    def test_related_entities_included(self):
        _add_lead("LEAD-C8")
        vehicle = Entity(id="VEH-TEST-LR-1", entity_type=VEHICLE, attributes={"VIN": "1FAKEVIN0000001"})
        ledger.add_entity(vehicle)
        ledger.add_relationship(
            Relationship(source_id="LEAD-C8", target_id="VEH-TEST-LR-1", relationship_type="INTERESTED_IN")
        )

        result = get_lead_record(ADMIN, "LEAD-C8")

        assert any(r["entity"]["id"] == "VEH-TEST-LR-1" for r in result["related_entities"])

    def test_task_briefs_carry_expected_fields(self):
        _add_lead("LEAD-C9")
        lead_tasks.create_task("LEAD-C9", "call", "Call back", _iso(2), "EMP-1", assigned_to="EMP-2")

        result = get_lead_record(ADMIN, "LEAD-C9")

        assert len(result["tasks"]) == 1
        brief = result["tasks"][0]
        assert brief["task_type"] == "call"
        assert brief["description"] == "Call back"
        assert brief["completed"] is False
        assert brief["assigned_to"] == "EMP-2"

    def test_note_briefs_carry_expected_fields(self):
        _add_lead("LEAD-C10")
        field_notes.create_field_note("Sales", "objection", "Price sensitive", "EMP-1", linked_entity_id="LEAD-C10")

        result = get_lead_record(ADMIN, "LEAD-C10")

        assert len(result["notes"]) == 1
        brief = result["notes"][0]
        assert brief["category"] == "objection"
        assert brief["body"] == "Price sensitive"
        assert brief["created_by"] == "EMP-1"


class TestGetLeadRecordTimeline:

    def test_timeline_merges_communications_and_task_created_events(self):
        _add_lead("LEAD-T1")
        field_notes.create_field_note("Sales", "call", "First contact", "EMP-1", linked_entity_id="LEAD-T1")
        lead_tasks.create_task("LEAD-T1", "call", "Follow up", _iso(5), "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-T1")

        types = {e["type"] for e in result["timeline"]}
        assert "communication" in types
        assert "task_created" in types

    def test_timeline_distinguishes_note_from_communication_type(self):
        _add_lead("LEAD-T2")
        field_notes.create_field_note("Sales", "call", "A call", "EMP-1", linked_entity_id="LEAD-T2")
        field_notes.create_field_note("Sales", "objection", "An objection", "EMP-1", linked_entity_id="LEAD-T2")

        result = get_lead_record(ADMIN, "LEAD-T2")

        kinds_by_category = {e["details"]["category"]: e["type"] for e in result["timeline"] if e["type"] in ("communication", "note")}
        assert kinds_by_category["call"] == "communication"
        assert kinds_by_category["objection"] == "note"

    def test_timeline_includes_task_completed_event(self):
        _add_lead("LEAD-T3")
        task = lead_tasks.create_task("LEAD-T3", "call", "Call back", _iso(-1), "EMP-1")
        lead_tasks.complete_task(task.id, "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-T3")
        types = [e["type"] for e in result["timeline"]]
        assert "task_completed" in types

    def test_timeline_omits_task_completed_event_for_open_task(self):
        _add_lead("LEAD-T4")
        lead_tasks.create_task("LEAD-T4", "call", "Call back", _iso(5), "EMP-1")

        result = get_lead_record(ADMIN, "LEAD-T4")
        types = [e["type"] for e in result["timeline"]]
        assert "task_created" in types
        assert "task_completed" not in types

    def test_timeline_sorted_descending_by_timestamp(self):
        _add_lead("LEAD-T5")
        field_notes.create_field_note("Sales", "call", "Older", "EMP-1", linked_entity_id="LEAD-T5")
        field_notes.create_field_note("Sales", "email", "Newer", "EMP-1", linked_entity_id="LEAD-T5")

        result = get_lead_record(ADMIN, "LEAD-T5")

        timestamps = [e["timestamp"] for e in result["timeline"] if e["timestamp"]]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# get_lead_record_api() -- a trivial passthrough, no extra ACL logic of its own.
# ---------------------------------------------------------------------------

class TestGetLeadRecordApi:

    def test_api_matches_direct_call_for_a_full_record(self):
        _add_lead("LEAD-API-1")
        field_notes.create_field_note("Sales", "call", "Talked", "EMP-1", linked_entity_id="LEAD-API-1")
        lead_tasks.create_task("LEAD-API-1", "call", "Follow up", _iso(3), "EMP-1")

        direct = get_lead_record(ADMIN, "LEAD-API-1")
        via_api = get_lead_record_api(ADMIN, "LEAD-API-1")

        assert via_api == direct

    def test_api_acl_denial_propagates_unchanged(self):
        _add_lead("LEAD-API-2")

        direct = get_lead_record(SERVICE, "LEAD-API-2")
        via_api = get_lead_record_api(SERVICE, "LEAD-API-2")

        assert via_api == direct
        assert "error" in via_api

    def test_api_unknown_lead_id_propagates_error(self):
        via_api = get_lead_record_api(ADMIN, "LEAD-NOPE")
        assert "error" in via_api
