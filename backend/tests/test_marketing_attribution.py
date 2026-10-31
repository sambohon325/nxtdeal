"""
Test coverage for core/marketing_attribution.py -- the Attribution Engine +
Marketing ROI Dashboard + Vehicle Attribution: real, honest first-touch
Lead.Source revenue attribution, a composed ROI dashboard reusing Campaign/
PURL revenue engines already built elsewhere, and a real Vehicle Attribution
cross-reference of marketing signals against funded sales.

Ledger fixtures (Lead/Customer/BECAME/Vehicle/Deal/Campaign/SocialPost) drive
the pure-graph-reading functions (_safe_float, _funded_deal_gross_since,
get_channel_mix, get_vehicle_attribution) directly against real entities/
relationships -- this exercises core.lead_scoring's real _resolve_identity()
too, since it's a top-level import reused verbatim (per this module's own
docstring), not a thing worth re-mocking.

get_marketing_roi_dashboard() is different: it calls get_channel_mix
(a same-module function, safely monkeypatchable on this module's own
namespace) plus 4 functions pulled in via DEFERRED, in-function imports
(core.campaigns.list_campaigns, core.campaign_analytics.get_campaign_revenue,
core.purls.list_purls/get_purl_analytics) -- those 4 must be monkeypatched on
their OWN source modules, not on core.marketing_attribution, since the
deferred `from X import name` re-reads X's attribute fresh at call time.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.marketing_attribution as ma
import core.campaigns as campaigns_mod
import core.campaign_analytics as campaign_analytics_mod
import core.purls as purls_mod

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.relationship_types import BECAME
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE, CAMPAIGN, SOCIAL_POST

import pytest


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _lead(lid, source=None, pipeline_state=None):
    attrs = {}
    if source is not None:
        attrs["Source"] = source
    if pipeline_state is not None:
        attrs["PipelineState"] = pipeline_state
    ledger.add_entity(Entity(id=lid, entity_type=LEAD, attributes=attrs))
    return ledger.get_entity(lid)


def _customer(cid):
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={}))
    return ledger.get_entity(cid)


def _became(lead_id, customer_id):
    ledger.add_relationship(Relationship(source_id=lead_id, target_id=customer_id, relationship_type=BECAME))


def _vehicle(vid, price=None, cost=None, make=None, model=None):
    attrs = {}
    if price is not None:
        attrs["Price"] = price
    if cost is not None:
        attrs["Cost"] = cost
    if make is not None:
        attrs["Make"] = make
    if model is not None:
        attrs["Model"] = model
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vid)


def _deal(did, status=None, customer_id=None, vehicle_id=None, funded_at=None):
    attrs = {}
    if status is not None:
        attrs["status"] = status
    if customer_id is not None:
        attrs["customer_id"] = customer_id
    if vehicle_id is not None:
        attrs["vehicle_id"] = vehicle_id
    if funded_at is not None:
        attrs["funded_at"] = funded_at
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes=attrs))
    return ledger.get_entity(did)


def _campaign(cid, campaign_type=None, status=None, params=None):
    attrs = {}
    if campaign_type is not None:
        attrs["campaign_type"] = campaign_type
    if status is not None:
        attrs["status"] = status
    if params is not None:
        attrs["params"] = params
    ledger.add_entity(Entity(id=cid, entity_type=CAMPAIGN, attributes=attrs))
    return ledger.get_entity(cid)


def _social_post(pid, linked_vehicle_ids=None):
    attrs = {}
    if linked_vehicle_ids is not None:
        attrs["linked_vehicle_ids"] = linked_vehicle_ids
    ledger.add_entity(Entity(id=pid, entity_type=SOCIAL_POST, attributes=attrs))
    return ledger.get_entity(pid)


class TestSafeFloat:

    def test_valid_string_converts(self):
        assert ma._safe_float("12.5") == 12.5

    def test_int_converts(self):
        assert ma._safe_float(7) == 7.0

    def test_none_returns_default(self):
        assert ma._safe_float(None) == 0.0

    def test_invalid_string_returns_default(self):
        assert ma._safe_float("not-a-number") == 0.0

    def test_custom_default_used_on_failure(self):
        assert ma._safe_float(None, default=99.0) == 99.0


class TestFundedDealGrossSince:

    def test_empty_customer_ids_returns_zero(self):
        vehicles = {}
        total, count = ma._funded_deal_gross_since(set(), None, vehicles)
        assert (total, count) == (0.0, 0)

    def test_non_funded_deal_excluded(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="contract", customer_id="CUST-1", vehicle_id="V1")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, None, ma._vehicles_by_id())

        assert (total, count) == (0.0, 0)

    def test_deal_for_a_different_customer_excluded(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-OTHER", vehicle_id="V1")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, None, ma._vehicles_by_id())

        assert (total, count) == (0.0, 0)

    def test_matching_funded_deal_contributes_gross_profit(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, None, ma._vehicles_by_id())

        assert total == 5000.0
        assert count == 1

    def test_multiple_deals_across_multiple_customer_ids_sum(self):
        _vehicle("V1", price=20000, cost=15000)
        _vehicle("V2", price=30000, cost=22000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")
        _deal("DEAL-2", status="funded", customer_id="CUST-2", vehicle_id="V2")

        total, count = ma._funded_deal_gross_since({"CUST-1", "CUST-2"}, None, ma._vehicles_by_id())

        assert total == 5000.0 + 8000.0
        assert count == 2

    def test_deal_with_no_matching_vehicle_still_counts_but_contributes_zero_gross(self):
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V-MISSING")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, None, ma._vehicles_by_id())

        assert total == 0.0
        assert count == 1

    def test_since_iso_floor_excludes_earlier_deals(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1", funded_at="2026-01-01T00:00:00")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, "2026-06-01T00:00:00", ma._vehicles_by_id())

        assert (total, count) == (0.0, 0)

    def test_since_iso_floor_includes_later_deals(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1", funded_at="2026-07-01T00:00:00")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, "2026-06-01T00:00:00", ma._vehicles_by_id())

        assert (total, count) == (5000.0, 1)

    def test_since_iso_floor_excludes_a_deal_with_no_funded_at_at_all(self):
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")

        total, count = ma._funded_deal_gross_since({"CUST-1"}, "2026-06-01T00:00:00", ma._vehicles_by_id())

        assert (total, count) == (0.0, 0)


class TestGetChannelMix:

    def test_groups_leads_by_source(self):
        _lead("LEAD-1", source="Website")
        _lead("LEAD-2", source="Website")
        _lead("LEAD-3", source="Walk-In")

        result = ma.get_channel_mix()
        by_source = {c["source"]: c for c in result["channels"]}

        assert by_source["Website"]["lead_count"] == 2
        assert by_source["Walk-In"]["lead_count"] == 1

    def test_missing_source_buckets_under_unknown(self):
        _lead("LEAD-1")

        result = ma.get_channel_mix()

        assert result["channels"][0]["source"] == "Unknown"
        assert result["channels"][0]["lead_count"] == 1

    def test_sold_count_only_increments_for_sold_pipeline_state(self):
        _lead("LEAD-1", source="Website", pipeline_state="SOLD")
        _lead("LEAD-2", source="Website", pipeline_state="CONTACTED")

        result = ma.get_channel_mix()
        website = result["channels"][0]

        assert website["lead_count"] == 2
        assert website["sold_count"] == 1

    def test_revenue_resolved_through_became_identity(self):
        _lead("LEAD-1", source="Website")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _vehicle("V1", price=25000, cost=18000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")

        result = ma.get_channel_mix()
        website = result["channels"][0]

        assert website["revenue"] == 7000.0
        assert website["funded_deals_count"] == 1

    def test_conversion_rate_and_revenue_per_lead_computed(self):
        _lead("LEAD-1", source="Website", pipeline_state="SOLD")
        _lead("LEAD-2", source="Website")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _vehicle("V1", price=25000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")

        result = ma.get_channel_mix()
        website = result["channels"][0]

        assert website["conversion_rate"] == 50.0
        assert website["revenue_per_lead"] == round(10000.0 / 2, 2)

    def test_channels_sorted_by_revenue_descending(self):
        _lead("LEAD-1", source="Low")
        _customer("CUST-LOW")
        _became("LEAD-1", "CUST-LOW")
        _vehicle("V-LOW", price=15000, cost=14000)
        _deal("DEAL-LOW", status="funded", customer_id="CUST-LOW", vehicle_id="V-LOW")

        _lead("LEAD-2", source="High")
        _customer("CUST-HIGH")
        _became("LEAD-2", "CUST-HIGH")
        _vehicle("V-HIGH", price=50000, cost=30000)
        _deal("DEAL-HIGH", status="funded", customer_id="CUST-HIGH", vehicle_id="V-HIGH")

        result = ma.get_channel_mix()

        assert [c["source"] for c in result["channels"]] == ["High", "Low"]

    def test_total_leads_and_total_revenue(self):
        _lead("LEAD-1", source="Website")
        _lead("LEAD-2", source="Walk-In")
        _customer("CUST-1")
        _became("LEAD-1", "CUST-1")
        _vehicle("V1", price=20000, cost=15000)
        _deal("DEAL-1", status="funded", customer_id="CUST-1", vehicle_id="V1")

        result = ma.get_channel_mix()

        assert result["total_leads"] == 2
        assert result["total_revenue"] == 5000.0

    def test_basis_and_disclaimer_present(self):
        result = ma.get_channel_mix()

        assert result["basis"] == "real_first_touch_not_multi_touch"
        assert "first-touch" in result["disclaimer"]

    def test_no_leads_at_all_returns_empty_channels(self):
        result = ma.get_channel_mix()

        assert result["channels"] == []
        assert result["total_leads"] == 0
        assert result["total_revenue"] == 0.0


class TestGetMarketingRoiDashboard:

    def test_composes_channel_mix_from_this_module(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {"marker": "channel-mix"})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [])
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})

        result = ma.get_marketing_roi_dashboard()

        assert result["channel_mix"] == {"marker": "channel-mix"}

    def test_only_active_or_completed_campaigns_are_considered(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})

        def _c(cid, status):
            return _campaign(cid, status=status)

        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [
            _c("CAMP-1", "active"),
            _c("CAMP-2", "completed"),
            _c("CAMP-3", "draft"),
            _c("CAMP-4", "cancelled"),
        ])

        seen_ids = []

        def fake_revenue(cid):
            seen_ids.append(cid)
            return {"eligible": True, "revenue": 100.0, "funded_deals_count": 1, "leads_sold_count": 1}

        monkeypatch.setattr(campaign_analytics_mod, "get_campaign_revenue", fake_revenue)

        ma.get_marketing_roi_dashboard()

        assert set(seen_ids) == {"CAMP-1", "CAMP-2"}

    def test_ineligible_campaign_revenue_is_excluded(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [_campaign("CAMP-1", status="active")])
        monkeypatch.setattr(campaign_analytics_mod, "get_campaign_revenue", lambda cid: {"eligible": False})

        result = ma.get_marketing_roi_dashboard()

        assert result["campaign_roi"]["campaigns"] == []
        assert result["campaign_roi"]["total_revenue"] == 0.0

    def test_non_dict_campaign_revenue_result_is_excluded(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [_campaign("CAMP-1", status="active")])
        monkeypatch.setattr(campaign_analytics_mod, "get_campaign_revenue", lambda cid: None)

        result = ma.get_marketing_roi_dashboard()

        assert result["campaign_roi"]["campaigns"] == []

    def test_campaign_rows_sorted_by_revenue_descending_and_capped_at_25(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})

        campaigns = [_campaign(f"CAMP-{i}", campaign_type="inventory_ads", status="active") for i in range(27)]
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: campaigns)

        def fake_revenue(cid):
            idx = int(cid.split("-")[1])
            return {"eligible": True, "revenue": float(idx), "funded_deals_count": 0, "leads_sold_count": 0}

        monkeypatch.setattr(campaign_analytics_mod, "get_campaign_revenue", fake_revenue)

        result = ma.get_marketing_roi_dashboard()

        rows = result["campaign_roi"]["campaigns"]
        assert len(rows) == 25
        assert rows[0]["campaign_id"] == "CAMP-26"
        assert result["campaign_roi"]["total_revenue"] == sum(range(27))

    def test_purls_with_correlated_data_are_included(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [])
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": [{"id": "PURL-1"}]})
        monkeypatch.setattr(purls_mod, "get_purl_analytics", lambda pid: {
            "correlated_since_creation": {"revenue": 1500.0},
            "visits": 4,
            "lead_generated": True,
        })

        result = ma.get_marketing_roi_dashboard()

        assert result["purl_roi"]["total_revenue"] == 1500.0
        assert result["purl_roi"]["purls"][0] == {
            "purl_id": "PURL-1",
            "revenue": 1500.0,
            "visits": 4,
            "lead_generated": True,
        }

    def test_purl_without_correlated_data_is_excluded(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [])
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": [{"id": "PURL-1"}]})
        monkeypatch.setattr(purls_mod, "get_purl_analytics", lambda pid: {"visits": 4})

        result = ma.get_marketing_roi_dashboard()

        assert result["purl_roi"]["purls"] == []
        assert result["purl_roi"]["total_revenue"] == 0.0

    def test_purl_rows_sorted_by_revenue_descending_and_capped_at_25(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [])

        purls = [{"id": f"PURL-{i}"} for i in range(27)]
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": purls})

        def fake_analytics(pid):
            idx = int(pid.split("-")[1])
            return {"correlated_since_creation": {"revenue": float(idx)}, "visits": 0, "lead_generated": False}

        monkeypatch.setattr(purls_mod, "get_purl_analytics", fake_analytics)

        result = ma.get_marketing_roi_dashboard()

        rows = result["purl_roi"]["purls"]
        assert len(rows) == 25
        assert rows[0]["purl_id"] == "PURL-26"

    def test_basis_and_disclaimer_fields_present(self, monkeypatch):
        monkeypatch.setattr(ma, "get_channel_mix", lambda: {})
        monkeypatch.setattr(campaigns_mod, "list_campaigns", lambda: [])
        monkeypatch.setattr(purls_mod, "list_purls", lambda: {"purls": []})

        result = ma.get_marketing_roi_dashboard()

        assert result["campaign_roi"]["basis"] == "real_but_not_proven_causal"
        assert result["purl_roi"]["basis"] == "real_but_not_proven_causal"
        assert "gross profit" in result["purl_roi"]["disclaimer"].lower() or "Vehicle.Price" in result["purl_roi"]["disclaimer"]


class TestGetVehicleAttribution:

    def test_inventory_ads_campaign_with_make_and_model_contributes_campaign_mentions(self):
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "Ford", "model": "F-150"})

        result = ma.get_vehicle_attribution()
        row = next(r for r in result["rows"] if r["make"] == "Ford" and r["model"] == "F-150")

        assert row["campaign_mentions"] == 1
        assert row["marketed"] is True

    def test_non_inventory_ads_campaign_excluded(self):
        _campaign("CAMP-1", campaign_type="retention", params={"make": "Ford", "model": "F-150"})

        result = ma.get_vehicle_attribution()

        assert result["rows"] == []

    def test_campaign_with_no_make_or_model_excluded(self):
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "", "model": ""})

        result = ma.get_vehicle_attribution()

        assert result["rows"] == []

    def test_campaign_with_only_make_falls_back_to_any_model(self):
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "Ford", "model": ""})

        result = ma.get_vehicle_attribution()
        row = result["rows"][0]

        assert row["make"] == "Ford"
        assert row["model"] == "Any Model"

    def test_multiple_campaigns_for_same_make_model_sum_mentions(self):
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "Ford", "model": "F-150"})
        _campaign("CAMP-2", campaign_type="inventory_ads", params={"make": "Ford", "model": "F-150"})

        result = ma.get_vehicle_attribution()
        row = result["rows"][0]

        assert row["campaign_mentions"] == 2

    def test_social_post_with_linked_vehicle_resolves_make_and_model(self):
        _vehicle("V1", make="Toyota", model="Camry")
        _social_post("POST-1", linked_vehicle_ids=["V1"])

        result = ma.get_vehicle_attribution()
        row = next(r for r in result["rows"] if r["make"] == "Toyota" and r["model"] == "Camry")

        assert row["social_mentions"] == 1

    def test_social_post_with_unresolvable_vehicle_id_is_skipped(self):
        _social_post("POST-1", linked_vehicle_ids=["V-MISSING"])

        result = ma.get_vehicle_attribution()

        assert result["rows"] == []

    def test_funded_deal_groups_into_sold_by_make_model(self):
        _vehicle("V1", price=30000, cost=22000, make="Honda", model="Civic")
        _deal("DEAL-1", status="funded", vehicle_id="V1")

        result = ma.get_vehicle_attribution()
        row = next(r for r in result["rows"] if r["make"] == "Honda" and r["model"] == "Civic")

        assert row["funded_deals_count"] == 1
        assert row["gross_revenue"] == 8000.0
        assert row["marketed"] is False

    def test_non_funded_deal_excluded_from_sold_data(self):
        _vehicle("V1", price=30000, cost=22000, make="Honda", model="Civic")
        _deal("DEAL-1", status="contract", vehicle_id="V1")

        result = ma.get_vehicle_attribution()

        assert result["rows"] == []

    def test_deal_with_unresolvable_vehicle_is_skipped(self):
        _deal("DEAL-1", status="funded", vehicle_id="V-MISSING")

        result = ma.get_vehicle_attribution()

        assert result["rows"] == []

    def test_marketed_and_sold_bucketed_correctly(self):
        _vehicle("V1", price=30000, cost=22000, make="Honda", model="Civic")
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "Honda", "model": "Civic"})
        _deal("DEAL-1", status="funded", vehicle_id="V1")

        result = ma.get_vehicle_attribution()

        assert result["marketed_and_sold_count"] == 1
        assert result["marketed_not_sold_count"] == 0
        assert result["sold_not_marketed_count"] == 0

    def test_marketed_not_sold_bucketed_correctly(self):
        _campaign("CAMP-1", campaign_type="inventory_ads", params={"make": "Ford", "model": "F-150"})

        result = ma.get_vehicle_attribution()

        assert result["marketed_and_sold_count"] == 0
        assert result["marketed_not_sold_count"] == 1
        assert result["sold_not_marketed_count"] == 0

    def test_sold_not_marketed_bucketed_correctly(self):
        _vehicle("V1", price=30000, cost=22000, make="Honda", model="Civic")
        _deal("DEAL-1", status="funded", vehicle_id="V1")

        result = ma.get_vehicle_attribution()

        assert result["marketed_and_sold_count"] == 0
        assert result["marketed_not_sold_count"] == 0
        assert result["sold_not_marketed_count"] == 1

    def test_rows_sorted_by_gross_revenue_then_mentions_descending(self):
        _vehicle("V1", price=20000, cost=19000, make="Low", model="Revenue")
        _deal("DEAL-1", status="funded", vehicle_id="V1")

        _vehicle("V2", price=50000, cost=30000, make="High", model="Revenue")
        _deal("DEAL-2", status="funded", vehicle_id="V2")

        result = ma.get_vehicle_attribution()

        assert result["rows"][0]["make"] == "High"
        assert result["rows"][1]["make"] == "Low"

    def test_rows_capped_at_50(self):
        for i in range(55):
            _campaign(f"CAMP-{i}", campaign_type="inventory_ads", params={"make": f"Make{i}", "model": "M"})

        result = ma.get_vehicle_attribution()

        assert len(result["rows"]) == 50

    def test_basis_and_disclaimer_present(self):
        result = ma.get_vehicle_attribution()

        assert result["basis"] == "real_but_not_proven_causal"
        assert "PURL" in result["disclaimer"]

    def test_no_signals_at_all_returns_empty_rows(self):
        result = ma.get_vehicle_attribution()

        assert result["rows"] == []
        assert result["marketed_and_sold_count"] == 0
        assert result["marketed_not_sold_count"] == 0
        assert result["sold_not_marketed_count"] == 0
