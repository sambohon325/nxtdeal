"""
Tests for core/workflow_engine_v2.py + core/workflow_engine_v2_api.py -- the
Operations Workflow Engine v2 pilot (Sam's "workflows should be the primary way
work gets done in NXTDeal" reframe). Added per BUILD_QUEUE.md's standing
"convert to a real pytest suite as each module gets touched" rule.

No save_graph stubbing -- same precedent tests/test_workflow_automation.py already
establishes: conftest.py points DEALEROS_STORAGE_DIR at an isolated tempdir for the
whole test session, so letting start_workflow_instance_v2()/advance_step()/etc.'s
own unconditional save_graph() calls write for real is harmless and deterministic.

Uses real graph entity ids (e.g. "VEH-00001") directly as linked_entity_id values
so _resolve_linked_entity()'s first branch (a direct ledger.get_entity() lookup)
resolves them without needing to seed core.dealeros.registry's business-key dicts.

Fixture workflows used throughout: "operations.vehicle_intake_v2" (8 real catalog
steps: acquire/inspect/repair/detail/photograph/merchandise/price/frontline) and
"operations.recon_v2" (6 real catalog steps: assign_vendor/body_work/mechanical/
detail/quality_check/return_to_lot), both confirmed directly against
core/workflow_definitions_v2.py's own source.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, EMPLOYEE
from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE

from core import workflow_engine_v2 as wev2
from core import workflow_engine_v2_api as wev2_api

VEHICLE_INTAKE_KEY = "operations.vehicle_intake_v2"
RECON_KEY = "operations.recon_v2"

VEHICLE_INTAKE_STEPS = [
    "acquire", "inspect", "repair", "detail",
    "photograph", "merchandise", "price", "frontline",
]

RECON_STEPS = [
    "assign_vendor", "body_work", "mechanical",
    "detail", "quality_check", "return_to_lot",
]


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _add_vehicle(entity_id="VEH-00001"):
    ledger.add_entity(Entity(id=entity_id, entity_type=VEHICLE, attributes={"Make": "Chevrolet"}))
    return entity_id


def _add_employee(entity_id="EMP-00001"):
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes={}))
    return entity_id


def _start(workflow_key=VEHICLE_INTAKE_KEY, linked_entity_id=None, started_by="EMP-00001"):
    instance, error = wev2.start_workflow_instance_v2(
        workflow_key=workflow_key,
        started_by=started_by,
        linked_entity_id=linked_entity_id,
    )
    assert error is None
    return instance


# ---------------------------------------------------------------------------
# start_workflow_instance_v2
# ---------------------------------------------------------------------------


class TestStartWorkflowInstanceV2:
    def test_creates_instance_with_first_step_in_progress(self):
        instance = _start()

        assert instance.attributes["workflow_key"] == VEHICLE_INTAKE_KEY
        assert instance.attributes["department"] == "Operations"
        assert instance.attributes["status"] == "in_progress"
        assert instance.attributes["current_step_key"] == "acquire"

        steps = instance.attributes["steps"]
        assert [s["key"] for s in steps] == VEHICLE_INTAKE_STEPS
        assert steps[0]["status"] == "in_progress"
        assert steps[0]["started_at"] is not None
        for s in steps[1:]:
            assert s["status"] == "not_started"
            assert s["started_at"] is None

    def test_history_seeded_with_started_action(self):
        instance = _start()
        assert len(instance.attributes["history"]) == 1
        assert instance.attributes["history"][0]["action"] == "started"
        assert instance.attributes["history"][0]["step"] == "acquire"

    def test_unknown_workflow_key_errors(self):
        instance, error = wev2.start_workflow_instance_v2(
            workflow_key="operations.not_a_real_workflow_v2",
            started_by="EMP-00001",
        )
        assert instance is None
        assert "no v2 workflow definition" in error

    def test_no_linked_entity_resolves_to_none(self):
        instance = _start()
        assert instance.attributes["linked_entity_id"] is None
        assert instance.attributes["linked_entity_raw"] is None

    def test_real_linked_entity_resolves_and_creates_tracks_relationship(self):
        vehicle_id = _add_vehicle()
        instance = _start(linked_entity_id=vehicle_id)

        assert instance.attributes["linked_entity_id"] == vehicle_id
        assert instance.attributes["linked_entity_raw"] == vehicle_id

        tracks = [
            r for r in ledger.relationships
            if r.source_id == instance.id and r.target_id == vehicle_id
        ]
        assert len(tracks) == 1
        assert tracks[0].relationship_type == "TRACKS"

    def test_unresolvable_linked_entity_keeps_raw_but_resolved_is_none(self):
        instance = _start(linked_entity_id="NOT-A-REAL-ID-999")

        assert instance.attributes["linked_entity_id"] is None
        assert instance.attributes["linked_entity_raw"] == "NOT-A-REAL-ID-999"

        tracks = [r for r in ledger.relationships if r.source_id == instance.id]
        assert tracks == []

    def test_second_workflow_definition_has_its_own_step_set(self):
        instance = _start(workflow_key=RECON_KEY)
        steps = instance.attributes["steps"]
        assert [s["key"] for s in steps] == RECON_STEPS
        assert instance.attributes["current_step_key"] == "assign_vendor"


# ---------------------------------------------------------------------------
# advance_step
# ---------------------------------------------------------------------------


class TestAdvanceStep:
    def test_advances_to_next_step(self):
        instance = _start()

        updated, error = wev2.advance_step(instance.id, actor="EMP-00001")
        assert error is None

        steps = updated.attributes["steps"]
        assert steps[0]["status"] == "completed"
        assert steps[0]["completed_at"] is not None
        assert steps[1]["status"] == "in_progress"
        assert steps[1]["started_at"] is not None
        assert updated.attributes["current_step_key"] == "inspect"
        assert updated.attributes["status"] == "in_progress"

        last_history = updated.attributes["history"][-1]
        assert last_history["action"] == "advanced"
        assert last_history["step"] == "inspect"

    def test_advancing_past_last_step_completes_instance(self):
        instance = _start()

        for _ in VEHICLE_INTAKE_STEPS:
            instance, error = wev2.advance_step(instance.id, actor="EMP-00001")
            assert error is None

        assert instance.attributes["status"] == "completed"
        assert instance.attributes["completed_at"] is not None
        assert instance.attributes["current_step_key"] is None
        assert all(s["status"] == "completed" for s in instance.attributes["steps"])

        last_history = instance.attributes["history"][-1]
        assert last_history["action"] == "completed"

    def test_refuses_when_not_in_progress(self):
        instance = _start()
        wev2.block_step(instance.id, "acquire", "waiting on paperwork", actor="EMP-00001")

        updated, error = wev2.advance_step(instance.id, actor="EMP-00001")
        assert updated is None
        assert "not 'in_progress'" in error

    def test_unknown_instance_errors(self):
        instance, error = wev2.advance_step("WF2-NOPE", actor="EMP-00001")
        assert instance is None
        assert "no workflow instance" in error

    def test_carries_notes_into_history(self):
        instance = _start()
        updated, error = wev2.advance_step(instance.id, actor="EMP-00001", notes="looks good")
        assert error is None
        assert updated.attributes["history"][-1]["notes"] == "looks good"


# ---------------------------------------------------------------------------
# tasks / evidence / comments
# ---------------------------------------------------------------------------


class TestStepTasks:
    def test_add_and_complete_task(self):
        instance = _start()

        updated, error = wev2.add_step_task(
            instance.id, "acquire", "Call the auction house back", actor="EMP-00001",
            assigned_to="EMP-00002",
        )
        assert error is None
        step = wev2._get_step(updated, "acquire")
        assert len(step["tasks"]) == 1
        task = step["tasks"][0]
        assert task["description"] == "Call the auction house back"
        assert task["assigned_to"] == "EMP-00002"
        assert task["status"] == "open"

        updated, error = wev2.complete_step_task(instance.id, "acquire", task["id"], actor="EMP-00002")
        assert error is None
        step = wev2._get_step(updated, "acquire")
        assert step["tasks"][0]["status"] == "completed"
        assert step["tasks"][0]["completed_at"] is not None
        assert step["tasks"][0]["completed_by"] == "EMP-00002"

    def test_empty_description_rejected(self):
        instance = _start()
        updated, error = wev2.add_step_task(instance.id, "acquire", "   ", actor="EMP-00001")
        assert updated is None
        assert "task description is required" in error

    def test_unknown_step_key_rejected(self):
        instance = _start()
        updated, error = wev2.add_step_task(instance.id, "not_a_step", "do the thing", actor="EMP-00001")
        assert updated is None
        assert "no step 'not_a_step'" in error

    def test_complete_unknown_task_rejected(self):
        instance = _start()
        updated, error = wev2.complete_step_task(instance.id, "acquire", "TASK-NOPE", actor="EMP-00001")
        assert updated is None
        assert "no task" in error

    def test_double_complete_rejected(self):
        instance = _start()
        instance, _ = wev2.add_step_task(instance.id, "acquire", "do it", actor="EMP-00001")
        task_id = wev2._get_step(instance, "acquire")["tasks"][0]["id"]
        instance, _ = wev2.complete_step_task(instance.id, "acquire", task_id, actor="EMP-00001")

        updated, error = wev2.complete_step_task(instance.id, "acquire", task_id, actor="EMP-00001")
        assert updated is None
        assert "already completed" in error


class TestStepEvidenceAndComments:
    def test_add_evidence(self):
        instance = _start()
        updated, error = wev2.add_step_evidence(
            instance.id, "acquire", "Odometer photo attached", actor="EMP-00001",
            url="https://example.com/photo.jpg",
        )
        assert error is None
        step = wev2._get_step(updated, "acquire")
        assert len(step["evidence"]) == 1
        assert step["evidence"][0]["description"] == "Odometer photo attached"
        assert step["evidence"][0]["url"] == "https://example.com/photo.jpg"

    def test_evidence_never_changes_step_status(self):
        instance = _start()
        updated, _ = wev2.add_step_evidence(instance.id, "acquire", "note", actor="EMP-00001")
        step = wev2._get_step(updated, "acquire")
        assert step["status"] == "in_progress"

    def test_empty_evidence_description_rejected(self):
        instance = _start()
        updated, error = wev2.add_step_evidence(instance.id, "acquire", "", actor="EMP-00001")
        assert updated is None
        assert "evidence description is required" in error

    def test_add_comment(self):
        instance = _start()
        updated, error = wev2.add_step_comment(instance.id, "acquire", "waiting on the vendor", actor="EMP-00001")
        assert error is None
        step = wev2._get_step(updated, "acquire")
        assert len(step["comments"]) == 1
        assert step["comments"][0]["text"] == "waiting on the vendor"
        assert step["comments"][0]["by"] == "EMP-00001"

    def test_empty_comment_rejected(self):
        instance = _start()
        updated, error = wev2.add_step_comment(instance.id, "acquire", "   ", actor="EMP-00001")
        assert updated is None
        assert "comment text is required" in error


# ---------------------------------------------------------------------------
# block / unblock
# ---------------------------------------------------------------------------


class TestBlockUnblockStep:
    def test_block_current_step_blocks_instance(self):
        instance = _start()
        updated, error = wev2.block_step(instance.id, "acquire", "title not on file", actor="EMP-00001")
        assert error is None

        step = wev2._get_step(updated, "acquire")
        assert step["status"] == "blocked"
        assert step["blocked_reason"] == "title not on file"
        assert updated.attributes["status"] == "blocked"
        assert updated.attributes["history"][-1]["action"] == "blocked"

    def test_block_future_step_also_flips_instance_to_blocked(self):
        # _recompute_instance_status() checks ANY step's status, not only the
        # current one -- confirmed directly against the real implementation.
        instance = _start()
        updated, error = wev2.block_step(instance.id, "price", "no comps available yet", actor="EMP-00001")
        assert error is None
        assert updated.attributes["status"] == "blocked"
        assert wev2._get_step(updated, "acquire")["status"] == "in_progress"
        assert wev2._get_step(updated, "price")["status"] == "blocked"

    def test_empty_reason_rejected(self):
        instance = _start()
        updated, error = wev2.block_step(instance.id, "acquire", "", actor="EMP-00001")
        assert updated is None
        assert "block reason is required" in error

    def test_cannot_block_completed_instance(self):
        instance = _start()
        for _ in VEHICLE_INTAKE_STEPS:
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")
        assert instance.attributes["status"] == "completed"

        updated, error = wev2.block_step(instance.id, "acquire", "too late", actor="EMP-00001")
        assert updated is None
        assert "already completed" in error

    def test_unblock_current_step_returns_to_in_progress(self):
        instance = _start()
        instance, _ = wev2.block_step(instance.id, "acquire", "reason", actor="EMP-00001")

        updated, error = wev2.unblock_step(instance.id, "acquire", actor="EMP-00001", notes="resolved")
        assert error is None

        step = wev2._get_step(updated, "acquire")
        assert step["status"] == "in_progress"
        assert step["blocked_reason"] is None
        assert updated.attributes["status"] == "in_progress"
        assert updated.attributes["history"][-1]["action"] == "unblocked"

    def test_unblock_non_current_step_returns_to_not_started(self):
        instance = _start()
        instance, _ = wev2.block_step(instance.id, "price", "reason", actor="EMP-00001")

        updated, error = wev2.unblock_step(instance.id, "price", actor="EMP-00001")
        assert error is None
        step = wev2._get_step(updated, "price")
        assert step["status"] == "not_started"
        assert updated.attributes["status"] == "in_progress"

    def test_unblock_when_not_blocked_rejected(self):
        instance = _start()
        updated, error = wev2.unblock_step(instance.id, "acquire", actor="EMP-00001")
        assert updated is None
        assert "is not blocked" in error


# ---------------------------------------------------------------------------
# approvals
# ---------------------------------------------------------------------------


class TestStepApprovals:
    def test_request_approval_sets_instance_waiting_approval(self):
        instance = _start()
        updated, error = wev2.request_step_approval(
            instance.id, "acquire", requested_by="EMP-00001", note="needs manager sign-off",
        )
        assert error is None
        assert updated.attributes["status"] == "waiting_approval"

        step = wev2._get_step(updated, "acquire")
        assert len(step["approvals"]) == 1
        approval = step["approvals"][0]
        assert approval["status"] == "pending"
        assert approval["requested_by"] == "EMP-00001"
        assert approval["note"] == "needs manager sign-off"

    def test_cannot_request_approval_on_completed_instance(self):
        instance = _start()
        for _ in VEHICLE_INTAKE_STEPS:
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")

        updated, error = wev2.request_step_approval(instance.id, "acquire", requested_by="EMP-00001")
        assert updated is None
        assert "already completed" in error

    def test_decide_approval_approved_returns_to_in_progress(self):
        instance = _start()
        instance, _ = wev2.request_step_approval(instance.id, "acquire", requested_by="EMP-00001")
        approval_id = wev2._get_step(instance, "acquire")["approvals"][0]["id"]

        updated, error = wev2.decide_step_approval(
            instance.id, "acquire", approval_id, approved=True, decided_by="EMP-00002", note="approved",
        )
        assert error is None

        approval = wev2._get_step(updated, "acquire")["approvals"][0]
        assert approval["status"] == "approved"
        assert approval["decided_by"] == "EMP-00002"
        assert approval["decision_note"] == "approved"
        assert updated.attributes["status"] == "in_progress"
        assert updated.attributes["history"][-1]["action"] == "approval_approved"

    def test_decide_approval_rejected_blocks_step(self):
        instance = _start()
        instance, _ = wev2.request_step_approval(instance.id, "acquire", requested_by="EMP-00001")
        approval_id = wev2._get_step(instance, "acquire")["approvals"][0]["id"]

        updated, error = wev2.decide_step_approval(
            instance.id, "acquire", approval_id, approved=False, decided_by="EMP-00002", note="missing title",
        )
        assert error is None

        step = wev2._get_step(updated, "acquire")
        approval = step["approvals"][0]
        assert approval["status"] == "rejected"
        assert step["status"] == "blocked"
        assert "missing title" in step["blocked_reason"]
        assert updated.attributes["status"] == "blocked"
        assert updated.attributes["history"][-1]["action"] == "approval_rejected"

    def test_decide_unknown_approval_rejected(self):
        instance = _start()
        updated, error = wev2.decide_step_approval(
            instance.id, "acquire", "APR-NOPE", approved=True, decided_by="EMP-00002",
        )
        assert updated is None
        assert "no pending approval" in error

    def test_cannot_decide_already_decided_approval_twice(self):
        instance = _start()
        instance, _ = wev2.request_step_approval(instance.id, "acquire", requested_by="EMP-00001")
        approval_id = wev2._get_step(instance, "acquire")["approvals"][0]["id"]
        instance, _ = wev2.decide_step_approval(instance.id, "acquire", approval_id, approved=True, decided_by="EMP-00002")

        updated, error = wev2.decide_step_approval(instance.id, "acquire", approval_id, approved=True, decided_by="EMP-00002")
        assert updated is None
        assert "no pending approval" in error


# ---------------------------------------------------------------------------
# escalation / force-close
# ---------------------------------------------------------------------------


class TestEscalationAndForceClose:
    def test_escalate_instance(self):
        instance = _start()
        updated, error = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="stuck for 5 days")
        assert error is None
        assert updated.attributes["status"] == "escalated"
        assert updated.attributes["escalated_reason"] == "stuck for 5 days"
        assert updated.attributes["escalated_at"] is not None
        assert updated.attributes["history"][-1]["action"] == "escalated"

    def test_escalate_empty_reason_rejected(self):
        instance = _start()
        updated, error = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="")
        assert updated is None
        assert "escalation reason is required" in error

    def test_cannot_escalate_completed_instance(self):
        instance = _start()
        for _ in VEHICLE_INTAKE_STEPS:
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")

        updated, error = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="whatever")
        assert updated is None
        assert "already completed" in error

    def test_escalated_instance_can_still_be_blocked(self):
        # _TERMINAL_INSTANCE_STATUSES only contains "completed" -- an escalated
        # instance is NOT terminal and block_step()'s own terminal-status guard
        # must not reject it.
        instance = _start()
        instance, _ = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="stuck")

        updated, error = wev2.block_step(instance.id, "acquire", "still stuck", actor="EMP-00001")
        assert error is None
        assert wev2._get_step(updated, "acquire")["status"] == "blocked"

    def test_resolve_escalation_returns_to_in_progress(self):
        instance = _start()
        instance, _ = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="stuck")

        updated, error = wev2.resolve_escalation(instance.id, actor="EMP-00001", notes="handled")
        assert error is None
        assert updated.attributes["status"] == "in_progress"
        assert updated.attributes["history"][-1]["action"] == "escalation_resolved"

    def test_resolve_escalation_recomputes_to_blocked_if_step_still_blocked(self):
        instance = _start()
        instance, _ = wev2.block_step(instance.id, "acquire", "reason", actor="EMP-00001")
        instance, _ = wev2.escalate_instance(instance.id, actor="EMP-00001", reason="stuck")

        updated, error = wev2.resolve_escalation(instance.id, actor="EMP-00001")
        assert error is None
        assert updated.attributes["status"] == "blocked"

    def test_resolve_escalation_when_not_escalated_rejected(self):
        instance = _start()
        updated, error = wev2.resolve_escalation(instance.id, actor="EMP-00001")
        assert updated is None
        assert "is not escalated" in error

    def test_force_close_instance(self):
        instance = _start()
        updated, error = wev2.force_close_instance(instance.id, actor="EMP-00001", reason="unit was totaled")
        assert error is None
        assert updated.attributes["status"] == "completed"
        assert updated.attributes["force_closed"] is True
        assert updated.attributes["force_close_reason"] == "unit was totaled"
        assert updated.attributes["history"][-1]["action"] == "force_closed"

    def test_force_close_empty_reason_rejected(self):
        instance = _start()
        updated, error = wev2.force_close_instance(instance.id, actor="EMP-00001", reason="")
        assert updated is None
        assert "reason is required" in error

    def test_cannot_force_close_already_completed_instance(self):
        instance = _start()
        instance, _ = wev2.force_close_instance(instance.id, actor="EMP-00001", reason="done")

        updated, error = wev2.force_close_instance(instance.id, actor="EMP-00001", reason="again")
        assert updated is None
        assert "already completed" in error


# ---------------------------------------------------------------------------
# listing / dashboard / stalled / ai-state
# ---------------------------------------------------------------------------


class TestListInstancesV2:
    def test_filters_by_workflow_key(self):
        _start(workflow_key=VEHICLE_INTAKE_KEY)
        _start(workflow_key=RECON_KEY)

        results = wev2.list_instances_v2(workflow_key=RECON_KEY)
        assert len(results) == 1
        assert results[0].attributes["workflow_key"] == RECON_KEY

    def test_filters_by_status(self):
        a = _start()
        b = _start()
        wev2.escalate_instance(b.id, actor="EMP-00001", reason="stuck")

        active = wev2.list_instances_v2(status="in_progress")
        escalated = wev2.list_instances_v2(status="escalated")
        assert len(active) == 1
        assert active[0].id == a.id
        assert len(escalated) == 1
        assert escalated[0].id == b.id

    def test_filters_by_department_and_category(self):
        _start()
        results_dept = wev2.list_instances_v2(department="Operations")
        results_wrong_dept = wev2.list_instances_v2(department="Sales")
        assert len(results_dept) == 1
        assert results_wrong_dept == []

        results_category = wev2.list_instances_v2(category="vehicle")
        assert len(results_category) == 1

    def test_filters_by_linked_entity_id(self):
        vehicle_id = _add_vehicle()
        matching = _start(linked_entity_id=vehicle_id)
        _start()

        results = wev2.list_instances_v2(linked_entity_id=vehicle_id)
        assert len(results) == 1
        assert results[0].id == matching.id

    def test_respects_limit(self):
        for _ in range(3):
            _start()
        results = wev2.list_instances_v2(limit=2)
        assert len(results) == 2


class TestDashboardV2:
    def test_includes_zero_instance_workflows(self):
        dashboard = wev2.get_dashboard_v2(department="Operations")
        rows_by_key = {r["workflow_key"]: r for r in dashboard["workflows"]}

        assert VEHICLE_INTAKE_KEY in rows_by_key
        assert rows_by_key[VEHICLE_INTAKE_KEY]["active"] == 0
        assert rows_by_key[VEHICLE_INTAKE_KEY]["total"] == 0
        assert rows_by_key[VEHICLE_INTAKE_KEY]["step_count"] == len(VEHICLE_INTAKE_STEPS)

    def test_real_counts_by_status(self):
        a = _start()
        b = _start()
        c = _start()
        wev2.block_step(b.id, "acquire", "reason", actor="EMP-00001")
        wev2.escalate_instance(c.id, actor="EMP-00001", reason="stuck")

        dashboard = wev2.get_dashboard_v2(department="Operations")
        row = next(r for r in dashboard["workflows"] if r["workflow_key"] == VEHICLE_INTAKE_KEY)

        assert row["total"] == 3
        assert row["active"] == 3
        assert row["blocked"] == 1
        assert row["escalated"] == 1
        assert row["completed"] == 0
        assert dashboard["total_active"] == 3
        assert dashboard["total_escalated"] == 1

    def test_completed_instances_are_not_counted_active(self):
        instance = _start()
        for _ in VEHICLE_INTAKE_STEPS:
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")

        dashboard = wev2.get_dashboard_v2(department="Operations")
        row = next(r for r in dashboard["workflows"] if r["workflow_key"] == VEHICLE_INTAKE_KEY)
        assert row["completed"] == 1
        assert row["active"] == 0


class TestStalledInstancesV2:
    def test_no_stalled_instances_when_fresh(self):
        _start()
        stalled = wev2.get_stalled_instances_v2(department="Operations")
        assert stalled == []

    def test_detects_stalled_instance_past_sla(self):
        instance = _start()
        current_step = wev2._current_step(instance)
        current_step["started_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=current_step["sla_hours"] + 5)
        ).isoformat()

        stalled = wev2.get_stalled_instances_v2(department="Operations")
        assert len(stalled) == 1
        assert stalled[0]["instance_id"] == instance.id
        assert stalled[0]["current_step_key"] == "acquire"
        assert stalled[0]["elapsed_hours"] > stalled[0]["sla_hours"]

    def test_completed_instances_excluded_from_stalled(self):
        instance = _start()
        current_step = wev2._current_step(instance)
        current_step["started_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=999)
        ).isoformat()
        for _ in VEHICLE_INTAKE_STEPS:
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")

        stalled = wev2.get_stalled_instances_v2(department="Operations")
        assert stalled == []


class TestInstanceAiState:
    def test_ai_state_for_fresh_instance(self):
        instance = _start()
        state, error = wev2.get_instance_ai_state(instance.id)
        assert error is None

        assert state["current_step"]["key"] == "acquire"
        assert state["next_step"]["key"] == "inspect"
        assert state["blocked_steps"] == []
        assert state["required_approvals"] == []
        assert state["missing_information"] == []
        assert state["stalled"]["is_stalled"] is False
        assert state["suggested_actions"] == []

    def test_ai_state_surfaces_blocked_steps_and_suggested_actions(self):
        instance = _start()
        instance, _ = wev2.block_step(instance.id, "acquire", "title not on file", actor="EMP-00001")

        state, error = wev2.get_instance_ai_state(instance.id)
        assert error is None
        assert len(state["blocked_steps"]) == 1
        assert state["blocked_steps"][0]["key"] == "acquire"
        assert state["blocked_steps"][0]["blocked_reason"] == "title not on file"
        assert len(state["suggested_actions"]) > 0

    def test_ai_state_surfaces_required_approvals(self):
        instance = _start()
        instance, _ = wev2.request_step_approval(instance.id, "acquire", requested_by="EMP-00001", note="sign off")

        state, error = wev2.get_instance_ai_state(instance.id)
        assert error is None
        assert len(state["required_approvals"]) == 1
        assert state["required_approvals"][0]["step_key"] == "acquire"
        assert state["required_approvals"][0]["note"] == "sign off"
        assert "approver" in state["suggested_actions"][0].lower()

    def test_ai_state_surfaces_open_tasks_as_missing_information(self):
        instance = _start()
        instance, _ = wev2.add_step_task(instance.id, "acquire", "confirm mileage", actor="EMP-00001")

        state, error = wev2.get_instance_ai_state(instance.id)
        assert error is None
        assert any("confirm mileage" in m for m in state["missing_information"])

    def test_ai_state_on_last_step_has_no_next_step(self):
        instance = _start()
        for _ in range(len(VEHICLE_INTAKE_STEPS) - 1):
            instance, _ = wev2.advance_step(instance.id, actor="EMP-00001")

        state, error = wev2.get_instance_ai_state(instance.id)
        assert error is None
        assert state["current_step"]["key"] == "frontline"
        assert state["next_step"] is None

    def test_ai_state_unknown_instance_errors(self):
        state, error = wev2.get_instance_ai_state("WF2-NOPE")
        assert state is None
        assert "no workflow instance" in error


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


class TestApiViewRoles:
    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE])
    def test_view_roles_allowed_catalog(self, role):
        result = wev2_api.get_catalog_v2_api(role)
        assert "error" not in result

    def test_unknown_role_denied_catalog(self):
        result = wev2_api.get_catalog_v2_api("NOT_A_ROLE")
        assert result == {"error": "You don't have access to this Workflow"}

    def test_view_roles_allowed_dashboard(self):
        result = wev2_api.get_dashboard_v2_api(SALES, department="Operations")
        assert "error" not in result

    def test_denied_role_dashboard(self):
        result = wev2_api.get_dashboard_v2_api("NOT_A_ROLE")
        assert "error" in result

    def test_view_roles_allowed_stalled(self):
        result = wev2_api.get_stalled_instances_v2_api(FINANCE)
        assert "error" not in result

    def test_view_roles_allowed_list_instances(self):
        result = wev2_api.list_instances_v2_api(MARKETING)
        assert "error" not in result
        assert result["instances"] == []
        assert result["count"] == 0

    def test_list_instances_bad_status_rejected(self):
        result = wev2_api.list_instances_v2_api(ADMIN, status="not_a_real_status")
        assert "error" in result


class TestApiMutateRoles:
    # SALES is a real mutate role (core/workflow_engine_v2_api.py's _MUTATE_ROLES) --
    # added alongside the Sales Workflow Engine v2 rollout so a Sales rep can work
    # their own Lead Management/Desking/Trade Appraisal/etc. instances directly,
    # matching core/deals_api.py's own "SALES can desk a deal" convention. Exercised
    # here against an Operations-prefixed workflow_key specifically to confirm mutate
    # access isn't itself department-scoped -- any _MUTATE_ROLES role can act on any
    # department's v2 instance, the same way _VIEW_ROLES already works.
    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE])
    def test_mutate_roles_allowed_to_start(self, role):
        result = wev2_api.start_workflow_instance_v2_api(role, "EMP-00001", VEHICLE_INTAKE_KEY)
        assert "error" not in result
        assert result["workflow_key"] == VEHICLE_INTAKE_KEY

    @pytest.mark.parametrize("role", [MARKETING, FINANCE])
    def test_non_mutate_roles_denied_start(self, role):
        result = wev2_api.start_workflow_instance_v2_api(role, "EMP-00001", VEHICLE_INTAKE_KEY)
        assert result == {"error": "You don't have access to this Workflow"}

    def test_start_missing_employee_id_rejected(self):
        result = wev2_api.start_workflow_instance_v2_api(ADMIN, None, VEHICLE_INTAKE_KEY)
        assert result == {"error": "employee_id is required"}

    def test_start_unknown_workflow_key_propagates_error(self):
        result = wev2_api.start_workflow_instance_v2_api(ADMIN, "EMP-00001", "operations.bogus_v2")
        assert "error" in result

    def test_full_mutation_lifecycle_through_api(self):
        started = wev2_api.start_workflow_instance_v2_api(OPERATIONS, "EMP-00001", VEHICLE_INTAKE_KEY)
        instance_id = started["id"]

        with_task = wev2_api.add_step_task_api(OPERATIONS, "EMP-00001", instance_id, "acquire", "call vendor")
        assert "error" not in with_task
        task_id = with_task["steps"][0]["tasks"][0]["id"]

        completed_task = wev2_api.complete_step_task_api(OPERATIONS, "EMP-00001", instance_id, "acquire", task_id)
        assert completed_task["steps"][0]["tasks"][0]["status"] == "completed"

        with_evidence = wev2_api.add_step_evidence_api(OPERATIONS, "EMP-00001", instance_id, "acquire", "photo taken")
        assert with_evidence["steps"][0]["evidence"][0]["description"] == "photo taken"

        with_comment = wev2_api.add_step_comment_api(OPERATIONS, "EMP-00001", instance_id, "acquire", "looks fine")
        assert with_comment["steps"][0]["comments"][0]["text"] == "looks fine"

        advanced = wev2_api.advance_step_api(OPERATIONS, "EMP-00001", instance_id)
        assert advanced["current_step_key"] == "inspect"

        blocked = wev2_api.block_step_api(OPERATIONS, "EMP-00001", instance_id, "inspect", "waiting on parts")
        assert blocked["status"] == "blocked"

        unblocked = wev2_api.unblock_step_api(OPERATIONS, "EMP-00001", instance_id, "inspect")
        assert unblocked["status"] == "in_progress"

        with_approval = wev2_api.request_step_approval_api(OPERATIONS, "EMP-00001", instance_id, "inspect", "sign off")
        assert with_approval["status"] == "waiting_approval"
        approval_id = with_approval["steps"][1]["approvals"][0]["id"]

        decided = wev2_api.decide_step_approval_api(
            OPERATIONS, "EMP-00002", instance_id, "inspect", approval_id, approved=True,
        )
        assert decided["status"] == "in_progress"

        escalated = wev2_api.escalate_instance_api(OPERATIONS, "EMP-00001", instance_id, "needs manager eyes")
        assert escalated["status"] == "escalated"

        resolved = wev2_api.resolve_escalation_api(OPERATIONS, "EMP-00001", instance_id)
        assert resolved["status"] == "in_progress"

        closed = wev2_api.force_close_instance_api(OPERATIONS, "EMP-00001", instance_id, "vehicle totaled")
        assert closed["status"] == "completed"
        assert closed["force_closed"] is True

    def test_get_instance_v2_api_roundtrip(self):
        started = wev2_api.start_workflow_instance_v2_api(ADMIN, "EMP-00001", VEHICLE_INTAKE_KEY)
        fetched = wev2_api.get_instance_v2_api(ADMIN, started["id"])
        assert fetched["id"] == started["id"]
        assert fetched["workflow_key"] == VEHICLE_INTAKE_KEY

    def test_get_instance_ai_state_api(self):
        started = wev2_api.start_workflow_instance_v2_api(ADMIN, "EMP-00001", VEHICLE_INTAKE_KEY)
        state = wev2_api.get_instance_ai_state_api(ADMIN, started["id"])
        assert state["current_step"]["key"] == "acquire"

    def test_get_workflow_def_v2_api(self):
        found = wev2_api.get_workflow_def_v2_api(ADMIN, VEHICLE_INTAKE_KEY)
        assert found["key"] == VEHICLE_INTAKE_KEY
        assert len(found["steps"]) == 8

        not_found = wev2_api.get_workflow_def_v2_api(ADMIN, "operations.bogus_v2")
        assert "error" in not_found

    def test_serialize_shape_is_flattened_not_nested(self):
        started = wev2_api.start_workflow_instance_v2_api(ADMIN, "EMP-00001", VEHICLE_INTAKE_KEY)
        assert "attributes" not in started
        assert "entity_type" not in started
        assert started["id"].startswith("WF2")
        assert "workflow_key" in started
        assert "steps" in started
