"""
Tests for the AI Negotiation Engine (core/negotiation_engine.py + _api.py) -- 2026-07-24,
Digital Retail DR-3. Run from backend/ with `pytest`.

Covers: dealer rules (defaults, set, validation); a deal session seeded from the deal;
evaluate/apply an in-bounds offer (approved, terms move); an out-of-bounds offer auto-escalates
(terms frozen) and a manager approve/deny resolves it; accept writes the agreed terms back as a
real deal scenario; the execution-mode gate (a customer can't drive negotiation until the dealer
enables it); payment-variance and expiry; and the API role gates.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, DEAL_SESSION
from core.permissions import ADMIN, SALES, MARKETING
from core.deals import create_deal, get_deal

from core import negotiation_engine as neg
from core import negotiation_engine_api as neg_api
from core import execution_modes as xm


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _seed_deal(cost=25000, price=30000, acv=5000, credit=720):
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER,
                             attributes={"Name": "Pat Q", "CreditScore": credit}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE,
                             attributes={"Price": price, "Cost": cost, "Make": "Ford", "Model": "F-150"}))
    deal = create_deal("CUST-1", "VEH-1", "EMP-1", trade_in={"acv": acv})
    return deal.id


def _session(**kw):
    return neg.start_session(_seed_deal(**kw), "EMP-1")["session"]


# ---------------------------------------------------------------------------- rules

def test_rules_defaults_and_set():
    r = neg.get_rules()
    assert r["min_front_gross"] == 500 and r["min_total_gross"] == 1500
    assert r["default_session_ttl_hours"] == 48
    out = neg.set_rules({"min_total_gross": 2000, "max_discount": 2500}, "EMP-1")
    assert out["rules"]["min_total_gross"] == 2000 and out["rules"]["max_discount"] == 2500


def test_rules_validation():
    assert "error" in neg.set_rules({"min_front_gross": -1}, "EMP-1")
    assert "error" in neg.set_rules({"nope": 1}, "EMP-1")
    assert "error" in neg.set_rules({"default_session_ttl_hours": 0}, "EMP-1")


# -------------------------------------------------------------------------- session

def test_start_session_seeds_and_expires():
    s = _session()
    assert s["status"] == "active"
    assert s["expires_at"] and s["ttl_hours"] == 48
    assert s["current_terms"]["trade_allowance"] == 5000  # seeded from trade ACV


def test_in_bounds_offer_is_approved_and_moves_terms():
    s = _session()
    ev = neg.evaluate_offer(s["id"], {"selling_price": 29000, "down_payment": 3000, "term_months": 60})
    assert ev["within_authority"] is True and ev["decision"] == "ai_approved"
    assert ev["metrics"]["front_gross"] == 4000

    applied = neg.apply_offer(s["id"], {"selling_price": 29000, "down_payment": 3000}, "EMP-1")
    assert applied["within_authority"] is True
    assert neg.get_session(s["id"])["current_terms"]["selling_price"] == 29000


def test_out_of_bounds_offer_escalates_and_freezes_terms():
    s = _session()
    # discount 3500 > 3000 max -> violation
    res = neg.apply_offer(s["id"], {"selling_price": 26500}, "EMP-1")
    assert res["within_authority"] is False and res["decision"] == "needs_manager_approval"
    assert res["violations"]
    got = neg.get_session(s["id"])
    assert got["status"] == "escalated"
    assert got["escalation"]["resolved"] is False
    # terms NOT changed by the escalated offer
    assert got["current_terms"]["selling_price"] != 26500
    # cannot apply another offer while escalated
    assert "error" in neg.apply_offer(s["id"], {"selling_price": 29000}, "EMP-1")


def test_manager_approve_applies_proposed_terms():
    s = _session()
    neg.apply_offer(s["id"], {"selling_price": 26500}, "EMP-1")  # escalates
    out = neg.resolve_escalation(s["id"], "approve", "MGR-1", note="ok deal")
    assert out["session"]["status"] == "active"
    assert out["session"]["current_terms"]["selling_price"] == 26500
    assert out["session"]["escalation"]["decision"] == "approve"


def test_manager_deny_leaves_terms_unchanged():
    s = _session()
    before = neg.get_session(s["id"])["current_terms"]["selling_price"]
    neg.apply_offer(s["id"], {"selling_price": 26500}, "EMP-1")
    out = neg.resolve_escalation(s["id"], "deny", "MGR-1")
    assert out["session"]["status"] == "active"
    assert out["session"]["current_terms"]["selling_price"] == before


def test_accept_writes_back_a_real_deal_scenario():
    s = _session()
    neg.apply_offer(s["id"], {"selling_price": 29000, "down_payment": 3000}, "EMP-1")
    out = neg.accept_session(s["id"], "EMP-1")
    assert out["session"]["status"] == "accepted"
    assert out["session"]["final_terms"]["selling_price"] == 29000
    assert out["accepted_scenario_id"] is not None
    # the scenario is real on the deal
    deal = get_deal(s["deal_id"])
    assert any(sc["id"] == out["accepted_scenario_id"] for sc in deal.attributes["scenarios"])


# ------------------------------------------------------------ execution-mode gate

def test_customer_cannot_negotiate_until_mode_allows():
    s = _session()
    # default negotiation mode = human -> a customer actor is blocked
    blocked = neg.apply_offer(s["id"], {"selling_price": 29000}, "cust-token", actor_kind="customer")
    assert "error" in blocked and "Human mode" in blocked["error"]
    # open negotiation to customers
    xm.set_execution_mode("negotiation", "customer", "EMP-1")
    ok = neg.apply_offer(s["id"], {"selling_price": 29000, "down_payment": 3000}, "cust-token",
                         actor_kind="customer")
    assert ok["within_authority"] is True


# ------------------------------------------------------------ variance + expiry

def test_payment_variance_violation():
    # a low target payment the in-bounds price can't hit -> variance violation escalates
    deal_id = _seed_deal()
    s = neg.start_session(deal_id, "EMP-1", target_payment=200)["session"]
    res = neg.apply_offer(s["id"], {"selling_price": 29000, "down_payment": 1000, "term_months": 60}, "EMP-1")
    assert res["within_authority"] is False
    assert any("payment variance" in v for v in res["violations"])


def test_expired_session_rejects_offers():
    s = _session()
    entity = ledger.get_entity(s["id"])
    entity.attributes["expires_at"] = "2000-01-01T00:00:00+00:00"  # force past
    assert neg.get_session(s["id"])["status"] == "expired"
    assert "error" in neg.apply_offer(s["id"], {"selling_price": 29000}, "EMP-1")


# ------------------------------------------------------------------- summary/api

def test_summary_counts_open_escalations():
    s = _session()
    neg.apply_offer(s["id"], {"selling_price": 26500}, "EMP-1")
    summ = neg.negotiation_summary()
    assert summ["total_sessions"] == 1
    assert summ["by_status"]["escalated"] == 1
    assert summ["open_escalations"] == 1


def test_api_role_gates():
    deal_id = _seed_deal()
    # rules set is ADMIN-only
    assert "error" in neg_api.set_negotiation_rules_api(SALES, "EMP-1", {"min_front_gross": 100})
    assert neg_api.set_negotiation_rules_api(ADMIN, "EMP-1", {"min_front_gross": 100})["rules"]["min_front_gross"] == 100
    # start is desk-roles only (MARKETING is not a desk role)
    assert "error" in neg_api.start_session_api(MARKETING, "EMP-9", deal_id)
    started = neg_api.start_session_api(SALES, "EMP-1", deal_id)
    sid = started["session"]["id"]
    # escalate, then only a manager can resolve
    neg_api.apply_offer_api(SALES, "EMP-1", sid, {"selling_price": 26500})
    assert "error" in neg_api.resolve_escalation_api(SALES, "EMP-1", sid, "approve")  # SALES not manager
    assert neg_api.resolve_escalation_api(ADMIN, "MGR-1", sid, "approve")["session"]["status"] == "active"
