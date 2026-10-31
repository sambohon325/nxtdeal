"""
core/module_adoption.py -- the extended-funnel signal for the Hub (Freemium Platform roadmap,
Phase 4, 2026-08-03).

Phase 4 redefines the Hub's Dealer Lifecycle Funnel. The Resolved Direction is to EXTEND, not
replace: add a "Foundation Signup" stage ahead of the existing Demo/Trial stages, so self-serve
free accounts show up distinctly, and track Free Signup -> Foundation Active -> Module Adoption ->
Expansion -> Churn Risk. The funnel itself lives in the Hub; what the Hub needs from each tenant is
a real signal of where that dealer sits -- module attach rate and free-to-paid conversion, read live
rather than hand-maintained.

This module computes that signal from the tenant's own state: the entitlement record (which paid
Modules are active, at what level) plus the onboarding signals (is the dealer actually operating on
Foundation yet). It is credential-free and Hub-independent -- the tenant emits, the Hub composes the
funnel stage.

Funnel stage derivation (tenant's contribution):
  * foundation_signup  -- the account exists but isn't operating yet (no real Foundation data).
  * foundation_active  -- operating on the free tier (Foundation data present) with no paid Module.
  * module_adoption    -- at least one paid Module is active (free-to-paid conversion happened).
The Hub layers Expansion / Churn Risk on top from its own longitudinal data.
"""

from core import entitlements
from core import onboarding_signals


def _foundation_active():
    """Is the dealer actually operating on Foundation -- i.e. have they put real data in? Reuses
    the onboarding signals: inventory or CRM imported means the free tier is live, not just signed
    up."""
    sig = onboarding_signals.compute_onboarding_signals()
    by_key = {s["key"]: s for s in sig["steps"]}
    inv = by_key.get("inventory_imported", {}).get("complete", False)
    crm = by_key.get("crm_imported", {}).get("complete", False)
    return bool(inv or crm), sig


def compute_module_adoption():
    """The tenant's funnel signal: which paid Modules are attached, whether free-to-paid conversion
    has happened, and the derived funnel stage."""
    active = entitlements.active_modules()  # includes 'foundation'
    paid_active = [m for m in active if m != entitlements.FOUNDATION]
    levels = entitlements.module_levels()

    foundation_active, onboarding = _foundation_active()
    converted = len(paid_active) > 0

    if converted:
        stage = "module_adoption"
    elif foundation_active:
        stage = "foundation_active"
    else:
        stage = "foundation_signup"

    # Per-module attach detail (every paid Module, on or off) so the Hub can compute attach rate.
    modules = []
    for key in entitlements.PAID_MODULES:
        on = entitlements.is_module_enabled(key)
        modules.append({
            "module": key,
            "name": entitlements.MODULE_CATALOG[key]["name"],
            "active": on,
            "level": levels.get(key) if on else None,
        })

    return {
        "funnel_stage": stage,
        "profile": entitlements.get_entitlements()["profile"],
        "foundation_active": foundation_active,
        "free_to_paid": converted,
        "active_paid_modules": paid_active,
        "paid_module_count": len(paid_active),
        "total_paid_modules": len(entitlements.PAID_MODULES),
        "attach_rate": round(len(paid_active) / len(entitlements.PAID_MODULES), 3),
        "modules": modules,
        "go_live": onboarding["go_live"],
    }


def build_module_adoption_snapshot():
    """Dealer-identified snapshot for the Hub's extended Dealer Lifecycle Funnel."""
    return compute_module_adoption()
