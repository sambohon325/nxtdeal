import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import pricing_desk
from core import pricing_desk_api
from core import inventory_aging
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # apply_price_recommendation() delegates directly to
    # core.inventory_aging.set_price(), which does its own top-level
    # `from core.storage import save_graph` -- pricing_desk.py itself never
    # imports save_graph at all, so the module to patch is inventory_aging,
    # not pricing_desk.
    monkeypatch.setattr(inventory_aging, "save_graph", lambda filepath: None)


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
        "Trim": "EX-L",
        "Price": 25000,
        "Cost": 21000,
        "Mileage": 30000,
    }
    if sold:
        attrs["DateSold"] = "2026-01-01"
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _expected_market_position(price, market_avg_price):
    if not price or not market_avg_price:
        return None
    if price < market_avg_price * 0.97:
        return "below_market"
    if price > market_avg_price * 1.03:
        return "above_market"
    return "at_market"


def _expected_age_band(days):
    if days <= 30:
        return "0-30 days", 0.0
    if days <= 60:
        return "31-60 days", -0.02
    if days <= 90:
        return "61-90 days", -0.05
    return "91+ days", -0.08


# ---------------------------------------------------------------------------
# Market Pricing
# ---------------------------------------------------------------------------


class TestGetMarketPricing:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.get_market_pricing("VEH-NOPE")
        assert "error" in result

    def test_shape_and_bounds(self):
        _add_vehicle()
        result = pricing_desk.get_market_pricing("VEH-1")
        assert result["vehicle_id"] == "VEH-1"
        assert result["current_price"] == 25000
        assert result["market_avg_price"] is not None
        # variance is +/- 8% of the real price
        assert 25000 * 0.92 <= result["market_avg_price"] <= 25000 * 1.08
        assert 15 <= result["market_days_supply"] <= 120
        assert result["basis"] == "simulated_market_data"
        assert "SIMULATED" in result["disclaimer"]

    def test_position_matches_the_documented_threshold_rule(self):
        _add_vehicle()
        result = pricing_desk.get_market_pricing("VEH-1")
        expected = _expected_market_position(result["current_price"], result["market_avg_price"])
        assert result["price_position"] == expected

    def test_no_real_price_yields_none_fields(self):
        _add_vehicle(Price=None)
        result = pricing_desk.get_market_pricing("VEH-1")
        assert result["current_price"] is None
        assert result["market_avg_price"] is None
        assert result["price_position"] is None

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = pricing_desk.get_market_pricing("VEH-1")
        r2 = pricing_desk.get_market_pricing("VEH-1")
        assert r1 == r2

    def test_different_make_model_can_shift_seed(self):
        _add_vehicle("VEH-1", Make="Honda", Model="Accord")
        _add_vehicle("VEH-2", Make="Ford", Model="F-150")
        r1 = pricing_desk.get_market_pricing("VEH-1")
        r2 = pricing_desk.get_market_pricing("VEH-2")
        # Not guaranteed to differ, but both must independently stay in bounds.
        assert 15 <= r1["market_days_supply"] <= 120
        assert 15 <= r2["market_days_supply"] <= 120


# ---------------------------------------------------------------------------
# Competitor Comparisons
# ---------------------------------------------------------------------------


class TestGetCompetitorComparisons:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.get_competitor_comparisons("VEH-NOPE")
        assert "error" in result

    def test_default_count_is_four(self):
        _add_vehicle()
        result = pricing_desk.get_competitor_comparisons("VEH-1")
        assert len(result["comparisons"]) == 4

    def test_custom_count_respected(self):
        _add_vehicle()
        result = pricing_desk.get_competitor_comparisons("VEH-1", count=2)
        assert len(result["comparisons"]) == 2

    def test_comparisons_sorted_ascending_by_price(self):
        _add_vehicle()
        result = pricing_desk.get_competitor_comparisons("VEH-1")
        prices = [c["price"] for c in result["comparisons"]]
        assert prices == sorted(prices)

    def test_comparison_shape(self):
        _add_vehicle()
        result = pricing_desk.get_competitor_comparisons("VEH-1")
        for c in result["comparisons"]:
            assert "dealer_name" in c
            assert "price" in c
            assert "mileage" in c
            assert c["mileage"] >= 0
            assert 3 <= c["distance_miles"] <= 85

    def test_basis_and_disclaimer_present(self):
        _add_vehicle()
        result = pricing_desk.get_competitor_comparisons("VEH-1")
        assert result["basis"] == "simulated_market_data"
        assert "SIMULATED" in result["disclaimer"]

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = pricing_desk.get_competitor_comparisons("VEH-1")
        r2 = pricing_desk.get_competitor_comparisons("VEH-1")
        assert r1 == r2


# ---------------------------------------------------------------------------
# Age-Based Adjustment
# ---------------------------------------------------------------------------


