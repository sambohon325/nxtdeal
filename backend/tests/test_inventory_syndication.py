"""
Test coverage for core/inventory_syndication.py -- Inventory Syndication, a
pure composition layer over core/merchandising.py's SIMULATED per-vehicle
feed-sync mechanism and core/marketing_attribution.py's REAL Lead.Source
first-touch revenue engine.

core/inventory_syndication_api.py (the thin ACL wrapper) already has coverage
in tests/test_thin_wrapper_batch_3.py, but that file mocks every function
this module exports away entirely -- the real aggregation/mapping/bulk-action
logic in this module itself has zero coverage before this file.

The three per-vehicle simulated dependencies (get_feed_status,
_vehicle_images, publish_to_feed) are all imported at this module's own top
level (`from core.merchandising import ...`), so they're monkeypatched at
core.inventory_syndication's own namespace for full, controllable per-test
fixtures rather than exercised via their real SHA-256-seeded simulation math
(core/merchandising.py owns that math and gets its own test file). By
contrast, get_channel_mix is imported INSIDE get_syndication_lead_
performance() (a deferred import) -- that name is re-resolved from
core.marketing_attribution's own namespace on every call, so it must be
monkeypatched there instead.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, LEAD

import core.inventory_syndication as isy
import core.marketing_attribution as ma


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, price=1000, date_sold=None, description=None):
    attrs = {"Price": price}
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    if description is not None:
        attrs["description"] = description
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vid)


def _fake_feed_status(status_map):
    """status_map: {vehicle_id: {platform: status}} -- any platform not
    explicitly given for a vehicle defaults to "pending", matching the real
    get_feed_status()'s own always-returns-all-4-platforms shape."""

    def fn(vehicle_id):
        per_platform = status_map.get(vehicle_id, {})
        return {
            "vehicle_id": vehicle_id,
            "feeds": [
                {"platform": p, "status": per_platform.get(p, "pending")}
                for p in isy.FEED_PLATFORMS
            ],
        }

    return fn


def _fake_vehicle_images(images_map):
    def fn(vehicle_id):
        return images_map.get(vehicle_id, [])

    return fn


def _fake_publish_to_feed(fail_for=()):
    calls = []

    def fn(vehicle_id, platform, published_by):
        calls.append((vehicle_id, platform, published_by))
        if vehicle_id in fail_for:
            return {"error": "simulated failure"}
        return {"vehicle_id": vehicle_id, "entry": {"platform": platform}, "basis": "simulated_market_data"}

    fn.calls = calls
    return fn


def _rig_feed_and_images(monkeypatch, feed_map, images_map=None):
    monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status(feed_map))
    monkeypatch.setattr(isy, "_vehicle_images", _fake_vehicle_images(images_map or {}))


def _channel(source, lead_count=0, sold_count=0, revenue=0.0, funded_deals_count=0, conversion_rate=0.0, revenue_per_lead=0.0):
    return {
        "source": source,
        "lead_count": lead_count,
        "sold_count": sold_count,
        "revenue": revenue,
        "funded_deals_count": funded_deals_count,
        "conversion_rate": conversion_rate,
        "revenue_per_lead": revenue_per_lead,
    }


def _fake_channel_mix(channels):
    return {"channels": channels}


class TestVehicleBrief:

    def test_includes_core_fields(self):
        v = _vehicle("V1", price=25000)
        v.attributes["VIN"] = "1FTFW1ET5BFC12345"
        v.attributes["StockNumber"] = "S123"
        v.attributes["Year"] = 2022
        v.attributes["Make"] = "Ford"
        v.attributes["Model"] = "F-150"

        brief = isy._vehicle_brief(v)

        assert brief["vehicle_id"] == "V1"
        assert brief["vin"] == "1FTFW1ET5BFC12345"
        assert brief["stock_number"] == "S123"
        assert brief["year"] == 2022
        assert brief["make"] == "Ford"
        assert brief["model"] == "F-150"
        assert brief["price"] == 25000.0

    def test_price_none_when_zero_or_missing(self):
        v = _vehicle("V1", price=0)
        assert isy._vehicle_brief(v)["price"] is None


