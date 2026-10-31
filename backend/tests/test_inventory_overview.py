"""
Test coverage for core/inventory_overview.py -- Inventory's Overview
enrichment: real lifecycle-stage counts + frontline-ready count, plus three
SIMULATED aggregates (aging summary, turn rate, market days supply) and a
real+simulated blended Readiness Score.

The three simulated dependency functions (get_age_based_adjustment,
get_market_pricing, get_vdp_health) are monkeypatched per-test to canned,
controllable fakes rather than exercised via their real deterministic
SHA-256 seeding -- this module's own logic (aggregation, bucketing,
weighting, grading) is the actual target, not core/pricing_desk.py's/
core/merchandising.py's own simulated-seed math (each already has -- or
will have -- its own dedicated test file).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DOCUMENT

import core.inventory_overview as io


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, price=None, cost=None, date_sold=None, lifecycle_status=None):
    attrs = {}
    if price is not None:
        attrs["Price"] = price
    if cost is not None:
        attrs["Cost"] = cost
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    if lifecycle_status is not None:
        attrs["lifecycle_status"] = lifecycle_status
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vid)


def _title_doc(doc_id, vehicle_id):
    ledger.add_entity(Entity(id=doc_id, entity_type=DOCUMENT, attributes={
        "EntityID": vehicle_id, "EntityType": VEHICLE, "DocumentType": "Title",
    }))


def _other_doc(doc_id, vehicle_id, doc_type):
    ledger.add_entity(Entity(id=doc_id, entity_type=DOCUMENT, attributes={
        "EntityID": vehicle_id, "EntityType": VEHICLE, "DocumentType": doc_type,
    }))


def _fake_age_map(mapping):
    def fn(vehicle_id):
        return mapping.get(vehicle_id, {"error": "not found"})
    return fn


def _fake_market_map(mapping):
    def fn(vehicle_id):
        return mapping.get(vehicle_id, {"error": "not found"})
    return fn


def _fake_vdp_map(mapping):
    def fn(vehicle_id):
        return mapping.get(vehicle_id, {"error": "not found"})
    return fn


class TestLifecycleStatusHelper:

    def test_returns_stored_lifecycle_status(self):
        v = _vehicle("VEH-1", lifecycle_status="Recon")
        assert io._lifecycle_status(v) == "Recon"

    def test_defaults_to_front_line_ready_when_unsold_and_unset(self):
        v = _vehicle("VEH-1")
        assert io._lifecycle_status(v) == "Front Line Ready"

    def test_defaults_to_sold_when_date_sold_and_unset(self):
        v = _vehicle("VEH-1", date_sold="2026-07-01")
        assert io._lifecycle_status(v) == "Sold"


class TestGetLifecycleStageCounts:

    def test_counts_all_vehicles_not_just_unsold(self):
        _vehicle("VEH-1", date_sold="2026-07-01")  # defaults to Sold
        _vehicle("VEH-2")  # defaults to Front Line Ready
        counts = io.get_lifecycle_stage_counts()
        assert counts["Sold"] == 1
        assert counts["Front Line Ready"] == 1

    def test_explicit_status_counted_under_that_stage(self):
        _vehicle("VEH-1", lifecycle_status="Recon")
        _vehicle("VEH-2", lifecycle_status="Recon")
        counts = io.get_lifecycle_stage_counts()
        assert counts["Recon"] == 2

    def test_every_lifecycle_stage_key_present(self):
        counts = io.get_lifecycle_stage_counts()
        for stage in io.LIFECYCLE_STAGES:
            assert stage in counts

    def test_empty_ledger_returns_all_zero_counts(self):
        counts = io.get_lifecycle_stage_counts()
        assert all(v == 0 for v in counts.values())
        assert sum(counts.values()) == 0


class TestGetFrontlineReadyCount:

    def test_counts_unsold_vehicle_defaulting_to_front_line_ready(self):
        _vehicle("VEH-1")
        assert io.get_frontline_ready_count() == 1

    def test_excludes_unsold_vehicle_in_a_different_stage(self):
        _vehicle("VEH-1", lifecycle_status="Recon")
        assert io.get_frontline_ready_count() == 0

    def test_excludes_sold_vehicle_even_if_stage_says_front_line_ready(self):
        _vehicle("VEH-1", date_sold="2026-07-01", lifecycle_status="Front Line Ready")
        assert io.get_frontline_ready_count() == 0

    def test_empty_ledger_returns_zero(self):
        assert io.get_frontline_ready_count() == 0


class TestGetSimulatedAgingSummary:

    def test_averages_ages_across_unsold_vehicles(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 10, "age_band": "0-30 days"},
            "VEH-2": {"estimated_listing_age_days": 30, "age_band": "0-30 days"},
        }))
        result = io.get_simulated_aging_summary()
        assert result["average_days_in_stock"] == 20.0
        assert result["sample_size"] == 2
        assert result["aged_units_by_band"]["0-30 days"] == 2
        assert result["basis"] == io.SIMULATED_BASIS

    def test_only_unsold_vehicles_considered(self, monkeypatch):
        _vehicle("VEH-1", date_sold="2026-07-01")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 999, "age_band": "91+ days"},
            "VEH-2": {"estimated_listing_age_days": 15, "age_band": "0-30 days"},
        }))
        result = io.get_simulated_aging_summary()
        assert result["sample_size"] == 1
        assert result["average_days_in_stock"] == 15.0

    def test_errored_vehicle_excluded_from_sample(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"error": "no data"},
            "VEH-2": {"estimated_listing_age_days": 40, "age_band": "31-60 days"},
        }))
        result = io.get_simulated_aging_summary()
        assert result["sample_size"] == 1
        assert result["average_days_in_stock"] == 40.0

    def test_no_unsold_vehicles_returns_none_average(self, monkeypatch):
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({}))
        result = io.get_simulated_aging_summary()
        assert result["average_days_in_stock"] is None
        assert result["sample_size"] == 0
        assert result["aged_units_by_band"] == {
            "0-30 days": 0, "31-60 days": 0, "61-90 days": 0, "91+ days": 0,
        }
        assert "disclaimer" in result


class TestGetSimulatedTurnRate:

    def test_uses_explicit_avg_days_in_stock(self):
        result = io.get_simulated_turn_rate(avg_days_in_stock=73.0)
        assert result["annualized_turn_rate"] == round(365 / 73.0, 2)
        assert result["based_on_avg_days_in_stock"] == 73.0
        assert result["basis"] == io.SIMULATED_BASIS

    def test_falls_back_to_aging_summary_when_not_supplied(self, monkeypatch):
        _vehicle("VEH-1")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 50, "age_band": "31-60 days"},
        }))
        result = io.get_simulated_turn_rate()
        assert result["based_on_avg_days_in_stock"] == 50.0
        assert result["annualized_turn_rate"] == round(365 / 50.0, 2)

    def test_none_avg_days_in_stock_yields_none_turn_rate(self):
        result = io.get_simulated_turn_rate(avg_days_in_stock=None)
        assert result["annualized_turn_rate"] is None

    def test_zero_avg_days_in_stock_yields_none_turn_rate(self):
        result = io.get_simulated_turn_rate(avg_days_in_stock=0)
        assert result["annualized_turn_rate"] is None


class TestGetSimulatedMarketDaysSupply:

    def test_averages_supply_across_unsold_vehicles(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 40, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 60, "price_position": "at_market"},
        }))
        result = io.get_simulated_market_days_supply()
        assert result["market_days_supply"] == 50.0
        assert result["sample_size"] == 2
        assert result["basis"] == io.SIMULATED_BASIS

    def test_only_unsold_vehicles_considered(self, monkeypatch):
        _vehicle("VEH-1", date_sold="2026-07-01")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 200, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 20, "price_position": "at_market"},
        }))
        result = io.get_simulated_market_days_supply()
        assert result["sample_size"] == 1
        assert result["market_days_supply"] == 20.0

    def test_errored_vehicle_excluded(self, monkeypatch):
        _vehicle("VEH-1")
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"error": "no comps"},
        }))
        result = io.get_simulated_market_days_supply()
        assert result["sample_size"] == 0
        assert result["market_days_supply"] is None

    def test_no_unsold_vehicles_returns_none(self, monkeypatch):
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({}))
        result = io.get_simulated_market_days_supply()
        assert result["market_days_supply"] is None
        assert result["sample_size"] == 0


class TestGetReadinessScore:

    def test_no_unsold_vehicles_returns_none_score(self, monkeypatch):
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({}))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({}))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({}))
        result = io.get_readiness_score()
        assert result["score"] is None
        assert result["grade"] is None
        assert result["sample_size"] == 0
        assert result["components"] == {}

    def _rig(self, monkeypatch, vehicle_ids, age_band="0-30 days", price_position="at_market", has_photos=True, has_description=True):
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            vid: {"estimated_listing_age_days": 10, "age_band": age_band} for vid in vehicle_ids
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            vid: {"market_days_supply": 30, "price_position": price_position} for vid in vehicle_ids
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            vid: {"has_photos": has_photos, "has_description": has_description} for vid in vehicle_ids
        }))

    def test_margin_ok_requires_price_above_cost(self, monkeypatch):
        v1 = _vehicle("VEH-1", price=20000, cost=15000)  # margin ok
        v2 = _vehicle("VEH-2", price=20000, cost=20000)  # not ok (not strictly above)
        self._rig(monkeypatch, ["VEH-1", "VEH-2"])
        result = io.get_readiness_score()
        assert result["components"]["margin_health"]["pct"] == 50.0

    def test_merch_ok_requires_both_photos_and_description(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 10, "age_band": "0-30 days"},
            "VEH-2": {"estimated_listing_age_days": 10, "age_band": "0-30 days"},
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 30, "price_position": "at_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            "VEH-1": {"has_photos": True, "has_description": True},
            "VEH-2": {"has_photos": True, "has_description": False},
        }))
        result = io.get_readiness_score()
        assert result["components"]["merchandising_health"]["pct"] == 50.0

    def test_title_ok_requires_real_title_document_on_vehicle(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        _title_doc("DOC-1", "VEH-1")
        _other_doc("DOC-2", "VEH-2", "Recon Form")
        self._rig(monkeypatch, ["VEH-1", "VEH-2"])
        result = io.get_readiness_score()
        assert result["components"]["title_health"]["pct"] == 50.0

    def test_aging_ok_excludes_91_plus_days_band(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 10, "age_band": "0-30 days"},
            "VEH-2": {"estimated_listing_age_days": 100, "age_band": "91+ days"},
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 30, "price_position": "at_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            "VEH-1": {"has_photos": True, "has_description": True},
            "VEH-2": {"has_photos": True, "has_description": True},
        }))
        result = io.get_readiness_score()
        assert result["components"]["aging_health"]["pct"] == 50.0
        assert result["components"]["aging_health"]["basis"] == io.SIMULATED_BASIS

    def test_aging_errored_vehicle_does_not_count_as_ok(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 10, "age_band": "0-30 days"},
            "VEH-2": {"error": "no data"},
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 30, "price_position": "at_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            "VEH-1": {"has_photos": True, "has_description": True},
            "VEH-2": {"has_photos": True, "has_description": True},
        }))
        result = io.get_readiness_score()
        assert result["components"]["aging_health"]["pct"] == 50.0

    def test_market_ok_includes_at_market_and_below_market_only(self, monkeypatch):
        _vehicle("VEH-1")
        _vehicle("VEH-2")
        _vehicle("VEH-3")
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            vid: {"estimated_listing_age_days": 10, "age_band": "0-30 days"} for vid in ("VEH-1", "VEH-2", "VEH-3")
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
            "VEH-2": {"market_days_supply": 30, "price_position": "below_market"},
            "VEH-3": {"market_days_supply": 30, "price_position": "above_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            vid: {"has_photos": True, "has_description": True} for vid in ("VEH-1", "VEH-2", "VEH-3")
        }))
        result = io.get_readiness_score()
        assert result["components"]["market_position_health"]["pct"] == round(100 * 2 / 3, 1)

    def test_all_criteria_met_scores_100_grade_a(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        _title_doc("DOC-1", "VEH-1")
        self._rig(monkeypatch, ["VEH-1"], age_band="0-30 days", price_position="at_market")
        result = io.get_readiness_score()
        assert result["score"] == 100.0
        assert result["grade"] == "A"

    def test_margin_merch_title_aging_only_scores_85_grade_b(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        _title_doc("DOC-1", "VEH-1")
        self._rig(monkeypatch, ["VEH-1"], age_band="0-30 days", price_position="above_market")
        result = io.get_readiness_score()
        assert result["score"] == 85.0
        assert result["grade"] == "B"

    def test_margin_merch_title_only_scores_70_grade_c(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        _title_doc("DOC-1", "VEH-1")
        self._rig(monkeypatch, ["VEH-1"], age_band="91+ days", price_position="above_market")
        result = io.get_readiness_score()
        assert result["score"] == 70.0
        assert result["grade"] == "C"

    def test_margin_title_aging_only_scores_60_grade_d(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        _title_doc("DOC-1", "VEH-1")
        self._rig(monkeypatch, ["VEH-1"], age_band="0-30 days", price_position="above_market", has_photos=False)
        result = io.get_readiness_score()
        assert result["score"] == 60.0
        assert result["grade"] == "D"

    def test_margin_merch_only_scores_50_grade_f(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        self._rig(monkeypatch, ["VEH-1"], age_band="91+ days", price_position="above_market")
        result = io.get_readiness_score()
        assert result["score"] == 50.0
        assert result["grade"] == "F"

    def test_nothing_met_scores_zero_grade_f(self, monkeypatch):
        _vehicle("VEH-1", price=15000, cost=20000)  # underwater
        self._rig(monkeypatch, ["VEH-1"], age_band="91+ days", price_position="above_market", has_photos=False, has_description=False)
        result = io.get_readiness_score()
        assert result["score"] == 0.0
        assert result["grade"] == "F"

    def test_disclaimer_and_mixed_basis_present(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        self._rig(monkeypatch, ["VEH-1"])
        result = io.get_readiness_score()
        assert result["basis"] == "mixed"
        assert "disclaimer" in result


class TestGetInventoryOverviewEnrichment:

    def test_returns_all_expected_top_level_keys(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 20, "age_band": "0-30 days"},
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            "VEH-1": {"has_photos": True, "has_description": True},
        }))
        result = io.get_inventory_overview_enrichment()
        for key in ("lifecycle_stage_counts", "frontline_ready_units", "aging_summary", "turn_rate", "market_days_supply", "readiness_score"):
            assert key in result

    def test_turn_rate_reuses_aging_summary_average(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({
            "VEH-1": {"estimated_listing_age_days": 73, "age_band": "61-90 days"},
        }))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({
            "VEH-1": {"market_days_supply": 30, "price_position": "at_market"},
        }))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({
            "VEH-1": {"has_photos": True, "has_description": True},
        }))
        result = io.get_inventory_overview_enrichment()
        assert result["turn_rate"]["based_on_avg_days_in_stock"] == result["aging_summary"]["average_days_in_stock"]
        assert result["turn_rate"]["based_on_avg_days_in_stock"] == 73.0

    def test_frontline_ready_units_reflects_real_count(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)  # unsold, defaults to Front Line Ready
        monkeypatch.setattr(io, "get_age_based_adjustment", _fake_age_map({}))
        monkeypatch.setattr(io, "get_market_pricing", _fake_market_map({}))
        monkeypatch.setattr(io, "get_vdp_health", _fake_vdp_map({}))
        result = io.get_inventory_overview_enrichment()
        assert result["frontline_ready_units"] == 1
