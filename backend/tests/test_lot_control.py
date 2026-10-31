import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DAMAGE_REPORT
from core import lot_control
from core import lot_control_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(lot_control, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _add_vehicle(vehicle_id="VEH-1", sold=False, **overrides):
    attrs = {
        "VIN": "1HGCM82633A004352",
        "StockNumber": "S123",
        "Year": 2022,
        "Make": "Honda",
        "Model": "Accord",
        "Lot": "Main Lot",
    }
    if sold:
        attrs["DateSold"] = "2026-01-01"
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


# ---------------------------------------------------------------------------
# Lot Position / Lot Map
# ---------------------------------------------------------------------------


class TestLotPosition:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.set_lot_position("VEH-NOPE", "EMP-1", row="A")
        assert "error" in result

    def test_set_position_shape(self):
        _add_vehicle()
        result = lot_control.set_lot_position(
            "VEH-1", "EMP-1", row="A", space="12", section="North", notes="Near entrance"
        )
        assert result["lot_position"]["row"] == "A"
        assert result["lot_position"]["space"] == "12"
        assert result["lot_position"]["section"] == "North"
        assert result["lot_position"]["notes"] == "Near entrance"
        assert result["lot_position"]["updated_by"] == "EMP-1"
        assert result["lot_position"]["updated_at"] is not None

    def test_set_position_overwrites_prior(self):
        _add_vehicle()
        lot_control.set_lot_position("VEH-1", "EMP-1", row="A", space="1")
        result = lot_control.set_lot_position("VEH-1", "EMP-2", row="B", space="2")
        assert result["lot_position"]["row"] == "B"
        assert result["lot_position"]["updated_by"] == "EMP-2"

    def test_get_lot_position_unknown_vehicle(self):
        result = lot_control.get_lot_position("VEH-NOPE")
        assert "error" in result

    def test_get_lot_position_none_when_unset(self):
        _add_vehicle()
        result = lot_control.get_lot_position("VEH-1")
        assert result["lot_position"] is None

    def test_get_lot_position_reflects_set(self):
        _add_vehicle()
        lot_control.set_lot_position("VEH-1", "EMP-1", row="A")
        result = lot_control.get_lot_position("VEH-1")
        assert result["lot_position"]["row"] == "A"


class TestLotMap:
    def test_empty_state(self):
        result = lot_control.get_lot_map()
        assert result["by_lot"] == {}
        assert result["total_unsold"] == 0
        assert result["positioned_count"] == 0
        assert result["unpositioned_count"] == 0

    def test_groups_unsold_vehicles_by_lot(self):
        _add_vehicle("VEH-1", Lot="North Lot")
        _add_vehicle("VEH-2", Lot="South Lot")
        result = lot_control.get_lot_map()
        assert result["total_unsold"] == 2
        assert "North Lot" in result["by_lot"]
        assert "South Lot" in result["by_lot"]
        assert len(result["by_lot"]["North Lot"]) == 1

    def test_missing_lot_bucketed_unknown(self):
        _add_vehicle("VEH-1", Lot=None)
        result = lot_control.get_lot_map()
        assert "Unknown" in result["by_lot"]

    def test_sold_vehicle_excluded(self):
        _add_vehicle("VEH-1", sold=True)
        result = lot_control.get_lot_map()
        assert result["total_unsold"] == 0

    def test_positioned_vs_unpositioned_counts(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        lot_control.set_lot_position("VEH-1", "EMP-1", row="A")
        result = lot_control.get_lot_map()
        assert result["positioned_count"] == 1
        assert result["unpositioned_count"] == 1

    def test_vehicle_entry_includes_position(self):
        _add_vehicle("VEH-1")
        lot_control.set_lot_position("VEH-1", "EMP-1", row="A", space="9")
        result = lot_control.get_lot_map()
        entry = result["by_lot"]["Main Lot"][0]
        assert entry["vehicle_id"] == "VEH-1"
        assert entry["lot_position"]["row"] == "A"


# ---------------------------------------------------------------------------
# Key Management
# ---------------------------------------------------------------------------


class TestKeyCheckout:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.checkout_key("VEH-NOPE", "EMP-1", "EMP-1")
        assert "error" in result

    def test_checkout_shape(self):
        _add_vehicle()
        result = lot_control.checkout_key("VEH-1", "John Smith", "EMP-1", notes="Test drive")
        assert result["key_status"]["status"] == "checked_out"
        assert result["key_status"]["holder"] == "John Smith"
        assert len(result["log"]) == 1
        assert result["log"][0]["action"] == "checked_out"
        assert result["log"][0]["holder"] == "John Smith"
        assert result["log"][0]["notes"] == "Test drive"
        assert result["log"][0]["updated_by"] == "EMP-1"

    def test_double_checkout_rejected(self):
        _add_vehicle()
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        result = lot_control.checkout_key("VEH-1", "Jane Doe", "EMP-2")
        assert "error" in result
        assert "John Smith" in result["error"]

    def test_checkin_unknown_vehicle_rejected(self):
        result = lot_control.checkin_key("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_checkin_when_not_checked_out_rejected(self):
        _add_vehicle()
        result = lot_control.checkin_key("VEH-1", "EMP-1")
        assert "error" in result

    def test_checkin_after_checkout_succeeds(self):
        _add_vehicle()
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        result = lot_control.checkin_key("VEH-1", "EMP-2", notes="Returned")
        assert result["key_status"]["status"] == "on_lot"
        assert result["key_status"]["holder"] is None
        assert len(result["log"]) == 2
        assert result["log"][-1]["action"] == "checked_in"
        assert result["log"][-1]["holder"] == "John Smith"
        assert result["log"][-1]["notes"] == "Returned"

    def test_checkout_after_checkin_allowed_again(self):
        _add_vehicle()
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        lot_control.checkin_key("VEH-1", "EMP-1")
        result = lot_control.checkout_key("VEH-1", "Jane Doe", "EMP-2")
        assert result["key_status"]["status"] == "checked_out"
        assert result["key_status"]["holder"] == "Jane Doe"


class TestReportKeyMissing:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.report_key_missing("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_report_missing_shape(self):
        _add_vehicle()
        result = lot_control.report_key_missing("VEH-1", "EMP-1", notes="Not on the board")
        assert result["key_status"]["status"] == "missing"
        assert result["key_status"]["holder"] is None
        assert len(result["log"]) == 1
        assert result["log"][0]["action"] == "reported_missing"
        assert result["log"][0]["notes"] == "Not on the board"

    def test_report_missing_from_checked_out(self):
        _add_vehicle()
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        result = lot_control.report_key_missing("VEH-1", "EMP-2")
        assert result["key_status"]["status"] == "missing"
        assert len(result["log"]) == 2


class TestGetKeyStatus:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.get_key_status("VEH-NOPE")
        assert "error" in result

    def test_default_status_is_on_lot(self):
        _add_vehicle()
        result = lot_control.get_key_status("VEH-1")
        assert result["key_status"] == {"status": "on_lot", "holder": None}
        assert result["log"] == []

    def test_reflects_checked_out_state(self):
        _add_vehicle()
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        result = lot_control.get_key_status("VEH-1")
        assert result["key_status"]["status"] == "checked_out"
        assert len(result["log"]) == 1


class TestKeyBoard:
    def test_empty_state(self):
        result = lot_control.get_key_board()
        assert result["checked_out"] == []
        assert result["missing"] == []
        assert result["on_lot_count"] == 0

    def test_on_lot_count_default(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        result = lot_control.get_key_board()
        assert result["on_lot_count"] == 2

    def test_checked_out_bucket(self):
        _add_vehicle("VEH-1")
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        result = lot_control.get_key_board()
        assert len(result["checked_out"]) == 1
        assert result["checked_out"][0]["vehicle_id"] == "VEH-1"
        assert result["on_lot_count"] == 0

    def test_missing_bucket(self):
        _add_vehicle("VEH-1")
        lot_control.report_key_missing("VEH-1", "EMP-1")
        result = lot_control.get_key_board()
        assert len(result["missing"]) == 1
        assert result["on_lot_count"] == 0

    def test_sold_vehicle_excluded_from_board(self):
        _add_vehicle("VEH-1", sold=True)
        result = lot_control.get_key_board()
        assert result["on_lot_count"] == 0

    def test_mixed_states(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        _add_vehicle("VEH-3")
        lot_control.checkout_key("VEH-1", "John", "EMP-1")
        lot_control.report_key_missing("VEH-2", "EMP-1")
        result = lot_control.get_key_board()
        assert len(result["checked_out"]) == 1
        assert len(result["missing"]) == 1
        assert result["on_lot_count"] == 1


# ---------------------------------------------------------------------------
# Damage Reports
# ---------------------------------------------------------------------------


class TestReportDamage:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.report_damage("VEH-NOPE", "minor", "Scratch", "EMP-1")
        assert "error" in result

    def test_invalid_severity_rejected(self):
        _add_vehicle()
        result = lot_control.report_damage("VEH-1", "catastrophic", "Big dent", "EMP-1")
        assert "error" in result

    def test_valid_report_shape(self):
        _add_vehicle()
        result = lot_control.report_damage(
            "VEH-1", "moderate", "Dent on rear bumper", "EMP-1", estimated_cost=450.0
        )
        assert result["id"].startswith("DMG-")
        assert result["vehicle_id"] == "VEH-1"
        assert result["severity"] == "moderate"
        assert result["description"] == "Dent on rear bumper"
        assert result["estimated_cost"] == 450.0
        assert result["status"] == "open"
        assert result["reported_by"] == "EMP-1"
        assert result["reported_at"] is not None
        assert result["resolved_by"] is None
        assert result["resolution_notes"] == ""

    def test_estimated_cost_defaults_none(self):
        _add_vehicle()
        result = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        assert result["estimated_cost"] is None

    def test_multiple_reports_get_unique_ids(self):
        _add_vehicle()
        r1 = lot_control.report_damage("VEH-1", "minor", "Scratch 1", "EMP-1")
        r2 = lot_control.report_damage("VEH-1", "minor", "Scratch 2", "EMP-1")
        assert r1["id"] != r2["id"]

    def test_creates_real_entity_in_ledger(self):
        _add_vehicle()
        result = lot_control.report_damage("VEH-1", "severe", "Cracked windshield", "EMP-1")
        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == DAMAGE_REPORT


class TestUpdateDamageStatus:
    def test_unknown_report_rejected(self):
        result = lot_control.update_damage_status("DMG-NOPE", "in_repair", "EMP-1")
        assert "error" in result

    def test_invalid_status_rejected(self):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        result = lot_control.update_damage_status(r["id"], "bogus", "EMP-1")
        assert "error" in result

    def test_valid_status_transition(self):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        result = lot_control.update_damage_status(r["id"], "in_repair", "EMP-2")
        assert result["status"] == "in_repair"
        assert result["updated_by"] == "EMP-2"
        assert result["updated_at"] is not None

    def test_resolve_sets_resolution_fields(self):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        result = lot_control.update_damage_status(
            r["id"], "resolved", "EMP-2", resolution_notes="Buffed out"
        )
        assert result["status"] == "resolved"
        assert result["resolved_by"] == "EMP-2"
        assert result["resolved_at"] is not None
        assert result["resolution_notes"] == "Buffed out"

    def test_already_resolved_rejected(self):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        lot_control.update_damage_status(r["id"], "resolved", "EMP-2")
        result = lot_control.update_damage_status(r["id"], "in_repair", "EMP-3")
        assert "error" in result

    def test_non_resolved_transition_does_not_set_resolution_fields(self):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        result = lot_control.update_damage_status(r["id"], "in_repair", "EMP-2")
        assert result["resolved_by"] is None
        assert result["resolved_at"] is None


class TestListDamageReports:
    def test_empty_state(self):
        result = lot_control.list_damage_reports()
        assert result == {"count": 0, "reports": []}

    def test_all_reports_returned(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        lot_control.report_damage("VEH-2", "severe", "Broken glass", "EMP-1")
        result = lot_control.list_damage_reports()
        assert result["count"] == 2

    def test_filter_by_vehicle(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        lot_control.report_damage("VEH-2", "severe", "Broken glass", "EMP-1")
        result = lot_control.list_damage_reports(vehicle_id="VEH-1")
        assert result["count"] == 1
        assert result["reports"][0]["vehicle_id"] == "VEH-1"

    def test_filter_by_status(self):
        _add_vehicle()
        r1 = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        lot_control.report_damage("VEH-1", "severe", "Broken glass", "EMP-1")
        lot_control.update_damage_status(r1["id"], "resolved", "EMP-2")
        result = lot_control.list_damage_reports(status="resolved")
        assert result["count"] == 1
        assert result["reports"][0]["id"] == r1["id"]

    def test_sorted_most_recent_first(self):
        _add_vehicle()
        r1 = lot_control.report_damage("VEH-1", "minor", "First", "EMP-1")
        ledger.get_entity(r1["id"]).attributes["reported_at"] = "2026-01-01T00:00:00+00:00"
        r2 = lot_control.report_damage("VEH-1", "minor", "Second", "EMP-1")
        ledger.get_entity(r2["id"]).attributes["reported_at"] = "2026-06-01T00:00:00+00:00"
        result = lot_control.list_damage_reports()
        assert result["reports"][0]["id"] == r2["id"]
        assert result["reports"][1]["id"] == r1["id"]


# ---------------------------------------------------------------------------
# Showroom Assignment
# ---------------------------------------------------------------------------


class TestShowroomAssignment:
    def test_assign_unknown_vehicle_rejected(self):
        result = lot_control.assign_showroom("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_assign_shape(self):
        _add_vehicle()
        result = lot_control.assign_showroom("VEH-1", "EMP-1", notes="Featured display")
        assert result["showroom_assignment"]["assigned"] is True
        assert result["showroom_assignment"]["assigned_by"] == "EMP-1"
        assert result["showroom_assignment"]["assigned_at"] is not None
        assert result["showroom_assignment"]["notes"] == "Featured display"

    def test_remove_unknown_vehicle_rejected(self):
        result = lot_control.remove_showroom_assignment("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_remove_after_assign(self):
        _add_vehicle()
        lot_control.assign_showroom("VEH-1", "EMP-1")
        result = lot_control.remove_showroom_assignment("VEH-1", "EMP-2")
        assert result["showroom_assignment"]["assigned"] is False
        assert result["showroom_assignment"]["removed_by"] == "EMP-2"
        assert result["showroom_assignment"]["removed_at"] is not None

    def test_remove_without_prior_assign_still_succeeds(self):
        _add_vehicle()
        result = lot_control.remove_showroom_assignment("VEH-1", "EMP-1")
        assert result["showroom_assignment"]["assigned"] is False


class TestShowroomBoard:
    def test_empty_state(self):
        result = lot_control.get_showroom_board()
        assert result == {"count": 0, "vehicles": []}

    def test_only_assigned_vehicles_listed(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        lot_control.assign_showroom("VEH-1", "EMP-1")
        result = lot_control.get_showroom_board()
        assert result["count"] == 1
        assert result["vehicles"][0]["vehicle_id"] == "VEH-1"

    def test_removed_assignment_excluded(self):
        _add_vehicle("VEH-1")
        lot_control.assign_showroom("VEH-1", "EMP-1")
        lot_control.remove_showroom_assignment("VEH-1", "EMP-1")
        result = lot_control.get_showroom_board()
        assert result["count"] == 0

    def test_sold_vehicle_excluded(self):
        _add_vehicle("VEH-1", sold=True)
        lot_control.assign_showroom("VEH-1", "EMP-1")
        result = lot_control.get_showroom_board()
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# Check-In / QR Scans
# ---------------------------------------------------------------------------


class TestScanLog:
    def test_log_scan_unknown_vehicle_rejected(self):
        result = lot_control.log_scan("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_log_scan_shape(self):
        _add_vehicle()
        result = lot_control.log_scan("VEH-1", "EMP-1", location_note="Front row")
        assert len(result["scan_log"]) == 1
        assert result["scan_log"][0]["scanned_by"] == "EMP-1"
        assert result["scan_log"][0]["location_note"] == "Front row"
        assert result["scan_log"][0]["at"] is not None

    def test_multiple_scans_accumulate(self):
        _add_vehicle()
        lot_control.log_scan("VEH-1", "EMP-1")
        lot_control.log_scan("VEH-1", "EMP-2")
        result = lot_control.log_scan("VEH-1", "EMP-3")
        assert len(result["scan_log"]) == 3

    def test_get_scan_log_unknown_vehicle_rejected(self):
        result = lot_control.get_scan_log("VEH-NOPE")
        assert "error" in result

    def test_get_scan_log_empty_default(self):
        _add_vehicle()
        result = lot_control.get_scan_log("VEH-1")
        assert result["scan_log"] == []

    def test_get_scan_log_reflects_logged_scans(self):
        _add_vehicle()
        lot_control.log_scan("VEH-1", "EMP-1")
        result = lot_control.get_scan_log("VEH-1")
        assert len(result["scan_log"]) == 1


# ---------------------------------------------------------------------------
# Composed view
# ---------------------------------------------------------------------------


class TestLotControlView:
    def test_unknown_vehicle_rejected(self):
        result = lot_control.get_lot_control_view("VEH-NOPE")
        assert "error" in result

    def test_defaults_when_nothing_logged(self):
        _add_vehicle()
        result = lot_control.get_lot_control_view("VEH-1")
        assert result["vehicle"]["vehicle_id"] == "VEH-1"
        assert result["lot_position"] is None
        assert result["key_status"] == {"status": "on_lot", "holder": None}
        assert result["key_log"] == []
        assert result["damage_reports"] == []
        assert result["showroom_assignment"] is None
        assert result["scan_log"] == []

    def test_composes_all_real_data(self):
        _add_vehicle()
        lot_control.set_lot_position("VEH-1", "EMP-1", row="A", space="3")
        lot_control.checkout_key("VEH-1", "John Smith", "EMP-1")
        lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        lot_control.assign_showroom("VEH-1", "EMP-1")
        lot_control.log_scan("VEH-1", "EMP-1")

        result = lot_control.get_lot_control_view("VEH-1")
        assert result["lot_position"]["row"] == "A"
        assert result["key_status"]["status"] == "checked_out"
        assert len(result["key_log"]) == 1
        assert len(result["damage_reports"]) == 1
        assert result["showroom_assignment"]["assigned"] is True
        assert len(result["scan_log"]) == 1

    def test_damage_reports_scoped_to_this_vehicle_only(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        lot_control.report_damage("VEH-2", "severe", "Broken glass", "EMP-1")
        result = lot_control.get_lot_control_view("VEH-1")
        assert result["damage_reports"] == []


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS, SERVICE]
_MUTATE_DENIED = [SALES, MARKETING, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_lot_map_denied(self, role):
        result = lot_control_api.get_lot_map_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_lot_map_allowed(self, role):
        result = lot_control_api.get_lot_map_api(role)
        assert "by_lot" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_lot_control_view_denied(self, role):
        _add_vehicle()
        result = lot_control_api.get_lot_control_view_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_lot_control_view_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.get_lot_control_view_api(role, "VEH-1")
        assert "vehicle" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_set_lot_position_denied(self, role):
        _add_vehicle()
        result = lot_control_api.set_lot_position_api(role, "EMP-1", "VEH-1", row="A")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_set_lot_position_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.set_lot_position_api(role, "EMP-1", "VEH-1", row="A")
        assert result["lot_position"]["row"] == "A"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_lot_position_denied(self, role):
        _add_vehicle()
        result = lot_control_api.get_lot_position_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_checkout_key_denied(self, role):
        _add_vehicle()
        result = lot_control_api.checkout_key_api(role, "EMP-1", "VEH-1", "John Smith")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_checkout_key_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.checkout_key_api(role, "EMP-1", "VEH-1", "John Smith")
        assert result["key_status"]["status"] == "checked_out"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_checkin_key_denied(self, role):
        _add_vehicle()
        result = lot_control_api.checkin_key_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_report_key_missing_denied(self, role):
        _add_vehicle()
        result = lot_control_api.report_key_missing_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_key_status_denied(self, role):
        _add_vehicle()
        result = lot_control_api.get_key_status_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_key_board_denied(self, role):
        result = lot_control_api.get_key_board_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_key_board_allowed(self, role):
        result = lot_control_api.get_key_board_api(role)
        assert "checked_out" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_report_damage_denied(self, role):
        _add_vehicle()
        result = lot_control_api.report_damage_api(role, "EMP-1", "VEH-1", "minor", "Scratch")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_report_damage_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.report_damage_api(role, "EMP-1", "VEH-1", "minor", "Scratch")
        assert result["status"] == "open"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_damage_status_denied(self, role):
        _add_vehicle()
        r = lot_control.report_damage("VEH-1", "minor", "Scratch", "EMP-1")
        result = lot_control_api.update_damage_status_api(role, "EMP-1", r["id"], "in_repair")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_list_damage_reports_denied(self, role):
        result = lot_control_api.list_damage_reports_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_list_damage_reports_allowed(self, role):
        result = lot_control_api.list_damage_reports_api(role)
        assert result == {"count": 0, "reports": []}

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_assign_showroom_denied(self, role):
        _add_vehicle()
        result = lot_control_api.assign_showroom_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_assign_showroom_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.assign_showroom_api(role, "EMP-1", "VEH-1")
        assert result["showroom_assignment"]["assigned"] is True

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_remove_showroom_assignment_denied(self, role):
        _add_vehicle()
        result = lot_control_api.remove_showroom_assignment_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_showroom_board_denied(self, role):
        result = lot_control_api.get_showroom_board_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_showroom_board_allowed(self, role):
        result = lot_control_api.get_showroom_board_api(role)
        assert result == {"count": 0, "vehicles": []}

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_log_scan_denied(self, role):
        _add_vehicle()
        result = lot_control_api.log_scan_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_log_scan_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.log_scan_api(role, "EMP-1", "VEH-1")
        assert len(result["scan_log"]) == 1

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_scan_log_denied(self, role):
        _add_vehicle()
        result = lot_control_api.get_scan_log_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_scan_log_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = lot_control_api.get_scan_log_api(role, "VEH-1")
        assert result["scan_log"] == []

def test_missing_key_can_be_found_and_checked_in_with_audit_history():
    _add_vehicle('VEH-FOUND')
    lot_control.report_key_missing('VEH-FOUND','EMP-1')
    result=lot_control.checkin_key('VEH-FOUND','EMP-2','Found in service')
    assert result['key_status']['status']=='on_lot'
    assert result['log'][-1]['previous_status']=='missing'
    assert result['log'][-1]['updated_by']=='EMP-2'
    assert result['log'][-1]['notes']=='Found in service'
    assert lot_control.get_key_status('VEH-FOUND')['key_status']['status']=='on_lot'
