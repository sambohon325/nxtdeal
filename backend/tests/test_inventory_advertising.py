"""Tests for core/inventory_advertising.py -- the graph-native Inventory
Advertising Engine (rule-based auto campaign specs across meta/google/
retargeting/price_drop/aged_inventory, a live channel/reach overview, and a
real, isolated-OpenAI-backed generate_ad_copy() with an honest fallback) plus
its core/inventory_advertising_api.py ACL layer.

Follows tests/test_customer_journey.py's / tests/test_communications_hub.py's
own established conventions (fresh_ledger + no_real_persistence autouse
fixtures, a _VIEW_ROLES constant, class-grouped tests, direct asserts, no
per-test docstrings) so the suite never touches real storage.

This sandbox has no outbound network access, so -- like the customer-journey AI
tests -- the happy-path AI test monkeypatches the isolated OpenAI client
(inventory_advertising.client) with a fake returning a valid JSON completion,
exercising the real parse path deterministically. The disabled path monkeypatches
the module's own is_feature_enabled gate to False (the real AI Management catalog
entry for this new feature is wired by the parent, not present standalone), and
the fallback path drives the real except branch with malformed model output.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER

from core import inventory_advertising
from core import inventory_advertising_api


_VIEW_ROLES = ("ADMIN", "OPERATIONS", "MARKETING")
_DENIED_ROLES = ("SALES", "SERVICE", "FINANCE", "BOGUS")

_AD_COPY_KEYS = {"headline", "body", "target_audience", "disclaimer"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(inventory_advertising, "save_graph", lambda filepath: None)


def _add_vehicle(vehicle_id="VEH-1", year=2022, make="Honda", model="Accord",
                 trim="EX", price=27500, **extra):
    attrs = {"Year": year, "Make": make, "Model": model, "Trim": trim, "Price": price}
    attrs.update(extra)
    vehicle = Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(vehicle)
    return vehicle


def _add_customer(customer_id="CUST-1"):
    customer = Entity(id=customer_id, entity_type=CUSTOMER, attributes={"Name": "Test"})
    ledger.add_entity(customer)
    return customer


class TestChannelsConstant:

    def test_five_channels(self):
        assert inventory_advertising.CHANNELS == [
            "meta", "google", "retargeting", "price_drop", "aged_inventory",
        ]


class TestGenerateCampaign:

    def test_builds_a_spec_with_the_required_fields(self):
        _add_vehicle()
        brief = inventory_advertising.generate_campaign("VEH-1", "meta")
        assert brief["vehicle_id"] == "VEH-1"
        assert brief["channel"] == "meta"
        assert brief["headline"]
        assert brief["body"]
        assert brief["target_audience"]
        assert isinstance(brief["suggested_daily_budget"], int)
        assert brief["suggested_daily_budget"] > 0
        assert "Accord" in brief["headline"] or "Accord" in brief["body"]

    def test_campaign_is_persisted_as_a_graph_entity(self):
        _add_vehicle()
        brief = inventory_advertising.generate_campaign("VEH-1", "google")
        entity = ledger.get_entity(brief["id"])
        assert entity is not None
        assert entity.entity_type == inventory_advertising.INVENTORY_AD_CAMPAIGN
        assert entity.attributes["vehicle_id"] == "VEH-1"

    def test_invalid_channel_raises(self):
        _add_vehicle()
        with pytest.raises(ValueError) as exc:
            inventory_advertising.generate_campaign("VEH-1", "tiktok")
        assert "Invalid channel" in str(exc.value)

    def test_unknown_vehicle_raises(self):
        with pytest.raises(ValueError) as exc:
            inventory_advertising.generate_campaign("VEH-404", "meta")
        assert str(exc.value) == "No vehicle found with id VEH-404."

    def test_an_id_that_is_not_a_vehicle_raises(self):
        _add_customer()
        with pytest.raises(ValueError) as exc:
            inventory_advertising.generate_campaign("CUST-1", "meta")
        assert str(exc.value) == "No vehicle found with id CUST-1."

    def test_pricier_units_get_a_higher_suggested_budget(self):
        _add_vehicle("VEH-cheap", price=10000)
        _add_vehicle("VEH-pricey", price=90000)
        cheap = inventory_advertising.generate_campaign("VEH-cheap", "meta")
        pricey = inventory_advertising.generate_campaign("VEH-pricey", "meta")
        assert pricey["suggested_daily_budget"] > cheap["suggested_daily_budget"]


class TestListCampaigns:

    def test_lists_built_campaigns_filterable_by_channel(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        inventory_advertising.generate_campaign("VEH-1", "meta")
        inventory_advertising.generate_campaign("VEH-2", "google")
        assert len(inventory_advertising.list_campaigns()) == 2
        meta_only = inventory_advertising.list_campaigns(channel="meta")
        assert len(meta_only) == 1
        assert meta_only[0]["channel"] == "meta"


class TestPriceDropCampaigns:

    def test_builds_for_units_with_a_recorded_price_drop(self):
        _add_vehicle("VEH-drop", price=24000, PreviousPrice=27000)
        _add_vehicle("VEH-flat", price=27500)
        built = inventory_advertising.price_drop_campaigns()
        assert len(built) == 1
        campaign = built[0]
        assert campaign["vehicle_id"] == "VEH-drop"
        assert campaign["channel"] == "price_drop"
        assert campaign["price_drop_from"] == 27000
        assert campaign["price_drop_to"] == 24000
        assert "3,000" in campaign["body"]  # the $3,000 savings surfaced honestly

    def test_price_history_signal_is_detected(self):
        _add_vehicle(
            "VEH-hist",
            price=19000,
            price_history=[{"price": 22000}, {"price": 20500}, {"price": 19000}],
        )
        built = inventory_advertising.price_drop_campaigns()
        assert len(built) == 1
        assert built[0]["price_drop_from"] == 22000

    def test_does_not_double_build_for_the_same_vehicle(self):
        _add_vehicle("VEH-drop", price=24000, PreviousPrice=27000)
        inventory_advertising.price_drop_campaigns()
        second = inventory_advertising.price_drop_campaigns()
        assert second == []

    def test_sold_units_are_excluded(self):
        _add_vehicle("VEH-sold", price=24000, PreviousPrice=27000, DateSold="2026-01-01")
        assert inventory_advertising.price_drop_campaigns() == []


class TestAgedInventoryCampaigns:

    def test_builds_for_units_past_the_threshold_with_real_age(self):
        _add_vehicle("VEH-old", days_in_stock=95)
        _add_vehicle("VEH-fresh", days_in_stock=10)
        built = inventory_advertising.aged_inventory_campaigns(days_threshold=60)
        assert len(built) == 1
        campaign = built[0]
        assert campaign["vehicle_id"] == "VEH-old"
        assert campaign["channel"] == "aged_inventory"
        assert campaign["age_days"] == 95
        assert campaign["age_is_estimated"] is False

    def test_threshold_is_respected(self):
        _add_vehicle("VEH-old", days_in_stock=45)
        assert inventory_advertising.aged_inventory_campaigns(days_threshold=60) == []
        built = inventory_advertising.aged_inventory_campaigns(days_threshold=30)
        assert len(built) == 1

    def test_age_falls_back_to_an_estimate_when_no_real_date_exists(self):
        # No days_in_stock / DateInStock -> estimated age, honestly flagged.
        _add_vehicle("VEH-noage", price=15000)
        built = inventory_advertising.aged_inventory_campaigns(days_threshold=0)
        assert len(built) == 1
        assert built[0]["age_is_estimated"] is True
        assert built[0]["age_days"] is not None


class TestAdvertisingOverview:

    def test_counts_campaigns_by_channel_with_all_channels_seeded(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        inventory_advertising.generate_campaign("VEH-1", "meta")
        inventory_advertising.generate_campaign("VEH-2", "meta")
        inventory_advertising.generate_campaign("VEH-1", "google")

        overview = inventory_advertising.get_advertising_overview()
        assert overview["total_campaigns"] == 3
        assert overview["campaigns_by_channel"]["meta"] == 2
        assert overview["campaigns_by_channel"]["google"] == 1
        # Every channel present, even empties.
        assert set(overview["campaigns_by_channel"].keys()) == set(inventory_advertising.CHANNELS)
        assert overview["campaigns_by_channel"]["retargeting"] == 0
        assert overview["estimated_total_daily_reach"] > 0
        assert overview["basis"] == inventory_advertising.SIMULATED_BASIS

    def test_empty_overview_is_all_zero(self):
        overview = inventory_advertising.get_advertising_overview()
        assert overview["total_campaigns"] == 0
        assert overview["estimated_total_daily_reach"] == 0
        assert all(v == 0 for v in overview["campaigns_by_channel"].values())


# ---------------------------------------------------------------------------
# AI ad copy
# ---------------------------------------------------------------------------

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

    monkeypatch.setattr(
        inventory_advertising.client.chat.completions, "create", _fake_create
    )


_VALID_MODEL_JSON = json.dumps({
    "headline": "Drive Home the 2022 Honda Accord",
    "body": "This one-owner Accord EX is priced to sell. Financing available. Message us to book a test drive.",
    "target_audience": "Local sedan shoppers 25-54 within 25 miles, auto intenders.",
    "disclaimer": "Price excludes tax, title, and dealer fees.",
})


class TestGenerateAdCopyHappyPath:

    def test_returns_the_parsed_ad_copy(self, monkeypatch):
        _add_vehicle()
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        result = inventory_advertising.generate_ad_copy("VEH-1", "meta")

        assert _AD_COPY_KEYS.issubset(result.keys())
        assert result["headline"] == "Drive Home the 2022 Honda Accord"
        assert result["ai_generated"] is True
        assert "disabled" not in result
        assert "fallback_reason" not in result

    def test_missing_model_keys_default_to_empty_never_invented(self, monkeypatch):
        _add_vehicle()
        _install_fake_client(monkeypatch, json.dumps({"headline": "Just a headline"}))

        result = inventory_advertising.generate_ad_copy("VEH-1", "google")

        assert result["headline"] == "Just a headline"
        assert result["body"] == ""
        assert result["target_audience"] == ""
        assert result["ai_generated"] is True


class TestGenerateAdCopyDisabled:

    def test_returns_an_honest_disabled_fallback_when_the_feature_is_off(self, monkeypatch):
        _add_vehicle()
        monkeypatch.setattr(inventory_advertising, "is_feature_enabled", lambda key: False)

        result = inventory_advertising.generate_ad_copy("VEH-1", "meta")

        assert _AD_COPY_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert result["disabled"] is True
        # Fallback copy is grounded in the real vehicle, never invented.
        assert "Accord" in result["headline"] or "Accord" in result["body"]


class TestGenerateAdCopyMalformedOutput:

    def test_malformed_model_output_falls_back_with_a_reason(self, monkeypatch):
        _add_vehicle()
        _install_fake_client(monkeypatch, "this is not valid json {oops")

        result = inventory_advertising.generate_ad_copy("VEH-1", "retargeting")

        assert _AD_COPY_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert "disabled" not in result
        assert result["fallback_reason"]


class TestGenerateAdCopyValidation:

    def test_invalid_channel_raises(self):
        _add_vehicle()
        with pytest.raises(ValueError):
            inventory_advertising.generate_ad_copy("VEH-1", "tiktok")

    def test_unknown_vehicle_raises(self):
        with pytest.raises(ValueError) as exc:
            inventory_advertising.generate_ad_copy("VEH-404", "meta")
        assert str(exc.value) == "No vehicle found with id VEH-404."


# ---------------------------------------------------------------------------
# API / ACL layer
# ---------------------------------------------------------------------------

class TestApiRoleGating:

    def test_every_view_role_can_read_the_overview(self):
        for role in _VIEW_ROLES:
            result = inventory_advertising_api.get_advertising_overview_api(role)
            assert "error" not in result

    def test_denied_roles_cannot_read_the_overview(self):
        for role in _DENIED_ROLES:
            result = inventory_advertising_api.get_advertising_overview_api(role)
            assert "error" in result

    def test_generate_campaign_api_surfaces_value_errors_as_error_dicts(self):
        result = inventory_advertising_api.generate_campaign_api("ADMIN", "VEH-404", "meta")
        assert result["error"] == "No vehicle found with id VEH-404."

    def test_generate_campaign_api_invalid_channel_surfaces_error(self):
        _add_vehicle()
        result = inventory_advertising_api.generate_campaign_api("MARKETING", "VEH-1", "tiktok")
        assert "Invalid channel" in result["error"]

    def test_generate_campaign_api_happy_path(self):
        _add_vehicle()
        result = inventory_advertising_api.generate_campaign_api("MARKETING", "VEH-1", "meta")
        assert "error" not in result
        assert result["channel"] == "meta"

    def test_denied_role_cannot_generate_a_campaign(self):
        _add_vehicle()
        result = inventory_advertising_api.generate_campaign_api("SALES", "VEH-1", "meta")
        assert "error" in result

    def test_price_drop_and_aged_apis_return_lists_for_view_roles(self):
        _add_vehicle("VEH-drop", price=24000, PreviousPrice=27000, days_in_stock=5)
        _add_vehicle("VEH-old", days_in_stock=120)
        drops = inventory_advertising_api.price_drop_campaigns_api("MARKETING")
        aged = inventory_advertising_api.aged_inventory_campaigns_api("MARKETING", days_threshold=60)
        assert isinstance(drops, list) and len(drops) == 1
        assert isinstance(aged, list) and len(aged) == 1

    def test_ad_copy_api_gated_and_functional(self, monkeypatch):
        _add_vehicle()
        monkeypatch.setattr(inventory_advertising, "is_feature_enabled", lambda key: False)
        denied = inventory_advertising_api.generate_ad_copy_api("SALES", "VEH-1", "meta")
        assert "error" in denied
        allowed = inventory_advertising_api.generate_ad_copy_api("MARKETING", "VEH-1", "meta")
        assert "error" not in allowed
        assert allowed["ai_generated"] is False
