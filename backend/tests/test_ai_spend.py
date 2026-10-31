"""
AI Spend Governor (Freemium roadmap, Phase 5, 2026-08-03). BYO-key posture + per-user monthly AI
consumption limits + aggregate admin view. Meters AI ACTIONS (no token/cost metering exists), fed
from ai_management.record_call_attempt(actor=...). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import ai_spend as s
from core import ai_management as m


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _use(actor, feature="ai_assist", n=1, outcome="succeeded"):
    """Meter n AI actions for a user the real way: through record_call_attempt, which writes the
    AiActionLog entities the governor derives usage from."""
    for _ in range(n):
        m.record_call_attempt(feature, outcome, actor=actor)


def test_default_policy_unlimited_openai():
    p = s.get_policy()
    assert p["provider"] == "openai"
    assert p["per_user_monthly_limit"] is None
    assert p["byo_key_configured"] is False


def test_set_provider_and_byo():
    p = s.set_provider("gemini", "admin", byo_key_configured=True)
    assert p["provider"] == "gemini" and p["byo_key_configured"] is True
    assert "error" in s.set_provider("nonsense", "admin")


def test_default_limit_enforced_per_user():
    s.set_default_limit(2, "admin")
    _use("EMP-1")
    assert s.enforce_user_allowance("EMP-1") is None  # 1/2
    _use("EMP-1")
    err = s.enforce_user_allowance("EMP-1")  # 2/2
    assert err["reason"] == "user_limit_reached" and err["limit"] == 2


def test_unlimited_never_blocks():
    _use("EMP-9", "ai_help", n=50)
    assert s.enforce_user_allowance("EMP-9") is None
    assert s.check_user_allowance("EMP-9")["remaining"] is None


def test_user_override_beats_default():
    s.set_default_limit(1, "admin")
    s.set_user_limit("EMP-2", 5, "admin")
    _use("EMP-2", n=4)
    assert s.enforce_user_allowance("EMP-2") is None  # 4/5, override applies
    assert s.user_limit("EMP-2") == 5
    s.clear_user_limit("EMP-2", "admin")
    assert s.user_limit("EMP-2") == 1  # back to default


def test_no_actor_is_unattributed_not_blocked():
    s.set_default_limit(1, "admin")
    assert s.enforce_user_allowance(None) is None  # can't meter to a person
    _use(None, "ai_help")
    ov = s.get_spend_overview()
    assert ov["unattributed_actions"] == 1 and ov["attributed_actions"] == 0


def test_overview_aggregates_and_sorts():
    _use("EMP-A")
    _use("EMP-B")
    _use("EMP-B", "ai_help")
    ov = s.get_spend_overview()
    assert ov["total_ai_actions"] == 3 and ov["distinct_users"] == 2
    assert ov["users"][0]["user_id"] == "EMP-B"  # heaviest first
    assert ov["metering_basis"] == "ai_actions"


def test_blocked_calls_are_not_metered():
    m.record_call_attempt("ai_assistant", "succeeded", actor="EMP-7")
    m.record_call_attempt("ai_assistant", "blocked", actor="EMP-7")  # blocked = no provider call, no cost
    assert s.usage_for("EMP-7")["count"] == 1


def test_governor_adds_no_extra_entity_on_hot_path():
    # metering derives from AiActionLog -- record_call_attempt must still create exactly ONE entity
    before = len(ledger.get_all())
    m.record_call_attempt("ai_assistant", "succeeded", actor="EMP-8")
    assert len(ledger.get_all()) == before + 1


def test_validation():
    assert "error" in s.set_default_limit(-1, "admin")
    assert "error" in s.set_user_limit("", 5, "admin")


# --- managed provider (paid add-on), custom endpoint, billing ---

def test_managed_provider_requires_add_on():
    from core import entitlements as e
    e.set_profile("foundation", "admin")  # add-on off
    r = s.set_provider("dealeros", "admin")
    assert r["reason"] == "add_on_required"
    e.set_module("dealeros_ai", True, "admin")
    r2 = s.set_provider("dealeros", "admin")
    assert r2["provider"] == "dealeros"


def test_managed_billing_only_on_managed_provider():
    from core import entitlements as e
    e.set_module("dealeros_ai", True, "admin")
    s.set_provider("dealeros", "admin")
    s.set_managed_rate(0.05, "admin")
    _use("EMP-1", n=4)
    ov = s.get_spend_overview()
    assert ov["managed_billing"]["billable_actions"] == 4
    assert ov["managed_billing"]["estimated_charge"] == 0.2
    # switch to BYO-key -> no managed billing
    s.set_provider("openai", "admin")
    assert s.get_spend_overview()["managed_billing"] is None


def test_custom_endpoint_config():
    s.set_provider("custom", "admin")
    r = s.set_custom_endpoint({"base_url": "https://ai.me.com", "model": "llama3"}, "admin")
    assert r["custom_endpoint"]["base_url"] == "https://ai.me.com"
    assert r["custom_endpoint"]["auth_header"] == "Authorization"  # defaulted
    s.set_custom_endpoint(None, "admin")
    assert s.get_policy()["custom_endpoint"] is None


# --- AI on/off: dealer master + per-user opt-out ---

def test_dealer_master_off_blocks_all_ai_server_side():
    from core import ai_management as mgmt
    assert mgmt.is_feature_enabled("ai_assistant") is True
    s.set_ai_enabled(False, "admin")
    assert mgmt.is_feature_enabled("ai_assistant") is False  # central gate honors the master switch
    assert s.enforce_user_allowance("EMP-1")["reason"] == "ai_off_dealer"
    s.set_ai_enabled(True, "admin")
    assert mgmt.is_feature_enabled("ai_assistant") is True


def test_per_user_opt_out():
    s.set_user_ai_enabled("EMP-5", False, "admin")
    assert s.is_ai_enabled_for("EMP-5") is False
    assert s.is_ai_enabled_for("EMP-6") is True  # others unaffected
    assert s.enforce_user_allowance("EMP-5")["reason"] == "ai_off_user"
    assert s.enforce_user_allowance("EMP-6") is None
    # re-enable
    s.set_user_ai_enabled("EMP-5", True, "admin")
    assert s.is_ai_enabled_for("EMP-5") is True


def test_per_user_opt_out_does_not_stop_agent_learning():
    # Sam's rule: a user turning AI off for themselves hides AI from them, but the agent must keep
    # learning/recording their workflows. Recording is ungated; the opt-out only affects user-facing AI.
    from core import bot_fleet
    s.set_user_ai_enabled("EMP-5", False, "admin")   # user opts out
    assert s.is_ai_enabled_for("EMP-5") is False       # AI hidden for them
    assert s.background_ai_enabled() is True            # background AI still on (dealer master on)
    # the opted-out user's workflow step still records
    result = bot_fleet.record_workflow_step("sales", "EMP-5", "created_deal")
    assert "event_id" in result and result.get("section") == "sales"


def test_my_status_explains_which_switch():
    s.set_user_ai_enabled("EMP-7", False, "admin")
    st = s.get_my_ai_status("EMP-7")
    assert st == {"ai_enabled": False, "dealer_ai_enabled": True, "user_ai_off": True}
    s.set_ai_enabled(False, "admin")
    st2 = s.get_my_ai_status("EMP-8")
    assert st2["ai_enabled"] is False and st2["dealer_ai_enabled"] is False and st2["user_ai_off"] is False


def test_network_snapshot_shape():
    s.set_default_limit(1, "admin")
    _use("EMP-1")  # 1/1 -> over
    snap = s.build_ai_spend_network_snapshot()
    assert set(["provider", "byo_key_configured", "total_ai_actions", "users_over_limit"]).issubset(snap)
    assert "EMP-1" in snap["users_over_limit"]
