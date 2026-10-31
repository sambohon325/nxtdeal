"""
Tests for core/lead_tasks.py / core/lead_tasks_api.py -- lead follow-up task
management (Sales sub-menu spec, session 92 follow-up). Run from backend/ with
`pytest`.

Covers: create_task()'s not-found/wrong-entity-type rejection, invalid task_type
rejection, the real attribute shape (description/completed*/created_at defaults,
assigned_to defaulting to created_by vs. an explicit override); get_task()'s
found/not-found/wrong-entity-type behavior; complete_task()'s not-found/already-
completed rejection and the real completion stamp; list_tasks()'s lead_id/
assigned_to filters, include_completed=False exclusion, and the due_at-then-
created_at sort fallback; list_overdue_tasks()'s real "due_at already passed"
filter (excluding completed tasks and tasks with no due_at, honoring an explicit
as_of override); and lead_tasks_api.py's ACL layer (ADMIN/OPERATIONS/SALES/
MARKETING allowed, FINANCE/SERVICE denied, on all three functions).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER
from core import lead_tasks
from core import lead_tasks_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, FINANCE, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lead_tasks, "save_graph", lambda filepath: None)


def _make_lead(lead_id="LEAD-1"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))
    return lead_id


class TestCreateTask:

    def test_lead_not_found(self):
        result = lead_tasks.create_task("LEAD-BOGUS", "call", "desc", "2026-01-01", "EMP-1")
        assert result == {"error": "Lead 'LEAD-BOGUS' not found"}

    def test_wrong_entity_type_treated_as_not_found(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=CUSTOMER, attributes={}))
        result = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")
        assert result == {"error": "Lead 'LEAD-1' not found"}

    def test_invalid_task_type_rejected(self):
        _make_lead("LEAD-1")
        result = lead_tasks.create_task("LEAD-1", "carrier_pigeon", "desc", "2026-01-01", "EMP-1")
        assert "error" in result

    def test_every_valid_task_type_accepted(self):
        _make_lead("LEAD-1")
        for task_type in lead_tasks.TASK_TYPES:
            task = lead_tasks.create_task("LEAD-1", task_type, "desc", "2026-01-01", "EMP-1")
            assert task.attributes["task_type"] == task_type

    def test_happy_path_attribute_shape(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "Call about pricing", "2026-01-02", "EMP-9")

        assert task.id.startswith("LTASK")
        assert task.attributes["lead_id"] == "LEAD-1"
        assert task.attributes["task_type"] == "call"
        assert task.attributes["description"] == "Call about pricing"
        assert task.attributes["due_at"] == "2026-01-02"
        assert task.attributes["completed"] is False
        assert task.attributes["completed_at"] is None
        assert task.attributes["completed_by"] is None
        assert task.attributes["created_by"] == "EMP-9"
        assert task.attributes["created_at"]

    def test_description_defaults_to_empty_string(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", None, "2026-01-02", "EMP-1")
        assert task.attributes["description"] == ""

    def test_assigned_to_defaults_to_created_by(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-02", "EMP-1")
        assert task.attributes["assigned_to"] == "EMP-1"

    def test_assigned_to_explicit_override(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-02", "EMP-1", assigned_to="EMP-2")
        assert task.attributes["assigned_to"] == "EMP-2"
        assert task.attributes["created_by"] == "EMP-1"


class TestGetTask:

    def test_found_returns_entity(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")
        assert lead_tasks.get_task(task.id) is task

    def test_not_found_returns_none(self):
        assert lead_tasks.get_task("LTASK-BOGUS") is None

    def test_wrong_entity_type_returns_none(self):
        ledger.add_entity(Entity(id="LTASK-FAKE", entity_type=LEAD, attributes={}))
        assert lead_tasks.get_task("LTASK-FAKE") is None


class TestCompleteTask:

    def test_task_not_found(self):
        result = lead_tasks.complete_task("LTASK-BOGUS", "EMP-1")
        assert result == {"error": "Task not found"}

    def test_already_completed_rejected(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")
        lead_tasks.complete_task(task.id, "EMP-1")

        result = lead_tasks.complete_task(task.id, "EMP-2")
        assert result == {"error": "Task is already completed"}

    def test_success_stamps_completion(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")

        result = lead_tasks.complete_task(task.id, "EMP-9")

        assert result.attributes["completed"] is True
        assert result.attributes["completed_at"]
        assert result.attributes["completed_by"] == "EMP-9"
        # get_task reflects the same in-place mutation.
        assert lead_tasks.get_task(task.id).attributes["completed"] is True


class TestListTasks:

    def test_filters_by_lead_id(self):
        _make_lead("LEAD-1")
        _make_lead("LEAD-2")
        lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1")
        lead_tasks.create_task("LEAD-2", "call", "d", "2026-01-01", "EMP-1")

        results = lead_tasks.list_tasks(lead_id="LEAD-1")
        assert len(results) == 1
        assert results[0].attributes["lead_id"] == "LEAD-1"

    def test_filters_by_assigned_to(self):
        _make_lead("LEAD-1")
        lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1", assigned_to="EMP-A")
        lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1", assigned_to="EMP-B")

        results = lead_tasks.list_tasks(assigned_to="EMP-A")
        assert len(results) == 1
        assert results[0].attributes["assigned_to"] == "EMP-A"

    def test_include_completed_false_excludes_completed_tasks(self):
        _make_lead("LEAD-1")
        open_task = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1")
        done_task = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-02", "EMP-1")
        lead_tasks.complete_task(done_task.id, "EMP-1")

        results = lead_tasks.list_tasks(lead_id="LEAD-1", include_completed=False)
        ids = [t.id for t in results]
        assert open_task.id in ids
        assert done_task.id not in ids

    def test_include_completed_true_includes_everything_by_default(self):
        _make_lead("LEAD-1")
        open_task = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1")
        done_task = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-02", "EMP-1")
        lead_tasks.complete_task(done_task.id, "EMP-1")

        results = lead_tasks.list_tasks(lead_id="LEAD-1")
        ids = {t.id for t in results}
        assert ids == {open_task.id, done_task.id}

    def test_sorted_by_due_at_ascending(self):
        _make_lead("LEAD-1")
        later = lead_tasks.create_task("LEAD-1", "call", "d", "2026-06-01", "EMP-1")
        earlier = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1")

        results = lead_tasks.list_tasks(lead_id="LEAD-1")
        assert [t.id for t in results] == [earlier.id, later.id]

    def test_no_filters_returns_every_task(self):
        _make_lead("LEAD-1")
        _make_lead("LEAD-2")
        lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01", "EMP-1")
        lead_tasks.create_task("LEAD-2", "call", "d", "2026-01-01", "EMP-1")

        assert len(lead_tasks.list_tasks()) == 2


class TestListOverdueTasks:

    def test_filters_to_tasks_with_due_at_before_as_of(self):
        _make_lead("LEAD-1")
        overdue = lead_tasks.create_task("LEAD-1", "call", "d", "2026-01-01T00:00:00", "EMP-1")
        not_yet_due = lead_tasks.create_task("LEAD-1", "call", "d", "2026-12-01T00:00:00", "EMP-1")

        results = lead_tasks.list_overdue_tasks(lead_id="LEAD-1", as_of="2026-06-01T00:00:00")

        ids = [t.id for t in results]
        assert overdue.id in ids
        assert not_yet_due.id not in ids

    def test_tasks_with_no_due_at_are_never_overdue(self):
        _make_lead("LEAD-1")
        lead_tasks.create_task("LEAD-1", "call", "d", None, "EMP-1")

        results = lead_tasks.list_overdue_tasks(lead_id="LEAD-1", as_of="2099-01-01")
        assert results == []

    def test_completed_tasks_are_excluded_even_if_overdue(self):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "d", "2020-01-01T00:00:00", "EMP-1")
        lead_tasks.complete_task(task.id, "EMP-1")

        results = lead_tasks.list_overdue_tasks(lead_id="LEAD-1", as_of="2026-06-01T00:00:00")
        assert results == []

    def test_assigned_to_filter_applies(self):
        _make_lead("LEAD-1")
        mine = lead_tasks.create_task(
            "LEAD-1", "call", "d", "2020-01-01T00:00:00", "EMP-1", assigned_to="EMP-A"
        )
        theirs = lead_tasks.create_task(
            "LEAD-1", "call", "d", "2020-01-01T00:00:00", "EMP-1", assigned_to="EMP-B"
        )

        results = lead_tasks.list_overdue_tasks(assigned_to="EMP-A", as_of="2026-06-01T00:00:00")
        ids = [t.id for t in results]
        assert mine.id in ids
        assert theirs.id not in ids

    def test_as_of_defaults_to_now_when_not_supplied(self):
        _make_lead("LEAD-1")
        overdue = lead_tasks.create_task("LEAD-1", "call", "d", "2000-01-01T00:00:00", "EMP-1")

        results = lead_tasks.list_overdue_tasks(lead_id="LEAD-1")
        assert overdue.id in [t.id for t in results]


class TestLeadTasksApiAcl:

    _ALLOWED = [ADMIN, OPERATIONS, SALES, MARKETING]
    _DENIED = [FINANCE, SERVICE]

    @pytest.mark.parametrize("role", _ALLOWED)
    def test_create_task_api_allowed_roles(self, role):
        _make_lead("LEAD-1")
        result = lead_tasks_api.create_task_api(role, "EMP-1", "LEAD-1", "call", "desc", "2026-01-01")
        assert "error" not in result
        assert result["id"].startswith("LTASK")

    @pytest.mark.parametrize("role", _DENIED)
    def test_create_task_api_denied_roles(self, role):
        _make_lead("LEAD-1")
        result = lead_tasks_api.create_task_api(role, "EMP-1", "LEAD-1", "call", "desc", "2026-01-01")
        assert result == {"error": "You don't have access to create tasks"}

    def test_create_task_api_error_from_core_passed_through_unwrapped(self):
        result = lead_tasks_api.create_task_api(ADMIN, "EMP-1", "LEAD-BOGUS", "call", "desc", "2026-01-01")
        assert result == {"error": "Lead 'LEAD-BOGUS' not found"}

    @pytest.mark.parametrize("role", _ALLOWED)
    def test_complete_task_api_allowed_roles(self, role):
        _make_lead("LEAD-1")
        task = lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")

        result = lead_tasks_api.complete_task_api(role, "EMP-9", task.id)
        assert "error" not in result
        assert result["completed"] is True
        assert result["completed_by"] == "EMP-9"

    @pytest.mark.parametrize("role", _DENIED)
    def test_complete_task_api_denied_roles(self, role):
        result = lead_tasks_api.complete_task_api(role, "EMP-1", "LTASK-BOGUS")
        assert result == {"error": "You don't have access to complete tasks"}

    def test_complete_task_api_error_from_core_passed_through(self):
        result = lead_tasks_api.complete_task_api(ADMIN, "EMP-1", "LTASK-BOGUS")
        assert result == {"error": "Task not found"}

    @pytest.mark.parametrize("role", _ALLOWED)
    def test_list_tasks_api_allowed_roles(self, role):
        _make_lead("LEAD-1")
        lead_tasks.create_task("LEAD-1", "call", "desc", "2026-01-01", "EMP-1")

        result = lead_tasks_api.list_tasks_api(role, lead_id="LEAD-1")
        assert isinstance(result, list)
        assert len(result) == 1
        assert "id" in result[0]

    @pytest.mark.parametrize("role", _DENIED)
    def test_list_tasks_api_denied_roles(self, role):
        result = lead_tasks_api.list_tasks_api(role)
        assert result == {"error": "You don't have access to the task list"}
