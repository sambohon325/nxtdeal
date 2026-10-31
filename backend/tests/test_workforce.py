"""
Tests for core/workforce.py / core/workforce_api.py -- Operations' Workforce
Management item: Directory, Shift Scheduling, Time-Off Requests (with a real
tier-gated approval chain), Coverage conflict detection, and Workforce
Performance composition.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, EMPLOYEE_SHIFT, TIME_OFF_REQUEST
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import workforce
from core.workforce import (
    get_directory,
    schedule_shift,
    complete_shift,
    mark_no_show,
    cancel_shift,
    list_shifts,
    request_time_off,
    approve_time_off,
    deny_time_off,
    cancel_time_off,
    list_time_off,
    get_coverage_for_date,
    get_workforce_performance,
    get_workforce_overview,
    SHIFT_STATUSES,
)
from core import workforce_api
from core.workforce_api import (
    get_workforce_overview_api,
    get_directory_api,
    get_coverage_api,
    get_performance_api,
    list_shifts_api,
    schedule_shift_api,
    complete_shift_api,
    mark_no_show_api,
    cancel_shift_api,
    list_time_off_api,
    request_time_off_api,
    approve_time_off_api,
    deny_time_off_api,
    cancel_time_off_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(workforce, "save_graph", lambda filepath: None)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
MUTATE_ROLES = (ADMIN, OPERATIONS)
NON_MUTATE_ROLES = (SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _employee(employee_id, first="Jane", last="Doe", department="Sales", title="Sales Associate"):
    ledger.add_entity(Entity(id=employee_id, entity_type=EMPLOYEE, attributes={
        "FirstName": first, "LastName": last, "Department": department, "Title": title,
    }))


STAFF_EMP = "EMP-STAFF"
MANAGER_EMP = "EMP-MGR"
EXEC_EMP = "EMP-EXEC"


def _seed_tiers():
    _employee(STAFF_EMP, first="Sam", last="Staff", title="Sales Associate")
    _employee(MANAGER_EMP, first="Mia", last="Manager", title="Sales Manager")
    _employee(EXEC_EMP, first="Gary", last="GM", title="General Manager")


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------

class TestGetDirectory:

    def test_no_employees(self):
        result = get_directory()
        assert result["total"] == 0
        assert result["employees"] == []

    def test_all_employees_included_and_sorted(self):
        _employee("EMP-1", first="Zoe", last="Zebra", department="Sales", title="Sales Associate")
        _employee("EMP-2", first="Adam", last="Ant", department="Sales", title="Sales Manager")
        result = get_directory()
        assert result["total"] == 2
        names = [e["name"] for e in result["employees"]]
        assert names == ["Adam Ant", "Zoe Zebra"]

    def test_department_filter(self):
        _employee("EMP-1", department="Sales")
        _employee("EMP-2", department="Service")
        result = get_directory(department="Service")
        assert result["total"] == 1
        assert result["employees"][0]["id"] == "EMP-2"

    def test_by_tier_breakdown(self):
        _seed_tiers()
        result = get_directory()
        assert result["by_tier"]["staff"] == 1
        assert result["by_tier"]["manager"] == 1
        assert result["by_tier"]["executive"] == 1

    def test_by_department_breakdown_uses_unknown_bucket(self):
        ledger.add_entity(Entity(id="EMP-1", entity_type=EMPLOYEE, attributes={"FirstName": "No", "LastName": "Dept"}))
        result = get_directory()
        assert result["by_department"]["Unknown"] == 1


# ---------------------------------------------------------------------------
# Shift Scheduling
# ---------------------------------------------------------------------------

class TestScheduleShift:

    def test_creates_real_shift_entity(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "EMP-CREATOR")
        assert shift.entity_type == EMPLOYEE_SHIFT
        assert shift.attributes["status"] == "scheduled"
        assert shift.attributes["employee_id"] == STAFF_EMP
        assert shift.attributes["status_history"][0]["status"] == "scheduled"

    def test_unknown_employee_rejected(self):
        result = schedule_shift("EMP-GHOST", "2026-08-01", "09:00", "17:00", "Sales", "EMP-CREATOR")
        assert "error" in result

    def test_department_defaults_to_employee_department_when_omitted(self):
        _employee(STAFF_EMP, department="Service")
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", None, "EMP-CREATOR")
        assert shift.attributes["department"] == "Service"


class TestShiftStatusLifecycle:

    def _new_shift(self):
        _employee(STAFF_EMP)
        return schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "EMP-CREATOR")

    def test_complete_shift(self):
        shift = self._new_shift()
        result = complete_shift(shift.id, "EMP-CREATOR")
        assert result.attributes["status"] == "completed"
        assert result.attributes["status_history"][-1]["status"] == "completed"

    def test_mark_no_show(self):
        shift = self._new_shift()
        result = mark_no_show(shift.id, "EMP-CREATOR")
        assert result.attributes["status"] == "no_show"

    def test_cancel_shift(self):
        shift = self._new_shift()
        result = cancel_shift(shift.id, "EMP-CREATOR")
        assert result.attributes["status"] == "cancelled"

    def test_cannot_double_complete(self):
        shift = self._new_shift()
        complete_shift(shift.id, "EMP-CREATOR")
        result = complete_shift(shift.id, "EMP-CREATOR")
        assert "error" in result

    def test_cannot_change_from_no_show(self):
        shift = self._new_shift()
        mark_no_show(shift.id, "EMP-CREATOR")
        result = cancel_shift(shift.id, "EMP-CREATOR")
        assert "error" in result

    def test_unknown_shift_id_rejected(self):
        result = complete_shift("SHIFT-GHOST", "EMP-CREATOR")
        assert "error" in result

    def test_all_shift_statuses_are_real(self):
        assert SHIFT_STATUSES == ("scheduled", "completed", "no_show", "cancelled")


class TestListShifts:

    def test_filters_by_employee_department_date_status(self):
        _employee("EMP-1", department="Sales")
        _employee("EMP-2", department="Service")
        schedule_shift("EMP-1", "2026-08-01", "09:00", "17:00", "Sales", "creator")
        schedule_shift("EMP-2", "2026-08-05", "09:00", "17:00", "Service", "creator")

        assert len(list_shifts(employee_id="EMP-1")) == 1
        assert len(list_shifts(department="Service")) == 1
        assert len(list_shifts(date_from="2026-08-03")) == 1
        assert len(list_shifts(date_to="2026-08-03")) == 1
        assert len(list_shifts(status="scheduled")) == 2

    def test_sorted_by_date_then_start_time(self):
        _employee("EMP-1")
        schedule_shift("EMP-1", "2026-08-02", "12:00", "20:00", "Sales", "creator")
        schedule_shift("EMP-1", "2026-08-01", "09:00", "17:00", "Sales", "creator")
        shifts = list_shifts()
        assert [s.attributes["shift_date"] for s in shifts] == ["2026-08-01", "2026-08-02"]


# ---------------------------------------------------------------------------
# Time-Off Requests
# ---------------------------------------------------------------------------

class TestRequestTimeOff:

    def test_creates_real_pending_request(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        assert req.entity_type == TIME_OFF_REQUEST
        assert req.attributes["status"] == "pending"
        assert req.attributes["requested_by"] == STAFF_EMP

    def test_created_by_defaults_to_employee_when_omitted(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation", created_by=None)
        assert req.attributes["requested_by"] == STAFF_EMP

    def test_custom_created_by_is_kept(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation", created_by="EMP-ADMIN")
        assert req.attributes["requested_by"] == "EMP-ADMIN"

    def test_unknown_employee_rejected(self):
        result = request_time_off("EMP-GHOST", "2026-08-10", "2026-08-15", "Vacation")
        assert "error" in result

    def test_end_before_start_rejected(self):
        _employee(STAFF_EMP)
        result = request_time_off(STAFF_EMP, "2026-08-15", "2026-08-10", "Vacation")
        assert "error" in result

    def test_missing_dates_rejected(self):
        _employee(STAFF_EMP)
        result = request_time_off(STAFF_EMP, None, "2026-08-15", "Vacation")
        assert "error" in result


class TestDecideTimeOff:

    def _new_request(self):
        _seed_tiers()
        return request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")

    def test_staff_tier_decider_denied(self):
        req = self._new_request()
        result = approve_time_off(req.id, STAFF_EMP)
        assert "error" in result
        assert "manager-or-above" in result["error"] or "manager" in result["error"].lower()

    def test_manager_tier_decider_can_approve(self):
        req = self._new_request()
        result = approve_time_off(req.id, MANAGER_EMP, note="Enjoy!")
        assert result.attributes["status"] == "approved"
        assert result.attributes["decided_by"] == MANAGER_EMP
        assert result.attributes["decision_note"] == "Enjoy!"

    def test_executive_tier_decider_can_deny(self):
        req = self._new_request()
        result = deny_time_off(req.id, EXEC_EMP, note="Staffing conflict")
        assert result.attributes["status"] == "denied"
        assert result.attributes["decided_by"] == EXEC_EMP

    def test_unknown_decider_denied(self):
        req = self._new_request()
        result = approve_time_off(req.id, "EMP-GHOST")
        assert "error" in result

    def test_cannot_decide_already_decided_request(self):
        req = self._new_request()
        approve_time_off(req.id, MANAGER_EMP)
        result = deny_time_off(req.id, MANAGER_EMP)
        assert "error" in result

    def test_unknown_request_id_rejected(self):
        _seed_tiers()
        result = approve_time_off("PTO-GHOST", MANAGER_EMP)
        assert "error" in result


class TestCancelTimeOff:

    def test_cancel_from_pending(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = cancel_time_off(req.id, STAFF_EMP)
        assert result.attributes["status"] == "cancelled"

    def test_cancel_from_approved(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        approve_time_off(req.id, MANAGER_EMP)
        result = cancel_time_off(req.id, STAFF_EMP)
        assert result.attributes["status"] == "cancelled"

    def test_cannot_cancel_denied_request(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        deny_time_off(req.id, MANAGER_EMP)
        result = cancel_time_off(req.id, STAFF_EMP)
        assert "error" in result

    def test_unknown_request_id_rejected(self):
        result = cancel_time_off("PTO-GHOST", STAFF_EMP)
        assert "error" in result


class TestListTimeOff:

    def test_filters_by_employee_and_status(self):
        _seed_tiers()
        req1 = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        request_time_off(MANAGER_EMP, "2026-09-01", "2026-09-05", "Vacation")
        approve_time_off(req1.id, MANAGER_EMP)

        assert len(list_time_off(employee_id=STAFF_EMP)) == 1
        assert len(list_time_off(status="approved")) == 1
        assert len(list_time_off(status="pending")) == 1
        assert len(list_time_off()) == 2


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

class TestGetCoverageForDate:

    def test_no_shifts_no_conflicts(self):
        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 0
        assert result["conflict_count"] == 0

    def test_shift_with_no_time_off_is_scheduled_not_conflict(self):
        _employee(STAFF_EMP)
        schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 1
        assert result["conflict_count"] == 0

    def test_shift_plus_approved_time_off_is_a_real_conflict(self):
        _seed_tiers()
        schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        req = request_time_off(STAFF_EMP, "2026-07-30", "2026-08-05", "Vacation")
        approve_time_off(req.id, MANAGER_EMP)

        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 0
        assert result["conflict_count"] == 1
        assert result["on_approved_time_off_count"] == 1

    def test_pending_time_off_does_not_cause_conflict(self):
        _employee(STAFF_EMP)
        schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        request_time_off(STAFF_EMP, "2026-07-30", "2026-08-05", "Vacation")  # still pending
        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 1
        assert result["conflict_count"] == 0

    def test_cancelled_shift_excluded_from_both_lists(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        cancel_shift(shift.id, "creator")
        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 0
        assert result["conflict_count"] == 0

    def test_completed_or_no_show_shift_still_counted(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        complete_shift(shift.id, "creator")
        result = get_coverage_for_date("2026-08-01")
        assert result["scheduled_count"] == 1

    def test_defaults_to_today_when_no_date_given(self):
        from datetime import date
        result = get_coverage_for_date()
        assert result["date"] == date.today().isoformat()

    def test_time_off_outside_range_does_not_conflict(self):
        _seed_tiers()
        schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        req = request_time_off(STAFF_EMP, "2026-09-01", "2026-09-05", "Vacation")
        approve_time_off(req.id, MANAGER_EMP)
        result = get_coverage_for_date("2026-08-01")
        assert result["conflict_count"] == 0


# ---------------------------------------------------------------------------
# Workforce Performance / Overview composition
# ---------------------------------------------------------------------------

class TestGetWorkforcePerformance:

    def test_admin_gets_real_credential_coverage(self, monkeypatch):
        monkeypatch.setattr(workforce, "get_workload_dashboard", lambda: {"stub": True}, raising=False)
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api
        import core.workflow_tab_data as wtd

        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda role: {"values": []})
        monkeypatch.setattr(wtd, "administration_onboarding_roster", lambda role: {"roster": []})

        result = get_workforce_performance(ADMIN)
        assert result["credential_coverage"] == {"roster": []}
        assert result["employee_value"] == {"values": []}
        assert "hours_worked" in result["not_yet_tracked"]
        assert "pto_balance_accrual" in result["not_yet_tracked"]

    def test_non_admin_ops_role_gets_denied_credential_coverage(self, monkeypatch):
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api

        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda role: {"values": []})

        result = get_workforce_performance(SALES)
        assert "error" in result["credential_coverage"]


class TestGetWorkforceOverview:

    def test_composes_directory_coverage_pending_time_off_and_performance(self, monkeypatch):
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api

        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda role: {"values": []})

        _seed_tiers()
        result = get_workforce_overview(ADMIN)
        assert result["directory"]["total"] == 3
        assert "coverage_today" in result
        assert "pending_time_off_count" in result
        assert "upcoming_shift_count" in result
        assert "performance" in result

    def test_pending_time_off_is_capped_at_25_in_the_preview_list(self, monkeypatch):
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api
        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda role: {"values": []})

        _employee(STAFF_EMP)
        for i in range(30):
            request_time_off(STAFF_EMP, "2026-08-01", "2026-08-02", f"reason {i}")

        result = get_workforce_overview(ADMIN)
        assert result["pending_time_off_count"] == 30
        assert len(result["pending_time_off"]) == 25


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetWorkforceOverviewApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api
        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda r: {"values": []})
        result = get_workforce_overview_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_workforce_overview_api("NOT_A_REAL_ROLE")
        assert "error" in result


class TestGetDirectoryApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = get_directory_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_directory_api("NOT_A_REAL_ROLE")
        assert "error" in result

    def test_department_filter_threaded_through(self):
        _employee("EMP-1", department="Sales")
        _employee("EMP-2", department="Service")
        result = get_directory_api(ADMIN, department="Sales")
        assert result["total"] == 1


class TestGetCoverageApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = get_coverage_api(role, "2026-08-01")
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_coverage_api("NOT_A_REAL_ROLE", "2026-08-01")
        assert "error" in result


class TestGetPerformanceApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        import core.workload_dashboard_api as wl_api
        import core.employee_value_api as ev_api
        monkeypatch.setattr(wl_api, "get_dashboard", lambda: {"employees": []})
        monkeypatch.setattr(ev_api, "list_employee_values_api", lambda r: {"values": []})
        result = get_performance_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_performance_api("NOT_A_REAL_ROLE")
        assert "error" in result


class TestListShiftsApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = list_shifts_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = list_shifts_api("NOT_A_REAL_ROLE")
        assert "error" in result


class TestScheduleShiftApi:

    @pytest.mark.parametrize("role", MUTATE_ROLES)
    def test_mutate_role_allowed(self, role):
        _employee(STAFF_EMP)
        result = schedule_shift_api(role, STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        assert "error" not in result
        assert result["status"] == "scheduled"

    @pytest.mark.parametrize("role", NON_MUTATE_ROLES)
    def test_non_mutate_role_denied(self, role):
        _employee(STAFF_EMP)
        result = schedule_shift_api(role, STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        assert "error" in result


class TestCompleteShiftApi:

    def test_admin_allowed(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = complete_shift_api(ADMIN, shift.id, "creator")
        assert result["status"] == "completed"

    def test_sales_denied(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = complete_shift_api(SALES, shift.id, "creator")
        assert "error" in result


class TestMarkNoShowApi:

    def test_operations_allowed(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = mark_no_show_api(OPERATIONS, shift.id, "creator")
        assert result["status"] == "no_show"


class TestCancelShiftApi:

    def test_admin_allowed(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = cancel_shift_api(ADMIN, shift.id, "creator")
        assert result["status"] == "cancelled"

    def test_marketing_denied(self):
        _employee(STAFF_EMP)
        shift = schedule_shift(STAFF_EMP, "2026-08-01", "09:00", "17:00", "Sales", "creator")
        result = cancel_shift_api(MARKETING, shift.id, "creator")
        assert "error" in result


class TestListTimeOffApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = list_time_off_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = list_time_off_api("NOT_A_REAL_ROLE")
        assert "error" in result


class TestRequestTimeOffApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_can_submit(self, role):
        _employee(STAFF_EMP)
        result = request_time_off_api(role, STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        assert "error" not in result

    def test_unknown_role_denied(self):
        _employee(STAFF_EMP)
        result = request_time_off_api("NOT_A_REAL_ROLE", STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        assert "error" in result


class TestApproveTimeOffApi:

    def test_admin_role_with_manager_tier_decider_succeeds(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = approve_time_off_api(ADMIN, req.id, MANAGER_EMP)
        assert result["status"] == "approved"

    def test_admin_role_with_staff_tier_decider_still_denied_by_inner_tier_gate(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = approve_time_off_api(ADMIN, req.id, STAFF_EMP)
        assert "error" in result

    def test_non_mutate_role_denied_before_reaching_tier_check(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = approve_time_off_api(SALES, req.id, EXEC_EMP)
        assert "error" in result


class TestDenyTimeOffApi:

    def test_operations_role_with_executive_tier_decider_succeeds(self):
        _seed_tiers()
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = deny_time_off_api(OPERATIONS, req.id, EXEC_EMP, note="No coverage")
        assert result["status"] == "denied"
        assert result["decision_note"] == "No coverage"


class TestCancelTimeOffApi:

    def test_admin_allowed(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = cancel_time_off_api(ADMIN, req.id, STAFF_EMP)
        assert result["status"] == "cancelled"

    def test_service_denied(self):
        _employee(STAFF_EMP)
        req = request_time_off(STAFF_EMP, "2026-08-10", "2026-08-15", "Vacation")
        result = cancel_time_off_api(SERVICE, req.id, STAFF_EMP)
        assert "error" in result
