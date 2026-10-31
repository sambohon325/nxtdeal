"""
Phase 1 (2026-07-25): Buy-Propensity Score (0-100) + third-party enrichment seam. Composes
engagement + equity + maturity + service-recency into an explainable 0-100 score, ranks
prospects, drafts outreach, and routes enrichment through the provider seam (simulated with
no provider). Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, LEAD, SERVICE_RECORD
from core import buy_propensity as bp
from core import buy_propensity_api as bp_api
from core import data_enrichment
from core import integrations_registry as ir


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    ir._ADAPTERS.clear()
    yield
    ledger.reset()
    ir._ADAPTERS.clear()


def _customer(cid="CUST-1", **attrs):
    a = {"FirstName": "Jane", "LastName": "Doe"}
    a.update(attrs)
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes=a))
    return cid


def _service(cid, days_ago):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    sid = f"SRV-{cid}-{days_ago}"
    ledger.add_entity(Entity(id=sid, entity_type=SERVICE_RECORD, attributes={"ServiceDate": d}))
    ledger.add_relationship(Relationship(source_id=cid, target_id=sid, relationship_type="AUTHORIZED"))


# --- scoring ---

def test_empty_customer_scores_low():
    _customer("CUST-1")
    r = bp.compute_propensity("CUST-1")
    assert r["score"] == 0 and r["tier"] == "cool"


def test_positive_equity_raises_score():
    _customer("CUST-1", estimated_value=25000, estimated_payoff=15000)  # $10k equity -> full 25
    r = bp.compute_propensity("CUST-1")
    equity = next(f for f in r["factors"] if f["label"] == "Positive equity")
    assert equity["points"] == 25
    assert r["score"] >= 25


def test_lease_maturity_soon_raises_score():
    soon = (date.today() + timedelta(days=10)).isoformat()
    _customer("CUST-1", lease_maturity_date=soon)
    r = bp.compute_propensity("CUST-1")
    mat = next(f for f in r["factors"] if f["label"] == "Loan/lease maturing")
    assert mat["points"] > 0
    # 10 days out is near the top of the 0-90 window.
    assert mat["points"] >= 15


def test_recent_service_visit_raises_score():
    _customer("CUST-1")
    _service("CUST-1", days_ago=15)  # ~0.5 months
    r = bp.compute_propensity("CUST-1")
    svc = next(f for f in r["factors"] if f["label"] == "Recent service visit")
    assert svc["points"] > 0


def test_score_is_capped_at_100():
    soon = (date.today() + timedelta(days=1)).isoformat()
    _customer("CUST-1", estimated_value=100000, estimated_payoff=1000, lease_maturity_date=soon)
    _service("CUST-1", days_ago=1)
    r = bp.compute_propensity("CUST-1")
    assert r["score"] <= 100


def test_tiers_and_recommended_action():
    soon = (date.today() + timedelta(days=5)).isoformat()
    _customer("CUST-1", estimated_value=30000, estimated_payoff=10000, lease_maturity_date=soon)
    r = bp.compute_propensity("CUST-1")
    assert r["tier"] in ("hot", "warm")
    assert "equity" in r["recommended_action"].lower() or "term" in r["recommended_action"].lower()


def test_rejects_non_customer_lead():
    ledger.add_entity(Entity(id="VEH-1", entity_type="Vehicle", attributes={}))
    assert "error" in bp.compute_propensity("VEH-1")


# --- ranking ---

def test_rank_orders_by_score_desc():
    _customer("CUST-A")  # 0
    _customer("CUST-B", estimated_value=30000, estimated_payoff=10000)  # equity
    result = bp.rank(segment="customers")
    assert result["count"] == 2
    assert result["ranked"][0]["entity_id"] == "CUST-B"
    assert result["ranked"][0]["score"] >= result["ranked"][1]["score"]


def test_rank_leads_segment_excludes_customers():
    _customer("CUST-1", estimated_value=30000, estimated_payoff=10000)
    ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={"PipelineState": "NEW", "FirstName": "Al"}))
    leads = bp.rank(segment="leads")
    assert all(r["entity_type"] == LEAD for r in leads["ranked"])
    assert leads["count"] == 1


# --- outreach ---

def test_draft_outreach_keys_off_top_factor():
    soon = (date.today() + timedelta(days=5)).isoformat()
    _customer("CUST-1", FirstName="Sam", lease_maturity_date=soon)
    draft = bp.draft_outreach("CUST-1", channel="email")
    assert "Sam" in draft["body"]
    assert draft["subject"]
    assert "Loan/lease maturing" in draft["based_on"]


def test_draft_outreach_sms_has_no_subject():
    _customer("CUST-1", estimated_value=30000, estimated_payoff=10000)
    draft = bp.draft_outreach("CUST-1", channel="sms")
    assert draft["subject"] is None and draft["body"]


# --- enrichment seam ---

def test_enrichment_simulated_appends_nothing():
    _customer("CUST-1", Email="j@d.com")
    r = data_enrichment.enrich_customer("CUST-1")
    assert r["mode"] == "simulated" and r["appended_count"] == 0
    stored = data_enrichment.get_enrichment("CUST-1")
    assert stored["simulated"] is True and stored["appended"] == {}


def test_enrichment_live_appends_provider_data():
    ir.register_adapter("enrichment", lambda record: {"provider": "acxiom", "appended": {"household_income": "100k-150k", "in_market": True}})
    _customer("CUST-1")
    r = data_enrichment.enrich_customer("CUST-1")
    assert r["mode"] == "live" and r["appended_count"] == 2
    cust = ledger.get_entity("CUST-1")
    assert cust.attributes["enriched_household_income"] == "100k-150k"


def test_enrichment_capability_in_seam():
    assert "enrichment" in ir.CAPABILITIES
    assert ir.enrich_record({"customer_id": "X"})["simulated"] is True


# --- API role gating ---

def test_api_enrich_requires_write_role():
    from core.permissions import ADMIN, SALES
    _customer("CUST-1")
    assert "error" in bp_api.enrich_customer_api(SALES, "EMP-1", "CUST-1")
    assert "customer_id" in bp_api.enrich_customer_api(ADMIN, "EMP-1", "CUST-1")
    # But any role can view a score.
    assert "score" in bp_api.compute_propensity_api(SALES, "CUST-1")
