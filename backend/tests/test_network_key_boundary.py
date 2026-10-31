import pytest
from core import network_snapshot_api as gate
from core import ai_kill_switch_network_api as control


@pytest.mark.parametrize("key", [None, "", "short", " " * 40,
    "dev-only-insecure-network-key-change-me", " dev-only-insecure-secret-change-me "])
def test_misconfigured_key_cannot_authorize_control_mutation(monkeypatch, key):
    monkeypatch.setattr(gate, "get_secret", lambda *_: key)
    monkeypatch.setattr(control, "set_dealer_wide_kill_switch",
        lambda *a, **k: pytest.fail("unauthorized mutation"))
    assert "error" in control.push_ai_kill_switch_api(key, "dealer_wide", True)


def test_network_key_is_exact_and_missing_input_is_denied(monkeypatch):
    key = "synthetic-network-key-for-boundary-tests-only"
    monkeypatch.setattr(gate, "get_secret", lambda *_: key)
    assert gate.check_network_key(key) is None
    for invalid in (None, {}, "", key.upper(), key + " "):
        assert "error" in gate.check_network_key(invalid)
