"""
core/bot_permissions.py -- security-hardening pass (2026-07-20), Task #7
"Build Bot Permission Layer." Sam's own diagnosis of the gap: every one of
the Bot's real, unattended mutation surfaces (core/bot_coverage.py's "auto"
mode, core/bot_actions.py's one real auto-action, and "Help Me With This
Screen"'s "Automate It"/"Do It" one-click actions, core/screen_guidance.py)
was gated only by (a) a coarse ADMIN-only check on who can even open the
coverage screen, and (b) core/ai_kill_switch.py's Task #6 kill switches --
a blunt, all-or-nothing emergency stop, not a standing, granular "which bot
capabilities are actually allowed for this employee/department/dealer"
policy.

This module is deliberately the OPPOSITE default posture from
core/permissions_registry.py's PermissionOverride (default-ALLOW, a role
gets a permission unless an override says no): every one of the 4 real bot
capabilities below is default-DENY -- nothing runs unattended unless a
real, explicit BotCapabilityGrant record says so, at one of three scopes,
most specific wins:

  1. employee scope    -- granted to one specific Employee.
  2. department scope  -- granted to everyone in one of
     core.ai_kill_switch.REAL_DEPARTMENTS.
  3. dealer_wide scope -- granted platform-wide for this one tenant.

Employee-scope beats department-scope beats dealer_wide-scope beats
"nothing granted at all" (== denied). A BotCapabilityGrant record is
itself always a grant of true OR false (mirroring PermissionOverride's own
`granted` field) -- an explicit "granted=False" record at a narrower scope
can override a broader "granted=True" one (e.g. dealer-wide auto-mode is
on, but one specific employee is explicitly excluded), while the true
default-deny posture is simply the absence of ANY active grant at ANY
scope for a given capability.

Same supersede-not-delete pattern PermissionOverride already established:
a new grant for the same (capability_key, scope, scope_target) triple
deactivates the prior one rather than deleting it -- full history stays
inspectable via list_grants_for_scope()/list_all_grants().

The 4 real capability keys, and exactly where each is enforced:

  bot.coverage.auto_mode              -> core.bot_coverage.start_coverage()
      Gates whether "auto" mode (as opposed to "draft", which never
      executes anything) can even be started for a given employee/
      department. Checked once, at admin-click time -- a denied request
      fails loud immediately rather than silently starting a coverage
      window that would never actually execute anything anyway (every
      task core.bot_scheduler.py's 5-minute tick would generate for it
      falls through the per-call check below regardless, but failing at
      creation time is a far better admin experience than a window that
      LOOKS active and silently does nothing for its whole duration).

  bot.action.auto_touch_overdue_leads -> core.bot_actions.run_action()
      Gates the Bot's one real ACTION_HANDLERS entry
      (_touch_overdue_leads), re-checked on every single call (not just
      at coverage-start time), since a grant can be revoked mid-window.

  bot.action.automate_screen_guidance -> core.screen_guidance.
      create_automation_rule_from_guidance() ("Automate It")

  bot.action.do_it_screen_guidance    -> core.screen_guidance.
      create_document_requests_from_guidance() ("Do It")

Department resolution is genuinely two different lookups depending on the
call site, and callers are responsible for picking the right one:
core.bot_coverage.BotCoverage's own `section` field is stored LOWERCASE
(e.g. "sales", core/bot_tasks.py's TASK_CATALOG keys), while a real
Employee.Department attribute is Title Case (e.g. "Sales") -- both must be
run through normalize_department() below before being compared against
core.ai_kill_switch.REAL_DEPARTMENTS, which is itself the reused, canonical
department list (not a second one invented here).

This module does NOT replace core/ai_kill_switch.py's Task #6 switches --
every real call site checks the kill switch first (the blunt emergency
stop), then this module's own granular grant (the standing policy). Either
one alone is sufficient to block an action; both must allow it for the
action to actually proceed.

Every mutation here also logs to core/audit.py's real, already-platform-
wide `audit_log` singleton, same convention every other permission-style
module in this codebase (core/permissions_registry.py, core/
ai_kill_switch.py) already follows.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import BOT_CAPABILITY_GRANT, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, AUDIT_PATH
from core.audit_storage import save_audit_log
from core.audit import audit_log
from core.ai_kill_switch import REAL_DEPARTMENTS


def _now():
    return datetime.now(timezone.utc).isoformat()


SCOPE_EMPLOYEE = "employee"
SCOPE_DEPARTMENT = "department"
SCOPE_DEALER_WIDE = "dealer_wide"
VALID_SCOPES = (SCOPE_EMPLOYEE, SCOPE_DEPARTMENT, SCOPE_DEALER_WIDE)


CAPABILITY_CATALOG = {
    "bot.coverage.auto_mode": {
        "label": "Coverage Mode -- Auto (bot executes tasks unattended)",
        "description": (
            "Whether an admin may start 'auto' mode Bot Coverage for an "
            "absent employee at all -- as opposed to 'draft' mode, which "
            "only ever suggests, never executes."
        ),
        "enforced_at": "core.bot_coverage.start_coverage",
    },
    "bot.action.auto_touch_overdue_leads": {
        "label": "Auto-touch overdue leads",
        "description": (
            "The Bot's one real scheduled auto-action -- resets a covered "
            "employee's overdue leads' follow-up clock, unattended, every "
            "5 minutes, for the life of an active auto-mode coverage "
            "window."
        ),
        "enforced_at": "core.bot_actions.run_action",
    },
    "bot.action.automate_screen_guidance": {
        "label": "\"Automate It\" -- create a live Workflow Automation rule",
        "description": (
            "'Help Me With This Screen''s one-click action that creates a "
            "real, live core.workflow_automation rule from a "
            "recommendation."
        ),
        "enforced_at": "core.screen_guidance.create_automation_rule_from_guidance",
    },
    "bot.action.do_it_screen_guidance": {
        "label": "\"Do It\" -- bulk-create document requests",
        "description": (
            "'Help Me With This Screen''s bulk action that creates a real "
            "OperationsTask per affected entity (e.g. request a Title for "
            "every vehicle currently missing one)."
        ),
        "enforced_at": "core.screen_guidance.create_document_requests_from_guidance",
    },
    "bot.fleet.auto_execute": {
        "label": "Fleet -- auto-execute a recognized team workflow step",
        "description": (
            "Whether an active 'auto' mode team agent (Pillar 4 fleet) may "
            "actually EXECUTE a recognized-workflow step unattended -- and "
            "then only steps on core.bot_fleet.FLEET_SAFE_ACTIONS (which "
            "ships empty; real business mutations are never on it). Every "
            "other step stays a drafted suggestion for a human regardless. "
            "Re-checked per step, on top of the kill switch."
        ),
        "enforced_at": "core.bot_fleet.run_recognized_workflow",
    },
    "ai.worker.autonomous": {
        "label": "AI Workforce -- autonomous mode (worker acts unattended)",
        "description": (
            "Whether a customer-facing AI worker (core.ai_worker, e.g. the AI "
            "Receptionist) may run in 'autonomous' mode and EXECUTE a whitelisted "
            "safe action unattended -- and then only actions on "
            "core.ai_worker.WORKER_SAFE_ACTIONS (route a call, book an "
            "appointment, send a confirmation; nothing financial or contractual). "
            "Draft and assisted modes never require it; autonomous also requires "
            "the AI kill switch on."
        ),
        "enforced_at": "core.ai_worker.activate_worker / handle_interaction",
    },
}


def list_capability_catalog():
    return [{"key": key, **entry} for key, entry in CAPABILITY_CATALOG.items()]


def normalize_department(raw):
    """Title-cases a raw department string (handles both a lowercase
    BotCoverage.section value and an already-Title-Case Employee.Department
    value identically) and validates it against
    core.ai_kill_switch.REAL_DEPARTMENTS -- returns None for anything that
    doesn't resolve to a real department rather than silently accepting a
    typo'd/unknown scope_target."""

    if not raw:
        return None
    candidate = str(raw).strip().title()
    return candidate if candidate in REAL_DEPARTMENTS else None


