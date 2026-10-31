"""
core/ai_kill_switch.py -- security-hardening pass (2026-07-20), Task #6
"Expand AI kill switch to dealer/department/bot/workflow scope."

core/ai_management.py's own per-feature kill switch (is_feature_enabled()/
set_feature_enabled(), 13 real flags, one per real OpenAI-backed feature)
has been real and load-bearing since the Administration Control Center
rebuild -- every real OpenAI-backed feature already checks its own flag
before attempting a call. What was still missing, and what Sam's own
security-hardening kickoff named explicitly by scope: a genuine EMERGENCY
STOP an admin can reach for that doesn't require remembering (or clicking
through) all 13 individual switches one at a time, plus three scopes the
per-feature switch was never designed to cover at all -- an entire
department's worth of AI capability, the Bot surface's own rules-engine-
driven actions (NOT OpenAI-backed at all, so the existing switch never
touched it), and the workflow-automation engine's own real, on-demand rule
evaluation.

Four layered, ADDITIVE scopes -- none of them replace
core/ai_management.py's existing per-feature switch, every one is checked
ON TOP of it, and none of them replace core/workflow_automation.py's own
existing per-rule set_rule_active() toggle either:

1. DEALER-WIDE.  One real, top-priority flag. When active, every gate in
   this module short-circuits to "disabled," regardless of any narrower
   flag's own state -- the literal "kill everything" emergency stop a real
   incident response would reach for first.

2. DEPARTMENT-SCOPED.  Real NXTDeal Top Menu department names (see
   core/menu_catalog.py's MENU_CATALOG -- Operations/Sales/Service/
   Marketing/Inventory/Finance/Administration/Readiness/Network) each get
   their own real on/off switch. is_ai_globally_enabled(feature_key)
   resolves a feature_key to its owning department via
   DEPARTMENT_FEATURE_MAP (below) and checks that department's switch too.
   Honest, stated design note: only 4 of the 9 real departments (Sales/
   Marketing/Readiness/Network) have any real AI feature mapped to them at
   all -- Service/Finance/Inventory/Operations/Administration have a real,
   confirmed zero-feature gap (no OpenAI-backed capability exists anywhere
   in those departments today, the same finding
   hub/hub_core/dealer_ai_management.py's own AI_AREA_CATALOG already made
   for the Hub's differently-shaped 5-area grouping) -- their own
   department switch still exists for forward compatibility (flipping it
   today is a real, harmless no-op, not an error) but has nothing to gate
   yet. Three features (help_assistant/workspace_explain/
   communications_hub_summary) are genuinely cross-department --
   deliberately NOT mapped to any one department's switch, since gating
   them behind e.g. Sales would incorrectly silence them for every other
   department's own use of the same Help widget or Communications Hub.

3. BOT-WIDE.  Gates core/bot_actions.py's run_action() -- the single real
   choke point for the Bot's own autonomous mutation surface (confirmed via
   grep: called only from core/bot_scheduler.py's real, unattended
   5-minute background tick for "auto" mode coverage, and from tests) --
   plus core/screen_guidance.py's two human-initiated one-click actions,
   create_automation_rule_from_guidance() ("Automate It") and
   create_document_requests_from_guidance() ("Do It"). Deliberately does
   NOT gate read-only recommendation generation (core/bot_tasks.py's
   generate_tasks(), core/screen_guidance.py's get_screen_guidance()) --
   an emergency stop on the Bot's real ability to DO something is the
   actual security-relevant surface here; suppressing the Bot's mere
   suggestions too would just make an admin's own screen less useful with
   no corresponding safety benefit.

4. WORKFLOW-AUTOMATION-WIDE.  Gates core/workflow_automation.py's
   evaluate_rules() at its own single real entry point -- the real,
   on-demand (not a background scheduler) "if this real condition, then
   this real action" rule engine. Distinct from that module's own
   pre-existing per-rule set_rule_active() toggle -- this is the one flip
   that silences every rule at once without an admin having to remember
   which of potentially many individual rules are currently active.

Every switch is a real, audited, ADMIN/OPERATIONS-only mutation
(core/ai_kill_switch_api.py) -- logged to core/audit.py's real audit_log,
same event-then-save pattern core/ai_management.py's own
set_feature_enabled() already established.

Hub emergency push (2026-07-20): hub/hub_core/dealer_ai_kill_switch.py can
push any one of these 4 scopes to a specific, reachable dealer over the
network, server-to-server, gated by the same DEALEROS_NETWORK_KEY shared
secret core/ai_management_network_api.py already uses -- see
api/routers/ai_kill_switch.py's POST /network/ai-kill-switch-push route
and that Hub module's own docstring for the full design. A Hub-pushed
toggle is recorded with updated_by="hub_emergency_push" so the audit trail
always distinguishes a Hub-initiated emergency stop from a local admin's
own action.
"""

