"""
Tests for core/shop_control.py + core/shop_control_api.py -- Service's Shop
Control: a real Technician Dispatch Board (technician-centric, not
stage-centric), real Technician Utilization off an ASSUMED daily-capacity
constant, real Stalled RO Detection, and a composed Shop Bottlenecks feed.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, EMPLOYEE
from core import repair_orders
from core import shop_control
from core import shop_control_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING,)


def _add_customer(customer_id="CUST-1"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={
        "CustomerID": customer_id, "FirstName": "Jane", "LastName": "Doe",
    }))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", vin="VIN1234567890"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "VIN": vin, "Year": "2022", "Make": "Ford", "Model": "F-150", "Mileage": 30000,
    }))
    return vehicle_id


def _add_technician(emp_id="EMP-TECH-1", first="Nate", last="Higgins", department="Service", title="Technician"):
    ledger.add_entity(Entity(id=emp_id, entity_type=EMPLOYEE, attributes={
        "FirstName": first, "LastName": last, "Department": department, "Title": title,
    }))
    return emp_id


def _add_ro(customer_id="CUST-1", vehicle_id="VEH-1", description="Brakes squeaking", created_by="EMP-1"):
    result = repair_orders.create_repair_order(vehicle_id, customer_id, description, created_by)
    assert "error" not in result
    return result["id"]


def _backdate_checkin(ro_id, hours_ago):
    ro = ledger.get_entity(ro_id)
    checkin_at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    ro.attributes["ro_stage_history"][0]["at"] = checkin_at


def _set_labor_hours(ro_id, hours):
    ledger.get_entity(ro_id).attributes["LaborHours"] = hours


def _set_service_date(ro_id, date_str):
    ledger.get_entity(ro_id).attributes["ServiceDate"] = date_str


# ---------------------------------------------------------------------------
# get_dispatch_board
# ---------------------------------------------------------------------------

class TestGetDispatchBoard:
    def test_every_real_service_technician_appears_even_with_zero_ros(self):
        _add_technician("EMP-TECH-1", "Nate", "Higgins")
        board = shop_control.get_dispatch_board()
        assert "EMP-TECH-1" in board["technicians"]
        assert board["technicians"]["EMP-TECH-1"]["name"] == "Nate Higgins"
        assert board["technicians"]["EMP-TECH-1"]["repair_orders"] == []

    def test_only_includes_service_department_technicians(self):
        _add_technician("EMP-1", department="Sales", title="Technician")
        board = shop_control.get_dispatch_board()
        assert "EMP-1" not in board["technicians"]

    def test_only_includes_titles_containing_technician(self):
        _add_technician("EMP-1", department="Service", title="Service Advisor")
        board = shop_control.get_dispatch_board()
        assert "EMP-1" not in board["technicians"]

    def test_a_live_ro_assigned_to_a_known_technician_lands_in_that_column(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-TECH-1")
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH-1", "EMP-1")

        board = shop_control.get_dispatch_board()
        assert len(board["technicians"]["EMP-TECH-1"]["repair_orders"]) == 1
        assert board["technicians"]["EMP-TECH-1"]["repair_orders"][0]["id"] == ro_id

    def test_a_ro_with_no_technician_lands_in_unassigned(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        board = shop_control.get_dispatch_board()
        assert len(board["unassigned"]) == 1
        assert board["unassigned"][0]["id"] == ro_id

    def test_a_ro_assigned_to_a_non_roster_technician_gets_its_own_fallback_column(self):
        _add_customer()
        _add_vehicle()
        # An employee id that's real but not a Service technician on this board.
        _add_technician("EMP-SALES-1", department="Sales", title="Sales Rep")
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-SALES-1", "EMP-1")

        board = shop_control.get_dispatch_board()
        assert "EMP-SALES-1" in board["technicians"]
        assert board["technicians"]["EMP-SALES-1"]["name"] == "EMP-SALES-1"
        assert len(board["technicians"]["EMP-SALES-1"]["repair_orders"]) == 1

    def test_excludes_follow_up_stage_ros(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        # Seed a completed historical RO; stage-transition gates are tested separately.
        ledger.get_entity(ro_id).attributes.update(ro_stage="Follow-Up", Status="Completed")

        board = shop_control.get_dispatch_board()
        assert board["unassigned"] == []

    def test_includes_every_non_follow_up_stage(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        repair_orders.advance_stage(ro_id, "Repair", "EMP-1")

        board = shop_control.get_dispatch_board()
        assert len(board["unassigned"]) == 1


# ---------------------------------------------------------------------------
# get_technician_utilization
# ---------------------------------------------------------------------------

class TestGetTechnicianUtilization:
    def test_empty_when_no_records(self):
        result = shop_control.get_technician_utilization(date="2026-01-01")
        assert result["technicians"] == []
        assert result["date"] == "2026-01-01"

    def test_skips_records_on_a_different_date(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_id, "2020-01-01")
        _set_labor_hours(ro_id, 5)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"] == []

    def test_skips_records_with_no_technician(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _set_service_date(ro_id, "2026-06-01")

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"] == []

    def test_sums_hours_and_ro_count_per_technician(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-TECH-1", "Nate", "Higgins")

        ro_a = _add_ro()
        repair_orders.assign_technician(ro_a, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_a, "2026-06-01")
        _set_labor_hours(ro_a, 3)

        ro_b = _add_ro()
        repair_orders.assign_technician(ro_b, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_b, "2026-06-01")
        _set_labor_hours(ro_b, 4)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert len(result["technicians"]) == 1
        entry = result["technicians"][0]
        assert entry["technician_id"] == "EMP-TECH-1"
        assert entry["name"] == "Nate Higgins"
        assert entry["ro_count"] == 2
        assert entry["hours_booked"] == 7.0

    def test_computes_utilization_pct_against_assumed_capacity(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-TECH-1")
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_id, "2026-06-01")
        _set_labor_hours(ro_id, 4)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"][0]["utilization_pct"] == 50.0
        assert result["technicians"][0]["assumed_capacity_hours"] == 8.0
        assert result["technicians"][0]["overloaded"] is False

    def test_flags_overloaded_when_over_capacity(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-TECH-1")
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_id, "2026-06-01")
        _set_labor_hours(ro_id, 9)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"][0]["overloaded"] is True

    def test_non_numeric_labor_hours_treated_as_zero(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-TECH-1")
        ro_id = _add_ro()
        repair_orders.assign_technician(ro_id, "EMP-TECH-1", "EMP-1")
        _set_service_date(ro_id, "2026-06-01")
        _set_labor_hours(ro_id, "not-a-number")

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"][0]["hours_booked"] == 0.0

    def test_falls_back_to_tech_id_when_no_employee_on_file(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        # A resolved employee id that no longer exists on the current
        # roster (e.g. a historical import) -- set directly, since
        # assign_technician() itself requires the technician to exist.
        ledger.get_entity(ro_id).attributes["Technician"] = "EMP-GHOST"
        _set_service_date(ro_id, "2026-06-01")
        _set_labor_hours(ro_id, 2)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        assert result["technicians"][0]["name"] == "EMP-GHOST"

    def test_defaults_to_todays_date_when_none_given(self):
        result = shop_control.get_technician_utilization()
        assert result["date"] == datetime.now(timezone.utc).date().isoformat()

    def test_sorted_by_utilization_pct_descending(self):
        _add_customer()
        _add_vehicle()
        _add_technician("EMP-LOW")
        _add_technician("EMP-HIGH")

        ro_low = _add_ro()
        repair_orders.assign_technician(ro_low, "EMP-LOW", "EMP-1")
        _set_service_date(ro_low, "2026-06-01")
        _set_labor_hours(ro_low, 1)

        ro_high = _add_ro()
        repair_orders.assign_technician(ro_high, "EMP-HIGH", "EMP-1")
        _set_service_date(ro_high, "2026-06-01")
        _set_labor_hours(ro_high, 9)

        result = shop_control.get_technician_utilization(date="2026-06-01")
        ids = [t["technician_id"] for t in result["technicians"]]
        assert ids == ["EMP-HIGH", "EMP-LOW"]


# ---------------------------------------------------------------------------
# get_stalled_ros
# ---------------------------------------------------------------------------

class TestGetStalledRos:
    def test_empty_when_no_records(self):
        result = shop_control.get_stalled_ros()
        assert result == {"count": 0, "repair_orders": [], "hours_threshold": 9.0}

    def test_flags_a_ro_open_past_threshold_with_no_labor_posted(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 10)

        result = shop_control.get_stalled_ros()
        assert result["count"] == 1
        assert result["repair_orders"][0]["id"] == ro_id
        assert result["repair_orders"][0]["hours_open"] == 10.0

    def test_not_flagged_under_the_threshold(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 3)

        result = shop_control.get_stalled_ros()
        assert result["count"] == 0

    def test_not_flagged_when_labor_has_been_posted(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 10)
        _set_labor_hours(ro_id, 1.5)

        result = shop_control.get_stalled_ros()
        assert result["count"] == 0

    def test_excludes_follow_up_stage(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 10)
        # Seed a completed historical RO; stage-transition gates are tested separately.
        ledger.get_entity(ro_id).attributes.update(ro_stage="Follow-Up", Status="Completed")

        result = shop_control.get_stalled_ros()
        assert result["count"] == 0

    def test_respects_a_custom_threshold(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 5)

        result = shop_control.get_stalled_ros(hours_threshold=4.0)
        assert result["count"] == 1
        assert result["hours_threshold"] == 4.0

    def test_sorted_most_stalled_first(self):
        _add_customer()
        _add_vehicle()
        ro_a = _add_ro()
        _backdate_checkin(ro_a, 12)
        ro_b = _add_ro()
        _backdate_checkin(ro_b, 30)

        result = shop_control.get_stalled_ros()
        assert [r["id"] for r in result["repair_orders"]] == [ro_b, ro_a]


# ---------------------------------------------------------------------------
# get_bottlenecks
# ---------------------------------------------------------------------------

class TestGetBottlenecks:
    def test_empty_when_no_records(self):
        result = shop_control.get_bottlenecks()
        assert result["parts_delays"]["count"] == 0
        assert result["approval_delays"]["count"] == 0
        assert result["technician_delays"]["count"] == 0

    def test_flags_a_backordered_parts_stage_ro(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        repair_orders.advance_stage(ro_id, "Parts", "EMP-1")
        repair_orders.update_parts_status(ro_id, "backordered", "EMP-1")

        result = shop_control.get_bottlenecks()
        assert result["parts_delays"]["count"] == 1
        assert result["parts_delays"]["repair_orders"][0]["id"] == ro_id

    def test_does_not_flag_an_all_available_parts_stage_ro(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        repair_orders.advance_stage(ro_id, "Parts", "EMP-1")
        repair_orders.update_parts_status(ro_id, "all_available", "EMP-1")

        result = shop_control.get_bottlenecks()
        assert result["parts_delays"]["count"] == 0

    def test_does_not_flag_a_backordered_ro_outside_parts_stage(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        repair_orders.update_parts_status(ro_id, "backordered", "EMP-1")  # still Check-In stage

        result = shop_control.get_bottlenecks()
        assert result["parts_delays"]["count"] == 0

    def test_flags_a_customer_approval_ro_open_past_threshold(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 30)
        repair_orders.advance_stage(ro_id, "Customer Approval", "EMP-1")

        result = shop_control.get_bottlenecks()
        assert result["approval_delays"]["count"] == 1
        assert result["approval_delays"]["repair_orders"][0]["id"] == ro_id
        assert result["approval_delays"]["repair_orders"][0]["hours_open"] == 30.0

    def test_does_not_flag_a_customer_approval_ro_under_threshold(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 5)
        repair_orders.advance_stage(ro_id, "Customer Approval", "EMP-1")

        result = shop_control.get_bottlenecks()
        assert result["approval_delays"]["count"] == 0

    def test_technician_delays_reuses_get_stalled_ros(self):
        _add_customer()
        _add_vehicle()
        ro_id = _add_ro()
        _backdate_checkin(ro_id, 10)

        result = shop_control.get_bottlenecks()
        assert result["technician_delays"]["count"] == 1
        assert result["technician_delays"]["repair_orders"][0]["id"] == ro_id


# ---------------------------------------------------------------------------
# ACL sweep -- core/shop_control_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_dispatch_board_api_denied(self, role):
        result = shop_control_api.get_dispatch_board_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_dispatch_board_api_allowed(self, role):
        result = shop_control_api.get_dispatch_board_api(role)
        assert "technicians" in result and "unassigned" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_technician_utilization_api_denied(self, role):
        result = shop_control_api.get_technician_utilization_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_technician_utilization_api_allowed(self, role):
        result = shop_control_api.get_technician_utilization_api(role, date="2026-01-01")
        assert result["date"] == "2026-01-01"

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_stalled_ros_api_denied(self, role):
        result = shop_control_api.get_stalled_ros_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_stalled_ros_api_allowed(self, role):
        result = shop_control_api.get_stalled_ros_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_bottlenecks_api_denied(self, role):
        result = shop_control_api.get_bottlenecks_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_bottlenecks_api_allowed(self, role):
        result = shop_control_api.get_bottlenecks_api(role)
        assert "parts_delays" in result