def department_for_employee(employee_id):
    """Real, direct Employee.Department lookup (Title Case, e.g. "Sales").
    Returns None if the employee doesn't exist or has no Department on
    file -- is_capability_granted() already degrades gracefully to
    dealer_wide-scope-only when department is None."""

    employee = ledger.get_entity(employee_id)
    if not employee or employee.entity_type != EMPLOYEE:
        return None
    return employee.attributes.get("Department")


def _active_grant(capability_key, scope, scope_target=None):
    for e in ledger.get_all().values():
        if (
            e.entity_type == BOT_CAPABILITY_GRANT
            and e.attributes.get("capability_key") == capability_key
            and e.attributes.get("scope") == scope
            and e.attributes.get("scope_target") == scope_target
            and e.attributes.get("active")
        ):
            return e
    return None


def is_capability_granted(capability_key, employee_id=None, department=None):
    """The real default-deny check. Unknown capability keys fail closed.
    Checks employee scope first (most specific), then department scope,
    then dealer_wide scope -- the first scope with ANY active grant record
    (granted=True or granted=False) decides the answer outright, even if a
    broader scope would otherwise allow it. No active grant at any scope
    == denied."""

    if capability_key not in CAPABILITY_CATALOG:
        return False

    if employee_id:
        grant = _active_grant(capability_key, SCOPE_EMPLOYEE, employee_id)
        if grant is not None:
            return bool(grant.attributes.get("granted"))

    normalized_department = normalize_department(department) if department else None
    if normalized_department:
        grant = _active_grant(capability_key, SCOPE_DEPARTMENT, normalized_department)
        if grant is not None:
            return bool(grant.attributes.get("granted"))

    grant = _active_grant(capability_key, SCOPE_DEALER_WIDE, None)
    if grant is not None:
        return bool(grant.attributes.get("granted"))

    return False


