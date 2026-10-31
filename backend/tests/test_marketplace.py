"""Tests for the NXTDeal Marketplace (core/marketplace.py, 2026-07-24)."""

import pytest

from core import marketplace as m
from core import integrations_registry


def test_catalog_shape():
    mp = m.get_marketplace()
    s = mp["summary"]
    assert s["total_listings"] > 80
    assert s["categories"] == 19  # 13 day1 + OEM + 5 phase2
    assert s["day1_categories"] == 13
    assert s["oem_brands"] == 10
    assert len(mp["sections"]["day1"]) == 13
    assert len(mp["sections"]["phase2"]) == 5
    assert mp["sections"]["oem"] == ["oem"]


def test_every_listing_has_a_valid_category():
    ids = {c["id"] for c in m.ALL_CATEGORIES}
    for l in m.LISTINGS:
        assert l["category"] in ids, l["id"]


def test_install_then_state_is_installed():
    r = m.install_listing("stripe", "admin-1")
    assert r["state"] == "installed"
    assert r["capability"] == "payments"
    assert r["installed_by"] == "admin-1"
    # reflected in the rollup
    mp = m.get_marketplace()
    stripe = next(l for c in mp["categories"] for l in c["listings"] if l["id"] == "stripe")
    assert stripe["state"] == "installed"


def test_install_records_intended_provider_via_seam():
    m.install_listing("persona", "admin-2")  # capability: identity
    settings = integrations_registry.get_or_create_settings()
    assert settings.attributes["providers"].get("identity", {}).get("provider_name") == "Persona"


def test_uninstall_is_soft_and_returns_available():
    m.install_listing("veriff", "admin-1")
    r = m.uninstall_listing("veriff", "admin-1")
    assert r["state"] == "available"
    # a second uninstall is rejected (not installed)
    r2 = m.uninstall_listing("veriff", "admin-1")
    assert "error" in r2


def test_phase2_listing_not_installable():
    r = m.install_listing("ai_sales_coach", "admin-1")
    assert "error" in r
    # and it always reads as coming_soon in the catalog
    detail = m.get_listing("ai_sales_coach")
    assert detail["state"] == "coming_soon"


def test_connected_when_a_real_adapter_is_registered():
    # No adapters ship in the repo, so register one transiently to prove the "connected" path.
    integrations_registry.register_adapter("notifications", lambda *a, **k: {"ok": True})
    try:
        detail = m.get_listing("twilio")  # capability: notifications
        assert detail["state"] == "connected"
        assert detail["capability_live"] is True
    finally:
        integrations_registry._ADAPTERS.pop("notifications", None)


def test_unknown_listing_errors():
    assert "error" in m.get_listing("nope")
    assert "error" in m.install_listing("nope")
