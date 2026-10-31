import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, IMAGE
from core.relationship_types import HAS_IMAGE
from core import merchandising
from core import merchandising_api
from core.merchandising import FEED_PLATFORMS, FEED_STATUSES
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(merchandising, "save_graph", lambda filepath: None)


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
        "Price": 24500,
    }
    if sold:
        attrs["DateSold"] = "2026-01-01"
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


class TestAddVehicleImage:
    def test_failed_save_removes_only_attempted_photo_and_retry_has_new_id(self, monkeypatch):
        _add_vehicle()
        existing = merchandising.add_vehicle_image("VEH-1", "https://cdn.example.com/old.jpg", "EMP-1")
        consumed = []
        def fail(_):
            consumed.extend(e.id for e in ledger.get_all().values() if e.entity_type == IMAGE)
            ledger.add_entity(Entity(id="VEH-UNRELATED", entity_type=VEHICLE, attributes={}))
            raise OSError("fixture disk failure")
        monkeypatch.setattr(merchandising, "save_graph", fail)
        result = merchandising.add_vehicle_image("VEH-1", "https://cdn.example.com/new.jpg", "EMP-1")
        assert "error" in result
        assert [p["id"] for p in merchandising.list_vehicle_images("VEH-1")["images"]] == [existing["image"]["id"]]
        assert ledger.get_entity("VEH-UNRELATED") is not None
        monkeypatch.setattr(merchandising, "save_graph", lambda _: None)
        retried = merchandising.add_vehicle_image("VEH-1", "https://cdn.example.com/new.jpg", "EMP-1")
        assert retried["image"]["id"] not in consumed

    def test_unknown_vehicle_rejected(self):
        result = merchandising.add_vehicle_image("VEH-NOPE", "http://x.com/a.jpg", "EMP-1")
        assert "error" in result

    def test_missing_url_rejected(self):
        _add_vehicle()
        result = merchandising.add_vehicle_image("VEH-1", "", "EMP-1")
        assert "error" in result

    def test_whitespace_only_url_rejected(self):
        _add_vehicle()
        result = merchandising.add_vehicle_image("VEH-1", "   ", "EMP-1")
        assert "error" in result

    def test_valid_add_shape(self):
        _add_vehicle()
        result = merchandising.add_vehicle_image(
            "VEH-1", "http://cdn.example.com/a.jpg", "EMP-1", caption="Front 3/4"
        )
        assert result["vehicle_id"] == "VEH-1"
        assert result["image"]["url"] == "http://cdn.example.com/a.jpg"
        assert result["image"]["caption"] == "Front 3/4"
        assert result["image"]["id"].startswith("IMG-")

    def test_url_is_stripped(self):
        _add_vehicle()
        result = merchandising.add_vehicle_image("VEH-1", "  http://x.com/a.jpg  ", "EMP-1")
        assert result["image"]["url"] == "http://x.com/a.jpg"

    def test_creates_real_image_entity_and_relationship(self):
        _add_vehicle()
        result = merchandising.add_vehicle_image("VEH-1", "http://x.com/a.jpg", "EMP-1")
        img_id = result["image"]["id"]
        img = ledger.get_entity(img_id)
        assert img is not None
        assert img.entity_type == IMAGE
        assert img.attributes["VehicleID"] == "VEH-1"
        assert img.attributes["UploadedBy"] == "EMP-1"

        rels = [r for r in ledger.get_relationships() if r.relationship_type == HAS_IMAGE]
        assert len(rels) == 1
        assert rels[0].source_id == "VEH-1"
        assert rels[0].target_id == img_id

    def test_multiple_images_get_unique_ids(self):
        _add_vehicle()
        r1 = merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1")
        r2 = merchandising.add_vehicle_image("VEH-1", "http://x.com/2.jpg", "EMP-1")
        assert r1["image"]["id"] != r2["image"]["id"]


