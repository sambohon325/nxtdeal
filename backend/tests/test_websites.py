"""
Tests for the website/inventory builder (core/websites.py, core/websites_api.py) --
session 32. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import VEHICLE, IMAGE
from core import websites
from core import websites_api
from core.permissions import ADMIN, MARKETING, SALES, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_audit_writes(monkeypatch):

    monkeypatch.setattr(websites_api, "save_audit_log", lambda filepath: None)


def _add_vehicle(vehicle_id, make="Honda", model="Civic", price="30000", date_sold=None):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={
            "Make": make,
            "Model": model,
            "Price": price,
            "Year": "2025",
            "Mileage": "10",
            "DateSold": date_sold,
        },
    ))

    return vehicle_id


def _add_image(image_id, vehicle_id, url):

    ledger.add_entity(Entity(id=image_id, entity_type=IMAGE, attributes={"URL": url}))

    ledger.add_relationship(Relationship(source_id=vehicle_id, target_id=image_id, relationship_type="HAS_IMAGE"))


# --- Section/page catalog ---


def test_list_section_templates_returns_supported_templates():

    templates = websites.list_section_templates()

    assert {t["key"] for t in templates} == {
        "hero_banner",
        "text_block",
        "image_gallery",
        "inventory_grid",
        "contact_form", "testimonials_carousel", "google_rating_badge", "social_links",
        "financing_info", "oem_branding_banner", "car_builder", "custom_html",
        "ask_dealeros", "payment_builder", "trade_evaluation", "buy_online", "delivery_scheduling",
    }


def test_list_page_keys_returns_six_fixed_pages():

    keys = [p["key"] for p in websites.list_page_keys()]

    assert keys == ["home", "inventory", "about", "testimonials", "financing", "contact"]


# --- Create / edit lifecycle ---


def test_create_website_starts_as_draft_with_empty_pages():

    result = websites_api.create_website_api("EMP-00001", "Acme Ford")

    assert "error" not in result
    assert result["status"] == "draft"
    assert result["requested_by"] == "EMP-00001"
    assert set(result["pages"].keys()) == {"home", "inventory", "about", "testimonials", "financing", "contact"}
    assert result["pages"]["home"]["sections"] == []


def test_create_website_rejects_blank_name():

    result = websites_api.create_website_api("EMP-00001", "   ")

    assert "error" in result


def test_add_section_rejects_unknown_page():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "not-a-page", "text_block", {"body": "hi"})

    assert "error" in result


def test_add_section_rejects_unknown_template():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "not-a-template", {})

    assert "error" in result


def test_add_section_rejects_missing_required_field():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "text_block", {})

    assert "error" in result
    assert "body" in result["error"]


def test_add_section_success_appends_to_page():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(
        SALES, "EMP-00001", site["id"], "home", "hero_banner", {"headline": "Welcome"}
    )

    assert "error" not in result
    assert len(result["pages"]["home"]["sections"]) == 1
    assert result["pages"]["home"]["sections"][0]["section_key"] == "hero_banner"


def test_add_section_denied_for_non_builder_non_admin():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(SALES, "EMP-00002", site["id"], "home", "hero_banner", {"headline": "Hi"})

    assert "error" in result


def test_add_section_allowed_for_admin_regardless_of_builder():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.add_section_api(ADMIN, "EMP-99999", site["id"], "home", "hero_banner", {"headline": "Hi"})

    assert "error" not in result


def test_cannot_edit_after_submitted():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    result = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "hero_banner", {"headline": "Hi"})

    assert "error" in result


def test_remove_section_removes_by_index():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    site = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "hero_banner", {"headline": "Hi"})
    site = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "text_block", {"body": "text"})

    result = websites_api.remove_section_api(SALES, "EMP-00001", site["id"], "home", 0)

    assert len(result["pages"]["home"]["sections"]) == 1
    assert result["pages"]["home"]["sections"][0]["section_key"] == "text_block"


def test_remove_section_rejects_out_of_range_index():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.remove_section_api(SALES, "EMP-00001", site["id"], "home", 0)

    assert "error" in result


# --- Submit lifecycle ---


def test_submit_requires_being_the_builder():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    denied = websites_api.submit_website_api(SALES, "EMP-00002", site["id"])
    assert "error" in denied

    allowed = websites_api.submit_website_api(SALES, "EMP-00001", site["id"])
    assert allowed["status"] == "pending_approval"


def test_cannot_resubmit_a_pending_site():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    result = websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    assert "error" in result


def test_rejected_site_can_be_edited_and_resubmitted():
    """Deliberate deviation from the asset workflow (which requires a fresh draft to
    resubmit): a rejected site can be revised in place and resubmitted, since sending
    someone all the way back to a blank draft after one rejected review would be a worse
    builder experience than assets/campaigns' one-shot approval flow."""

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])
    websites_api.reject_website_api(MARKETING, "EMP-00002", site["id"], "Needs a real headline")

    edited = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "hero_banner", {"headline": "Fixed"})
    assert "error" not in edited

    resubmitted = websites_api.submit_website_api(SALES, "EMP-00001", site["id"])
    assert resubmitted["status"] == "pending_approval"


