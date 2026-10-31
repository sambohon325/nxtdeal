"""
core/entitlements.py -- NXTDeal Foundation + paid Modules: the tenant-side ENFORCEMENT layer
(Freemium Platform / Hub Restructuring roadmap, Phase 1, 2026-08-03).

Why this exists
---------------
The strategic shift is away from a sales-led Demo/Trial motion toward a product-led "Free
Forever" model: NXTDeal Foundation (Tier 0, free) plus paid Modules. The single biggest
engineering blocker the roadmap named is that *every* tiering mechanism today (the Hub's
Module Management, its global/group/dealer Licensing feature flags, integration config) is a
CONFIGURATION RECORD ONLY -- nothing the running product actually reads before serving a
feature. The Hub can describe "Sales Module: off" but the tenant never asks.

This module is the missing seam: a tenant-side entitlement record the running product reads
(`is_module_enabled` / `require_module` / `is_feature_available` / `check_usage`) before it
serves a Module feature or lets a metered Foundation feature grow past its cap. The Hub (or a
future sync) can push state INTO this record the same way it already authors feature flags;
until then it is a real, local, admin-editable record with honest defaults.

Design decisions (locked with Sam, 2026-08-03)
----------------------------------------------
* DEFAULT = the full-build "reference" profile: every Module enabled at the "enterprise"
  level, every usage cap unlimited. That means an existing single-tenant instance (Dealer1,
  the full-build reference) keeps every feature it has today -- enforcement is PRESENT but
  gates nothing until someone opts a dealer down. Nothing that works today breaks.
* A "foundation" profile gates every paid Module OFF and applies the Tier-0 starting caps
  (~250 active contacts, 25 inventory units live on the website, a 90-day report window, 3
  staff seats). These are starting points, tunable per dealer -- not fixed limits.
* Foundation (Tier 0) is ALWAYS enabled; it is the free base every dealer has.
* Feature levels within a Module mirror HubSpot's Free / Professional / Enterprise split. A
  feature marked level "free" is the Foundation baseline and is always available; a
  "professional" / "enterprise" feature requires its Module enabled at >= that level.

Same fixed-id-singleton convention as core/system_config.py's SystemConfig: one real
Entitlement entity, created on first read, backfilled, persisted into the one graph -- not a
second parallel file.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import ENTITLEMENT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


_ENTITLEMENT_ID = "ENTL-00001"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Module + feature catalog (the Foundation-vs-Modules taxonomy from the roadmap).
# ---------------------------------------------------------------------------

FOUNDATION = "foundation"

# The eight paid Modules, canonical order (roadmap "Modules, Instead of Starter/Pro/Enterprise").
PAID_MODULES = (
    "sales",
    "service",
    "marketing",
    "finance",
    "operations",
    "ai_workforce",
    "connect",
    "network_premium",
)
# Paid ADD-ONS (2026-08-03): metered products that aren't feature Modules. "dealeros_ai" is our own
# hosted, usage-billed AI inference -- deliberately NOT in the free model. It gates the managed
# "dealeros" AI provider (see core/ai_spend.py); a dealer who doesn't want it can still bring their
# own key or a homegrown endpoint at any tier. Kept OUT of PAID_MODULES so the eight-feature-Module
# structure (and its tests) is unchanged; GATED_KEYS is the union that can actually be toggled on/off.
ADD_ONS = ("dealeros_ai",)
GATED_KEYS = PAID_MODULES + ADD_ONS

ALL_MODULES = (FOUNDATION,) + PAID_MODULES

# Feature levels within a Module (HubSpot-style). Ordered; higher rank includes lower.
LEVELS = ("free", "professional", "enterprise")
LEVEL_RANK = {level: i for i, level in enumerate(LEVELS)}


def _feat(key, name, level):
    return {"key": key, "name": name, "level": level}


# Each catalog entry: key, name, category ("foundation" | "module"), tagline, and a flat list
# of features each tagged with the level at which it unlocks WITHIN the module. Foundation
# features are all "free" (the baseline every dealer gets).
MODULE_CATALOG = {
    FOUNDATION: {
        "key": FOUNDATION,
        "name": "NXTDeal Foundation",
        "category": "foundation",
        "tagline": "Free forever. Your dealership's data, live in NXTDeal from day one.",
        "features": [
            # Basic CRM
            _feat("crm_contacts", "Contacts", "free"),
            _feat("crm_customers", "Customers", "free"),
            _feat("crm_vehicles", "Vehicles", "free"),
            _feat("crm_opportunities", "Opportunities", "free"),
            _feat("crm_tasks", "Tasks", "free"),
            _feat("crm_activity_tracking", "Activity Tracking", "free"),
            # Basic Inventory
            _feat("inv_upload", "Inventory Upload", "free"),
            _feat("inv_vin_decode", "VIN Decode", "free"),
            _feat("inv_search", "Inventory Search", "free"),
            _feat("inv_vehicle_storage", "Vehicle Storage", "free"),
            # Basic Communications (logging only -- no AI, no automation)
            _feat("comms_email_logging", "Email Logging", "free"),
            _feat("comms_sms_logging", "SMS Logging", "free"),
            _feat("comms_contact_history", "Contact History", "free"),
            # Basic Reporting
            _feat("report_inventory", "Inventory Report", "free"),
            _feat("report_lead", "Lead Report", "free"),
            _feat("report_sales_activity", "Sales Activity Report", "free"),
            _feat("report_service_activity", "Service Activity Report", "free"),
            # NXTDeal Network (full, free -- the top-down hook)
            _feat("network_benchmarking", "Benchmarking", "free"),
            _feat("network_peer_comparison", "Peer Comparison", "free"),
            _feat("network_performance_scores", "Performance Scores", "free"),
            _feat("network_opportunity_highlights", "Opportunity Highlights", "free"),
            # Basic Website
            _feat("website_inventory", "Inventory Website", "free"),
            _feat("website_contact_forms", "Contact Forms", "free"),
            _feat("website_basic_seo", "Basic SEO", "free"),
            _feat("website_mobile_responsive", "Mobile Responsive", "free"),
            # Workforce AI Viewer (see recommendations; execution locked until a Module is bought)
            _feat("workforce_ai_viewer", "Workforce AI Viewer", "free"),
        ],
    },
    "sales": {
        "key": "sales",
        "name": "Sales Module",
        "category": "module",
        "tagline": "Turn the free CRM pipeline into a closing machine.",
        "features": [
            _feat("appointments", "Appointments", "professional"),
            _feat("desking", "Desking", "professional"),
            _feat("trade_evaluation", "Trade Evaluation", "professional"),
            _feat("manager_approval", "Manager Approval Routing", "professional"),
            _feat("up_rotation", "Up-Rotation System", "professional"),
            _feat("digital_retail", "Digital Retail (Start Your Deal Online)", "professional"),
            _feat("ai_sales_agents", "AI Sales Agents", "enterprise"),
        ],
    },
    "service": {
        "key": "service",
        "name": "Service Module",
        "category": "module",
        "tagline": "Run the shop: repair orders, inspections, parts, and the floor.",
        "features": [
            _feat("repair_orders", "Repair Orders", "professional"),
            _feat("dvi", "Digital Vehicle Inspections", "professional"),
            _feat("parts", "Parts", "professional"),
            _feat("warranty", "Warranty", "professional"),
            _feat("shop_control", "Shop Control", "enterprise"),
        ],
    },
    "marketing": {
        "key": "marketing",
        "name": "Marketing Module",
        "category": "module",
        "tagline": "From the free inventory site to a full marketing engine.",
        "features": [
            _feat("website_studio", "Website Studio (builder)", "professional"),
            _feat("email", "Email Marketing", "professional"),
            _feat("sms", "SMS Marketing", "professional"),
            _feat("purls", "PURLs", "professional"),
            _feat("events", "Events", "enterprise"),
            _feat("advertising", "Advertising", "enterprise"),
            _feat("ai_marketing_agent", "AI Marketing Agent", "enterprise"),
        ],
    },
    "finance": {
        "key": "finance",
        "name": "Finance Module",
        "category": "module",
        "tagline": "Contracting through funding -- plus BHPH, collections, and payments.",
        "features": [
            _feat("contracting", "Contracting", "professional"),
            _feat("funding", "Funding", "professional"),
            _feat("lenders", "Lenders", "professional"),
            _feat("fi_products", "F&I Products", "professional"),
            _feat("payments", "Payments", "professional"),
            _feat("collections", "Collections", "professional"),
            _feat("gps_starter_interrupt", "GPS / Starter Interrupt", "enterprise"),
            _feat("bhph", "Buy-Here-Pay-Here", "enterprise"),
        ],
    },
    "operations": {
        "key": "operations",
        "name": "Operations Module",
        "category": "module",
        "tagline": "Recon, compliance, delivery, and task management.",
        "features": [
            _feat("recon", "Recon", "professional"),
            _feat("compliance", "Compliance", "professional"),
            _feat("delivery", "Delivery", "professional"),
            _feat("task_management", "Task Management", "professional"),
        ],
    },
    "ai_workforce": {
        "key": "ai_workforce",
        "name": "AI Workforce Module",
        "category": "module",
        "tagline": "Let the Workforce AI Viewer's recommendations actually execute.",
        "features": [
            _feat("ai_coaching", "AI Coaching", "professional"),
            _feat("ai_coverage", "AI Coverage", "professional"),
            _feat("ai_screen_assistance", "AI Screen Assistance", "professional"),
            _feat("ai_workers", "AI Workers", "enterprise"),
        ],
    },
    "connect": {
        "key": "connect",
        "name": "Connect Module",
        "category": "module",
        "tagline": "Phone, SMS, chat, recording, and conversation intelligence.",
        "features": [
            _feat("phone", "Phone", "professional"),
            _feat("connect_sms", "SMS", "professional"),
            _feat("chat", "Chat", "professional"),
            _feat("recording", "Recording", "professional"),
            _feat("transcripts", "Transcripts", "enterprise"),
            _feat("conversation_intelligence", "Conversation Intelligence", "enterprise"),
        ],
    },
    "network_premium": {
        "key": "network_premium",
        "name": "Network Premium Module",
        "category": "module",
        "tagline": "Upgrade the free Network hook into forecasting and advisory intelligence.",
        "features": [
            _feat("forecasting", "Forecasting", "professional"),
            _feat("ai_advisors", "AI Advisors", "professional"),
            _feat("playbooks", "Playbooks", "professional"),
            _feat("gap_analysis", "Gap Analysis", "enterprise"),
            _feat("executive_insights", "Executive Insights", "enterprise"),
        ],
    },
    # Paid ADD-ON, not a feature Module: NXTDeal's own hosted AI, billed by usage. Selecting the
    # managed "dealeros" AI provider requires this to be on; it is never on in the free model. A
    # dealer can instead bring their own key or a homegrown endpoint at any tier (no add-on needed).
    "dealeros_ai": {
        "key": "dealeros_ai",
        "name": "NXTDeal AI",
        "category": "add_on",
        "tagline": "Our hosted AI, billed by usage -- zero setup, no key to manage. Not in the free tier.",
        "features": [
            _feat("dealeros_managed_inference", "Managed AI inference", "professional"),
        ],
    },
}

# feature_key -> (module_key, required_level). Built once from the catalog.
FEATURE_INDEX = {
    feat["key"]: (mod_key, feat["level"])
    for mod_key, mod in MODULE_CATALOG.items()
    for feat in mod["features"]
}


# ---------------------------------------------------------------------------
# Usage caps (metered Foundation features). Foundation starting defaults from the roadmap's
# "Resolved Direction"; reference profile = unlimited (None).
# ---------------------------------------------------------------------------

USAGE_CAPS = {
    "active_contacts": {
        "name": "Active contacts",
        "unit": "contacts",
        "foundation_default": 250,
        "description": "CRM contacts kept active on the free tier.",
    },
    "inventory_units_online": {
        "name": "Inventory units live on website",
        "unit": "units",
        "foundation_default": 25,
        "description": "Vehicles published to the free Foundation website at once.",
    },
    "report_history_days": {
        "name": "Report history window",
        "unit": "days",
        "foundation_default": 90,
        "description": "How far back Foundation reporting can look.",
    },
    "staff_seats": {
        "name": "Staff seats",
        "unit": "seats",
        "foundation_default": 3,
        "description": "Named staff logins on the free tier.",
    },
}


# ---------------------------------------------------------------------------
# Industry launch paths (the onboarding "Tell Us About Your Business" auto-recommend).
# Reuses the same industry vocabulary as the Hub's Dealer.industry_type. Values are the paid
# Modules to recommend (Foundation basics -- CRM, basic inventory, basic website -- are always
# free, so they are not listed here). BHPH/collections/GPS/payments all resolve to Finance;
# recon/compliance/delivery to Operations; servicing to Service.
# ---------------------------------------------------------------------------

INDUSTRY_LAUNCH_PATHS = {
    "franchise": {
        "label": "Franchise Dealer",
        "recommended_modules": ["sales", "service", "marketing"],
        "spoken": ["Sales", "Service", "Inventory", "Marketing"],
    },
    "independent": {
        "label": "Independent Dealer",
        "recommended_modules": ["sales", "marketing"],
        "spoken": ["Sales", "Inventory", "Marketing"],
    },
    "bhph": {
        "label": "Buy-Here-Pay-Here",
        "recommended_modules": ["finance", "operations"],
        "spoken": ["Inventory", "Finance", "Collections", "GPS", "Payments"],
    },
    "finance_company": {
        "label": "Finance Company",
        "recommended_modules": ["finance", "service"],
        "spoken": ["Servicing", "Payments", "Collections"],
    },
}


def recommend_modules(industry_type):
    """The Modules the onboarding wizard should pre-select for a dealer type. Returns the
    canonical recommended-module keys (empty list for an unknown industry)."""
    path = INDUSTRY_LAUNCH_PATHS.get((industry_type or "").strip().lower())
    return list(path["recommended_modules"]) if path else []


# ---------------------------------------------------------------------------
# Profiles + the entitlement record (state), following system_config's singleton pattern.
# ---------------------------------------------------------------------------

PROFILE_REFERENCE = "reference"
PROFILE_FOUNDATION = "foundation"
PROFILE_CUSTOM = "custom"


def _reference_modules():
    """Every paid Module + add-on on, at the top level -- the full-build reference (Dealer1)."""
    return {m: {"enabled": True, "level": "enterprise"} for m in GATED_KEYS}


def _foundation_modules():
    """Every paid Module + add-on off -- Tier 0 only (managed AI is not in the free model)."""
    return {m: {"enabled": False, "level": "free"} for m in GATED_KEYS}


def _reference_caps():
    return {cap: None for cap in USAGE_CAPS}  # None == unlimited


def _foundation_caps():
    return {cap: spec["foundation_default"] for cap, spec in USAGE_CAPS.items()}


def _default_attributes():
    # DEFAULT is the reference profile so an existing instance keeps everything (see docstring).
    return {
        "profile": PROFILE_REFERENCE,
        "modules": _reference_modules(),
        "caps": _reference_caps(),
        "updated_by": None,
        "updated_at": _now(),
    }


def _get_or_create():
    entity = ledger.get_entity(_ENTITLEMENT_ID)
    if entity and entity.entity_type == ENTITLEMENT:
        # Backfill newly-added Modules / caps onto an already-persisted record, same convention
        # system_config._get_or_create() uses. A never-seen Module inherits the record's current
        # profile posture (reference -> on@enterprise, anything else -> off) so backfill never
        # silently grants a paid Module to a Foundation dealer.
        changed = False
        defaults = _default_attributes()
        for key, value in defaults.items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True

        profile = entity.attributes.get("profile", PROFILE_REFERENCE)
        mods = entity.attributes.setdefault("modules", {})
        for m in GATED_KEYS:
            if m not in mods:
                mods[m] = (
                    {"enabled": True, "level": "enterprise"}
                    if profile == PROFILE_REFERENCE
                    else {"enabled": False, "level": "free"}
                )
                changed = True

        caps = entity.attributes.setdefault("caps", {})
        for cap in USAGE_CAPS:
            if cap not in caps:
                caps[cap] = None if profile == PROFILE_REFERENCE else USAGE_CAPS[cap]["foundation_default"]
                changed = True

        if changed:
            save_graph(GRAPH_PATH)
        return entity

    entity = Entity(id=_ENTITLEMENT_ID, entity_type=ENTITLEMENT, attributes=_default_attributes())
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


# ---------------------------------------------------------------------------
# Read API -- what the running product asks.
# ---------------------------------------------------------------------------

def _module_state(module_key):
    """Raw {enabled, level} for a paid Module; Foundation is a synthetic always-on record."""
    if module_key == FOUNDATION:
        return {"enabled": True, "level": "enterprise"}
    entity = _get_or_create()
    return entity.attributes.get("modules", {}).get(module_key)


def is_module_enabled(module_key):
    """True iff this dealer is entitled to the Module. Foundation is always enabled. An unknown
    key is False (fail CLOSED for typos on a real Module gate -- the opposite of the AI
    kill-switch's fail-open, because here a wrong answer must not silently unlock a paid Module)."""
    if module_key == FOUNDATION:
        return True
    if module_key not in MODULE_CATALOG:
        return False
    state = _module_state(module_key)
    return bool(state and state.get("enabled"))


def module_level(module_key):
    """The owned level ('free'|'professional'|'enterprise') for an enabled Module, else None."""
    if module_key == FOUNDATION:
        return "free"
    if not is_module_enabled(module_key):
        return None
    return _module_state(module_key).get("level", "professional")


def _upgrade_hint(module_key):
    mod = MODULE_CATALOG.get(module_key, {})
    return {
        "module": module_key,
        "module_name": mod.get("name", module_key),
        "tagline": mod.get("tagline"),
    }


def require_module(module_key):
    """Gate a Module feature. Returns None when entitled, else a real error dict the caller can
    return straight to the client (HTTP handlers do `err = require_module(...); if err: return err`).
    The error carries an upgrade hint so the product can show an Add-Modules prompt."""
    if is_module_enabled(module_key):
        return None
    mod = MODULE_CATALOG.get(module_key)
    if not mod:
        return {"error": f"Unknown module '{module_key}'.", "reason": "unknown_module"}
    return {
        "error": f"The {mod['name']} isn't active on your plan.",
        "reason": "module_locked",
        "module": module_key,
        "upgrade": _upgrade_hint(module_key),
    }


def is_feature_available(feature_key):
    """True iff a specific catalog feature is usable. A 'free'-level feature (the Foundation
    baseline) is always available; a professional/enterprise feature needs its Module enabled at
    >= its level. Unknown feature keys fail CLOSED."""
    idx = FEATURE_INDEX.get(feature_key)
    if not idx:
        return False
    module_key, required_level = idx
    if required_level == "free":
        return True
    owned = module_level(module_key)
    if owned is None:
        return False
    return LEVEL_RANK[owned] >= LEVEL_RANK[required_level]


def feature_status(feature_key):
    """Full locked-state detail for one feature -- powers the in-product locked UI (Phase 5)."""
    idx = FEATURE_INDEX.get(feature_key)
    if not idx:
        return {"feature": feature_key, "available": False, "reason": "unknown_feature"}
    module_key, required_level = idx
    owned = module_level(module_key)
    available = is_feature_available(feature_key)
    return {
        "feature": feature_key,
        "module": module_key,
        "required_level": required_level,
        "owned_level": owned,
        "available": available,
        "reason": None if available else ("module_locked" if owned is None else "level_locked"),
        "upgrade": None if available else _upgrade_hint(module_key),
    }


def usage_cap(cap_key):
    """The numeric cap for a metered Foundation feature, or None for unlimited."""
    entity = _get_or_create()
    return entity.attributes.get("caps", {}).get(cap_key)


def check_usage(cap_key, current_count):
    """Whether one more of a metered thing is allowed. None cap == unlimited. Unknown cap ==
    unlimited (fail open -- an un-metered feature is never a paywall)."""
    if cap_key not in USAGE_CAPS:
        return {"allowed": True, "cap": None, "current": current_count, "remaining": None, "reason": "unmetered"}
    cap = usage_cap(cap_key)
    if cap is None:
        return {"allowed": True, "cap": None, "current": current_count, "remaining": None}
    remaining = max(0, cap - current_count)
    return {
        "allowed": current_count < cap,
        "cap": cap,
        "current": current_count,
        "remaining": remaining,
        "reason": None if current_count < cap else "cap_reached",
    }


def active_modules():
    """The Module keys this dealer is entitled to (Foundation always included)."""
    return [FOUNDATION] + [m for m in PAID_MODULES if is_module_enabled(m)]


def module_levels():
    """module_key -> owned level, for every ENABLED module (Foundation = 'free')."""
    out = {FOUNDATION: "free"}
    for m in PAID_MODULES:
        lvl = module_level(m)
        if lvl is not None:
            out[m] = lvl
    return out


def active_add_ons():
    """Enabled paid ADD-ONs (kept separate from active_modules so module attach-rate math over the
    eight feature Modules is unaffected)."""
    return [a for a in ADD_ONS if is_module_enabled(a)]


def is_managed_ai_available():
    """True iff this dealer has the NXTDeal AI add-on -- the gate for the managed 'dealeros' AI
    provider. Never true on the free Foundation profile."""
    return is_module_enabled("dealeros_ai")


def get_entitlements():
    """The full entitlement record (state + resolved conveniences) -- the admin/console read."""
    entity = _get_or_create()
    a = entity.attributes
    return {
        "id": entity.id,
        "profile": a.get("profile", PROFILE_REFERENCE),
        "modules": a.get("modules", {}),
        "caps": a.get("caps", {}),
        "active_modules": active_modules(),
        "module_levels": module_levels(),
        "add_ons": active_add_ons(),
        "managed_ai_available": is_managed_ai_available(),
        "updated_by": a.get("updated_by"),
        "updated_at": a.get("updated_at"),
    }


def public_entitlements():
    """The read-only, non-sensitive slice a customer-facing app (no staff session) may fetch to
    gate its own screens -- just the active-module set and owned levels."""
    return {"active_modules": active_modules(), "module_levels": module_levels()}


def get_catalog():
    """The full Module + feature + cap + launch-path catalog (static; the product's price sheet)."""
    return {
        "foundation_key": FOUNDATION,
        "paid_modules": list(PAID_MODULES),
        "add_ons": list(ADD_ONS),
        "levels": list(LEVELS),
        "modules": MODULE_CATALOG,
        "usage_caps": USAGE_CAPS,
        "industry_launch_paths": INDUSTRY_LAUNCH_PATHS,
    }


# ---------------------------------------------------------------------------
# Write API -- admin edits (mirrors the Hub's Module Management / Licensing intent, but
# tenant-side and actually enforced). Every setter returns the fresh record or an {"error": ...}.
# ---------------------------------------------------------------------------

def set_profile(profile, updated_by):
    """Switch the whole record to a named profile. 'reference' = full build (everything on),
    'foundation' = Tier 0 only with starting caps."""
    entity = _get_or_create()
    if profile == PROFILE_REFERENCE:
        entity.attributes["modules"] = _reference_modules()
        entity.attributes["caps"] = _reference_caps()
    elif profile == PROFILE_FOUNDATION:
        entity.attributes["modules"] = _foundation_modules()
        entity.attributes["caps"] = _foundation_caps()
    else:
        return {"error": f"Unknown profile '{profile}'. Valid: reference, foundation."}
    entity.attributes["profile"] = profile
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_entitlements()


def set_module(module_key, enabled, updated_by, level=None):
    """Enable/disable one paid Module or add-on (and optionally set its level). Editing an
    individual Module moves the record to the 'custom' profile."""
    if module_key not in GATED_KEYS:
        return {"error": f"Unknown paid module '{module_key}'. Valid: {list(GATED_KEYS)}"}
    if level is not None and level not in LEVELS:
        return {"error": f"Unknown level '{level}'. Valid: {list(LEVELS)}"}
    entity = _get_or_create()
    mods = entity.attributes.setdefault("modules", {})
    current = mods.get(module_key, {"enabled": False, "level": "professional"})
    new_level = level or current.get("level") or "professional"
    mods[module_key] = {"enabled": bool(enabled), "level": new_level}
    entity.attributes["profile"] = PROFILE_CUSTOM
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_entitlements()


def set_cap(cap_key, value, updated_by):
    """Set a usage cap (int) or lift it (value=None -> unlimited). Adjustable per dealer, the
    same way Licensing feature flags are -- these are starting points, not fixed limits."""
    if cap_key not in USAGE_CAPS:
        return {"error": f"Unknown usage cap '{cap_key}'. Valid: {list(USAGE_CAPS)}"}
    if value is not None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return {"error": "Cap value must be an integer or null (unlimited)."}
        if value < 0:
            return {"error": "Cap value cannot be negative."}
    entity = _get_or_create()
    entity.attributes.setdefault("caps", {})[cap_key] = value
    if entity.attributes.get("profile") != PROFILE_CUSTOM:
        entity.attributes["profile"] = PROFILE_CUSTOM
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return get_entitlements()
