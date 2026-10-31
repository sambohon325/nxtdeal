"""Tests for core/accessories.py -- the graph-native Accessories Accelerator
(catalog, rule-based recommendations, accessory sales + revenue tracking stored
directly on the Customer entity, install tracking, program overview) plus its
core/accessories_api.py ACL layer and the isolated-OpenAI accessory pitch.

Follows tests/test_customer_journey.py's / tests/test_customer_journey_ai.py's
own established conventions (fresh_ledger + no_real_persistence autouse fixtures,
a _VIEW_ROLES constant, class-grouped tests, direct asserts, no per-test
docstrings) so the suite never touches real storage. This sandbox has no
outbound network access, so the happy-path pitch test monkeypatches the isolated
OpenAI client (accessories.client) with a fake returning valid JSON, exercising
the real parse-and-store path deterministically; the disabled path monkeypatches
accessories.is_feature_enabled (the feature is registered in AI_FEATURE_CATALOG
by the parent's shared wiring, so the module gates on it in production, but the
test stays self-contained by patching the gate directly).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import accessories
from core import accessories_api


# core/accessories_api.py's VIEW_ROLES -- accessories are a sales+marketing
# motion, deliberately narrower than the six-role journey/comms-hub tier.
_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)
_DENIED_ROLES = (SERVICE, FINANCE, "BOGUS")

_PITCH_KEYS = {"pitch", "highlighted_items", "suggested_bundle_note"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(accessories, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", first="Jamie", last="Buyer"):
    customer = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    )
    ledger.add_entity(customer)
    return customer


def _add_lead(lead_id="LEAD-1", name="Jordan Prospect"):
    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"Name": name})
    ledger.add_entity(lead)
    return lead


# --- Fake OpenAI client plumbing (mirrors test_customer_journey_ai.py) ---

class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _install_fake_client(monkeypatch, content):
    def _fake_create(*args, **kwargs):
        return _FakeCompletion(content)

    monkeypatch.setattr(accessories.client.chat.completions, "create", _fake_create)


_VALID_PITCH_JSON = json.dumps({
    "pitch": "Congrats on the truck! A bed liner and tonneau cover would protect it well.",
    "highlighted_items": ["Spray-In Bed Liner", "Hard Tri-Fold Tonneau Cover"],
    "suggested_bundle_note": "Bundle both at delivery for the best value.",
})


class TestCatalog:

    def test_catalog_lists_every_category(self):
        catalog = accessories.list_accessory_catalog()
        assert catalog["categories"] == [
            "truck_accessories", "protection_packages", "oem_accessories",
            "lift_kits", "wheels", "tint",
        ]

    def test_every_item_has_id_category_name_price(self):
        catalog = accessories.list_accessory_catalog()
        assert len(catalog["items"]) > 0
        for item in catalog["items"]:
            assert set(item.keys()) == {"id", "category", "name", "price"}
            assert item["category"] in accessories.CATEGORIES
            assert isinstance(item["price"], (int, float))

    def test_catalog_can_be_filtered_to_one_category(self):
        catalog = accessories.list_accessory_catalog(category="tint")
        assert len(catalog["items"]) > 0
        assert all(i["category"] == "tint" for i in catalog["items"])

    def test_catalog_carries_an_honest_disclaimer(self):
        catalog = accessories.list_accessory_catalog()
        assert catalog["basis"] == "default_price_list"
        assert catalog["disclaimer"]

    def test_an_invalid_category_raises(self):
        with pytest.raises(ValueError) as exc:
            accessories.list_accessory_catalog(category="spoilers")
        assert "Invalid accessory category 'spoilers'" in str(exc.value)


class TestRecommend:

    def test_recommends_one_item_per_category_for_a_fresh_customer(self):
        _add_customer()
        rec = accessories.recommend_accessories("CUST-1")
        cats = [r["category"] for r in rec["recommendations"]]
        assert cats == list(accessories.CATEGORIES)
        assert rec["name"] == "Jamie Buyer"

    def test_leads_with_the_highest_value_item_in_a_category(self):
        _add_customer()
        rec = accessories.recommend_accessories("CUST-1")
        truck = next(r for r in rec["recommendations"] if r["category"] == "truck_accessories")
        # Highest-ticket truck item in the default catalog is the tonneau cover.
        assert truck["item_id"] == "ACC-TRUCK-TONNEAU"

    def test_already_purchased_items_are_excluded_from_recommendations(self):
        _add_customer()
        accessories.create_accessory_sale("CUST-1", ["ACC-TRUCK-TONNEAU"])
        rec = accessories.recommend_accessories("CUST-1")
        truck = next(r for r in rec["recommendations"] if r["category"] == "truck_accessories")
        # Now the next-highest truck item (running boards) is recommended.
        assert truck["item_id"] != "ACC-TRUCK-TONNEAU"

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            accessories.recommend_accessories("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."

    def test_a_non_customer_id_raises(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            accessories.recommend_accessories("LEAD-1")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestCreateSale:

    def test_records_a_sale_with_priced_line_items_and_total(self):
        _add_customer()
        sale = accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD", "ACC-OEM-CARGO"])
        assert sale["sale_id"].startswith("ASALE-")
        assert len(sale["line_items"]) == 2
        assert sale["total_revenue"] == round(299.00 + 199.00, 2)
        assert sale["installed"] is False

    def test_sale_is_persisted_onto_the_customer_entity(self):
        _add_customer()
        accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        entity = ledger.get_entity("CUST-1")
        assert len(entity.attributes["accessory_sales"]) == 1
        assert entity.attributes["accessory_revenue_total"] == 299.00

    def test_revenue_accumulates_across_multiple_sales(self):
        _add_customer()
        accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        accessories.create_accessory_sale("CUST-1", ["ACC-OEM-CARGO"])
        entity = ledger.get_entity("CUST-1")
        assert entity.attributes["accessory_revenue_total"] == round(299.00 + 199.00, 2)
        assert len(entity.attributes["accessory_sales"]) == 2

    def test_empty_item_list_raises(self):
        _add_customer()
        with pytest.raises(ValueError) as exc:
            accessories.create_accessory_sale("CUST-1", [])
        assert "at least one item" in str(exc.value)

    def test_unknown_item_id_raises(self):
        _add_customer()
        with pytest.raises(ValueError) as exc:
            accessories.create_accessory_sale("CUST-1", ["ACC-NOPE"])
        assert "Unknown accessory item id 'ACC-NOPE'" in str(exc.value)

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            accessories.create_accessory_sale("CUST-404", ["ACC-TINT-STD"])
        assert str(exc.value) == "No customer found with id CUST-404."


class TestMarkInstalled:

    def test_marks_a_sale_installed_with_a_timestamp(self):
        _add_customer()
        sale = accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        updated = accessories.mark_installed("CUST-1", sale["sale_id"])
        assert updated["installed"] is True
        assert updated["installed_at"] is not None

    def test_install_state_persists_on_the_customer(self):
        _add_customer()
        sale = accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        accessories.mark_installed("CUST-1", sale["sale_id"])
        entity = ledger.get_entity("CUST-1")
        assert entity.attributes["accessory_sales"][0]["installed"] is True

    def test_marking_an_already_installed_sale_raises(self):
        _add_customer()
        sale = accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        accessories.mark_installed("CUST-1", sale["sale_id"])
        with pytest.raises(ValueError) as exc:
            accessories.mark_installed("CUST-1", sale["sale_id"])
        assert "already marked installed" in str(exc.value)

    def test_unknown_sale_id_raises(self):
        _add_customer()
        with pytest.raises(ValueError) as exc:
            accessories.mark_installed("CUST-1", "ASALE-99999")
        assert "No accessory sale found with id ASALE-99999" in str(exc.value)

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            accessories.mark_installed("CUST-404", "ASALE-00001")
        assert str(exc.value) == "No customer found with id CUST-404."


class TestOverview:

    def test_empty_overview_seeds_every_category_to_zero(self):
        overview = accessories.get_accessories_overview()
        assert overview["total_accessory_revenue"] == 0.0
        assert overview["total_sales"] == 0
        assert overview["installed_count"] == 0
        assert overview["pending_count"] == 0
        for category in accessories.CATEGORIES:
            assert overview["revenue_by_category"][category] == 0.0

    def test_counts_installed_vs_pending_and_revenue_by_category(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        s1 = accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])       # 299 tint
        accessories.create_accessory_sale("CUST-1", ["ACC-OEM-CARGO"])            # 199 oem, pending
        accessories.create_accessory_sale("CUST-2", ["ACC-WHEEL-ALLOY"])         # 1499 wheels, pending
        accessories.mark_installed("CUST-1", s1["sale_id"])

        overview = accessories.get_accessories_overview()
        assert overview["total_sales"] == 3
        assert overview["installed_count"] == 1
        assert overview["pending_count"] == 2
        assert overview["revenue_by_category"]["tint"] == 299.00
        assert overview["revenue_by_category"]["oem_accessories"] == 199.00
        assert overview["revenue_by_category"]["wheels"] == 1499.00
        assert overview["total_accessory_revenue"] == round(299.00 + 199.00 + 1499.00, 2)

    def test_attach_rate_is_estimated_and_labeled(self):
        _add_customer("CUST-1")
        _add_customer("CUST-2")
        accessories.create_accessory_sale("CUST-1", ["ACC-TINT-STD"])
        overview = accessories.get_accessories_overview()
        # 1 of 2 customers has an accessory sale.
        assert overview["attach_rate_estimate"] == 0.5
        assert overview["customers_with_accessory_sale"] == 1
        assert overview["total_customers"] == 2
        assert overview["attach_rate_basis"] == "estimated_against_customer_count"
        assert overview["attach_rate_disclaimer"]

    def test_non_customer_entities_are_never_counted(self):
        _add_lead()
        overview = accessories.get_accessories_overview()
        assert overview["total_customers"] == 0


class TestGenerateAccessoryPitchHappyPath:

    def test_returns_the_parsed_structured_pitch(self, monkeypatch):
        _add_customer()
        _install_fake_client(monkeypatch, _VALID_PITCH_JSON)

        result = accessories.generate_accessory_pitch("CUST-1")

        assert _PITCH_KEYS.issubset(result.keys())
        assert result["pitch"].startswith("Congrats on the truck")
        assert "Spray-In Bed Liner" in result["highlighted_items"]
        assert result["ai_generated"] is True
        assert "disabled" not in result
        assert "fallback_reason" not in result

    def test_a_successful_pitch_is_stored_onto_the_customer_entity(self, monkeypatch):
        _add_customer()
        _install_fake_client(monkeypatch, _VALID_PITCH_JSON)

        accessories.generate_accessory_pitch("CUST-1")

        entity = ledger.get_entity("CUST-1")
        stored = entity.attributes["accessory_pitch"]
        assert stored["ai_generated"] is True
        assert stored["pitch"].startswith("Congrats on the truck")

    def test_missing_model_keys_default_to_empty_never_invented(self, monkeypatch):
        _add_customer()
        _install_fake_client(monkeypatch, json.dumps({"pitch": "Short and sweet."}))

        result = accessories.generate_accessory_pitch("CUST-1")

        assert result["pitch"] == "Short and sweet."
        assert result["highlighted_items"] == []
        assert result["suggested_bundle_note"] == ""
        assert result["ai_generated"] is True


class TestGenerateAccessoryPitchDisabled:

    def test_returns_an_honest_disabled_fallback_when_the_flag_is_off(self, monkeypatch):
        _add_customer()
        monkeypatch.setattr(accessories, "is_feature_enabled", lambda key: False)

        result = accessories.generate_accessory_pitch("CUST-1")

        assert _PITCH_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert result["disabled"] is True
        # Fallback is grounded in the real recommendations, never invented.
        assert result["pitch"]

    def test_a_disabled_pitch_is_not_persisted_onto_the_customer(self, monkeypatch):
        _add_customer()
        monkeypatch.setattr(accessories, "is_feature_enabled", lambda key: False)

        accessories.generate_accessory_pitch("CUST-1")

        entity = ledger.get_entity("CUST-1")
        assert "accessory_pitch" not in entity.attributes


class TestGenerateAccessoryPitchMalformedOutput:

    def test_malformed_model_output_falls_back_with_a_reason(self, monkeypatch):
        _add_customer()
        _install_fake_client(monkeypatch, "this is not valid json {oops")

        result = accessories.generate_accessory_pitch("CUST-1")

        assert _PITCH_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert "disabled" not in result
        assert "fallback_reason" in result
        assert result["fallback_reason"]

    def test_a_failed_pitch_is_not_persisted_onto_the_customer(self, monkeypatch):
        _add_customer()
        _install_fake_client(monkeypatch, "not json")

        accessories.generate_accessory_pitch("CUST-1")

        entity = ledger.get_entity("CUST-1")
        assert "accessory_pitch" not in entity.attributes


class TestGenerateAccessoryPitchUnknownCustomer:

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            accessories.generate_accessory_pitch("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."

    def test_a_non_customer_id_raises(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            accessories.generate_accessory_pitch("LEAD-1")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestFallbackAccessoryPitch:

    def test_builds_a_pitch_grounded_in_the_recommendations(self):
        _add_customer()
        rec = accessories.recommend_accessories("CUST-1")
        result = accessories.fallback_accessory_pitch(rec)
        assert result["pitch"]
        assert len(result["highlighted_items"]) <= 3
        assert result["suggested_bundle_note"]


class TestAccessoriesApiRoleGating:

    def test_every_sales_marketing_role_can_view_the_catalog(self):
        for role in _VIEW_ROLES:
            result = accessories_api.list_accessory_catalog_api(role)
            assert "error" not in result

    def test_denied_roles_cannot_view_the_catalog(self):
        for role in _DENIED_ROLES:
            result = accessories_api.list_accessory_catalog_api(role)
            assert "error" in result

    def test_every_sales_marketing_role_can_view_the_overview(self):
        for role in _VIEW_ROLES:
            result = accessories_api.get_accessories_overview_api(role)
            assert "error" not in result

    def test_denied_roles_cannot_view_the_overview(self):
        for role in _DENIED_ROLES:
            result = accessories_api.get_accessories_overview_api(role)
            assert "error" in result

    def test_every_sales_marketing_role_can_recommend(self):
        _add_customer()
        for role in _VIEW_ROLES:
            result = accessories_api.recommend_accessories_api(role, "CUST-1")
            assert "error" not in result

    def test_denied_role_cannot_recommend(self):
        _add_customer()
        result = accessories_api.recommend_accessories_api(SERVICE, "CUST-1")
        assert "error" in result

    def test_create_sale_and_install_are_gated_and_functional(self):
        _add_customer()
        sale = accessories_api.create_accessory_sale_api(SALES, "CUST-1", ["ACC-TINT-STD"])
        assert "error" not in sale
        installed = accessories_api.mark_installed_api(SALES, "CUST-1", sale["sale_id"])
        assert installed["installed"] is True

    def test_denied_role_cannot_create_a_sale(self):
        _add_customer()
        result = accessories_api.create_accessory_sale_api(FINANCE, "CUST-1", ["ACC-TINT-STD"])
        assert "error" in result


class TestAccessoriesApiErrorsSurface:

    def test_an_unknown_customer_error_surfaces_through_the_api(self):
        result = accessories_api.recommend_accessories_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."

    def test_an_unknown_item_error_surfaces_through_the_api(self):
        _add_customer()
        result = accessories_api.create_accessory_sale_api(ADMIN, "CUST-1", ["ACC-NOPE"])
        assert "error" in result
        assert "Unknown accessory item id 'ACC-NOPE'" in result["error"]

    def test_pitch_api_is_gated_and_returns_a_pitch(self):
        _add_customer()
        result = accessories_api.generate_accessory_pitch_api(MARKETING, "CUST-1")
        assert "error" not in result
        assert _PITCH_KEYS.issubset(result.keys())

    def test_denied_role_cannot_generate_a_pitch(self):
        _add_customer()
        result = accessories_api.generate_accessory_pitch_api(SERVICE, "CUST-1")
        assert "error" in result
