"""
core/screen_guidance.py -- "Help Me With This Screen" (Sam's own concrete kickoff
ask, 2026-07-19): "I'd like to add this into the bot feature... into the bar...
while the chat bot will make the recommendations, when the user clicks on prompts
they're loaded into the main chat (the chat stays as the interface, the bot is
just its sidekick / prompter)." This is the first, explicitly-scoped slice of
Sam's larger four-pillar "NXTDeal Workforce AI" vision (Assistant/Automation/
Coverage/Coaching) -- the Assistant pillar's "what needs my attention on this
screen right now" half, wired directly into the existing core/bot_tasks.py-backed
BotWidget rather than a parallel system. The rest of that vision (full Coaching
intensity tiers/manager controls/AI Performance Reviews/AI Career Pathing, and an
expanded Coverage Mode with human-review/autonomous execution) is NOT built here
-- described by Sam as future direction, not yet a concrete build request.

Deliberately a COMPOSITION layer, zero new signal-detection -- reuses
core/enterprise_risk_center.py's already-real, already-categorized, already-
severity-scored exception engine (Readiness' own Exceptions/Enterprise Risk
Center capstone) verbatim, filtered per department via DEPARTMENT_EXCEPTION_KEYS,
and reshapes each matched exception into the same {key, title, description,
prompt, priority} contract core/bot_tasks.py's generate_tasks() already
established -- so frontend/components/BotWidget.tsx's existing task-card
rendering + click-to-chat + dismiss mechanism can be reused directly with no new
UI paradigm, matching Sam's own explicit instruction that the chat stays the one
real interaction surface and the bot only ever proposes, never auto-executes.
Clicking a card's prompt hands a plain question to the SAME real, tool-calling AI
assistant (core/ai_assistant.py's ask_ai(), with its own real role-filtered graph
tool access) every other chat message already goes through -- this module makes
no OpenAI call of its own and no graph mutation, pure read/composition.

Sam's own richer "Suggested AI Actions" ask (Explain / Show Me / Do It /
Automate It, four buttons per recommendation) is intentionally NOT built this
pass -- a single clickable prompt (mirroring the existing BotTask card exactly)
is the honest v1 scope Sam's own concrete instruction described; a future slice
can add the other three action verbs once "Do It"/"Automate It" have a real,
safe, reviewed action behind them (this codebase's automation precedent,
core/workflow_automation.py, only supports a small, explicit trigger/action
catalog today -- inventing a fourth here would be exactly the kind of
fabricated-capability shortcut this codebase's own conventions warn against).

Honest scope, stated plainly rather than force-mapped: only the 5 departments
with a real, already-categorized Enterprise Risk Center signal are covered by
DEPARTMENT_EXCEPTION_KEYS (sales/service/finance/operations/inventory).
Administration/Readiness/Network still get an honest empty response with a
note, not a fabricated recommendation -- same "real signal or an honest gap,
never a guess" bar every other AI-recommendation engine in this codebase
already holds (core/network_audit.py, core/lead_record.py's
next_best_action()).

Extended (2026-07-19, same "keep going" instruction) to also compose
core/readiness_recommendations.py's real, already-built 12-rule recommendation
engine (Readiness' "Recommendations" item) as a SECOND real source, via
DEPARTMENT_RECOMMENDATION_KEYS -- deliberately only the rules from that engine
NOT already duplicated by an Enterprise Risk Center exception this module
already surfaces for the same department (e.g. Finance's own funding_delays/
unfunded_contracts/negative_gross_deals/open_compliance_issues exception items
already cover the same real underlying signal readiness_recommendations.py's
finance_funding_delays/finance_unfunded_contracts/finance_negative_gross/
finance_compliance_risk rules just re-wrap -- including both would show the
same real finding twice under two different titles). What's genuinely new per
department: Sales gets sales_show_rate (real Appointment show-rate signal);
Service gets service_type_underperformance (Sam's own "Brake services
underperforming" example, built for real off a real service-type revenue
trend) and service_shop_overload (real technician-overload signal); Finance
gets finance_collections_risk (real Collections Recovery-Risk count); Inventory
gets inventory_aging_action (Sam's own "Wholesale N units, Reduce pricing on M
units" example, built for real); and this is what closes the Marketing gap
entirely -- marketing_channel_performance is the direct real analog to Sam's
own "Leads from Facebook converting 22% higher. Increase budget." example.
Operations still has no second-source item, since readiness_recommendations.py
has no "operations" category at all -- an honest, unchanged gap for that one
department, not silently papered over.

Extended again (2026-07-19, same "keep going" instruction) with three more
department-specific branches that don't fit the generic per-department
filtered-key-list pattern above, since none of them draw from either of the
two composed sources: "readiness" reuses core/readiness_recommendations.py's
own already-curated, cross-department Executive Recommendations feed directly
(every triggered rule at High/Critical severity across every covered
department, already ranked) -- the honest, real answer to "what needs my
attention across the whole dealership right now" for whoever's looking at the
Readiness Overview screen. "administration" reuses core/governance.py's real
Compliance & Governance summaries (open compliance alert count, pending
approval-hierarchy request count), each bucketed through the same
_count_severity helper core/enterprise_risk_center.py already established, so
severity buckets stay consistent across every source in this module; the
pending-approvals card deliberately resolves to Administration's own
"roles_permissions" item, not "governance" -- core/governance.py's own
docstring states plainly that screen is read-only reporting, the real
approve/reject action lives on Roles & Permissions' Approval Hierarchy tab.
"network" reuses core/network_playbooks.py's real, live-checked playbook
library (its own is_currently_active flag re-runs the same real root-cause
diagnostic Gap Analysis's Root Cause Analysis already uses) -- only playbooks
currently flagged active are surfaced, resolving to Network's own real
"playbooks" item. Operations still has no second-source item (see above) --
the one remaining honest, unchanged gap in this whole feature.

Extended a third time (2026-07-19, same "keep going" instruction) to close
Sam's own "Automate It" verb -- every guidance item across every source now
carries a real automation tier (0/1/3), reusing core/network_playbooks.py's
own already-built _automation_score() helper verbatim rather than a second
tier-scoring pass. Only 2 real underlying signals genuinely match one of
core/workflow_automation.py's 3 real trigger types (_TRIGGER_TYPE_BY_KEY,
below) -- everything else honestly reports tier 0, "no automation path yet."
create_automation_rule_from_guidance() is the real, one-click action behind
a tier-1 item's "Automate It" button -- it creates an actual, live
AutomationRule via the existing ADMIN/OPERATIONS-gated create_rule_api(),
with sensible defaults (Create Operations Task, high priority), refusing to
run for a tier-0 (no path) or tier-3 (already covered) item even if called
directly, not just hidden in the UI. Deliberately still does NOT build Sam's
remaining "Do It" verb -- that would need a bespoke, per-recommendation-type
real mutation across many different domains (resolve a compliance alert,
request a document, submit a wholesale offer, etc.), a much larger and
riskier slice than reusing an already-built, already-safe automation-rule
creation action.
"""

