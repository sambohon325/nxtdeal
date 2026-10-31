"""
Tests for AI-demo leads + accounts (hub_core/demo_leads.py) — 2026-07-25. Run from hub/ with
`pytest`. Covers: sign-up creates a durable account + lead (no secrets leaked), duplicate email +
weak password + missing persona rejected; login right/wrong; forgot → reset round-trip; Turnstile
skipped when unconfigured and enforced (fail-closed) when configured; and the admin leads list.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)
if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)

import pytest

from hub_core import demo_leads as leads
from hub_core import demo_leads_storage as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    store.reset()
    monkeypatch.setattr(leads, "DEMO_ACCOUNTS_PATH", str(tmp_path / "demo_accounts.json"))
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    # The reset token is no longer returned to callers by default (security fix); opt in so the
    # forgot→reset roundtrip test can read it, like a local operator would.
    monkeypatch.setenv("HUB_EXPOSE_RESET_TOKEN", "1")
    yield
    store.reset()


def _signup(email="pat@store.com", **over):
    kw = dict(name="Pat Rep", email=email, password="hunter2xyz", persona="sales_manager",
              position="Sales Manager", dealership="City Motors", city="Austin", region="TX",
              country="USA", phone="555-0100", turnstile_token=None)
    kw.update(over)
    return leads.sign_up(**kw)


def test_signup_creates_account_without_leaking_secrets():
    out = _signup()
    assert out.get("ok") is True
    acct = out["account"]
    assert acct["email"] == "pat@store.com"
    assert acct["persona"] == "sales_manager"
    assert acct["dealership"] == "City Motors"
    assert "hash" not in acct and "salt" not in acct   # never leak credentials
    # persisted + retrievable
    assert store.get("pat@store.com") is not None


def test_signup_validation():
    assert "error" in _signup(email="notanemail")
    assert "error" in _signup(password="short")
    assert "error" in _signup(persona="")
    _signup()
    assert "error" in _signup(email="PAT@store.com")   # duplicate (case-insensitive)


def test_login_right_and_wrong():
    _signup()
    assert leads.log_in("pat@store.com", "hunter2xyz").get("ok") is True
    assert leads.log_in("PAT@store.com", "hunter2xyz").get("ok") is True   # case-insensitive
    assert "error" in leads.log_in("pat@store.com", "wrongpass9")
    assert "error" in leads.log_in("nobody@store.com", "hunter2xyz")


def test_login_by_username():
    _signup(username="patrep")
    assert leads.log_in("patrep", "hunter2xyz").get("ok") is True


def test_forgot_and_reset_roundtrip():
    _signup()
    req = leads.request_reset("pat@store.com")
    assert req["ok"] is True
    token = req["dev_reset_token"]
    # wrong token rejected
    assert "error" in leads.reset_password("pat@store.com", "wrong", "newpass123")
    # correct token resets; new password works, old doesn't
    assert leads.reset_password("pat@store.com", token, "newpass123").get("ok") is True
    assert leads.log_in("pat@store.com", "newpass123").get("ok") is True
    assert "error" in leads.log_in("pat@store.com", "hunter2xyz")
    # unknown email still returns ok (no enumeration)
    assert leads.request_reset("ghost@store.com")["ok"] is True


def test_turnstile_skipped_when_unconfigured_and_enforced_when_set(monkeypatch):
    # Unconfigured → allowed with no token.
    assert leads.turnstile_enabled() is False
    assert _signup(email="a@b.com").get("ok") is True

    # Configured → verified. Monkeypatch the network verify to fail then pass.
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk")
    assert leads.turnstile_enabled() is True
    monkeypatch.setattr(leads, "verify_turnstile", lambda token, remoteip=None: False)
    assert "error" in _signup(email="c@d.com", turnstile_token="bad")
    monkeypatch.setattr(leads, "verify_turnstile", lambda token, remoteip=None: True)
    assert _signup(email="e@f.com", turnstile_token="good").get("ok") is True


def test_list_leads_has_no_credentials():
    _signup()
    _signup(email="two@store.com")
    leads_list = leads.list_leads()
    assert len(leads_list) == 2
    assert all("hash" not in l and "salt" not in l for l in leads_list)
    assert all("created_at" in l for l in leads_list)


def test_reset_token_not_leaked_or_enumerated_by_default(monkeypatch):
    """Regression: /forgot must not hand the reset token to an anonymous caller, and its body
    must be identical whether or not the account exists (no email enumeration)."""
    monkeypatch.delenv("HUB_EXPOSE_RESET_TOKEN", raising=False)  # production default
    _signup()
    assert leads.request_reset("pat@store.com") == {"ok": True}       # token NOT returned
    assert leads.request_reset("ghost@store.com") == {"ok": True}     # same body, no enumeration
