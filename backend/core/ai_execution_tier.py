"""
AI Execution-Tier framework -- security-hardening initiative (Task #8).

Every real AI-adjacent capability in this codebase -- whether it's an OpenAI
call in core/ai_management.py's own AI_FEATURE_CATALOG, or a rules-based
"if this real condition, then this real action" engine like
core/workflow_automation.py's automation rules -- falls into exactly one of
three real, checkable execution tiers, based on ONE question: does a human
review the specific output/action before it takes effect?

    INFORMATIONAL -- pure read/answer. Never mutates the graph. A user reads
    the response and decides what (if anything) to do next. Example:
    core/ai_business_analyst.py's Q&A, core/help_api.py's "Ask AI" tab.

    ASSISTED -- drafts real content (an email, a section of website copy, an
    ad recommendation), but a human must explicitly review and apply/send it
    before it has any real-world effect. The AI never acts on its own.
    Example: core/email_wizard.py's generated copy, only used once a
    marketer clicks Apply on core/marketing_studio.py's own draft.

    AUTONOMOUS -- executes a real mutation/action with NO human review of
    that specific instance before it happens. The AI (or a rules engine
    acting like one) decides AND acts in one step. Example:
    core/reputation.py's auto_respond_review() posting a real review reply
    with nobody reading it first; core/workflow_automation.py's
    evaluate_rules() creating a real OperationsTask or sending a real DM the
    moment its condition is met, unattended.

This module is deliberately a pure, dependency-light COMPOSITION layer over
core/ai_management.py's own AI_FEATURE_CATALOG -- it does not fork or
duplicate that catalog, it classifies it. Nothing here makes an OpenAI call,
mutates the graph, or has any side effect at all; it's a static
classification + a fail-safe lookup helper, matching this codebase's own
established "real rules, never fake AI" convention for exactly this kind of
governance layer (core/network_audit.py, core/collections.py's risk scoring).

Two real, non-OpenAI automation surfaces are also classified here, since
Task #8's own scope explicitly names one of them: they're not OpenAI calls,
but they ARE unattended, decide-and-act systems, and belong in the same
governance conversation as the 13 catalog entries above.

    workflow_automation_rule_engine -- core/workflow_automation.py's
    evaluate_rules(). THE flagship Autonomous-tier surface this task exists
    to gate: see core/permissions_registry.py's new
    "autonomous_ai_rule_activation" Approval Chain, and
    core/workflow_automation.py's own create_rule()/set_rule_active(), which
    now enforce that gate for real -- a newly-created automation rule starts
    INACTIVE and cannot be armed until a real manager-tier-or-higher
    employee approves the linked ApprovalRequest.

    bot_auto_touch_overdue_leads -- core/bot_actions.py's run_action(), the
    Coverage Mode "auto" tier's own real, unattended lead-state mutation
    (session 36-era). Classified here as Autonomous for completeness and
    honest documentation; NOT wired into the new Approval Chain gate by this
    task -- that would be a second, separately-scoped change to
    core/bot_coverage.py's own activation flow, flagged here rather than
    silently expanded into.

Fail-safe default: an unrecognized feature key is reported as Autonomous
with an explicit "unknown feature" rationale, never silently assumed safe --
the strictest tier is always the safe default for something this module has
no real classification for.
"""

from core.ai_management import AI_FEATURE_CATALOG


TIER_INFORMATIONAL = "informational"
TIER_ASSISTED = "assisted"
TIER_AUTONOMOUS = "autonomous"

EXECUTION_TIERS = (TIER_INFORMATIONAL, TIER_ASSISTED, TIER_AUTONOMOUS)

TIER_DESCRIPTIONS = {
    TIER_INFORMATIONAL: (
        "Reads or answers only -- never mutates the graph. A human reads the "
        "output and decides what to do next."
    ),
    TIER_ASSISTED: (
        "Drafts real content, but a human must explicitly review and apply/"
        "send/publish it before it has any real-world effect."
    ),
    TIER_AUTONOMOUS: (
        "Decides and acts in one step, with no human reviewing that specific "
        "instance before it happens -- requires a real Approval Chain "
        "(core/permissions_registry.py) before it may run unattended."
    ),
}