def explain_capability_check(capability_key, employee_id=None, department=None):
    """Same real precedence as is_capability_granted(), but returns WHICH
    scope actually decided the answer -- the transparency layer an admin
    screen needs to explain why a given employee can or can't trigger a
    given bot action, matching core.ai_kill_switch.explain_ai_gate()'s own
    established shape for the kill-switch side of this same story."""

    if capability_key not in CAPABILITY_CATALOG:
        return {
            "capability_key": capability_key,
            "granted": False,
            "decided_by": "unknown_capability",
            "scope_target": None,
            "grant_id": None,
            "reason": f"'{capability_key}' is not a real bot capability.",
        }

    if employee_id:
        grant = _active_grant(capability_key, SCOPE_EMPLOYEE, employee_id)
        if grant is not None:
            granted = bool(grant.attributes.get("granted"))
            return {
                "capability_key": capability_key,
                "granted": granted,
                "decided_by": "employee",
                "scope_target": employee_id,
                "grant_id": grant.id,
                "reason": (
                    f"An explicit employee-level grant for {employee_id} "
                    f"{'allows' if granted else 'denies'} this."
                ),
            }

    normalized_department = normalize_department(department) if department else None
    if normalized_department:
        grant = _active_grant(capability_key, SCOPE_DEPARTMENT, normalized_department)
        if grant is not None:
            granted = bool(grant.attributes.get("granted"))
            return {
                "capability_key": capability_key,
                "granted": granted,
                "decided_by": "department",
                "scope_target": normalized_department,
                "grant_id": grant.id,
                "reason": (
                    f"A department-level grant for {normalized_department} "
                    f"{'allows' if granted else 'denies'} this."
                ),
            }

    grant = _active_grant(capability_key, SCOPE_DEALER_WIDE, None)
    if grant is not None:
        granted = bool(grant.attributes.get("granted"))
        return {
            "capability_key": capability_key,
            "granted": granted,
            "decided_by": "dealer_wide",
            "scope_target": None,
            "grant_id": grant.id,
            "reason": f"A dealer-wide grant {'allows' if granted else 'denies'} this.",
        }

    return {
        "capability_key": capability_key,
        "granted": False,
        "decided_by": "default_deny",
        "scope_target": None,
        "grant_id": None,
        "reason": "No active grant exists at any scope -- default-deny.",
    }


