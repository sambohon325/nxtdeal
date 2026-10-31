"""
core/ai_management.py -- admin.pdf's "AI Management" item (Administration Control
Center rebuild, continued 2026-07-18/19).

Research done before writing anything (per this session's own standing discipline):
a full grep of core/*.py for `from openai import`/`OpenAI(` found exactly 9 real,
independently-built OpenAI-backed features across this codebase's whole history --
core/ai_assistant.py (the main tool-calling chat assistant), core/help_api.py (the
floating "?" widget's isolated Q&A), core/workspace_explain.py (chart explanations),
core/email_wizard.py (Email/SMS AI drafting), core/website_wizard.py (website copy,
per-section regen, vehicle descriptions, SEO copy -- 4 real generator functions),
core/social_caption_wizard.py (social post captions), core/reputation.py's
_draft_response() (review auto-response), core/website_chat.py's _draft_ai_reply()
(the AI Receptionist), and core/advertising.py's generate_ad_recommendation() (ad
copy drafts). Every one already follows the same established pattern: an isolated
client (no tool-calling access except ai_assistant.py itself), and a try/except with
an honest fallback on failure -- EXCEPT core/ai_assistant.py's ask_ai(),
core/help_api.py's ask_help_api(), and core/workspace_explain.py's explain_chart(),
which had NO try/except at all before this module (a real, previously-undocumented
resilience gap -- an OpenAI outage would raise an unhandled exception all the way
into the route handler for those three, unlike every other AI feature in this
codebase). Fixed as part of wiring this module's kill switches, since it's the same
touch point.

This sandbox has NO outbound network path to the real OpenAI API at all (confirmed
repeatedly across sessions 112/113's own smoke tests -- every AI call in this
environment falls back to its template fallback with a real APIConnectionError, not
a code defect). That means "AI Management" cannot show real usage/cost/token metrics
pulled from OpenAI itself -- no real API call ever succeeds here. Nothing here
fabricates that. What IS real and honestly buildable: (1) a catalog of which AI
features exist and whether each has a real fallback path, (2) real, working
per-feature kill switches backed by core/system_config.py's FEATURE_FLAGS -- wired
into the actual consumer functions, not just stored-and-ignored the way
`ai_assistant_enabled` had been sitting since it was first added, and (3) lightweight,
honest call-attempt counters (attempted/succeeded/fell_back/blocked), in-memory only
-- same "in-memory, single-process, resets on restart" limitation
core/ws_manager.py's ConnectionManager already documents for this codebase, not
persisted to the graph/audit log on every single call (that would mean a real
save_graph()-scale disk-write cost on this codebase's hottest read path, the main
chat endpoint -- the same class of performance regression session 113's own
trigger_alerts.py fix specifically avoided). Only the ADMIN action of actually
toggling a flag is logged to the real, persisted audit_log (core/audit.py) -- a low-
frequency admin action, not a per-call event, matching this whole rebuild's own
established "reuse the audit log for real admin actions" convention
(core/permissions_registry.py's set_override()/core/compliance.py's create_alert()).

Also surfaced honestly, not silently fixed (out of this module's own scope): a real
route-wiring gap found during this research -- core/help_api.py's ask_help_api() is
imported into api/app.py (line ~538) and a `HelpRequest` Pydantic model is defined
(line ~1303), but NO route ever calls it. The floating "?" widget's "Ask AI" tab has
had no real backend route behind it since it shipped (session 34) -- the same class
of gap sessions 88/89 found and fixed for Compliance/Employee Value/Department
Intelligence/Network/Readiness/the Bot layer. Flagged in this catalog's
`wired_route`/`route_note` fields rather than fixed here, since wiring a missing
route is a different, separate task from AI Management itself.
"""

from datetime import datetime, timezone

from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH
from core.system_config import get_system_config, set_feature_flag


def _now():
    return datetime.now(timezone.utc).isoformat()


