"""
Generalized per-user, per-app AI config tests (2026-10-24).
Run from backend/ with `pytest tests/test_ai_config.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import ai_config as ac


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_defaults():
    c = ac.get_config("EMP-1", "salesapp")
    assert c["ai_enabled"] is True
    assert c["byok"]["configured"] is False
    assert c["routing"]["on_device_when_available"] is True
    assert c["routing"]["routine_tier"] == ac.DEFAULT_ROUTINE_TIER
    assert c["routing"]["premium_tier"] == ac.DEFAULT_PREMIUM_TIER
    assert c["app_slug"] == "salesapp"
    assert c["user_id"] == "EMP-1"


def test_byok_never_stores_raw_key():
    c = ac.set_byok("EMP-1", "salesapp", "anthropic", "sk-1234")
    assert c["byok"]["configured"] is True
    assert c["byok"]["provider"] == "anthropic"
    assert c["byok"]["key_masked"] == "••••1234"
    ent = ledger.get_entity("AIC-salesapp-EMP-1")
    assert "sk-1234" not in str(ent.attributes)


def test_byok_bad_provider_rejected():
    assert "error" in ac.set_byok("EMP-1", "salesapp", "not_a_provider", "x")


def test_byok_empty_clears_configured():
    ac.set_byok("EMP-1", "salesapp", "openai", "sk-abcd")
    c = ac.set_byok("EMP-1", "salesapp", "openai", "")
    assert c["byok"]["configured"] is False
    assert c["byok"]["provider"] == "openai"


def test_routing_priority_byok_beats_on_device():
    ac.set_byok("EMP-1", "salesapp", "openai", "sk-1234")
    d = ac.resolve_model("EMP-1", "salesapp", "routine")
    assert d["source"] == "byok" and d["provider"] == "openai"


def test_routing_on_device_for_routine_only():
    assert ac.resolve_model("EMP-1", "salesapp", "routine")["source"] == "on_device"
    assert ac.resolve_model("EMP-1", "salesapp", "premium")["source"] == "dealer"


def test_routing_off_when_user_disables():
    ac.set_ai_enabled("EMP-1", "salesapp", False)
    assert ac.resolve_model("EMP-1", "salesapp", "routine")["source"] == "off"


def test_routing_falls_back_to_dealer_when_no_on_device():
    ac.set_routing("EMP-1", "salesapp", on_device_when_available=False)
    d = ac.resolve_model("EMP-1", "salesapp", "routine")
    assert d["source"] == "dealer" and d["model"] == ac.DEFAULT_ROUTINE_TIER


def test_scoped_per_user_and_app():
    ac.set_ai_enabled("EMP-1", "salesapp", False)
    assert ac.get_config("EMP-1", "salesapp")["ai_enabled"] is False
    assert ac.get_config("EMP-1", "serviceops")["ai_enabled"] is True
    assert ac.get_config("EMP-2", "salesapp")["ai_enabled"] is True


def test_resolve_model_invalid_user():
    assert ac.resolve_model("", "salesapp", "routine")["source"] == "off"


def test_clear_byok():
    ac.set_byok("EMP-1", "salesapp", "openai", "sk-1234")
    ac.clear_byok("EMP-1", "salesapp")
    assert ac.get_config("EMP-1", "salesapp")["byok"]["configured"] is False


def test_mysales_delegates_to_mysales_ai():
    from core import mysales_ai as ma
    # Setting a config via ai_config for mysales should delegate to mysales_ai
    c = ac.get_config("REP-1", "mysales")
    assert c["ai_enabled"] is True
    # resolve_model for mysales delegates to mysales_ai
    d = ac.resolve_model("REP-1", "mysales", "routine")
    assert d["source"] == "on_device"
    # Compare with direct mysales_ai call
    d2 = ma.resolve_model("REP-1", "routine")
    assert d["source"] == d2["source"]


def test_mysales_delegates_set_ai_enabled():
    from core import mysales_ai as ma
    ac.set_ai_enabled("REP-1", "mysales", False)
    c = ac.get_config("REP-1", "mysales")
    assert c["ai_enabled"] is False
    # Verify it used the mysales_ai entity
    ent = ledger.get_entity("MSAI-REP-1")
    assert ent is not None and ent.entity_type == "MySalesAiConfig"


def test_mysales_delegates_set_byok_uses_old_entity():
    ac.set_byok("REP-1", "mysales", "anthropic", "sk-1234")
    # Should have used the old MSAI-{rep_id} entity, not the new AIC- one
    old_ent = ledger.get_entity("MSAI-REP-1")
    assert old_ent is not None
    new_ent = ledger.get_entity("AIC-mysales-REP-1")
    assert new_ent is None
    c = ac.get_config("REP-1", "mysales")
    assert c["byok"]["configured"] is True


def test_mysales_delegates_clear_byok():
    ac.set_byok("REP-1", "mysales", "anthropic", "sk-1234")
    ac.clear_byok("REP-1", "mysales")
    c = ac.get_config("REP-1", "mysales")
    assert c["byok"]["configured"] is False


def test_mysales_delegates_set_routing():
    ac.set_routing("REP-1", "mysales", on_device_when_available=False)
    c = ac.get_config("REP-1", "mysales")
    assert c["routing"]["on_device_when_available"] is False
