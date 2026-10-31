"""Tests for core/strategic_planning.py -- the Strategic Objectives/Initiatives
module (Readiness rebuild). Real, ledger-backed quarter-pace computation for
Sales/Service/Marketing objectives, an honest manual-self-report fallback for
every other department, tracking-type-specific initiative progress
(website_launch/gps_rollout/manual), a validated initiative status state
machine, and the one-way sync-to-monthly-goal coupling with
core/system_config.py's department_goals.

Ledger-touching category -- needs fresh_ledger + no_real_save fixtures."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.strategic_planning as sp
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, SERVICE_RECORD, LEAD, WEBSITE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_save(monkeypatch):
    monkeypatch.setattr(sp, "save_graph", lambda path: None)


def _make_vehicle(vid, date_sold):
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"DateSold": date_sold}))


def _make_service_record(rid, service_date, cost, parts_cost):
    ledger.add_entity(Entity(
        id=rid,
        entity_type=SERVICE_RECORD,
        attributes={"ServiceDate": service_date, "Cost": cost, "PartsCost": parts_cost},
    ))


def _make_lead(lid, created_date):
    ledger.add_entity(Entity(id=lid, entity_type=LEAD, attributes={"CreatedDate": created_date}))


# ---------------------------------------------------------------------------
# Quarter helpers (sanity-check the assumed Q1-Q4 -> month-range mapping
# before relying on it in every other test below)
# ---------------------------------------------------------------------------


class TestQuarterHelpers:

    def test_quarter_bounds_q1(self):
        start, end = sp._quarter_bounds("Q1", 2026)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_quarter_bounds_q3(self):
        start, end = sp._quarter_bounds("Q3", 2026)
        assert start == date(2026, 7, 1)
        assert end == date(2026, 9, 30)

    def test_quarter_of_resolves_correctly(self):
        assert sp._quarter_of(date(2026, 8, 15)) == "Q3"
        assert sp._quarter_of(date(2026, 1, 1)) == "Q1"
        assert sp._quarter_of(date(2026, 12, 31)) == "Q4"


# ---------------------------------------------------------------------------
# get_quarter_pace()
# ---------------------------------------------------------------------------


class TestGetQuarterPace:

    def test_unsupported_department_returns_none(self):
        assert sp.get_quarter_pace("inventory", "Q3", 2026, today=date(2026, 8, 1)) is None

    def test_sales_counts_real_vehicle_sales_in_range(self):
        _make_vehicle("VEH-1", "2026-07-05")
        _make_vehicle("VEH-2", "2026-08-01")
        _make_vehicle("VEH-3", "2026-06-15")  # before the quarter -- excluded

        result = sp.get_quarter_pace("sales", "Q3", 2026, today=date(2026, 8, 15))

        assert result["actual_to_date"] == 2
        assert result["basis"] == "real"
        assert result["phase"] == "in_progress"

    def test_service_sums_real_gross_in_range(self):
        _make_service_record("SRV-1", "2026-07-10", 500.0, 200.0)
        _make_service_record("SRV-2", "2026-07-20", 300.0, 100.0)

        result = sp.get_quarter_pace("service", "Q3", 2026, today=date(2026, 8, 1))

        assert result["actual_to_date"] == 500.0

    def test_marketing_counts_real_leads_in_range(self):
        _make_lead("LEAD-1", "2026-07-01")
        _make_lead("LEAD-2", "2026-07-15")
        _make_lead("LEAD-3", "2026-10-01")  # outside the quarter

        result = sp.get_quarter_pace("marketing", "Q3", 2026, today=date(2026, 8, 1))

        assert result["actual_to_date"] == 2

    def test_future_quarter_reports_future_phase_zeroed(self):
        result = sp.get_quarter_pace("sales", "Q3", 2026, today=date(2026, 3, 1))

        assert result["phase"] == "future"
        assert result["actual_to_date"] == 0

    def test_complete_quarter_reports_complete_phase(self):
        _make_vehicle("VEH-1", "2026-07-05")

        result = sp.get_quarter_pace("sales", "Q3", 2026, today=date(2026, 10, 5))

        assert result["phase"] == "complete"
        assert result["actual_to_date"] == 1

    def test_projected_total_extrapolates_from_actual(self):
        for i in range(10):
            _make_vehicle(f"VEH-{i}", "2026-07-05")

        result = sp.get_quarter_pace("sales", "Q3", 2026, today=date(2026, 7, 10))

        assert result["projected_quarter_total"] is not None
        assert result["projected_quarter_total"] >= result["actual_to_date"]


# ---------------------------------------------------------------------------
# compute_objective_status() -- real-ledger-department branch
# ---------------------------------------------------------------------------


class TestComputeObjectiveStatusRealLedger:

    def test_cancelled_objective(self):
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 10, "is_cancelled": True}

        result = sp.compute_objective_status(attrs, today=date(2026, 8, 1))

        assert result["status"] == "cancelled"
        assert result["current_value"] is None

    def test_future_phase_is_not_started(self):
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 10, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 3, 1))

        assert result["status"] == "not_started"

    def test_no_target_value(self):
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": None, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 8, 1))

        assert result["status"] == "no_target"

    def test_complete_phase_achieved(self):
        _make_vehicle("VEH-1", "2026-07-05")
        _make_vehicle("VEH-2", "2026-08-01")
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 2, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 10, 5))

        assert result["status"] == "achieved"
        assert result["current_value"] == 2
        assert result["pct_of_target"] == 100.0

    def test_complete_phase_missed(self):
        _make_vehicle("VEH-1", "2026-07-05")
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 5, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 10, 5))

        assert result["status"] == "missed"

    def test_in_progress_on_track(self):
        for i in range(40):
            _make_vehicle(f"VEH-{i}", "2026-07-05")
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 50, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 7, 15))

        assert result["status"] == "on_track"
        assert result["current_value_basis"] == "real"

    def test_in_progress_at_risk(self):
        for i in range(9):
            _make_vehicle(f"VEH-{i}", "2026-09-01")
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 10, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert result["status"] == "at_risk"

    def test_in_progress_behind(self):
        for i in range(5):
            _make_vehicle(f"VEH-{i}", "2026-09-01")
        attrs = {"department": "Sales", "quarter": "Q3", "year": 2026,
                  "target_value": 10, "is_cancelled": False}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert result["status"] == "behind"


# ---------------------------------------------------------------------------
# compute_objective_status() -- manual self-report fallback branch
# ---------------------------------------------------------------------------


class TestComputeObjectiveStatusManualFallback:

    def test_no_manual_progress_is_no_data(self):
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "target_value": None, "is_cancelled": False,
                  "manual_progress_pct": None}

        result = sp.compute_objective_status(attrs, today=date(2026, 8, 1))

        assert result["status"] == "no_data"

    def test_future_phase_is_not_started(self):
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": 0}

        result = sp.compute_objective_status(attrs, today=date(2026, 3, 1))

        assert result["status"] == "not_started"

    def test_complete_phase_achieved(self):
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": 100}

        result = sp.compute_objective_status(attrs, today=date(2026, 10, 5))

        assert result["status"] == "achieved"

    def test_complete_phase_missed(self):
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": 50}

        result = sp.compute_objective_status(attrs, today=date(2026, 10, 5))

        assert result["status"] == "missed"

    def test_in_progress_on_track_at_or_above_expected(self):
        expected_pct, _phase = sp._manual_expected_pct("Q3", 2026, today=date(2026, 9, 28))
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": 100.0}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert 100.0 >= expected_pct
        assert result["status"] == "on_track"

    def test_in_progress_at_risk_between_seventy_and_expected(self):
        expected_pct, _phase = sp._manual_expected_pct("Q3", 2026, today=date(2026, 9, 28))
        manual_pct = round(expected_pct * 0.75, 1)
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": manual_pct}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert result["status"] == "at_risk"

    def test_in_progress_behind_below_seventy_percent_of_expected(self):
        expected_pct, _phase = sp._manual_expected_pct("Q3", 2026, today=date(2026, 9, 28))
        manual_pct = round(expected_pct * 0.3, 1)
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": manual_pct}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert result["status"] == "behind"

    def test_reported_basis_is_manual(self):
        attrs = {"department": "Finance", "quarter": "Q3", "year": 2026,
                  "is_cancelled": False, "manual_progress_pct": 42}

        result = sp.compute_objective_status(attrs, today=date(2026, 9, 28))

        assert result["current_value_basis"] == "manual"
        assert result["current_value"] == 42


# ---------------------------------------------------------------------------
# Objective CRUD
# ---------------------------------------------------------------------------


class TestCreateObjective:

    def test_rejects_bad_quarter(self):
        result = sp.create_objective("Q9", 2026, "Sales", "Grow units", "EMP-1")
        assert "error" in result

    def test_rejects_bad_year(self):
        result = sp.create_objective("Q3", "not-a-year", "Sales", "Grow units", "EMP-1")
        assert "error" in result

    def test_rejects_bad_department(self):
        result = sp.create_objective("Q3", 2026, "NotADepartment", "Grow units", "EMP-1")
        assert "error" in result

    def test_rejects_empty_title(self):
        result = sp.create_objective("Q3", 2026, "Sales", "", "EMP-1")
        assert "error" in result

    def test_creates_real_objective(self):
        result = sp.create_objective(
            "Q3", 2026, "Sales", "Grow unit sales", "EMP-1",
            description="Push volume", target_value=100, unit="units",
            budget_allocated=5000,
        )

        assert "error" not in result
        assert result["id"].startswith("OBJ-")
        assert result["department"] == "Sales"
        assert result["quarter"] == "Q3"
        assert result["year"] == 2026
        assert result["title"] == "Grow unit sales"
        assert result["target_value"] == 100
        assert result["synced_monthly_goal"] is False

    def test_persists_on_the_ledger(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Grow unit sales", "EMP-1")

        fetched = sp.get_objective(created["id"])

        assert fetched["id"] == created["id"]


class TestGetObjective:

    def test_unknown_id_is_error(self):
        result = sp.get_objective("OBJ-99999")
        assert "error" in result


class TestListObjectives:

    def test_filters_by_department(self):
        sp.create_objective("Q3", 2026, "Sales", "Sales goal", "EMP-1")
        sp.create_objective("Q3", 2026, "Service", "Service goal", "EMP-1")

        result = sp.list_objectives(department="Sales")["objectives"]

        assert all(o["department"] == "Sales" for o in result)
        assert len(result) == 1

    def test_filters_by_quarter_and_year(self):
        sp.create_objective("Q3", 2026, "Sales", "Q3 goal", "EMP-1")
        sp.create_objective("Q4", 2026, "Sales", "Q4 goal", "EMP-1")

        result = sp.list_objectives(quarter="Q3", year=2026)["objectives"]

        assert len(result) == 1
        assert result[0]["title"] == "Q3 goal"


class TestUpdateObjective:

    def test_updates_editable_fields_only(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Original title", "EMP-1")

        updated = sp.update_objective(created["id"], "EMP-2", title="New title",
                                       target_value=200)

        assert updated["title"] == "New title"
        assert updated["target_value"] == 200
        assert updated["department"] == "Sales"

    def test_unknown_id_is_error(self):
        result = sp.update_objective("OBJ-99999", "EMP-1", title="x")
        assert "error" in result


class TestUpdateObjectiveProgress:

    def test_rejects_out_of_range_pct(self):
        created = sp.create_objective("Q3", 2026, "Finance", "Manual goal", "EMP-1")

        result = sp.update_objective_progress(created["id"], 150, "EMP-1")

        assert "error" in result

    def test_accepts_valid_pct(self):
        created = sp.create_objective("Q3", 2026, "Finance", "Manual goal", "EMP-1")

        result = sp.update_objective_progress(created["id"], 42, "EMP-1")

        assert "error" not in result
        assert result["manual_progress_pct"] == 42


class TestUpdateObjectiveBudget:

    def test_always_attaches_budget_spent_note(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1",
                                       budget_allocated=1000)

        result = sp.update_objective_budget(created["id"], "EMP-1", budget_spent=250)

        assert "budget_spent_note" in result
        assert result["budget_spent"] == 250


class TestCancelReopenObjective:

    def test_cancel_sets_is_cancelled(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1")

        result = sp.cancel_objective(created["id"], "EMP-1")

        assert result["status"] == "cancelled"

    def test_reopen_clears_cancellation(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1",
                                       target_value=10)
        sp.cancel_objective(created["id"], "EMP-1")

        result = sp.reopen_objective(created["id"], "EMP-1")

        assert result["status"] != "cancelled"


class TestSyncObjectiveToMonthlyGoal:

    def test_rejects_non_goal_tracked_department(self):
        created = sp.create_objective("Q3", 2026, "Inventory", "Goal", "EMP-1",
                                       target_value=90)

        result = sp.sync_objective_to_monthly_goal(created["id"], "EMP-1")

        assert "error" in result

    def test_rejects_missing_target_value(self):
        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1")

        result = sp.sync_objective_to_monthly_goal(created["id"], "EMP-1")

        assert "error" in result

    def test_success_divides_target_by_three_and_calls_set_department_goal(self, monkeypatch):
        calls = []

        def _fake_set_department_goal(*args, **kwargs):
            calls.append((args, kwargs))
            return {"success": True}

        monkeypatch.setattr(sp, "set_department_goal", _fake_set_department_goal)

        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1",
                                       target_value=90)

        result = sp.sync_objective_to_monthly_goal(created["id"], "EMP-1")

        assert "error" not in result
        assert result["synced_monthly_goal"] is True
        assert result["synced_monthly_target"] == 30.0
        assert len(calls) == 1

    def test_propagates_error_from_set_department_goal(self, monkeypatch):
        def _fake_set_department_goal(*args, **kwargs):
            return {"error": "goal rejected"}

        monkeypatch.setattr(sp, "set_department_goal", _fake_set_department_goal)

        created = sp.create_objective("Q3", 2026, "Sales", "Goal", "EMP-1",
                                       target_value=90)

        result = sp.sync_objective_to_monthly_goal(created["id"], "EMP-1")

        assert "error" in result


class TestGetQuarterlyRollup:

    def test_groups_by_department_and_counts_status(self):
        sp.create_objective("Q3", 2026, "Sales", "Sales goal", "EMP-1")
        sp.create_objective("Q3", 2026, "Service", "Service goal", "EMP-1")

        result = sp.get_quarterly_rollup(quarter="Q3", year=2026)

        assert "Sales" in result["by_department"] or "Sales" in str(result)


# ---------------------------------------------------------------------------
# Initiative CRUD
# ---------------------------------------------------------------------------


class TestCreateInitiative:

    def test_rejects_empty_name(self):
        result = sp.create_initiative("", "Sales", "manual", "EMP-1")
        assert "error" in result

    def test_rejects_bad_department(self):
        result = sp.create_initiative("New thing", "NotADept", "manual", "EMP-1")
        assert "error" in result

    def test_rejects_bad_tracking_type(self):
        result = sp.create_initiative("New thing", "Sales", "not_a_type", "EMP-1")
        assert "error" in result

    def test_website_launch_requires_linked_entity_id(self):
        result = sp.create_initiative("Launch new site", "Marketing", "website_launch",
                                       "EMP-1")
        assert "error" in result

    def test_website_launch_requires_real_website(self, monkeypatch):
        monkeypatch.setattr(sp, "get_website", lambda website_id: None)

        result = sp.create_initiative("Launch new site", "Marketing", "website_launch",
                                       "EMP-1", linked_entity_id="SITE-999")

        assert "error" in result

    def test_website_launch_succeeds_with_real_website(self, monkeypatch):
        monkeypatch.setattr(
            sp, "get_website",
            lambda website_id: Entity(id=website_id, entity_type=WEBSITE,
                                       attributes={"status": "draft"}),
        )

        result = sp.create_initiative("Launch new site", "Marketing", "website_launch",
                                       "EMP-1", linked_entity_id="SITE-1")

        assert "error" not in result
        assert result["tracking_type"] == "website_launch"

    def test_gps_rollout_requires_target_metric(self):
        result = sp.create_initiative("Roll out GPS", "Operations", "gps_rollout",
                                       "EMP-1")
        assert "error" in result

    def test_gps_rollout_succeeds_with_target_metric(self):
        result = sp.create_initiative("Roll out GPS", "Operations", "gps_rollout",
                                       "EMP-1", target_metric_value=25)
        assert "error" not in result
        assert result["target_metric_value"] == 25

    def test_manual_tracking_starts_planned_with_one_history_entry(self):
        result = sp.create_initiative("New service center", "Operations", "manual",
                                       "EMP-1")

        assert result["status"] == "planned"
        assert len(result["status_history"]) == 1
        assert result["status_history"][0]["status"] == "planned"


class TestGetInitiative:

    def test_unknown_id_is_error(self):
        result = sp.get_initiative("INIT-99999")
        assert "error" in result


class TestListInitiatives:

    def test_filters_by_department(self):
        sp.create_initiative("A", "Sales", "manual", "EMP-1")
        sp.create_initiative("B", "Service", "manual", "EMP-1")

        result = sp.list_initiatives(department="Sales")["initiatives"]

        assert all(i["department"] == "Sales" for i in result)
        assert len(result) == 1

    def test_filters_by_status(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")
        sp.update_initiative_status(created["id"], "in_progress", "EMP-1")
        sp.create_initiative("B", "Sales", "manual", "EMP-1")

        result = sp.list_initiatives(status="in_progress")["initiatives"]

        assert len(result) == 1
        assert result[0]["id"] == created["id"]

    def test_filters_by_tracking_type(self):
        sp.create_initiative("A", "Sales", "manual", "EMP-1")
        sp.create_initiative("B", "Operations", "gps_rollout", "EMP-1",
                              target_metric_value=10)

        result = sp.list_initiatives(tracking_type="gps_rollout")["initiatives"]

        assert len(result) == 1
        assert result[0]["tracking_type"] == "gps_rollout"


class TestUpdateInitiativeStatus:

    def test_valid_transition_planned_to_in_progress(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")

        result = sp.update_initiative_status(created["id"], "in_progress", "EMP-1")

        assert result["status"] == "in_progress"
        assert len(result["status_history"]) == 2

    def test_valid_transition_in_progress_to_completed(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")
        sp.update_initiative_status(created["id"], "in_progress", "EMP-1")

        result = sp.update_initiative_status(created["id"], "completed", "EMP-1")

        assert result["status"] == "completed"

    def test_rejects_direct_planned_to_completed_skip(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")

        result = sp.update_initiative_status(created["id"], "completed", "EMP-1")

        assert "error" in result

    def test_rejects_transition_from_terminal_state(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")
        sp.update_initiative_status(created["id"], "in_progress", "EMP-1")
        sp.update_initiative_status(created["id"], "completed", "EMP-1")

        result = sp.update_initiative_status(created["id"], "in_progress", "EMP-1")

        assert "error" in result

    def test_rejects_invalid_status_value(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")

        result = sp.update_initiative_status(created["id"], "not_a_real_status", "EMP-1")

        assert "error" in result

    def test_cancelled_is_a_valid_off_ramp_from_planned(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1")

        result = sp.update_initiative_status(created["id"], "cancelled", "EMP-1")

        assert result["status"] == "cancelled"


class TestUpdateInitiativeProgress:

    def test_rejects_non_manual_tracking_type(self):
        created = sp.create_initiative("Roll out GPS", "Operations", "gps_rollout",
                                        "EMP-1", target_metric_value=10)

        result = sp.update_initiative_progress(created["id"], 50, "EMP-1")

        assert "error" in result

    def test_accepts_manual_tracking_type(self):
        created = sp.create_initiative("New service center", "Operations", "manual",
                                        "EMP-1")

        result = sp.update_initiative_progress(created["id"], 65, "EMP-1")

        assert "error" not in result
        assert result["manual_progress_pct"] == 65

    def test_rejects_out_of_range_pct(self):
        created = sp.create_initiative("New service center", "Operations", "manual",
                                        "EMP-1")

        result = sp.update_initiative_progress(created["id"], 150, "EMP-1")

        assert "error" in result


class TestUpdateInitiativeBudget:

    def test_always_attaches_budget_spent_note(self):
        created = sp.create_initiative("A", "Sales", "manual", "EMP-1",
                                        budget_allocated=1000)

        result = sp.update_initiative_budget(created["id"], "EMP-1", budget_spent=100)

        assert "budget_spent_note" in result
        assert result["budget_spent"] == 100


# ---------------------------------------------------------------------------
# get_initiative_progress() -- the real-vs-manual dispatcher
# ---------------------------------------------------------------------------


class TestGetInitiativeProgress:

    def test_website_launch_missing_website_is_honest_error(self, monkeypatch):
        monkeypatch.setattr(sp, "get_website", lambda website_id: None)

        attrs = {"tracking_type": "website_launch", "linked_entity_id": "SITE-999"}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] is None
        assert "error" in result

    def test_website_launch_draft_status(self, monkeypatch):
        monkeypatch.setattr(
            sp, "get_website",
            lambda website_id: Entity(id=website_id, entity_type=WEBSITE,
                                       attributes={"status": "draft"}),
        )
        monkeypatch.setattr(sp, "get_website_analytics",
                             lambda website_id: {"total_views": 0})

        attrs = {"tracking_type": "website_launch", "linked_entity_id": "SITE-1"}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] == 10.0

    def test_website_launch_published_status(self, monkeypatch):
        monkeypatch.setattr(
            sp, "get_website",
            lambda website_id: Entity(id=website_id, entity_type=WEBSITE,
                                       attributes={"status": "published"}),
        )
        monkeypatch.setattr(sp, "get_website_analytics",
                             lambda website_id: {"total_views": 100})

        attrs = {"tracking_type": "website_launch", "linked_entity_id": "SITE-1"}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] == 100.0

    def test_website_launch_analytics_failure_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(
            sp, "get_website",
            lambda website_id: Entity(id=website_id, entity_type=WEBSITE,
                                       attributes={"status": "published"}),
        )

        def _boom(website_id):
            raise RuntimeError("analytics unavailable")

        monkeypatch.setattr(sp, "get_website_analytics", _boom)

        attrs = {"tracking_type": "website_launch", "linked_entity_id": "SITE-1"}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] == 100.0

    def test_gps_rollout_computes_real_ratio(self, monkeypatch):
        monkeypatch.setattr(sp, "list_devices",
                             lambda: {"count": 5, "devices": [{"id": f"DEV-{i}"} for i in range(5)]})

        attrs = {"tracking_type": "gps_rollout", "target_metric_value": 10}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] == 50.0

    def test_gps_rollout_no_target_is_honest_none(self, monkeypatch):
        monkeypatch.setattr(sp, "list_devices",
                             lambda: {"count": 1, "devices": [{"id": "DEV-1"}]})

        attrs = {"tracking_type": "gps_rollout", "target_metric_value": None}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] is None

    def test_manual_returns_self_report_verbatim(self):
        attrs = {"tracking_type": "manual", "manual_progress_pct": 42}
        result = sp.get_initiative_progress(attrs)

        assert result["progress_pct"] == 42
        assert result["basis"] == "manual"


# ---------------------------------------------------------------------------
# get_strategic_planning_overview()
# ---------------------------------------------------------------------------


class TestGetStrategicPlanningOverview:

    def test_includes_department_options_and_tracking_catalog(self):
        result = sp.get_strategic_planning_overview(quarter="Q3", year=2026)

        assert result["department_options"] == list(sp.STRATEGIC_DEPARTMENTS)
        assert result["tracking_type_catalog"] == sp.TRACKING_TYPE_CATALOG

    def test_includes_goal_tracked_departments(self):
        result = sp.get_strategic_planning_overview(quarter="Q3", year=2026)

        assert result["goal_tracked_departments"] == list(sp.GOAL_TRACKED_DEPARTMENTS)

    def test_includes_not_yet_tracked_notes(self):
        result = sp.get_strategic_planning_overview(quarter="Q3", year=2026)

        assert "budget_ledger" in result["not_yet_tracked"]
        assert "non_goal_department_status" in result["not_yet_tracked"]

    def test_defaults_to_current_quarter_when_unspecified(self):
        result = sp.get_strategic_planning_overview()

        assert result["current_quarter"] in sp.QUARTERS
        assert isinstance(result["current_year"], int)


# ---------------------------------------------------------------------------
# Module-level catalogs -- light structural checks
# ---------------------------------------------------------------------------


class TestCatalogs:

    def test_tracking_type_catalog_has_three_entries(self):
        assert set(sp.TRACKING_TYPE_CATALOG.keys()) == {"website_launch", "gps_rollout", "manual"}

    def test_website_launch_requires_linked_entity(self):
        assert sp.TRACKING_TYPE_CATALOG["website_launch"]["requires_linked_entity_id"] is True

    def test_gps_rollout_requires_target_metric(self):
        assert sp.TRACKING_TYPE_CATALOG["gps_rollout"]["requires_target_metric"] is True

    def test_manual_requires_neither(self):
        entry = sp.TRACKING_TYPE_CATALOG["manual"]
        assert entry["requires_linked_entity_id"] is False
        assert entry["requires_target_metric"] is False

    def test_strategic_departments_are_title_case(self):
        assert "Sales" in sp.STRATEGIC_DEPARTMENTS
        assert "Company-Wide" in sp.STRATEGIC_DEPARTMENTS

    def test_goal_tracked_departments_matches_system_config(self):
        assert set(sp.GOAL_TRACKED_DEPARTMENTS) == {"sales", "service", "marketing"}
