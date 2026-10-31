"""
MySales personal AI config + tiered routing (Freemium Phase 5+, 2026-08-03). Per-rep (not per-dealer)
AI setup: personal on/off, BYOK (raw key never stored), and tiered routing (routine->cheap tier,
premium->high-end, on-device when available). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import mysales_ai as ma


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_defaults():
    c = ma.get_config("EMP-1")
    assert c["ai_enabled"] is True
    assert c["byok"]["configured"] is False
    assert c["routing"]["on_device_when_available"] is True
    assert c["routing"]["routine_tier"] == ma.DEFAULT_ROUTINE_TIER


def test_byok_never_stores_raw_key():
    c = ma.set_byok("EMP-1", "anthropic", "sk-ant-supersecret-9999")
    assert c["byok"]["configured"] is True
    assert c["byok"]["provider"] == "anthropic"
    assert c["byok"]["key_masked"] == "••••9999"
    # the raw key must appear nowhere in the stored entity
    ent = ledger.get_entity("MSAI-EMP-1")
    assert "supersecret" not in str(ent.attributes)


def test_byok_bad_provider_rejected():
    assert "error" in ma.set_byok("EMP-1", "not_a_provider", "x")


def test_routing_priority_byok_beats_on_device():
    ma.set_byok("EMP-1", "openai", "sk-1234")
    d = ma.resolve_model("EMP-1", "routine")
    assert d["source"] == "byok" and d["provider"] == "openai"


def test_routing_on_device_for_routine_only():
    # default: on_device on, no byok
    assert ma.resolve_model("EMP-1", "routine")["source"] == "on_device"
    assert ma.resolve_model("EMP-1", "premium")["source"] == "dealer"  # premium never on-device


def test_routing_off_when_rep_disables():
    ma.set_ai_enabled("EMP-1", False)
    assert ma.resolve_model("EMP-1", "routine")["source"] == "off"


def test_routing_falls_back_to_dealer_when_no_on_device():
    ma.set_routing("EMP-1", on_device_when_available=False)
    d = ma.resolve_model("EMP-1", "routine")
    assert d["source"] == "dealer" and d["model"] == ma.DEFAULT_ROUTINE_TIER


def test_clear_byok():
    ma.set_byok("EMP-1", "openai", "sk-1234")
    ma.clear_byok("EMP-1")
    assert ma.get_config("EMP-1")["byok"]["configured"] is False


def test_scoped_per_rep():
    ma.set_ai_enabled("EMP-1", False)
    assert ma.get_config("EMP-1")["ai_enabled"] is False
    assert ma.get_config("EMP-2")["ai_enabled"] is True  # independent
