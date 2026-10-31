"""
Tests for the MySales rep referral/reward program (core/rep_referrals.py + _api.py) —
2026-07-24. Run from backend/ with `pytest`.

Covers: a rep gets a stable unique code; submitting a dealership demo/conversion referral;
recruiting attribution via code (self-referral + double-credit guards); admin advancing a
referral to 'rewarded' moves it from pending → earned in the summary totals; invalid status
and invalid kind are rejected; and the _api role gate on the admin actions.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import rep_referrals as rr
from core import rep_referrals_api as rr_api
from core.permissions import ADMIN, SALES


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def test_rep_gets_a_stable_unique_code():
    p1 = rr.get_or_create_profile("EMP-1")
    code = p1.attributes["code"]
    assert len(code) == rr._CODE_LEN
    # Stable across calls.
    assert rr.get_or_create_profile("EMP-1").attributes["code"] == code
    # Distinct rep → distinct code.
    assert rr.get_or_create_profile("EMP-2").attributes["code"] != code
    # Reverse lookup.
    assert rr.find_profile_by_code(code).attributes["employee_id"] == "EMP-1"
    assert rr.find_profile_by_code(code.lower()).attributes["employee_id"] == "EMP-1"


def test_submit_dealership_referral_and_summary_pending():
    out = rr.submit_dealership_referral("EMP-1", "dealership_demo", "City Motors",
                                        contact_name="Dana", contact_email="dana@city.com")
    assert out["kind"] == "dealership_demo"
    assert out["status"] == "submitted"
    assert out["reward"] == rr.REWARD_TIERS["dealership_demo"]["reward"]
    assert out["earned"] is False

    summary = rr.get_my_summary("EMP-1")
    assert summary["totals"]["pending"] == rr.REWARD_TIERS["dealership_demo"]["reward"]
    assert summary["totals"]["earned"] == 0
    assert summary["totals"]["dealership_referrals"] == 1


def test_submit_rejects_bad_kind_and_blank_name():
    assert "error" in rr.submit_dealership_referral("EMP-1", "not_a_kind", "X")
    assert "error" in rr.submit_dealership_referral("EMP-1", "dealership_demo", "   ")


def test_recruit_attribution_credits_referrer_with_guards():
    code = rr.get_or_create_profile("EMP-1").attributes["code"]

    # Another rep joins with EMP-1's code → EMP-1 credited.
    out = rr.attribute_signup("EMP-2", code)
    assert out["kind"] == "rep_recruit"
    assert out["subject"] == "EMP-2"
    assert rr.get_my_summary("EMP-1")["totals"]["recruits"] == 1

    # Self-referral blocked.
    assert "error" in rr.attribute_signup("EMP-1", code)
    # Double credit for the same recruit blocked.
    assert "error" in rr.attribute_signup("EMP-2", code)
    # Bad code blocked.
    assert "error" in rr.attribute_signup("EMP-3", "ZZZZZZZ")


def test_advance_to_rewarded_moves_pending_to_earned():
    ref = rr.submit_dealership_referral("EMP-1", "dealership_conversion", "City Motors")
    reward = rr.REWARD_TIERS["dealership_conversion"]["reward"]

    # Bad status rejected.
    assert "error" in rr.advance_referral(ref["id"], "not_a_status", "ADM-1")

    advanced = rr.advance_referral(ref["id"], "rewarded", "ADM-1")
    assert advanced["earned"] is True
    summary = rr.get_my_summary("EMP-1")
    assert summary["totals"]["earned"] == reward
    assert summary["totals"]["pending"] == 0


def test_api_role_gate_on_admin_actions():
    ref = rr.submit_dealership_referral("EMP-1", "dealership_demo", "City Motors")
    # A salesperson can't see the whole queue or advance referrals.
    assert "error" in rr_api.list_all_api(SALES)
    assert "error" in rr_api.advance_referral_api(SALES, "EMP-9", ref["id"], "rewarded")
    # Admin can.
    assert "referrals" in rr_api.list_all_api(ADMIN)
    assert rr_api.advance_referral_api(ADMIN, "ADM-1", ref["id"], "rewarded")["earned"] is True
