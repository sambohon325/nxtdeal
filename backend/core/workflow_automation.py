"""
core/workflow_automation.py -- admin.pdf's "Workflow Automation" item
(Administration Control Center rebuild, continued 2026-07-18/19). A real,
ADMIN-configurable "if this real condition, then this real action" rule
engine, platform-wide -- deliberately distinct from core/bot_tasks.py's
per-employee suggested-task layer (which surfaces "things you might want to
do" to one logged-in person) and from core/compliance.py's cited-rules gate
(which blocks a specific mutating action at the moment it's attempted). This
module instead watches real, already-computed graph signals and fires a
real, unattended action the moment a rule's condition is met -- no employee
has to be looking at anything for it to happen.

SCOPING DECISION, stated plainly rather than silently under-delivered: rule
evaluation is ON-DEMAND, not a third live background scheduler. This
codebase has exactly two real background-scheduler precedents
(core/bot_scheduler.py, core/compliance_scheduler.py's 12-hour tick), both
narrow and deliberately scoped in their own right. Adding a THIRD live
asyncio background loop autonomously, overnight, with no one watching the
process, is a real, non-trivial operational risk to a production-adjacent
backend (a bug in a new tick loop can degrade every request this process
serves, not just this one feature) -- the same judgment call
core/appointment_scheduling.py's reminder-sending already made explicitly
("Deliberately NOT a background scheduler... an explicit human action from
the board, not an automated job"). evaluate_rules() is instead called
either explicitly (an admin clicks "Run Rules Now") or implicitly on every
fetch of the Automation dashboard (get_automation_dashboard()) -- the same
"compute live on read" convention core/vehicle_holds.py's expires_at and
core/inventory_aging.py's price banding already established. A future
session wiring this into compliance_scheduler.py's existing 12-hour tick
(reusing that tick, not adding a new one) would be a safe, small follow-up
-- deliberately not done here without Sam's own sign-off on running
unattended code on a schedule with no review step.

Trigger catalog (TRIGGER_TYPES) -- three real, already-computable signals,
reusing engines this codebase already built rather than inventing new
computations:
  - "deal_stage_stalled": a real Deal sitting in "financing" or "contract"
    status longer than a real, configurable threshold_hours since its own
    updated_at -- the same HEURISTIC updated_at-as-staleness-proxy
    core/finance_menu.py's funding-aging figure and
    core/collections.py's own delinquency signal already established (Deal
    has no separate "entered this stage at" timestamp, only one shared
    updated_at that moves on every mutation).
  - "lead_no_contact": a real, still-open Lead (PipelineState not in
    SOLD/LOST) with no core/field_notes.py FieldNote logged against it
    within a real, configurable threshold_hours -- reuses
    list_field_notes(linked_entity_id=...) directly rather than a second
    communication-log mechanism, same real signal
    core/lead_record.py's next_best_action() already surfaces per-lead.
  - "vehicle_aging_price": a real unsold Vehicle whose Price is at or above
    a real, configurable min_price threshold -- the same honest price-band
    proxy for aging core/inventory_aging.py/core/workflow_tab_data.py
    already established (Vehicle has no acquisition-date field anywhere in
    this codebase, confirmed absent across sessions 63/85/106/109).

Action catalog (ACTION_TYPES) -- two real, already-real mechanisms:
  - "create_operations_task": core/operations_tasks.py's create_task(),
    task_type "custom", linked_entity_id = the triggering entity, so the
    resulting ticket is a real, trackable, SLA-timed OperationsTask, not a
    fabricated notification.
  - "send_notification_dm": core/messaging.py's real send_direct_message(),
    to a specific, rule-configured employee_id -- the same real DM
    mechanism core/compliance.py's _notify_managers_and_admin() and
    core/trigger_alerts.py already use to reach a human, not a new channel.

Dedup, matching core/compliance.py's run_full_scan()/
core/operations_tasks.py's sync_derived_tasks() precedent: evaluate_rules()
skips firing a rule against an entity it has ALREADY fired for (one
AutomationExecution log entry per (rule_id, target_entity_id) pair, checked
before acting) -- a deliberately simple, permanent dedup (once fired for a
given entity, that rule never re-fires for that same entity again, even if
the condition later re-breaches) rather than a more elaborate
still-open/resolved re-arming state machine, stated here explicitly as a
considered simplification, not an oversight.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import (
    AUTOMATION_RULE,
    AUTOMATION_EXECUTION,
    DEAL,
    LEAD,
    VEHICLE,
    EMPLOYEE,
)

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.operations_tasks import create_task, TASK_TYPES as _OPS_TASK_TYPES
from core.messaging import send_direct_message
from core.field_notes import list_field_notes
from core.workflow_tab_data import _unsold_vehicles, _safe_float

AUTOMATION_ACTOR_ID = "AUTOMATION"

TRIGGER_CATALOG = [
    {
        "type": "deal_stage_stalled",
        "label": "Deal Stalled In Stage",
        "description": (
            "A Deal has sat in 'financing' or 'contract' status longer than "
            "the configured threshold since it was last updated."
        ),
        "params": [
            {"key": "stage", "label": "Deal Stage", "kind": "enum", "options": ["financing", "contract"]},
            {"key": "threshold_hours", "label": "Threshold (hours)", "kind": "number", "default": 48},
        ],
    },
    {
        "type": "lead_no_contact",
        "label": "Lead With No Contact Logged",
        "description": (
            "A still-open Lead has had no communication (call/text/email/video) "
            "logged against it within the configured threshold."
        ),
        "params": [
            {"key": "threshold_hours", "label": "Threshold (hours)", "kind": "number", "default": 72},
        ],
    },
    {
        "type": "vehicle_aging_price",
        "label": "Aging High-Value Vehicle",
        "description": (
            "An unsold Vehicle's price is at or above the configured threshold -- "
            "the honest price-band proxy for aging this codebase already uses "
            "(no acquisition-date field exists to compute real days-on-lot)."
        ),
        "params": [
            {"key": "min_price", "label": "Minimum Price ($)", "kind": "number", "default": 40000},
        ],
    },
]

TRIGGER_TYPES = [t["type"] for t in TRIGGER_CATALOG]

ACTION_CATALOG = [
    {
        "type": "create_operations_task",
        "label": "Create Operations Task",
        "description": "Creates a real, trackable OperationsTask linked to the triggering entity.",
        "params": [
            {"key": "priority", "label": "Task Priority", "kind": "enum", "options": ["low", "normal", "high", "urgent"], "default": "normal"},
            {"key": "detail_template", "label": "Task Detail", "kind": "text", "default": ""},
        ],
    },
    {
        "type": "send_notification_dm",
        "label": "Send Notification DM",
        "description": "Sends a real direct message to a specific employee via the platform's own messaging system.",
        "params": [
            {"key": "notify_employee_id", "label": "Notify Employee ID", "kind": "text", "default": ""},
            {"key": "message_template", "label": "Message", "kind": "text", "default": ""},
        ],
    },
]

ACTION_TYPES = [a["type"] for a in ACTION_CATALOG]


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hours_since(ts):
    dt = _parse(ts)
    if not dt:
        return None
    return (_now() - dt).total_seconds() / 3600


def _all_of_type(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _serialize(entity):
    if isinstance(entity, dict):
        return entity
    return {"id": entity.id, **entity.attributes}


# --- Rule CRUD ---------------------------------------------------------------

def create_rule(name, trigger_type, trigger_params, action_type, action_params, created_by, description=""):

    if trigger_type not in TRIGGER_TYPES:
        return {"error": f"trigger_type must be one of {TRIGGER_TYPES}"}

    if action_type not in ACTION_TYPES:
        return {"error": f"action_type must be one of {ACTION_TYPES}"}

    if action_type == "send_notification_dm":
        notify_id = (action_params or {}).get("notify_employee_id")
        target = ledger.get_entity(notify_id) if notify_id else None
        if not target or target.entity_type != EMPLOYEE:
            return {"error": "send_notification_dm requires a valid notify_employee_id"}

    rule_id = id_generator.generate("AUTOR")

    # Security-hardening pass (2026-07-20, Task #8): the whole rule engine is
    # classified AUTONOMOUS by core/ai_execution_tier.py ("workflow_automation_
    # rule_engine" -- it decides-and-acts unattended, no human reviews a fired
    # action before it happens), and requires_approval_chain(TIER_AUTONOMOUS)
    # is True -- so a brand-new rule can never start active anymore. A real
    # ApprovalRequest is created via core/permissions_registry.py's existing
    # tier-gated Approval Hierarchy mechanism ("autonomous_ai_rule_activation"
    # chain, one real manager-tier step) -- set_rule_active() below refuses to
    # flip is_active True until that request's own real status resolves to
    # "approved". Deferred import, same circular-import-avoidance convention
    # core/loan_servicing.py's own get_loan_financials() already established.
    from core.permissions_registry import create_approval_request

    approval = create_approval_request(
        chain_key="autonomous_ai_rule_activation",
        requested_by=created_by,
        subject=f"Activate automation rule: {name}",
        details=f"Trigger: {trigger_type} -> Action: {action_type}",
        entity_id=rule_id,
    )
    if isinstance(approval, dict) and approval.get("error"):
        return approval

    entity = Entity(
        id=rule_id,
        entity_type=AUTOMATION_RULE,
        attributes={
            "name": name,
            "description": description or "",
            "trigger_type": trigger_type,
            "trigger_params": trigger_params or {},
            "action_type": action_type,
            "action_params": action_params or {},
            "is_active": False,
            "execution_tier": "autonomous",
            "approval_request_id": approval["id"],
            "approval_status": approval.get("status", "pending"),
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "last_run_at": None,
            "times_fired": 0,
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def list_rules(active_only=False):

    rules = _all_of_type(AUTOMATION_RULE)

    if active_only:
        rules = [r for r in rules if r.attributes.get("is_active")]

    rules.sort(key=lambda r: r.attributes.get("created_at", ""), reverse=True)

    return rules


def get_rule(rule_id):
    entity = ledger.get_entity(rule_id)
    if entity and entity.entity_type == AUTOMATION_RULE:
        return entity
    return None


def set_rule_active(rule_id, is_active, updated_by):
    """Security-hardening pass (2026-07-20, Task #8): every rule this engine
    creates is AUTONOMOUS tier (see create_rule()'s own comment above) --
    activating one for real requires its linked ApprovalRequest to have
    actually cleared its real manager-tier approval step first. Re-fetches
    the request's LIVE status on every activation attempt rather than
    trusting a possibly-stale stored approval_status, so a rejected/still-
    pending request can never be silently bypassed by re-clicking Activate.
    Deactivating (is_active=False) stays ungated -- turning an automation
    off is never the risky direction."""

    rule = get_rule(rule_id)
    if not rule:
        return {"error": "Rule not found"}

    if is_active:

        from core.permissions_registry import get_approval_request

        approval_request_id = rule.attributes.get("approval_request_id")
        if not approval_request_id:
            return {"error": "This rule has no linked approval request -- cannot activate."}

        approval = get_approval_request(approval_request_id)
        if isinstance(approval, dict) and approval.get("error"):
            return approval

        live_status = approval.get("status")
        rule.attributes["approval_status"] = live_status

        if live_status != "approved":
            return {
                "error": (
                    f"Cannot activate: this rule's autonomous-activation approval "
                    f"request ({approval_request_id}) is currently '{live_status}', "
                    f"not 'approved'. A manager-tier employee must approve it first."
                )
            }

    rule.attributes["is_active"] = bool(is_active)
    rule.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return rule


def update_rule(rule_id, updated_by, name=None, description=None, trigger_params=None, action_params=None):

    rule = get_rule(rule_id)
    if not rule:
        return {"error": "Rule not found"}

    if name is not None:
        rule.attributes["name"] = name
    if description is not None:
        rule.attributes["description"] = description
    if trigger_params is not None:
        rule.attributes["trigger_params"] = trigger_params
    if action_params is not None:
        if rule.attributes.get("action_type") == "send_notification_dm":
            notify_id = action_params.get("notify_employee_id")
            target = ledger.get_entity(notify_id) if notify_id else None
            if not target or target.entity_type != EMPLOYEE:
                return {"error": "send_notification_dm requires a valid notify_employee_id"}
        rule.attributes["action_params"] = action_params

    rule.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return rule


def delete_rule(rule_id):

    rule = get_rule(rule_id)
    if not rule:
        return {"error": "Rule not found"}

    del ledger.entities[rule_id]

    save_graph(GRAPH_PATH)

    return {"deleted": rule_id}


# --- Execution log ------------------------------------------------------------

def _already_fired(rule_id, target_entity_id):
    for e in _all_of_type(AUTOMATION_EXECUTION):
        if e.attributes.get("rule_id") == rule_id and e.attributes.get("target_entity_id") == target_entity_id:
            return True
    return False


def _log_execution(rule, target_entity, action_result, detail):

    exec_id = id_generator.generate("AUTOX")

    entity = Entity(
        id=exec_id,
        entity_type=AUTOMATION_EXECUTION,
        attributes={
            "rule_id": rule.id,
            "rule_name": rule.attributes.get("name"),
            "trigger_type": rule.attributes.get("trigger_type"),
            "action_type": rule.attributes.get("action_type"),
            "target_entity_id": target_entity.id,
            "target_entity_type": target_entity.entity_type,
            "detail": detail,
            "action_result": action_result,
            "fired_at": _now_iso(),
        },
    )

    ledger.add_entity(entity)

    return entity


def list_executions(rule_id=None, limit=100):

    executions = _all_of_type(AUTOMATION_EXECUTION)

    if rule_id:
        executions = [e for e in executions if e.attributes.get("rule_id") == rule_id]

    executions.sort(key=lambda e: e.attributes.get("fired_at", ""), reverse=True)

    return executions[:limit]


# --- Condition evaluation -------------------------------------------------------

def _find_deal_stage_stalled(params):

    stage = params.get("stage", "financing")
    threshold_hours = _safe_float(params.get("threshold_hours"), 48)

    matches = []
    for deal in _all_of_type(DEAL):
        if deal.attributes.get("status") != stage:
            continue
        hours = _hours_since(deal.attributes.get("updated_at"))
        if hours is not None and hours >= threshold_hours:
            matches.append((deal, f"Deal {deal.id} has been in '{stage}' for {round(hours, 1)}h (threshold {threshold_hours}h)."))

    return matches


def _find_lead_no_contact(params):

    threshold_hours = _safe_float(params.get("threshold_hours"), 72)

    matches = []
    for lead in _all_of_type(LEAD):
        if lead.attributes.get("PipelineState") in ("SOLD", "LOST"):
            continue

        notes = list_field_notes(linked_entity_id=lead.id, limit=1000)
        if notes:
            last_contact = max((n.attributes.get("created_at") or "" for n in notes), default=None)
        else:
            last_contact = lead.attributes.get("PipelineStateSince") or lead.attributes.get("CreatedAt")

        hours = _hours_since(last_contact)
        if hours is not None and hours >= threshold_hours:
            matches.append((lead, f"Lead {lead.id} has had no contact logged in {round(hours, 1)}h (threshold {threshold_hours}h)."))

    return matches


def _find_vehicle_aging_price(params):

    min_price = _safe_float(params.get("min_price"), 40000)

    matches = []
    for vehicle in _unsold_vehicles():
        price = _safe_float(vehicle.attributes.get("Price"))
        if price >= min_price:
            matches.append((vehicle, f"Vehicle {vehicle.id} is priced at ${price:,.2f}, at/above the ${min_price:,.2f} threshold."))

    return matches


_CONDITION_FUNCS = {
    "deal_stage_stalled": _find_deal_stage_stalled,
    "lead_no_contact": _find_lead_no_contact,
    "vehicle_aging_price": _find_vehicle_aging_price,
}


# --- Action execution ------------------------------------------------------------

def _run_create_operations_task(rule, entity, condition_detail):
    """Note: passes _skip_save=True -- evaluate_rules() below does exactly ONE
    real save_graph() call at the very end of a whole pass, not once per
    matched entity, same batching precedent core/websites.py's
    create_website_from_wizard()/core/dealership_events.py's publish_event()
    already established. A rule matching many real entities in one pass
    (e.g. dozens of stalled financing deals) would otherwise cost several
    real seconds PER MATCH (create_task()'s own unconditional save), a real
    latency problem for what's meant to be a live, on-demand dashboard
    fetch."""

    params = rule.attributes.get("action_params") or {}
    priority = params.get("priority", "normal")
    detail_template = params.get("detail_template") or condition_detail

    task = create_task(
        task_type="custom",
        detail=f"[Automation: {rule.attributes.get('name')}] {detail_template}",
        created_by=AUTOMATION_ACTOR_ID,
        priority=priority if priority in ("low", "normal", "high", "urgent") else "normal",
        linked_entity_id=entity.id,
        source_entity_id=entity.id,
        _skip_save=True,
    )

    if isinstance(task, dict) and task.get("error"):
        return {"error": task["error"]}

    return {"created_task_id": task.id}


def _run_send_notification_dm(rule, entity, condition_detail):
    """See _run_create_operations_task's own comment above -- same
    _skip_save=True batching reasoning, this time for
    send_direct_message()'s own unconditional save."""

    params = rule.attributes.get("action_params") or {}
    notify_employee_id = params.get("notify_employee_id")
    message_template = params.get("message_template") or condition_detail

    if not notify_employee_id:
        return {"error": "No notify_employee_id configured on this rule"}

    message = send_direct_message(
        sender_id=AUTOMATION_ACTOR_ID,
        recipient_id=notify_employee_id,
        content=f"[Automation Rule: {rule.attributes.get('name')}] {message_template}",
        _skip_save=True,
    )

    return {"sent_message_id": message.id, "notified_employee_id": notify_employee_id}


_ACTION_FUNCS = {
    "create_operations_task": _run_create_operations_task,
    "send_notification_dm": _run_send_notification_dm,
}


def evaluate_rules(rule_id=None):
    """The real, on-demand evaluation pass -- see this module's own docstring
    for why this is explicitly NOT a background scheduler. Checks every
    active rule's real condition against the real graph, and for every
    matching entity that hasn't already had this rule fire against it
    (_already_fired dedup), runs the rule's real action and logs a real
    AutomationExecution entry. Returns a summary of what fired this pass.

    Security-hardening pass (2026-07-20, Task #6): gated by the real
    Workflow-Automation-wide (and dealer-wide) kill switch,
    core/ai_kill_switch.py's is_workflow_automation_enabled() -- checked
    at this single real entry point, distinct from this module's own
    pre-existing per-rule set_rule_active() toggle. A killed switch
    returns the same real response shape this function always returns,
    with rules_evaluated=0 and a real "gated" flag, rather than an empty
    dict a caller might not expect."""

    from core.ai_kill_switch import is_workflow_automation_enabled
    if not is_workflow_automation_enabled():
        return {
            "rules_evaluated": 0,
            "fired_count": 0,
            "fired": [],
            "errors": [],
            "gated": True,
            "gated_reason": "The Workflow Automation-wide (or dealer-wide) AI kill switch is currently active.",
            "evaluated_at": _now_iso(),
        }

    rules = [get_rule(rule_id)] if rule_id else list_rules(active_only=True)
    rules = [r for r in rules if r and r.attributes.get("is_active")]

    fired = []
    errors = []

    for rule in rules:

        condition_func = _CONDITION_FUNCS.get(rule.attributes.get("trigger_type"))
        action_func = _ACTION_FUNCS.get(rule.attributes.get("action_type"))

        if not condition_func or not action_func:
            errors.append({"rule_id": rule.id, "error": "Unknown trigger/action type"})
            continue

        matches = condition_func(rule.attributes.get("trigger_params") or {})

        for entity, detail in matches:

            if _already_fired(rule.id, entity.id):
                continue

            action_result = action_func(rule, entity, detail)

            if isinstance(action_result, dict) and action_result.get("error"):
                # A failed action must NOT be recorded as a dedup execution — _already_fired treats
                # any logged execution as "fired," so persisting one here would permanently suppress
                # this rule for this entity even after the error's cause clears. Log the error only;
                # a later pass retries while the condition still holds.
                errors.append({"rule_id": rule.id, "entity_id": entity.id, "error": action_result["error"]})
                continue

            _log_execution(rule, entity, action_result, detail)
            rule.attributes["times_fired"] = rule.attributes.get("times_fired", 0) + 1
            fired.append({
                "rule_id": rule.id,
                "rule_name": rule.attributes.get("name"),
                "entity_id": entity.id,
                "entity_type": entity.entity_type,
                "detail": detail,
                "action_result": action_result,
            })

        rule.attributes["last_run_at"] = _now_iso()

    if rules:
        save_graph(GRAPH_PATH)

    return {
        "rules_evaluated": len(rules),
        "fired_count": len(fired),
        "fired": fired,
        "errors": errors,
        "evaluated_at": _now_iso(),
    }


def get_automation_dashboard(run_now=True):
    """Automation's own Top Menu view: the rule list, a real evaluation pass
    (run live on every fetch unless run_now=False, same "compute live on
    read" convention as core/vehicle_holds.py's expires_at -- see this
    module's docstring for the full background-scheduler scoping decision),
    and the recent execution log."""

    result = evaluate_rules() if run_now else {"rules_evaluated": 0, "fired_count": 0, "fired": [], "errors": []}

    rules = list_rules()

    return {
        "rules": [_serialize(r) for r in rules],
        "active_rule_count": len([r for r in rules if r.attributes.get("is_active")]),
        "trigger_catalog": TRIGGER_CATALOG,
        "action_catalog": ACTION_CATALOG,
        "last_evaluation": result,
        "recent_executions": [_serialize(e) for e in list_executions(limit=50)],
    }
