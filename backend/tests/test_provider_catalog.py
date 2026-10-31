"""
Provider catalog (Freemium roadmap, Phase 3, 2026-08-03). A real named-provider catalog the Hub's
Integrations Center + Migration Tracking read instead of manual data entry. Run from backend/ with
`pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import provider_catalog as pc


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def test_catalog_has_named_dms_crm_migration_sources():
    cat = pc.get_provider_catalog()
    keys = {p["key"] for p in cat["providers"]}
    for k in ["cdk", "reynolds", "tekion", "dealersocket", "vinsolutions", "hubspot"]:
        assert k in keys
    assert cat["migration_source_count"] >= 6


def test_every_entry_has_required_metadata():
    for p in pc.get_provider_catalog()["providers"]:
        assert p["key"] and p["name"]
        assert p["category"] in pc.CATEGORIES
        assert p["auth_type"] in (pc.AUTH_API_KEY, pc.AUTH_OAUTH, pc.AUTH_FEED, pc.AUTH_WEBHOOK, pc.AUTH_NONE)
        assert isinstance(p["migration_source"], bool)
        assert isinstance(p["requires_credentials"], bool)


def test_nhtsa_is_live_and_keyless():
    nhtsa = pc.get_provider("nhtsa_vpic")
    assert nhtsa["status"] == "live"
    assert nhtsa["requires_credentials"] is False
    assert nhtsa["auth_type"] == pc.AUTH_NONE


def test_migration_sources_are_dms_or_crm_flagged():
    sources = pc.list_migration_sources()
    assert all(s["migration_source"] for s in sources)
    names = {s["key"] for s in sources}
    assert {"cdk", "reynolds", "tekion"}.issubset(names)


def test_live_capability_annotation_present():
    # with no adapters registered, nothing is live -- but the annotation must exist and be honest
    cat = pc.get_provider_catalog()
    twilio = next(p for p in cat["providers"] if p["key"] == "twilio")
    assert "live_capabilities" in twilio and twilio["any_capability_live"] is False


def test_unknown_provider_returns_none():
    assert pc.get_provider("not_a_provider") is None
