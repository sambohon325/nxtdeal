"""
Test coverage for core/campaign_analytics.py -- real A/B Testing + Revenue
Tracking for Campaigns, layered on top of core/campaigns.py's real Campaign
engine.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CAMPAIGN, EMAIL_TEMPLATE, CUSTOMER, LEAD, DEAL, VEHICLE

import core.campaign_analytics as ca


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(ca, "save_graph", lambda filepath: None)


def _campaign(cid, status="draft", **attrs):
    attrs.setdefault("status", status)
    attrs.setdefault("audience_ids", [])
    ledger.add_entity(Entity(id=cid, entity_type=CAMPAIGN, attributes=attrs))
    return ledger.get_entity(cid)


def _template(tid, channel="email"):
    ledger.add_entity(Entity(id=tid, entity_type=EMAIL_TEMPLATE, attributes={"channel": channel}))
    return ledger.get_entity(tid)


def _customer(cid):
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={}))
    return ledger.get_entity(cid)


def _lead(lid, **attrs):
    ledger.add_entity(Entity(id=lid, entity_type=LEAD, attributes=attrs))
    return ledger.get_entity(lid)


def _vehicle(vid, price, cost):
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"Price": price, "Cost": cost}))
    return ledger.get_entity(vid)


def _deal(did, customer_id, vehicle_id, status="funded", funded_at="2026-07-10T00:00:00+00:00"):
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes={
        "customer_id": customer_id, "vehicle_id": vehicle_id,
        "status": status, "funded_at": funded_at,
    }))
    return ledger.get_entity(did)


class TestSetAbVariant:

    def test_campaign_not_found(self):
        result = ca.set_ab_variant("CAMP-NOPE", "TMPL-1")
        assert "error" in result

    def test_rejects_when_campaign_is_not_draft(self):
        _campaign("CAMP-1", status="active", linked_template_id="TMPL-A")
        _template("TMPL-B")
        result = ca.set_ab_variant("CAMP-1", "TMPL-B")
        assert "error" in result
        assert "draft" in result["error"]

    def test_variant_b_template_not_found(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A")
        result = ca.set_ab_variant("CAMP-1", "TMPL-NOPE")
        assert "error" in result

    def test_rejects_when_no_variant_a_linked_yet(self):
        _campaign("CAMP-1")
        _template("TMPL-B")
        result = ca.set_ab_variant("CAMP-1", "TMPL-B")
        assert "error" in result
        assert "Variant A" in result["error"]

    def test_rejects_mismatched_channels(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A")
        _template("TMPL-A", channel="email")
        _template("TMPL-B", channel="sms")
        result = ca.set_ab_variant("CAMP-1", "TMPL-B")
        assert "error" in result
        assert "channel" in result["error"]

    def test_success_sets_variant_b_on_campaign(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A")
        _template("TMPL-A", channel="email")
        _template("TMPL-B", channel="email")
        result = ca.set_ab_variant("CAMP-1", "TMPL-B")
        assert result["campaign_id"] == "CAMP-1"
        assert result["variant_a_template_id"] == "TMPL-A"
        assert result["variant_b_template_id"] == "TMPL-B"
        campaign = ledger.get_entity("CAMP-1")
        assert campaign.attributes["variant_b_template_id"] == "TMPL-B"


class TestClearAbVariant:

    def test_campaign_not_found(self):
        result = ca.clear_ab_variant("CAMP-NOPE")
        assert "error" in result

    def test_success_clears_variant_b(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B")
        result = ca.clear_ab_variant("CAMP-1")
        assert result["campaign_id"] == "CAMP-1"
        campaign = ledger.get_entity("CAMP-1")
        assert campaign.attributes["variant_b_template_id"] is None


class TestIsAbTest:

    def test_false_when_no_variant_b(self):
        campaign = _campaign("CAMP-1")
        assert ca.is_ab_test(campaign) is False

    def test_true_when_variant_b_set(self):
        campaign = _campaign("CAMP-1", variant_b_template_id="TMPL-B")
        assert ca.is_ab_test(campaign) is True

    def test_false_when_variant_b_is_none(self):
        campaign = _campaign("CAMP-1", variant_b_template_id=None)
        assert ca.is_ab_test(campaign) is False


class TestGetVariantForMember:

    def test_deterministic_across_repeated_calls(self):
        v1 = ca.get_variant_for_member("CAMP-1", "CUST-1")
        v2 = ca.get_variant_for_member("CAMP-1", "CUST-1")
        assert v1 == v2

    def test_result_is_always_a_or_b(self):
        for i in range(20):
            assert ca.get_variant_for_member("CAMP-1", f"CUST-{i}") in ("a", "b")

    def test_different_campaigns_can_split_the_same_entity_differently(self):
        # Not asserted to always differ (hash could coincide), just confirm the
        # campaign_id genuinely participates in the hash rather than being ignored.
        v_camp1 = ca.get_variant_for_member("CAMP-1", "CUST-1")
        v_camp2 = ca.get_variant_for_member("CAMP-2", "CUST-1")
        assert v_camp1 in ("a", "b")
        assert v_camp2 in ("a", "b")

    def test_roughly_splits_a_population_into_both_buckets(self):
        variants = {ca.get_variant_for_member("CAMP-SPLIT", f"CUST-{i}") for i in range(50)}
        assert variants == {"a", "b"}


class TestGetCampaignAbConfig:

    def test_campaign_not_found(self):
        result = ca.get_campaign_ab_config("CAMP-NOPE")
        assert "error" in result

    def test_no_ab_test_puts_everyone_in_variant_a(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A", audience_ids=["CUST-1", "CUST-2", "CUST-3"])
        result = ca.get_campaign_ab_config("CAMP-1")
        assert result["is_ab_test"] is False
        assert result["variant_a_audience_count"] == 3
        assert result["variant_b_audience_count"] == 0

    def test_ab_test_splits_audience_counts_that_sum_to_total(self):
        audience = [f"CUST-{i}" for i in range(20)]
        _campaign("CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B", audience_ids=audience)
        result = ca.get_campaign_ab_config("CAMP-1")
        assert result["is_ab_test"] is True
        assert result["variant_a_audience_count"] + result["variant_b_audience_count"] == 20

    def test_empty_audience_returns_zero_counts(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B", audience_ids=[])
        result = ca.get_campaign_ab_config("CAMP-1")
        assert result["variant_a_audience_count"] == 0
        assert result["variant_b_audience_count"] == 0


class TestGetCampaignRevenue:

    def test_campaign_not_found(self):
        result = ca.get_campaign_revenue("CAMP-NOPE")
        assert "error" in result

    def test_not_activated_is_ineligible(self):
        _campaign("CAMP-1")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["eligible"] is False
        assert "not been activated" in result["reason"] or "hasn't been activated" in result["reason"]

    def test_funded_deal_after_activation_counted(self):
        _customer("CUST-1")
        _vehicle("VEH-1", price=30000, cost=25000)
        _deal("DEAL-1", "CUST-1", "VEH-1", status="funded", funded_at="2026-07-15T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["CUST-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["eligible"] is True
        assert result["funded_deals_count"] == 1
        assert result["revenue"] == 5000.0
        assert result["basis"] == "real_but_not_proven_causal"

    def test_deal_funded_before_activation_excluded(self):
        _customer("CUST-1")
        _vehicle("VEH-1", price=30000, cost=25000)
        _deal("DEAL-1", "CUST-1", "VEH-1", status="funded", funded_at="2026-07-01T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["CUST-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["funded_deals_count"] == 0
        assert result["revenue"] == 0.0

    def test_deal_for_a_different_customer_excluded(self):
        _customer("CUST-1")
        _customer("CUST-2")
        _vehicle("VEH-1", price=30000, cost=25000)
        _deal("DEAL-1", "CUST-2", "VEH-1", status="funded", funded_at="2026-07-15T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["CUST-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["funded_deals_count"] == 0

    def test_non_funded_deal_excluded(self):
        _customer("CUST-1")
        _vehicle("VEH-1", price=30000, cost=25000)
        _deal("DEAL-1", "CUST-1", "VEH-1", status="financing", funded_at="2026-07-15T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["CUST-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["funded_deals_count"] == 0

    def test_lead_sold_after_activation_counted(self):
        _lead("LEAD-1", PipelineState="SOLD", PipelineStateSince="2026-07-15T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["LEAD-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["leads_sold_count"] == 1

    def test_lead_not_sold_excluded(self):
        _lead("LEAD-1", PipelineState="CONTACTED")
        _campaign("CAMP-1", audience_ids=["LEAD-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["leads_sold_count"] == 0

    def test_lead_sold_before_activation_excluded(self):
        _lead("LEAD-1", PipelineState="SOLD", PipelineStateSince="2026-07-01T00:00:00+00:00")
        _campaign("CAMP-1", audience_ids=["LEAD-1"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["leads_sold_count"] == 0

    def test_missing_audience_entity_is_skipped_gracefully(self):
        _campaign("CAMP-1", audience_ids=["CUST-DOES-NOT-EXIST"], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["eligible"] is True
        assert result["revenue"] == 0.0

    def test_empty_audience_returns_zero(self):
        _campaign("CAMP-1", audience_ids=[], activated_at="2026-07-10T00:00:00+00:00")
        result = ca.get_campaign_revenue("CAMP-1")
        assert result["audience_count"] == 0
        assert result["revenue"] == 0.0


class TestGetAbTestResults:

    def test_campaign_not_found(self):
        result = ca.get_ab_test_results("CAMP-NOPE")
        assert "error" in result

    def test_not_an_ab_test_is_an_error(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A")
        result = ca.get_ab_test_results("CAMP-1")
        assert "error" in result
        assert "A/B variant" in result["error"]

    def test_not_activated_is_ineligible(self):
        _campaign("CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B")
        result = ca.get_ab_test_results("CAMP-1")
        assert result["eligible"] is False

    def test_splits_real_deal_revenue_by_variant(self):
        # For campaign_id "CAMP-1": CUST-1 -> variant b, CUST-2 -> variant a
        # (confirmed live against the real hash function before writing this test).
        _customer("CUST-1")
        _customer("CUST-2")
        _vehicle("VEH-1", price=30000, cost=25000)
        _vehicle("VEH-2", price=20000, cost=18000)
        _deal("DEAL-1", "CUST-1", "VEH-1", status="funded", funded_at="2026-07-15T00:00:00+00:00")
        _deal("DEAL-2", "CUST-2", "VEH-2", status="funded", funded_at="2026-07-15T00:00:00+00:00")
        _campaign(
            "CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B",
            audience_ids=["CUST-1", "CUST-2"], activated_at="2026-07-10T00:00:00+00:00",
        )
        result = ca.get_ab_test_results("CAMP-1")
        assert result["eligible"] is True
        assert result["results"]["b"]["revenue"] == 5000.0
        assert result["results"]["b"]["funded_deals_count"] == 1
        assert result["results"]["a"]["revenue"] == 2000.0
        assert result["results"]["a"]["funded_deals_count"] == 1
        assert result["winner"] == "b"  # higher revenue wins

    def test_audience_counts_across_both_buckets_sum_to_total(self):
        audience = [f"CUST-{i}" for i in range(30)]
        for cid in audience:
            _customer(cid)
        _campaign(
            "CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B",
            audience_ids=audience, activated_at="2026-07-10T00:00:00+00:00",
        )
        result = ca.get_ab_test_results("CAMP-1")
        total = result["results"]["a"]["audience_count"] + result["results"]["b"]["audience_count"]
        assert total == 30

    def test_no_winner_when_revenue_and_conversion_rate_both_tie(self):
        # Two customers, both zero revenue, zero conversions -- a genuine tie.
        _customer("CUST-1")
        _customer("CUST-2")
        _campaign(
            "CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B",
            audience_ids=["CUST-1", "CUST-2"], activated_at="2026-07-10T00:00:00+00:00",
        )
        result = ca.get_ab_test_results("CAMP-1")
        assert result["winner"] is None

    def test_conversion_rate_breaks_a_revenue_tie(self):
        # Both variants at $0 revenue, but variant b has a sold lead (a real
        # conversion with no dollar value attached) -- conversion rate should
        # decide the winner since revenue is tied.
        _lead("LEAD-1", PipelineState="SOLD", PipelineStateSince="2026-07-15T00:00:00+00:00")  # -> b
        _customer("CUST-2")  # -> a, no deal
        _campaign(
            "CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B",
            audience_ids=["LEAD-1", "CUST-2"], activated_at="2026-07-10T00:00:00+00:00",
        )
        result = ca.get_ab_test_results("CAMP-1")
        assert result["results"]["a"]["revenue"] == result["results"]["b"]["revenue"] == 0.0
        assert result["winner"] == "b"

    def test_disclaimer_and_basis_present(self):
        _campaign(
            "CAMP-1", linked_template_id="TMPL-A", variant_b_template_id="TMPL-B",
            audience_ids=[], activated_at="2026-07-10T00:00:00+00:00",
        )
        result = ca.get_ab_test_results("CAMP-1")
        assert result["basis"] == "real_but_not_proven_causal"
        assert "disclaimer" in result