from core.enterprise_risk_center import get_risk_center_overview, _count_severity
from core.readiness_recommendations import get_recommendations_overview
from core.governance import get_compliance_governance_summary, get_approval_hierarchy_summary
from core.network_playbooks import get_playbook_library, _automation_score
from core.workflow_automation import TRIGGER_CATALOG
from core.workflow_automation_api import create_rule_api
from core.document_workflows_api import request_document_api
from core.operations_tasks import list_tasks
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# The only 2 real underlying signals (by their raw, unprefixed source key --
# the exception/recommendation engine's own "key" field, not this module's
# "screen_guidance_..." prefixed id) that genuinely match one of
# core/workflow_automation.py's 3 real trigger types. "funding_delays" is
# core/enterprise_risk_center.py's exception key; "finance_funding_delays" is
# the same real signal under core/readiness_recommendations.py's own rule-key
# naming (only ever surfaced via the Readiness executive-recommendations
# reuse, since the per-department dispatch already de-dupes it against the
# exception). Every other key is deliberately left unmapped -- tier 0, an
# honest "no automation path yet," not a guess.
_TRIGGER_TYPE_BY_KEY = {
    "funding_delays": "deal_stage_stalled",
    "finance_funding_delays": "deal_stage_stalled",
    "inventory_aging_action": "vehicle_aging_price",
}

