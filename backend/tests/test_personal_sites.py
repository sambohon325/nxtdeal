import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import PERSONAL_SITE, WEBSITE, VEHICLE, LEAD, WEBSITE_ANALYTICS_EVENT
from core import personal_sites
from core import personal_sites_api
from core import lead_intake
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(personal_sites, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_intake, "save_graph", lambda filepath: None)


def make_website(suffix="00001", **extra):
    attrs = {"admin_settings": {}}
    attrs.update(extra)
    entity = Entity(id=f"SITE-{suffix}", entity_type=WEBSITE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_vehicle(suffix="00001", date_sold=None, **extra):
    attrs = {
        "Year": 2023, "Make": "Toyota", "Model": "Camry", "Trim": "LE",
        "Price": 28000, "Mileage": 12000, "DateSold": date_sold,
    }
    attrs.update(extra)
    entity = Entity(id=f"VEH-{suffix}", entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def make_site(employee_id="EMP-00001", slug="john-smith", parent_website_id=None):
    result = personal_sites.create_personal_site(employee_id, slug, parent_website_id=parent_website_id)
    assert "error" not in (result if isinstance(result, dict) and "error" in result else {})
    return result


# ---------------------------------------------------------------------------
# slug_available / slug validation
# ---------------------------------------------------------------------------

class TestSlugValidation:

    def test_available_when_no_sites_exist(self):
        assert personal_sites.slug_available("john-smith") is True

    def test_unavailable_once_taken(self):
        make_site(slug="john-smith")
        assert personal_sites.slug_available("john-smith") is False

    def test_case_insensitive_uniqueness_check(self):
        make_site(slug="john-smith")
        assert personal_sites.slug_available("JOHN-SMITH") is False

    def test_excludes_the_given_site_id_from_the_collision_check(self):
        site = make_site(slug="john-smith")
        assert personal_sites.slug_available("john-smith", exclude_site_id=site.id) is True

    def test_create_rejects_uppercase_or_invalid_characters(self):
        result = personal_sites.create_personal_site("EMP-00001", "John_Smith!")
        assert "error" in result

    def test_create_rejects_leading_hyphen(self):
        result = personal_sites.create_personal_site("EMP-00001", "-johnsmith")
        assert "error" in result

    def test_create_rejects_trailing_hyphen(self):
        result = personal_sites.create_personal_site("EMP-00001", "johnsmith-")
        assert "error" in result

    def test_create_rejects_empty_slug(self):
        result = personal_sites.create_personal_site("EMP-00001", "")
        assert "error" in result

    def test_create_rejects_slug_over_fifty_characters(self):
        too_long = "a" * 51
        result = personal_sites.create_personal_site("EMP-00001", too_long)
        assert "error" in result

    def test_create_accepts_slug_at_exactly_fifty_characters(self):
        exactly_fifty = "a" + ("b" * 48) + "c"
        assert len(exactly_fifty) == 50
        result = personal_sites.create_personal_site("EMP-00001", exactly_fifty)
        assert isinstance(result, Entity)

    def test_create_accepts_a_single_character_slug(self):
        # Real behavior quirk: the error message claims "2-50 characters" but the
        # regex's trailing group is fully optional, so a single character actually
        # passes validation.
        result = personal_sites.create_personal_site("EMP-00001", "a")
        assert isinstance(result, Entity)
        assert result.attributes["slug"] == "a"

    def test_create_lowercases_the_slug(self):
        result = personal_sites.create_personal_site("EMP-00001", "JohnSmith")
        assert isinstance(result, Entity)
        assert result.attributes["slug"] == "johnsmith"


# ---------------------------------------------------------------------------
# create_personal_site
# ---------------------------------------------------------------------------

class TestCreatePersonalSite:

    def test_happy_path_defaults(self):
        site = personal_sites.create_personal_site("EMP-00001", "john-smith")

        assert "error" not in site.attributes if isinstance(site.attributes, dict) else True
        assert site.entity_type == PERSONAL_SITE
        assert site.attributes["employee_id"] == "EMP-00001"
        assert site.attributes["slug"] == "john-smith"
        assert site.attributes["status"] == "draft"
        assert site.attributes["parent_website_id"] is None
        assert site.attributes["cta_text"] == "Get In Touch"
        assert site.attributes["featured_vehicle_ids"] == []
        assert len(site.attributes["history"]) == 1
        assert site.attributes["history"][0]["action"] == "created"

    def test_duplicate_slug_rejected(self):
        make_site(slug="john-smith")
        result = personal_sites.create_personal_site("EMP-00002", "john-smith")
        assert result == {"error": "Slug 'john-smith' is already taken"}

    def test_nonexistent_parent_website_rejected(self):
        result = personal_sites.create_personal_site("EMP-00001", "john-smith", parent_website_id="SITE-99999")
        assert result == {"error": "parent_website_id does not refer to a real Website"}

    def test_parent_website_id_pointing_at_wrong_entity_type_rejected(self):
        vehicle = make_vehicle()
        result = personal_sites.create_personal_site("EMP-00001", "john-smith", parent_website_id=vehicle.id)
        assert result == {"error": "parent_website_id does not refer to a real Website"}

    def test_real_parent_website_accepted(self):
        website = make_website()
        result = personal_sites.create_personal_site("EMP-00001", "john-smith", parent_website_id=website.id)
        assert isinstance(result, Entity)
        assert result.attributes["parent_website_id"] == website.id

    def test_no_parent_website_id_is_allowed(self):
        result = personal_sites.create_personal_site("EMP-00001", "john-smith", parent_website_id=None)
        assert isinstance(result, Entity)


# ---------------------------------------------------------------------------
# get_personal_site / get_personal_site_by_slug
# ---------------------------------------------------------------------------

class TestGetPersonalSite:

    def test_returns_none_for_nonexistent_id(self):
        assert personal_sites.get_personal_site("PSITE-99999") is None

    def test_returns_none_for_wrong_entity_type(self):
        website = make_website()
        assert personal_sites.get_personal_site(website.id) is None

    def test_returns_the_real_entity(self):
        site = make_site()
        found = personal_sites.get_personal_site(site.id)
        assert found is not None
        assert found.id == site.id

    def test_backfills_missing_featured_vehicle_ids_and_history(self):
        entity = Entity(id="PSITE-00099", entity_type=PERSONAL_SITE, attributes={"employee_id": "EMP-00001"})
        ledger.add_entity(entity)

        found = personal_sites.get_personal_site(entity.id)
        assert found.attributes["featured_vehicle_ids"] == []
        assert found.attributes["history"] == []


class TestGetPersonalSiteBySlug:

    def test_returns_none_when_not_found(self):
        assert personal_sites.get_personal_site_by_slug("no-such-slug") is None

    def test_finds_by_exact_slug(self):
        site = make_site(slug="jane-doe")
        found = personal_sites.get_personal_site_by_slug("jane-doe")
        assert found.id == site.id

    def test_case_insensitive_lookup(self):
        site = make_site(slug="jane-doe")
        found = personal_sites.get_personal_site_by_slug("JANE-DOE")
        assert found.id == site.id


# ---------------------------------------------------------------------------
# update_personal_site
# ---------------------------------------------------------------------------

class TestUpdatePersonalSite:

    def test_site_not_found(self):
        result = personal_sites.update_personal_site("PSITE-99999", {"headline": "Hi"})
        assert result == {"error": "Personal site not found"}

    def test_updates_whitelisted_fields(self):
        site = make_site()
        result = personal_sites.update_personal_site(
            site.id,
            {
                "headline": "Your Trusted Advisor",
                "bio": "20 years in the business",
                "featured_vehicle_ids": ["VEH-00001"],
            },
            by="EMP-00001",
        )
        assert result.attributes["headline"] == "Your Trusted Advisor"
        assert result.attributes["bio"] == "20 years in the business"
        assert result.attributes["featured_vehicle_ids"] == ["VEH-00001"]

    def test_ignores_non_whitelisted_fields(self):
        site = make_site(employee_id="EMP-00001", slug="john-smith")
        result = personal_sites.update_personal_site(
            site.id,
            {"employee_id": "EMP-99999", "slug": "hijacked", "status": "active"},
            by="EMP-00001",
        )
        assert result.attributes["employee_id"] == "EMP-00001"
        assert result.attributes["slug"] == "john-smith"
        assert result.attributes["status"] == "draft"

    def test_logs_a_history_entry_naming_the_changed_fields(self):
        site = make_site()
        personal_sites.update_personal_site(site.id, {"headline": "Hi", "bio": "Bio"}, by="EMP-00001")

        last_entry = site.attributes["history"][-1]
        assert last_entry["action"] == "updated"
        assert last_entry["by"] == "EMP-00001"
        assert "headline" in last_entry["notes"]
        assert "bio" in last_entry["notes"]

    def test_no_op_patch_leaves_history_and_updated_at_untouched(self):
        site = make_site()
        original_history_len = len(site.attributes["history"])
        original_updated_at = site.attributes["updated_at"]

        result = personal_sites.update_personal_site(site.id, {"not_a_real_field": "x"}, by="EMP-00001")

        assert "error" not in (result if isinstance(result, dict) and "error" in result else {})
        assert len(site.attributes["history"]) == original_history_len
        assert site.attributes["updated_at"] == original_updated_at

    def test_empty_patch_still_returns_the_site(self):
        site = make_site()
        result = personal_sites.update_personal_site(site.id, {}, by="EMP-00001")
        assert result.id == site.id


# ---------------------------------------------------------------------------
# set_slug
# ---------------------------------------------------------------------------

class TestSetSlug:

    def test_site_not_found(self):
        result = personal_sites.set_slug("PSITE-99999", "new-slug")
        assert result == {"error": "Personal site not found"}

    def test_invalid_new_slug_rejected(self):
        site = make_site()
        result = personal_sites.set_slug(site.id, "-bad-slug-")
        assert "error" in result

    def test_taken_slug_rejected(self):
        make_site(slug="taken-slug")
        site_b = make_site(slug="original-slug")

        result = personal_sites.set_slug(site_b.id, "taken-slug")
        assert result == {"error": "Slug 'taken-slug' is already taken"}

    def test_setting_to_its_own_current_slug_is_allowed(self):
        site = make_site(slug="my-slug")
        result = personal_sites.set_slug(site.id, "my-slug", by="EMP-00001")
        assert isinstance(result, Entity)
        assert result.attributes["slug"] == "my-slug"

    def test_happy_path_logs_history_with_old_and_new_slug(self):
        site = make_site(slug="old-slug")
        result = personal_sites.set_slug(site.id, "new-slug", by="EMP-00001")

        assert result.attributes["slug"] == "new-slug"
        last_entry = result.attributes["history"][-1]
        assert last_entry["action"] == "slug_changed"
        assert "old-slug" in last_entry["notes"]
        assert "new-slug" in last_entry["notes"]


# ---------------------------------------------------------------------------
# set_parent_website
# ---------------------------------------------------------------------------

class TestSetParentWebsite:

    def test_site_not_found(self):
        result = personal_sites.set_parent_website("PSITE-99999", "SITE-00001")
        assert result == {"error": "Personal site not found"}

    def test_nonexistent_parent_rejected(self):
        site = make_site()
        result = personal_sites.set_parent_website(site.id, "SITE-99999")
        assert result == {"error": "parent_website_id does not refer to a real Website"}

    def test_wrong_entity_type_rejected(self):
        site = make_site()
        vehicle = make_vehicle()
        result = personal_sites.set_parent_website(site.id, vehicle.id)
        assert result == {"error": "parent_website_id does not refer to a real Website"}

    def test_can_be_cleared_to_none(self):
        website = make_website()
        site = make_site(parent_website_id=website.id)

        result = personal_sites.set_parent_website(site.id, None, by="EMP-00001")
        assert isinstance(result, Entity)
        assert result.attributes["parent_website_id"] is None

    def test_happy_path_sets_real_parent(self):
        site = make_site()
        website = make_website()

        result = personal_sites.set_parent_website(site.id, website.id, by="EMP-00001")
        assert result.attributes["parent_website_id"] == website.id
        assert result.attributes["history"][-1]["action"] == "parent_website_changed"


# ---------------------------------------------------------------------------
# set_personal_site_status
# ---------------------------------------------------------------------------

class TestSetPersonalSiteStatus:

    def test_site_not_found(self):
        result = personal_sites.set_personal_site_status("PSITE-99999", "active")
        assert result == {"error": "Personal site not found"}

    def test_unknown_status_rejected(self):
        site = make_site()
        result = personal_sites.set_personal_site_status(site.id, "published")
        assert "error" in result
        assert "published" in result["error"]

    @pytest.mark.parametrize("status", personal_sites.STATUSES)
    def test_every_valid_status_accepted(self, status):
        site = make_site()
        result = personal_sites.set_personal_site_status(site.id, status, by="EMP-00001")
        assert result.attributes["status"] == status
        assert result.attributes["history"][-1]["action"] == "status_changed"


# ---------------------------------------------------------------------------
# get_personal_site_rendered / _resolve_featured_vehicles
# ---------------------------------------------------------------------------

class TestGetPersonalSiteRendered:

    def test_returns_none_when_site_not_found(self):
        assert personal_sites.get_personal_site_rendered("PSITE-99999") is None

    def test_default_branding_when_no_parent(self):
        site = make_site()
        rendered = personal_sites.get_personal_site_rendered(site.id)

        assert rendered["branding"] == {"branding_mode": "independent", "oem_name": None, "oem_logo_url": None}

    def test_default_branding_when_parent_id_points_nowhere(self):
        site = make_site(parent_website_id=None)
        site.attributes["parent_website_id"] = "SITE-99999"  # dangling reference

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["branding"]["branding_mode"] == "independent"

    def test_default_branding_when_parent_is_wrong_entity_type(self):
        vehicle = make_vehicle()
        site = make_site()
        site.attributes["parent_website_id"] = vehicle.id

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["branding"]["branding_mode"] == "independent"

    def test_live_borrows_real_parent_branding(self):
        website = make_website(admin_settings={
            "branding_mode": "oem", "oem_name": "Ford", "oem_logo_url": "https://example.com/ford.png",
        })
        site = make_site(parent_website_id=website.id)

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["branding"] == {
            "branding_mode": "oem", "oem_name": "Ford", "oem_logo_url": "https://example.com/ford.png",
        }

    def test_branding_reflects_live_parent_changes_not_a_snapshot(self):
        website = make_website(admin_settings={"branding_mode": "independent"})
        site = make_site(parent_website_id=website.id)

        first = personal_sites.get_personal_site_rendered(site.id)
        assert first["branding"]["branding_mode"] == "independent"

        website.attributes["admin_settings"]["branding_mode"] = "oem"
        website.attributes["admin_settings"]["oem_name"] = "Toyota"

        second = personal_sites.get_personal_site_rendered(site.id)
        assert second["branding"]["branding_mode"] == "oem"
        assert second["branding"]["oem_name"] == "Toyota"

    def test_excludes_featured_vehicle_ids_key_but_includes_featured_vehicles(self):
        site = make_site()
        rendered = personal_sites.get_personal_site_rendered(site.id)

        assert "featured_vehicle_ids" not in rendered
        assert rendered["featured_vehicles"] == []

    def test_resolves_real_unsold_featured_vehicles(self):
        vehicle = make_vehicle("00001")
        site = make_site()
        site.attributes["featured_vehicle_ids"] = [vehicle.id]

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert len(rendered["featured_vehicles"]) == 1
        assert rendered["featured_vehicles"][0] == {
            "id": vehicle.id, "year": 2023, "make": "Toyota", "model": "Camry",
            "trim": "LE", "price": 28000, "mileage": 12000,
        }

    def test_skips_a_sold_featured_vehicle(self):
        vehicle = make_vehicle("00001", date_sold="2026-06-01")
        site = make_site()
        site.attributes["featured_vehicle_ids"] = [vehicle.id]

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["featured_vehicles"] == []

    def test_skips_a_nonexistent_featured_vehicle_id(self):
        site = make_site()
        site.attributes["featured_vehicle_ids"] = ["VEH-99999"]

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["featured_vehicles"] == []

    def test_skips_a_featured_id_pointing_at_the_wrong_entity_type(self):
        website = make_website()
        site = make_site()
        site.attributes["featured_vehicle_ids"] = [website.id]

        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["featured_vehicles"] == []

    def test_includes_id_and_top_level_attributes(self):
        site = make_site()
        rendered = personal_sites.get_personal_site_rendered(site.id)
        assert rendered["id"] == site.id
        assert rendered["slug"] == site.attributes["slug"]
        assert rendered["status"] == "draft"


# ---------------------------------------------------------------------------
# record_personal_site_view / get_personal_site_analytics
# ---------------------------------------------------------------------------

class TestRecordAndAnalytics:

    def test_record_creates_a_real_analytics_event(self):
        site = make_site()
        event = personal_sites.record_personal_site_view(site.id, viewer_ref="EMP-00001")

        assert event.entity_type == WEBSITE_ANALYTICS_EVENT
        assert event.attributes["WebsiteID"] == site.id
        assert event.attributes["PageKey"] == "personal_site"
        assert event.attributes["ViewerRef"] == "EMP-00001"
        assert event.attributes["Timestamp"] is not None

    def test_record_allows_anonymous_viewer_ref(self):
        site = make_site()
        event = personal_sites.record_personal_site_view(site.id)
        assert event.attributes["ViewerRef"] is None

    def test_analytics_empty_when_no_views(self):
        site = make_site()
        stats = personal_sites.get_personal_site_analytics(site.id)
        assert stats == {"personal_site_id": site.id, "total_views": 0, "by_day": {}}

    def test_analytics_counts_only_this_site_and_only_personal_site_page_key(self):
        site_a = make_site(slug="site-a")
        site_b = make_site(slug="site-b")

        personal_sites.record_personal_site_view(site_a.id)
        personal_sites.record_personal_site_view(site_a.id)
        personal_sites.record_personal_site_view(site_b.id)

        # a view on some other page key with the same WebsiteID should not count
        other_event = Entity(
            id="PVIEW-90001", entity_type=WEBSITE_ANALYTICS_EVENT,
            attributes={"WebsiteID": site_a.id, "PageKey": "home", "Timestamp": "2026-07-19T00:00:00+00:00"},
        )
        ledger.add_entity(other_event)

        stats = personal_sites.get_personal_site_analytics(site_a.id)
        assert stats["total_views"] == 2

    def test_analytics_buckets_by_day_sorted(self):
        site = make_site()

        for ts in [
            "2026-07-01T09:00:00+00:00",
            "2026-07-01T15:00:00+00:00",
            "2026-06-30T09:00:00+00:00",
        ]:
            event = Entity(
                id=f"PVIEW-{ts}", entity_type=WEBSITE_ANALYTICS_EVENT,
                attributes={"WebsiteID": site.id, "PageKey": "personal_site", "Timestamp": ts},
            )
            ledger.add_entity(event)

        stats = personal_sites.get_personal_site_analytics(site.id)
        assert stats["total_views"] == 3
        assert stats["by_day"] == {"2026-06-30": 1, "2026-07-01": 2}
        assert list(stats["by_day"].keys()) == ["2026-06-30", "2026-07-01"]


# ---------------------------------------------------------------------------
# submit_personal_site_contact_form
# ---------------------------------------------------------------------------

class TestSubmitContactForm:

    @pytest.mark.parametrize("name,email,phone", [
        ("   ", "visitor@example.com", None),
        ("Visitor", "   ", "\t"),
    ])
    def test_whitespace_only_details_rejected_without_creating_lead(self, name, email, phone):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        result = personal_sites.submit_personal_site_contact_form(site.id, name, email=email, phone=phone)
        assert "error" in result
        assert not any(e.entity_type == LEAD for e in ledger.get_all().values())

    def test_site_not_found(self):
        result = personal_sites.submit_personal_site_contact_form("PSITE-99999", "John Doe", email="j@example.com")
        assert result == {"error": "Personal site not found"}

    def test_draft_site_rejected_with_same_not_found_message(self):
        site = make_site()  # defaults to draft
        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe", email="j@example.com")
        assert result == {"error": "Personal site not found"}

    def test_inactive_site_rejected(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        personal_sites.set_personal_site_status(site.id, "inactive", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe", email="j@example.com")
        assert result == {"error": "Personal site not found"}

    def test_missing_name_rejected(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "", email="j@example.com")
        assert result == {"error": "name and at least one of email/phone are required"}

    def test_missing_both_email_and_phone_rejected(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe")
        assert result == {"error": "name and at least one of email/phone are required"}

    def test_email_only_is_sufficient(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe", email="j@example.com")
        assert "error" not in result

    def test_phone_only_is_sufficient(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe", phone="555-0100")
        assert "error" not in result

    def test_no_owner_rejected(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        site.attributes["employee_id"] = None

        result = personal_sites.submit_personal_site_contact_form(site.id, "John Doe", email="j@example.com")
        assert result == {"error": "This page has no owner to route the lead to"}

    def test_happy_path_creates_a_lead_assigned_to_the_site_owner(self):
        site = make_site(employee_id="EMP-00042")
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00042")

        result = personal_sites.submit_personal_site_contact_form(
            site.id, "Jane Prospect", email="jane@example.com", phone="555-0100", message="Interested in a truck",
        )

        assert "error" not in result
        assert result["assigned_to"] == "EMP-00042"
        lead = ledger.get_entity(result["lead_id"])
        assert lead.entity_type == LEAD
        assert lead.attributes["FirstName"] == "Jane"
        assert lead.attributes["LastName"] == "Prospect"
        assert lead.attributes["Source"] == "Website"
        assert lead.attributes["AssignedSalesperson"] == "EMP-00042"
        assert lead.attributes["PersonalSiteID"] == site.id
        assert lead.attributes["Message"] == "Interested in a truck"

    def test_single_word_name_has_empty_last_name(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "Madonna", email="m@example.com")
        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["FirstName"] == "Madonna"
        assert lead.attributes["LastName"] == ""

    def test_logs_history_and_bumps_updated_at(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "Jane Doe", email="j@example.com")

        last_entry = site.attributes["history"][-1]
        assert last_entry["action"] == "contact_form_submitted"
        assert result["lead_id"] in last_entry["notes"]

    def test_no_message_defaults_to_empty_string(self):
        site = make_site()
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites.submit_personal_site_contact_form(site.id, "Jane Doe", email="j@example.com")
        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["Message"] == ""


# ---------------------------------------------------------------------------
# list_personal_sites
# ---------------------------------------------------------------------------

class TestListPersonalSites:

    def test_empty_when_no_sites(self):
        assert personal_sites.list_personal_sites() == []

    def test_filters_by_employee_id(self):
        site_a = make_site(employee_id="EMP-00001", slug="site-a")
        make_site(employee_id="EMP-00002", slug="site-b")

        result = personal_sites.list_personal_sites(employee_id="EMP-00001")
        assert len(result) == 1
        assert result[0].id == site_a.id

    def test_filters_by_status(self):
        site_a = make_site(slug="site-a")
        personal_sites.set_personal_site_status(site_a.id, "active", by="EMP-00001")
        make_site(slug="site-b")  # stays draft

        result = personal_sites.list_personal_sites(status="active")
        assert len(result) == 1
        assert result[0].id == site_a.id

    def test_filters_by_employee_id_and_status_together(self):
        site_a = make_site(employee_id="EMP-00001", slug="site-a")
        personal_sites.set_personal_site_status(site_a.id, "active", by="EMP-00001")
        site_b = make_site(employee_id="EMP-00001", slug="site-b")  # draft, same employee
        make_site(employee_id="EMP-00002", slug="site-c")

        result = personal_sites.list_personal_sites(employee_id="EMP-00001", status="active")
        assert len(result) == 1
        assert result[0].id == site_a.id

    def test_sorted_most_recently_created_first_with_id_tiebreak(self):
        site_a = make_site(slug="site-a")
        site_b = make_site(slug="site-b")
        # Force identical created_at to exercise the id tiebreaker.
        site_a.attributes["created_at"] = "2026-07-01T00:00:00+00:00"
        site_b.attributes["created_at"] = "2026-07-01T00:00:00+00:00"

        result = personal_sites.list_personal_sites()
        assert [s.id for s in result] == sorted([site_a.id, site_b.id], reverse=True)


# ---------------------------------------------------------------------------
# personal_sites_api -- ACL / thin-wrapper layer
# ---------------------------------------------------------------------------

class TestCheckSlugApi:

    def test_reports_availability_and_normalizes_slug(self):
        result = personal_sites_api.check_slug_api("John-Smith")
        assert result == {"slug": "john-smith", "available": True}

    def test_reports_unavailable_when_taken(self):
        make_site(slug="john-smith")
        result = personal_sites_api.check_slug_api("john-smith")
        assert result == {"slug": "john-smith", "available": False}


class TestCreatePersonalSiteApi:

    def test_serializes_the_created_site(self):
        result = personal_sites_api.create_personal_site_api(SALES, "EMP-00001", "john-smith")
        assert "error" not in result
        assert result["employee_id"] == "EMP-00001"
        assert result["slug"] == "john-smith"

    def test_passes_through_errors(self):
        make_site(slug="taken")
        result = personal_sites_api.create_personal_site_api(SALES, "EMP-00002", "taken")
        assert "error" in result


class TestGetMyPersonalSiteApi:

    def test_returns_none_when_no_site_exists(self):
        assert personal_sites_api.get_my_personal_site_api("EMP-00001") is None

    def test_returns_serialized_site(self):
        make_site(employee_id="EMP-00001", slug="my-site")
        result = personal_sites_api.get_my_personal_site_api("EMP-00001")
        assert result["slug"] == "my-site"


class TestListPersonalSitesApi:

    def test_non_admin_always_sees_only_their_own_sites(self):
        make_site(employee_id="EMP-00001", slug="mine")
        make_site(employee_id="EMP-00002", slug="not-mine")

        result = personal_sites_api.list_personal_sites_api(SALES, "EMP-00001")
        assert len(result) == 1
        assert result[0]["slug"] == "mine"

    def test_admin_with_mine_only_true_sees_only_their_own(self):
        make_site(employee_id="EMP-00001", slug="admin-own")
        make_site(employee_id="EMP-00002", slug="someone-elses")

        result = personal_sites_api.list_personal_sites_api(ADMIN, "EMP-00001", mine_only=True)
        assert len(result) == 1
        assert result[0]["slug"] == "admin-own"

    def test_admin_with_mine_only_false_sees_everything(self):
        make_site(employee_id="EMP-00001", slug="site-a")
        make_site(employee_id="EMP-00002", slug="site-b")

        result = personal_sites_api.list_personal_sites_api(ADMIN, "EMP-00001", mine_only=False)
        assert len(result) == 2


class TestOwnershipGatedApis:
    """get_personal_site_api / update / set_slug / set_parent / set_status /
    preview / analytics all share the same `_owns` gate: ADMIN, or the acting
    employee_id must equal the site's own employee_id."""

    def test_get_denied_to_a_non_owner_non_admin(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_api(SALES, "EMP-00002", site.id)
        assert result == {"error": "You don't have access to this page"}

    def test_get_allowed_to_the_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_api(SALES, "EMP-00001", site.id)
        assert "error" not in result
        assert result["id"] == site.id

    def test_get_allowed_to_admin_regardless_of_ownership(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_api(ADMIN, "EMP-99999", site.id)
        assert "error" not in result

    def test_get_site_not_found(self):
        result = personal_sites_api.get_personal_site_api(ADMIN, "EMP-00001", "PSITE-99999")
        assert result == {"error": "Personal site not found"}

    def test_update_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.update_personal_site_api(SALES, "EMP-00002", site.id, {"headline": "Hi"})
        assert result == {"error": "You don't have access to edit this page"}

    def test_update_allowed_to_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.update_personal_site_api(SALES, "EMP-00001", site.id, {"headline": "Hi"})
        assert result["headline"] == "Hi"

    def test_set_slug_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.set_personal_site_slug_api(SALES, "EMP-00002", site.id, "new-slug")
        assert result == {"error": "You don't have access to edit this page"}

    def test_set_slug_allowed_to_owner(self):
        site = make_site(employee_id="EMP-00001", slug="old-slug")
        result = personal_sites_api.set_personal_site_slug_api(SALES, "EMP-00001", site.id, "new-slug")
        assert result["slug"] == "new-slug"

    def test_set_parent_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        website = make_website()
        result = personal_sites_api.set_personal_site_parent_api(SALES, "EMP-00002", site.id, website.id)
        assert result == {"error": "You don't have access to edit this page"}

    def test_set_parent_allowed_to_owner(self):
        site = make_site(employee_id="EMP-00001")
        website = make_website()
        result = personal_sites_api.set_personal_site_parent_api(SALES, "EMP-00001", site.id, website.id)
        assert result["parent_website_id"] == website.id

    def test_set_status_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.set_personal_site_status_api(SALES, "EMP-00002", site.id, "active")
        assert result == {"error": "You don't have access to this page"}

    def test_set_status_allowed_to_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.set_personal_site_status_api(SALES, "EMP-00001", site.id, "active")
        assert result["status"] == "active"

    def test_preview_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.preview_personal_site_api(SALES, "EMP-00002", site.id)
        assert result == {"error": "You don't have access to this page"}

    def test_preview_allowed_to_owner_without_recording_customer_traffic(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.preview_personal_site_api(SALES, "EMP-00001", site.id)
        assert "error" not in result

        stats = personal_sites.get_personal_site_analytics(site.id)
        assert stats["total_views"] == 0

    def test_analytics_denied_to_non_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_analytics_api(SALES, "EMP-00002", site.id)
        assert result == {"error": "You don't have access to this page"}

    def test_analytics_allowed_to_owner(self):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_analytics_api(SALES, "EMP-00001", site.id)
        assert "total_views" in result

    @pytest.mark.parametrize("role", [OPERATIONS, MARKETING, FINANCE, SERVICE])
    def test_ownership_gate_applies_regardless_of_role_when_not_admin(self, role):
        site = make_site(employee_id="EMP-00001")
        result = personal_sites_api.get_personal_site_api(role, "EMP-00002", site.id)
        assert result == {"error": "You don't have access to this page"}


class TestPublicApis:

    def test_public_page_excludes_internal_and_future_private_attributes(self):
        site = make_site(slug="public-rep")
        site.attributes.update({
            "headline": "Meet your rep", "email": "public@example.com",
            "internal_notes": "never public", "future_private_field": {"secret": True},
        })
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        result = personal_sites_api.get_public_personal_site_api("public-rep")
        assert set(result) == {
            "slug", "headline", "subheadline", "bio", "photo_url", "phone",
            "email", "cta_text", "calendar_link", "review_link", "featured_vehicles", "branding",
        }
        assert result["headline"] == "Meet your rep"
        assert result["email"] == "public@example.com"
        # Owner editing/preview retains its complete record and audit history.
        owner = personal_sites_api.get_personal_site_api(SALES, "EMP-00001", site.id)
        assert owner["employee_id"] == "EMP-00001"
        assert owner["history"]
        assert owner["internal_notes"] == "never public"

    def test_public_featured_vehicle_and_branding_do_not_expose_private_data(self):
        website = make_website(admin_settings={"oem_name": "Example", "private_key": "secret"})
        vehicle = make_vehicle(Cost=21000, CustomerID="private-customer")
        site = make_site(slug="public-rep", parent_website_id=website.id)
        site.attributes["featured_vehicle_ids"] = [vehicle.id]
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        result = personal_sites_api.get_public_personal_site_api("public-rep")
        assert result["branding"]["oem_name"] == "Example"
        assert "private_key" not in result["branding"]
        assert result["featured_vehicles"][0]["price"] == 28000
        assert "Cost" not in result["featured_vehicles"][0]
        assert "CustomerID" not in result["featured_vehicles"][0]

    def test_get_public_returns_error_for_unknown_slug(self):
        result = personal_sites_api.get_public_personal_site_api("no-such-slug")
        assert result == {"error": "Page not found"}

    def test_get_public_returns_error_for_draft_site(self):
        make_site(slug="john-smith")  # defaults to draft
        result = personal_sites_api.get_public_personal_site_api("john-smith")
        assert result == {"error": "Page not found"}

    def test_get_public_returns_error_for_inactive_site(self):
        site = make_site(slug="john-smith")
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")
        personal_sites.set_personal_site_status(site.id, "inactive", by="EMP-00001")

        result = personal_sites_api.get_public_personal_site_api("john-smith")
        assert result == {"error": "Page not found"}

    def test_get_public_serves_an_active_site_and_records_an_anonymous_view(self):
        site = make_site(slug="john-smith")
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00001")

        result = personal_sites_api.get_public_personal_site_api("john-smith")
        assert "error" not in result
        assert result["slug"] == "john-smith"

        stats = personal_sites.get_personal_site_analytics(site.id)
        assert stats["total_views"] == 1

    def test_submit_contact_form_unknown_slug(self):
        result = personal_sites_api.submit_personal_site_contact_form_api("no-such-slug", "Jane Doe", email="j@example.com")
        assert result == {"error": "Page not found"}

    def test_submit_contact_form_happy_path(self):
        site = make_site(slug="john-smith", employee_id="EMP-00007")
        personal_sites.set_personal_site_status(site.id, "active", by="EMP-00007")

        result = personal_sites_api.submit_personal_site_contact_form_api(
            "john-smith", "Jane Doe", email="jane@example.com",
        )
        assert "error" not in result
        assert result["assigned_to"] == "EMP-00007"

    def test_submit_contact_form_on_draft_site_via_slug_lookup(self):
        make_site(slug="john-smith")  # draft
        result = personal_sites_api.submit_personal_site_contact_form_api(
            "john-smith", "Jane Doe", email="jane@example.com",
        )
        # Slug lookup itself succeeds (site exists), but the underlying
        # not-active check still rejects it with the same "not found" message.
        assert result == {"error": "Personal site not found"}

class TestFeaturedSelectionBoundary:
    @pytest.mark.parametrize('value', ['VEH-00001', None, {}, [None], [{}], [''], [' '], ['x' * 129], ['VEH-1'] * 25])
    def test_invalid_selection_does_not_partially_update(self, value):
        site = make_site()
        before = dict(site.attributes)
        result = personal_sites.update_personal_site(site.id, {'headline': 'Changed', 'featured_vehicle_ids': value})
        assert 'error' in result
        assert site.attributes == before

    def test_selection_deduplicates_and_resolves_current_inventory(self):
        vehicle = make_vehicle()
        site = make_site()
        result = personal_sites.update_personal_site(site.id, {'featured_vehicle_ids': [vehicle.id, vehicle.id]})
        assert result.attributes['featured_vehicle_ids'] == [vehicle.id]
        assert len(personal_sites.get_personal_site_rendered(site.id)['featured_vehicles']) == 1
        vehicle.attributes['DateSold'] = '2026-10-03'
        assert personal_sites.get_personal_site_rendered(site.id)['featured_vehicles'] == []

    def test_legacy_malformed_selection_does_not_break_public_render(self):
        vehicle = make_vehicle()
        site = make_site()
        site.attributes['featured_vehicle_ids'] = [{}, None, vehicle.id, vehicle.id]
        assert len(personal_sites.get_personal_site_rendered(site.id)['featured_vehicles']) == 1
        site.attributes['featured_vehicle_ids'] = {'invalid': vehicle.id}
        assert personal_sites.get_personal_site_rendered(site.id)['featured_vehicles'] == []

    def test_failed_save_restores_selection_and_history(self, monkeypatch):
        from copy import deepcopy
        site = make_site()
        before = deepcopy(site.attributes)
        def fail(_):
            raise OSError('fixture save failure')
        monkeypatch.setattr(personal_sites, 'save_graph', fail)
        with pytest.raises(OSError):
            personal_sites.update_personal_site(site.id, {'featured_vehicle_ids': ['VEH-1']}, by='EMP-00001')
        assert site.attributes == before

    def test_other_employee_cannot_change_selection(self):
        site = make_site()
        result = personal_sites_api.update_personal_site_api(SALES, 'EMP-OTHER', site.id, {'featured_vehicle_ids': ['VEH-1']})
        assert 'error' in result
        assert site.attributes['featured_vehicle_ids'] == []

@pytest.mark.parametrize('unlink', [False, True])
def test_parent_save_failure_restores_link_history_and_rendering(monkeypatch, unlink):
    from copy import deepcopy
    old = make_website('OLD', admin_settings={'branding_mode':'oem','oem_name':'Original'})
    new = make_website('NEW', admin_settings={'branding_mode':'oem','oem_name':'Replacement'})
    site = make_site(parent_website_id=old.id)
    before = deepcopy(site.attributes)
    def fail(_):
        raise OSError('fixture save failure')
    monkeypatch.setattr(personal_sites, 'save_graph', fail)
    with pytest.raises(OSError):
        personal_sites.set_parent_website(site.id, None if unlink else new.id, by='EMP-00001')
    assert site.attributes == before
    assert personal_sites.get_personal_site_rendered(site.id)['branding']['oem_name'] == 'Original'


def test_failed_creation_releases_slug_and_owner_lookup_for_retry(monkeypatch):
    existing = make_site(slug='existing-page')
    before = dict(ledger.get_all())
    failed_ids = []
    def fail(_):
        failed_ids.append(personal_sites.get_personal_site_by_slug('retry-page').id)
        raise OSError('fixture persistence failure')
    monkeypatch.setattr(personal_sites, 'save_graph', fail)
    with pytest.raises(OSError):
        personal_sites_api.create_personal_site_api(SALES, 'EMP-RETRY', 'retry-page')
    assert ledger.get_all() == before
    assert ledger.get_entity(existing.id) is existing
    assert personal_sites.slug_available('retry-page') is True
    assert personal_sites.get_personal_site_by_slug('retry-page') is None
    assert personal_sites_api.get_my_personal_site_api('EMP-RETRY') is None
    monkeypatch.setattr(personal_sites, 'save_graph', lambda _: None)
    result = personal_sites_api.create_personal_site_api(SALES, 'EMP-RETRY', 'retry-page')
    assert result['id'] not in failed_ids
    assert personal_sites_api.get_my_personal_site_api('EMP-RETRY')['id'] == result['id']
    assert len(personal_sites.list_personal_sites(employee_id='EMP-RETRY')) == 1

@pytest.mark.parametrize('link', ['javascript:alert(1)', 'http://example.com', 'https://u:p@example.com', 'https://example.com/\nfoo', 'https://example.com:bad', 'https://', {}, ['https://example.com']])
def test_review_destination_rejects_invalid_values_without_changes(link):
    from copy import deepcopy
    site = make_site()
    before = deepcopy(site.attributes)
    result = personal_sites_api.update_personal_site_api(SALES, 'EMP-00001', site.id, {'review_link':link})
    assert 'error' in result
    assert site.attributes == before


def test_review_link_uses_existing_owner_and_publication_boundaries():
    site = make_site()
    link = 'https://example.com/review'
    assert 'error' in personal_sites_api.update_personal_site_api(SALES, 'OTHER', site.id, {'review_link':link})
    assert personal_sites_api.update_personal_site_api(SALES, 'EMP-00001', site.id, {'review_link':link})['review_link'] == link
    assert 'error' in personal_sites_api.get_public_personal_site_api('john-smith')
    personal_sites.set_personal_site_status(site.id, 'active')
    public = personal_sites_api.get_public_personal_site_api('john-smith')
    assert public['review_link'] == link
    assert 'history' not in public
    personal_sites.update_personal_site(site.id, {'review_link':''})
    assert personal_sites_api.get_public_personal_site_api('john-smith')['review_link'] is None


def test_contact_first_persist_already_contains_page_message_and_assignment(monkeypatch, tmp_path):
    from core.relationship_types import ASSIGNED_TO
    site = make_site()
    personal_sites.set_personal_site_status(site.id, 'active')
    path = str(tmp_path / 'first-contact-save.json')
    monkeypatch.setattr(lead_intake, 'save_graph', lambda _: ledger.save(path))
    def fail_history(_): raise OSError('fixture second write failure')
    monkeypatch.setattr(personal_sites, 'save_graph', fail_history)
    from copy import deepcopy
    before = deepcopy(site.attributes)
    result = personal_sites.submit_personal_site_contact_form(site.id, 'Fixture Customer', email='fixture@example.com', message='Original request')
    assert result['history_recorded'] is False
    assert site.attributes == before
    assert ledger.get_entity(result['lead_id']).attributes['Message'] == 'Original request'
    ledger.reset()
    assert ledger.load(path) is True
    leads = [e for e in ledger.get_all().values() if e.entity_type == LEAD]
    assert len(leads) == 1
    lead = leads[0]
    assert lead.attributes['PersonalSiteID'] == site.id
    assert lead.attributes['Message'] == 'Original request'
    assert lead.attributes['Source'] == 'Website'
    assert lead.attributes['AssignedSalesperson'] == 'EMP-00001'
    assert any(r.source_id == 'EMP-00001' and r.target_id == lead.id and r.relationship_type == ASSIGNED_TO for r in ledger.relationships)


def test_contact_intake_failure_is_not_reported_as_confirmed(monkeypatch):
    from copy import deepcopy
    site = make_site()
    personal_sites.set_personal_site_status(site.id, 'active')
    before = deepcopy(site.attributes)
    def fail(_): raise OSError('fixture first write failure')
    monkeypatch.setattr(lead_intake, 'save_graph', fail)
    with pytest.raises(OSError):
        personal_sites.submit_personal_site_contact_form(site.id, 'Fixture', phone='5550100')
    assert site.attributes == before
