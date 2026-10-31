"""
Tests for core/demo_drive.py + core/demo_drive_api.py -- Demo Drive (session
102 follow-up): a real test-drive log with a driver's-license-verification
gate, out/in odometer readings, and a live out -> returned/cancelled
lifecycle.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, CUSTOMER, VEHICLE, EMPLOYEE
from core import demo_drive
from core import demo_drive_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(demo_drive, "save_graph", lambda filepath: None)


_ALLOWED_ROLES = (ADMIN, OPERATIONS, SALES)
_DENIED_ROLES = (MARKETING, SERVICE, FINANCE)


def _add_lead(lead_id="LEAD-1", first="Alex", last="Prospect"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={"FirstName": first, "LastName": last}))
    return lead_id


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": first, "LastName": last}))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", year="2025", make="Honda", model="Civic"):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={"Year": year, "Make": make, "Model": model}))
    return vehicle_id


def _add_employee(employee_id="EMP-1", first="Sam", last="Sales"):
    ledger.add_entity(Entity(id=employee_id, entity_type=EMPLOYEE, attributes={"FirstName": first, "LastName": last}))
    return employee_id


def _start_valid_drive(**overrides):
    _add_lead()
    _add_vehicle()
    _add_employee()
    kwargs = dict(license_verified=True, odometer_out=1000)
    kwargs.update(overrides)
    return demo_drive.start_demo_drive("LEAD-1", "VEH-1", "EMP-1", **kwargs)


# ---------------------------------------------------------------------------
# start_demo_drive
# ---------------------------------------------------------------------------

class TestStartDemoDrive:
    def test_rejects_unknown_driver(self):
        _add_vehicle()
        _add_employee()
        result = demo_drive.start_demo_drive("LEAD-BAD", "VEH-1", "EMP-1", license_verified=True)
        assert "error" in result

    def test_rejects_driver_that_is_not_a_lead_or_customer(self):
        _add_vehicle()
        _add_employee()
        ledger.add_entity(Entity(id="VEH-DRIVER", entity_type=VEHICLE, attributes={}))
        result = demo_drive.start_demo_drive("VEH-DRIVER", "VEH-1", "EMP-1", license_verified=True)
        assert "error" in result

    def test_rejects_unknown_vehicle(self):
        _add_lead()
        _add_employee()
        result = demo_drive.start_demo_drive("LEAD-1", "VEH-BAD", "EMP-1", license_verified=True)
        assert "error" in result

    def test_rejects_unknown_salesperson(self):
        _add_lead()
        _add_vehicle()
        result = demo_drive.start_demo_drive("LEAD-1", "VEH-1", "EMP-BAD", license_verified=True)
        assert "error" in result

    def test_rejects_salesperson_that_is_not_an_employee(self):
        _add_lead()
        _add_vehicle()
        result = demo_drive.start_demo_drive("LEAD-1", "VEH-1", "LEAD-1", license_verified=True)
        assert "error" in result

    def test_rejects_when_license_not_verified(self):
        _add_lead()
        _add_vehicle()
        _add_employee()
        result = demo_drive.start_demo_drive("LEAD-1", "VEH-1", "EMP-1", license_verified=False)
        assert "error" in result

    def test_rejects_when_license_verified_omitted(self):
        _add_lead()
        _add_vehicle()
        _add_employee()
        result = demo_drive.start_demo_drive("LEAD-1", "VEH-1", "EMP-1")
        assert "error" in result

    def test_succeeds_with_a_verified_lead_driver(self):
        demo = _start_valid_drive()
        assert not isinstance(demo, dict) or "error" not in demo
        assert demo.attributes["status"] == "out"
        assert demo.attributes["linked_entity_type"] == LEAD

    def test_succeeds_with_a_verified_customer_driver(self):
        _add_customer()
        _add_vehicle()
        _add_employee()
        demo = demo_drive.start_demo_drive("CUST-1", "VEH-1", "EMP-1", license_verified=True)
        assert demo.attributes["status"] == "out"
        assert demo.attributes["linked_entity_type"] == CUSTOMER

    def test_stores_the_real_linked_ids(self):
        demo = _start_valid_drive()
        assert demo.attributes["linked_entity_id"] == "LEAD-1"
        assert demo.attributes["vehicle_id"] == "VEH-1"
        assert demo.attributes["salesperson_id"] == "EMP-1"

    def test_coerces_odometer_out_to_an_int(self):
        demo = _start_valid_drive(odometer_out="1234")
        assert demo.attributes["odometer_out"] == 1234

    def test_bad_odometer_out_becomes_none(self):
        demo = _start_valid_drive(odometer_out="not-a-number")
        assert demo.attributes["odometer_out"] is None

    def test_start_at_is_set_and_end_at_is_none(self):
        demo = _start_valid_drive()
        assert demo.attributes["start_at"] is not None
        assert demo.attributes["end_at"] is None

    def test_captures_license_number(self):
        demo = _start_valid_drive(license_number="D1234567")
        assert demo.attributes["license_number"] == "D1234567"

    def test_records_notes(self):
        demo = _start_valid_drive(notes="Interested in the sunroof package")
        assert demo.attributes["notes"] == "Interested in the sunroof package"

    def test_creates_a_real_entity_on_the_ledger(self):
        demo = _start_valid_drive()
        stored = ledger.get_entity(demo.id)
        assert stored is not None
        assert stored.attributes["status"] == "out"


# ---------------------------------------------------------------------------
# return_demo_drive
# ---------------------------------------------------------------------------

class TestReturnDemoDrive:
    def test_rejects_unknown_demo(self):
        result = demo_drive.return_demo_drive("DEMO-BAD")
        assert "error" in result

    def test_rejects_returning_an_already_returned_drive(self):
        demo = _start_valid_drive()
        demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1060)
        assert "error" in result

    def test_rejects_returning_a_cancelled_drive(self):
        demo = _start_valid_drive()
        demo_drive.cancel_demo_drive(demo.id)
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        assert "error" in result

    def test_rejects_bad_interest_level(self):
        demo = _start_valid_drive()
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050, interest_level="lukewarm")
        assert "error" in result

    def test_accepts_every_real_interest_level(self):
        for level in demo_drive.INTEREST_LEVELS:
            demo = _start_valid_drive()
            result = demo_drive.return_demo_drive(demo.id, odometer_in=1050, interest_level=level)
            assert result.attributes["interest_level"] == level

    def test_sets_status_to_returned(self):
        demo = _start_valid_drive()
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        assert result.attributes["status"] == "returned"

    def test_computes_real_miles_driven(self):
        demo = _start_valid_drive(odometer_out=1000)
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1075)
        assert result.attributes["miles_driven"] == 75

    def test_miles_driven_is_none_when_odometer_in_missing(self):
        demo = _start_valid_drive(odometer_out=1000)
        result = demo_drive.return_demo_drive(demo.id)
        assert result.attributes["miles_driven"] is None

    def test_miles_driven_is_none_when_odometer_out_missing(self):
        demo = _start_valid_drive(odometer_out=None)
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        assert result.attributes["miles_driven"] is None

    def test_miles_driven_is_none_when_odometer_in_is_less_than_out(self):
        """A genuinely inconsistent reading -- never fabricate a negative or
        nonsensical mileage figure."""
        demo = _start_valid_drive(odometer_out=1000)
        result = demo_drive.return_demo_drive(demo.id, odometer_in=900)
        assert result.attributes["miles_driven"] is None

    def test_records_feedback(self):
        demo = _start_valid_drive()
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050, feedback="Loved it")
        assert result.attributes["feedback"] == "Loved it"

    def test_computes_a_real_duration(self):
        demo = _start_valid_drive()
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        assert result.attributes["duration_minutes"] is not None
        assert result.attributes["duration_minutes"] >= 0

    def test_sets_end_at(self):
        demo = _start_valid_drive()
        result = demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        assert result.attributes["end_at"] is not None


# ---------------------------------------------------------------------------
# cancel_demo_drive
# ---------------------------------------------------------------------------

class TestCancelDemoDrive:
    def test_rejects_unknown_demo(self):
        result = demo_drive.cancel_demo_drive("DEMO-BAD")
        assert "error" in result

    def test_rejects_cancelling_a_returned_drive(self):
        demo = _start_valid_drive()
        demo_drive.return_demo_drive(demo.id, odometer_in=1050)
        result = demo_drive.cancel_demo_drive(demo.id)
        assert "error" in result

    def test_cancels_an_active_drive(self):
        demo = _start_valid_drive()
        result = demo_drive.cancel_demo_drive(demo.id)
        assert result.attributes["status"] == "cancelled"

    def test_sets_end_at_on_cancel(self):
        demo = _start_valid_drive()
        result = demo_drive.cancel_demo_drive(demo.id)
        assert result.attributes["end_at"] is not None

    def test_re_cancelling_an_already_cancelled_drive_is_allowed(self):
        demo = _start_valid_drive()
        demo_drive.cancel_demo_drive(demo.id)
        result = demo_drive.cancel_demo_drive(demo.id)
        assert result.attributes["status"] == "cancelled"


# ---------------------------------------------------------------------------
# list_demo_drives / list_active_demo_drives
# ---------------------------------------------------------------------------

class TestListing:
    def test_lists_all_demo_drives(self):
        _start_valid_drive()
        demos = demo_drive.list_demo_drives()
        assert len(demos) == 1

    def test_filters_by_status(self):
        demo1 = _start_valid_drive()
        demo_drive.return_demo_drive(demo1.id, odometer_in=1050)

        _add_lead("LEAD-2")
        _add_vehicle("VEH-2")
        demo2 = demo_drive.start_demo_drive("LEAD-2", "VEH-2", "EMP-1", license_verified=True)

        out_only = demo_drive.list_demo_drives(status="out")
        returned_only = demo_drive.list_demo_drives(status="returned")

        assert len(out_only) == 1
        assert out_only[0].id == demo2.id
        assert len(returned_only) == 1
        assert returned_only[0].id == demo1.id

    def test_filters_by_salesperson_id(self):
        _start_valid_drive()
        _add_employee("EMP-2")
        _add_lead("LEAD-2")
        _add_vehicle("VEH-2")
        demo_drive.start_demo_drive("LEAD-2", "VEH-2", "EMP-2", license_verified=True)

        for_emp1 = demo_drive.list_demo_drives(salesperson_id="EMP-1")
        assert len(for_emp1) == 1
        assert for_emp1[0].attributes["salesperson_id"] == "EMP-1"

    def test_filters_by_vehicle_id(self):
        _start_valid_drive()
        _add_lead("LEAD-2")
        demo_drive.start_demo_drive("LEAD-2", "VEH-1", "EMP-1", license_verified=True)
        _add_vehicle("VEH-2")
        _add_lead("LEAD-3")
        demo_drive.start_demo_drive("LEAD-3", "VEH-2", "EMP-1", license_verified=True)

        for_veh1 = demo_drive.list_demo_drives(vehicle_id="VEH-1")
        assert len(for_veh1) == 2

    def test_list_active_only_returns_out_status(self):
        demo1 = _start_valid_drive()
        demo_drive.cancel_demo_drive(demo1.id)

        _add_lead("LEAD-2")
        _add_vehicle("VEH-2")
        demo2 = demo_drive.start_demo_drive("LEAD-2", "VEH-2", "EMP-1", license_verified=True)

        active = demo_drive.list_active_demo_drives()
        assert len(active) == 1
        assert active[0].id == demo2.id


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_stats_are_honest_zeros_and_nones(self):
        stats = demo_drive.get_stats()
        assert stats["total"] == 0
        assert stats["active"] == 0
        assert stats["returned"] == 0
        assert stats["cancelled"] == 0
        assert stats["license_verified_pct"] is None
        assert stats["avg_duration_minutes"] is None
        assert stats["avg_miles_driven"] is None

    def test_counts_by_status(self):
        d1 = _start_valid_drive()
        demo_drive.return_demo_drive(d1.id, odometer_in=1050)

        _add_lead("LEAD-2")
        _add_vehicle("VEH-2")
        d2 = demo_drive.start_demo_drive("LEAD-2", "VEH-2", "EMP-1", license_verified=True)
        demo_drive.cancel_demo_drive(d2.id)

        _add_lead("LEAD-3")
        _add_vehicle("VEH-3")
        demo_drive.start_demo_drive("LEAD-3", "VEH-3", "EMP-1", license_verified=True)

        stats = demo_drive.get_stats()
        assert stats["total"] == 3
        assert stats["returned"] == 1
        assert stats["cancelled"] == 1
        assert stats["active"] == 1

    def test_license_verified_pct_is_real(self):
        _start_valid_drive()
        stats = demo_drive.get_stats()
        assert stats["license_verified_pct"] == 100.0

    def test_avg_duration_and_miles_computed_over_returned_only(self):
        d1 = _start_valid_drive(odometer_out=1000)
        demo_drive.return_demo_drive(d1.id, odometer_in=1080)

        stats = demo_drive.get_stats()
        assert stats["avg_miles_driven"] == 80.0
        assert stats["avg_duration_minutes"] is not None


# ---------------------------------------------------------------------------
# ACL sweep -- core/demo_drive_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    def test_list_demo_statuses_api_is_open(self):
        result = demo_drive_api.list_demo_statuses_api()
        assert result == demo_drive.STATUSES

    def test_list_interest_levels_api_is_open(self):
        result = demo_drive_api.list_interest_levels_api()
        assert result == demo_drive.INTEREST_LEVELS

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_start_demo_drive_api_denied(self, role):
        _add_lead()
        _add_vehicle()
        _add_employee()
        result = demo_drive_api.start_demo_drive_api(role, "LEAD-1", "VEH-1", "EMP-1", license_verified=True)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_start_demo_drive_api_allowed(self, role):
        ledger.reset()
        _add_lead()
        _add_vehicle()
        _add_employee()
        result = demo_drive_api.start_demo_drive_api(role, "LEAD-1", "VEH-1", "EMP-1", license_verified=True)
        assert "error" not in result
        assert result["status"] == "out"

    def test_start_demo_drive_api_serializes_labels(self):
        _add_lead(first="Alex", last="Prospect")
        _add_vehicle(year="2024", make="Toyota", model="Camry")
        _add_employee(first="Sam", last="Sales")
        result = demo_drive_api.start_demo_drive_api(ADMIN, "LEAD-1", "VEH-1", "EMP-1", license_verified=True)
        assert result["driver_label"] == "Alex Prospect"
        assert result["vehicle_label"] == "2024 Toyota Camry"
        assert result["salesperson_name"] == "Sam Sales"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_return_demo_drive_api_denied(self, role):
        demo = _start_valid_drive()
        result = demo_drive_api.return_demo_drive_api(role, demo.id, odometer_in=1050)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_return_demo_drive_api_allowed(self, role):
        ledger.reset()
        demo = _start_valid_drive()
        result = demo_drive_api.return_demo_drive_api(role, demo.id, odometer_in=1050)
        assert "error" not in result
        assert result["status"] == "returned"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_cancel_demo_drive_api_denied(self, role):
        demo = _start_valid_drive()
        result = demo_drive_api.cancel_demo_drive_api(role, demo.id)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_cancel_demo_drive_api_allowed(self, role):
        ledger.reset()
        demo = _start_valid_drive()
        result = demo_drive_api.cancel_demo_drive_api(role, demo.id)
        assert "error" not in result
        assert result["status"] == "cancelled"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_list_active_demo_drives_api_denied(self, role):
        result = demo_drive_api.list_active_demo_drives_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_list_active_demo_drives_api_allowed(self, role):
        result = demo_drive_api.list_active_demo_drives_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_list_demo_drives_api_denied(self, role):
        result = demo_drive_api.list_demo_drives_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_list_demo_drives_api_allowed(self, role):
        result = demo_drive_api.list_demo_drives_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_demo_drive_dashboard_api_denied(self, role):
        result = demo_drive_api.get_demo_drive_dashboard_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_demo_drive_dashboard_api_allowed(self, role):
        result = demo_drive_api.get_demo_drive_dashboard_api(role)
        assert "error" not in result
        assert "active" in result
        assert "stats" in result