_TRIGGER_DEFAULTS = {
    t["type"]: {p["key"]: p.get("default") for p in t["params"]}
    for t in TRIGGER_CATALOG
}


def _automation_for(raw_key):
    return _automation_score(_TRIGGER_TYPE_BY_KEY.get(raw_key))


def create_automation_rule_from_guidance(role, employee_id, item_key, title):
    """The real, one-click "Automate It" action for a tier-1 guidance item --
    creates a live core/workflow_automation.py AutomationRule via the existing
    ADMIN/OPERATIONS-gated create_rule_api(), with sensible defaults (Create
    Operations Task, high priority). Refuses to run for an item with no
    matching real trigger type (tier 0) or one that's already automated
    (tier 3, a live rule already covers it) -- enforced here, not just hidden
    in the UI, so a direct call can't bypass the same real check."""

    from core.ai_kill_switch import is_bot_enabled
    if not is_bot_enabled():
        return {"error": "The Bot-wide (or dealer-wide) AI kill switch is currently active -- Automate It is disabled."}

    # Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    # Layer"): a second, more granular, default-deny gate on top of the
    # blunt kill switch above -- "Automate It" creates a real, live
    # AutomationRule, one of this codebase's few genuinely unattended
    # mutation surfaces, so it's covered by the same standing capability
    # policy core/bot_coverage.py's auto-mode and core/bot_actions.py's own
    # auto-action already are.
    from core.bot_permissions import is_capability_granted, department_for_employee
    department = department_for_employee(employee_id)
    if not is_capability_granted(
        "bot.action.automate_screen_guidance", employee_id=employee_id, department=department
    ):
        return {
            "error": (
                "Automate It is not currently granted for this employee or "
                "department -- an ADMIN must grant the "
                "bot.action.automate_screen_guidance capability first "
                "(Administration > Roles & Permissions > Bot Permissions)."
            )
        }

    trigger_type = _TRIGGER_TYPE_BY_KEY.get(item_key)
    if not trigger_type:
        return {
            "error": "This item has no matching Workflow Automation trigger "
                     "type yet -- there's nothing real to automate."
        }

    tier = _automation_score(trigger_type)
    if tier["tier"] == 3:
        return {
            "error": "A live Workflow Automation rule already covers this -- "
                     "nothing further to create."
        }

    return create_rule_api(
        role,
        employee_id,
        name=f"Auto: {title}",
        trigger_type=trigger_type,
        trigger_params=_TRIGGER_DEFAULTS.get(trigger_type, {}),
        action_type="create_operations_task",
        action_params={"priority": "high", "detail_template": f"Guidance: {title}"},
        description=f"Created from a 'Help Me With This Screen' recommendation: {title}",
    )


# The only 2 guidance items across this whole surface with a real, safe,
# genuinely BULK-suitable action behind them -- core/document_workflows.py's
# real request_document(), the exact action each exception's own "resolve"
# field already points at ("Request the missing Title document" / "Request
# the missing Deal Jacket / Buyer Order"). Every other item would need a
# bespoke, per-domain mutation (resolve a compliance alert one at a time,
# submit a wholesale offer, negotiate a stalled deal, etc.) -- deliberately
# NOT attempted here, same "one real, safe action beats a fabricated fourth
# verb everywhere" discipline this module's docstring already states.
_DOC_REQUEST_SPEC = {
    "vehicles_missing_titles": {
        "entity_type": "Vehicle", "document_type": "Title", "task_type": "title_processing",
    },
    "contracts_missing_documents": {
        "entity_type": "Deal", "document_type": "Deal Jacket", "task_type": "document_request",
    },
}


def _do_it_for(raw_key):
    return raw_key in _DOC_REQUEST_SPEC


def _already_requested(task_type, entity_id):
    open_tasks = list_tasks(status="open")
    return any(
        t.attributes.get("task_type") == task_type and t.attributes.get("linked_entity_id") == entity_id
        for t in open_tasks
    )