class TestListVehicleImages:
    @pytest.mark.parametrize("field,action,value", [
        ("description", merchandising.update_description, "New description"),
        ("featured", merchandising.set_featured, True),
    ])
    @pytest.mark.parametrize("had_value", [False, True])
    def test_failed_merchandising_save_restores_prior_fields(self, monkeypatch, field, action, value, had_value):
        _add_vehicle()
        vehicle = ledger.get_entity("VEH-1")
        if had_value:
            vehicle.attributes.update({field: "Old" if field == "description" else False,
                field + "_updated_by": "EMP-OLD", field + "_updated_at": "old-time"})
        old = dict(vehicle.attributes)
        def fail(_):
            vehicle.attributes["unrelated"] = "preserve"
            raise OSError("fixture disk failure")
        monkeypatch.setattr(merchandising, "save_graph", fail)
        assert "error" in action("VEH-1", value, "EMP-NEW")
        assert vehicle.attributes == {**old, "unrelated": "preserve"}

    def test_unknown_vehicle_rejected(self):
        result = merchandising.list_vehicle_images("VEH-NOPE")
        assert "error" in result

    def test_empty_default(self):
        _add_vehicle()
        result = merchandising.list_vehicle_images("VEH-1")
        assert result["images"] == []

    def test_reflects_added_images(self):
        _add_vehicle()
        merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1", caption="Front")
        result = merchandising.list_vehicle_images("VEH-1")
        assert len(result["images"]) == 1
        assert result["images"][0]["url"] == "http://x.com/1.jpg"
        assert result["images"][0]["caption"] == "Front"

    def test_images_scoped_to_this_vehicle_only(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        merchandising.add_vehicle_image("VEH-2", "http://x.com/1.jpg", "EMP-1")
        result = merchandising.list_vehicle_images("VEH-1")
        assert result["images"] == []


# ---------------------------------------------------------------------------
# Description / Featured
# ---------------------------------------------------------------------------


class TestUpdateDescription:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.update_description("VEH-NOPE", "Nice car", "EMP-1")
        assert "error" in result

    def test_sets_description_and_metadata(self):
        _add_vehicle()
        result = merchandising.update_description("VEH-1", "One owner, garage kept", "EMP-1")
        assert result["description"] == "One owner, garage kept"
        v = ledger.get_entity("VEH-1")
        assert v.attributes["description"] == "One owner, garage kept"
        assert v.attributes["description_updated_by"] == "EMP-1"
        assert v.attributes["description_updated_at"] is not None

    def test_overwrites_prior_description(self):
        _add_vehicle()
        merchandising.update_description("VEH-1", "First", "EMP-1")
        merchandising.update_description("VEH-1", "Second", "EMP-2")
        v = ledger.get_entity("VEH-1")
        assert v.attributes["description"] == "Second"
        assert v.attributes["description_updated_by"] == "EMP-2"


class TestSetFeatured:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.set_featured("VEH-NOPE", True, "EMP-1")
        assert "error" in result

    def test_sets_true(self):
        _add_vehicle()
        result = merchandising.set_featured("VEH-1", True, "EMP-1")
        assert result["featured"] is True
        v = ledger.get_entity("VEH-1")
        assert v.attributes["featured"] is True
        assert v.attributes["featured_updated_by"] == "EMP-1"

    def test_sets_false(self):
        _add_vehicle()
        merchandising.set_featured("VEH-1", True, "EMP-1")
        result = merchandising.set_featured("VEH-1", False, "EMP-2")
        assert result["featured"] is False

    def test_truthy_non_bool_coerced(self):
        _add_vehicle()
        result = merchandising.set_featured("VEH-1", "yes", "EMP-1")
        assert result["featured"] is True

    def test_falsy_non_bool_coerced(self):
        _add_vehicle()
        result = merchandising.set_featured("VEH-1", "", "EMP-1")
        assert result["featured"] is False


class TestGetFeaturedVehicles:
    def test_empty_state(self):
        result = merchandising.get_featured_vehicles()
        assert result == {"count": 0, "vehicles": []}

    def test_only_featured_listed(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        merchandising.set_featured("VEH-1", True, "EMP-1")
        result = merchandising.get_featured_vehicles()
        assert result["count"] == 1
        assert result["vehicles"][0]["vehicle_id"] == "VEH-1"

    def test_sold_vehicle_excluded_even_if_featured(self):
        _add_vehicle("VEH-1", sold=True)
        v = ledger.get_entity("VEH-1")
        v.attributes["featured"] = True
        result = merchandising.get_featured_vehicles()
        assert result["count"] == 0

    def test_unfeatured_after_toggled_off(self):
        _add_vehicle()
        merchandising.set_featured("VEH-1", True, "EMP-1")
        merchandising.set_featured("VEH-1", False, "EMP-1")
        result = merchandising.get_featured_vehicles()
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# VDP Health Score
# ---------------------------------------------------------------------------


class TestVdpHealth:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.get_vdp_health("VEH-NOPE")
        assert "error" in result

    def test_default_no_real_signals(self):
        _add_vehicle()
        result = merchandising.get_vdp_health("VEH-1")
        assert result["has_photos"] is False
        assert result["has_description"] is False
        assert result["is_featured"] is False

    def test_real_signals_reflected(self):
        _add_vehicle()
        merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-1", "Great car", "EMP-1")
        merchandising.set_featured("VEH-1", True, "EMP-1")
        result = merchandising.get_vdp_health("VEH-1")
        assert result["has_photos"] is True
        assert result["has_description"] is True
        assert result["is_featured"] is True

    def test_full_real_signals_grant_65_real_points_floor(self):
        _add_vehicle()
        merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-1", "Great car", "EMP-1")
        merchandising.set_featured("VEH-1", True, "EMP-1")
        result = merchandising.get_vdp_health("VEH-1")
        assert result["health_score"] >= 65

    def test_zero_real_signals_scores_below_35(self):
        _add_vehicle()
        result = merchandising.get_vdp_health("VEH-1")
        assert result["health_score"] <= 35

    def test_score_never_exceeds_max(self):
        _add_vehicle()
        merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-1", "Great car", "EMP-1")
        merchandising.set_featured("VEH-1", True, "EMP-1")
        result = merchandising.get_vdp_health("VEH-1")
        assert result["health_score"] <= result["health_score_max"] == 100

    def test_basis_and_disclaimer_present(self):
        _add_vehicle()
        result = merchandising.get_vdp_health("VEH-1")
        assert "simulated_market_data" in result["basis"]
        assert "SIMULATED" in result["disclaimer"]

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = merchandising.get_vdp_health("VEH-1")
        r2 = merchandising.get_vdp_health("VEH-1")
        assert r1["simulated_page_views"] == r2["simulated_page_views"]
        assert r1["simulated_lead_conversion_rate"] == r2["simulated_lead_conversion_rate"]
        assert r1["health_score"] == r2["health_score"]

    def test_different_vehicles_can_differ(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        r1 = merchandising.get_vdp_health("VEH-1")
        r2 = merchandising.get_vdp_health("VEH-2")
        # Not guaranteed to differ, but the simulated seed is vehicle-scoped --
        # confirm both are within the documented bounds independently.
        assert 5 <= r1["simulated_page_views"] <= 400
        assert 5 <= r2["simulated_page_views"] <= 400


# ---------------------------------------------------------------------------
# Feed Sync Status
# ---------------------------------------------------------------------------


class TestFeedStatus:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.get_feed_status("VEH-NOPE")
        assert "error" in result

    def test_all_platforms_present(self):
        _add_vehicle()
        result = merchandising.get_feed_status("VEH-1")
        platforms_seen = {f["platform"] for f in result["feeds"]}
        assert platforms_seen == set(FEED_PLATFORMS)

    def test_statuses_within_known_values(self):
        _add_vehicle()
        result = merchandising.get_feed_status("VEH-1")
        for f in result["feeds"]:
            assert f["status"] in FEED_STATUSES

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = merchandising.get_feed_status("VEH-1")
        r2 = merchandising.get_feed_status("VEH-1")
        assert r1["feeds"] == r2["feeds"]

    def test_basis_and_disclaimer_present(self):
        _add_vehicle()
        result = merchandising.get_feed_status("VEH-1")
        assert result["basis"] == "simulated_market_data"
        assert "SIMULATED" in result["disclaimer"]


class TestPublishToFeed:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.publish_to_feed("VEH-NOPE", "Cars.com", "EMP-1")
        assert "error" in result

    def test_invalid_platform_rejected(self):
        _add_vehicle()
        result = merchandising.publish_to_feed("VEH-1", "Bogus Platform", "EMP-1")
        assert "error" in result

    def test_valid_publish_shape(self):
        _add_vehicle()
        result = merchandising.publish_to_feed("VEH-1", "Cars.com", "EMP-1")
        assert result["entry"]["platform"] == "Cars.com"
        assert result["entry"]["published_by"] == "EMP-1"
        assert result["entry"]["simulated"] is True
        assert result["basis"] == "simulated_market_data"
        assert "Cars.com" in result["disclaimer"]

    def test_log_persists_on_vehicle(self):
        _add_vehicle()
        merchandising.publish_to_feed("VEH-1", "Cars.com", "EMP-1")
        v = ledger.get_entity("VEH-1")
        assert len(v.attributes["feed_publish_log"]) == 1

    def test_log_accumulates_across_platforms(self):
        _add_vehicle()
        merchandising.publish_to_feed("VEH-1", "Cars.com", "EMP-1")
        merchandising.publish_to_feed("VEH-1", "AutoTrader", "EMP-1")
        v = ledger.get_entity("VEH-1")
        assert len(v.attributes["feed_publish_log"]) == 2


# ---------------------------------------------------------------------------
# Composed view + queue
# ---------------------------------------------------------------------------


class TestMerchandisingView:
    def test_unknown_vehicle_rejected(self):
        result = merchandising.get_merchandising_view("VEH-NOPE")
        assert "error" in result

    def test_defaults_when_nothing_set(self):
        _add_vehicle()
        result = merchandising.get_merchandising_view("VEH-1")
        assert result["vehicle"]["vehicle_id"] == "VEH-1"
        assert result["images"] == []
        assert result["description"] == ""
        assert result["featured"] is False
        assert result["feed_publish_log"] == []
        assert "vdp_health" in result
        assert "feed_status" in result

    def test_composes_all_real_data(self):
        _add_vehicle()
        merchandising.add_vehicle_image("VEH-1", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-1", "Great car", "EMP-1")
        merchandising.set_featured("VEH-1", True, "EMP-1")
        merchandising.publish_to_feed("VEH-1", "Cars.com", "EMP-1")

        result = merchandising.get_merchandising_view("VEH-1")
        assert len(result["images"]) == 1
        assert result["description"] == "Great car"
        assert result["featured"] is True
        assert len(result["feed_publish_log"]) == 1
        assert result["vdp_health"]["has_photos"] is True


class TestMerchandisingQueue:
    def test_empty_state(self):
        result = merchandising.get_merchandising_queue()
        assert result == {"count": 0, "vehicles": [], "total": 0, "offset": 0}

    def test_worst_completeness_ranked_first(self):
        _add_vehicle("VEH-1")  # no photos, no description -- completeness 0
        _add_vehicle("VEH-2")
        merchandising.add_vehicle_image("VEH-2", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-2", "Great car", "EMP-1")  # completeness 2

        result = merchandising.get_merchandising_queue()
        ids = [v["vehicle_id"] for v in result["vehicles"]]
        assert ids.index("VEH-1") < ids.index("VEH-2")

    def test_partial_completeness_sorts_between(self):
        _add_vehicle("VEH-1")  # completeness 0
        _add_vehicle("VEH-2")
        merchandising.add_vehicle_image("VEH-2", "http://x.com/1.jpg", "EMP-1")  # completeness 1
        _add_vehicle("VEH-3")
        merchandising.add_vehicle_image("VEH-3", "http://x.com/1.jpg", "EMP-1")
        merchandising.update_description("VEH-3", "Nice", "EMP-1")  # completeness 2

        result = merchandising.get_merchandising_queue()
        ids = [v["vehicle_id"] for v in result["vehicles"]]
        assert ids.index("VEH-1") < ids.index("VEH-2") < ids.index("VEH-3")

    def test_each_entry_has_vdp_health_attached(self):
        _add_vehicle()
        result = merchandising.get_merchandising_queue()
        assert "vdp_health" in result["vehicles"][0]

    def test_count_reflects_capped_length_not_true_total(self):
        # Unlike wholesale_desk/parts_desk's "count = true total, list capped
        # separately" convention, get_merchandising_queue's own `count` field
        # reflects the ALREADY-CAPPED length (ranked = sorted(...)[:limit]
        # happens before results is built) -- a deliberately different shape,
        # confirmed here rather than assumed.
        for i in range(5):
            _add_vehicle(f"VEH-{i}")
        result = merchandising.get_merchandising_queue(limit=2)
        assert result["count"] == 2
        assert len(result["vehicles"]) == 2

    def test_sold_vehicle_excluded(self):
        _add_vehicle("VEH-1", sold=True)
        result = merchandising.get_merchandising_queue()
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS, MARKETING]
_MUTATE_DENIED = [SALES, SERVICE, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    def test_get_catalog_has_no_role_gate(self):
        result = merchandising_api.get_catalog_api()
        assert result["feed_platforms"] == list(FEED_PLATFORMS)

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_add_vehicle_image_denied(self, role):
        _add_vehicle()
        result = merchandising_api.add_vehicle_image_api(role, "EMP-1", "VEH-1", "http://x.com/1.jpg")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_add_vehicle_image_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.add_vehicle_image_api(role, "EMP-1", "VEH-1", "http://x.com/1.jpg")
        assert "image" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_list_vehicle_images_denied(self, role):
        _add_vehicle()
        result = merchandising_api.list_vehicle_images_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_list_vehicle_images_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.list_vehicle_images_api(role, "VEH-1")
        assert result["images"] == []

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_update_description_denied(self, role):
        _add_vehicle()
        result = merchandising_api.update_description_api(role, "EMP-1", "VEH-1", "Nice")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_update_description_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.update_description_api(role, "EMP-1", "VEH-1", "Nice")
        assert result["description"] == "Nice"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_set_featured_denied(self, role):
        _add_vehicle()
        result = merchandising_api.set_featured_api(role, "EMP-1", "VEH-1", True)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_set_featured_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.set_featured_api(role, "EMP-1", "VEH-1", True)
        assert result["featured"] is True

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_featured_vehicles_denied(self, role):
        result = merchandising_api.get_featured_vehicles_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_featured_vehicles_allowed(self, role):
        result = merchandising_api.get_featured_vehicles_api(role)
        assert result == {"count": 0, "vehicles": []}

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vdp_health_denied(self, role):
        _add_vehicle()
        result = merchandising_api.get_vdp_health_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vdp_health_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.get_vdp_health_api(role, "VEH-1")
        assert "health_score" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_feed_status_denied(self, role):
        _add_vehicle()
        result = merchandising_api.get_feed_status_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_feed_status_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.get_feed_status_api(role, "VEH-1")
        assert "feeds" in result

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_publish_to_feed_denied(self, role):
        _add_vehicle()
        result = merchandising_api.publish_to_feed_api(role, "EMP-1", "VEH-1", "Cars.com")
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_publish_to_feed_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.publish_to_feed_api(role, "EMP-1", "VEH-1", "Cars.com")
        assert result["entry"]["platform"] == "Cars.com"

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_merchandising_view_denied(self, role):
        _add_vehicle()
        result = merchandising_api.get_merchandising_view_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_merchandising_view_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = merchandising_api.get_merchandising_view_api(role, "VEH-1")
        assert "vehicle" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_merchandising_queue_denied(self, role):
        result = merchandising_api.get_merchandising_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_merchandising_queue_allowed(self, role):
        result = merchandising_api.get_merchandising_queue_api(role)
        assert result == {"count": 0, "vehicles": [], "total": 0, "offset": 0}


def test_queue_pages_reach_all_unsold_vehicles_with_stable_order():
    for i in reversed(range(31)):
        _add_vehicle(f"VEH-{i:03d}")
    _add_vehicle("SOLD", sold=True)
    ids=[]
    for offset in range(0,32,4):
        result=merchandising.get_merchandising_queue(limit=4,offset=offset)
        assert result["total"]==31
        assert result["offset"]==offset
        ids.extend(v["vehicle_id"] for v in result["vehicles"])
    assert ids==[f"VEH-{i:03d}" for i in range(31)]
    assert merchandising.get_merchandising_queue(4,40)["vehicles"]==[]