# --- Approval queue ACL ---


def test_pending_websites_denied_for_non_marketing_non_admin():

    result = websites_api.list_pending_websites_api(SALES)

    assert "error" in result


def test_pending_websites_allowed_for_marketing_and_admin():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    for role in (MARKETING, ADMIN):
        result = websites_api.list_pending_websites_api(role)
        assert isinstance(result, list)
        assert any(w["id"] == site["id"] for w in result)


def test_approve_denied_for_non_marketing_non_admin():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    result = websites_api.approve_website_api(SERVICE, "EMP-00002", site["id"])

    assert "error" in result


def test_approve_requires_pending_status():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.approve_website_api(MARKETING, "EMP-00002", site["id"])

    assert "error" in result


def test_approve_success_publishes_and_records_reviewer():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    result = websites_api.approve_website_api(MARKETING, "EMP-00002", site["id"], "Looks great")

    assert result["status"] == "published"
    assert result["reviewed_by"] == "EMP-00002"
    assert result["review_notes"] == "Looks great"
    assert result["published_at"] is not None


def test_reject_success_records_reviewer_and_notes():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.submit_website_api(SALES, "EMP-00001", site["id"])

    result = websites_api.reject_website_api(ADMIN, "EMP-00003", site["id"], "Wrong hours")

    assert result["status"] == "rejected"
    assert result["reviewed_by"] == "EMP-00003"
    assert result["review_notes"] == "Wrong hours"


# --- Visibility / listing ---


def test_get_website_visible_to_builder():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.get_website_api(SALES, "EMP-00001", site["id"])

    assert "error" not in result


def test_get_website_denied_to_unrelated_non_reviewer():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")

    result = websites_api.get_website_api(SALES, "EMP-00002", site["id"])

    assert "error" in result


def test_list_my_websites_only_returns_own_sites():

    websites_api.create_website_api("EMP-00001", "Acme Ford")
    websites_api.create_website_api("EMP-00002", "Acme Honda")

    mine = websites_api.list_my_websites_api("EMP-00001")

    assert len(mine) == 1
    assert mine[0]["requested_by"] == "EMP-00001"


def test_list_websites_most_recent_first():

    first = websites_api.create_website_api("EMP-00001", "Site A")
    second = websites_api.create_website_api("EMP-00001", "Site B")

    mine = websites_api.list_my_websites_api("EMP-00001")

    assert [w["id"] for w in mine] == [second["id"], first["id"]]


# --- Live inventory (DriveFinder-lite) ---


def test_get_live_inventory_excludes_sold_vehicles():

    _add_vehicle("VEH-1", date_sold=None)
    _add_vehicle("VEH-2", date_sold="2026-01-01")

    result = websites.get_live_inventory()

    assert [v["id"] for v in result] == ["VEH-1"]


def test_get_live_inventory_filters_by_make():

    _add_vehicle("VEH-1", make="Honda")
    _add_vehicle("VEH-2", make="Ford")

    result = websites.get_live_inventory(make="Ford")

    assert [v["id"] for v in result] == ["VEH-2"]


def test_get_live_inventory_filters_by_max_price():

    _add_vehicle("VEH-1", price="25000")
    _add_vehicle("VEH-2", price="45000")

    result = websites.get_live_inventory(max_price="30000")

    assert [v["id"] for v in result] == ["VEH-1"]


def test_get_live_inventory_respects_limit():

    for i in range(5):
        _add_vehicle(f"VEH-{i}")

    result = websites.get_live_inventory(limit=2)

    assert len(result) == 2


def test_get_live_inventory_includes_linked_image_url():

    _add_vehicle("VEH-1")
    _add_image("IMG-1", "VEH-1", "https://example.com/civic.jpg")

    result = websites.get_live_inventory()

    assert result[0]["image_url"] == "https://example.com/civic.jpg"


def test_get_live_inventory_image_url_none_when_unlinked():

    _add_vehicle("VEH-1")

    result = websites.get_live_inventory()

    assert result[0]["image_url"] is None


# --- Rendering (inventory_grid resolves to live data) ---


def test_get_website_api_renders_inventory_grid_with_live_vehicles():

    _add_vehicle("VEH-1", make="Honda")

    site = websites_api.create_website_api("EMP-00001", "Acme Honda")
    site = websites_api.add_section_api(
        SALES, "EMP-00001", site["id"], "inventory", "inventory_grid", {"make": "Honda"}
    )

    rendered = websites_api.get_website_api(SALES, "EMP-00001", site["id"])

    inventory_sections = rendered["pages"]["inventory"]["sections"]
    assert len(inventory_sections) == 1
    assert inventory_sections[0]["live_vehicles"][0]["id"] == "VEH-1"


def test_get_website_api_home_page_sections_have_no_live_vehicles_key():

    site = websites_api.create_website_api("EMP-00001", "Acme Ford")
    site = websites_api.add_section_api(SALES, "EMP-00001", site["id"], "home", "hero_banner", {"headline": "Hi"})

    rendered = websites_api.get_website_api(SALES, "EMP-00001", site["id"])

    assert "live_vehicles" not in rendered["pages"]["home"]["sections"][0]
