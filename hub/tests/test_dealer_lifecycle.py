"""
Self-serve signup + inactivity lifecycle (NXTDeal Freemium, 2026-08-03). Proves the LOGIC against an
in-memory store + an injected clock, so the 6-month-deactivate / 12-month-delete / reactivate rules
are verified independently of the Hub's real persistence. Run from repo root: `pytest hub/tests/`.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from hub.core._signup_store import InMemoryDealerStore
from hub.core import dealer_signup, dealer_lifecycle


@pytest.fixture(autouse=True)
def fresh_store():
    store = InMemoryDealerStore()
    dealer_signup.set_store(store)
    dealer_signup.set_provisioner(None)
    dealer_lifecycle.set_store(store)
    yield store


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _signup(**over):
    args = dict(name="Sam", work_email="sam@acmeauto.com", dealership_name="Acme Auto", business_type="bhph")
    args.update(over)
    return dealer_signup.self_serve_signup(**args)


# --- signup ---

def test_signup_creates_free_foundation_dealer():
    r = _signup()
    assert r["ok"] and r["plan_tier"] == "foundation" and r["seat_count"] == 20
    assert r["slug"] == "acme-auto"
    assert r["status"] == "active"
    assert r["suggested_modules"] == ["finance", "operations"]   # BHPH package, suggested not bought
    assert r["instance_url"].startswith("https://acme-auto.")


def test_signup_does_not_auto_buy_modules():
    r = _signup()
    dealer = dealer_signup._store.get(r["dealer_id"])
    assert dealer["active_modules"] == ["foundation"]            # free tier only
    assert dealer["created_via"] == "self_serve"
    assert dealer["last_activity_at"] is not None                # inactivity clock started


def test_signup_validation_and_dupe_email():
    assert "error" in _signup(dealership_name="")
    assert "error" in _signup(work_email="not-an-email")
    assert "error" in _signup(business_type="spaceship")
    _signup(work_email="dup@acmeauto.com")
    assert _signup(work_email="dup@acmeauto.com", dealership_name="Other")["reason"] == "email_taken"


def test_slug_uniqueness():
    a = _signup(work_email="a@x.com")
    b = _signup(work_email="b@x.com")  # same dealership name -> slug bumped
    assert a["slug"] == "acme-auto" and b["slug"] == "acme-auto-2"


def test_free_email_warns_not_blocks():
    r = _signup(work_email="sam@gmail.com")
    assert r["ok"] and any("work email" in w for w in r["warnings"])


def test_provisioner_is_called_and_wired():
    calls = {}
    def prov(record):
        calls["id"] = record["dealer_id"]
        return {"api_url": "https://acme-api.dealeros.xyz", "frontend_url": "https://acme.dealeros.xyz"}
    dealer_signup.set_provisioner(prov)
    r = _signup()
    assert calls["id"] == r["dealer_id"]
    assert r["instance_url"] == "https://acme.dealeros.xyz"


def test_signup_survives_provisioner_failure():
    def boom(record):
        raise RuntimeError("coolify down")
    dealer_signup.set_provisioner(boom)
    r = _signup()
    assert r["ok"] and r["status"] == "provisioning"   # left for retry, signup still succeeded


# --- inactivity lifecycle ---

def test_no_deactivation_before_six_months():
    _signup()
    res = dealer_lifecycle.sweep(now=T0 + timedelta(days=182))
    assert res["deactivated_count"] == 0


def test_deactivates_after_six_months_inactive():
    r = _signup()
    # signup stamped last_activity at "now" (real clock); overwrite to T0 for deterministic math
    d = dealer_lifecycle._store.get(r["dealer_id"]); d["last_activity_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    res = dealer_lifecycle.sweep(now=T0 + timedelta(days=183))
    assert res["deactivated"] == [r["dealer_id"]]
    d = dealer_lifecycle._store.get(r["dealer_id"])
    assert d["status"] == "suspended" and d["suspended_reason"] == "inactivity"
    assert d["scheduled_deletion_at"] is not None


def test_deletes_twelve_months_total():
    r = _signup()
    d = dealer_lifecycle._store.get(r["dealer_id"]); d["last_activity_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    dealer_lifecycle.sweep(now=T0 + timedelta(days=183))          # deactivate at ~6mo
    # not yet deleted just after deactivation
    assert dealer_lifecycle.sweep(now=T0 + timedelta(days=200))["deleted_count"] == 0
    # deleted once the second 6-month window passes (~12 months total)
    res = dealer_lifecycle.sweep(now=T0 + timedelta(days=183 + 183))
    assert res["deleted"] == [r["dealer_id"]]
    assert dealer_lifecycle._store.get(r["dealer_id"]) is None


def test_relogin_reactivates_and_resets_clock():
    r = _signup()
    d = dealer_lifecycle._store.get(r["dealer_id"]); d["last_activity_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    dealer_lifecycle.sweep(now=T0 + timedelta(days=183))          # deactivated
    assert dealer_lifecycle._store.get(r["dealer_id"])["status"] == "suspended"
    # re-login 30 days into the deletion window
    back = dealer_lifecycle.record_dealer_activity(r["dealer_id"], now=T0 + timedelta(days=213))
    assert back["reactivated"] is True and back["status"] == "active"
    d = dealer_lifecycle._store.get(r["dealer_id"])
    assert d["suspended_reason"] is None and d["deactivated_at"] is None
    # and it is NOT deleted at what would have been the 12-month mark
    assert dealer_lifecycle.sweep(now=T0 + timedelta(days=366))["deleted_count"] == 0


def test_admin_suspension_is_not_auto_deleted():
    r = _signup()
    d = dealer_lifecycle._store.get(r["dealer_id"])
    d["status"] = "suspended"; d["suspended_reason"] = "billing"        # not inactivity
    d["deactivated_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    res = dealer_lifecycle.sweep(now=T0 + timedelta(days=400))
    assert res["deleted_count"] == 0   # only inactivity-suspended are auto-deleted


def test_paid_dealer_not_auto_deleted():
    r = _signup()
    d = dealer_lifecycle._store.get(r["dealer_id"])
    d["last_activity_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    dealer_lifecycle.sweep(now=T0 + timedelta(days=183))                 # deactivated while foundation
    d = dealer_lifecycle._store.get(r["dealer_id"]); d["plan_tier"] = "pro"; dealer_lifecycle._store.save(d)
    res = dealer_lifecycle.sweep(now=T0 + timedelta(days=400))
    assert res["deleted_count"] == 0   # upgraded to paid -> never auto-deleted


def test_lifecycle_status_countdowns():
    r = _signup()
    d = dealer_lifecycle._store.get(r["dealer_id"]); d["last_activity_at"] = T0.isoformat(); dealer_lifecycle._store.save(d)
    st = dealer_lifecycle.lifecycle_status(r["dealer_id"], now=T0 + timedelta(days=100))
    assert st["next"] == "deactivation" and st["days_until_deactivation"] == 83.0