class TestGetVehicleHelper:

    def test_returns_none_for_missing_id(self):
        assert isy._get_vehicle("VEH-NOPE") is None

    def test_returns_none_for_wrong_entity_type(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
        assert isy._get_vehicle("LEAD-1") is None

    def test_returns_the_entity_for_a_real_vehicle(self):
        _vehicle("V1")
        assert isy._get_vehicle("V1").id == "V1"


class TestGetFeedHealthRollup:

    def test_aggregates_synced_pending_error_counts_per_platform(self, monkeypatch):
        _vehicle("V1", description="A description")
        _vehicle("V2", description="A description")
        _vehicle("V3", description="")
        _vehicle("V4", description="")
        _vehicle("V5", description="A description")

        feed_map = {
            "V1": {"Cars.com": "synced"},
            "V2": {"AutoTrader": "synced"},
            "V3": {"CarGurus": "synced"},
            "V4": {},
            "V5": {"Cars.com": "error"},
        }
        images_map = {
            "V1": [{"id": "IMG-1"}],
            "V3": [{"id": "IMG-2"}],
            "V5": [{"id": "IMG-3"}],
        }
        _rig_feed_and_images(monkeypatch, feed_map, images_map)

        result = isy.get_feed_health_rollup()
        by_platform = {p["platform"]: p for p in result["platforms"]}

        assert by_platform["Cars.com"]["synced"] == 1
        assert by_platform["Cars.com"]["pending"] == 3
        assert by_platform["Cars.com"]["error"] == 1

        assert by_platform["AutoTrader"]["synced"] == 1
        assert by_platform["AutoTrader"]["pending"] == 4
        assert by_platform["AutoTrader"]["error"] == 0

        assert by_platform["CarGurus"]["synced"] == 1
        assert by_platform["CarGurus"]["pending"] == 4

        assert by_platform["CarFax Listings"]["synced"] == 0
        assert by_platform["CarFax Listings"]["pending"] == 5

        assert result["total_unsold"] == 5

    def test_error_vehicles_drilldown_only_contains_errored_vehicles(self, monkeypatch):
        _vehicle("V5", description="A description")
        _rig_feed_and_images(monkeypatch, {"V5": {"Cars.com": "error"}}, {"V5": [{"id": "IMG"}]})

        result = isy.get_feed_health_rollup()
        by_platform = {p["platform"]: p for p in result["platforms"]}

        assert [v["vehicle_id"] for v in by_platform["Cars.com"]["error_vehicles"]] == ["V5"]
        assert by_platform["AutoTrader"]["error_vehicles"] == []

    def test_error_drilldown_capped_at_limit(self, monkeypatch):
        feed_map = {}
        for i in range(5):
            vid = f"V{i}"
            _vehicle(vid, description="d")
            feed_map[vid] = {"Cars.com": "error"}
        _rig_feed_and_images(monkeypatch, feed_map, {})

        result = isy.get_feed_health_rollup(error_drilldown_limit=2)
        by_platform = {p["platform"]: p for p in result["platforms"]}

        assert by_platform["Cars.com"]["error"] == 5
        assert len(by_platform["Cars.com"]["error_vehicles"]) == 2

    def test_listing_completeness_flags_synced_vehicle_missing_photos(self, monkeypatch):
        _vehicle("V1", description="A description")
        _rig_feed_and_images(monkeypatch, {"V1": {"Cars.com": "synced"}}, {})

        result = isy.get_feed_health_rollup()

        assert result["listing_completeness_risk"]["count"] == 1
        risk = result["listing_completeness_risk"]["vehicles"][0]
        assert risk["vehicle_id"] == "V1"
        assert risk["has_photos"] is False
        assert risk["has_description"] is True

    def test_listing_completeness_flags_synced_vehicle_missing_description(self, monkeypatch):
        _vehicle("V1", description="")
        _rig_feed_and_images(monkeypatch, {"V1": {"Cars.com": "synced"}}, {"V1": [{"id": "IMG"}]})

        result = isy.get_feed_health_rollup()

        assert result["listing_completeness_risk"]["count"] == 1
        assert result["listing_completeness_risk"]["vehicles"][0]["has_description"] is False

    def test_listing_completeness_does_not_flag_a_complete_synced_listing(self, monkeypatch):
        _vehicle("V1", description="A description")
        _rig_feed_and_images(monkeypatch, {"V1": {"Cars.com": "synced"}}, {"V1": [{"id": "IMG"}]})

        result = isy.get_feed_health_rollup()

        assert result["listing_completeness_risk"]["count"] == 0

    def test_listing_completeness_ignores_a_vehicle_never_synced_anywhere(self, monkeypatch):
        _vehicle("V1", description="")
        _rig_feed_and_images(monkeypatch, {"V1": {}}, {})

        result = isy.get_feed_health_rollup()

        assert result["listing_completeness_risk"]["count"] == 0

    def test_excludes_sold_vehicles(self, monkeypatch):
        _vehicle("V1", date_sold="2026-01-01", description="")
        _rig_feed_and_images(monkeypatch, {}, {})

        result = isy.get_feed_health_rollup()

        assert result["total_unsold"] == 0

    def test_basis_and_disclaimer_present(self, monkeypatch):
        _rig_feed_and_images(monkeypatch, {}, {})

        result = isy.get_feed_health_rollup()

        assert result["basis"] == isy.SIMULATED_BASIS
        assert "SIMULATED" in result["disclaimer"]
        assert "REAL" in result["listing_completeness_risk"]["note"]


class TestGetSyndicationLeadPerformance:

    def test_real_data_flows_through_for_a_mapped_platform(self, monkeypatch):
        channels = [_channel("Cars.com", lead_count=10, revenue=5000.0)]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_lead_performance()
        row = next(r for r in result["platform_performance"] if r["platform"] == "Cars.com")

        assert row["lead_source"] == "Cars.com"
        assert row["lead_count"] == 10
        assert row["revenue"] == 5000.0

    def test_unmatched_mapped_platform_gets_zero_fallback_row(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_lead_performance()
        row = next(r for r in result["platform_performance"] if r["platform"] == "CarGurus")

        assert row["lead_count"] == 0
        assert row["revenue"] == 0.0
        assert row["conversion_rate"] == 0.0

    def test_autotrader_platform_maps_to_capitalized_autotrader_source(self, monkeypatch):
        channels = [_channel("Autotrader", lead_count=109, revenue=1200.0)]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_lead_performance()
        row = next(r for r in result["platform_performance"] if r["platform"] == "AutoTrader")

        assert row["lead_source"] == "Autotrader"
        assert row["lead_count"] == 109

    def test_sorted_by_revenue_descending(self, monkeypatch):
        channels = [
            _channel("Cars.com", revenue=100.0),
            _channel("Autotrader", revenue=500.0),
            _channel("CarGurus", revenue=250.0),
        ]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_lead_performance()

        assert [r["platform"] for r in result["platform_performance"]] == ["AutoTrader", "CarGurus", "Cars.com"]

    def test_total_syndication_revenue_and_leads_sum_across_platforms(self, monkeypatch):
        channels = [
            _channel("Cars.com", lead_count=10, revenue=100.0),
            _channel("Autotrader", lead_count=20, revenue=200.0),
        ]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_lead_performance()

        # CarGurus contributes 0 (no matching channel) -- 100 + 200 + 0 = 300
        assert result["total_syndication_revenue"] == 300.0
        assert result["total_syndication_leads"] == 30

    def test_carfax_listings_reported_as_feed_only_platform(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_lead_performance()

        assert "CarFax Listings" in result["feed_only_platforms"]
        assert "Cars.com" not in result["feed_only_platforms"]

    def test_facebook_marketplace_reported_as_lead_only_channel_when_present(self, monkeypatch):
        channels = [_channel("Facebook Marketplace", lead_count=59, revenue=900.0)]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_lead_performance()

        assert len(result["lead_only_channels"]) == 1
        assert result["lead_only_channels"][0]["source"] == "Facebook Marketplace"
        assert result["lead_only_channels"][0]["lead_count"] == 59

    def test_facebook_marketplace_absent_when_no_leads_exist_for_it(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_lead_performance()

        assert result["lead_only_channels"] == []

    def test_basis_and_disclaimer_present(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_lead_performance()

        assert result["basis"] == "real_first_touch_not_multi_touch"
        assert "Facebook Marketplace" in result["disclaimer"]


class TestRepublishPlatform:

    def test_bad_platform_returns_error(self):
        result = isy.republish_platform("Not A Real Platform", "EMP-1")
        assert "error" in result

    def test_republishes_only_pending_or_error_vehicles_for_that_platform(self, monkeypatch):
        _vehicle("V-SYNCED")
        _vehicle("V-PENDING")
        _vehicle("V-ERROR")
        feed_map = {
            "V-SYNCED": {"Cars.com": "synced"},
            "V-PENDING": {"Cars.com": "pending"},
            "V-ERROR": {"Cars.com": "error"},
        }
        monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status(feed_map))
        fake_publish = _fake_publish_to_feed()
        monkeypatch.setattr(isy, "publish_to_feed", fake_publish)

        result = isy.republish_platform("Cars.com", "EMP-1")

        assert sorted(result["republished_vehicle_ids"]) == ["V-ERROR", "V-PENDING"]
        assert result["republished_count"] == 2
        assert sorted(vid for vid, platform, by in fake_publish.calls) == ["V-ERROR", "V-PENDING"]

    def test_skips_a_vehicle_when_publish_returns_an_error(self, monkeypatch):
        _vehicle("V-PENDING-1")
        _vehicle("V-PENDING-2")
        feed_map = {
            "V-PENDING-1": {"Cars.com": "pending"},
            "V-PENDING-2": {"Cars.com": "pending"},
        }
        monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status(feed_map))
        monkeypatch.setattr(isy, "publish_to_feed", _fake_publish_to_feed(fail_for=("V-PENDING-1",)))

        result = isy.republish_platform("Cars.com", "EMP-1")

        assert result["republished_vehicle_ids"] == ["V-PENDING-2"]
        assert result["republished_count"] == 1

    def test_only_checks_the_requested_platforms_own_status_entry(self, monkeypatch):
        _vehicle("V1")
        # Cars.com is synced (should NOT republish) even though AutoTrader errors
        feed_map = {"V1": {"Cars.com": "synced", "AutoTrader": "error"}}
        monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status(feed_map))
        fake_publish = _fake_publish_to_feed()
        monkeypatch.setattr(isy, "publish_to_feed", fake_publish)

        result = isy.republish_platform("Cars.com", "EMP-1")

        assert result["republished_count"] == 0
        assert fake_publish.calls == []

    def test_excludes_sold_vehicles(self, monkeypatch):
        _vehicle("V-SOLD", date_sold="2026-01-01")
        feed_map = {"V-SOLD": {"Cars.com": "pending"}}
        monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status(feed_map))
        fake_publish = _fake_publish_to_feed()
        monkeypatch.setattr(isy, "publish_to_feed", fake_publish)

        result = isy.republish_platform("Cars.com", "EMP-1")

        assert result["republished_count"] == 0

    def test_basis_and_disclaimer_present(self, monkeypatch):
        monkeypatch.setattr(isy, "get_feed_status", _fake_feed_status({}))
        monkeypatch.setattr(isy, "publish_to_feed", _fake_publish_to_feed())

        result = isy.republish_platform("Cars.com", "EMP-1")

        assert result["basis"] == isy.SIMULATED_BASIS
        assert "SIMULATED" in result["disclaimer"]
        assert "Cars.com" in result["disclaimer"]


class TestGetSyndicationOverview:

    def test_composes_feed_health_and_lead_performance(self, monkeypatch):
        _vehicle("V1", description="d")
        _vehicle("V2", description="")
        feed_map = {
            "V1": {"Cars.com": "synced"},
            "V2": {"Cars.com": "error", "AutoTrader": "pending"},
        }
        _rig_feed_and_images(monkeypatch, feed_map, {"V1": [{"id": "IMG"}]})
        channels = [_channel("Cars.com", lead_count=5, revenue=100.0)]
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix(channels))

        result = isy.get_syndication_overview()

        assert result["total_unsold_vehicles"] == 2
        assert result["total_listing_errors"] == 1
        assert result["total_syndication_revenue"] == 100.0
        assert result["total_syndication_leads"] == 5
        assert "feed_health" in result
        assert "lead_performance" in result

    def test_listing_completeness_risk_count_matches_feed_health(self, monkeypatch):
        _vehicle("V1", description="")
        _rig_feed_and_images(monkeypatch, {"V1": {"Cars.com": "synced"}}, {})
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_overview()

        assert result["listing_completeness_risk_count"] == 1
        assert result["listing_completeness_risk_count"] == result["feed_health"]["listing_completeness_risk"]["count"]

    def test_total_listing_pending_sums_across_platforms(self, monkeypatch):
        _vehicle("V1")
        # No status supplied for V1 -- all 4 platforms default to "pending"
        _rig_feed_and_images(monkeypatch, {}, {})
        monkeypatch.setattr(ma, "get_channel_mix", lambda: _fake_channel_mix([]))

        result = isy.get_syndication_overview()

        assert result["total_listing_pending"] == 4