from datetime import datetime, timezone

from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH

from core.system_config import (
    get_ai_kill_switches,
    set_ai_kill_switch as _store_set_ai_kill_switch,
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# feature_key (core/ai_management.py's AI_FEATURE_CATALOG) -> the one real
# NXTDeal Top Menu department (core/menu_catalog.py's MENU_CATALOG) that
# feature is judged to belong to, or None for a genuinely cross-department
# feature. Matches the same real per-feature judgment call
# hub/hub_core/dealer_ai_management.py's own AI_AREA_CATALOG already made,
# reshaped onto backend's real 9 department names rather than the Hub's own
# 5-area Sam-requested grouping.
DEPARTMENT_FEATURE_MAP = {
    "ai_assistant": "Sales",
    "email_sms_wizard": "Marketing",
    "website_wizard": "Marketing",
    "social_caption_wizard": "Marketing",
    "reputation_autorespond": "Marketing",
    "website_ai_receptionist": "Marketing",
    "advertising_ai": "Marketing",
    "readiness_executive_summary": "Readiness",
    "ai_business_analyst": "Readiness",
    "network_executive_summary": "Network",
    "network_advisors": "Network",
    # AI Consulting Engine (2026-07-23) -- lives inside Network (this dealer's
    # relationship to the whole network), one step up from the per-department
    # AI Advisors, so it's mapped to the same real Network department switch.
    "ai_consulting_engine": "Network",
    # Cross-department -- deliberately unmapped, see module docstring.
    "help_assistant": None,
    "workspace_explain": None,
    # Communications Hub AI Summary spans Sales/Service/Marketing/Finance/
    # Operations (every department logs through the same Communication
    # entity) -- gating it behind any one department's switch would
    # incorrectly silence it for every other department's own use.
    "communications_hub_summary": None,
    # Customer Journey AI Recommendation (2026-07-22, slice 2) is genuinely
    # cross-department (Marketing owns Awareness/Lead, Sales owns Appointment/
    # Sale, Service owns Service, everyone shares Loyalty/Repeat) -- deliberately
    # unmapped, same reasoning as communications_hub_summary above. This is now a
    # REAL OpenAI-backed feature (core/customer_journey.py's
    # generate_journey_recommendation()), so it is keyed by its real
    # AI_FEATURE_CATALOG key; gating it behind any one department's switch would
    # incorrectly silence it for every other department's own use.
    "customer_journey_recommendation": None,
    # Newly-built modules (2026-07-23 integration pass). accessories_pitch and
    # equity_upgrade_offer are Sales-desk features; inventory_ad_copy is a
    # Marketing feature. success_qbr_insights is NXTDeal-internal and
    # portfolio-wide (spans every dealer's data), so it's deliberately unmapped
    # like the other cross-cutting features above.
    "accessories_pitch": "Sales",
    "equity_upgrade_offer": "Sales",
    "inventory_ad_copy": "Marketing",
    "success_qbr_insights": None,
    # Inline AI Text-Assist (2026-07-23) is genuinely cross-department -- every
    # employee in every department uses it to draft/rewrite any text field --
    # so it's deliberately unmapped, same reasoning as communications_hub_summary
    # above. Gating it behind any one department's switch would incorrectly
    # silence inline assist for every other department's text fields.
    "ai_assist": None,
}

# The real 9 NXTDeal departments (core/menu_catalog.py) -- hardcoded here
# rather than imported live, since this list only needs to stay in sync
# with department NAMES (a rare, deliberate product decision), not with
# menu_catalog.py's much larger, frequently-changing per-department item
# catalog, and importing that whole module here for 9 strings would add an
# import-time dependency this lightweight module doesn't otherwise need.
REAL_DEPARTMENTS = (
    "Operations", "Sales", "Service", "Marketing", "Inventory",
    "Finance", "Administration", "Readiness", "Network",
)


def department_for_feature(feature_key):
    return DEPARTMENT_FEATURE_MAP.get(feature_key)


def _dealer_wide_active():
    return bool(get_ai_kill_switches().get("dealer_wide", {}).get("active"))


def is_ai_globally_enabled(feature_key):
    """The real gate core/ai_management.py's is_feature_enabled() checks on
    top of its own per-feature flag. Returns True (fail-open, matching that
    function's own established convention) unless the dealer-wide switch or
    this feature's owning department's switch is explicitly active."""

    # Freemium roadmap (2026-08-03): the dealer-level master AI switch is the widest veto of all.
    # When a dealership has simply turned AI off (core/ai_spend.py's ai_enabled=False), every
    # catalogued AI feature is off, ahead of the emergency kill switches below. Deferred import to
    # avoid a load-time cycle (ai_spend doesn't import this module, but keep it lazy + guarded so a
    # gate check can never be broken by an import error).
    try:
        from core.ai_spend import dealer_ai_enabled
        if not dealer_ai_enabled():
            return False
    except Exception:
        pass

    switches = get_ai_kill_switches()

    if switches.get("dealer_wide", {}).get("active"):
        return False

    department = department_for_feature(feature_key)
    if department:
        dept_state = switches.get("departments", {}).get(department)
        if dept_state and dept_state.get("active"):
            return False

    return True


def explain_ai_gate(feature_key):
    """Real, human-readable reason a feature is currently gated (or None if
    it isn't) -- for the admin dashboard, not for the hot-path check
    itself."""

    switches = get_ai_kill_switches()

    dealer_wide = switches.get("dealer_wide", {})
    if dealer_wide.get("active"):
        return {
            "gated_by": "dealer_wide",
            "reason": dealer_wide.get("reason"),
            "activated_by": dealer_wide.get("activated_by"),
            "activated_at": dealer_wide.get("activated_at"),
        }

    department = department_for_feature(feature_key)
    if department:
        dept_state = switches.get("departments", {}).get(department)
        if dept_state and dept_state.get("active"):
            return {
                "gated_by": "department",
                "department": department,
                "reason": dept_state.get("reason"),
                "activated_by": dept_state.get("activated_by"),
                "activated_at": dept_state.get("activated_at"),
            }

    return None


def is_bot_enabled():
    """The real gate core/bot_actions.py's run_action() and
    core/screen_guidance.py's two "Automate It"/"Do It" mutating actions
    check before doing anything. Read-only recommendation generation is
    deliberately NOT gated by this -- see module docstring."""

    switches = get_ai_kill_switches()

    if switches.get("dealer_wide", {}).get("active"):
        return False

    return not switches.get("bot", {}).get("active")


def is_workflow_automation_enabled():
    """The real gate core/workflow_automation.py's evaluate_rules() checks
    at its own single entry point before evaluating any rule."""

    switches = get_ai_kill_switches()

    if switches.get("dealer_wide", {}).get("active"):
        return False

    return not switches.get("workflow_automation", {}).get("active")


def _record_toggle(event_type, summary, updated_by, details):
    audit_log.record(
        event_type=event_type,
        summary=summary,
        actor=updated_by,
        details=details,
    )
    save_audit_log(AUDIT_PATH)


def set_dealer_wide_kill_switch(active, updated_by, reason=None):

    result = _store_set_ai_kill_switch("dealer_wide", active, updated_by, reason=reason)
    if isinstance(result, dict) and result.get("error"):
        return result

    _record_toggle(
        event_type="ai_kill_switch_dealer_wide_toggled",
        summary=f"{'ACTIVATED' if active else 'Deactivated'} the dealer-wide AI kill switch"
                + (f" -- {reason}" if active and reason else ""),
        updated_by=updated_by,
        details={"scope": "dealer_wide", "active": bool(active), "reason": reason},
    )

    return result.get("dealer_wide", {})


def set_department_kill_switch(department, active, updated_by, reason=None):

    if department not in REAL_DEPARTMENTS:
        return {"error": f"Unknown department '{department}'. Valid: {REAL_DEPARTMENTS}"}

    result = _store_set_ai_kill_switch(
        "department", active, updated_by, reason=reason, department=department
    )
    if isinstance(result, dict) and result.get("error"):
        return result

    _record_toggle(
        event_type="ai_kill_switch_department_toggled",
        summary=f"{'ACTIVATED' if active else 'Deactivated'} the AI kill switch for "
                f"{department}" + (f" -- {reason}" if active and reason else ""),
        updated_by=updated_by,
        details={"scope": "department", "department": department, "active": bool(active), "reason": reason},
    )

    return result.get("departments", {}).get(department, {})


def set_bot_kill_switch(active, updated_by, reason=None):

    result = _store_set_ai_kill_switch("bot", active, updated_by, reason=reason)
    if isinstance(result, dict) and result.get("error"):
        return result

    _record_toggle(
        event_type="ai_kill_switch_bot_toggled",
        summary=f"{'ACTIVATED' if active else 'Deactivated'} the Bot-wide kill switch"
                + (f" -- {reason}" if active and reason else ""),
        updated_by=updated_by,
        details={"scope": "bot", "active": bool(active), "reason": reason},
    )

    return result.get("bot", {})


def set_workflow_automation_kill_switch(active, updated_by, reason=None):

    result = _store_set_ai_kill_switch("workflow_automation", active, updated_by, reason=reason)
    if isinstance(result, dict) and result.get("error"):
        return result

    _record_toggle(
        event_type="ai_kill_switch_workflow_automation_toggled",
        summary=f"{'ACTIVATED' if active else 'Deactivated'} the Workflow Automation-wide "
                f"kill switch" + (f" -- {reason}" if active and reason else ""),
        updated_by=updated_by,
        details={"scope": "workflow_automation", "active": bool(active), "reason": reason},
    )

    return result.get("workflow_automation", {})


def get_kill_switch_overview():
    """Real, composed dashboard view -- current state of all 4 scopes, plus,
    for each real department, which real AI features it actually governs
    (an honest empty list for the 5 departments with no mapped feature
    today). Deferred import of core.ai_management to avoid a circular
    import (that module deferred-imports THIS module inside its own
    is_feature_enabled(), see that function's own docstring)."""

    from core.ai_management import AI_FEATURE_CATALOG

    switches = get_ai_kill_switches()

    features_by_department = {dept: [] for dept in REAL_DEPARTMENTS}
    cross_department_features = []

    for entry in AI_FEATURE_CATALOG:
        department = DEPARTMENT_FEATURE_MAP.get(entry["key"])
        brief = {"key": entry["key"], "name": entry["name"]}
        if department:
            features_by_department[department].append(brief)
        else:
            cross_department_features.append(brief)

    departments = []
    stored_departments = switches.get("departments", {})
    for dept in REAL_DEPARTMENTS:
        state = stored_departments.get(dept) or {"active": False, "activated_by": None, "activated_at": None, "reason": None}
        departments.append({
            "department": dept,
            "active": bool(state.get("active")),
            "activated_by": state.get("activated_by"),
            "activated_at": state.get("activated_at"),
            "reason": state.get("reason"),
            "governed_features": features_by_department[dept],
        })

    return {
        "dealer_wide": switches.get("dealer_wide", {}),
        "departments": departments,
        "cross_department_features": cross_department_features,
        "bot": switches.get("bot", {}),
        "workflow_automation": switches.get("workflow_automation", {}),
        "generated_at": _now_iso(),
    }