class TestGetAgeBasedAdjustment:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.get_age_based_adjustment("VEH-NOPE")
        assert "error" in result

    def test_estimated_days_within_bounds(self):
        _add_vehicle()
        result = pricing_desk.get_age_based_adjustment("VEH-1")
        assert 1 <= result["estimated_listing_age_days"] <= 130

    def test_band_and_adjustment_match_the_documented_rule(self):
        _add_vehicle()
        result = pricing_desk.get_age_based_adjustment("VEH-1")
        expected_band, expected_adj = _expected_age_band(result["estimated_listing_age_days"])
        assert result["age_band"] == expected_band
        assert result["suggested_adjustment_pct"] == expected_adj

    def test_suggested_price_reflects_adjustment(self):
        _add_vehicle()
        result = pricing_desk.get_age_based_adjustment("VEH-1")
        expected = round(25000 * (1 + result["suggested_adjustment_pct"]), 2)
        assert result["suggested_price"] == expected

    def test_no_real_price_yields_none_fields(self):
        _add_vehicle(Price=None)
        result = pricing_desk.get_age_based_adjustment("VEH-1")
        assert result["current_price"] is None
        assert result["suggested_price"] is None

    def test_basis_and_disclaimer_present(self):
        _add_vehicle()
        result = pricing_desk.get_age_based_adjustment("VEH-1")
        assert result["basis"] == "simulated_market_data"
        assert "SIMULATED" in result["disclaimer"]

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = pricing_desk.get_age_based_adjustment("VEH-1")
        r2 = pricing_desk.get_age_based_adjustment("VEH-1")
        assert r1 == r2


# ---------------------------------------------------------------------------
# Pricing Recommendation
# ---------------------------------------------------------------------------


class TestGetPricingRecommendation:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.get_pricing_recommendation("VEH-NOPE")
        assert "error" in result

    def test_recommends_a_price_for_a_normal_vehicle(self):
        _add_vehicle()
        result = pricing_desk.get_pricing_recommendation("VEH-1")
        assert result["current_price"] == 25000
        assert result["recommended_price"] is not None
        assert result["basis"] == "simulated_market_data"
        assert "3%" in result["disclaimer"]

    def test_margin_floor_computed_from_real_cost(self):
        _add_vehicle(Cost=20000)
        result = pricing_desk.get_pricing_recommendation("VEH-1")
        assert result["margin_floor"] == round(20000 * 1.03, 2)

    def test_no_cost_means_no_margin_floor_and_never_applied(self):
        _add_vehicle(Cost=None)
        result = pricing_desk.get_pricing_recommendation("VEH-1")
        assert result["margin_floor"] is None
        assert result["margin_floor_applied"] is False

    def test_margin_floor_applies_when_cost_is_very_high(self):
        # candidates are capped near [price*0.92, price*1.08] blended down
        # further by averaging with the age adjustment (which is always <=
        # price, never above it) -- so a cost set to 2x price forces
        # margin_floor (price*2*1.03) well above every possible candidate,
        # guaranteeing the floor applies regardless of the seeded values.
        _add_vehicle(Price=25000, Cost=50000)
        result = pricing_desk.get_pricing_recommendation("VEH-1")
        assert result["margin_floor_applied"] is True
        assert result["recommended_price"] == result["margin_floor"]

    def test_no_real_price_yields_no_candidates(self):
        _add_vehicle(Price=None)
        result = pricing_desk.get_pricing_recommendation("VEH-1")
        assert result["current_price"] is None
        assert result["recommended_price"] is None

    def test_deterministic_across_repeat_calls(self):
        _add_vehicle()
        r1 = pricing_desk.get_pricing_recommendation("VEH-1")
        r2 = pricing_desk.get_pricing_recommendation("VEH-1")
        assert r1 == r2


# ---------------------------------------------------------------------------
# Composed view + queue
# ---------------------------------------------------------------------------


class TestGetPricingView:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.get_pricing_view("VEH-NOPE")
        assert "error" in result

    def test_composes_all_four_sections(self):
        _add_vehicle()
        result = pricing_desk.get_pricing_view("VEH-1")
        assert result["vehicle"]["vehicle_id"] == "VEH-1"
        assert "market_pricing" in result
        assert "competitor_comparisons" in result
        assert "age_based_adjustment" in result
        assert "recommendation" in result
        assert result["market_pricing"]["vehicle_id"] == "VEH-1"


