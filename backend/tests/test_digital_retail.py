"""
Tests for NXTDeal Digital Retail self-service orchestration (core/digital_retail.py) --
2026-07-24, DR-4. Run from backend/ with `pytest`.

Covers: the two gates on every step (the Verify tier must unlock the capability AND the
dealer must have opened the workflow to the customer); the full self-service happy path
(start deal -> trade -> negotiate/accept -> apply credit [auto-promotes to Credit Verified] ->
choose financing -> select F&I [rolled into the payment] -> sign); ownership enforcement; and
the F&I-into-payment gap fix.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE

from core import dealeros_verify as verify
from core import execution_modes as xm
from core import digital_retail as dr


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


_WORKFLOWS = ("desking", "trade", "negotiation", "credit", "fi", "contracting")


def _open_all_to_customer():
    for wf in _WORKFLOWS:
        xm.set_execution_mode(wf, "hybrid", "EMP-1")


def _seed_vehicle(vid="VEH-1", cost=25000, price=30000):
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE,
                             attributes={"Price": price, "Cost": cost, "Make": "Ford", "Model": "F-150"}))
    return vid


def _token_at(tier):
    """Start a Verify session and climb it to the requested tier; return its token."""
    started = verify.start_verification(email="pat@example.com", phone="555-000-1234")
    vid = started["verification"]["id"]
    token = ledger.get_entity(vid).attributes["session_token"]
    if tier == "anonymous":
        return token
    verify.confirm_email_code(vid, verify.request_email_code(vid)["dev_code"])
    verify.confirm_sms_code(vid, verify.request_sms_code(vid)["dev_code"])
    if tier == "verified_human":
        return token
    verify.submit_identity(vid, "D1234567")
    return token  # identity_verified


# ------------------------------------------------------------------------- the gates

def test_execution_mode_blocks_even_a_verified_customer():
    _seed_vehicle()
    token = _token_at("identity_verified")
    # desking still in default Human mode -> blocked despite Identity Verified
    res = dr.start_deal(token, "VEH-1")
    assert "error" in res and "Human mode" in res["error"]
    xm.set_execution_mode("desking", "customer", "EMP-1")
    assert "deal" in dr.start_deal(token, "VEH-1")


def test_verify_tier_blocks_underverified_customer():
    _seed_vehicle()
    _open_all_to_customer()
    token = _token_at("verified_human")  # not Identity Verified
    res = dr.start_deal(token, "VEH-1")
    assert "error" in res and "Identity Verified" in res["error"]


def test_bad_token_rejected():
    _seed_vehicle()
    _open_all_to_customer()
    assert "error" in dr.start_deal("not-a-token", "VEH-1")


# ------------------------------------------------------------------- full happy path

def test_full_self_service_journey():
    _seed_vehicle()
    _open_all_to_customer()
    token = _token_at("identity_verified")

    # 1. start a deal (materializes a Customer + Deal)
    deal = dr.start_deal(token, "VEH-1")["deal"]
    deal_id = deal["id"]
    assert deal["status"] == "desking"

    # 2. submit a trade
    traded = dr.submit_trade(token, deal_id, {"vin": "1FTFW1E50MFA00001", "mileage": 40000, "condition": "good"})
    assert traded["deal"]["trade_in"]["mileage"] == 40000

    # 3. negotiate an in-bounds offer and accept
    sess = dr.start_negotiation(token, deal_id)["session"]
    offered = dr.make_offer(token, sess["id"], {"selling_price": 29000, "down_payment": 3000})
    assert offered["within_authority"] is True
    acc = dr.accept_negotiation(token, sess["id"])
    assert acc["session"]["status"] == "accepted"

    # 4. apply for credit -> decisioned -> auto-promoted to Credit Verified
    credit = dr.apply_credit(token, deal_id, {"employment_status": "employed"}, monthly_income=5000)
    assert credit["decision"]["decision"] in ("approved", "conditional", "declined")
    assert credit["verification"]["tier"] == "credit_verified"

    # 5. choose financing (in-house/BHPH self-approve) -> deal in financing
    fin = dr.choose_financing(token, deal_id)
    assert fin["deal"]["status"] == "financing"
    assert fin["deal"]["financing_status"] == "approved"

    # 6. select F&I -> accepted price rolls into the payment
    fi = dr.select_fi(token, deal_id, "vsc", "accepted")
    pay = fi["payment"]
    assert pay["fi_accepted_price"] > 0
    assert pay["monthly_payment_with_fi"] > pay["base_monthly_payment"]

    # 7. sign
    signed = dr.sign(token, deal_id, "Customer")
    assert signed["fully_signed"] is True

    # deal room reflects the finished journey
    room = dr.get_deal_room(token, deal_id)
    assert room["verification"]["tier"] == "credit_verified"
    assert room["payment"]["monthly_payment_with_fi"] > 0


def test_customer_cannot_touch_another_customers_deal():
    _seed_vehicle()
    _open_all_to_customer()
    owner = _token_at("identity_verified")
    deal_id = dr.start_deal(owner, "VEH-1")["deal"]["id"]

    intruder = _token_at("identity_verified")
    assert "error" in dr.submit_trade(intruder, deal_id, {"mileage": 1})
    assert "error" in dr.get_deal_room(intruder, deal_id)


def test_estimate_payment_with_fi_rolls_in_accepted_products():
    _seed_vehicle()
    _open_all_to_customer()
    token = _token_at("identity_verified")
    deal_id = dr.start_deal(token, "VEH-1")["deal"]["id"]
    sess = dr.start_negotiation(token, deal_id)["session"]
    dr.make_offer(token, sess["id"], {"selling_price": 29000, "down_payment": 3000})
    dr.accept_negotiation(token, sess["id"])
    dr.apply_credit(token, deal_id, {"employment_status": "employed"}, monthly_income=5000)
    dr.choose_financing(token, deal_id)

    before = dr.estimate_payment_with_fi(deal_id)
    assert before["fi_accepted_price"] == 0
    dr.select_fi(token, deal_id, "gap", "accepted")
    after = dr.estimate_payment_with_fi(deal_id)
    assert after["fi_accepted_price"] > 0
    assert after["amount_financed_with_fi"] > before["amount_financed_with_fi"]