def create_document_requests_from_guidance(role, employee_id, item_key):
    """The real, one-click "Do It" action for the two guidance items with a
    real, safe, bulk-suitable action behind them. Re-derives the current real
    affected-entity list itself straight from core/enterprise_risk_center.py
    -- same "never trust a client-sent id list" discipline
    create_automation_rule_from_guidance() already established for its own
    tier check -- then calls the existing ADMIN/OPERATIONS-gated
    request_document_api() once per entity, skipping any entity that already
    has a real, open request task on file rather than creating a duplicate on
    a repeated click. Batches the writes into one real save_graph() call at
    the end (request_document()'s own default behavior is unaffected for
    every other caller), matching core/websites.py's
    create_website_from_wizard()/core/dealership_events.py's publish_event()
    established batching precedent."""

    if role not in ("ADMIN", "OPERATIONS"):
        return {"error": "Admin/Operations role required."}

    from core.ai_kill_switch import is_bot_enabled
    if not is_bot_enabled():
        return {"error": "The Bot-wide (or dealer-wide) AI kill switch is currently active -- Do It is disabled."}

    # Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    # Layer"): "Do It" bulk-creates real OperationsTask entities across
    # potentially many entities in one click -- the same standing,
    # default-deny capability policy every other unattended bot mutation
    # surface in this codebase is now gated by.
    from core.bot_permissions import is_capability_granted, department_for_employee
    department = department_for_employee(employee_id)
    if not is_capability_granted(
        "bot.action.do_it_screen_guidance", employee_id=employee_id, department=department
    ):
        return {
            "error": (
                "Do It is not currently granted for this employee or "
                "department -- an ADMIN must grant the "
                "bot.action.do_it_screen_guidance capability first "
                "(Administration > Roles & Permissions > Bot Permissions)."
            )
        }

    spec = _DOC_REQUEST_SPEC.get(item_key)
    if not spec:
        return {
            "error": "This item has no matching bulk action yet -- there's "
                     "nothing real to do it with."
        }

    overview = get_risk_center_overview(role)
    if isinstance(overview, dict) and "error" in overview:
        return overview

    all_items = [item for bucket in overview.get("categories", {}).values() for item in bucket]
    by_key = {item["key"]: item for item in all_items}
    guidance_item = by_key.get(item_key)

    if not guidance_item or not guidance_item.get("count"):
        return {
            "error": "Nothing currently flagged for this item -- a real, "
                     "current all-clear, not something to act on."
        }

    entity_type = spec["entity_type"]
    document_type = spec["document_type"]
    task_type = spec["task_type"]

    created = []
    skipped_existing = []
    errors = []

    for entry in guidance_item.get("items", []):
        entity_id = entry.get("id")
        if not entity_id:
            continue
        if _already_requested(task_type, entity_id):
            skipped_existing.append(entity_id)
            continue
        result = request_document_api(
            role, employee_id, entity_type, entity_id, document_type,
            notes="Bulk-requested via 'Help Me With This Screen' -> Do It.",
            _skip_save=True,
        )
        if isinstance(result, dict) and result.get("error"):
            errors.append({"entity_id": entity_id, "error": result["error"]})
        else:
            created.append(entity_id)

    if created:
        save_graph(GRAPH_PATH)

    return {
        "item_key": item_key,
        "document_type": document_type,
        "created_count": len(created),
        "created": created,
        "skipped_existing_count": len(skipped_existing),
        "skipped_existing": skipped_existing,
        "errors": errors,
    }


# Only departments with a real, already-categorized Enterprise Risk Center
# signal are covered this pass -- see module docstring.
DEPARTMENT_EXCEPTION_KEYS = {
    "sales": ["negative_gross_deals", "unfunded_contracts", "open_compliance_issues"],
    "service": ["service_delays"],
    "finance": [
        "unfunded_contracts",
        "funding_delays",
        "negative_gross_deals",
        "open_compliance_issues",
        "data_sync_failures",
    ],
    "operations": [
        "vehicles_missing_titles",
        "contracts_missing_documents",
        "inventory_not_located",
        "recon_delays",
        "data_sync_failures",
    ],
    "inventory": ["vehicles_missing_titles", "inventory_not_located", "recon_delays"],
}

