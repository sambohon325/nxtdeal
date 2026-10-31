"""
Phase 4 (2026-07-25): F&I credit pull routed through the credit_bureau seam (real pull when
a bureau is connected, honest simulated fallback otherwise) + personalized F&I menu
recommendation. Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE
from core import integrations_registry as ir
from core import credit_app
from core import fi_products
from core import deals


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    ir._ADAPTERS.clear()
    yield
    ledger.reset()
    ir._ADAPTERS.clear()


def _customer(cid="CUST-1", score=None):
    a = {"FirstName": "Jane", "LastName": "Doe", "monthly_income": 5000}
    if score is not None:
        a["CreditScore"] = score
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes=a))
    return cid


def _submit_app(cid):
    app = credit_app.create_credit_application(cid, "EMP-1")
    credit_app.update_applicant(app.id, {"first_name": "Jane", "last_name": "Doe", "monthly_income": 5000})
    credit_app.give_fcra_consent(app.id)
    return credit_app.submit_credit_application(app.id)


# --- credit pull through the seam ---

def test_credit_decision_simulated_when_no_bureau():
    cid = _customer(score=700)
    app = _submit_app(cid)
    decision = app.attributes["decision"]
    assert decision["pull_mode"] == "simulated"
    assert decision["decision"] == "approved"  # 700 -> Good
    assert decision["simulated_score"] == 700


def test_credit_decision_blocks_unreviewed_live_bureau():
    # No CreditScore on file -> without a bureau this would be "conditional/Unknown".
    cid = _customer(score=None)
    ir.register_adapter("credit_bureau", lambda applicant: pytest.fail("Unreviewed credit pull"))
    app = _submit_app(cid)
    assert app["blocked"] is True


def test_pull_credit_dispatcher_simulated():
    r = ir.pull_credit({"customer_id": "CUST-1"})
    assert r["simulated"] is True and r["score"] is None


# --- personalized F&I recommendation ---

def _deal_with_vehicle(year, mileage, term=72, down=0, sale=30000, score=700):
    _customer("CUST-1", score=score)
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"Year": year, "Mileage": mileage, "Make": "X", "Model": "Y"}))
    deal = deals.create_deal("CUST-1", "VEH-1", "EMP-1")
    deals.add_scenario(deal.id, "Base", sale, down, term)
    return deal


def test_recommend_flags_vsc_for_older_high_mileage():
    old_year = datetime.now(timezone.utc).year - 6
    deal = _deal_with_vehicle(old_year, 80000, term=72)
    rec = fi_products.recommend_fi_products(deal.id)
    vsc = next(r for r in rec["recommendations"] if r["product_key"] == "vsc")
    assert vsc["recommended"] is True
    assert vsc["fit_score"] >= 60
    assert any("warranty" in reason.lower() or "mile" in reason.lower() for reason in vsc["reasons"])


def test_recommend_flags_gap_for_low_down_long_term():
    new_year = datetime.now(timezone.utc).year
    deal = _deal_with_vehicle(new_year, 5, term=84, down=0, sale=40000)
    rec = fi_products.recommend_fi_products(deal.id)
    gap = next(r for r in rec["recommendations"] if r["product_key"] == "gap")
    assert gap["recommended"] is True
    assert "gap" in rec["recommended_keys"]


def test_recommend_prepaid_maintenance_for_new_vehicle():
    new_year = datetime.now(timezone.utc).year
    deal = _deal_with_vehicle(new_year, 10, term=60)
    rec = fi_products.recommend_fi_products(deal.id)
    pm = next(r for r in rec["recommendations"] if r["product_key"] == "prepaid_maintenance")
    assert any("today's price" in reason for reason in pm["reasons"])


def test_recommend_sorted_and_marks_on_menu():
    old_year = datetime.now(timezone.utc).year - 6
    deal = _deal_with_vehicle(old_year, 80000, term=72)
    # Move deal to financing and present vsc so it shows already_on_menu.
    fi_products.present_fi_products  # ensure importable
    deal.attributes["status"] = "financing"
    fi_products.present_fi_products(deal.id, ["vsc"], "EMP-1")
    rec = fi_products.recommend_fi_products(deal.id)
    scores = [r["fit_score"] for r in rec["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    vsc = next(r for r in rec["recommendations"] if r["product_key"] == "vsc")
    assert vsc["already_on_menu"] is True
    assert "vsc" not in rec["recommended_keys"]  # excluded because already on menu


def test_recommend_deal_not_found():
    assert "error" in fi_products.recommend_fi_products("DEAL-NOPE")
