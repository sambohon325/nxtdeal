"""
Test coverage for core/event_planning.py -- Events' Project Management +
War Room: a real EventTask checklist per Event plus a composed live-ops view
(RSVP attendance + task completion + generated campaigns).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.event_planning as ep
from core.dealership_events import (
    create_event,
    publish_event,
    start_event,
    create_rsvp,
    update_rsvp_status,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _event(name="Community Day", event_type="community"):
    return create_event("EMP-1", name, event_type, "2026-08-01T10:00:00+00:00")


class TestCreateTask:

    def test_missing_event_is_rejected(self):
        result = ep.create_task("EVT-99999", "EMP-1", "Book DJ")
        assert result == {"error": "Event not found"}

    def test_blank_title_is_rejected(self):
        ev = _event()
        result = ep.create_task(ev.id, "EMP-1", "   ")
        assert result == {"error": "A task needs a title"}

    def test_success_returns_full_attributes(self):
        ev = _event()
        task = ep.create_task(
            ev.id, "EMP-1", "Book DJ",
            assignee_employee_id="EMP-2", due_date="2026-07-25", notes="urgent",
        )
        assert task.id.startswith("ETASK")
        assert task.attributes["event_id"] == ev.id
        assert task.attributes["title"] == "Book DJ"
        assert task.attributes["assignee_employee_id"] == "EMP-2"
        assert task.attributes["due_date"] == "2026-07-25"
        assert task.attributes["notes"] == "urgent"
        assert task.attributes["status"] == "open"
        assert task.attributes["created_by"] == "EMP-1"
        assert task.attributes["completed_at"] is None
        assert task.attributes["created_at"]
        assert task.attributes["updated_at"]

    def test_title_is_stripped(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "  Book DJ  ")
        assert task.attributes["title"] == "Book DJ"

    def test_optional_fields_default_sensibly(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        assert task.attributes["assignee_employee_id"] is None
        assert task.attributes["due_date"] is None
        assert task.attributes["notes"] == ""


class TestGetTask:

    def test_missing_task_returns_none(self):
        assert ep.get_task("ETASK-99999") is None

    def test_wrong_type_id_returns_none(self):
        ev = _event()
        assert ep.get_task(ev.id) is None

    def test_real_task_is_returned(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        fetched = ep.get_task(task.id)
        assert fetched.id == task.id


class TestUpdateTask:

    def test_missing_task_is_rejected(self):
        result = ep.update_task("ETASK-99999", {"title": "New title"})
        assert result == {"error": "Task not found"}

    def test_editable_fields_are_applied(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ", notes="n1")
        updated = ep.update_task(task.id, {"title": "Book Live Band", "notes": "n2"})
        assert updated.attributes["title"] == "Book Live Band"
        assert updated.attributes["notes"] == "n2"

    def test_status_key_in_patch_is_silently_ignored(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        updated = ep.update_task(task.id, {"status": "done", "title": "Book Live Band"})
        assert updated.attributes["title"] == "Book Live Band"
        assert updated.attributes["status"] == "open"

    def test_unknown_field_in_patch_is_ignored(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        updated = ep.update_task(task.id, {"bogus_field": "whatever"})
        assert "bogus_field" not in updated.attributes

    def test_updated_at_always_bumped(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        original_updated_at = task.attributes["updated_at"]
        updated = ep.update_task(task.id, {"notes": "changed"})
        assert updated.attributes["updated_at"] >= original_updated_at


class TestUpdateTaskStatus:

    def test_bad_status_is_rejected(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        result = ep.update_task_status(task.id, "bogus")
        assert result == {
            "error": "status must be one of open, in_progress, done, blocked"
        }

    def test_bad_status_checked_before_task_existence(self):
        # A missing task id with a bad status still returns the status-validation
        # error, not "Task not found" -- confirmed live, the status check runs first.
        result = ep.update_task_status("ETASK-99999", "bogus")
        assert result == {
            "error": "status must be one of open, in_progress, done, blocked"
        }

    def test_missing_task_with_valid_status_is_rejected(self):
        result = ep.update_task_status("ETASK-99999", "done")
        assert result == {"error": "Task not found"}

    def test_marking_done_sets_completed_at(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        updated = ep.update_task_status(task.id, "done")
        assert updated.attributes["status"] == "done"
        assert updated.attributes["completed_at"] is not None

    def test_reverting_from_done_clears_completed_at(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        ep.update_task_status(task.id, "done")
        reverted = ep.update_task_status(task.id, "open")
        assert reverted.attributes["status"] == "open"
        assert reverted.attributes["completed_at"] is None

    def test_every_valid_status_is_accepted(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        for status in ("open", "in_progress", "done", "blocked"):
            updated = ep.update_task_status(task.id, status)
            assert updated.attributes["status"] == status


class TestDeleteTask:

    def test_success_removes_the_task(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        result = ep.delete_task(task.id)
        assert result == {"deleted": task.id}
        assert ep.get_task(task.id) is None

    def test_already_deleted_task_is_rejected(self):
        ev = _event()
        task = ep.create_task(ev.id, "EMP-1", "Book DJ")
        ep.delete_task(task.id)
        result = ep.delete_task(task.id)
        assert result == {"error": "Task not found"}

    def test_missing_task_is_rejected(self):
        result = ep.delete_task("ETASK-99999")
        assert result == {"error": "Task not found"}


class TestListTasksForEvent:

    def test_only_returns_tasks_for_the_given_event(self):
        ev1 = _event("Event A")
        ev2 = _event("Event B")
        ep.create_task(ev1.id, "EMP-1", "A task")
        ep.create_task(ev2.id, "EMP-1", "B task")
        tasks = ep.list_tasks_for_event(ev1.id)
        assert len(tasks) == 1
        assert tasks[0].attributes["title"] == "A task"

    def test_status_filter(self):
        ev = _event()
        t1 = ep.create_task(ev.id, "EMP-1", "Open task")
        t2 = ep.create_task(ev.id, "EMP-1", "Done task")
        ep.update_task_status(t2.id, "done")
        open_tasks = ep.list_tasks_for_event(ev.id, status="open")
        assert len(open_tasks) == 1
        assert open_tasks[0].id == t1.id

    def test_sort_order_by_due_date_then_created_at(self):
        ev = _event()
        ep.create_task(ev.id, "EMP-1", "No due date task")
        ep.create_task(ev.id, "EMP-1", "Book Live Band", due_date="2020-01-01")
        ep.create_task(ev.id, "EMP-1", "Order swag", due_date="2099-01-01")
        tasks = ep.list_tasks_for_event(ev.id)
        titles = [t.attributes["title"] for t in tasks]
        assert titles == ["Book Live Band", "Order swag", "No due date task"]

    def test_empty_event_returns_empty_list(self):
        ev = _event()
        assert ep.list_tasks_for_event(ev.id) == []


class TestGetProjectManagementSummary:

    def test_no_tasks_returns_honest_empty_summary(self):
        summary = ep.get_project_management_summary("EVT-99999")
        assert summary["event_id"] == "EVT-99999"
        assert summary["total_tasks"] == 0
        assert summary["by_status"] == {
            "open": 0, "in_progress": 0, "done": 0, "blocked": 0,
        }
        assert summary["completion_pct"] is None
        assert summary["overdue_tasks"] == []
        assert summary["overdue_count"] == 0

    def test_by_status_counts_are_always_present(self):
        ev = _event()
        ep.create_task(ev.id, "EMP-1", "Task 1")
        summary = ep.get_project_management_summary(ev.id)
        assert set(summary["by_status"].keys()) == {
            "open", "in_progress", "done", "blocked",
        }
        assert summary["by_status"]["open"] == 1

    def test_completion_pct_math(self):
        ev = _event()
        t1 = ep.create_task(ev.id, "EMP-1", "Task 1")
        ep.create_task(ev.id, "EMP-1", "Task 2")
        ep.create_task(ev.id, "EMP-1", "Task 3")
        ep.update_task_status(t1.id, "done")
        summary = ep.get_project_management_summary(ev.id)
        assert summary["total_tasks"] == 3
        assert summary["completion_pct"] == round((1 / 3) * 100, 1)

    def test_overdue_excludes_done_and_blocked(self):
        ev = _event()
        t_blocked = ep.create_task(ev.id, "EMP-1", "Blocked task", due_date="2020-01-01")
        ep.update_task_status(t_blocked.id, "blocked")
        t_done = ep.create_task(ev.id, "EMP-1", "Done task", due_date="2020-01-01")
        ep.update_task_status(t_done.id, "done")
        t_overdue = ep.create_task(ev.id, "EMP-1", "Really overdue", due_date="2020-01-01")

        summary = ep.get_project_management_summary(ev.id)
        assert summary["overdue_count"] == 1
        assert [t["title"] for t in summary["overdue_tasks"]] == ["Really overdue"]
        assert summary["overdue_tasks"][0]["id"] == t_overdue.id

    def test_no_due_date_task_is_never_overdue(self):
        ev = _event()
        ep.create_task(ev.id, "EMP-1", "No due date task")
        summary = ep.get_project_management_summary(ev.id)
        assert summary["overdue_count"] == 0

    def test_future_due_date_is_not_overdue(self):
        ev = _event()
        ep.create_task(ev.id, "EMP-1", "Future task", due_date="2099-01-01")
        summary = ep.get_project_management_summary(ev.id)
        assert summary["overdue_count"] == 0


class TestGetEventWarRoom:

    def test_missing_event_propagates_the_error(self):
        result = ep.get_event_war_room("EVT-99999")
        assert result == {"error": "Event not found"}

    def test_draft_event_is_not_live(self):
        ev = _event()
        wr = ep.get_event_war_room(ev.id)
        assert wr["is_live"] is False

    def test_zero_roster_gives_none_check_in_rate_not_zero(self):
        ev = _event()
        wr = ep.get_event_war_room(ev.id)
        assert wr["attendance"]["total_roster"] == 0
        assert wr["attendance"]["check_in_rate_pct"] is None

    def test_scheduled_event_is_still_not_live(self):
        ev = _event()
        publish_event(ev.id)
        wr = ep.get_event_war_room(ev.id)
        assert wr["is_live"] is False

    def test_started_event_is_live(self):
        ev = _event()
        publish_event(ev.id)
        start_event(ev.id)
        wr = ep.get_event_war_room(ev.id)
        assert wr["is_live"] is True

    def test_attendance_math_across_real_rsvps(self):
        ev = _event()
        publish_event(ev.id)
        r1 = create_rsvp(ev.id, "Alice", source="walk_in")
        r2 = create_rsvp(ev.id, "Bob", source="walk_in")
        create_rsvp(ev.id, "Carol", source="walk_in")  # stays "confirmed"
        update_rsvp_status(r1.id, "attended")
        update_rsvp_status(r2.id, "no_show")

        wr = ep.get_event_war_room(ev.id)
        attendance = wr["attendance"]
        assert attendance["total_roster"] == 3
        assert attendance["checked_in_count"] == 1
        assert attendance["no_show_count"] == 1
        assert attendance["check_in_rate_pct"] == round((1 / 3) * 100, 1)
        assert "basis" in attendance

    def test_project_management_summary_is_embedded(self):
        ev = _event()
        ep.create_task(ev.id, "EMP-1", "Task 1")
        ep.create_task(ev.id, "EMP-1", "Task 2")
        wr = ep.get_event_war_room(ev.id)
        assert wr["project_management"]["total_tasks"] == 2

    def test_no_campaigns_generated_by_default(self):
        ev = _event()
        wr = ep.get_event_war_room(ev.id)
        assert wr["campaigns_generated"] == 0
        assert wr["recent_campaigns"] == []

    def test_campaigns_generated_only_counts_matching_event_promo_campaigns(self):
        ev = _event()
        other_ev = _event("Other Event")

        ledger.add_entity(Entity(
            id="CAMP-1", entity_type="Campaign",
            attributes={
                "campaign_type": "event_promo",
                "params": {"event_id": ev.id},
                "name": "Community Day Promo", "status": "draft", "channel": "email",
            },
        ))
        ledger.add_entity(Entity(
            id="CAMP-2", entity_type="Campaign",
            attributes={
                "campaign_type": "event_promo",
                "params": {"event_id": other_ev.id},
                "name": "Other Event Promo", "status": "draft", "channel": "email",
            },
        ))
        # a non-event_promo campaign, deliberately excluded
        ledger.add_entity(Entity(
            id="CAMP-3", entity_type="Campaign",
            attributes={"campaign_type": "retention", "params": {}, "name": "Unrelated"},
        ))

        wr = ep.get_event_war_room(ev.id)
        assert wr["campaigns_generated"] == 1
        assert wr["recent_campaigns"] == [
            {"id": "CAMP-1", "name": "Community Day Promo", "status": "draft", "channel": "email"},
        ]

    def test_recent_campaigns_capped_at_five(self):
        ev = _event()
        for i in range(7):
            ledger.add_entity(Entity(
                id=f"CAMP-{i}", entity_type="Campaign",
                attributes={
                    "campaign_type": "event_promo",
                    "params": {"event_id": ev.id},
                    "name": f"Promo {i}", "status": "draft", "channel": "email",
                },
            ))
        wr = ep.get_event_war_room(ev.id)
        assert wr["campaigns_generated"] == 7
        assert len(wr["recent_campaigns"]) == 5