# core/readiness_recommendations.py rule keys to layer in per department --
# deliberately only the ones NOT already duplicating an exception key above for
# the same department. See module docstring for the full per-department
# reasoning. This is also the ONLY source for Marketing, which has no
# DEPARTMENT_EXCEPTION_KEYS entry at all.
DEPARTMENT_RECOMMENDATION_KEYS = {
    "sales": ["sales_show_rate"],
    "service": ["service_type_underperformance", "service_shop_overload"],
    "finance": ["finance_collections_risk"],
    "inventory": ["inventory_aging_action"],
    "marketing": ["marketing_channel_performance"],
}

_NOT_YET_SCOPED_NOTE = (
    "'Help Me With This Screen' doesn't have a real, already-built exception or "
    "recommendation signal mapped for this department yet -- honestly reported as "
    "empty rather than a fabricated suggestion. See core/screen_guidance.py's "
    "DEPARTMENT_EXCEPTION_KEYS / DEPARTMENT_RECOMMENDATION_KEYS."
)


# Numeric, matching core/bot_tasks.py's generate_tasks() BotTask.priority contract
# exactly (higher = more important, sorted descending) -- not the string
# "high"/"medium"/"low" this module's own severity uses internally, so the two
# recommendation sources can render through the exact same frontend BotTask list
# with no per-source special-casing.
_SEVERITY_TO_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}

_PROMPT_TEMPLATES = {
    "vehicles_missing_titles": "Show me the {count} vehicle(s) missing a Title so I can request them.",
    "contracts_missing_documents": "Show me the {count} funded deal(s) missing a Deal Jacket or Buyer Order.",
    "inventory_not_located": "Show me the {count} vehicle(s) with a key reported missing.",
    "data_sync_failures": "Show me the {count} data connection(s) currently failing to sync.",
    "unfunded_contracts": "Show me the {count} deal(s) in contract status that still aren't funded.",
    "funding_delays": "Show me the {count} deal(s) stalled in financing so I can follow up.",
    "negative_gross_deals": "Show me the {count} funded deal(s) with negative gross profit.",
    "recon_delays": "Show me the {count} vehicle(s) sitting in the recon backlog.",
    "service_delays": "Show me the {count} repair order(s) currently stalled or delayed.",
    "open_compliance_issues": "Show me the {count} open compliance alert(s) I need to resolve.",
}


def _priority_for(severity):
    return _SEVERITY_TO_PRIORITY.get(severity, 1)


def _prompt_for(item):
    template = _PROMPT_TEMPLATES.get(
        item["key"], "Help me with the {count} '{title}' item(s)."
    )
    return template.format(count=item.get("count") or 0, title=item.get("title"))


def _readiness_guidance(role):
    """Readiness' own screen guidance -- reuses core/readiness_recommendations.py's
    already-curated Executive Recommendations feed directly rather than a second
    curation pass over its 12 rules."""

    overview = get_recommendations_overview(role)
    executive = overview.get("executive_recommendations") or []

    guidance = []
    for item in executive:
        guidance.append({
            "key": f"screen_guidance_exec_{item['key']}",
            "title": item["title"],
            "description": item.get("finding") or "",
            "prompt": item.get("recommendation") or item.get("finding"),
            "priority": _priority_for(item.get("severity")),
            "severity": item.get("severity"),
            "count": None,
            "basis": item.get("basis"),
            "resolve": item.get("resolve"),
            "source": "executive_recommendation",
            "automation": _automation_for(item["key"]),
            "do_it_available": _do_it_for(item["key"]),
        })
    return guidance


