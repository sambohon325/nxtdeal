"""
Freemium Platform / Foundation-plus-Modules enforcement (Phase 1, 2026-08-03). The tenant-side
entitlement record the running product reads before serving a paid Module feature. Default is the
full-build "reference" profile (everything on) so an existing instance is unchanged; a "foundation"
profile gates paid Modules off and applies Tier-0 caps. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import ENTITLEMENT
from core import entitlements as ent


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


# --- catalog integrity ---

def test_catalog_has_foundation_plus_eight_modules():
    assert ent.FOUNDATION in ent.MODULE_CATALOG
    assert len(ent.PAID_MODULES) == 8
    for m in ent.PAID_MODULES:
        assert m in ent.MODULE_CATALOG
        assert ent.MODULE_CATALOG[m]["category"] == "module"
    assert ent.MODULE_CATALOG[ent.FOUNDATION]["category"] == "foundation"


def test_feature_index_covers_every_feature_with_valid_levels():
    total = sum(len(m["features"]) for m in ent.MODULE_CATALOG.values())
    assert len(ent.FEATURE_INDEX) == total  # unique feature keys, no collisions
    for feat_key, (mod_key, level) in ent.FEATURE_INDEX.items():
        assert mod_key in ent.MODULE_CATALOG
        assert level in ent.LEVELS
    # Every Foundation feature is the free baseline.
    for feat in ent.MODULE_CATALOG[ent.FOUNDATION]["features"]:
        assert feat["level"] == "free"


# --- default = reference (Dealer1 unchanged) ---

def test_default_profile_is_reference_everything_on():
    e = ent.get_entitlements()
    assert e["profile"] == ent.PROFILE_REFERENCE
    assert all(ent.is_module_enabled(m) for m in ent.PAID_MODULES)
    assert ent.is_module_enabled(ent.FOUNDATION)


def test_reference_caps_are_unlimited():
    for cap in ent.USAGE_CAPS:
        assert ent.usage_cap(cap) is None
        assert ent.check_usage(cap, 10_000)["allowed"] is True


def test_reference_enterprise_features_available():
    assert ent.is_feature_available("desking") is True          # sales / professional
    assert ent.is_feature_available("ai_sales_agents") is True   # sales / enterprise
    assert ent.is_feature_available("crm_contacts") is True      # foundation / free


# --- foundation profile gates paid modules ---

def test_foundation_profile_gates_all_paid_modules():
    ent.set_profile("foundation", "admin")
    assert not any(ent.is_module_enabled(m) for m in ent.PAID_MODULES)
    assert ent.is_module_enabled(ent.FOUNDATION)  # foundation always on


def test_foundation_free_features_stay_available_paid_locked():
    ent.set_profile("foundation", "admin")
    assert ent.is_feature_available("crm_contacts") is True   # free baseline
    assert ent.is_feature_available("desking") is False       # sales professional, module off
    assert ent.is_feature_available("repair_orders") is False


def test_foundation_caps_are_the_starting_defaults():
    ent.set_profile("foundation", "admin")
    assert ent.usage_cap("active_contacts") == 250
    assert ent.usage_cap("inventory_units_online") == 25
    assert ent.usage_cap("report_history_days") == 90
    assert ent.usage_cap("staff_seats") == 3


def test_check_usage_boundary():
    ent.set_profile("foundation", "admin")
    assert ent.check_usage("active_contacts", 249)["allowed"] is True
    r = ent.check_usage("active_contacts", 250)
    assert r["allowed"] is False and r["reason"] == "cap_reached" and r["remaining"] == 0


# --- require_module gate (what routes call) ---

def test_require_module_passes_when_enabled_blocks_when_locked():
    assert ent.require_module("service") is None  # reference default
    ent.set_profile("foundation", "admin")
    err = ent.require_module("service")
    assert err["reason"] == "module_locked" and err["module"] == "service"
    assert err["upgrade"]["module_name"] == "Service Module"


def test_unknown_module_and_feature_fail_closed():
    assert ent.is_module_enabled("teleport") is False
    assert ent.is_feature_available("warp_drive") is False
    assert ent.require_module("teleport")["reason"] == "unknown_module"


# --- level gating within a module ---

def test_enable_single_module_moves_to_custom_and_gates_by_level():
    ent.set_profile("foundation", "admin")
    ent.set_module("sales", True, "admin", level="professional")
    assert ent.get_entitlements()["profile"] == ent.PROFILE_CUSTOM
    assert ent.is_module_enabled("sales") and ent.module_level("sales") == "professional"
    assert ent.is_feature_available("desking") is True         # professional owned
    assert ent.is_feature_available("ai_sales_agents") is False  # enterprise not owned

    ent.set_module("sales", True, "admin", level="enterprise")
    assert ent.is_feature_available("ai_sales_agents") is True


def test_feature_status_reports_lock_reason():
    ent.set_profile("foundation", "admin")
    s = ent.feature_status("ai_sales_agents")
    assert s["available"] is False and s["reason"] == "module_locked"
    ent.set_module("sales", True, "admin", level="professional")
    s2 = ent.feature_status("ai_sales_agents")
    assert s2["available"] is False and s2["reason"] == "level_locked" and s2["owned_level"] == "professional"


# --- caps setter ---

def test_set_cap_custom_and_unlimited():
    assert "error" not in ent.set_cap("active_contacts", 500, "admin")
    assert ent.usage_cap("active_contacts") == 500
    ent.set_cap("active_contacts", None, "admin")  # lift
    assert ent.usage_cap("active_contacts") is None
    assert "error" in ent.set_cap("active_contacts", -5, "admin")
    assert "error" in ent.set_cap("nonexistent_cap", 5, "admin")


def test_set_module_rejects_bad_input():
    assert "error" in ent.set_module("not_a_module", True, "admin")
    assert "error" in ent.set_module("sales", True, "admin", level="platinum")


# --- launch paths + public read ---

def test_recommend_modules_by_industry():
    assert ent.recommend_modules("franchise") == ["sales", "service", "marketing"]
    assert ent.recommend_modules("independent") == ["sales", "marketing"]
    assert ent.recommend_modules("bhph") == ["finance", "operations"]
    assert ent.recommend_modules("finance_company") == ["finance", "service"]
    assert ent.recommend_modules("unknown") == []


def test_public_entitlements_shape():
    p = ent.public_entitlements()
    assert set(p.keys()) == {"active_modules", "module_levels"}
    assert ent.FOUNDATION in p["active_modules"]
    assert p["module_levels"][ent.FOUNDATION] == "free"


# --- backfill: an older record missing a newly-added module inherits its profile posture ---

def test_backfill_missing_module_on_foundation_record_stays_off():
    # simulate a persisted foundation record that predates a module being added to PAID_MODULES
    ledger.add_entity(Entity(id="ENTL-00001", entity_type=ENTITLEMENT, attributes={
        "profile": "foundation",
        "modules": {m: {"enabled": False, "level": "free"} for m in ent.PAID_MODULES if m != "connect"},
        "caps": {c: ent.USAGE_CAPS[c]["foundation_default"] for c in ent.USAGE_CAPS},
        "updated_by": "seed", "updated_at": "2026-01-01T00:00:00Z",
    }))
    # reading backfills 'connect' -> off (never silently granted to a Foundation dealer)
    assert ent.is_module_enabled("connect") is False


def test_backfill_missing_module_on_reference_record_turns_on():
    ledger.add_entity(Entity(id="ENTL-00001", entity_type=ENTITLEMENT, attributes={
        "profile": "reference",
        "modules": {m: {"enabled": True, "level": "enterprise"} for m in ent.PAID_MODULES if m != "connect"},
        "caps": {c: None for c in ent.USAGE_CAPS},
        "updated_by": "seed", "updated_at": "2026-01-01T00:00:00Z",
    }))
    assert ent.is_module_enabled("connect") is True


# --- NXTDeal AI add-on (managed inference, not in the free model) ---

def test_dealeros_ai_addon_on_by_default_reference():
    assert ent.is_managed_ai_available() is True
    assert "dealeros_ai" in ent.active_add_ons()
    # add-ons are NOT counted among the 8 feature Modules
    assert ent.active_modules().count("dealeros_ai") == 0
    assert len(ent.PAID_MODULES) == 8


def test_dealeros_ai_off_on_foundation():
    ent.set_profile("foundation", "admin")
    assert ent.is_managed_ai_available() is False
    assert ent.active_add_ons() == []


def test_dealeros_ai_can_be_added_individually():
    ent.set_profile("foundation", "admin")
    r = ent.set_module("dealeros_ai", True, "admin")
    assert "error" not in r
    assert ent.is_managed_ai_available() is True
    assert r["managed_ai_available"] is True


def test_catalog_exposes_add_ons():
    cat = ent.get_catalog()
    assert cat["add_ons"] == ["dealeros_ai"]
    assert cat["modules"]["dealeros_ai"]["category"] == "add_on"


# --- API surface exists ---

def test_entitlement_routes_registered():
    from api.app import app
    paths = {getattr(r, "path", None) for r in app.routes}
    for p in ["/public/entitlements", "/entitlements", "/entitlements/catalog",
              "/entitlements/profile", "/entitlements/module", "/entitlements/cap"]:
        assert p in paths
