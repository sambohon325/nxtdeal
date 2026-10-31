"""Synthetic-only validation of design persistence and the existing owner gate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from core import websites
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core.permissions import SALES, ADMIN
from core.website_studio import catalogue, validate_config, update_studio_api, render_studio_events, studio_inventory_api
from datetime import date


@pytest.fixture
def site(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(websites, "save_graph", lambda *_: None)
    result = websites.create_website("Synthetic studio", "owner")
    yield result
    ledger.reset()


def config(**patch):
    return {"version": 1, "theme_id": "lone-star", **patch}


def test_reviewed_catalogue_identity():
    library = catalogue()
    assert len(library["themes"]) == 20
    assert len(library["events"]) == 46
    for event in library["events"]:
        assert event["titleEs"] and event["context"]
        assert event["image"].startswith("/website-studio/assets/")
    aa = [e for e in library["events"] if "African American" in e["category"]]
    assert len(aa) == 2


def test_owner_save_revision_and_stale_write(site):
    saved = update_studio_api(SALES, "owner", site.id, config(), 0)
    assert saved["studio_revision"] == 1
    assert saved["status"] == "draft"
    assert "error" in update_studio_api(SALES, "owner", site.id, config(theme_id="union"), 0)
    assert site.attributes["studio_config"]["theme_id"] == "lone-star"


def test_nonowner_cannot_write(site):
    assert "error" in update_studio_api(SALES, "stranger", site.id, config(), 0)
    assert "studio_config" not in site.attributes


@pytest.mark.parametrize("status", ["pending_approval", "published"])
def test_even_admin_cannot_mutate_review_or_live_design(site, status):
    site.attributes["status"] = status
    assert "error" in update_studio_api(ADMIN, "admin", site.id, config(), 0)
    assert "studio_config" not in site.attributes


@pytest.mark.parametrize("patch", [
    {"theme_id": "unknown"},
    {"social_links": {"facebook": "javascript:alert(1)"}},
    {"backgrounds": {"about": "https://user:password@example.com/image.png"}},
    {"events": [{"template_id": "spring", "starts_on": "2026-05-02", "ends_on": "2026-04-01"}]},
    {"events": [{"template_id": "spring", "enabled": "false"}]},
    {"events": [{"template_id": "spring", "starts_on": "20260501"}]},
    {"events": [{"template_id": "spring", "starts_on": None}]},
    {"events": [{"template_id": "spring"}, {"template_id": "spring"}]},
    {"arbitrary_html": "<script>"},
])
def test_invalid_settings_rejected_without_mutation(site, patch):
    assert "error" in update_studio_api(SALES, "owner", site.id, config(**patch), 0)
    assert "studio_config" not in site.attributes


def test_eligibility_references_only_current_tenant_inventory(site):
    candidate = config(events=[{"template_id": "spring", "vehicle_ids": ["car-1"]}])
    assert "error" in update_studio_api(SALES, "owner", site.id, candidate, 0)
    ledger.add_entity(Entity(id="car-1", entity_type=VEHICLE, attributes={"Make": "Test", "DateSold": None}))
    result = update_studio_api(SALES, "owner", site.id, candidate, 0)
    assert result["studio_config"]["events"][0]["vehicle_ids"] == ["car-1"]


def test_bilingual_custom_copy_preserved():
    result = validate_config(config(events=[{"template_id": "spring", "title": "Spring trucks", "title_es": "Camionetas de primavera"}]))
    assert result["events"][0]["title_es"] == "Camionetas de primavera"


def test_event_schedule_and_live_inventory_projection(site):
    vehicle = Entity(id="car-1", entity_type=VEHICLE, attributes={"Make": "Test", "DateSold": None})
    ledger.add_entity(vehicle)
    settings = config(events=[{"template_id": "spring", "enabled": True, "starts_on": "2026-03-01", "ends_on": "2026-03-31", "title_es": "Oferta local", "vehicle_ids": ["car-1"]}])
    assert "error" not in update_studio_api(SALES, "owner", site.id, settings, 0)
    assert render_studio_events(site, date(2026, 2, 28)) == []
    visible = render_studio_events(site, date(2026, 3, 1))
    assert visible[0]["title_es"] == "Oferta local"
    assert len(visible[0]["vehicles"]) == 1
    vehicle.attributes["DateSold"] = "2026-03-02"
    assert render_studio_events(site, date(2026, 3, 2))[0]["vehicles"] == []
    assert render_studio_events(site, date(2026, 4, 1)) == []


def test_disabled_events_never_render(site):
    update_studio_api(SALES, "owner", site.id, config(events=[{"template_id": "spring", "enabled": False}]), 0)
    assert render_studio_events(site) == []


def test_inventory_picker_uses_owner_access(site):
    assert "error" in studio_inventory_api(SALES, "stranger", site.id)
    assert studio_inventory_api(SALES, "owner", site.id) == []


def test_rendered_website_includes_saved_event_copy(site):
    update_studio_api(SALES, "owner", site.id, config(events=[{"template_id": "spring", "enabled": True, "title": "Dealer's spring event"}]), 0)
    assert websites.get_website_rendered(site.id)["studio_events"][0]["title"] == "Dealer's spring event"

@pytest.mark.parametrize("mutation", [
    lambda id: websites.update_admin_settings(id, {"header_script": "changed"}),
    lambda id: websites.update_page_seo(id, "home", {"title": "changed"}),
    lambda id: websites.set_section_locked(id, "home", 0, False),
    lambda id: websites.update_section_fields(id, "home", 0, {"headline": "changed"}),
    lambda id: websites.add_section(id, "home", "text_block", {}),
    lambda id: websites.set_mode(id, "ai"),
    lambda id: websites.apply_site_template(id, "modern"),
    lambda id: websites.generate_vehicle_page_description(id, "car-1"),
])
@pytest.mark.parametrize("status", ["pending_approval", "published"])
def test_core_studio_content_paths_are_read_only(site, mutation, status):
    from copy import deepcopy
    update_studio_api(SALES, "owner", site.id, config(), 0)
    site.attributes["status"] = status
    before = deepcopy(site.attributes)
    assert "error" in mutation(site.id)
    assert site.attributes == before


def test_review_freezes_content_and_rejects_bypass_mutation(site):
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    assert site.attributes["review_snapshot"]["name"] == "Synthetic studio"
    site.attributes["name"] = "Unreviewed change"
    assert "error" in websites.approve_website(site.id, "reviewer")
    assert site.attributes["status"] == "pending_approval"
    assert "published_snapshot" not in site.attributes


def test_rejected_site_can_edit_and_resubmit(site):
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.reject_website(site.id, "reviewer")
    assert "error" not in update_studio_api(SALES, "owner", site.id, config(theme_id="union"), 1)
    websites.submit_for_approval(site.id, "owner")
    assert websites.approve_website(site.id, "reviewer").attributes["status"] == "published"
    assert site.attributes["published_snapshot"]["studio_config"]["theme_id"] == "union"


def test_public_uses_approved_content_and_omits_internal_metadata(site, monkeypatch):
    from core import websites_api
    monkeypatch.setattr(websites_api, "record_page_view", lambda *args, **kwargs: None)
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer", "Internal review notes")
    site.attributes["name"] = "Unreviewed change"
    site.attributes["studio_config"]["theme_id"] = "union"
    public = websites_api.get_public_website_api(site.id)
    assert public["name"] == "Synthetic studio"
    assert public["studio_config"]["theme_id"] == "lone-star"
    for key in ("review_snapshot", "published_snapshot", "history", "owners", "requested_by", "reviewed_by", "review_notes", "vehicle_pages"):
        assert key not in public
    preview = websites_api.preview_website_api(SALES, "owner", site.id)
    assert preview["name"] == "Unreviewed change"
    assert preview["studio_config"]["theme_id"] == "union"


def test_review_vehicle_copy_is_frozen(site):
    update_studio_api(SALES, "owner", site.id, config(), 0)
    ledger.add_entity(Entity(id="car-1", entity_type=VEHICLE, attributes={"Make": "Test"}))
    site.attributes["vehicle_pages"] = {"car-1": {"description": "Approved description"}}
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    site.attributes["vehicle_pages"]["car-1"]["description"] = "Unapproved description"
    assert websites.get_vehicle_landing_page(site.id, "car-1")["description"] == "Approved description"



def test_stale_review_stops_before_compliance_gate(site, monkeypatch):
    from core import websites_api
    from core.permissions import MARKETING
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    site.attributes["pages"]["home"]["sections"].append({"section_key": "text_block", "fields": {"body": "Unreviewed"}})
    def unexpected_gate(*args):
        raise AssertionError("Stale submission must stop before the publication gate")
    monkeypatch.setattr(websites_api, "enforce_gate", unexpected_gate)
    assert "error" in websites_api.approve_website_api(MARKETING, "reviewer", site.id)
    assert site.attributes["status"] == "pending_approval"


def test_current_review_still_requires_compliance(site, monkeypatch):
    from core import websites_api
    from core.permissions import MARKETING
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    monkeypatch.setattr(websites_api, "enforce_gate", lambda *args: {"blocked": True, "alert_id": "synthetic", "violations": [], "notice": "Needs correction"})
    assert "error" in websites_api.approve_website_api(MARKETING, "reviewer", site.id)
    assert site.attributes["status"] == "pending_approval"
    assert "published_snapshot" not in site.attributes


def test_published_event_inventory_remains_live(site):
    vehicle = Entity(id="car-1", entity_type=VEHICLE, attributes={"Make": "Test", "DateSold": None})
    ledger.add_entity(vehicle)
    update_studio_api(SALES, "owner", site.id, config(events=[{"template_id": "spring", "enabled": True, "vehicle_ids": ["car-1"]}]), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    assert len(websites.get_website_rendered(site.id, published=True)["studio_events"][0]["vehicles"]) == 1
    vehicle.attributes["DateSold"] = "2026-10-20"
    assert websites.get_website_rendered(site.id, published=True)["studio_events"][0]["vehicles"] == []

@pytest.mark.parametrize("theme", [item["id"] for item in catalogue()["themes"]])
def test_create_approved_design_is_one_canonical_draft(site, theme, monkeypatch):
    from uuid import uuid4
    from core.website_studio import create_studio_api
    saves = []
    monkeypatch.setattr(websites, "save_graph", lambda *_: saves.append(True))
    count = len(websites.list_websites())
    result = create_studio_api("owner", "Synthetic new dealer", theme, str(uuid4()))
    assert result["status"] == "draft"
    assert result["studio_config"]["theme_id"] == theme
    assert result["owners"] == ["owner"]
    assert result["studio_revision"] == 1
    assert len(websites.list_websites()) == count + 1
    assert len(saves) == 1
    assert result["pages"]["inventory"]["sections"][0]["section_key"] == "inventory_grid"
    assert result["pages"]["contact"]["sections"][0]["section_key"] == "contact_form"
    assert not result["studio_config"]["events"]
    assert "testimonials_carousel" not in str(result["pages"])


def test_creation_retry_does_not_duplicate_or_overwrite(site):
    from uuid import uuid4
    from core.website_studio import create_studio_api
    key = str(uuid4())
    first = create_studio_api("owner", "Original", "union", key)
    retry = create_studio_api("owner", "Changed", "tempo", key)
    assert retry["id"] == first["id"]
    assert retry["name"] == "Original"
    assert retry["studio_config"]["theme_id"] == "union"
    other = create_studio_api("other-owner", "Other", "tempo", key)
    assert other["id"] != first["id"]
    assert other["owners"] == ["other-owner"]


@pytest.mark.parametrize("name,theme,key,mode", [
    ("", "union", "00000000-0000-4000-8000-000000000000", "traditional"),
    ("Dealer", "missing", "00000000-0000-4000-8000-000000000000", "traditional"),
    ("Dealer", "union", "invalid", "traditional"),
    ("Dealer", "union", "00000000-0000-4000-8000-000000000000", "invalid"),
])
def test_invalid_creation_does_not_leave_empty_record(site, name, theme, key, mode):
    from core.website_studio import create_studio_api
    count = len(websites.list_websites())
    assert "error" in create_studio_api("owner", name, theme, key, mode)
    assert len(websites.list_websites()) == count


def test_location_projection_and_filter_before_limit(site):
    ledger.add_entity(Entity(id="loc-north", entity_type="Location", attributes={"name": "North", "address": "Synthetic address", "private_note": "Never public"}))
    ledger.add_entity(Entity(id="loc-south", entity_type="Location", attributes={"name": "South"}))
    ledger.add_entity(Entity(id="car-1", entity_type=VEHICLE, attributes={"location_id": "loc-north"}))
    ledger.add_entity(Entity(id="car-2", entity_type=VEHICLE, attributes={"location_id": "loc-south"}))
    result = websites.get_live_inventory(location_id="loc-south", limit=1)
    assert [v["id"] for v in result] == ["car-2"]
    assert result[0]["location_name"] == "South"
    assert "private_note" not in str(websites.get_live_inventory())
    websites.approve_website(site.id, "reviewer")
    detail = websites.get_vehicle_landing_page(site.id, "car-1")
    assert detail["location_name"] == "North"
    assert detail["location_address"] == "Synthetic address"


def test_unresolved_location_does_not_leak_raw_identifier(site):
    ledger.add_entity(Entity(id="private-employee", entity_type="Employee", attributes={"name": "Private name"}))
    ledger.add_entity(Entity(id="car-1", entity_type=VEHICLE, attributes={"location_id": "private-employee"}))
    result = websites.get_live_inventory()[0]
    assert result["location_id"] is None
    assert result["location_name"] is None


def test_existing_named_rooftop_resolves_without_creating_config(site):
    car = Entity(id="car-1", entity_type=VEHICLE, attributes={"Location": "North"})
    ledger.add_entity(car)
    assert websites.website_vehicle_location(car)["location_name"] is None
    assert ledger.get_entity("SYSCFG-00001") is None
    ledger.add_entity(Entity(id="SYSCFG-00001", entity_type="SystemConfig", attributes={"locations": [{"name": "North", "address": "Synthetic address"}]}))
    assert websites.get_live_inventory(location_id="name:North")[0]["location_name"] == "North"


def test_background_and_event_artwork_survive_review_snapshot(site):
    settings = config(backgrounds={"about": "/website-studio/assets/scene-forest.png", "contact": "https://images.example.test/contact.jpg"}, events=[{"template_id": "spring", "enabled": True, "banner_url": "https://images.example.test/banner.jpg", "image_url": "https://images.example.test/truck.jpg"}])
    assert "error" not in update_studio_api(SALES, "owner", site.id, settings, 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    rendered = websites.get_website_rendered(site.id, published=True)
    assert rendered["studio_config"]["backgrounds"]["about"].endswith("scene-forest.png")
    assert rendered["studio_events"][0]["banner_url"] == "https://images.example.test/banner.jpg"
    assert rendered["studio_events"][0]["image_url"] == "https://images.example.test/truck.jpg"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:image/png;base64,abc", "//remote.example/image.png", "/website-studio/assets/../private"])
def test_unsafe_backgrounds_rejected(site, url):
    assert "error" in update_studio_api(SALES, "owner", site.id, config(backgrounds={"about": url}), 0)


def test_published_vehicle_brand_and_contact_socials_are_reviewed(site):
    vehicle = Entity(id="car-1", entity_type=VEHICLE, attributes={"Make": "Test"})
    ledger.add_entity(vehicle)
    websites.add_section(site.id, "contact", "contact_form", {"heading": "Contact"})
    update_studio_api(SALES, "owner", site.id, config(theme_id="tempo", social_links={"snapchat": "https://example.test/social"}), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    site.attributes["studio_config"]["theme_id"] = "union"
    site.attributes["studio_config"]["social_links"]["snapchat"] = "https://example.test/unreviewed"
    detail = websites.get_vehicle_landing_page(site.id, "car-1")
    assert detail["theme_id"] == "tempo"
    assert detail["social_links"]["snapchat"] == "https://example.test/social"
    public = websites.get_website_rendered(site.id, published=True)
    assert public["pages"]["contact"]["sections"][0]["social_links"]["snapchat"] == "https://example.test/social"


def test_vehicle_inquiry_creates_canonical_lead_and_interest(site, monkeypatch):
    from core import lead_intake
    monkeypatch.setattr(lead_intake, "save_graph", lambda *_: None)
    from core.websites_api import submit_contact_form_api
    vehicle = Entity(id="car-1", entity_type=VEHICLE, attributes={"VIN": "SYNTHETIC-ONLY", "Make": "Test"})
    ledger.add_entity(vehicle)
    websites.add_section(site.id, "contact", "contact_form", {"heading": "Contact"})
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    result = submit_contact_form_api(site.id, "contact", 0, "Synthetic Shopper", email="shopper@example.test", vehicle_id="car-1", intent="purchase")
    assert "error" not in result
    lead = ledger.get_entity(result["lead_id"])
    assert lead.attributes["WebsiteVehicleID"] == "car-1"
    assert lead.attributes["WebsiteInquiryIntent"] == "purchase"
    assert lead.attributes["VIN"] == "SYNTHETIC-ONLY"
    assert sum(r.source_id == lead.id and r.target_id == "car-1" and r.relationship_type == "INTERESTED_IN" for r in ledger.relationships) == 1


@pytest.mark.parametrize("vehicle_id,intent,index,email", [("missing", "purchase", 0, "x@example.test"), (None, "invalid", 0, "x@example.test"), (None, "information", 99, "x@example.test"), (None, "information", 0, "   ")])
def test_invalid_studio_inquiry_creates_no_lead(site, vehicle_id, intent, index, email):
    websites.add_section(site.id, "contact", "contact_form", {"heading": "Contact"})
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    before = sum(e.entity_type == "Lead" for e in ledger.get_all().values())
    assert "error" in websites.submit_contact_form(site.id, "contact", index, "Synthetic", email=email, vehicle_id=vehicle_id, intent=intent)
    assert sum(e.entity_type == "Lead" for e in ledger.get_all().values()) == before


def test_inquiry_retry_and_provenance_are_single_durable_write(site, monkeypatch):
    from core import lead_intake
    from core.websites_api import submit_contact_form_api
    from uuid import uuid4
    saves = []
    ledger.add_entity(Entity(id="car-1", entity_type=VEHICLE, attributes={}))
    site.attributes["status"] = "published"
    def capture(*_):
        leads = [e for e in ledger.get_all().values() if e.entity_type == "Lead"]
        assert len(leads) == 1
        lead = leads[0]
        assert lead.attributes["WebsiteID"] == site.id
        assert lead.attributes["WebsiteVehicleID"] == "car-1"
        assert lead.attributes["WebsiteRequestID"] == key
        assert any(r.source_id == lead.id and r.target_id == "car-1" for r in ledger.relationships)
        saves.append(lead.id)
    monkeypatch.setattr(lead_intake, "save_graph", capture)
    key = str(uuid4())
    args = dict(email="test@example.test", vehicle_id="car-1", intent="purchase", request_id=key)
    first = submit_contact_form_api(site.id, "contact", 0, "Synthetic Shopper", **args)
    assert submit_contact_form_api(site.id, "contact", 0, "Synthetic Shopper", **args) == first
    assert len(saves) == 1
    assert "error" in submit_contact_form_api(site.id, "contact", 0, "Different Shopper", **args)
    assert len(saves) == 1


def test_inquiry_failure_rolls_back_lead_relationships_registry_and_history(site, monkeypatch):
    from core import lead_intake
    from core.dealeros import registry
    from copy import deepcopy
    from uuid import uuid4
    key = str(uuid4())
    websites.get_website(site.id)  # Normalize legacy defaults before measuring the transaction.
    before = deepcopy(site.attributes)
    relationships = list(ledger.relationships)
    registered = dict(registry.lead_ids)
    def fail(*_):
        raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(lead_intake, "save_graph", fail)
    with pytest.raises(OSError):
        websites.submit_contact_form(site.id, "contact", 0, "Synthetic", email="test@example.test", request_id=key)
    assert site.attributes == before
    assert ledger.relationships == relationships
    assert registry.lead_ids == registered
    assert not any(e.entity_type == "Lead" for e in ledger.get_all().values())
    monkeypatch.setattr(lead_intake, "save_graph", lambda *_: None)
    result = websites.submit_contact_form(site.id, "contact", 0, "Synthetic", email="test@example.test", request_id=key)
    assert "lead_id" in result


def test_inquiry_retry_key_is_scoped_to_site(site, monkeypatch):
    from core import lead_intake
    from uuid import uuid4
    monkeypatch.setattr(lead_intake, "save_graph", lambda *_: None)
    key = str(uuid4())
    other = websites.create_website("Other synthetic", "other-owner")
    a = websites.submit_contact_form(site.id, "contact", 0, "Synthetic", email="test@example.test", request_id=key)
    b = websites.submit_contact_form(other.id, "contact", 0, "Synthetic", email="test@example.test", request_id=key)
    assert a["lead_id"] != b["lead_id"]
    assert b["assigned_to"] == "other-owner"
    count = len(ledger.get_all())
    assert "error" in websites.submit_contact_form(site.id, "contact", 0, "Synthetic", email="test@example.test", request_id="bad")
    assert len(ledger.get_all()) == count



def test_successor_draft_keeps_approved_content_until_next_approval(site, monkeypatch):
    from core.website_studio import start_draft_api
    from core.websites_api import get_public_website_api, submit_contact_form_api
    from core import lead_intake
    monkeypatch.setattr(lead_intake, "save_graph", lambda *_: None)
    websites.add_section(site.id, "contact", "contact_form", {"heading": "Approved contact"})
    update_studio_api(SALES, "owner", site.id, config(theme_id="tempo"), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    assert "error" in start_draft_api(SALES, "other", site.id)
    assert start_draft_api(SALES, "owner", site.id)["status"] == "draft"
    websites.update_section_fields(site.id, "contact", 0, {"heading": "New contact"})
    start_draft_api(SALES, "owner", site.id)  # A retry must preserve edited draft.
    assert site.attributes["pages"]["contact"]["sections"][0]["fields"]["heading"] == "New contact"
    for transition in [lambda: None, lambda: websites.submit_for_approval(site.id, "owner"), lambda: websites.reject_website(site.id, "reviewer")]:
        transition()
        public = get_public_website_api(site.id)
        assert public["status"] == "published"
        assert public["pages"]["contact"]["sections"][0]["fields"]["heading"] == "Approved contact"
        assert "lead_id" in submit_contact_form_api(site.id, "contact", 0, "Synthetic", email="test@example.test")
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    assert get_public_website_api(site.id)["pages"]["contact"]["sections"][0]["fields"]["heading"] == "New contact"
    assert len(websites.list_websites()) == 1


def test_failed_successor_publish_cannot_replace_public_snapshot(site, monkeypatch):
    from core.website_studio import start_draft_api
    from core.websites_api import get_public_website_api
    from copy import deepcopy
    update_studio_api(SALES, "owner", site.id, config(theme_id="tempo"), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    start_draft_api(SALES, "owner", site.id)
    update_studio_api(SALES, "owner", site.id, config(theme_id="union"), 2)
    websites.submit_for_approval(site.id, "owner")
    before = deepcopy(site.attributes)
    def fail(*_): raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(websites, "save_graph", fail)
    with pytest.raises(OSError): websites.approve_website(site.id, "reviewer")
    assert site.attributes == before
    assert get_public_website_api(site.id)["studio_config"]["theme_id"] == "tempo"


def test_public_inventory_filters_all_stock_before_paging(site):
    from core.website_studio import public_inventory_api, start_draft_api
    assert "error" in public_inventory_api(site.id)
    update_studio_api(SALES, "owner", site.id, config(), 0)
    websites.submit_for_approval(site.id, "owner")
    websites.approve_website(site.id, "reviewer")
    for location in ("north", "south"):
        ledger.add_entity(Entity(id=location, entity_type="Location", attributes={"name": location.title()}))
    for index in range(35):
        ledger.add_entity(Entity(id=f"car-{index:03}", entity_type=VEHICLE, attributes={"Make": "Synthetic", "Model": "Truck" if index < 30 else "Sedan", "Year": 2024, "location_id": "north" if index < 20 else "south", "private_cost": 123, "Price": 25000}))
    ledger.add_entity(Entity(id="sold", entity_type=VEHICLE, attributes={"DateSold": "2026-10-01", "location_id": "south"}))
    first = public_inventory_api(site.id)
    second = public_inventory_api(site.id, page=2)
    assert first["total"] == 35 and first["pages"] == 3
    assert len(first["vehicles"]) == len(second["vehicles"]) == 12
    assert not set(v["id"] for v in first["vehicles"]) & set(v["id"] for v in second["vehicles"])
    south = public_inventory_api(site.id, location_id="south")
    assert south["total"] == 15 and len(south["vehicles"]) == 12
    assert all(v["location_id"] == "south" for v in south["vehicles"])
    assert public_inventory_api(site.id, query="sedan", location_id="south")["total"] == 5
    assert public_inventory_api(site.id, location_id="missing")["vehicles"] == []
    assert public_inventory_api(site.id, page=100)["page"] == 3
    assert "private_cost" not in str(first)
    assert "sold" not in [v["id"] for v in public_inventory_api(site.id, page_size=48)["vehicles"]]
    start_draft_api(SALES, "owner", site.id)
    assert public_inventory_api(site.id)["total"] == 35
    assert "error" in public_inventory_api(site.id, page_size=100)