def _administration_guidance(role):
    """Administration's own screen guidance -- reuses core/governance.py's real
    compliance-alert and approval-hierarchy summaries directly. Those two
    functions are role-free at their own layer by design (ACL is meant to be
    applied by the caller, same convention core/administration_menu.py's own
    governance() enforces via its _ADMIN_ONLY_ERROR check) -- so this function
    applies that identical ADMIN/OPERATIONS-only gate itself rather than
    silently inheriting an unrestricted read."""

    if role not in ("ADMIN", "OPERATIONS"):
        return None  # role-denied sentinel, distinct from a real empty/all-clear result

    guidance = []

    compliance = get_compliance_governance_summary()
    open_alerts = compliance.get("by_status", {}).get("open", 0)
    if open_alerts:
        severity = _count_severity(open_alerts)
        guidance.append({
            "key": "screen_guidance_admin_open_compliance_alerts",
            "title": "Open Compliance Alerts",
            "description": f"{open_alerts} real cited-federal-rule compliance alert(s) are still open.",
            "prompt": f"Show me the {open_alerts} open compliance alert(s) I need to resolve.",
            "priority": _priority_for(severity),
            "severity": severity,
            "count": open_alerts,
            "basis": "real",
            "resolve": {
                "department": "Administration",
                "item_key": "governance",
                "hint": "Open Compliance & Governance and resolve or override the alert.",
            },
            "source": "administration_governance",
            "automation": _automation_for("open_compliance_alerts"),
            "do_it_available": _do_it_for("open_compliance_alerts"),
        })

    approvals = get_approval_hierarchy_summary()
    pending = approvals.get("by_status", {}).get("pending", 0)
    if pending:
        severity = _count_severity(pending)
        guidance.append({
            "key": "screen_guidance_admin_pending_approvals",
            "title": "Pending Approval Requests",
            "description": f"{pending} real approval request(s) are waiting on a decision.",
            "prompt": f"Show me the {pending} pending approval request(s) waiting on a decision.",
            "priority": _priority_for(severity),
            "severity": severity,
            "count": pending,
            "basis": "real",
            "resolve": {
                "department": "Administration",
                "item_key": "roles_permissions",
                "hint": "Open Roles & Permissions -> Approval Hierarchy and clear the pending request(s).",
            },
            "source": "administration_governance",
            "automation": _automation_for("pending_approvals"),
            "do_it_available": _do_it_for("pending_approvals"),
        })

    return guidance


def _network_guidance(role):
    """Network's own screen guidance -- reuses core/network_playbooks.py's real,
    live-checked playbook library, surfacing only entries whose is_currently_active
    flag is true (a real root-cause diagnostic re-run, not a static description)."""

    library = get_playbook_library(role)
    guidance = []
    for pb in library.get("playbooks", []):
        if not pb.get("is_currently_active"):
            continue
        finding = pb.get("active_finding") or pb["summary"]
        guidance.append({
            "key": f"screen_guidance_playbook_{pb['key']}",
            "title": pb["title"],
            "description": finding,
            "prompt": f"Walk me through the '{pb['title']}' playbook -- {finding}",
            "priority": 2,
            "severity": "medium",
            "count": None,
            "basis": "real",
            "resolve": {
                "department": "Network",
                "item_key": "playbooks",
                "hint": "Open Playbooks and follow this guide's real steps.",
            },
            "source": "playbook",
            "automation": pb.get("automation_score"),
        })
    return guidance


_SPECIAL_DEPARTMENT_BUILDERS = {
    "readiness": (
        _readiness_guidance,
        "No real Executive Recommendation is currently triggered at High or "
        "Critical severity across any covered department -- a real, current "
        "all-clear (core/readiness_recommendations.py), not an empty placeholder.",
    ),
    "administration": (
        _administration_guidance,
        "No open compliance alerts or pending approval requests right now -- a "
        "real, current all-clear (core/governance.py), not an empty placeholder.",
    ),
    "network": (
        _network_guidance,
        "No curated playbook is currently flagged active against real data right "
        "now -- a real, current all-clear (core/network_playbooks.py), not an "
        "empty placeholder.",
    ),
}


