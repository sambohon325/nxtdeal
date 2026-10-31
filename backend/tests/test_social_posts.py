"""
Test coverage for core/social_posts.py -- the social media post builder +
content calendar (session 83): a real SocialPost graph entity per platform,
a SIMULATED publish action (real graph state, no real platform delivery),
and a live, computed content calendar with no parallel store.

Every mutating function in this module calls save_graph(GRAPH_PATH) for
real -- conftest.py points GRAPH_PATH at a fresh, isolated temp storage dir
for the whole test session, so these calls are safe to let run for real
rather than monkeypatched out.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.social_posts as sp

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE

import pytest


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, year=None, make=None, model=None, trim=None, vin=None, stock=None, price=None, date_sold=None):
    attrs = {}
    if year is not None:
        attrs["Year"] = year
    if make is not None:
        attrs["Make"] = make
    if model is not None:
        attrs["Model"] = model
    if trim is not None:
        attrs["Trim"] = trim
    if vin is not None:
        attrs["VIN"] = vin
    if stock is not None:
        attrs["StockNumber"] = stock
    if price is not None:
        attrs["Price"] = price
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vid)


class TestListPlatforms:

    def test_returns_all_platforms(self):
        assert sp.list_platforms() == ["facebook", "instagram", "x", "linkedin", "tiktok"]

    def test_returns_a_copy_not_the_original_list(self):
        result = sp.list_platforms()
        result.append("myspace")
        assert "myspace" not in sp.PLATFORMS


class TestCreatePost:

    def test_unknown_platform_returns_error(self):
        result = sp.create_post("EMP-1", "myspace", "hello")
        assert "error" in result
        assert "myspace" in result["error"]

    def test_valid_platform_with_no_scheduled_time_is_draft(self):
        post = sp.create_post("EMP-1", "facebook", "Check out our new inventory!")
        assert post.attributes["status"] == "draft"
        assert post.attributes["platform"] == "facebook"

    def test_valid_platform_with_scheduled_time_is_scheduled(self):
        post = sp.create_post("EMP-1", "instagram", "New arrivals", scheduled_time="2026-08-01T09:00:00")
        assert post.attributes["status"] == "scheduled"

    def test_content_defaults_to_empty_string(self):
        post = sp.create_post("EMP-1", "x", None)
        assert post.attributes["content"] == ""

    def test_linked_vehicle_ids_filters_out_nonexistent_ids(self):
        _vehicle("VEH-1")
        post = sp.create_post("EMP-1", "facebook", "Look at this", linked_vehicle_ids=["VEH-1", "VEH-MISSING"])
        assert post.attributes["linked_vehicle_ids"] == ["VEH-1"]

    def test_linked_vehicle_ids_filters_out_non_vehicle_entities(self):
        post_for_ref = sp.create_post("EMP-1", "facebook", "placeholder")
        post = sp.create_post("EMP-1", "facebook", "Another", linked_vehicle_ids=[post_for_ref.id])
        assert post.attributes["linked_vehicle_ids"] == []

    def test_created_post_is_retrievable(self):
        post = sp.create_post("EMP-1", "linkedin", "hello world")
        fetched = sp.get_post(post.id)
        assert fetched is not None
        assert fetched.attributes["content"] == "hello world"

    def test_target_date_stored(self):
        post = sp.create_post("EMP-1", "tiktok", "hi", target_date="2026-08-05")
        assert post.attributes["target_date"] == "2026-08-05"

    def test_created_by_and_timestamps_set(self):
        post = sp.create_post("EMP-9", "facebook", "hi")
        assert post.attributes["created_by"] == "EMP-9"
        assert post.attributes["created_at"]
        assert post.attributes["updated_at"]
        assert post.attributes["published_at"] is None


class TestGetPost:

    def test_returns_none_for_missing_id(self):
        assert sp.get_post("SOC-DOES-NOT-EXIST") is None

    def test_returns_none_for_wrong_entity_type(self):
        _vehicle("VEH-1")
        assert sp.get_post("VEH-1") is None

    def test_returns_the_real_post(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        assert sp.get_post(post.id).id == post.id


class TestUpdatePost:

    def test_returns_none_for_missing_post(self):
        assert sp.update_post("SOC-MISSING", {"content": "new"}) is None

    def test_non_editable_fields_are_ignored(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        updated = sp.update_post(post.id, {"status": "published", "created_by": "EMP-9"})
        assert updated.attributes["status"] == "draft"
        assert updated.attributes["created_by"] == "EMP-1"

    def test_editable_fields_are_applied(self):
        post = sp.create_post("EMP-1", "facebook", "old content")
        updated = sp.update_post(post.id, {"content": "new content", "platform": "instagram", "media_url": "http://x.png"})
        assert updated.attributes["content"] == "new content"
        assert updated.attributes["platform"] == "instagram"
        assert updated.attributes["media_url"] == "http://x.png"

    def test_linked_vehicle_ids_filtered_on_update_too(self):
        _vehicle("VEH-1")
        post = sp.create_post("EMP-1", "facebook", "hi")
        updated = sp.update_post(post.id, {"linked_vehicle_ids": ["VEH-1", "VEH-MISSING"]})
        assert updated.attributes["linked_vehicle_ids"] == ["VEH-1"]

    def test_setting_scheduled_time_on_a_draft_flips_status_to_scheduled(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        assert post.attributes["status"] == "draft"
        updated = sp.update_post(post.id, {"scheduled_time": "2026-08-01T09:00:00"})
        assert updated.attributes["status"] == "scheduled"

    def test_setting_scheduled_time_on_a_published_post_does_not_flip_status(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        sp.publish_post(post.id)
        updated = sp.update_post(post.id, {"scheduled_time": "2026-08-01T09:00:00"})
        assert updated.attributes["status"] == "published"

    def test_updated_at_refreshed(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        original_updated_at = post.attributes["updated_at"]
        updated = sp.update_post(post.id, {"content": "changed"})
        assert updated.attributes["updated_at"] is not None
        assert isinstance(original_updated_at, str)


class TestPublishPost:

    def test_returns_none_for_missing_post(self):
        assert sp.publish_post("SOC-MISSING") is None

    def test_draft_becomes_published(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        result = sp.publish_post(post.id)
        assert result.attributes["status"] == "published"
        assert result.attributes["published_at"] is not None

    def test_scheduled_becomes_published(self):
        post = sp.create_post("EMP-1", "facebook", "hi", scheduled_time="2026-08-01T09:00:00")
        result = sp.publish_post(post.id)
        assert result.attributes["status"] == "published"

    def test_already_published_returns_error(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        sp.publish_post(post.id)
        result = sp.publish_post(post.id)
        assert "error" in result

    def test_cancelled_post_cannot_be_published(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        sp.cancel_post(post.id)
        result = sp.publish_post(post.id)
        assert "error" in result


class TestCancelPost:

    def test_returns_none_for_missing_post(self):
        assert sp.cancel_post("SOC-MISSING") is None

    def test_draft_becomes_cancelled(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        result = sp.cancel_post(post.id)
        assert result.attributes["status"] == "cancelled"

    def test_scheduled_becomes_cancelled(self):
        post = sp.create_post("EMP-1", "facebook", "hi", scheduled_time="2026-08-01T09:00:00")
        result = sp.cancel_post(post.id)
        assert result.attributes["status"] == "cancelled"

    def test_already_published_cannot_be_cancelled(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        sp.publish_post(post.id)
        result = sp.cancel_post(post.id)
        assert "error" in result

    def test_already_cancelled_cannot_be_cancelled_again(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        sp.cancel_post(post.id)
        result = sp.cancel_post(post.id)
        assert "error" in result


class TestListPosts:

    def test_filters_by_platform(self):
        sp.create_post("EMP-1", "facebook", "a")
        sp.create_post("EMP-1", "instagram", "b")
        result = sp.list_posts(platform="facebook")
        assert len(result) == 1
        assert result[0].attributes["platform"] == "facebook"

    def test_filters_by_status(self):
        p1 = sp.create_post("EMP-1", "facebook", "a")
        p2 = sp.create_post("EMP-1", "facebook", "b")
        sp.publish_post(p1.id)
        result = sp.list_posts(status="published")
        assert len(result) == 1
        assert result[0].id == p1.id

    def test_filters_by_created_by(self):
        sp.create_post("EMP-1", "facebook", "a")
        sp.create_post("EMP-2", "facebook", "b")
        result = sp.list_posts(created_by="EMP-2")
        assert len(result) == 1
        assert result[0].attributes["created_by"] == "EMP-2"

    def test_no_filters_returns_all(self):
        sp.create_post("EMP-1", "facebook", "a")
        sp.create_post("EMP-2", "instagram", "b")
        assert len(sp.list_posts()) == 2

    def test_sorted_by_scheduled_time_or_created_at_descending(self):
        p1 = sp.create_post("EMP-1", "facebook", "earliest", scheduled_time="2026-08-01T09:00:00")
        p2 = sp.create_post("EMP-1", "facebook", "latest", scheduled_time="2026-08-05T09:00:00")
        result = sp.list_posts()
        assert result[0].id == p2.id
        assert result[1].id == p1.id


class TestGetCalendar:

    def test_excludes_cancelled_posts(self):
        post = sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-01")
        sp.cancel_post(post.id)
        result = sp.get_calendar()
        assert result["total"] == 0

    def test_includes_draft_with_target_date(self):
        sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-01")
        result = sp.get_calendar()
        assert "2026-08-01" in result["by_date"]
        assert result["total"] == 1

    def test_scheduled_time_takes_priority_over_target_date(self):
        sp.create_post("EMP-1", "facebook", "hi", scheduled_time="2026-08-10T09:00:00", target_date="2026-08-01")
        result = sp.get_calendar()
        assert "2026-08-10" in result["by_date"]
        assert "2026-08-01" not in result["by_date"]

    def test_published_at_takes_priority_over_target_date(self):
        post = sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-01")
        sp.publish_post(post.id)
        result = sp.get_calendar()
        published_date = post.attributes["published_at"][:10]
        # published_at is set at publish time, not equal to the original target_date
        assert published_date in result["by_date"]

    def test_post_with_no_resolvable_date_excluded(self):
        sp.create_post("EMP-1", "facebook", "hi")
        result = sp.get_calendar()
        assert result["total"] == 0

    def test_start_date_filter_excludes_earlier_entries(self):
        sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-01")
        result = sp.get_calendar(start_date="2026-08-05")
        assert result["total"] == 0

    def test_end_date_filter_excludes_later_entries(self):
        sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-10")
        result = sp.get_calendar(end_date="2026-08-05")
        assert result["total"] == 0

    def test_start_and_end_date_are_inclusive(self):
        sp.create_post("EMP-1", "facebook", "hi", target_date="2026-08-05")
        result = sp.get_calendar(start_date="2026-08-05", end_date="2026-08-05")
        assert result["total"] == 1

    def test_content_truncated_to_120_chars(self):
        long_content = "x" * 200
        sp.create_post("EMP-1", "facebook", long_content, target_date="2026-08-01")
        result = sp.get_calendar()
        entry = result["by_date"]["2026-08-01"][0]
        assert len(entry["content"]) == 120

    def test_multiple_posts_on_the_same_day_grouped_together(self):
        sp.create_post("EMP-1", "facebook", "a", target_date="2026-08-01")
        sp.create_post("EMP-1", "instagram", "b", target_date="2026-08-01")
        result = sp.get_calendar()
        assert len(result["by_date"]["2026-08-01"]) == 2
        assert result["total"] == 2


class TestResolveLinkedVehicles:

    def test_returns_empty_for_missing_post(self):
        assert sp.resolve_linked_vehicles("SOC-MISSING") == []

    def test_returns_empty_when_no_linked_vehicles(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        assert sp.resolve_linked_vehicles(post.id) == []

    def test_resolves_real_vehicles_with_expected_shape(self):
        _vehicle("VEH-1", year=2024, make="Ford", model="F-150", trim="XLT", price=45000)
        post = sp.create_post("EMP-1", "facebook", "hi", linked_vehicle_ids=["VEH-1"])
        result = sp.resolve_linked_vehicles(post.id)
        assert result == [{
            "id": "VEH-1",
            "year": 2024,
            "make": "Ford",
            "model": "F-150",
            "trim": "XLT",
            "price": 45000,
        }]


class TestGetVehicleBrief:

    def test_returns_none_for_missing_vehicle(self):
        assert sp.get_vehicle_brief("VEH-MISSING") is None

    def test_returns_none_for_non_vehicle_entity(self):
        post = sp.create_post("EMP-1", "facebook", "hi")
        assert sp.get_vehicle_brief(post.id) is None

    def test_returns_real_brief_for_a_vehicle(self):
        _vehicle("VEH-1", year=2023, make="Honda", model="Civic", trim="EX", price=25000)
        result = sp.get_vehicle_brief("VEH-1")
        assert result == {
            "id": "VEH-1",
            "year": 2023,
            "make": "Honda",
            "model": "Civic",
            "trim": "EX",
            "price": 25000,
        }


class TestSearchInventoryForPost:

    def test_excludes_sold_vehicles(self):
        _vehicle("VEH-1", make="Ford", date_sold="2026-01-01")
        _vehicle("VEH-2", make="Honda")
        result = sp.search_inventory_for_post()
        ids = [r["id"] for r in result]
        assert "VEH-1" not in ids
        assert "VEH-2" in ids

    def test_empty_query_returns_all_unsold(self):
        _vehicle("VEH-1", make="Ford")
        _vehicle("VEH-2", make="Honda")
        result = sp.search_inventory_for_post()
        assert len(result) == 2

    def test_query_filters_case_insensitively_across_fields(self):
        _vehicle("VEH-1", make="Ford", model="F-150")
        _vehicle("VEH-2", make="Honda", model="Civic")
        result = sp.search_inventory_for_post(query="ford")
        assert len(result) == 1
        assert result[0]["id"] == "VEH-1"

    def test_query_matches_vin_and_stock_number(self):
        _vehicle("VEH-1", vin="1FTFW1ET1EFA12345", stock="STK-99")
        result = sp.search_inventory_for_post(query="stk-99")
        assert len(result) == 1

    def test_respects_limit(self):
        for i in range(5):
            _vehicle(f"VEH-{i}", make="Ford")
        result = sp.search_inventory_for_post(limit=3)
        assert len(result) == 3

    def test_no_match_returns_empty(self):
        _vehicle("VEH-1", make="Ford")
        result = sp.search_inventory_for_post(query="totally-unmatched-string")
        assert result == []
