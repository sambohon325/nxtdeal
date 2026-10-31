import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER
from core import vehicle_inspection
from core import vehicle_inspection_api
from core import repair_orders
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(vehicle_inspection, "save_graph", lambda filepath: None)
    monkeypatch.setattr(repair_orders, "save_graph", lambda filepath: None)


TOTAL_ITEMS = sum(len(cat["items"]) for cat in vehicle_inspection.DVI_CATEGORIES.values())


def make_customer(suffix="00001", **extra):
    attrs = {
        "CustomerID": f"C{suffix}", "FirstName": "Jane", "LastName": "Doe",
        "Phone": "555-0100", "Email": "jane@example.com",
    }
    attrs.update(extra)
    entity = Entity(id=f"CUST-{suffix}", entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_vehicle(suffix="00001", **extra):
    attrs = {
        "VIN": f"VIN{suffix}", "Year": 2023, "Make": "Toyota", "Model": "Camry",
        "Trim": "LE", "Mileage": 12000, "Condition": "Used",
    }
    attrs.update(extra)
    entity = Entity(id=f"VEH-{suffix}", entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_ro(vehicle=None, customer=None, description="Brake noise on braking", created_by="EMP-00001"):
    vehicle = vehicle or make_vehicle()
    customer = customer or make_customer()
    result = repair_orders.create_repair_order(vehicle.id, customer.id, description, created_by)
    assert "error" not in result
    return result["id"]


def first_item_key():
    return next(iter(vehicle_inspection._blank_items().keys()))


# ---------------------------------------------------------------------------
# Catalog / blank items
# ---------------------------------------------------------------------------

class TestCatalogAndBlankItems:

    def test_get_catalog_returns_categories_and_statuses(self):
        catalog = vehicle_inspection.get_catalog()
        assert catalog["categories"] == vehicle_inspection.DVI_CATEGORIES
        assert catalog["statuses"] == list(vehicle_inspection.INSPECTION_STATUSES)

    def test_blank_items_covers_every_catalog_item_exactly_once(self):
        items = vehicle_inspection._blank_items()
        assert len(items) == TOTAL_ITEMS

        for cat_key, cat in vehicle_inspection.DVI_CATEGORIES.items():
            for item_name in cat["items"]:
                key = f"{cat_key}::{item_name}"
                assert key in items
                entry = items[key]
                assert entry["category"] == cat_key
                assert entry["item"] == item_name
                assert entry["status"] == "not_inspected"
                assert entry["notes"] == ""
                assert entry["photo_urls"] == []
                assert entry["concern_created"] is False
                assert entry["updated_by"] is None
                assert entry["updated_at"] is None


# ---------------------------------------------------------------------------
# start_inspection
# ---------------------------------------------------------------------------

class TestStartInspection:

    def test_ro_not_found(self):
        result = vehicle_inspection.start_inspection("SRV-99999", "EMP-00001")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_happy_path(self):
        ro_id = make_ro()
        result = vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        assert "error" not in result
        assert result["status"] == "in_progress"
        assert result["started_by"] == "EMP-00001"
        assert result["started_at"] is not None
        assert result["completed_by"] is None
        assert result["summary"] == {"not_inspected": TOTAL_ITEMS, "green": 0, "yellow": 0, "red": 0}

    def test_cannot_start_twice(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.start_inspection(ro_id, "EMP-00002")
        assert result == {"error": "Inspection already in 'in_progress' status for this RO"}

    def test_cannot_start_once_completed(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        for key in vehicle_inspection._blank_items():
            vehicle_inspection.update_inspection_item(ro_id, key, "green", "", "EMP-00001")
        vehicle_inspection.complete_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        assert result == {"error": "Inspection already in 'completed' status for this RO"}


# ---------------------------------------------------------------------------
# update_inspection_item
# ---------------------------------------------------------------------------

class TestUpdateInspectionItem:

    def test_bad_status_rejected(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.update_inspection_item(ro_id, first_item_key(), "broken", "", "EMP-00001")
        assert "error" in result
        assert "status must be one of" in result["error"]

    def test_ro_not_found(self):
        result = vehicle_inspection.update_inspection_item("SRV-99999", "tires::Tread Depth", "green", "", "EMP-00001")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_rejects_update_before_inspection_started(self):
        ro_id = make_ro()
        result = vehicle_inspection.update_inspection_item(ro_id, first_item_key(), "green", "", "EMP-00001")
        assert result == {"error": "Inspection must be started before updating an item"}

    def test_unknown_item_key_rejected(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.update_inspection_item(ro_id, "not::a-real-key", "green", "", "EMP-00001")
        assert result == {"error": "Unknown inspection item 'not::a-real-key'"}

    def test_happy_path_updates_status_notes_and_stamps(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "brakes::Front Pads"

        result = vehicle_inspection.update_inspection_item(ro_id, key, "red", "Worn to metal", "EMP-00002")

        entry = result["items"][key]
        assert entry["status"] == "red"
        assert entry["notes"] == "Worn to metal"
        assert entry["updated_by"] == "EMP-00002"
        assert entry["updated_at"] is not None
        assert result["summary"]["red"] == 1
        assert result["summary"]["not_inspected"] == TOTAL_ITEMS - 1

    def test_no_notes_defaults_to_empty_string(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "tires::Tire Pressure"

        result = vehicle_inspection.update_inspection_item(ro_id, key, "green", None, "EMP-00001")
        assert result["items"][key]["notes"] == ""


# ---------------------------------------------------------------------------
# attach_inspection_photo
# ---------------------------------------------------------------------------

class TestAttachInspectionPhoto:

    @pytest.mark.parametrize("image_url", [
        "not-a-photo-url", "/relative/photo.jpg", "javascript:alert(1)",
        "data:image/png;base64,abc", "https://", "https://[bad/photo.jpg",
        "https://example.test:bad/photo.jpg", "https://user:secret@example.test/photo.jpg",
        "https://example.test/bad photo.jpg", "https://example.test/\nphoto.jpg",
    ])
    def test_invalid_url_does_not_create_attachment(self, image_url):
        ro_id = make_ro()
        key = first_item_key()
        result = vehicle_inspection.attach_inspection_photo(ro_id, key, image_url, "EMP-00001")
        assert result == {"error": "Enter a valid http:// or https:// photo URL"}
        assert vehicle_inspection.get_inspection(ro_id)["items"][key]["photo_urls"] == []

    def test_empty_image_url_rejected(self):
        ro_id = make_ro()
        result = vehicle_inspection.attach_inspection_photo(ro_id, first_item_key(), "   ", "EMP-00001")
        assert result == {"error": "image_url is required"}

    def test_ro_not_found(self):
        result = vehicle_inspection.attach_inspection_photo("SRV-99999", "tires::Tread Depth", "https://x/1.jpg", "EMP-00001")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_unknown_item_key_rejected(self):
        ro_id = make_ro()
        result = vehicle_inspection.attach_inspection_photo(ro_id, "bogus::key", "https://x/1.jpg", "EMP-00001")
        assert result == {"error": "Unknown inspection item 'bogus::key'"}

    def test_allowed_before_the_inspection_is_started(self):
        # Real quirk: attach_inspection_photo never checks dvi status, only
        # that the item key exists -- a photo can be attached before
        # start_inspection() is ever called, and doing so does NOT itself
        # start the inspection.
        ro_id = make_ro()
        key = first_item_key()

        result = vehicle_inspection.attach_inspection_photo(ro_id, key, "https://x/1.jpg", "EMP-00001")

        assert "error" not in result
        assert result["status"] == "not_started"
        assert result["items"][key]["photo_urls"] == ["https://x/1.jpg"]

    def test_happy_path_appends_and_stamps(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "lights::Headlights"

        vehicle_inspection.attach_inspection_photo(ro_id, key, "  https://x/1.jpg  ", "EMP-00002")
        result = vehicle_inspection.attach_inspection_photo(ro_id, key, "https://x/2.jpg", "EMP-00002")

        entry = result["items"][key]
        assert entry["photo_urls"] == ["https://x/1.jpg", "https://x/2.jpg"]
        assert entry["updated_by"] == "EMP-00002"
        assert entry["updated_at"] is not None

    def test_url_is_stripped(self):
        ro_id = make_ro()
        key = first_item_key()
        result = vehicle_inspection.attach_inspection_photo(ro_id, key, "  https://x/photo.jpg  ", "EMP-00001")
        assert result["items"][key]["photo_urls"] == ["https://x/photo.jpg"]


# ---------------------------------------------------------------------------
# complete_inspection
# ---------------------------------------------------------------------------

class TestCompleteInspection:

    def test_ro_not_found(self):
        result = vehicle_inspection.complete_inspection("SRV-99999", "EMP-00001")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_rejects_completing_before_started(self):
        ro_id = make_ro()
        result = vehicle_inspection.complete_inspection(ro_id, "EMP-00001")
        assert result == {"error": "Inspection has not been started yet"}

    def test_rejects_double_completion(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        for key in vehicle_inspection._blank_items():
            vehicle_inspection.update_inspection_item(ro_id, key, "green", "", "EMP-00001")
        vehicle_inspection.complete_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.complete_inspection(ro_id, "EMP-00001")
        assert result == {"error": "Inspection is already completed"}

    def test_rejects_completion_with_items_still_not_inspected(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        vehicle_inspection.update_inspection_item(ro_id, first_item_key(), "green", "", "EMP-00001")

        result = vehicle_inspection.complete_inspection(ro_id, "EMP-00001")
        assert "error" in result
        assert f"{TOTAL_ITEMS - 1} inspection item(s) still not inspected" in result["error"]

    def test_happy_path(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        for key in vehicle_inspection._blank_items():
            vehicle_inspection.update_inspection_item(ro_id, key, "green", "", "EMP-00001")

        result = vehicle_inspection.complete_inspection(ro_id, "EMP-00002")

        assert result["status"] == "completed"
        assert result["completed_by"] == "EMP-00002"
        assert result["completed_at"] is not None
        assert result["summary"]["green"] == TOTAL_ITEMS


# ---------------------------------------------------------------------------
# get_inspection
# ---------------------------------------------------------------------------

class TestGetInspection:

    def test_ro_not_found(self):
        result = vehicle_inspection.get_inspection("SRV-99999")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_default_shape_before_any_inspection_started(self):
        ro_id = make_ro()
        result = vehicle_inspection.get_inspection(ro_id)

        assert result["ro_id"] == ro_id
        assert result["status"] == "not_started"
        assert result["started_by"] is None
        assert result["completed_by"] is None
        assert result["summary"] == {"not_inspected": TOTAL_ITEMS, "green": 0, "yellow": 0, "red": 0}
        assert len(result["items"]) == TOTAL_ITEMS

    def test_reflects_real_updates(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        vehicle_inspection.update_inspection_item(ro_id, "tires::Tread Depth", "yellow", "Getting low", "EMP-00001")
        vehicle_inspection.update_inspection_item(ro_id, "brakes::Front Pads", "red", "Metal on metal", "EMP-00001")

        result = vehicle_inspection.get_inspection(ro_id)
        assert result["summary"] == {
            "not_inspected": TOTAL_ITEMS - 2, "green": 0, "yellow": 1, "red": 1,
        }


# ---------------------------------------------------------------------------
# create_concerns_from_inspection
# ---------------------------------------------------------------------------

class TestCreateConcernsFromInspection:

    def test_ro_not_found(self):
        result = vehicle_inspection.create_concerns_from_inspection("SRV-99999", ["tires::Tread Depth"], "EMP-00001")
        assert result == {"error": "Repair order 'SRV-99999' not found"}

    def test_missing_item_keys_rejected(self):
        ro_id = make_ro()
        result = vehicle_inspection.create_concerns_from_inspection(ro_id, [], "EMP-00001")
        assert result == {"error": "item_keys is required (at least one inspection item)"}

    def test_nonexistent_item_key_is_reported_invalid(self):
        ro_id = make_ro()
        result = vehicle_inspection.create_concerns_from_inspection(ro_id, ["not::real"], "EMP-00001")

        assert result["created_concerns_for"] == []
        assert result["invalid_items"] == ["not::real"]
        assert result["already_had_concerns"] == []

    def test_not_inspected_item_is_invalid(self):
        ro_id = make_ro()
        key = first_item_key()

        result = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00001")
        assert result["invalid_items"] == [key]

    def test_green_item_is_invalid_not_creatable(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "fluids::Engine Oil"
        vehicle_inspection.update_inspection_item(ro_id, key, "green", "", "EMP-00001")

        result = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00001")
        assert result["invalid_items"] == [key]
        assert result["created_concerns_for"] == []

    def test_yellow_item_creates_a_real_concern(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "tires::Tread Depth"
        vehicle_inspection.update_inspection_item(ro_id, key, "yellow", "2/32nds remaining", "EMP-00001")

        result = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00002")

        assert result["created_concerns_for"] == [key]
        assert result["invalid_items"] == []
        assert result["already_had_concerns"] == []

        workspace = result["workspace"]
        concern_descriptions = [c["description"] for c in workspace["concerns"]]
        expected = "DVI finding — Tires: Tread Depth (YELLOW) — 2/32nds remaining"
        assert expected in concern_descriptions

    def test_red_item_creates_a_real_concern_without_notes_suffix(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "brakes::Rotors"
        vehicle_inspection.update_inspection_item(ro_id, key, "red", "", "EMP-00001")

        result = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00002")

        concern_descriptions = [c["description"] for c in result["workspace"]["concerns"]]
        assert "DVI finding — Brakes: Rotors (RED)" in concern_descriptions

    def test_item_is_marked_concern_created(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "battery::Battery Health"
        vehicle_inspection.update_inspection_item(ro_id, key, "red", "", "EMP-00001")

        vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00001")

        inspection = vehicle_inspection.get_inspection(ro_id)
        assert inspection["items"][key]["concern_created"] is True

    def test_re_converting_the_same_item_reports_already_had_and_does_not_duplicate(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "wipers::Wiper Blades"
        vehicle_inspection.update_inspection_item(ro_id, key, "yellow", "Streaking", "EMP-00001")

        first = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00001")
        assert first["created_concerns_for"] == [key]

        second = vehicle_inspection.create_concerns_from_inspection(ro_id, [key], "EMP-00001")
        assert second["created_concerns_for"] == []
        assert second["already_had_concerns"] == [key]

        concern_descriptions = [c["description"] for c in second["workspace"]["concerns"]]
        matches = [d for d in concern_descriptions if "Wiper Blades" in d]
        assert len(matches) == 1

    def test_mixed_batch_of_valid_invalid_and_already_done(self):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        already_key = "suspension::Shocks / Struts"
        new_key = "suspension::Alignment (visual)"
        green_key = "belts_hoses::Serpentine Belt"

        vehicle_inspection.update_inspection_item(ro_id, already_key, "red", "", "EMP-00001")
        vehicle_inspection.update_inspection_item(ro_id, new_key, "yellow", "", "EMP-00001")
        vehicle_inspection.update_inspection_item(ro_id, green_key, "green", "", "EMP-00001")
        vehicle_inspection.create_concerns_from_inspection(ro_id, [already_key], "EMP-00001")

        result = vehicle_inspection.create_concerns_from_inspection(
            ro_id, [already_key, new_key, green_key, "bogus::key"], "EMP-00001",
        )

        assert result["created_concerns_for"] == [new_key]
        assert result["already_had_concerns"] == [already_key]
        assert set(result["invalid_items"]) == {green_key, "bogus::key"}


# ---------------------------------------------------------------------------
# get_inspection_history_for_vehicle
# ---------------------------------------------------------------------------

class TestGetInspectionHistoryForVehicle:

    def test_empty_string_has_no_vin(self):
        result = vehicle_inspection.get_inspection_history_for_vehicle("")
        assert result == {"error": "No VIN found for ''"}

    def test_real_vehicle_with_no_vin_attribute_errors(self):
        vehicle = make_vehicle(vin_override=True)
        vehicle.attributes["VIN"] = ""
        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert result == {"error": f"No VIN found for '{vehicle.id}'"}

    def test_nonexistent_vehicle_shaped_id_is_treated_as_a_raw_vin_not_an_error(self):
        # Real quirk: a Vehicle-id-shaped string that doesn't resolve to a
        # real entity falls through to being treated as a literal VIN --
        # no error, just zero matching inspections.
        result = vehicle_inspection.get_inspection_history_for_vehicle("VEH-99999")
        assert "error" not in result
        assert result["vin"] == "VEH-99999"
        assert result["vehicle_id"] is None
        assert result["inspection_count"] == 0

    def test_no_matching_service_records_returns_empty_history(self):
        vehicle = make_vehicle()
        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)

        assert result["vehicle_id"] == vehicle.id
        assert result["vin"] == vehicle.attributes["VIN"]
        assert result["inspection_count"] == 0
        assert result["inspections"] == []
        assert result["recurring_findings"] == []

    def test_never_started_inspection_is_excluded(self):
        vehicle = make_vehicle()
        make_ro(vehicle=vehicle)  # dvi never started -> excluded

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert result["inspection_count"] == 0

    def test_in_progress_inspection_is_included(self):
        vehicle = make_vehicle()
        ro_id = make_ro(vehicle=vehicle)
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert result["inspection_count"] == 1
        assert result["inspections"][0]["ro_id"] == ro_id
        assert result["inspections"][0]["dvi_status"] == "in_progress"

    def test_lookup_by_raw_vin_string_works_directly(self):
        vehicle = make_vehicle(suffix="00042")
        ro_id = make_ro(vehicle=vehicle)
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.attributes["VIN"])
        assert result["vehicle_id"] is None
        assert result["vin"] == vehicle.attributes["VIN"]
        assert result["inspection_count"] == 1

    def test_sorted_most_recent_service_date_first(self):
        vehicle = make_vehicle()
        ro_old = make_ro(vehicle=vehicle)
        ledger.get_entity(ro_old).attributes["ServiceDate"] = "2026-01-01"
        vehicle_inspection.start_inspection(ro_old, "EMP-00001")

        ro_new = make_ro(vehicle=vehicle)
        ledger.get_entity(ro_new).attributes["ServiceDate"] = "2026-06-01"
        vehicle_inspection.start_inspection(ro_new, "EMP-00001")

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert [i["ro_id"] for i in result["inspections"]] == [ro_new, ro_old]

    def test_flagged_items_and_recurring_findings(self):
        vehicle = make_vehicle()

        ro1 = make_ro(vehicle=vehicle)
        vehicle_inspection.start_inspection(ro1, "EMP-00001")
        vehicle_inspection.update_inspection_item(ro1, "tires::Tread Depth", "yellow", "Low tread", "EMP-00001")
        vehicle_inspection.update_inspection_item(ro1, "brakes::Front Pads", "green", "", "EMP-00001")

        ro2 = make_ro(vehicle=vehicle)
        vehicle_inspection.start_inspection(ro2, "EMP-00001")
        vehicle_inspection.update_inspection_item(ro2, "tires::Tread Depth", "red", "Same tire, worse", "EMP-00001")
        vehicle_inspection.update_inspection_item(ro2, "lights::Headlights", "yellow", "Dim", "EMP-00001")

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert result["inspection_count"] == 2

        recurring = {(f["category"], f["item"]): f["occurrences"] for f in result["recurring_findings"]}
        assert recurring == {("tires", "Tread Depth"): 2}
        assert result["recurring_findings"][0]["label"] == "Tires: Tread Depth"

        # a green item is never a "flagged item" in either inspection's own list
        ro1_entry = next(i for i in result["inspections"] if i["ro_id"] == ro1)
        flagged_items_ro1 = {f["item_key"] for f in ro1_entry["flagged_items"]}
        assert "brakes::Front Pads" not in flagged_items_ro1
        assert "tires::Tread Depth" in flagged_items_ro1

    def test_recurring_findings_sorted_by_occurrences_descending(self):
        vehicle = make_vehicle()

        for _ in range(3):
            ro_id = make_ro(vehicle=vehicle)
            vehicle_inspection.start_inspection(ro_id, "EMP-00001")
            vehicle_inspection.update_inspection_item(ro_id, "fluids::Coolant", "yellow", "", "EMP-00001")

        for _ in range(2):
            ro_id = make_ro(vehicle=vehicle)
            vehicle_inspection.start_inspection(ro_id, "EMP-00001")
            vehicle_inspection.update_inspection_item(ro_id, "wipers::Washer Fluid", "red", "", "EMP-00001")

        result = vehicle_inspection.get_inspection_history_for_vehicle(vehicle.id)
        assert [f["occurrences"] for f in result["recurring_findings"]] == [3, 2]
        assert result["recurring_findings"][0]["item"] == "Coolant"


# ---------------------------------------------------------------------------
# vehicle_inspection_api -- ACL layer
# ---------------------------------------------------------------------------

_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, FINANCE]
_VIEW_DENIED = [MARKETING]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS, SERVICE]
_MUTATE_DENIED = [SALES, MARKETING, FINANCE]


class TestApiAcl:

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_catalog_allowed(self, role):
        result = vehicle_inspection_api.get_catalog_api(role)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_catalog_denied(self, role):
        result = vehicle_inspection_api.get_catalog_api(role)
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_inspection_allowed(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.get_inspection_api(role, ro_id)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_inspection_denied(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.get_inspection_api(role, ro_id)
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_start_inspection_allowed(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.start_inspection_api(role, ro_id, "EMP-00001")
        assert result["status"] == "in_progress"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_start_inspection_denied(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.start_inspection_api(role, ro_id, "EMP-00001")
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_update_inspection_item_allowed(self, role):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = first_item_key()

        result = vehicle_inspection_api.update_inspection_item_api(role, ro_id, key, "green", "ok", "EMP-00001")
        assert result["items"][key]["status"] == "green"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_inspection_item_denied(self, role):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")

        result = vehicle_inspection_api.update_inspection_item_api(role, ro_id, first_item_key(), "green", "", "EMP-00001")
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_attach_inspection_photo_allowed(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.attach_inspection_photo_api(role, ro_id, first_item_key(), "https://x/1.jpg", "EMP-00001")
        assert "error" not in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_attach_inspection_photo_denied(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.attach_inspection_photo_api(role, ro_id, first_item_key(), "https://x/1.jpg", "EMP-00001")
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_complete_inspection_allowed(self, role):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        for key in vehicle_inspection._blank_items():
            vehicle_inspection.update_inspection_item(ro_id, key, "green", "", "EMP-00001")

        result = vehicle_inspection_api.complete_inspection_api(role, ro_id, "EMP-00001")
        assert result["status"] == "completed"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_complete_inspection_denied(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.complete_inspection_api(role, ro_id, "EMP-00001")
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_create_concerns_from_inspection_allowed(self, role):
        ro_id = make_ro()
        vehicle_inspection.start_inspection(ro_id, "EMP-00001")
        key = "tires::Tread Depth"
        vehicle_inspection.update_inspection_item(ro_id, key, "red", "", "EMP-00001")

        result = vehicle_inspection_api.create_concerns_from_inspection_api(role, ro_id, [key], "EMP-00001")
        assert result["created_concerns_for"] == [key]

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_create_concerns_from_inspection_denied(self, role):
        ro_id = make_ro()
        result = vehicle_inspection_api.create_concerns_from_inspection_api(role, ro_id, ["tires::Tread Depth"], "EMP-00001")
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_inspection_history_allowed(self, role):
        vehicle = make_vehicle()
        result = vehicle_inspection_api.get_inspection_history_api(role, vehicle.id)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_inspection_history_denied(self, role):
        vehicle = make_vehicle()
        result = vehicle_inspection_api.get_inspection_history_api(role, vehicle.id)
        assert result == {"error": "You don't have access to the Digital Vehicle Inspection tool"}
def test_video_evidence_is_separate_and_deduplicated():
    ro_id=make_ro();key=first_item_key()
    for _ in range(2):
        result=vehicle_inspection.attach_inspection_photo(ro_id,key,'https://synthetic.example/video.mp4','EMP-00001','video')
        assert 'error' not in result
    item=vehicle_inspection.get_inspection(ro_id)['items'][key]
    assert item['video_urls']==['https://synthetic.example/video.mp4']
    assert item['photo_urls']==[]
    assert 'error' in vehicle_inspection.attach_inspection_photo(ro_id,key,'https://synthetic.example/file','EMP-00001','executable')
