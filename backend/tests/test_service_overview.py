"""
Test coverage for core/service_overview.py -- Service's "Overview" item (the
Command Center, Today's Risks, and per-Advisor personal dashboard), the second
slice of Service's rebuild (following the RO Workflow Engine).

Covers: get_command_center() (open_ros/waiting_approval/waiting_parts/
waiting_technician/waiting_delivery real buckets off core/repair_orders.py's
ro_stage, plus the real "Comebacks" same-VIN-within-30-days signal);
get_todays_risks() (customers_waiting, jobs_behind_schedule via
_hours_since_checkin >= 24h, techs_overloaded via core/shop_control.py's real
get_technician_utilization(), parts_delayed via a backordered parts_status,
and the honest promised_today_not_started gap); get_advisor_dashboard() (the
"advisor" derived from ro_stage_history[0]["by"], the 3 personal-queue
buckets, and real appointment counts via core/appointments.py); and
get_service_my_day()'s real is_manager_view gate (role in ADMIN/OPERATIONS,
OR the employee's own real Title inferring to manager/executive tier via
core/bot_tasks.py's infer_tier()).

Every value below was live-verified against this exact module before being
written as an assertion.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.service_overview as so


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _sr(sr_id, **attrs):
    ledger.add_entity(Entity(id=sr_id, entity_type="ServiceRecord", attributes=attrs))


def _emp(emp_id, **attrs):
    ledger.add_entity(Entity(id=emp_id, entity_type="Employee", attributes=attrs))


class TestEmptyLedgerSanity:

    def test_command_center_empty(self):
        cc = so.get_command_center()
        assert cc["open_ros"]["count"] == 0
        assert cc["comebacks"]["count"] == 0

    def test_todays_risks_empty(self):
        risks = so.get_todays_risks()
        assert risks["customers_waiting"]["count"] == 0
        assert risks["jobs_behind_schedule"]["count"] == 0
        assert risks["techs_overloaded"]["count"] == 0
        assert risks["parts_delayed"]["count"] == 0

    def test_advisor_dashboard_empty(self):
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["advisor"] == {"id": "EMP-1", "name": None}
        assert adv["my_waiting_customers"]["count"] == 0
        assert adv["my_appointments"] == {"today_count": 0, "this_week_count": 0}


class TestCommandCenter:

    def test_completed_records_default_to_follow_up_and_are_excluded_from_live(self):
        _sr("SRV-1", Status="Completed")
        cc = so.get_command_center()
        assert cc["open_ros"]["count"] == 0

    def test_open_ros_counts_every_non_follow_up_stage(self):
        _sr("SRV-1", ro_stage="Check-In", Status="Open")
        _sr("SRV-2", ro_stage="Repair", Status="Open")
        _sr("SRV-3", Status="Completed")  # excluded
        cc = so.get_command_center()
        assert cc["open_ros"]["count"] == 2

    def test_waiting_approval_bucket(self):
        _sr("SRV-1", ro_stage="Customer Approval", Status="Open")
        _sr("SRV-2", ro_stage="Parts", Status="Open")
        cc = so.get_command_center()
        assert cc["waiting_approval"]["count"] == 1
        assert cc["waiting_approval"]["repair_orders"][0]["id"] == "SRV-1"

    def test_waiting_parts_bucket(self):
        _sr("SRV-1", ro_stage="Parts", Status="Open")
        _sr("SRV-2", ro_stage="Parts", Status="Open")
        _sr("SRV-3", ro_stage="Repair", Status="Open")
        cc = so.get_command_center()
        assert cc["waiting_parts"]["count"] == 2

    def test_waiting_delivery_bucket(self):
        _sr("SRV-1", ro_stage="Delivery", Status="Open")
        cc = so.get_command_center()
        assert cc["waiting_delivery"]["count"] == 1

    def test_waiting_technician_only_counts_repair_stage_with_no_technician(self):
        _sr("SRV-1", ro_stage="Repair", Status="Open")  # no Technician -> waiting
        _sr("SRV-2", ro_stage="Repair", Status="Open", Technician="EMP-9")  # assigned -> not waiting
        _sr("SRV-3", ro_stage="Customer Approval", Status="Open")  # wrong stage
        cc = so.get_command_center()
        assert cc["waiting_technician"]["count"] == 1
        assert cc["waiting_technician"]["repair_orders"][0]["id"] == "SRV-1"

    def test_comeback_within_window_is_detected(self):
        _sr("SRV-1", VIN="VIN1", ServiceDate="2026-01-01")
        _sr("SRV-2", VIN="VIN1", ServiceDate="2026-01-15")  # 14 days later -> comeback
        cc = so.get_command_center()
        assert cc["comebacks"]["count"] == 1
        assert cc["comebacks"]["repair_orders"][0]["id"] == "SRV-2"

    def test_comeback_outside_window_is_not_detected(self):
        _sr("SRV-1", VIN="VIN1", ServiceDate="2026-01-01")
        _sr("SRV-2", VIN="VIN1", ServiceDate="2026-06-01")  # far more than 30 days
        cc = so.get_command_center()
        assert cc["comebacks"]["count"] == 0

    def test_comeback_requires_at_least_two_records_for_the_same_vin(self):
        _sr("SRV-1", VIN="VIN1", ServiceDate="2026-01-01")
        _sr("SRV-2", VIN="VIN2", ServiceDate="2026-01-02")
        cc = so.get_command_center()
        assert cc["comebacks"]["count"] == 0

    def test_records_missing_vin_or_service_date_are_excluded_from_comeback_scan(self):
        _sr("SRV-1", VIN="VIN1")  # no ServiceDate
        _sr("SRV-2", ServiceDate="2026-01-01")  # no VIN
        cc = so.get_command_center()
        assert cc["comebacks"]["count"] == 0


class TestTodaysRisks:

    def test_customers_waiting_is_check_in_stage_only(self):
        _sr("SRV-1", ro_stage="Check-In", Status="Open")
        _sr("SRV-2", ro_stage="RO Written", Status="Open")
        risks = so.get_todays_risks()
        assert risks["customers_waiting"]["count"] == 1

    def test_jobs_behind_schedule_flags_ro_checked_in_24_plus_hours_ago(self):
        now = datetime.now(timezone.utc)
        old_checkin = (now - timedelta(hours=30)).isoformat()
        recent_checkin = (now - timedelta(hours=5)).isoformat()

        _sr("SRV-1", ro_stage="Repair", Status="Open", ro_stage_history=[{"at": old_checkin, "by": "EMP-1"}])
        _sr("SRV-2", ro_stage="Repair", Status="Open", ro_stage_history=[{"at": recent_checkin, "by": "EMP-1"}])
        _sr("SRV-3", ro_stage="Repair", Status="Open")  # no history -> _hours_since_checkin is None -> excluded

        risks = so.get_todays_risks()
        assert risks["jobs_behind_schedule"]["count"] == 1
        assert risks["jobs_behind_schedule"]["repair_orders"][0]["id"] == "SRV-1"

    def test_parts_delayed_only_counts_backordered_parts_status(self):
        _sr("SRV-1", ro_stage="Parts", Status="Open", parts_status={"status": "backordered"})
        _sr("SRV-2", ro_stage="Parts", Status="Open", parts_status={"status": "ordered"})
        _sr("SRV-3", ro_stage="Parts", Status="Open")  # no parts_status at all
        risks = so.get_todays_risks()
        assert risks["parts_delayed"]["count"] == 1
        assert risks["parts_delayed"]["repair_orders"][0]["id"] == "SRV-1"

    def test_techs_overloaded_reuses_shop_control_and_flags_over_8_hours(self):
        today = datetime.now(timezone.utc).date().isoformat()
        _sr("SRV-1", ro_stage="Repair", Status="Open", Technician="EMP-TECH", ServiceDate=today, LaborHours="9")
        risks = so.get_todays_risks()
        assert risks["techs_overloaded"]["count"] == 1
        tech = risks["techs_overloaded"]["technicians"][0]
        assert tech["technician_id"] == "EMP-TECH"
        assert tech["hours_booked_today"] == 9.0
        assert tech["assumed_capacity_hours"] == so.TECH_DAILY_CAPACITY_HOURS

    def test_techs_at_or_under_capacity_are_not_overloaded(self):
        today = datetime.now(timezone.utc).date().isoformat()
        _sr("SRV-1", ro_stage="Repair", Status="Open", Technician="EMP-TECH", ServiceDate=today, LaborHours="8")
        risks = so.get_todays_risks()
        assert risks["techs_overloaded"]["count"] == 0

    def test_promised_today_not_started_is_an_honest_gap(self):
        risks = so.get_todays_risks()
        assert risks["promised_today_not_started"]["count"] is None
        assert "not_yet_tracked" in risks["promised_today_not_started"]


class TestAdvisorDashboard:

    def test_advisor_is_derived_from_first_stage_history_entry(self):
        _sr("SRV-1", ro_stage="Check-In", Status="Open", ro_stage_history=[{"at": "2026-01-01T00:00:00+00:00", "by": "EMP-1"}])
        _sr("SRV-2", ro_stage="Repair", Status="Open", ro_stage_history=[{"at": "2026-01-01T00:00:00+00:00", "by": "EMP-OTHER"}])
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_waiting_customers"]["count"] == 1
        assert adv["my_waiting_customers"]["repair_orders"][0]["id"] == "SRV-1"

    def test_advisor_name_resolves_from_the_real_employee_entity(self):
        _emp("EMP-1", FirstName="Jane", LastName="Doe")
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["advisor"] == {"id": "EMP-1", "name": "Jane Doe"}

    def test_my_waiting_customers_covers_check_in_ro_written_and_inspection(self):
        by = "EMP-1"
        _sr("SRV-1", ro_stage="Check-In", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        _sr("SRV-2", ro_stage="RO Written", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        _sr("SRV-3", ro_stage="Inspection", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        _sr("SRV-4", ro_stage="Repair", Status="Open", ro_stage_history=[{"at": "x", "by": by}])  # not in bucket
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_waiting_customers"]["count"] == 3

    def test_my_pending_approvals_is_customer_approval_stage(self):
        by = "EMP-1"
        _sr("SRV-1", ro_stage="Customer Approval", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_pending_approvals"]["count"] == 1

    def test_my_vehicles_ready_covers_quality_control_and_delivery(self):
        by = "EMP-1"
        _sr("SRV-1", ro_stage="Quality Control", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        _sr("SRV-2", ro_stage="Delivery", Status="Open", ro_stage_history=[{"at": "x", "by": by}])
        _sr("SRV-3", ro_stage="Repair", Status="Open", ro_stage_history=[{"at": "x", "by": by}])  # not ready
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_vehicles_ready"]["count"] == 2

    def test_completed_records_are_excluded_from_my_ros_even_for_the_right_advisor(self):
        _sr("SRV-1", Status="Completed", ro_stage_history=[{"at": "x", "by": "EMP-1"}])
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_waiting_customers"]["count"] == 0
        assert adv["my_pending_approvals"]["count"] == 0
        assert adv["my_vehicles_ready"]["count"] == 0

    def test_records_with_no_stage_history_are_never_attributed_to_any_advisor(self):
        _sr("SRV-1", ro_stage="Check-In", Status="Open")  # no ro_stage_history at all
        adv = so.get_advisor_dashboard("EMP-1")
        assert adv["my_waiting_customers"]["count"] == 0


class TestGetServiceMyDay:

    def test_staff_tier_sales_role_is_not_manager_view(self):
        _emp("EMP-STAFF", Title="Service Advisor")
        result = so.get_service_my_day("SALES", "EMP-STAFF")
        assert result["is_manager_view"] is False
        assert "command_center" not in result
        assert "todays_risks" not in result

    def test_manager_titled_employee_with_a_non_privileged_role_is_manager_view(self):
        _emp("EMP-MGR", Title="Service Manager")
        result = so.get_service_my_day("SALES", "EMP-MGR")
        assert result["is_manager_view"] is True
        assert "command_center" in result
        assert "todays_risks" in result

    def test_admin_role_is_always_manager_view_regardless_of_title(self):
        _emp("EMP-STAFF", Title="Service Advisor")
        result = so.get_service_my_day("ADMIN", "EMP-STAFF")
        assert result["is_manager_view"] is True

    def test_operations_role_is_always_manager_view_regardless_of_title(self):
        _emp("EMP-STAFF", Title="Service Advisor")
        result = so.get_service_my_day("OPERATIONS", "EMP-STAFF")
        assert result["is_manager_view"] is True

    def test_nonexistent_employee_with_a_non_privileged_role_is_not_manager_view(self):
        result = so.get_service_my_day("SALES", "EMP-DOES-NOT-EXIST")
        assert result["is_manager_view"] is False

    def test_advisor_dashboard_is_always_included_regardless_of_manager_view(self):
        _emp("EMP-STAFF", Title="Service Advisor")
        result = so.get_service_my_day("SALES", "EMP-STAFF")
        assert "advisor_dashboard" in result
        assert result["advisor_dashboard"]["advisor"]["id"] == "EMP-STAFF"


class TestBucketCapping:

    def test_bucket_lists_cap_at_25_but_count_reflects_the_real_total(self):
        for i in range(30):
            _sr(f"SRV-{i}", ro_stage="Check-In", Status="Open")
        risks = so.get_todays_risks()
        assert risks["customers_waiting"]["count"] == 30
        assert len(risks["customers_waiting"]["repair_orders"]) == 25

@pytest.mark.parametrize("stage", ["Check-In", "RO Written", "Inspection", "Quality Control", "Delivery", "Repair", "Parts", "Customer Approval"])
def test_returned_custody_leaves_physical_queues_but_preserves_open_work(stage):
    _sr("RETURNED", ro_stage=stage, Status="Open", return_handover={"recorded_at":"2026-10-12T12:00:00Z"}, ro_stage_history=[{"by":"ADVISOR"}])
    _sr("ONSITE", ro_stage=stage, Status="Open", ro_stage_history=[{"by":"OTHER"}])
    cc = so.get_command_center()
    assert cc["open_ros"]["count"] == 2
    assert [r["id"] for r in cc["returned_unfinished"]["repair_orders"]] == ["RETURNED"]
    for key in ("waiting_approval","waiting_parts","waiting_technician","waiting_delivery"):
        assert all(r["id"] != "RETURNED" for r in cc[key]["repair_orders"])
    adv = so.get_advisor_dashboard("ADVISOR")
    assert adv["my_returned_unfinished"]["count"] == 1
    assert adv["my_returned_unfinished"]["repair_orders"][0]["vehicle_returned_at"]
    for key in ("my_waiting_customers","my_pending_approvals","my_vehicles_ready"):
        assert adv[key]["count"] == 0
    assert so.get_advisor_dashboard("OTHER")["my_returned_unfinished"]["count"] == 0
    risks = so.get_todays_risks()
    for key in ("customers_waiting","jobs_behind_schedule","parts_delayed"):
        assert all(r["id"] != "RETURNED" for r in risks[key]["repair_orders"])

def test_returned_followup_moves_to_recorded_owner_without_losing_manager_visibility():
    _sr("RETURNED", ro_stage="RO Written", return_handover={"recorded_at":"2026-10-12"}, ro_stage_history=[{"by":"ORIGINAL"}], return_followup={"owner_id":"NEW","due_date":"2026-10-14","next_action":"Call"})
    assert so.get_advisor_dashboard("ORIGINAL")["my_returned_unfinished"]["count"] == 0
    assert so.get_advisor_dashboard("NEW")["my_returned_unfinished"]["count"] == 1
    assert so.get_command_center()["returned_unfinished"]["count"] == 1
    assert so.get_command_center()["open_ros"]["count"] == 1

def test_returned_work_is_prioritized_before_summary_cap():
    for i in range(30):
        _sr(f"FUTURE-{i}",ro_stage="RO Written",return_handover={"recorded_at":"2026-10-12"},return_followup={"due_date":"2026-12-01"})
    _sr("OVERDUE",ro_stage="RO Written",return_handover={"recorded_at":"2026-10-12"},return_followup={"due_date":"2026-10-01"})
    _sr("UNPLANNED",ro_stage="RO Written",return_handover={"recorded_at":"2026-10-12"})
    bucket=so.get_command_center()["returned_unfinished"]
    assert bucket["count"] == 32
    assert len(bucket["repair_orders"]) == 25
    assert [r["id"] for r in bucket["repair_orders"][:2]] == ["UNPLANNED","OVERDUE"]


def test_recorded_followups_remain_visible_after_active_work():
    _sr("DONE", ro_stage="RO Written", return_handover={"recorded_at":"2026-10-12"}, return_followup={"status":"completed","due_date":"2026-10-01"})
    _sr("ACTIVE", ro_stage="RO Written", return_handover={"recorded_at":"2026-10-12"}, return_followup={"status":"planned","due_date":"2026-10-20"})
    bucket = so.get_command_center()["returned_unfinished"]
    assert [r["id"] for r in bucket["repair_orders"]] == ["ACTIVE","DONE"]
    assert so.get_command_center()["open_ros"]["count"] == 2