def get_effective_capabilities(employee_id, department=None):
    """Every catalog capability plus whether this specific employee
    currently has it, and which scope decided it -- the real per-employee
    view a Bot Permissions admin screen needs."""

    return [
        explain_capability_check(key, employee_id=employee_id, department=department)
        for key in CAPABILITY_CATALOG
    ]


def list_grants_for_scope(scope, scope_target=None):
    grants = [
        e for e in ledger.get_all().values()
        if e.entity_type == BOT_CAPABILITY_GRANT
        and e.attributes.get("scope") == scope
        and e.attributes.get("scope_target") == scope_target
    ]
    grants.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in grants]


def list_all_grants():
    grants = [e for e in ledger.get_all().values() if e.entity_type == BOT_CAPABILITY_GRANT]
    grants.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in grants]


def grant_capability(capability_key, scope, granted, granted_by, scope_target=None, reason=""):
    """Grants or denies one bot capability at one scope. A new record for
    the same (capability_key, scope, scope_target) triple deactivates any
    prior one rather than deleting it -- full history stays inspectable,
    only the currently-active grant changes."""

    if capability_key not in CAPABILITY_CATALOG:
        return {"error": f"Unknown bot capability key '{capability_key}'"}

    if scope not in VALID_SCOPES:
        return {"error": f"Unknown scope '{scope}' -- must be one of {VALID_SCOPES}"}

    normalized_target = None

    if scope == SCOPE_EMPLOYEE:
        if not scope_target:
            return {"error": "scope_target (an employee id) is required for employee scope"}
        employee = ledger.get_entity(scope_target)
        if not employee or employee.entity_type != EMPLOYEE:
            return {"error": f"Employee '{scope_target}' not found"}
        normalized_target = scope_target

    elif scope == SCOPE_DEPARTMENT:
        normalized_target = normalize_department(scope_target)
        if not normalized_target:
            return {
                "error": (
                    f"'{scope_target}' is not a real department -- must be "
                    f"one of {REAL_DEPARTMENTS}"
                )
            }

    # SCOPE_DEALER_WIDE: normalized_target stays None.

    prior = _active_grant(capability_key, scope, normalized_target)
    if prior is not None:
        prior.attributes["active"] = False
        prior.attributes["superseded_at"] = _now()

    grant_id = id_generator.generate("BCAP")
    entity = Entity(
        id=grant_id,
        entity_type=BOT_CAPABILITY_GRANT,
        attributes={
            "capability_key": capability_key,
            "scope": scope,
            "scope_target": normalized_target,
            "granted": bool(granted),
            "reason": reason,
            "active": True,
            "granted_by": granted_by,
            "created_at": _now(),
            "superseded_at": None,
        },
    )
    ledger.add_entity(entity)

    audit_log.record(
        event_type="bot_capability_grant_set",
        summary=(
            f"{'Granted' if granted else 'Denied'} bot capability "
            f"'{capability_key}' at {scope} scope"
            + (f" ({normalized_target})" if normalized_target else "")
        ),
        entity_id=normalized_target or "dealer_wide",
        actor=granted_by,
        details={
            "capability_key": capability_key,
            "scope": scope,
            "scope_target": normalized_target,
            "granted": bool(granted),
            "reason": reason,
        },
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


def revoke_grant(grant_id, actor_employee_id):
    """Deactivates a specific grant outright, reverting that scope back to
    the plain default-deny (or next-broader-scope) state for that one
    capability -- distinct from grant_capability() creating a new,
    opposite-direction record."""

    entity = ledger.get_entity(grant_id)
    if not entity or entity.entity_type != BOT_CAPABILITY_GRANT:
        return {"error": f"Grant '{grant_id}' not found"}

    if not entity.attributes.get("active"):
        return {"error": "This grant is already inactive"}

    entity.attributes["active"] = False
    entity.attributes["superseded_at"] = _now()

    audit_log.record(
        event_type="bot_capability_grant_revoked",
        summary=(
            f"Deactivated bot capability grant {grant_id} "
            f"({entity.attributes.get('capability_key')} @ "
            f"{entity.attributes.get('scope')})"
        ),
        entity_id=entity.attributes.get("scope_target") or "dealer_wide",
        actor=actor_employee_id,
        details={"grant_id": grant_id},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}
