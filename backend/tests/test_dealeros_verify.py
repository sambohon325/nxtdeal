"""
Tests for NXTDeal Verify (core/dealeros_verify.py + core/dealeros_verify_api.py) --
2026-07-24, the Digital Retail identity-tier gate. Run from backend/ with `pytest`.

Covers: the trust ladder (anonymous -> verified_human -> identity_verified -> credit_verified)
and its cumulative capability unlocks; email/SMS one-time codes (request, wrong code, correct
code, both-channels-promote); identity requires Verified Human first (simulated match); credit
requires Identity Verified first and a decisioned credit application; the require_capability
gate other modules use (incl. fail-closed on unknown capability); changing a verified contact
resets that channel and recomputes the tier down; and the public token-driven customer flow.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import SALES

from core import dealeros_verify as verify
from core import dealeros_verify_api as verify_api
from core.credit_app import (
    create_credit_application,
    update_applicant,
    give_fcra_consent,
    submit_credit_application,
)


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


def _new(email="pat@example.com", phone="555-123-9876"):
    return verify.start_verification(email=email, phone=phone)["verification"]


def _to_verified_human(vid):
    verify.confirm_email_code(vid, verify.request_email_code(vid)["dev_code"])
    verify.confirm_sms_code(vid, verify.request_sms_code(vid)["dev_code"])


def _decisioned_credit_app():
    ledger.add_entity(Entity(id="CUST-9", entity_type=CUSTOMER,
                             attributes={"Name": "Pat Q", "CreditScore": 720}))
    app = create_credit_application("CUST-9", "EMP-1")
    update_applicant(app.id, applicant_patch={"employment_status": "employed", "monthly_income": 5000})
    give_fcra_consent(app.id)
    submit_credit_application(app.id)
    return app.id


# ----------------------------------------------------------------------------- tiers

def test_start_is_anonymous_with_browse_only():
    v = _new()
    assert v["tier"] == "anonymous"
    assert set(v["capabilities"]) == {"browse_inventory", "vehicle_research", "faq"}
    assert verify.can(v["id"], "browse_inventory") is True
    assert verify.can(v["id"], "trade_estimate") is False


def test_email_and_sms_promote_to_verified_human():
    v = _new()
    vid = v["id"]
    # one channel alone is NOT enough
    verify.confirm_email_code(vid, verify.request_email_code(vid)["dev_code"])
    assert verify.get_verification(vid)["tier"] == "anonymous"
    verify.confirm_sms_code(vid, verify.request_sms_code(vid)["dev_code"])
    got = verify.get_verification(vid)
    assert got["tier"] == "verified_human"
    assert "trade_estimate" in got["capabilities"] and "pricing_request" in got["capabilities"]
    assert "negotiate" not in got["capabilities"]


def test_wrong_code_is_rejected_then_correct_accepted():
    vid = _new()["id"]
    issued = verify.request_email_code(vid)["dev_code"]
    bad = verify.confirm_email_code(vid, "000000" if issued != "000000" else "111111")
    assert "error" in bad
    assert verify.get_verification(vid)["email_verified"] is False
    ok = verify.confirm_email_code(vid, issued)
    assert ok["verification"]["email_verified"] is True


def test_request_code_needs_contact_on_file():
    vid = verify.start_verification(email=None, phone=None)["verification"]["id"]
    assert "error" in verify.request_email_code(vid)
    verify.set_contact(vid, email="new@example.com")
    assert verify.request_email_code(vid)["dev_code"]


# -------------------------------------------------------------------------- identity

def test_identity_requires_verified_human_first():
    vid = _new()["id"]
    assert "error" in verify.submit_identity(vid, "D1234567")  # still anonymous
    _to_verified_human(vid)
    res = verify.submit_identity(vid, "D1234567")
    assert res["verification"]["tier"] == "identity_verified"
    assert res["verification"]["identity_verified"] is True
    assert res["verification"]["license_last4"] == "4567"
    assert "simulated" in res["disclaimer"].lower()
    caps = res["verification"]["capabilities"]
    assert {"negotiate", "create_deal", "reserve_vehicle"} <= set(caps)


def test_identity_requires_license_and_selfie():
    vid = _new()["id"]
    _to_verified_human(vid)
    assert "error" in verify.submit_identity(vid, "")                       # no license
    assert "error" in verify.submit_identity(vid, "D1", selfie_provided=False)  # no selfie


# ---------------------------------------------------------------------------- credit

def test_credit_requires_identity_and_a_decisioned_app():
    vid = _new()["id"]
    _to_verified_human(vid)
    app_id = _decisioned_credit_app()
    # identity not yet done -> blocked
    assert "error" in verify.submit_credit_verification(vid, app_id)
    verify.submit_identity(vid, "D1234567")
    got = verify.submit_credit_verification(vid, app_id)
    assert got["verification"]["tier"] == "credit_verified"
    assert got["verification"]["credit_verified"] is True
    assert {"final_financing", "contracting", "schedule_delivery"} <= set(got["verification"]["capabilities"])


def test_credit_rejects_undecisioned_app():
    vid = _new()["id"]
    _to_verified_human(vid)
    verify.submit_identity(vid, "D1234567")
    ledger.add_entity(Entity(id="CUST-3", entity_type=CUSTOMER, attributes={"Name": "Q"}))
    draft = create_credit_application("CUST-3", "EMP-1")  # never submitted -> still draft
    assert "error" in verify.submit_credit_verification(vid, draft.id)


# ------------------------------------------------------------------- capability gate

def test_require_capability_returns_clear_gate():
    vid = _new()["id"]
    ok, err = verify.require_capability(vid, "negotiate")
    assert ok is False and "Identity Verified" in err
    _to_verified_human(vid)
    verify.submit_identity(vid, "D1234567")
    ok, err = verify.require_capability(vid, "negotiate")
    assert ok is True and err is None


def test_require_capability_fails_closed_on_unknown():
    vid = _new()["id"]
    ok, err = verify.require_capability(vid, "launch_rockets")
    assert ok is False and "Unknown capability" in err


def test_changing_verified_email_drops_tier():
    vid = _new()["id"]
    _to_verified_human(vid)
    assert verify.get_verification(vid)["tier"] == "verified_human"
    verify.set_contact(vid, email="different@example.com")
    got = verify.get_verification(vid)
    assert got["email_verified"] is False
    assert got["tier"] == "anonymous"  # lost a required proof, recomputed down


# --------------------------------------------------------------------- catalog/lists

def test_capability_catalog_lists_all_four_tiers():
    cat = verify.capability_catalog()
    tiers = [t["tier"] for t in cat["tiers"]]
    assert tiers == ["anonymous", "verified_human", "identity_verified", "credit_verified"]
    top = cat["tiers"][-1]
    assert len(top["all_capabilities"]) == 12  # cumulative across all tiers
    assert "otp" in cat["disclaimers"] and "identity" in cat["disclaimers"]


def test_summary_counts_by_tier():
    a = _new()["id"]
    _to_verified_human(_new()["id"])
    s = verify.verification_summary()
    assert s["total"] == 2
    assert s["by_tier"]["anonymous"] == 1
    assert s["by_tier"]["verified_human"] == 1
    assert s["verified_humans_or_above"] == 1


def test_linked_entity_must_be_customer_or_lead():
    assert "error" in verify.start_verification(linked_entity_id="NOPE-1")
    ledger.add_entity(Entity(id="LEAD-7", entity_type=LEAD, attributes={"FirstName": "A"}))
    v = verify.start_verification(linked_entity_id="LEAD-7")
    assert v["verification"]["linked_entity_id"] == "LEAD-7"


# ------------------------------------------------------------------------- public API

def test_public_flow_via_token():
    started = verify_api.public_start_verification(email="pat@example.com", phone="555-000-1234")
    token = started["session_token"]
    assert token and started["verification"]["tier"] == "anonymous"

    # get by token
    assert verify_api.public_get_verification(token)["id"] == started["verification"]["id"]

    # Public callers cannot use internally simulated challenges as identity proof.
    for channel in ("email", "sms"):
        got = verify_api.public_request_code(token, channel)
        assert got["reason"] == "provider_unavailable"
        assert "dev_code" not in got
        assert verify_api.public_confirm_code(token, channel, "123456")["reason"] == "provider_unavailable"
    assert verify_api.public_submit_identity(token, "D9999999")["reason"] == "provider_unavailable"
    assert verify_api.public_submit_credit(token, "CREDIT-1")["reason"] == "provider_unavailable"
    entity = ledger.get_entity(started["verification"]["id"])
    assert entity.attributes["tier"] == "anonymous"
    assert entity.attributes["challenges"] == {}


def test_public_cannot_confirm_a_challenge_created_by_internal_simulation():
    started = verify_api.public_start_verification(email="pat@example.com")
    vid = started["verification"]["id"]
    code = verify.request_email_code(vid)["dev_code"]
    result = verify_api.public_confirm_code(started["session_token"], "email", code)
    assert result["reason"] == "provider_unavailable"
    assert not ledger.get_entity(vid).attributes["email_verified"]


def test_public_bad_token_is_rejected():
    assert "error" in verify_api.public_get_verification("not-a-real-token")
    assert "error" in verify_api.public_request_code("nope", "email")


def test_staff_dashboard_open_to_any_role():
    _to_verified_human(_new()["id"])
    dash = verify_api.get_verify_dashboard_api(SALES)
    assert dash["summary"]["total"] == 1
    assert len(dash["recent"]) == 1
    assert len(dash["catalog"]["tiers"]) == 4