# Real, individually-reasoned classification of every core/ai_management.py
# AI_FEATURE_CATALOG entry, plus the 2 non-OpenAI automation surfaces named
# in this task's own scope. Every entry's rationale states the specific,
# checkable reason for its tier -- never a blanket assumption.
FEATURE_EXECUTION_TIERS = {
    "ai_assistant": {
        "tier": TIER_INFORMATIONAL,
        "rationale": (
            "Tool-calling access is READ-ONLY (core/ai_tools.py's "
            "role-filtered search/get-by-id/get-related) -- ask_ai() never "
            "mutates the graph on its own."
        ),
    },
    "help_assistant": {
        "tier": TIER_INFORMATIONAL,
        "rationale": "A single-call, non-tool-calling Q&A response -- no mutation.",
    },
    "workspace_explain": {
        "tier": TIER_INFORMATIONAL,
        "rationale": "Explains an already-rendered chart/report to the user -- no mutation.",
    },
    "email_sms_wizard": {
        "tier": TIER_ASSISTED,
        "rationale": (
            "Drafts email/SMS copy only -- a marketer must apply it via "
            "core/marketing_studio.py's own draft-review-apply flow or "
            "core/email_templates.py's template editor before it's ever sent."
        ),
    },
    "website_wizard": {
        "tier": TIER_ASSISTED,
        "rationale": (
            "Drafts site copy/section content/SEO meta/vehicle descriptions -- "
            "a builder must review and save it through the Website Builder "
            "before it's ever shown to a real visitor."
        ),
    },
    "social_caption_wizard": {
        "tier": TIER_ASSISTED,
        "rationale": (
            "Drafts a social caption only -- a marketer must apply it via "
            "core/marketing_studio.py's draft-review-apply flow before "
            "core/social_posts.py's publish_post() ever runs."
        ),
    },
    "reputation_autorespond": {
        "tier": TIER_AUTONOMOUS,
        "rationale": (
            "auto_respond_review() drafts AND posts a real review response "
            "in one step, with no human reading it first -- the response is "
            "live the moment the function returns."
        ),
    },
    "website_ai_receptionist": {
        "tier": TIER_AUTONOMOUS,
        "rationale": (
            "Auto-replies to an unclaimed live chat session the instant a "
            "visitor messages, with no employee reviewing that specific "
            "reply before it's sent to the real visitor."
        ),
    },
    "advertising_ai": {
        "tier": TIER_ASSISTED,
        "rationale": (
            "generate_ad_recommendation() only drafts a recommendation -- "
            "create_ad_campaign()/launch_ad_campaign() are separate, "
            "explicit, human-triggered actions in core/advertising.py."
        ),
    },
    "readiness_executive_summary": {
        "tier": TIER_INFORMATIONAL,
        "rationale": (
            "Polishes the phrasing of an already-real, already-computed "
            "templated summary -- never mutates the graph, and the "
            "underlying real template is always the honest fallback."
        ),
    },
    "network_executive_summary": {
        "tier": TIER_INFORMATIONAL,
        "rationale": "Same polish-only pattern as readiness_executive_summary -- no mutation.",
    },
    "ai_business_analyst": {
        "tier": TIER_INFORMATIONAL,
        "rationale": "Q&A over pre-fetched real facts -- no mutation.",
    },
    "network_advisors": {
        "tier": TIER_INFORMATIONAL,
        "rationale": "Q&A over pre-fetched real per-department facts -- no mutation.",
    },
    "communications_hub_summary": {
        "tier": TIER_AUTONOMOUS,
        "rationale": (
            "generate_ai_summary() writes the AI-generated summary directly "
            "onto the communication's own ai_summary field and calls "
            "save_graph() in the same call, with no separate human-review/ "
            "apply step before it's persisted -- unlike email_sms_wizard/"
            "website_wizard/social_caption_wizard/advertising_ai, which only "
            "ever return a draft for a separate, explicit apply action. Not "
            "yet wired into a real Approval Chain gate -- flagged as "
            "separately scoped future work, not silently expanded into by "
            "this task."
        ),
    },
    'customer_journey_recommendation': {"tier": TIER_AUTONOMOUS, "rationale": 'generate_journey_recommendation persists the generated recommendation on the customer without a separate review/apply step; classification does not add an approval gate.'},
    'accessories_pitch': {"tier": TIER_AUTONOMOUS, "rationale": 'generate_accessory_pitch persists generated pitch text on the customer in the same call, without separate review; no customer delivery or approval gate is implied.'},
    'equity_upgrade_offer': {"tier": TIER_AUTONOMOUS, "rationale": 'generate_upgrade_offer persists its generated offer on the customer without separate review; classification does not establish delivery or approval enforcement.'},
    'inventory_ad_copy': {"tier": TIER_ASSISTED, "rationale": 'generate_ad_copy returns draft copy only; applying or publishing that copy requires a separate user action.'},
    'success_qbr_insights': {"tier": TIER_AUTONOMOUS, "rationale": 'generate_qbr_insights persists generated insights on the dealer record without separate review; classification does not add an approval gate.'},
    'ai_consulting_engine': {"tier": TIER_AUTONOMOUS, "rationale": 'run_consultation logs its generated result to the graph without a separate apply step; proposed action-plan steps are not executed and approval enforcement remains separate.'},
    'ai_assist': {"tier": TIER_ASSISTED, "rationale": 'assist_text returns transformed or generated draft text; the caller must explicitly apply it to the edited field.'},
    # Non-AI_FEATURE_CATALOG surfaces, included for complete, honest coverage
    # of every real unattended decide-and-act system in this codebase.
    "workflow_automation_rule_engine": {
        "tier": TIER_AUTONOMOUS,
        "rationale": (
            "core/workflow_automation.py's evaluate_rules() creates a real "
            "OperationsTask or sends a real DM the instant a rule's real "
            "condition is met, unattended -- the flagship surface this task "
            "exists to gate behind a real Approval Chain."
        ),
    },
    "bot_auto_touch_overdue_leads": {
        "tier": TIER_AUTONOMOUS,
        "rationale": (
            "core/bot_actions.py's run_action(), driving Coverage Mode's "
            "'auto' tier -- a real, unattended Lead pipeline-state mutation "
            "with no human reviewing that specific action first. Classified "
            "here for honest documentation; not yet wired into the new "
            "Approval Chain gate by this task -- flagged as separately "
            "scoped future work on core/bot_coverage.py's own activation "
            "flow, not silently expanded into."
        ),
    },
}