def get_screen_guidance(role, section, employee_id=None):
    """Returns the same {key, title, description, prompt, priority} shape
    core/bot_tasks.py's generate_tasks() already uses, so BotWidget.tsx's existing
    task-card UI (click -> load into main chat, dismiss) works unchanged.

    Composes up to two real sources -- core/enterprise_risk_center.py's
    exception engine and core/readiness_recommendations.py's 12-rule
    recommendation engine (the latter deliberately trimmed to only its
    non-duplicate rules per department, see module docstring) -- into one
    merged, priority-sorted list. Either source can be empty for a given
    department without the other being skipped.

    employee_id (2026-07-19, Coaching Intensity Tiers) is optional and purely
    additive -- when supplied, the final guidance list is run through
    core/coaching.py's real intensity post-processing (Participant/Productive/
    Aggressive); omitted, this behaves exactly as before."""

    from core.coaching import apply_intensity_to_tasks

    dept = (section or "").strip().lower()

    if dept in _SPECIAL_DEPARTMENT_BUILDERS:
        builder, empty_note = _SPECIAL_DEPARTMENT_BUILDERS[dept]
        guidance = builder(role)
        if guidance is None:
            # Role-denied, not a real all-clear -- never conflate the two.
            return {
                "department": dept,
                "guidance": [],
                "error": "Admin/Operations role required.",
            }
        guidance.sort(key=lambda g: g["priority"], reverse=True)
        guidance, intensity, resolved_from = apply_intensity_to_tasks(guidance, employee_id, role=role, department=dept)
        return {
            "department": dept,
            "guidance": guidance,
            "note": None if guidance else empty_note,
            "coaching_intensity": intensity,
            "coaching_intensity_source": resolved_from,
        }

    exception_keys = DEPARTMENT_EXCEPTION_KEYS.get(dept) or []
    recommendation_keys = DEPARTMENT_RECOMMENDATION_KEYS.get(dept) or []

    if not exception_keys and not recommendation_keys:
        return {
            "department": dept or None,
            "guidance": [],
            "note": _NOT_YET_SCOPED_NOTE,
        }

    guidance = []

    if exception_keys:
        overview = get_risk_center_overview(role)

        if isinstance(overview, dict) and "error" in overview:
            return {"department": dept, "guidance": [], "error": overview["error"]}

        all_items = [
            item for bucket in overview.get("categories", {}).values() for item in bucket
        ]
        by_key = {item["key"]: item for item in all_items}

        for key in exception_keys:

            item = by_key.get(key)

            if not item or not item.get("severity") or not item.get("count"):
                # A real, current zero/all-clear -- or the caller's role was denied this
                # specific sub-signal (access_error) -- neither is a suggestion to surface.
                continue

            guidance.append({
                "key": f"screen_guidance_{item['key']}",
                "title": item["title"],
                "description": item.get("note") or "",
                "prompt": _prompt_for(item),
                "priority": _priority_for(item["severity"]),
                "severity": item["severity"],
                "count": item["count"],
                "basis": item.get("basis"),
                "resolve": item.get("resolve"),
                "source": "exception",
                "automation": _automation_for(item["key"]),
                "do_it_available": _do_it_for(item["key"]),
            })

    if recommendation_keys:
        rec_overview = get_recommendations_overview(role)

        rec_by_key = {}
        for bucket in rec_overview.get("categories", {}).values():
            for item in bucket:
                rec_by_key[item["key"]] = item

        for key in recommendation_keys:

            item = rec_by_key.get(key)

            if not item or not item.get("triggered"):
                # A real, current "no recommendation fired" -- or the caller's role
                # was denied this specific sub-signal (access_error, which forces
                # triggered=False) -- neither is a suggestion to surface.
                continue

            guidance.append({
                "key": f"screen_guidance_rec_{item['key']}",
                "title": item["title"],
                "description": item.get("finding") or "",
                "prompt": item.get("recommendation") or item.get("finding"),
                "priority": _priority_for(item.get("severity")),
                "severity": item.get("severity"),
                "count": None,
                "basis": item.get("basis"),
                "resolve": item.get("resolve"),
                "source": "recommendation",
                "automation": _automation_for(item["key"]),
                "do_it_available": _do_it_for(item["key"]),
            })

    guidance.sort(key=lambda g: g["priority"], reverse=True)

    note = (
        None
        if guidance
        else (
            "No active exceptions or recommendations currently flagged for this "
            "department -- a real, current all-clear (core/enterprise_risk_center.py "
            "+ core/readiness_recommendations.py), not an empty placeholder."
        )
    )

    guidance, intensity, resolved_from = apply_intensity_to_tasks(guidance, employee_id, role=role, department=dept)

    return {
        "department": dept,
        "guidance": guidance,
        "note": note,
        "coaching_intensity": intensity,
        "coaching_intensity_source": resolved_from,
    }