# One real catalog entry per real OpenAI-backed feature found by the grep described
# above. `flag` is the real core/system_config.py FEATURE_FLAGS key this feature's
# kill switch is backed by. `wired_route` / `route_note` record whether the feature
# is actually reachable over real HTTP today (a separate, honest finding from
# whether its AI call itself is real).
AI_FEATURE_CATALOG = [
    {
        "key": "ai_assistant",
        "flag": "ai_assistant_enabled",
        "name": "AI Assistant (Workspace Chat)",
        "module": "core.ai_assistant",
        "functions": ["ask_ai"],
        "description": (
            "The main tool-calling assistant behind the /workspace chat -- the "
            "only AI feature in this codebase with real, role-filtered read "
            "access to the graph (core/ai_tools.py)."
        ),
        "has_tool_calling_access": True,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /ai/chat",
    },
    {
        "key": "help_assistant",
        "flag": "ai_help_enabled",
        "name": "Help Widget AI ('Ask AI' tab)",
        "module": "core.help_api",
        "functions": ["ask_help_api"],
        "description": (
            "The floating '?' widget's isolated, non-tool-calling Q&A -- "
            "deliberately separate from the main assistant so it can never "
            "become a side-channel around ai_tools.py's graph ACL."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": False,
        "route_note": (
            "GAP found during this module's own research: ask_help_api() is "
            "imported into api/app.py and a HelpRequest model is defined, but "
            "no route ever calls it -- the widget's 'Ask AI' tab has had no "
            "real backend route since it shipped. Not fixed here (out of "
            "this module's scope); flagged for a future session."
        ),
    },
    {
        "key": "workspace_explain",
        "flag": "ai_workspace_explain_enabled",
        "name": "Workspace Chart Explanations",
        "module": "core.workspace_explain",
        "functions": ["explain_chart"],
        "description": (
            "Explains a chart the caller already has the underlying "
            "already-role-filtered rows for, from the Workspace board."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /workspace-board/explain",
    },
    {
        "key": "email_sms_wizard",
        "flag": "ai_email_wizard_enabled",
        "name": "Email/SMS AI Wizard",
        "module": "core.email_wizard",
        "functions": ["generate_email_copy", "generate_sms_copy"],
        "description": "Drafts email/SMS campaign copy for Marketing's CRM Email/SMS builder.",
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /email-templates/wizard (and related email-templates routes)",
    },
    {
        "key": "website_wizard",
        "flag": "ai_website_wizard_enabled",
        "name": "Website Builder AI Wizard",
        "module": "core.website_wizard",
        "functions": [
            "generate_wizard_copy",
            "regenerate_section_copy",
            "generate_page_seo_copy",
            "generate_vehicle_description",
        ],
        "description": (
            "Drafts hero/about/financing/testimonial copy, per-section rewrites, "
            "SEO meta copy, and vehicle description copy for the Website Builder."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /websites/wizard (and related websites/* routes)",
    },
    {
        "key": "social_caption_wizard",
        "flag": "ai_social_caption_enabled",
        "name": "Social Post Caption Wizard",
        "module": "core.social_caption_wizard",
        "functions": ["generate_caption"],
        "description": "Drafts platform-aware social post captions, optionally grounded in a real vehicle.",
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /social/posts/generate-caption",
    },
    {
        "key": "reputation_autorespond",
        "flag": "ai_reputation_autorespond_enabled",
        "name": "Review Auto-Response",
        "module": "core.reputation",
        "functions": ["auto_respond_review", "_draft_response"],
        "description": (
            "Drafts and auto-applies a real review response. When disabled, "
            "falls back to the same templated response every review response "
            "already falls back to on an AI failure -- disabling this never "
            "leaves a review unanswered, it just stops drafting one with AI."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /reputation/reviews/{review_id}/auto-respond",
    },
    {
        "key": "website_ai_receptionist",
        "flag": "ai_receptionist_platform_enabled",
        "name": "Website Chat AI Receptionist",
        "module": "core.website_chat",
        "functions": ["ai_respond_to_session", "_draft_ai_reply"],
        "description": (
            "Auto-replies to an unclaimed live chat session, grounded in real "
            "live inventory. This is a PLATFORM-WIDE kill switch, distinct from "
            "each individual website's own per-site "
            "admin_settings['ai_receptionist_enabled'] toggle (session 113) -- "
            "a reply only fires when BOTH this platform flag AND that site's "
            "own toggle are on. Disabling this flag overrides every site "
            "regardless of their own per-site setting."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /chat/{session_id}/ai-reply (and the auto-trigger inside send_visitor_message)",
    },
    {
        "key": "advertising_ai",
        "flag": "ai_advertising_enabled",
        "name": "Ad Campaign AI Recommendations",
        "module": "core.advertising",
        "functions": ["generate_ad_recommendation"],
        "description": "Drafts headline/primary text/targeting suggestions for a new ad campaign.",
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /advertising/recommend",
    },
    {
        "key": "readiness_executive_summary",
        "flag": "ai_readiness_summary_enabled",
        "name": "Readiness Executive Summary Polish",
        "module": "core.readiness_summary_wizard",
        "functions": ["polish_executive_summary"],
        "description": (
            "Optional phrasing-only polish of Readiness Overview's Executive "
            "Summary. The underlying facts always come from a real, already-"
            "computed template (core/readiness_overview.py) -- this step "
            "never invents a number; disabling it (or an OpenAI failure) "
            "falls back to that same real templated summary unchanged."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "GET /readiness-overview/overview (and POST /readiness-overview/regenerate-summary)",
    },
    {
        "key": "network_executive_summary",
        "flag": "ai_network_summary_enabled",
        "name": "Network Executive Summary Polish",
        "module": "core.network_summary_wizard",
        "functions": ["polish_network_executive_summary"],
        "description": (
            "Optional phrasing-only polish of the Network Overview/"
            "Opportunities Executive Summary. The underlying facts always "
            "come from a real, already-computed template (core/"
            "network_opportunity_value.py) -- this step never invents a "
            "number; disabling it (or an OpenAI failure) falls back to that "
            "same real templated summary unchanged."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "GET /menu/data?department=Network&item_key=overview (and POST /network-overview/regenerate-summary)",
    },
    {
        "key": "ai_business_analyst",
        "flag": "ai_business_analyst_enabled",
        "name": "AI Business Analyst",
        "module": "core.ai_business_analyst",
        "functions": ["ask_business_analyst"],
        "description": (
            "Readiness' final capstone -- an executive asks a natural-language "
            "question and gets a real, factual answer composed from Business "
            "Health/Enterprise Risk Center/Recommendations/Forecasts data. The "
            "isolated OpenAI call may only phrase an answer from a real, "
            "pre-computed FACTS block it can never add numbers to; its fallback "
            "is a real topic-matching formatter over that same FACTS block, not "
            "a generic 'AI unavailable' message."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /ai-business-analyst/ask",
    },
    {
        "key": "network_advisors",
        "flag": "network_advisors_enabled",
        "name": "Network AI Advisors",
        "module": "core.network_advisors",
        "functions": ["ask_department_advisor"],
        "description": (
            "5 real, department-specific Q&A advisors (Sales/Service/Parts/"
            "F&I/BHPH) on the Network dash -- an isolated OpenAI call may "
            "only phrase an answer from a real, pre-computed per-department "
            "FACTS block (benchmark + gap analysis + curated playbooks, all "
            "already-built Intelligence Network modules); its fallback is a "
            "real topic-matching formatter over that same FACTS block, not "
            "a generic 'AI unavailable' message."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /network-advisors/ask",
    },
    {
        "key": "communications_hub_summary",
        "flag": "communications_hub_summary_enabled",
        "name": "Communications Hub AI Summary",
        "module": "core.communications_hub",
        "functions": ["generate_ai_summary"],
        "description": (
            "Summarizes one logged Communication (call/text/email/chat/social) "
            "into a short recap + next-step suggestion, grounded strictly in "
            "the real logged body text (and, for phone calls, the honestly-"
            "SIMULATED transcript already disclosed on that record) -- never "
            "invents a fact not present in the source text. Cross-department "
            "(Sales/Service/Marketing/Finance/Operations all log through the "
            "same Communication entity), so this isn't scoped to one "
            "department's own AI feature the way email_sms_wizard/"
            "social_caption_wizard are."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /communications-hub/communications/{comm_id}/ai-summary",
    },
    {
        "key": "customer_journey_recommendation",
        "flag": "customer_journey_recommendation_enabled",
        "name": "Customer Journey AI Recommendation",
        "module": "core.customer_journey",
        "functions": ["generate_journey_recommendation"],
        "description": (
            "Recommends the single next best action for one customer based "
            "strictly on their current lifecycle journey stage (Awareness -> "
            "Lead -> Appointment -> Sale -> Service -> Loyalty -> Repeat) and "
            "stage history -- never invents a fact not present in that record. "
            "Cross-department (Marketing owns Awareness/Lead, Sales owns "
            "Appointment/Sale, Service owns Service, everyone shares Loyalty/"
            "Repeat), so this isn't scoped to one department's own AI feature "
            "the way email_sms_wizard/social_caption_wizard are -- same "
            "reasoning as communications_hub_summary."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /customer-journey/customer/{customer_id}/recommendation",
    },
    {
        "key": "accessories_pitch",
        "flag": "accessories_pitch_enabled",
        "name": "Accessories AI Pitch",
        "module": "core.accessories",
        "functions": ["generate_accessory_pitch"],
        "description": (
            "Generates a short, personalized accessories upsell pitch for one "
            "customer based strictly on their vehicle and recorded accessory "
            "interest -- never invents a fact not present in that record. Scoped "
            "to the Sales department's accessories desk."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /accessories/customer/{customer_id}/pitch",
    },
    {
        "key": "equity_upgrade_offer",
        "flag": "equity_upgrade_offer_enabled",
        "name": "Equity Center AI Upgrade Offer",
        "module": "core.equity_center",
        "functions": ["generate_upgrade_offer"],
        "description": (
            "Drafts a personalized upgrade offer for one customer based strictly "
            "on their current loan/equity position and eligible inventory -- "
            "never invents a fact not present in that record. Scoped to the Sales "
            "department's equity center."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /equity-center/customer/{customer_id}/upgrade-offer",
    },
    {
        "key": "inventory_ad_copy",
        "flag": "inventory_ad_copy_enabled",
        "name": "Inventory Advertising AI Ad Copy",
        "module": "core.inventory_advertising",
        "functions": ["generate_ad_copy"],
        "description": (
            "Writes channel-specific advertising copy for one vehicle based "
            "strictly on its real inventory record and the target channel -- "
            "never invents a fact not present in that record. Scoped to the "
            "Marketing department's inventory advertising."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /inventory-advertising/vehicle/{vehicle_id}/ad-copy",
    },
    {
        "key": "success_qbr_insights",
        "flag": "success_qbr_insights_enabled",
        "name": "Success Center AI QBR Insights",
        "module": "core.success_center",
        "functions": ["generate_qbr_insights"],
        "description": (
            "Generates quarterly business review insights for one dealer based "
            "strictly on their recorded success-center metrics and history -- "
            "never invents a fact not present in that record. NXTDeal-internal "
            "(Administration), portfolio-wide across dealers."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /success-center/dealer/{dealer_id}/qbr-insights",
    },
    {
        "key": "ai_consulting_engine",
        "flag": "ai_consulting_engine_enabled",
        "name": "AI Consulting Engine",
        "module": "core.consulting_engine",
        "functions": ["run_consultation"],
        "description": (
            "The strategic centerpiece -- a user asks a plain business question "
            "and gets a structured four-part consulting answer (Analysis, Root "
            "Cause, Opportunity, Action Plan). An isolated OpenAI call may only "
            "phrase the four sections from a real, pre-composed FACTS block that "
            "reuses NXTDeal's own already-real analysis (ai_business_analyst / "
            "network_advisors facts + readiness recommendations + "
            "network_opportunity_value dollar sizing); its fallback is a real, "
            "fact-grounded four-part consultation over that same FACTS block, "
            "never a generic 'AI unavailable' message. Lives inside Network."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /consulting-engine/ask",
    },
    {
        "key": "ai_assist",
        "flag": "ai_assist_enabled",
        "name": "Inline AI Text-Assist",
        "module": "core.ai_assist",
        "functions": ["assist_text"],
        "description": (
            "A single generic inline text-assist (generate/rewrite/shorten/"
            "expand/retone/grammar) reused by every text field across NXTDeal "
            "-- an isolated OpenAI call injected with this dealer's own brand "
            "tone/voice/style guidelines (core/system_config.py's "
            "brand_settings) so all generated copy is on-brand. Cross-"
            "department (every employee uses inline assist), so it isn't scoped "
            "to one department's own AI feature the way email_sms_wizard/"
            "social_caption_wizard are. Its fallback is a real, rule-based text "
            "transform (trim/expand/whitespace+capitalization cleanup), never a "
            "generic 'AI unavailable' blank."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": True,
        "wired_route": True,
        "route_note": "POST /ai-assist",
    },
]

_CATALOG_BY_KEY = {entry["key"]: entry for entry in AI_FEATURE_CATALOG}

# In-memory only, by design -- see this module's own docstring for why this isn't
# persisted per-call. Resets to zero on every process restart, same documented
# limitation as core/ws_manager.py's ConnectionManager.
_CALL_STATS = {}


def _stats_for(feature_key):
    return _CALL_STATS.setdefault(
        feature_key,
        {"attempted": 0, "succeeded": 0, "fell_back": 0, "blocked": 0, "last_outcome": None, "last_at": None},
    )


def record_call_attempt(feature_key, outcome, detail=None, actor=None, prompt_summary=None, output_summary=None):
    """outcome: 'succeeded' | 'fell_back' | 'blocked'. Called by each real AI
    consumer function itself right at its own OpenAI call site -- the
    in-memory `_CALL_STATS` counters below are unchanged from before this
    pass (still in-memory only, see module docstring).

    Security-hardening pass (2026-07-20, Task #5): also writes a real,
    persisted `AiActionLog` entity via core/ai_audit.py's log_action(), on
    top of (not instead of) the in-memory counters. `actor`/`prompt_summary`/
    `output_summary` are all optional and default to None -- fully
    backward-compatible with every existing call site across this codebase,
    which continue to work unchanged. Deferred import (core/ai_audit.py
    imports core/entities.py + core/dealeros.py, neither of which import
    this module, so there's no real circularity risk -- deferred anyway to
    keep this module's own top-level import list minimal and avoid coupling
    every AI feature's import chain to the ledger at module-load time)."""

    stats = _stats_for(feature_key)
    stats["attempted"] += 1
    if outcome in ("succeeded", "fell_back", "blocked"):
        stats[outcome] += 1
    stats["last_outcome"] = outcome
    stats["last_at"] = _now()
    stats["last_detail"] = detail

    from core.ai_audit import log_action

    log_action(
        feature_key,
        outcome,
        actor=actor,
        prompt_summary=prompt_summary,
        output_summary=output_summary,
        detail=detail,
    )

    # NOTE (Freemium roadmap, Phase 5): the AI Spend Governor meters per-user usage by DERIVING it
    # from these AiActionLog entities (actor + feature + outcome + created_at), so there is no extra
    # write on this hot path -- see core/ai_spend.py. Nothing to do here.

    return stats


def is_feature_enabled(feature_key):
    """The real kill-switch check every wired consumer function calls before
    attempting an OpenAI call. Returns True (fail-open) for an unknown feature_key
    or a flag that isn't present in feature_flags yet -- a config record that
    predates a new flag shouldn't silently disable a feature nobody asked to turn
    off.

    Security-hardening pass (2026-07-20, Task #6): checks the broader
    dealer-wide/department-scoped kill switches (core/ai_kill_switch.py)
    FIRST, before this function's own narrower per-feature flag -- a wider
    veto always wins. Deferred import to avoid a circular import
    (core/ai_kill_switch.py's own get_kill_switch_overview() deferred-
    imports THIS module's AI_FEATURE_CATALOG right back)."""

    entry = _CATALOG_BY_KEY.get(feature_key)
    if not entry:
        return True

    from core.ai_kill_switch import is_ai_globally_enabled
    if not is_ai_globally_enabled(feature_key):
        return False

    config = get_system_config()
    flags = config.get("feature_flags", {})
    return bool(flags.get(entry["flag"], True))


def set_feature_enabled(feature_key, enabled, updated_by):
    entry = _CATALOG_BY_KEY.get(feature_key)
    if not entry:
        return {"error": f"Unknown AI feature '{feature_key}'"}

    result = set_feature_flag(entry["flag"], enabled, updated_by)
    if isinstance(result, dict) and result.get("error"):
        return result

    audit_log.record(
        event_type="ai_feature_toggled",
        summary=f"{'Enabled' if enabled else 'Disabled'} AI feature '{entry['name']}'",
        actor=updated_by,
        details={"feature_key": feature_key, "flag": entry["flag"], "enabled": bool(enabled)},
    )
    save_audit_log(AUDIT_PATH)

    return {
        "feature_key": feature_key,
        "name": entry["name"],
        "flag": entry["flag"],
        "enabled": bool(enabled),
    }


def get_call_stats(feature_key=None):
    if feature_key:
        return dict(_stats_for(feature_key))
    return {key: dict(_stats_for(key)) for key in _CATALOG_BY_KEY}


SANDBOX_NETWORK_NOTE = (
    "This environment has no outbound network path to the real OpenAI API -- every "
    "AI call attempted here falls back to its honest template fallback rather than "
    "a real model response. Call-attempt counters below reflect that reality (a "
    "high 'fell_back' count in this environment is expected, not a bug); they are "
    "not a claim about behavior on Sam's own production deployment, where a real "
    "API key with real network access would let these succeed."
)


def build_ai_management_network_snapshot():
    """Coarse, aggregate, non-identity-joinable AI feature snapshot for the NXTDeal
    Hub's per-dealer AI Management screen (Dealer Management rebuild, slice 4 of 5,
    2026-07-19), gated by the SAME DEALEROS_NETWORK_KEY shared secret core/
    network_snapshot.py's build_anonymous_snapshot() already uses for server-to-
    server Hub calls (see core/network_snapshot_api.py's check_network_key,
    reused directly by core/ai_management_network_api.py rather than a second
    copy of the same check).

    Unlike build_anonymous_snapshot(), this response IS meant to be dealer-
    identified on the Hub side -- Sam's own ask is "AI Management... per dealer,"
    the same "this specific dealer's operational status" shape hub/core/
    server_health.py's reachability check and hub/core/dealer_onboarding.py's
    Network Connected check already return (both already tie a live check
    directly back to one dealer_id). DEALEROS_NETWORK_KEY's job is authenticating
    the Hub as a legitimate server-to-server caller, not enforcing anonymization --
    that's a design choice specific to the peer-benchmark snapshot, not a blanket
    rule every route under this key must follow.

    What leaves this process, and why it's judged safe: for each AI_FEATURE_CATALOG
    entry, only its static key/name (identical across every deployment, not a
    per-dealer secret), its current enabled state, and 4 plain integer counters
    (attempted/succeeded/fell_back/blocked). Deliberately OMITTED: `last_detail`
    (a raw string that could carry an exception message with more incidental
    detail than a bare count) and `last_outcome`/`last_at` (no operational value
    add over the 4 counters for this coarse a view). No graph entity, no
    customer or employee record, no PII of any kind is read or returned
    anywhere in this function -- there is nothing here to anonymize in the
    first place, unlike department KPI dollars/unit-counts."""

    config = get_system_config()
    flags = config.get("feature_flags", {})
    stats = get_call_stats()

    features = []
    for entry in AI_FEATURE_CATALOG:
        feature_stats = stats.get(entry["key"], _stats_for(entry["key"]))
        features.append({
            "key": entry["key"],
            "name": entry["name"],
            "enabled": bool(flags.get(entry["flag"], True)),
            "attempted": feature_stats["attempted"],
            "succeeded": feature_stats["succeeded"],
            "fell_back": feature_stats["fell_back"],
            "blocked": feature_stats["blocked"],
        })

    return {
        "submitted_at": _now(),
        "features": features,
        "note": (
            "Real, aggregate, per-feature call-attempt counters -- in-memory "
            "only, resets to zero on every process restart (same limitation as "
            "core/ws_manager.py's ConnectionManager). No token count or dollar "
            "cost is tracked anywhere in this codebase; 'attempted' is the "
            "closest real proxy to a prompt count. This environment has no "
            "outbound path to the real OpenAI API, so 'succeeded' will read 0 "
            "here regardless of real usage on a production deployment with a "
            "working API key."
        ),
    }


def get_ai_management_overview(role=None):
    config = get_system_config()
    flags = config.get("feature_flags", {})
    stats = get_call_stats()

    features = []
    enabled_count = 0
    for entry in AI_FEATURE_CATALOG:
        enabled = bool(flags.get(entry["flag"], True))
        if enabled:
            enabled_count += 1
        features.append({
            **entry,
            "enabled": enabled,
            "stats": stats.get(entry["key"], _stats_for(entry["key"])),
        })

    return {
        "features": features,
        "summary": {
            "total_features": len(AI_FEATURE_CATALOG),
            "enabled_count": enabled_count,
            "disabled_count": len(AI_FEATURE_CATALOG) - enabled_count,
            "features_with_recorded_activity": sum(
                1 for s in stats.values() if s["attempted"] > 0
            ),
            "features_missing_a_real_route": sum(
                1 for entry in AI_FEATURE_CATALOG if not entry["wired_route"]
            ),
        },
        "sandbox_network_note": SANDBOX_NETWORK_NOTE,
    }
