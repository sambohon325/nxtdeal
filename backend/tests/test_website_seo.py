"""
Test coverage for core/website_seo.py -- Enterprise SEO Automation for the Website
Builder (sitemap.xml generation, an SEO health score, and schema.org JSON-LD
structured data).

All 3 pieces are 100% real computations over already-real, already-stored Website
fields -- no simulated data, no external API calls. Covers get_sitemap_xml()
(missing/unpublished-site error paths, the real 6-PAGE_KEYS + real-unsold-vehicle
URL set, sold vehicles correctly excluded, custom_domain overriding the default
DNS_TARGET_HOSTNAME), get_seo_health()/_page_health() (the 4 real per-page checks
with their exact inclusive char-count boundaries -- meta_title 10-60,
meta_description 50-160 -- the site-wide meta fallback when a page-level value
isn't set, and the 4 real site-wide checks), and get_structured_data() (the base
AutoDealer JSON-LD shape, contact_form's phone/address each independently included
only when truthy -- found by scanning every page's sections, not just the "contact"
page -- and OEM branding_mode + oem_logo_url gating the logo field).

Every value below was live-verified against this exact module before being written
as an assertion.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.website_seo as wseo
from core.websites import (
    create_website,
    get_website,
    add_section,
    update_page_seo,
    update_admin_settings,
    approve_website,
    PAGE_KEYS,
    DNS_TARGET_HOSTNAME,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, **attrs):
    ledger.add_entity(Entity(id=vid, entity_type="Vehicle", attributes=attrs))


class TestGetSitemapXmlErrorPaths:

    def test_missing_website_returns_error(self):
        result = wseo.get_sitemap_xml("SITE-99999")
        assert result == {"error": "Website not found"}

    def test_unpublished_draft_site_returns_error(self):
        site = create_website("Test Dealer", "EMP-1")
        result = wseo.get_sitemap_xml(site.id)
        assert "error" in result
        assert "isn't published yet" in result["error"]


class TestGetSitemapXmlPublished:

    def test_published_site_with_no_vehicles_has_one_url_per_page_key(self):
        site = create_website("Pub Site", "EMP-1")
        approve_website(site.id, "EMP-ADMIN")
        result = wseo.get_sitemap_xml(site.id)
        assert result["url_count"] == len(PAGE_KEYS) == 6
        assert "<urlset" in result["sitemap_xml"]
        assert f"/site/{site.id}<" in result["sitemap_xml"]

    def test_default_domain_is_dns_target_hostname(self):
        site = create_website("Pub Site", "EMP-1")
        approve_website(site.id, "EMP-ADMIN")
        result = wseo.get_sitemap_xml(site.id)
        assert result["domain"] == DNS_TARGET_HOSTNAME

    def test_custom_domain_overrides_the_default_domain(self):
        site = create_website("Pub Site", "EMP-1")
        approve_website(site.id, "EMP-ADMIN")
        update_admin_settings(site.id, {"custom_domain": "mydealer.com"})
        result = wseo.get_sitemap_xml(site.id)
        assert result["domain"] == "mydealer.com"
        assert "mydealer.com" in result["sitemap_xml"]

    def test_only_unsold_vehicles_are_included_and_sold_vehicles_are_excluded(self):
        site = create_website("Pub Site", "EMP-1")
        approve_website(site.id, "EMP-ADMIN")
        _vehicle("VEH-1", Year="2022", Make="Ford", Model="F-150", Price="30000")
        _vehicle("VEH-2", Year="2023", Make="Chevy", Model="Silverado", Price="35000")
        _vehicle("VEH-3", Year="2020", Make="Toyota", Model="Camry", Price="20000", DateSold="2026-01-01")

        result = wseo.get_sitemap_xml(site.id)
        assert result["url_count"] == 8  # 6 pages + 2 unsold vehicles
        assert "VEH-1" in result["sitemap_xml"]
        assert "VEH-2" in result["sitemap_xml"]
        assert "VEH-3" not in result["sitemap_xml"]


class TestGetSeoHealthErrorPath:

    def test_missing_website_returns_error(self):
        result = wseo.get_seo_health("SITE-99999")
        assert result == {"error": "Website not found"}


class TestSeoHealthMetaTitleBoundary:

    def test_title_9_chars_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_title": "x" * 9})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        assert check["pass"] is False

    def test_title_10_chars_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_title": "x" * 10})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        assert check["pass"] is True

    def test_title_60_chars_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_title": "x" * 60})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        assert check["pass"] is True

    def test_title_61_chars_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_title": "x" * 61})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        assert check["pass"] is False

    def test_no_title_set_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        assert check["pass"] is False
        assert "No page-level or site-wide meta title set" in check["detail"]


class TestSeoHealthMetaDescriptionBoundary:

    def test_description_49_chars_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_description": "x" * 49})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_description")
        assert check["pass"] is False

    def test_description_50_chars_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_description": "x" * 50})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_description")
        assert check["pass"] is True

    def test_description_160_chars_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_description": "x" * 160})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_description")
        assert check["pass"] is True

    def test_description_161_chars_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"meta_description": "x" * 161})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_description")
        assert check["pass"] is False


class TestSeoHealthOgImageAndContent:

    def test_og_image_set_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {"og_image_url": "https://example.com/img.png"})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "og_image")
        assert check["pass"] is True

    def test_og_image_unset_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "og_image")
        assert check["pass"] is False

    def test_page_with_sections_passes_content_check(self):
        site = create_website("Test Dealer", "EMP-1")
        add_section(site.id, "home", "hero_banner", {"headline": "Welcome"}, by="EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "content")
        assert check["pass"] is True

    def test_page_with_no_sections_fails_content_check(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["pages"][0]["checks"] if c["check"] == "content")
        assert check["pass"] is False
        assert "no sections yet" in check["detail"]


class TestSeoHealthScoringAndFallback:

    def test_a_fresh_site_scores_zero_everywhere(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        assert health["overall_score_pct"] == 0.0
        for page in health["pages"]:
            assert page["score_pct"] == 0.0

    def test_all_four_checks_passing_scores_100_for_that_page(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {
            "meta_title": "x" * 30,
            "meta_description": "x" * 100,
            "og_image_url": "https://example.com/img.png",
        })
        add_section(site.id, "home", "hero_banner", {"headline": "Welcome"}, by="EMP-1")
        health = wseo.get_seo_health(site.id)
        assert health["pages"][0]["score_pct"] == 100.0

    def test_overall_score_averages_across_all_page_keys(self):
        site = create_website("Test Dealer", "EMP-1")
        update_page_seo(site.id, "home", {
            "meta_title": "x" * 30,
            "meta_description": "x" * 100,
            "og_image_url": "https://example.com/img.png",
        })
        add_section(site.id, "home", "hero_banner", {"headline": "Welcome"}, by="EMP-1")
        health = wseo.get_seo_health(site.id)
        # home = 100%, the other 5 page keys = 0% each -> 100/6 = 16.7
        assert health["overall_score_pct"] == 16.7

    def test_site_wide_meta_fields_are_used_when_page_level_is_unset(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"meta_title": "Site Wide Title", "meta_description": "x" * 60})
        health = wseo.get_seo_health(site.id)
        title_check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_title")
        desc_check = next(c for c in health["pages"][0]["checks"] if c["check"] == "meta_description")
        assert title_check["pass"] is True
        assert desc_check["pass"] is True


class TestSeoHealthSiteChecks:

    def test_sitemap_enabled_defaults_true(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "sitemap_enabled")
        assert check["pass"] is True

    def test_sitemap_enabled_false_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"sitemap_enabled": False})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "sitemap_enabled")
        assert check["pass"] is False

    def test_search_engines_allowed_defaults_true(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "search_engines_allowed")
        assert check["pass"] is True

    def test_search_engines_allowed_false_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"allow_search_engines": False})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "search_engines_allowed")
        assert check["pass"] is False

    def test_custom_domain_unset_fails(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "custom_domain")
        assert check["pass"] is False

    def test_custom_domain_set_passes(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"custom_domain": "mydealer.com"})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "custom_domain")
        assert check["pass"] is True

    def test_analytics_passes_via_google_analytics_id_alone(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"google_analytics_id": "G-XXXX"})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "analytics")
        assert check["pass"] is True

    def test_analytics_passes_via_umami_site_id_alone(self):
        site = create_website("Test Dealer", "EMP-1")
        update_admin_settings(site.id, {"umami_site_id": "abc123"})
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "analytics")
        assert check["pass"] is True

    def test_analytics_fails_with_neither_id_set(self):
        site = create_website("Test Dealer", "EMP-1")
        health = wseo.get_seo_health(site.id)
        check = next(c for c in health["site_checks"] if c["check"] == "analytics")
        assert check["pass"] is False


class TestGetStructuredDataErrorPath:

    def test_missing_website_returns_error(self):
        result = wseo.get_structured_data("SITE-99999")
        assert result == {"error": "Website not found"}


class TestStructuredDataBase:

    def test_base_shape_with_no_contact_form_at_all(self):
        site = create_website("Struct Site", "EMP-1")
        result = wseo.get_structured_data(site.id)
        json_ld = result["json_ld"]
        assert json_ld["@context"] == "https://schema.org"
        assert json_ld["@type"] == "AutoDealer"
        assert json_ld["name"] == "Struct Site"
        assert json_ld["url"] == f"https://{DNS_TARGET_HOSTNAME}/site/{site.id}"
        assert "telephone" not in json_ld
        assert "address" not in json_ld
        assert "logo" not in json_ld


class TestStructuredDataContactForm:

    def test_phone_only_included_when_present(self):
        site = create_website("Struct Site", "EMP-1")
        add_section(site.id, "contact", "contact_form", {"heading": "Visit", "phone": "555-1234"}, by="EMP-1")
        result = wseo.get_structured_data(site.id)
        assert result["json_ld"]["telephone"] == "555-1234"
        assert "address" not in result["json_ld"]

    def test_address_only_included_when_present(self):
        site = create_website("Struct Site", "EMP-1")
        add_section(site.id, "contact", "contact_form", {"heading": "Visit", "address": "123 Main St"}, by="EMP-1")
        result = wseo.get_structured_data(site.id)
        assert result["json_ld"]["address"] == {"@type": "PostalAddress", "streetAddress": "123 Main St"}
        assert "telephone" not in result["json_ld"]

    def test_both_phone_and_address_included_together(self):
        site = create_website("Struct Site", "EMP-1")
        add_section(site.id, "contact", "contact_form", {"heading": "Visit", "phone": "555-9999", "address": "456 Oak Ave"}, by="EMP-1")
        result = wseo.get_structured_data(site.id)
        assert result["json_ld"]["telephone"] == "555-9999"
        assert result["json_ld"]["address"]["streetAddress"] == "456 Oak Ave"

    def test_empty_string_phone_and_address_are_not_included(self):
        site = create_website("Struct Site", "EMP-1")
        add_section(site.id, "contact", "contact_form", {"heading": "Visit", "phone": "", "address": ""}, by="EMP-1")
        result = wseo.get_structured_data(site.id)
        assert "telephone" not in result["json_ld"]
        assert "address" not in result["json_ld"]

    def test_contact_form_is_found_on_any_page_not_just_contact(self):
        site = create_website("Odd Placement", "EMP-1")
        add_section(site.id, "about", "contact_form", {"phone": "555-0000"}, by="EMP-1")
        result = wseo.get_structured_data(site.id)
        assert result["json_ld"]["telephone"] == "555-0000"


class TestStructuredDataOemBranding:

    def test_oem_mode_without_logo_url_omits_logo(self):
        site = create_website("OEM Site", "EMP-1")
        update_admin_settings(site.id, {"branding_mode": "oem"})
        result = wseo.get_structured_data(site.id)
        assert "logo" not in result["json_ld"]

    def test_oem_mode_with_logo_url_includes_logo(self):
        site = create_website("OEM Site", "EMP-1")
        update_admin_settings(site.id, {"branding_mode": "oem", "oem_logo_url": "https://example.com/logo.png"})
        result = wseo.get_structured_data(site.id)
        assert result["json_ld"]["logo"] == "https://example.com/logo.png"

    def test_independent_mode_never_includes_logo_even_if_oem_logo_url_is_set(self):
        site = create_website("Indep Site", "EMP-1")
        update_admin_settings(site.id, {"oem_logo_url": "https://example.com/logo2.png"})
        result = wseo.get_structured_data(site.id)
        assert "logo" not in result["json_ld"]


class TestPageHealthDirect:

    def test_page_health_returns_page_key_score_and_checks(self):
        site = create_website("Direct Test", "EMP-1")
        website = get_website(site.id)
        result = wseo._page_health(website, "about")
        assert result["page_key"] == "about"
        assert result["score_pct"] == 0.0
        assert len(result["checks"]) == 4
