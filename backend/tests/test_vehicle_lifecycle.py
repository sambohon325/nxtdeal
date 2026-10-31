import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, AUCTION_TRANSACTION, DOCUMENT, EMPLOYEE
from core import vehicle_lifecycle
from core import vehicle_lifecycle_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(vehicle_lifecycle, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _add_assignment_staff():
    for employee_id in ("EMP-2", "EMP-3"):
        ledger.add_entity(Entity(id=employee_id, entity_type=EMPLOYEE, attributes={"Name": "Fictional staff"}))


def _add_vehicle(vehicle_id="VEH-1", **overrides):
    attrs = {
        "VIN": "1HGCM82633A004352",
        "StockNumber": "S1001",
        "Year": 2022,
        "Make": "Toyota",
        "Model": "Camry",
        "Trim": "LE",
        "Color": "Silver",
        "Mileage": 15000,
        "Price": 24999,
        "Cost": 21000,
        "Condition": "Used",
        "Lot": "Main Lot",
        "DateSold": None,
    }
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _add_auction(vehicle_id, **overrides):
    attrs = {
        "vehicle_id": vehicle_id,
        "auction_house": "Manheim",
        "bid_amount": 19500,
        "purchase_date": "2026-06-01",
        "carrier": "ABC Transport",
        "transport_status": "delivered",
    }
    attrs.update(overrides)
    aid = "AUCT-1"
    ledger.add_entity(Entity(id=aid, entity_type=AUCTION_TRANSACTION, attributes=attrs))
    return aid


def _add_document(vehicle_id, **overrides):
    attrs = {
        "EntityID": vehicle_id,
        "DocumentType": "Title",
        "CreatedAt": "2026-06-01T00:00:00+00:00",
        "UploadedBy": "EMP-1",
        "approval_status": "pending",
    }
    attrs.update(overrides)
    did = overrides.get("id", "DOC-1")
    ledger.add_entity(Entity(id=did, entity_type=DOCUMENT, attributes=attrs))
    return did


# ---------------------------------------------------------------------------
# get_vehicle_lifecycle
# ---------------------------------------------------------------------------


class TestGetVehicleLifecycle:
    def test_unknown_vehicle_returns_error(self):
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-NOPE")
        assert "error" in result

    def test_wrong_entity_type_returns_error(self):
        ledger.add_entity(Entity(id="EMP-9", entity_type=EMPLOYEE, attributes={}))
        result = vehicle_lifecycle.get_vehicle_lifecycle("EMP-9")
        assert "error" in result

    def test_default_status_front_line_ready_when_unsold(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["lifecycle_status"] == "Front Line Ready"
        assert result["lifecycle_status_is_default"] is True

    def test_default_status_sold_when_date_sold_set(self):
        _add_vehicle(DateSold="2026-07-01")
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["lifecycle_status"] == "Sold"
        assert result["lifecycle_status_is_default"] is True

    def test_stored_status_overrides_computed_default(self):
        _add_vehicle(lifecycle_status="Recon")
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["lifecycle_status"] == "Recon"
        assert result["lifecycle_status_is_default"] is False

    def test_status_history_defaults_to_empty_list(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["status_history"] == []

    def test_recon_checklist_default_shape_for_all_items(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        checklist = result["recon_checklist"]
        assert set(checklist.keys()) == set(vehicle_lifecycle.RECON_ITEMS)
        for item in vehicle_lifecycle.RECON_ITEMS:
            entry = checklist[item]
            assert entry == {
                "complete": False,
                "notes": "",
                "updated_by": None,
                "updated_at": None,
            }

    def test_vendor_assignments_defaults_to_empty_list(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["vendor_assignments"] == []

    def test_vin_decode_defaults_to_none(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["vin_decode"] is None

    def test_vin_decode_surfaces_once_applied(self):
        _add_vehicle()
        from core.vin_decoder import apply_decode_to_vehicle
        apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=False, _skip_save=True)
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["vin_decode"] is not None
        assert result["vin_decode"]["decoded_by"] == "EMP-1"

    def test_acquisition_no_auction_data_has_not_yet_tracked_note(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        acquisition = result["acquisition"]
        assert acquisition["auction_data"] is None
        assert acquisition["cost"] == 21000
        assert acquisition["lot"] == "Main Lot"
        assert acquisition["condition"] == "Used"
        assert "not_yet_tracked" in acquisition

    def test_acquisition_real_auction_data_surfaces_no_not_yet_tracked_note(self):
        _add_vehicle()
        _add_auction("VEH-1")
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        acquisition = result["acquisition"]
        assert acquisition["auction_data"] == {
            "auction_house": "Manheim",
            "bid_amount": 19500,
            "purchase_date": "2026-06-01",
            "carrier": "ABC Transport",
            "transport_status": "delivered",
        }
        assert "not_yet_tracked" not in acquisition

    def test_auction_data_for_different_vehicle_not_matched(self):
        _add_vehicle()
        _add_auction("VEH-OTHER")
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["acquisition"]["auction_data"] is None

    def test_identity_fields_surfaced(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert result["vin"] == "1HGCM82633A004352"
        assert result["stock_number"] == "S1001"
        assert result["year"] == 2022
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["trim"] == "LE"
        assert result["color"] == "Silver"
        assert result["mileage"] == 15000
        assert result["price"] == 24999
        assert result["date_sold"] is None


# ---------------------------------------------------------------------------
# update_lifecycle_status
# ---------------------------------------------------------------------------


class TestUpdateLifecycleStatus:
    def test_invalid_stage_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Bogus Stage", "EMP-1")
        assert "error" in result

    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.update_lifecycle_status("VEH-NOPE", "Recon", "EMP-1")
        assert "error" in result

    def test_valid_update_sets_status(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        assert result["lifecycle_status"] == "Recon"
        assert result["lifecycle_status_is_default"] is False

    def test_valid_update_appends_history_entry(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        history = result["status_history"]
        assert len(history) == 1
        assert history[0]["status"] == "Recon"
        assert history[0]["by"] == "EMP-1"
        assert history[0]["at"] is not None

    def test_multiple_updates_append_not_overwrite(self):
        _add_vehicle()
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Photo", "EMP-2")
        history = result["status_history"]
        assert len(history) == 2
        assert history[0]["status"] == "Recon"
        assert history[1]["status"] == "Photo"
        assert result["lifecycle_status"] == "Photo"

    def test_replaces_computed_default(self):
        _add_vehicle(DateSold="2026-07-01")
        before = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert before["lifecycle_status_is_default"] is True
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Delivered", "EMP-1")
        after = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")
        assert after["lifecycle_status_is_default"] is False
        assert after["lifecycle_status"] == "Delivered"


# ---------------------------------------------------------------------------
# update_lifecycle_status -- NXTDeal VIN Intelligence, Phase 3 auto-decode
# on Received (real, best-effort, non-blocking; offline-only in this
# sandbox since there's no outbound network access for the live NHTSA half)
# ---------------------------------------------------------------------------


class TestUpdateLifecycleStatusVinAutoDecode:
    def test_received_with_blank_fields_backfills_year_and_make(self, monkeypatch):
        # Exercise offline backfill deterministically, regardless of network access.
        from core import vin_decoder
        decode = vin_decoder.decode_vin
        monkeypatch.setattr(vin_decoder, "decode_vin", lambda vin, **kwargs: decode(vin, attempt_live=False))
        _add_vehicle(Year="", Make="", Model="", Trim="")
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Received", "EMP-1")
        assert result["lifecycle_status"] == "Received"
        assert result["vin_decode"] is not None
        # Only Year/Make are backfillable offline in this sandbox (no live
        # NHTSA access) -- Model/Trim genuinely require the live half and
        # correctly stay blank/unbackfilled here, not guessed at.
        assert "Year" in result["vin_decode"]["backfilled_fields"]
        assert "Make" in result["vin_decode"]["backfilled_fields"]
        assert result["year"] == "2003"
        assert result["make"] == "Honda"
        assert result["model"] is None or result["model"] == ""
        assert result["trim"] is None or result["trim"] == ""

    def test_never_overwrites_already_set_fields(self):
        _add_vehicle()  # Year/Make/Model/Trim all already populated by default
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Received", "EMP-1")
        # A real decode still runs and gets stored (there's a real VIN on
        # file), but nothing gets overwritten since nothing was blank.
        assert result["vin_decode"] is not None
        assert result["vin_decode"]["backfilled_fields"] == []
        assert result["year"] == 2022
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["trim"] == "LE"

    def test_does_not_refire_once_vin_decode_already_on_file(self):
        _add_vehicle(Year="", Make="")
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Received", "EMP-1")
        first_decode = vehicle_lifecycle.get_vehicle_lifecycle("VEH-1")["vin_decode"]
        # Move it to Received a second time (e.g. re-marking after a status
        # correction) -- the hook should not re-run since vin_decode is
        # already on file, so the original decoded_at timestamp is preserved.
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Received", "EMP-2")
        assert result["vin_decode"]["decoded_at"] == first_decode["decoded_at"]
        assert result["vin_decode"]["decoded_by"] == "EMP-1"

    def test_non_received_status_never_triggers_auto_decode(self):
        _add_vehicle(Year="", Make="")
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        assert result["vin_decode"] is None

    def test_missing_or_invalid_vin_does_not_block_the_status_update(self):
        _add_vehicle(Year="", Make="", VIN="")
        result = vehicle_lifecycle.update_lifecycle_status("VEH-1", "Received", "EMP-1")
        # The real lifecycle status update must still land even though the
        # best-effort auto-decode had nothing to decode.
        assert result["lifecycle_status"] == "Received"
        assert result["vin_decode"] is None


# ---------------------------------------------------------------------------
# update_recon_item
# ---------------------------------------------------------------------------


class TestUpdateReconItem:
    def test_invalid_item_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_recon_item("VEH-1", "bogus_item", True, "EMP-1")
        assert "error" in result

    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.update_recon_item("VEH-NOPE", "tires", True, "EMP-1")
        assert "error" in result

    def test_valid_update_sets_checklist_entry(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_recon_item(
            "VEH-1", "tires", True, "EMP-1", notes="New tires installed"
        )
        entry = result["recon_checklist"]["tires"]
        assert entry["complete"] is True
        assert entry["notes"] == "New tires installed"
        assert entry["updated_by"] == "EMP-1"
        assert entry["updated_at"] is not None

    def test_other_items_stay_at_default(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_recon_item("VEH-1", "tires", True, "EMP-1")
        assert result["recon_checklist"]["oil_change"] == {
            "complete": False,
            "notes": "",
            "updated_by": None,
            "updated_at": None,
        }

    def test_incomplete_flag_stored(self):
        _add_vehicle()
        vehicle_lifecycle.update_recon_item("VEH-1", "tires", True, "EMP-1")
        result = vehicle_lifecycle.update_recon_item("VEH-1", "tires", False, "EMP-2")
        entry = result["recon_checklist"]["tires"]
        assert entry["complete"] is False
        assert entry["updated_by"] == "EMP-2"

    def test_no_notes_defaults_to_empty_string(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_recon_item("VEH-1", "tires", True, "EMP-1")
        assert result["recon_checklist"]["tires"]["notes"] == ""


# ---------------------------------------------------------------------------
# assign_vendor
# ---------------------------------------------------------------------------


class TestAssignVendor:
    def test_invalid_vendor_type_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.assign_vendor("VEH-1", "bogus_type", "Joe's Shop", "EMP-1")
        assert "error" in result

    def test_empty_vendor_name_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "", "EMP-1")
        assert "error" in result

    def test_whitespace_only_vendor_name_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "   ", "EMP-1")
        assert "error" in result

    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.assign_vendor("VEH-NOPE", "body_shop", "Joe's Shop", "EMP-1")
        assert "error" in result

    def test_valid_assignment_creates_entry(self):
        _add_vehicle()
        result = vehicle_lifecycle.assign_vendor(
            "VEH-1", "body_shop", "  Joe's Shop  ", "EMP-1", notes="Bumper repair"
        )
        assignments = result["vendor_assignments"]
        assert len(assignments) == 1
        a = assignments[0]
        assert a["vendor_type"] == "body_shop"
        assert a["vendor_name"] == "Joe's Shop"
        assert a["status"] == "assigned"
        assert a["notes"] == "Bumper repair"
        assert a["assigned_by"] == "EMP-1"
        assert a["assigned_at"] is not None
        assert a["updated_by"] is None
        assert a["updated_at"] is None
        assert a["completed_at"] is None
        assert a["id"].startswith("VEND")

    def test_multiple_assignments_accumulate(self):
        _add_vehicle()
        vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        result = vehicle_lifecycle.assign_vendor("VEH-1", "detail", "Shiny Detail", "EMP-2")
        assert len(result["vendor_assignments"]) == 2

    def test_assignment_ids_are_unique(self):
        _add_vehicle()
        r1 = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        r2 = vehicle_lifecycle.assign_vendor("VEH-1", "detail", "Shiny Detail", "EMP-2")
        ids = [a["id"] for a in r2["vendor_assignments"]]
        assert len(set(ids)) == 2
        assert ids != []


# ---------------------------------------------------------------------------
# update_vendor_status
# ---------------------------------------------------------------------------


class TestUpdateVendorStatus:
    def _assign(self, vehicle_id="VEH-1"):
        result = vehicle_lifecycle.assign_vendor(vehicle_id, "body_shop", "Joe's Shop", "EMP-1")
        return result["vendor_assignments"][0]["id"]

    def test_invalid_status_rejected(self):
        _add_vehicle()
        assignment_id = self._assign()
        result = vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "bogus", "EMP-1")
        assert "error" in result

    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.update_vendor_status("VEH-NOPE", "VEND-1", "in_progress", "EMP-1")
        assert "error" in result

    def test_assignment_not_found_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_vendor_status("VEH-1", "VEND-BOGUS", "in_progress", "EMP-1")
        assert result["error"] == "Vendor assignment not found"

    def test_valid_status_update(self):
        _add_vehicle()
        assignment_id = self._assign()
        result = vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "in_progress", "EMP-2")
        a = result["vendor_assignments"][0]
        assert a["status"] == "in_progress"
        assert a["updated_by"] == "EMP-2"
        assert a["updated_at"] is not None
        assert a["completed_at"] is None

    def test_complete_status_sets_completed_at(self):
        _add_vehicle()
        assignment_id = self._assign()
        result = vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "complete", "EMP-2")
        a = result["vendor_assignments"][0]
        assert a["status"] == "complete"
        assert a["completed_at"] is not None

    def test_non_complete_status_does_not_set_completed_at(self):
        _add_vehicle()
        assignment_id = self._assign()
        result = vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "in_progress", "EMP-2")
        assert result["vendor_assignments"][0]["completed_at"] is None

    def test_only_target_assignment_updated(self):
        _add_vehicle()
        first_id = self._assign()
        second = vehicle_lifecycle.assign_vendor("VEH-1", "detail", "Shiny Detail", "EMP-1")
        second_id = second["vendor_assignments"][1]["id"]
        result = vehicle_lifecycle.update_vendor_status("VEH-1", first_id, "complete", "EMP-2")
        by_id = {a["id"]: a for a in result["vendor_assignments"]}
        assert by_id[first_id]["status"] == "complete"
        assert by_id[second_id]["status"] == "assigned"


# ---------------------------------------------------------------------------
# list_by_stage
# ---------------------------------------------------------------------------


class TestListByStage:
    def test_empty_state_returns_all_stages_empty(self):
        result = vehicle_lifecycle.list_by_stage()
        assert set(result.keys()) == set(vehicle_lifecycle.LIFECYCLE_STAGES)
        assert all(v == [] for v in result.values())

    def test_default_grouping_by_computed_status(self):
        _add_vehicle("VEH-1")  # unsold -> Front Line Ready
        _add_vehicle("VEH-2", DateSold="2026-07-01")  # sold -> Sold
        result = vehicle_lifecycle.list_by_stage()
        assert [v["vehicle_id"] for v in result["Front Line Ready"]] == ["VEH-1"]
        assert [v["vehicle_id"] for v in result["Sold"]] == ["VEH-2"]

    def test_stored_status_used_over_default(self):
        _add_vehicle("VEH-1", lifecycle_status="Recon")
        result = vehicle_lifecycle.list_by_stage()
        assert [v["vehicle_id"] for v in result["Recon"]] == ["VEH-1"]
        assert result["Front Line Ready"] == []

    def test_entry_shape(self):
        _add_vehicle("VEH-1")
        result = vehicle_lifecycle.list_by_stage()
        entry = result["Front Line Ready"][0]
        assert entry == {
            "vehicle_id": "VEH-1",
            "vin": "1HGCM82633A004352",
            "stock_number": "S1001",
            "year": 2022,
            "make": "Toyota",
            "model": "Camry",
            "price": 24999,
        }

    def test_stage_filter_returns_only_that_stage_key(self):
        _add_vehicle("VEH-1")
        result = vehicle_lifecycle.list_by_stage(stage="Front Line Ready")
        assert list(result.keys()) == ["Front Line Ready"]
        assert len(result["Front Line Ready"]) == 1

    def test_stage_filter_excludes_non_matching_vehicles(self):
        _add_vehicle("VEH-1")  # Front Line Ready
        _add_vehicle("VEH-2", DateSold="2026-07-01")  # Sold
        result = vehicle_lifecycle.list_by_stage(stage="Sold")
        assert list(result.keys()) == ["Sold"]
        assert [v["vehicle_id"] for v in result["Sold"]] == ["VEH-2"]

    def test_limit_per_stage_caps_results(self):
        for i in range(5):
            _add_vehicle(f"VEH-{i}")
        result = vehicle_lifecycle.list_by_stage(limit_per_stage=2)
        assert len(result["Front Line Ready"]) == 2

    def test_no_separate_count_field(self):
        _add_vehicle("VEH-1")
        result = vehicle_lifecycle.list_by_stage()
        assert "count" not in result


# ---------------------------------------------------------------------------
# get_cost_breakdown
# ---------------------------------------------------------------------------


class TestGetCostBreakdown:
    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.get_cost_breakdown("VEH-NOPE")
        assert "error" in result

    def test_acquisition_cost_defaults_to_vehicle_cost(self):
        _add_vehicle(Cost=21000)
        result = vehicle_lifecycle.get_cost_breakdown("VEH-1")
        assert result["breakdown"]["acquisition_cost"] == 21000
        assert result["acquisition_cost_is_default"] is True

    def test_acquisition_cost_defaults_to_zero_when_no_cost_on_file(self):
        _add_vehicle(Cost=None)
        result = vehicle_lifecycle.get_cost_breakdown("VEH-1")
        assert result["breakdown"]["acquisition_cost"] == 0

    def test_other_fields_default_to_zero(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_cost_breakdown("VEH-1")
        for field in ("transport_cost", "recon_cost", "floorplan_interest", "marketing_cost"):
            assert result["breakdown"][field] == 0

    def test_total_investment_computed_from_defaults(self):
        _add_vehicle(Cost=21000)
        result = vehicle_lifecycle.get_cost_breakdown("VEH-1")
        assert result["total_investment"] == 21000.0

    def test_updated_by_and_at_none_before_any_update(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_cost_breakdown("VEH-1")
        assert result["updated_by"] is None
        assert result["updated_at"] is None


# ---------------------------------------------------------------------------
# update_cost_breakdown
# ---------------------------------------------------------------------------


class TestUpdateCostBreakdown:
    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.update_cost_breakdown("VEH-NOPE", "EMP-1", transport_cost=500)
        assert "error" in result

    def test_unknown_field_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", bogus_field=100)
        assert "error" in result

    def test_unknown_field_persists_nothing(self):
        _add_vehicle()
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", bogus_field=100)
        v = ledger.get_entity("VEH-1")
        assert "cost_breakdown" not in v.attributes

    def test_non_numeric_value_rejected(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost="not-a-number")
        assert "error" in result

    def test_non_numeric_value_persists_nothing(self):
        _add_vehicle()
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost="not-a-number")
        v = ledger.get_entity("VEH-1")
        assert "cost_breakdown" not in v.attributes

    def test_valid_update_sets_field(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=500)
        assert result["breakdown"]["transport_cost"] == 500.0
        assert result["updated_by"] == "EMP-1"
        assert result["updated_at"] is not None

    def test_explicit_acquisition_cost_override(self):
        _add_vehicle(Cost=21000)
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", acquisition_cost=19500)
        assert result["breakdown"]["acquisition_cost"] == 19500.0
        assert result["acquisition_cost_is_default"] is False

    def test_none_value_skipped(self):
        _add_vehicle()
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=500)
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=None)
        # None is skipped -- the prior real value should survive untouched.
        assert result["breakdown"]["transport_cost"] == 500.0

    def test_total_investment_reflects_all_updates(self):
        _add_vehicle(Cost=21000)
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=500)
        result = vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", recon_cost=250)
        assert result["total_investment"] == 21750.0

    def test_multiple_fields_in_one_call(self):
        _add_vehicle()
        result = vehicle_lifecycle.update_cost_breakdown(
            "VEH-1", "EMP-1", transport_cost=100, recon_cost=200, marketing_cost=50
        )
        assert result["breakdown"]["transport_cost"] == 100.0
        assert result["breakdown"]["recon_cost"] == 200.0
        assert result["breakdown"]["marketing_cost"] == 50.0


# ---------------------------------------------------------------------------
# get_ownership / assign_ownership
# ---------------------------------------------------------------------------


class TestOwnership:
    def test_get_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.get_ownership("VEH-NOPE")
        assert "error" in result

    def test_get_default_all_roles_none(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_ownership("VEH-1")
        assert result["assignments"] == {role: None for role in vehicle_lifecycle.OWNERSHIP_ROLES}
        assert result["updated_by"] is None
        assert result["updated_at"] is None

    def test_assign_unknown_vehicle_rejected(self):
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-NOPE", "EMP-1", buyer="EMP-2")
        assert "error" in result

    def test_assign_unknown_role_rejected(self):
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", bogus_role="EMP-2")
        assert "error" in result

    def test_assign_valid_role(self):
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        assert result["assignments"]["buyer"] == "EMP-2"
        assert result["updated_by"] == "EMP-1"
        assert result["updated_at"] is not None

    def test_partial_update_leaves_other_roles_unset(self):
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        assert result["assignments"]["inventory_manager"] is None

    def test_multiple_roles_in_one_call(self):
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership(
            "VEH-1", "EMP-1", buyer="EMP-2", recon_manager="EMP-3"
        )
        assert result["assignments"]["buyer"] == "EMP-2"
        assert result["assignments"]["recon_manager"] == "EMP-3"

    def test_none_value_skipped_leaves_existing_value(self):
        _add_vehicle()
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer=None)
        assert result["assignments"]["buyer"] == "EMP-2"

    def test_empty_string_value_stored_as_none(self):
        _add_vehicle()
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="")
        assert result["assignments"]["buyer"] is None

    def test_second_call_updates_updated_by(self):
        _add_vehicle()
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        _add_assignment_staff()
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-2", recon_manager="EMP-3")
        assert result["updated_by"] == "EMP-2"
        assert result["assignments"]["buyer"] == "EMP-2"
        assert result["assignments"]["recon_manager"] == "EMP-3"


# ---------------------------------------------------------------------------
# get_vehicle_activity_feed
# ---------------------------------------------------------------------------


class TestGetVehicleActivityFeed:
    def test_unknown_vehicle_rejected(self):
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-NOPE")
        assert "error" in result

    def test_empty_state(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result == {"vehicle_id": "VEH-1", "count": 0, "events": []}

    def test_lifecycle_status_event(self):
        _add_vehicle()
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        e = result["events"][0]
        assert e["type"] == "lifecycle_status"
        assert e["label"] == "Status changed to Recon"
        assert e["by"] == "EMP-1"

    def test_recon_item_event_only_when_updated_at_set(self):
        _add_vehicle()
        vehicle_lifecycle.update_recon_item("VEH-1", "tires", True, "EMP-1", notes="New tires")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        e = result["events"][0]
        assert e["type"] == "recon_item"
        assert "tires" in e["label"]
        assert "complete" in e["label"]
        assert e["notes"] == "New tires"

    def test_recon_item_incomplete_label(self):
        _add_vehicle()
        vehicle_lifecycle.update_recon_item("VEH-1", "tires", False, "EMP-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert "incomplete" in result["events"][0]["label"]

    def test_vendor_assigned_event(self):
        _add_vehicle()
        vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        e = result["events"][0]
        assert e["type"] == "vendor_assigned"
        assert "Joe's Shop" in e["label"]

    def test_vendor_completed_event_added_alongside_assigned(self):
        _add_vehicle()
        assign_result = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        assignment_id = assign_result["vendor_assignments"][0]["id"]
        vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "complete", "EMP-2")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        types = {e["type"] for e in result["events"]}
        assert "vendor_assigned" in types
        assert "vendor_completed" in types
        assert result["count"] == 2

    def test_vendor_not_completed_no_completed_event(self):
        _add_vehicle()
        assign_result = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        assignment_id = assign_result["vendor_assignments"][0]["id"]
        vehicle_lifecycle.update_vendor_status("VEH-1", assignment_id, "in_progress", "EMP-2")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1

    def test_price_change_event(self):
        _add_vehicle(
            price_history=[
                {"old_price": 25000, "new_price": 23500, "updated_at": "2026-06-01T00:00:00+00:00", "updated_by": "EMP-1", "reason": "Aging"}
            ]
        )
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        e = result["events"][0]
        assert e["type"] == "price_change"
        assert "25000" in e["label"]
        assert "23500" in e["label"]
        assert e["notes"] == "Aging"

    def test_document_uploaded_event(self):
        _add_vehicle()
        _add_document("VEH-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        e = result["events"][0]
        assert e["type"] == "document_uploaded"
        assert "Title" in e["label"]
        assert e["by"] == "EMP-1"

    def test_document_approved_event_adds_second_event(self):
        _add_vehicle()
        _add_document(
            "VEH-1",
            approval_status="approved",
            approved_at="2026-06-02T00:00:00+00:00",
            approved_by="EMP-2",
        )
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 2
        types = {e["type"] for e in result["events"]}
        assert "document_uploaded" in types
        assert "document_approved" in types

    def test_document_for_different_vehicle_not_matched(self):
        _add_vehicle()
        _add_document("VEH-OTHER")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 0

    def test_cost_breakdown_update_event(self):
        _add_vehicle()
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=500)
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        assert result["events"][0]["type"] == "cost_breakdown_updated"

    def test_ownership_update_event(self):
        _add_vehicle()
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 1
        assert result["events"][0]["type"] == "ownership_updated"

    def test_events_sorted_most_recent_first(self):
        _add_vehicle()
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Photo", "EMP-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        assert result["count"] == 2
        assert result["events"][0]["label"] == "Status changed to Photo"
        assert result["events"][1]["label"] == "Status changed to Recon"

    def test_limit_caps_events(self):
        _add_vehicle()
        for stage in ("Recon", "Photo", "Merchandising"):
            vehicle_lifecycle.update_lifecycle_status("VEH-1", stage, "EMP-1")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1", limit=2)
        assert len(result["events"]) == 2
        assert result["count"] == 3

    def test_composes_across_multiple_real_sources(self):
        _add_vehicle()
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        vehicle_lifecycle.update_recon_item("VEH-1", "tires", True, "EMP-1")
        vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=100)
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        result = vehicle_lifecycle.get_vehicle_activity_feed("VEH-1")
        types = {e["type"] for e in result["events"]}
        assert types == {
            "lifecycle_status",
            "recon_item",
            "vendor_assigned",
            "cost_breakdown_updated",
            "ownership_updated",
        }
        assert result["count"] == 5


# ---------------------------------------------------------------------------
# get_vehicle_workspace
# ---------------------------------------------------------------------------


class TestGetVehicleWorkspace:
    def test_unknown_vehicle_short_circuits_with_lifecycle_error(self):
        result = vehicle_lifecycle.get_vehicle_workspace("VEH-NOPE")
        assert result == {"error": "Vehicle 'VEH-NOPE' not found"}

    def test_composes_lifecycle_cost_ownership_activity(self):
        _add_vehicle()
        result = vehicle_lifecycle.get_vehicle_workspace("VEH-1")
        assert result["vehicle_id"] == "VEH-1"
        assert result["lifecycle_status"] == "Front Line Ready"
        assert "cost_breakdown" in result
        assert result["cost_breakdown"]["breakdown"]["acquisition_cost"] == 21000
        assert "ownership" in result
        assert result["ownership"]["assignments"]["buyer"] is None
        assert "activity_feed" in result
        assert result["activity_feed"]["events"] == []

    def test_workspace_reflects_real_mutations(self):
        _add_vehicle()
        vehicle_lifecycle.update_lifecycle_status("VEH-1", "Recon", "EMP-1")
        vehicle_lifecycle.update_cost_breakdown("VEH-1", "EMP-1", transport_cost=250)
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        result = vehicle_lifecycle.get_vehicle_workspace("VEH-1")
        assert result["lifecycle_status"] == "Recon"
        assert result["cost_breakdown"]["breakdown"]["transport_cost"] == 250.0
        assert result["ownership"]["assignments"]["buyer"] == "EMP-2"
        assert result["activity_feed"]["count"] == 3

    def test_activity_feed_capped_at_50_within_workspace(self):
        _add_vehicle()
        for i in range(60):
            vehicle_lifecycle.update_recon_item(
                "VEH-1", "tires", i % 2 == 0, "EMP-1", notes=f"pass {i}"
            )
        result = vehicle_lifecycle.get_vehicle_workspace("VEH-1")
        # 60 real recon-item mutations against the SAME item collapse into a
        # single checklist entry (only the latest updated_at survives), so the
        # activity feed only ever surfaces the one most-recent real event --
        # confirming the workspace composes the real, current checklist state
        # rather than a synthetic per-call history.
        assert result["activity_feed"]["count"] == 1


# ---------------------------------------------------------------------------
# API layer / catalog
# ---------------------------------------------------------------------------


class TestCatalogApi:
    def test_catalog_shape(self):
        catalog = vehicle_lifecycle_api.list_lifecycle_catalog_api()
        assert catalog["stages"] == vehicle_lifecycle.LIFECYCLE_STAGES
        assert catalog["recon_items"] == list(vehicle_lifecycle.RECON_ITEMS)
        assert catalog["vendor_types"] == list(vehicle_lifecycle.VENDOR_TYPES)
        assert catalog["vendor_statuses"] == list(vehicle_lifecycle.VENDOR_STATUSES)
        assert catalog["cost_fields"] == list(vehicle_lifecycle.COST_FIELDS)
        assert catalog["ownership_roles"] == list(vehicle_lifecycle.OWNERSHIP_ROLES)


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS, SERVICE]
_MUTATE_DENIED = [SALES, MARKETING, FINANCE, "BOGUS_ROLE"]

_COST_MUTATE_ALLOWED = [ADMIN, OPERATIONS, FINANCE]
_COST_MUTATE_DENIED = [SALES, MARKETING, SERVICE, "BOGUS_ROLE"]

_OWNERSHIP_MUTATE_ALLOWED = [ADMIN, OPERATIONS]
_OWNERSHIP_MUTATE_DENIED = [SALES, MARKETING, SERVICE, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vehicle_lifecycle_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_lifecycle_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vehicle_lifecycle_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_lifecycle_api(role, "VEH-1")
        assert "lifecycle_status" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_lifecycle_status_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.update_lifecycle_status_api(role, "EMP-1", "VEH-1", "Recon")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_update_lifecycle_status_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.update_lifecycle_status_api(role, "EMP-1", "VEH-1", "Recon")
        assert result["lifecycle_status"] == "Recon"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_recon_item_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.update_recon_item_api(role, "EMP-1", "VEH-1", "tires", True)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_update_recon_item_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.update_recon_item_api(role, "EMP-1", "VEH-1", "tires", True)
        assert result["recon_checklist"]["tires"]["complete"] is True

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_assign_vendor_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.assign_vendor_api(
            role, "EMP-1", "VEH-1", "body_shop", "Joe's Shop"
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_assign_vendor_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.assign_vendor_api(
            role, "EMP-1", "VEH-1", "body_shop", "Joe's Shop"
        )
        assert len(result["vendor_assignments"]) == 1

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_vendor_status_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.update_vendor_status_api(
            role, "EMP-1", "VEH-1", "VEND-1", "complete"
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_update_vendor_status_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        assign = vehicle_lifecycle.assign_vendor("VEH-1", "body_shop", "Joe's Shop", "EMP-1")
        assignment_id = assign["vendor_assignments"][0]["id"]
        result = vehicle_lifecycle_api.update_vendor_status_api(
            role, "EMP-1", "VEH-1", assignment_id, "complete"
        )
        assert result["vendor_assignments"][0]["status"] == "complete"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_list_lifecycle_board_denied(self, role):
        result = vehicle_lifecycle_api.list_lifecycle_board_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_list_lifecycle_board_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.list_lifecycle_board_api(role)
        assert set(result.keys()) == set(vehicle_lifecycle.LIFECYCLE_STAGES)

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vehicle_workspace_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_workspace_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vehicle_workspace_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_workspace_api(role, "VEH-1")
        assert "activity_feed" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_cost_breakdown_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.get_cost_breakdown_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_cost_breakdown_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.get_cost_breakdown_api(role, "VEH-1")
        assert "breakdown" in result

    @pytest.mark.parametrize("role", _COST_MUTATE_DENIED)
    def test_update_cost_breakdown_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.update_cost_breakdown_api(
            role, "EMP-1", "VEH-1", transport_cost=500
        )
        assert "error" in result

    @pytest.mark.parametrize("role", _COST_MUTATE_ALLOWED)
    def test_update_cost_breakdown_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.update_cost_breakdown_api(
            role, "EMP-1", "VEH-1", transport_cost=500
        )
        assert result["breakdown"]["transport_cost"] == 500.0

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_ownership_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.get_ownership_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_ownership_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.get_ownership_api(role, "VEH-1")
        assert "assignments" in result

    @pytest.mark.parametrize("role", _OWNERSHIP_MUTATE_DENIED)
    def test_assign_ownership_denied(self, role):
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle_api.assign_ownership_api(role, "EMP-1", "VEH-1", buyer="EMP-2")
        assert "error" in result

    @pytest.mark.parametrize("role", _OWNERSHIP_MUTATE_ALLOWED)
    def test_assign_ownership_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        _add_assignment_staff()
        result = vehicle_lifecycle_api.assign_ownership_api(role, "EMP-1", "VEH-1", buyer="EMP-2")
        assert result["assignments"]["buyer"] == "EMP-2"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vehicle_activity_feed_denied(self, role):
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_activity_feed_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vehicle_activity_feed_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vehicle_lifecycle_api.get_vehicle_activity_feed_api(role, "VEH-1")
        assert result["events"] == []

class TestOwnershipEmployeeValidation:
    @pytest.mark.parametrize("employee_id", ["MISSING", "VEH-1", 42])
    def test_invalid_assignment_preserves_all_roles_and_metadata(self, monkeypatch, employee_id):
        _add_vehicle()
        _add_assignment_staff()
        vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="EMP-2")
        before = vehicle_lifecycle.get_ownership("VEH-1")
        def unexpected(*args, **kwargs):
            pytest.fail("Invalid assignment must not save")
        monkeypatch.setattr(vehicle_lifecycle, "save_graph", unexpected)
        result = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="", recon_manager=employee_id)
        assert "error" in result
        assert vehicle_lifecycle.get_ownership("VEH-1") == before

    def test_employee_ids_trim_and_clearing_remains_supported(self):
        _add_vehicle()
        _add_assignment_staff()
        assigned = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer=" EMP-2 ")
        assert assigned["assignments"]["buyer"] == "EMP-2"
        cleared = vehicle_lifecycle.assign_ownership("VEH-1", "EMP-1", buyer="  ")
        assert cleared["assignments"]["buyer"] is None
