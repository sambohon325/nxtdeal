"""
core/system_config.py -- Administration's "Organizations" + "System
Configuration" items, combined into one real singleton settings record
(Administration Control Center rebuild, continued).

Combined deliberately, not two separate modules: this codebase is one NXTDeal
instance per dealer (see CLAUDE.md's "NXTDeal Hub / Multi-Tenant Architecture"
section) -- "Organizations" here means this ONE dealer's own profile and
locations/rooftops, not multiple separate dealers (that's the Hub's job, a
genuinely different app). No dealership-identity/settings store existed
anywhere in this codebase before this module -- individual features
(core/websites.py's admin_settings, etc.) each grew their own tiny bag of
settings, but nothing held the dealer's own name/address/EIN or platform-wide
defaults (business hours, currency, timezone) in one real place.

Same fixed-id-singleton convention as core/up_system.py's UpRotation -- one
real SystemConfig entity, created on first read if it doesn't exist yet, not a
second parallel JSON file.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SYSTEM_CONFIG
from core.id_generator import IDGenerator

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

_CONFIG_ID = "SYSCFG-00001"

# Prompt-template ids (PROMPT-00001, ...) -- one shared generator instance,
# same convention core/communications_hub.py's own module-level IDGenerator()
# already established. The "PROMPT" counter is registered in
# core/id_generator.py alongside every other id prefix.
id_generator = IDGenerator()

# Performance Readiness (Readiness reframe, item #4 -- "Goal Tracking against
# real pace") -- the 3 departments Sam's own worked examples name a goal
# metric for (Sales: monthly units, Service: monthly labor $, Marketing:
# monthly leads). See core/performance_readiness.py's own module docstring
# for the full reasoning on why this simple, flat per-department numeric
# target lives here rather than waiting on the separately-scoped, richer
# "Strategic Planning" item (objectives/initiatives/budgets) -- a genuine,
# small, working stopgap that Strategic Planning may supersede or extend
# later, not a duplicate of it.
GOAL_TRACKED_DEPARTMENTS = ("sales", "service", "marketing")

FEATURE_FLAGS = (
    "ai_assistant_enabled",
    "compliance_scanning_enabled",
    "bot_coverage_enabled",
    # AI Management (Administration Control Center rebuild, continued) -- one real
    # kill-switch flag per real OpenAI-backed feature in this codebase (confirmed via
    # a full grep for `from openai import`/`OpenAI(` across core/*.py -- see
    # core/ai_management.py's AI_FEATURE_CATALOG for the full mapping). Each flag is
    # actually read by its real consumer function, not just stored -- see
    # core/ai_management.py's docstring.
    "ai_help_enabled",
    "ai_workspace_explain_enabled",
    "ai_email_wizard_enabled",
    "ai_website_wizard_enabled",
    "ai_social_caption_enabled",
    "ai_reputation_autorespond_enabled",
    "ai_receptionist_platform_enabled",
    "ai_advertising_enabled",
    # Readiness Overview's Executive Summary polish step (Enterprise Readiness &
    # Intelligence reframe, Overview slice) -- see core/readiness_summary_wizard.py.
    "ai_readiness_summary_enabled",
    # AI Business Analyst -- Readiness' final capstone (Enterprise Readiness &
    # Intelligence reframe, Reporting/AI Business Analyst slice). Optional
    # phrasing polish over a real, always-correct topic-matched fallback
    # answer -- see core/ai_business_analyst.py.
    "ai_business_analyst_enabled",
    # Network Overview/Opportunities Executive Summary polish step (Network ->
    # NXTDeal Intelligence Network reframe, slice 1) -- see
    # core/network_summary_wizard.py.
    "ai_network_summary_enabled",
    # Network AI Advisors -- 5 real, department-specific Q&A advisors (Intelligence
    # Network reframe, slice 6). Optional phrasing polish over a real, always-correct
    # topic-matched fallback answer -- see core/network_advisors.py.
    "network_advisors_enabled",
    # Communications Hub AI Summary -- summarizes one logged Communication (call/
    # text/email/chat/social) into a real recap + next-step suggestion, grounded
    # strictly in the logged body text (and, for phone calls, the honestly-SIMULATED
    # transcript). Cross-department, not scoped to one department's own AI feature --
    # see core/communications_hub.py.
    "communications_hub_summary_enabled",
    # Customer Journey Engine (2026-07-22, slice 1) -- graph-native lifecycle
    # stage tracking (Awareness -> Lead -> Appointment -> Sale -> Service ->
    # Loyalty -> Repeat) stored directly on the Customer entity. A general
    # feature toggle registering the module (defaults enabled, backfilled like
    # every other flag); slice 1 is AI-free, so this is a plain on/off feature
    # switch, not an OpenAI kill switch -- see core/customer_journey.py.
    "customer_journey_enabled",
    # Customer Journey AI Recommendation (2026-07-22, slice 2) -- the real,
    # isolated OpenAI kill switch for generate_journey_recommendation(): reads a
    # customer's current journey stage + history and recommends the single next
    # best action. Cross-department, mirrors communications_hub_summary_enabled's
    # own per-feature kill switch -- see core/customer_journey.py.
    "customer_journey_recommendation_enabled",
    # Newly-built modules (2026-07-23 integration pass) -- each mirrors the
    # per-feature kill-switch pattern above. loyalty has no AI feature but keeps
    # a module-level enable flag for consistency.
    "accessories_pitch_enabled",
    "equity_upgrade_offer_enabled",
    "inventory_ad_copy_enabled",
    "loyalty_enabled",
    "success_qbr_insights_enabled",
    # AI Consulting Engine (2026-07-23) -- the real, isolated OpenAI kill switch
    # for core/consulting_engine.py's run_consultation(): composes NXTDeal's own
    # already-real cross-department analysis into a four-part (Analysis / Root
    # Cause / Opportunity / Action Plan) strategic consultation. Lives inside
    # Network; mirrors network_advisors_enabled's per-feature kill switch.
    "ai_consulting_engine_enabled",
    # AI Text-Assist (2026-07-23) -- the real, isolated OpenAI kill switch for
    # core/ai_assist.py's assist_text(): a single generic inline text-assist
    # (generate/rewrite/shorten/expand/retone/grammar) reused by every text
    # field across NXTDeal, injected with this dealer's own brand tone/style
    # guidelines (brand_settings below). Cross-department -- every employee uses
    # inline assist -- so it mirrors communications_hub_summary_enabled's own
    # per-feature kill switch rather than a department-scoped one. Its non-AI
    # fallback is a real rule-based text transform, never a blank "AI
    # unavailable" message.
    "ai_assist_enabled",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _default_attributes():
    return {
        # Organization / dealership profile
        "dealership_name": "",
        "dba_name": "",
        "ein": "",
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "phone": "",
        "website_url": "",
        "locations": [],  # [{"name": ..., "address": ..., "is_primary": bool}]
        # System configuration
        "business_hours": {
            "monday": "9:00 AM - 7:00 PM", "tuesday": "9:00 AM - 7:00 PM",
            "wednesday": "9:00 AM - 7:00 PM", "thursday": "9:00 AM - 7:00 PM",
            "friday": "9:00 AM - 7:00 PM", "saturday": "9:00 AM - 6:00 PM",
            "sunday": "Closed",
        },
        "default_currency": "USD",
        "default_timezone": "America/Chicago",
        "feature_flags": {flag: True for flag in FEATURE_FLAGS},
        # Performance Readiness's real Goal Tracking mechanism -- flat
        # department -> monthly numeric target (float), only for
        # GOAL_TRACKED_DEPARTMENTS. Absent key or None value both mean
        # "unset" -- never defaulted to a fabricated target.
        "department_goals": {},
        # Security-hardening pass (2026-07-20, Task #6) -- real, layered AI
        # kill switches on top of feature_flags' own per-feature granularity.
        # See core/ai_kill_switch.py's own module docstring for the full
        # design (dealer-wide/department/bot/workflow-automation scopes).
        # This is one new top-level key, so the existing top-level backfill
        # loop in _get_or_create() picks it up automatically for an
        # already-persisted SystemConfig entity -- no second explicit
        # backfill pass needed here, unlike feature_flags' own nested-dict
        # backfill quirk (that one predates this key and only applies to
        # itself).
        "ai_kill_switches": _default_ai_kill_switches(),
        # AI Management dashboard (2026-07-23) -- the dealer's own brand voice,
        # injected as context into every AI text-assist (core/ai_assist.py) so
        # all generated/rewritten copy is on-brand. brand_tone is the default
        # tone assist_text() falls back to when a caller doesn't pass one; the
        # free-text brand_voice/style_guidelines are extra guidance the prompt
        # passes through verbatim. Backfilled like every other top-level key by
        # _get_or_create().
        "brand_settings": _default_brand_settings(),
        # Reusable named prompt templates an admin can save once and re-run --
        # a list of {id, name, body, created_by, created_at}, ids from the
        # shared PROMPT counter. New top-level key, so _get_or_create()'s own
        # top-level backfill loop picks it up for an existing SystemConfig.
        "prompt_templates": [],
        "updated_by": None,
        "updated_at": _now(),
    }


# Brand tones the AI text-assist offers (core/ai_assist.py's TONES mirrors
# this) -- a small, fixed vocabulary Sam named, not free text, so the tone
# picker and the brand default stay in sync.
BRAND_TONES = ("Professional", "High Energy", "Direct", "Friendly")


def _default_brand_settings():
    return {
        "brand_tone": "Professional",
        "brand_voice": "",
        "style_guidelines": "",
    }


def _default_kill_switch_state():
    return {"active": False, "activated_by": None, "activated_at": None, "reason": None}


def _default_ai_kill_switches():
    return {
        "dealer_wide": _default_kill_switch_state(),
        # department -> state, only for departments that have ever had a
        # switch explicitly set -- an absent department key means "not
        # killed", same "absent means unset, never fabricated" convention
        # department_goals already established just above.
        "departments": {},
        "bot": _default_kill_switch_state(),
        "workflow_automation": _default_kill_switch_state(),
    }


def get_ai_kill_switches():
    """Raw storage read -- core/ai_kill_switch.py is where the real
    gating/resolution logic lives; this is just the persisted state."""

    entity = _get_or_create()
    return entity.attributes.get("ai_kill_switches", _default_ai_kill_switches())


_VALID_KILL_SWITCH_SCOPES = ("dealer_wide", "department", "bot", "workflow_automation")


def set_ai_kill_switch(scope, active, updated_by, reason=None, department=None):
    """One real, generic setter for all 4 kill-switch scopes -- matching this
    codebase's own established preference for one mechanism with a scope
    parameter over several near-duplicate setters (e.g.
    core/permissions_registry.py's single PermissionOverride resolution
    covering every scope). Returns the full, updated ai_kill_switches dict
    on success, or a real {"error": ...} dict."""

    if scope not in _VALID_KILL_SWITCH_SCOPES:
        return {"error": f"Unknown kill-switch scope '{scope}'. Valid: {_VALID_KILL_SWITCH_SCOPES}"}

    if scope == "department" and not department:
        return {"error": "A department is required when scope='department'."}

    entity = _get_or_create()
    switches = entity.attributes.setdefault("ai_kill_switches", _default_ai_kill_switches())

    new_state = {
        "active": bool(active),
        "activated_by": updated_by,
        "activated_at": _now() if active else None,
        "reason": reason if active else None,
    }

    if scope == "department":
        switches.setdefault("departments", {})[department] = new_state
    else:
        switches[scope] = new_state

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return dict(switches)


def _get_or_create():
    entity = ledger.get_entity(_CONFIG_ID)
    if entity and entity.entity_type == SYSTEM_CONFIG:
        # Backfill any new keys added to _default_attributes() since this
        # singleton was first created, same convention used across this
        # codebase for other singletons (e.g. Website's admin_settings).
        defaults = _default_attributes()
        changed = False
        for key, value in defaults.items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True

        # AI Management (Administration Control Center rebuild, continued): the
        # top-level backfill above only catches a brand-new top-level key -- it
        # does NOT reach inside an already-present "feature_flags" dict, so a new
        # flag added to FEATURE_FLAGS (e.g. this session's 8 new AI kill-switch
        # flags) would never get backfilled into an existing SystemConfig entity's
        # stored feature_flags, even though core/ai_management.py's own
        # is_feature_enabled() already fails open (treats a missing flag as
        # enabled) so this was never a functional bug -- just an honesty gap
        # between what's actually stored and what the real default should be.
        # Backfilled explicitly here so the Admin toggle UI shows a real,
        # persisted True rather than an absent key the UI has to interpret.
        stored_flags = entity.attributes.setdefault("feature_flags", {})
        for flag in FEATURE_FLAGS:
            if flag not in stored_flags:
                stored_flags[flag] = True
                changed = True

        if changed:
            save_graph(GRAPH_PATH)
        return entity

    entity = Entity(id=_CONFIG_ID, entity_type=SYSTEM_CONFIG, attributes=_default_attributes())
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


def get_system_config():
    entity = _get_or_create()
    return {"id": entity.id, **entity.attributes}


def update_organization_profile(updated_by, **fields):
    entity = _get_or_create()
    editable = (
        "dealership_name", "dba_name", "ein", "address_line1", "address_line2",
        "city", "state", "zip_code", "phone", "website_url",
    )
    for key, value in fields.items():
        if key in editable and value is not None:
            entity.attributes[key] = value
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def add_location(name, address, updated_by, is_primary=False):
    if not name or not name.strip():
        return {"error": "A location name is required"}

    entity = _get_or_create()
    locations = entity.attributes.setdefault("locations", [])

    if is_primary:
        for loc in locations:
            loc["is_primary"] = False

    locations.append({"name": name.strip(), "address": address, "is_primary": bool(is_primary)})
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def remove_location(index, updated_by):
    entity = _get_or_create()
    locations = entity.attributes.get("locations", [])
    if index < 0 or index >= len(locations):
        return {"error": "Location index out of range"}

    locations.pop(index)
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def update_business_hours(day, hours, updated_by):
    day = (day or "").lower()
    entity = _get_or_create()
    if day not in entity.attributes.get("business_hours", {}):
        return {"error": f"Unknown day '{day}'"}

    entity.attributes["business_hours"][day] = hours
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def update_defaults(updated_by, default_currency=None, default_timezone=None):
    entity = _get_or_create()
    if default_currency is not None:
        entity.attributes["default_currency"] = default_currency
    if default_timezone is not None:
        entity.attributes["default_timezone"] = default_timezone
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def set_feature_flag(flag, enabled, updated_by):
    if flag not in FEATURE_FLAGS:
        return {"error": f"Unknown feature flag '{flag}'. Valid: {FEATURE_FLAGS}"}

    entity = _get_or_create()
    entity.attributes.setdefault("feature_flags", {})[flag] = bool(enabled)
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def get_department_goals():
    """Real, flat department -> monthly numeric target dict -- only the
    departments in GOAL_TRACKED_DEPARTMENTS that an ADMIN/OPERATIONS user has
    actually set a target for. A department with no key here is genuinely
    unset, not defaulted to anything."""

    entity = _get_or_create()
    return dict(entity.attributes.get("department_goals", {}))


def set_department_goal(department, monthly_target, updated_by):
    department = (department or "").lower()
    if department not in GOAL_TRACKED_DEPARTMENTS:
        return {"error": f"Unknown department '{department}' for goal tracking. Valid: {GOAL_TRACKED_DEPARTMENTS}"}

    try:
        target = float(monthly_target)
    except (TypeError, ValueError):
        return {"error": "monthly_target must be a positive number."}

    if target <= 0:
        return {"error": "monthly_target must be a positive number."}

    entity = _get_or_create()
    entity.attributes.setdefault("department_goals", {})[department] = target
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def clear_department_goal(department, updated_by):
    department = (department or "").lower()
    if department not in GOAL_TRACKED_DEPARTMENTS:
        return {"error": f"Unknown department '{department}' for goal tracking. Valid: {GOAL_TRACKED_DEPARTMENTS}"}

    entity = _get_or_create()
    entity.attributes.setdefault("department_goals", {}).pop(department, None)
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


# ---------------------------------------------------------------------------
# Brand settings + prompt templates (AI Management dashboard, 2026-07-23) --
# the dealer's own brand voice powering core/ai_assist.py's on-brand text
# assists, plus reusable named prompt templates. Stored on the same singleton
# SystemConfig record, persisted by the same save_graph() every other setting
# here already uses.
# ---------------------------------------------------------------------------

def get_brand_settings():
    """The dealer's own brand tone/voice/style guidelines. Always returns a
    full dict (falls back to _default_brand_settings() for a record that
    predates this key, though _get_or_create()'s backfill already fills it)."""

    entity = _get_or_create()
    settings = entity.attributes.get("brand_settings") or {}
    defaults = _default_brand_settings()
    # Merge over defaults so a partially-stored dict still returns every key.
    return {**defaults, **settings}


def update_brand_settings(patch, updated_by):
    """Partial patch of brand_settings -- only the keys present in `patch` are
    written, same partial-update convention update_organization_profile()
    already uses. brand_tone must be one of BRAND_TONES; the two free-text
    fields accept any string. Returns the full updated brand_settings dict, or
    a real {"error": ...} dict."""

    patch = patch or {}
    editable = ("brand_tone", "brand_voice", "style_guidelines")

    if "brand_tone" in patch and patch["brand_tone"] is not None:
        if patch["brand_tone"] not in BRAND_TONES:
            return {"error": f"Unknown brand_tone '{patch['brand_tone']}'. Valid: {BRAND_TONES}"}

    entity = _get_or_create()
    settings = entity.attributes.setdefault("brand_settings", _default_brand_settings())

    for key in editable:
        if key in patch and patch[key] is not None:
            settings[key] = patch[key]

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return dict(settings)


def list_prompt_templates():
    """Every saved prompt template, most-recent-first (same ordering
    convention list_communications() already uses)."""

    entity = _get_or_create()
    templates = list(entity.attributes.get("prompt_templates") or [])
    templates.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    return templates


def add_prompt_template(name, body, created_by):
    """Saves a new reusable prompt template. Returns the created template dict,
    or a real {"error": ...} dict on an empty name/body."""

    if not name or not str(name).strip():
        return {"error": "A prompt template requires a non-empty name."}

    if not body or not str(body).strip():
        return {"error": "A prompt template requires a non-empty body."}

    entity = _get_or_create()
    templates = entity.attributes.setdefault("prompt_templates", [])

    template = {
        "id": id_generator.generate("PROMPT"),
        "name": str(name).strip(),
        "body": str(body).strip(),
        "created_by": created_by,
        "created_at": _now(),
    }
    templates.append(template)

    entity.attributes["updated_by"] = created_by
    entity.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return template


def remove_prompt_template(template_id):
    """Deletes a saved prompt template by id. Returns {"removed": template_id}
    on success, or a real {"error": ...} dict when no such template exists."""

    entity = _get_or_create()
    templates = entity.attributes.get("prompt_templates") or []

    for index, template in enumerate(templates):
        if template.get("id") == template_id:
            templates.pop(index)
            entity.attributes["prompt_templates"] = templates
            entity.attributes["updated_at"] = _now()
            save_graph(GRAPH_PATH)
            return {"removed": template_id}

    return {"error": f"No prompt template found with id {template_id}."}