_UNKNOWN_FEATURE_RATIONALE = (
    "No real classification exists for this feature key -- defaulting to "
    "the strictest tier (Autonomous) as a fail-safe rather than silently "
    "assuming it's safe."
)


def get_execution_tier(feature_key):
    """Real, fail-safe lookup: returns {"tier": ..., "rationale": ...}. An
    unrecognized key always resolves to Autonomous, never a guessed-safer
    tier -- the whole point of a fail-safe default."""

    entry = FEATURE_EXECUTION_TIERS.get(feature_key)
    if entry:
        return dict(entry)
    return {"tier": TIER_AUTONOMOUS, "rationale": _UNKNOWN_FEATURE_RATIONALE}


def requires_approval_chain(tier):
    """The one real, load-bearing question this whole module exists to
    answer: does this tier require a real Approval Chain
    (core/permissions_registry.py) before it may run unattended?"""

    return tier == TIER_AUTONOMOUS


_NON_CATALOG_SURFACES = [
    {
        "key": "workflow_automation_rule_engine",
        "name": "Workflow Automation Rule Engine",
        "module": "core/workflow_automation.py",
        "functions": ["evaluate_rules", "create_rule", "set_rule_active"],
        "description": (
            "A real, ADMIN-configurable 'if this real condition, then this "
            "real action' rule engine (deal_stage_stalled / lead_no_contact "
            "/ vehicle_aging_price triggers; create_operations_task / "
            "send_notification_dm actions) -- not an OpenAI call, but a real "
            "unattended decide-and-act system, gated the same way."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": None,
        "wired_route": True,
        "route_note": (
            "POST /automation-rules (create), POST /automation-rules/"
            "{rule_id}/active (activate/deactivate) -- activation is now "
            "gated behind a real Approval Chain, see "
            "core/permissions_registry.py's 'autonomous_ai_rule_activation' "
            "chain."
        ),
    },
    {
        "key": "bot_auto_touch_overdue_leads",
        "name": "Bot Coverage Mode -- Auto-Touch Overdue Leads",
        "module": "core/bot_actions.py",
        "functions": ["run_action"],
        "description": (
            "Coverage Mode's 'auto' tier real, unattended Lead pipeline-"
            "state mutation for a covered-absent employee's overdue leads."
        ),
        "has_tool_calling_access": False,
        "fallback_exists": None,
        "wired_route": True,
        "route_note": "Driven by core/bot_scheduler.py's tick loop, not a direct route.",
    },
]


def list_execution_tier_catalog():
    """Merges core.ai_management.AI_FEATURE_CATALOG's 14 real entries with
    the 2 non-catalog automation surfaces above into one real, unified,
    tier-tagged list -- every entry carries its own real execution_tier +
    execution_tier_rationale, computed via the same fail-safe lookup every
    other consumer of this module uses."""

    catalog = []
    for entry in AI_FEATURE_CATALOG:
        tier_info = get_execution_tier(entry["key"])
        catalog.append({
            **entry,
            "execution_tier": tier_info["tier"],
            "execution_tier_rationale": tier_info["rationale"],
        })

    for entry in _NON_CATALOG_SURFACES:
        tier_info = get_execution_tier(entry["key"])
        catalog.append({
            **entry,
            "execution_tier": tier_info["tier"],
            "execution_tier_rationale": tier_info["rationale"],
        })

    return catalog


def get_execution_tier_summary():
    """A real count-by-tier across the full, unified catalog -- e.g. how
    many real surfaces in this codebase currently require Approval Chain
    gating (Autonomous) versus draft-only (Assisted) versus pure read
    (Informational)."""

    catalog = list_execution_tier_catalog()
    counts = {tier: 0 for tier in EXECUTION_TIERS}
    for entry in catalog:
        counts[entry["execution_tier"]] = counts.get(entry["execution_tier"], 0) + 1

    return {
        "total": len(catalog),
        "by_tier": counts,
        "autonomous_requiring_approval": counts.get(TIER_AUTONOMOUS, 0),
    }
