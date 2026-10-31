"""
Tests for core/device_management.py / core/device_management_api.py (Finance's "GPS &
Devices" + "Starter Interrupt" Top Menu items, the fifth slice of the Retail
Automotive Lending Platform expansion, 2026-07-17). Run from backend/ with `pytest`.

Covers: register_device()'s validation (bad device_type/missing serial/loan not
found/one-active-device-per-loan constraint, including re-registering after a prior
device was removed) + real defaults per device_type; remove_device(); list_devices()
filtering/sorting; get_simulated_location()'s deterministic-per-day seeding and
SIMULATED basis/disclaimer; get_location_history()'s multi-day entries; the starter-
interrupt capability gate (_require_starter_capable, exercised via every mutating
starter function on a gps_only device); arm_starter_interrupt(); send_warning()
(default vs. custom message); disable_starter()'s real enforced gate (must be armed,
must have a warning on file, NOT_LEGAL_ADVICE_NOTICE, already-disabled rejection);
enable_starter() (no warning required, already-enabled rejection); get_device_detail()
(location populated only when active); get_device_management_dashboard()'s real
counts; get_starter_interrupt_dashboard()'s armed/disabled/pending_warning counts; and
the ACL layer in core/device_management_api.py (ADMIN/OPERATIONS/FINANCE for both
viewing and mutating -- the same role set on both sides, unlike most sibling modules).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT
from core import device_management
from core import device_management_api
from core.compliance_rules import NOT_LEGAL_ADVICE_NOTICE
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(device_management, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(
        id=customer_id, entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    ))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", make="Honda", model="Civic", year="2025"):
    ledger.add_entity(Entity(
        id=vehicle_id, entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year},
    ))
    return vehicle_id


def _add_loan(loan_id="FIN-1", link_customer="CUST-1", link_vehicle="VEH-1"):
    ledger.add_entity(Entity(
        id=loan_id, entity_type=FINANCE_CONTRACT,
        attributes={
            "FinanceNumber": loan_id, "AmountFinanced": 12000.0, "APR": 9.0,
            "TermMonths": 48, "MonthlyPayment": 298.62, "ContractDate": "2026-01-01",
        },
    ))
    if link_customer:
        ledger.add_relationship(Relationship(source_id=link_customer, target_id=loan_id, relationship_type="FINANCED_BY"))
    if link_vehicle:
        ledger.add_relationship(Relationship(source_id=loan_id, target_id=link_vehicle, relationship_type="COVERS"))
    return loan_id


def _full_loan_setup(loan_id="FIN-1"):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    return _add_loan(loan_id=loan_id, link_customer="CUST-1", link_vehicle="VEH-1")


# ---------------------------------------------------------------------------
# register_device()
# ---------------------------------------------------------------------------

class TestRegisterDevice:

    def test_bad_device_type_rejected(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "cellular_only", "SN1", "EMP-1")
        assert "error" in result
        assert "device_type must be one of" in result["error"]

    def test_missing_serial_number_rejected(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_only", "", "EMP-1")
        assert result == {"error": "serial_number is required"}

    def test_loan_not_found(self):
        result = device_management.register_device("FIN-BOGUS", "gps_only", "SN1", "EMP-1")
        assert result == {"error": "Loan 'FIN-BOGUS' not found"}

    def test_happy_path_gps_only(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_only", "SN123", "EMP-1")

        assert isinstance(result, Entity)
        assert result.attributes["loan_id"] == "FIN-1"
        assert result.attributes["customer_id"] == "CUST-1"
        assert result.attributes["vehicle_id"] == "VEH-1"
        assert result.attributes["device_type"] == "gps_only"
        assert result.attributes["serial_number"] == "SN123"
        assert result.attributes["status"] == "active"
        assert result.attributes["starter_interrupt_armed"] is False
        assert result.attributes["starter_status"] is None
        assert result.attributes["last_warning_at"] is None
        assert result.attributes["removed_at"] is None

    def test_happy_path_gps_starter_interrupt_defaults_starter_enabled(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN456", "EMP-1")
        assert result.attributes["starter_status"] == "enabled"

    def test_install_date_defaults_to_today(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        assert result.attributes["install_date"] == device_management._today_iso()

    def test_install_date_can_be_overridden(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1", install_date="2026-02-14")
        assert result.attributes["install_date"] == "2026-02-14"

    def test_command_history_has_registered_entry(self):
        _full_loan_setup()
        result = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-9")
        history = result.attributes["command_history"]
        assert len(history) == 1
        assert history[0]["action"] == "registered"
        assert history[0]["by"] == "EMP-9"

    def test_second_active_device_on_same_loan_rejected(self):
        _full_loan_setup()
        first = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.register_device("FIN-1", "gps_only", "SN2", "EMP-1")
        assert "error" in result
        assert first.id in result["error"]
        assert "already has an active device" in result["error"]

    def test_can_register_new_device_after_prior_one_removed(self):
        _full_loan_setup()
        first = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        device_management.remove_device(first.id, "EMP-1")

        result = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN2", "EMP-1")
        assert isinstance(result, Entity)
        assert result.attributes["serial_number"] == "SN2"


# ---------------------------------------------------------------------------
# remove_device()
# ---------------------------------------------------------------------------

class TestRemoveDevice:

    def test_not_found(self):
        result = device_management.remove_device("DEV-BOGUS", "EMP-1")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_already_removed_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        device_management.remove_device(device.id, "EMP-1")

        result = device_management.remove_device(device.id, "EMP-1")
        assert result == {"error": "Device is already removed"}

    def test_happy_path(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.remove_device(device.id, "EMP-2", reason="Loan paid off")

        assert isinstance(result, Entity)
        assert result.attributes["status"] == "removed"
        assert result.attributes["removed_by"] == "EMP-2"
        assert result.attributes["removed_reason"] == "Loan paid off"
        assert result.attributes["removed_at"] is not None
        assert result.attributes["command_history"][-1]["action"] == "removed"


# ---------------------------------------------------------------------------
# list_devices()
# ---------------------------------------------------------------------------

class TestListDevices:

    def test_filters_by_status_loan_and_type(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")

        gps_device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1", install_date="2026-01-01")
        si_device = device_management.register_device("FIN-2", "gps_starter_interrupt", "SN2", "EMP-1", install_date="2026-02-01")
        device_management.remove_device(si_device.id, "EMP-1")

        active_only = device_management.list_devices(status="active")
        assert active_only["count"] == 1
        assert active_only["devices"][0]["id"] == gps_device.id

        by_loan = device_management.list_devices(loan_id="FIN-2")
        assert by_loan["count"] == 1
        assert by_loan["devices"][0]["id"] == si_device.id

        by_type = device_management.list_devices(device_type="gps_starter_interrupt")
        assert by_type["count"] == 1

    def test_sorted_by_install_date_descending(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")

        older = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1", install_date="2026-01-01")
        newer = device_management.register_device("FIN-2", "gps_only", "SN2", "EMP-1", install_date="2026-06-01")

        result = device_management.list_devices()
        assert [d["id"] for d in result["devices"]] == [newer.id, older.id]

    def test_empty_when_no_devices(self):
        result = device_management.list_devices()
        assert result == {"count": 0, "devices": []}


# ---------------------------------------------------------------------------
# get_simulated_location() / get_location_history()
# ---------------------------------------------------------------------------

class TestSimulatedLocation:

    def test_device_not_found(self):
        result = device_management.get_simulated_location("DEV-BOGUS")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_happy_path_shape(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_simulated_location(device.id)

        assert result["device_id"] == device.id
        assert result["loan_id"] == "FIN-1"
        assert isinstance(result["latitude"], float)
        assert isinstance(result["longitude"], float)
        assert "approximate_address" in result
        assert result["moving"] == (result["speed_mph"] > 0)
        assert result["basis"] == device_management.SIMULATED_GPS_BASIS
        assert result["disclaimer"] == device_management._DISCLAIMER_GPS

    def test_deterministic_within_the_same_day(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        first = device_management.get_simulated_location(device.id)
        second = device_management.get_simulated_location(device.id)

        assert first["latitude"] == second["latitude"]
        assert first["longitude"] == second["longitude"]
        assert first["speed_mph"] == second["speed_mph"]
        assert first["approximate_address"] == second["approximate_address"]

    def test_different_devices_differ(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")

        d1 = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        d2 = device_management.register_device("FIN-2", "gps_only", "SN2", "EMP-1")

        loc1 = device_management.get_simulated_location(d1.id)
        loc2 = device_management.get_simulated_location(d2.id)
        assert (loc1["latitude"], loc1["longitude"]) != (loc2["latitude"], loc2["longitude"])


class TestLocationHistory:

    def test_device_not_found(self):
        result = device_management.get_location_history("DEV-BOGUS")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_default_seven_days(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_location_history(device.id)
        assert result["days"] == 7
        assert len(result["entries"]) == 7
        assert result["basis"] == device_management.SIMULATED_GPS_BASIS

    def test_custom_days(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_location_history(device.id, days=3)
        assert result["days"] == 3
        assert len(result["entries"]) == 3

    def test_entries_across_days_are_not_all_identical(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_location_history(device.id, days=7)
        distinct_points = {(e["latitude"], e["longitude"]) for e in result["entries"]}
        assert len(distinct_points) > 1

    def test_entries_have_real_dates(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_location_history(device.id, days=2)
        dates = [e["date"] for e in result["entries"]]
        assert dates[0] == device_management._today_iso()
        assert len(set(dates)) == 2


# ---------------------------------------------------------------------------
# Starter-interrupt capability gate
# ---------------------------------------------------------------------------

class TestRequireStarterCapableGate:

    def test_arm_rejected_on_gps_only_device(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.arm_starter_interrupt(device.id, "EMP-1")
        assert "does not have starter-interrupt capability" in result["error"]

    def test_send_warning_rejected_on_gps_only_device(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.send_warning(device.id, "EMP-1")
        assert "does not have starter-interrupt capability" in result["error"]

    def test_disable_rejected_on_gps_only_device(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-1")
        assert "does not have starter-interrupt capability" in result["error"]

    def test_enable_rejected_on_gps_only_device(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.enable_starter(device.id, "EMP-1")
        assert "does not have starter-interrupt capability" in result["error"]


# ---------------------------------------------------------------------------
# arm_starter_interrupt()
# ---------------------------------------------------------------------------

class TestArmStarterInterrupt:

    def test_device_not_found(self):
        result = device_management.arm_starter_interrupt("DEV-BOGUS", "EMP-1")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_removed_device_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.remove_device(device.id, "EMP-1")

        result = device_management.arm_starter_interrupt(device.id, "EMP-1")
        assert result == {"error": "Cannot arm a removed device"}

    def test_happy_path(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")

        result = device_management.arm_starter_interrupt(device.id, "EMP-2")

        assert isinstance(result, Entity)
        assert result.attributes["starter_interrupt_armed"] is True
        assert result.attributes["command_history"][-1] == {
            "action": "armed", "by": "EMP-2", "reason": "", "at": result.attributes["command_history"][-1]["at"],
        }


# ---------------------------------------------------------------------------
# send_warning()
# ---------------------------------------------------------------------------

class TestSendWarning:

    def test_device_not_found(self):
        result = device_management.send_warning("DEV-BOGUS", "EMP-1")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_default_message_used_when_none_given(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")

        result = device_management.send_warning(device.id, "EMP-2")

        assert isinstance(result, Entity)
        assert "delinquent" in result.attributes["last_warning_message"]
        assert result.attributes["last_warning_by"] == "EMP-2"
        assert result.attributes["last_warning_at"] is not None

    def test_custom_message_used_when_given(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")

        result = device_management.send_warning(device.id, "EMP-2", message="Final notice.")
        assert result.attributes["last_warning_message"] == "Final notice."
        assert result.attributes["command_history"][-1]["action"] == "warning_sent"


# ---------------------------------------------------------------------------
# disable_starter()
# ---------------------------------------------------------------------------

class TestDisableStarter:

    def test_device_not_found(self):
        result = device_management.disable_starter("DEV-BOGUS", "EMP-1")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_removed_device_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")
        device_management.remove_device(device.id, "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-1")
        assert result == {"error": "Cannot issue a disable command to a removed device"}

    def test_not_armed_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-1")
        assert "must be armed before it can be disabled" in result["error"]

    def test_armed_but_no_warning_rejected_with_legal_notice(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-1")
        assert "A warning must be sent to the customer" in result["error"]
        assert NOT_LEGAL_ADVICE_NOTICE in result["error"]

    def test_already_disabled_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")
        device_management.disable_starter(device.id, "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-1")
        assert result == {"error": "Starter is already disabled"}

    def test_happy_path_requires_armed_and_warning_first(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")

        result = device_management.disable_starter(device.id, "EMP-2", reason="30 days delinquent")

        assert isinstance(result, Entity)
        assert result.attributes["starter_status"] == "disabled"
        assert result.attributes["command_history"][-1]["action"] == "disabled"
        assert result.attributes["command_history"][-1]["reason"] == "30 days delinquent"


# ---------------------------------------------------------------------------
# enable_starter()
# ---------------------------------------------------------------------------

class TestEnableStarter:

    def test_device_not_found(self):
        result = device_management.enable_starter("DEV-BOGUS", "EMP-1")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_already_enabled_rejected_on_a_fresh_device(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")

        result = device_management.enable_starter(device.id, "EMP-1")
        assert result == {"error": "Starter is already enabled"}

    def test_re_enable_does_not_require_a_warning(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")
        device_management.disable_starter(device.id, "EMP-1")

        result = device_management.enable_starter(device.id, "EMP-2", reason="Customer caught up on payments")

        assert isinstance(result, Entity)
        assert result.attributes["starter_status"] == "enabled"
        assert result.attributes["command_history"][-1]["action"] == "enabled"

    def test_double_enable_rejected(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")
        device_management.disable_starter(device.id, "EMP-1")
        device_management.enable_starter(device.id, "EMP-1")

        result = device_management.enable_starter(device.id, "EMP-1")
        assert result == {"error": "Starter is already enabled"}


# ---------------------------------------------------------------------------
# get_device_detail()
# ---------------------------------------------------------------------------

class TestGetDeviceDetail:

    def test_not_found(self):
        result = device_management.get_device_detail("DEV-BOGUS")
        assert result == {"error": "Device 'DEV-BOGUS' not found"}

    def test_active_device_has_location_and_notice(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")

        result = device_management.get_device_detail(device.id)

        assert result["id"] == device.id
        assert result["customer"]["id"] == "CUST-1"
        assert result["vehicle"]["id"] == "VEH-1"
        assert result["location"] is not None
        assert result["location"]["basis"] == device_management.SIMULATED_GPS_BASIS
        assert result["not_legal_advice_notice"] == NOT_LEGAL_ADVICE_NOTICE

    def test_removed_device_has_no_location(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        device_management.remove_device(device.id, "EMP-1")

        result = device_management.get_device_detail(device.id)
        assert result["location"] is None


# ---------------------------------------------------------------------------
# get_device_management_dashboard()
# ---------------------------------------------------------------------------

class TestGetDeviceManagementDashboard:

    def test_counts_across_a_mix_of_devices(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_customer("CUST-3")
        _add_vehicle("VEH-3")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")
        _add_loan("FIN-3", "CUST-3", "VEH-3")

        d1 = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        device_management.register_device("FIN-2", "gps_starter_interrupt", "SN2", "EMP-1")
        d3 = device_management.register_device("FIN-3", "gps_starter_interrupt", "SN3", "EMP-1")
        device_management.remove_device(d3.id, "EMP-1")

        result = device_management.get_device_management_dashboard()

        assert result["total_devices"] == 3
        assert result["active_devices"] == 2
        assert result["removed_devices"] == 1
        assert result["gps_only_count"] == 1
        assert result["gps_starter_interrupt_count"] == 1
        assert result["basis"] == device_management.SIMULATED_GPS_BASIS

    def test_empty_dashboard(self):
        result = device_management.get_device_management_dashboard()
        assert result["total_devices"] == 0
        assert result["active_devices"] == 0


# ---------------------------------------------------------------------------
# get_starter_interrupt_dashboard()
# ---------------------------------------------------------------------------

class TestGetStarterInterruptDashboard:

    def test_only_counts_active_starter_interrupt_capable_devices(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")

        device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")  # excluded, not SI-capable
        si_device = device_management.register_device("FIN-2", "gps_starter_interrupt", "SN2", "EMP-1")

        result = device_management.get_starter_interrupt_dashboard()
        assert result["starter_interrupt_capable_devices"] == 1
        assert result["devices"][0]["id"] == si_device.id
        assert result["not_legal_advice_notice"] == NOT_LEGAL_ADVICE_NOTICE

    def test_removed_starter_interrupt_device_excluded(self):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.remove_device(device.id, "EMP-1")

        result = device_management.get_starter_interrupt_dashboard()
        assert result["starter_interrupt_capable_devices"] == 0

    def test_armed_disabled_and_pending_warning_counts(self):
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")
        _add_customer("CUST-2")
        _add_vehicle("VEH-2")
        _add_customer("CUST-3")
        _add_vehicle("VEH-3")
        _add_loan("FIN-1", "CUST-1", "VEH-1")
        _add_loan("FIN-2", "CUST-2", "VEH-2")
        _add_loan("FIN-3", "CUST-3", "VEH-3")

        # Armed, no warning yet -- pending_warning
        pending = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(pending.id, "EMP-1")

        # Armed, warned, disabled -- disabled, and no longer pending_warning
        disabled = device_management.register_device("FIN-2", "gps_starter_interrupt", "SN2", "EMP-1")
        device_management.arm_starter_interrupt(disabled.id, "EMP-1")
        device_management.send_warning(disabled.id, "EMP-1")
        device_management.disable_starter(disabled.id, "EMP-1")

        # Never armed at all -- not counted anywhere
        device_management.register_device("FIN-3", "gps_starter_interrupt", "SN3", "EMP-1")

        result = device_management.get_starter_interrupt_dashboard()

        assert result["starter_interrupt_capable_devices"] == 3
        assert result["armed_count"] == 2
        assert result["disabled_count"] == 1
        assert result["pending_warning_count"] == 1
        pending_ids = {d["id"] for d in result["devices"] if d["id"] == pending.id}
        assert pending.id in pending_ids


# ---------------------------------------------------------------------------
# core/device_management_api.py -- ACL layer
# ---------------------------------------------------------------------------

_ALLOWED_ROLES = [ADMIN, OPERATIONS, FINANCE]
_DENIED_ROLES = [SALES, MARKETING, SERVICE]


class TestApiAcl:

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_register_device_allowed(self, role):
        _full_loan_setup()
        result = device_management_api.register_device_api(role, "EMP-1", "FIN-1", "gps_only", "SN1")
        assert "id" in result
        assert result["device_type"] == "gps_only"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_register_device_denied(self, role):
        _full_loan_setup()
        result = device_management_api.register_device_api(role, "EMP-1", "FIN-1", "gps_only", "SN1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_remove_device_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        result = device_management_api.remove_device_api(role, "EMP-1", device.id)
        assert result["status"] == "removed"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_remove_device_denied(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        result = device_management_api.remove_device_api(role, "EMP-1", device.id)
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_list_devices_allowed(self, role):
        result = device_management_api.list_devices_api(role)
        assert "count" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_list_devices_denied(self, role):
        result = device_management_api.list_devices_api(role)
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_simulated_location_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        result = device_management_api.get_simulated_location_api(role, device.id)
        assert "latitude" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_simulated_location_denied(self, role):
        result = device_management_api.get_simulated_location_api(role, "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_location_history_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        result = device_management_api.get_location_history_api(role, device.id)
        assert "entries" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_location_history_denied(self, role):
        result = device_management_api.get_location_history_api(role, "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_arm_starter_interrupt_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        result = device_management_api.arm_starter_interrupt_api(role, "EMP-1", device.id)
        assert result["starter_interrupt_armed"] is True

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_arm_starter_interrupt_denied(self, role):
        result = device_management_api.arm_starter_interrupt_api(role, "EMP-1", "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_send_warning_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        result = device_management_api.send_warning_api(role, "EMP-1", device.id)
        assert result["last_warning_at"] is not None

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_send_warning_denied(self, role):
        result = device_management_api.send_warning_api(role, "EMP-1", "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_disable_starter_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")

        result = device_management_api.disable_starter_api(role, "EMP-1", device.id)
        assert result["starter_status"] == "disabled"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_disable_starter_denied(self, role):
        result = device_management_api.disable_starter_api(role, "EMP-1", "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_enable_starter_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_starter_interrupt", "SN1", "EMP-1")
        device_management.arm_starter_interrupt(device.id, "EMP-1")
        device_management.send_warning(device.id, "EMP-1")
        device_management.disable_starter(device.id, "EMP-1")

        result = device_management_api.enable_starter_api(role, "EMP-1", device.id)
        assert result["starter_status"] == "enabled"

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_enable_starter_denied(self, role):
        result = device_management_api.enable_starter_api(role, "EMP-1", "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_device_detail_allowed(self, role):
        _full_loan_setup()
        device = device_management.register_device("FIN-1", "gps_only", "SN1", "EMP-1")
        result = device_management_api.get_device_detail_api(role, device.id)
        assert result["id"] == device.id

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_device_detail_denied(self, role):
        result = device_management_api.get_device_detail_api(role, "DEV-1")
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_device_management_dashboard_allowed(self, role):
        result = device_management_api.get_device_management_dashboard_api(role)
        assert "total_devices" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_device_management_dashboard_denied(self, role):
        result = device_management_api.get_device_management_dashboard_api(role)
        assert result == {"error": "You don't have access to Device Management"}

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_get_starter_interrupt_dashboard_allowed(self, role):
        result = device_management_api.get_starter_interrupt_dashboard_api(role)
        assert "starter_interrupt_capable_devices" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_get_starter_interrupt_dashboard_denied(self, role):
        result = device_management_api.get_starter_interrupt_dashboard_api(role)
        assert result == {"error": "You don't have access to Device Management"}