class TestGetPricingQueue:
    def test_empty_state(self):
        result = pricing_desk.get_pricing_queue()
        assert result == {"count": 0, "vehicles": []}

    def test_zero_price_sorts_first(self):
        _add_vehicle("VEH-1", Price=0)
        _add_vehicle("VEH-2", Price=25000, Cost=21000)
        result = pricing_desk.get_pricing_queue()
        ids = [v["vehicle_id"] for v in result["vehicles"]]
        assert ids[0] == "VEH-1"

    def test_worse_margin_sorts_before_better_margin(self):
        _add_vehicle("VEH-LOW", Price=100, Cost=90)   # margin 0.10 -- worse
        _add_vehicle("VEH-HIGH", Price=100, Cost=40)  # margin 0.60 -- better
        result = pricing_desk.get_pricing_queue()
        ids = [v["vehicle_id"] for v in result["vehicles"]]
        assert ids.index("VEH-LOW") < ids.index("VEH-HIGH")

    def test_missing_cost_but_real_price_sorts_between_zero_and_healthy_margin(self):
        _add_vehicle("VEH-NOCOST", Price=100, Cost=None)   # fallback key 0.5
        _add_vehicle("VEH-ZERO", Price=0)                   # key -1.0
        _add_vehicle("VEH-GOOD", Price=100, Cost=10)         # margin 0.9 -- better than 0.5
        result = pricing_desk.get_pricing_queue()
        ids = [v["vehicle_id"] for v in result["vehicles"]]
        assert ids.index("VEH-ZERO") < ids.index("VEH-NOCOST") < ids.index("VEH-GOOD")

    def test_each_entry_has_a_recommendation_attached(self):
        _add_vehicle()
        result = pricing_desk.get_pricing_queue()
        assert "recommendation" in result["vehicles"][0]

    def test_sold_vehicle_excluded(self):
        _add_vehicle("VEH-1", sold=True)
        result = pricing_desk.get_pricing_queue()
        assert result["count"] == 0

    def test_count_reflects_capped_length_not_true_total(self):
        # Same shape as merchandising's get_merchandising_queue -- ranked is
        # sliced to `limit` BEFORE results/count are built, so count reflects
        # the post-slice length, not the true total of unsold inventory.
        for i in range(5):
            _add_vehicle(f"VEH-{i}", Price=100 + i, Cost=50)
        result = pricing_desk.get_pricing_queue(limit=2)
        assert result["count"] == 2
        assert len(result["vehicles"]) == 2


class TestApplyPriceRecommendation:
    def test_unknown_vehicle_rejected(self):
        result = pricing_desk.apply_price_recommendation("VEH-NOPE", "EMP-1", 22000)
        assert "error" in result

    def test_non_numeric_price_rejected(self):
        _add_vehicle()
        result = pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", "not-a-number")
        assert "error" in result

    def test_zero_or_negative_price_rejected(self):
        _add_vehicle()
        result = pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 0)
        assert "error" in result

    def test_can_reduce_price(self):
        _add_vehicle(Price=25000)
        result = pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 22000)
        assert result["vehicle"]["price"] == 22000

    def test_can_increase_price_bidirectionally(self):
        # Unlike inventory_aging.reduce_price(), set_price() (and therefore
        # apply_price_recommendation()) is explicitly bidirectional -- a
        # Pricing Desk recommendation can raise an underpriced unit too.
        _add_vehicle(Price=25000)
        result = pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 28000)
        assert result["vehicle"]["price"] == 28000

    def test_default_reason_used_when_not_supplied(self):
        _add_vehicle(Price=25000)
        pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 22000)
        v = ledger.get_entity("VEH-1")
        assert v.attributes["price_history"][-1]["reason"] == "Applied Pricing Desk recommendation"

    def test_explicit_reason_respected(self):
        _add_vehicle(Price=25000)
        pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 22000, reason="Manager override")
        v = ledger.get_entity("VEH-1")
        assert v.attributes["price_history"][-1]["reason"] == "Manager override"

    def test_price_history_records_old_and_new(self):
        _add_vehicle(Price=25000)
        pricing_desk.apply_price_recommendation("VEH-1", "EMP-1", 22000)
        v = ledger.get_entity("VEH-1")
        entry = v.attributes["price_history"][-1]
        assert entry["old_price"] == 25000
        assert entry["new_price"] == 22000
        assert entry["updated_by"] == "EMP-1"


# ---------------------------------------------------------------------------
# API layer -- role gating
# ---------------------------------------------------------------------------


_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]

_MUTATE_ALLOWED = [ADMIN, OPERATIONS]
_MUTATE_DENIED = [SALES, SERVICE, MARKETING, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_market_pricing_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.get_market_pricing_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_market_pricing_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.get_market_pricing_api(role, "VEH-1")
        assert "market_avg_price" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_competitor_comparisons_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.get_competitor_comparisons_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_competitor_comparisons_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.get_competitor_comparisons_api(role, "VEH-1")
        assert "comparisons" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_age_based_adjustment_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.get_age_based_adjustment_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_age_based_adjustment_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.get_age_based_adjustment_api(role, "VEH-1")
        assert "age_band" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_pricing_recommendation_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.get_pricing_recommendation_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_pricing_recommendation_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.get_pricing_recommendation_api(role, "VEH-1")
        assert "recommended_price" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_pricing_view_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.get_pricing_view_api(role, "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_pricing_view_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.get_pricing_view_api(role, "VEH-1")
        assert "vehicle" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_pricing_queue_denied(self, role):
        result = pricing_desk_api.get_pricing_queue_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_pricing_queue_allowed(self, role):
        result = pricing_desk_api.get_pricing_queue_api(role)
        assert result == {"count": 0, "vehicles": []}

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_apply_price_recommendation_denied(self, role):
        _add_vehicle()
        result = pricing_desk_api.apply_price_recommendation_api(role, "EMP-1", "VEH-1", 22000)
        assert "error" in result

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_apply_price_recommendation_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = pricing_desk_api.apply_price_recommendation_api(role, "EMP-1", "VEH-1", 22000)
        assert result["vehicle"]["price"] == 22000
