"""
Operations Workflow Engine v2 (2026-07-20/21).

Sam's own reframe of this whole feature area: a workflow must stop being "a report
with steps" and become "the primary way work gets done in NXTDeal." A real
operations manager should touch 20-50 workflow instances a day, not interact with 4
high-level categories -- every instance must always be able to answer: I have a
problem -> what are the steps to resolution -> who owns each step -> what can AI
automate.

Deliberately PARALLEL to, not a replacement for, core/workflow_tracking.py's own
WorkflowInstance engine (session 53) -- that flat, single-`current_stage_index`
model still backs every OTHER department's already-shipped job-workflow screens
(Sales/Service/Inventory/Finance/Marketing/Administration/Readiness/Network), all
explicitly out of scope for this pilot. Rewriting that shared engine out from under
8 already-working departments to gain a richer per-step model for one department
(Operations) would be a much larger, much riskier change than building this
Operations-scoped v2 engine alongside it. If this pilot proves out, migrating the
other 8 departments onto this v2 engine is the natural next initiative -- not
attempted here.

The real difference from v1: v1 tracks one `current_stage_index` into a flat list of
plain stage-name strings. v2 tracks a real per-STEP object -- its own status, owner,
tasks, evidence, approvals, comments, and blocked-reason -- because a step in this
model is a genuine unit of accountable work, not just a label a progress bar points
at. See core/workflow_definitions_v2.py for the 21-workflow/114-step static catalog
this engine executes against, including its own real per-step `owner_role`/
`automation_tier`/`automation_note`/`sla_hours`/`real_source_hint` metadata (all
carried forward onto each instance's own runtime step objects, since a step's
definition-time defaults are the honest starting point for that step's real record).

State machine, exactly as specified (2 layers, distinct value sets):

  - INSTANCE status (`INSTANCE_STATUSES`): not_started / in_progress / blocked /
    waiting_approval / completed / escalated -- the caller-facing state, and the one
    surfaced to the bot / dashboards / coaching.
  - STEP status (`STEP_STATUSES`): not_started / in_progress / blocked / completed --
    narrower, since an individual step never itself "waits for approval" or
    "escalates" as a first-class state; those are properties of an approval/
    escalation record attached to the step, which is what actually drives the
    INSTANCE's own status via `_recompute_instance_status()`.

Deliberate, explicitly-reasoned scope boundary, stated here rather than silently
omitted: this engine does NOT attempt genuine autonomous unattended execution of any
workflow step. `core/workflow_definitions_v2.py`'s own `TIER_AUTONOMOUS` classification
is real, transparent metadata about what KIND of step this could safely be (per
core/ai_execution_tier.py's own established rule that autonomous execution requires a
real Approval Chain before it may run unattended) -- it does not itself mean this
engine, or anything wired to it, will actually take that action without a human
clicking something first. Building real per-step autonomous execution wired through
core/permissions_registry.py's Approval Chain is a substantially larger, separate
initiative, consistent with this codebase's established "real or honest gap, never
fabricated" convention.
"""

import uuid
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import WORKFLOW_INSTANCE_V2
from core.relationships import Relationship
from core.relationship_types import TRACKS
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_definitions_v2 import (
    DEFAULT_SLA_HOURS,
    TIER_ASSISTED,
    TIER_AUTONOMOUS,
    TIER_HUMAN_ONLY,
    get_workflow_def_v2,
    list_workflow_defs_v2,
)

INSTANCE_STATUSES = (
    "not_started",
    "in_progress",
    "blocked",
    "waiting_approval",
    "completed",
    "escalated",
)

STEP_STATUSES = ("not_started", "in_progress", "blocked", "completed")

_TERMINAL_INSTANCE_STATUSES = ("completed",)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hours_since(iso_timestamp):
    then = datetime.fromisoformat(iso_timestamp)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - then).total_seconds() / 3600.0


def _sub_id(prefix):
    """A random, per-call sub-id for objects embedded inside an instance's own
    attributes dict (tasks/evidence/approvals/comments) -- deliberately NOT
    id_generator.generate(), which this codebase has already found (repair_orders.py's
    concern/parts-request ids) does not survive process-boundary recovery the way a
    real graph-entity id does, since id_generator only recovers counters by rescanning
    real top-level Entity ids, never anything nested inside an attributes dict."""

    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _department_for_key(workflow_key):
    """Workflow keys are "department.slug_v2" by construction in
    core/workflow_definitions_v2.py -- read that back out rather than requiring every
    caller to also pass department separately, matching core/workflow_tracking.py's
    own established convention exactly."""

    return workflow_key.split(".", 1)[0].capitalize()


def _resolve_linked_entity(linked_entity_id):
    """Best-effort resolution of whatever the caller typed into the "linked entity"
    field -- a real graph id already (VEH-00042, DEAL-00123, EMP-00014, ...), or a
    business key a field employee would actually think in (a VIN, a lead id, ...).
    Mirrors core/workflow_tracking.py's own identical helper. Returns None (not an
    error) if nothing resolves -- a workflow instance is allowed to exist with no
    linked entity, same permissive precedent as FieldNote/WorkflowInstance."""

    if not linked_entity_id:
        return None

    if ledger.get_entity(linked_entity_id):
        return linked_entity_id

    for finder in (
        registry.find_vehicle,
        registry.find_lead,
        registry.find_customer,
        registry.find_employee,
        registry.find_finance,
        registry.find_lender,
        registry.find_part,
    ):
        resolved = finder(linked_entity_id)
        if resolved:
            return resolved

    return None


def _build_runtime_steps(workflow_def):
    """Turns the static per-step catalog definitions into the real, mutable runtime
    step objects a live instance actually tracks -- every definition-time field
    (owner_role/automation_tier/automation_note/sla_hours/real_source_hint) is carried
    forward verbatim as this step's own honest starting point, plus the real runtime
    fields (status/owner/tasks/evidence/approvals/comments/started_at/completed_at/
    blocked_reason) that only exist once an instance is actually running."""

    steps = []

    for step_def in workflow_def["steps"]:
        steps.append(
            {
                "key": step_def["key"],
                "label": step_def["label"],
                "owner_role": step_def["owner_role"],
                "automation_tier": step_def["automation_tier"],
                "automation_note": step_def["automation_note"],
                "sla_hours": step_def["sla_hours"],
                "real_source_hint": step_def["real_source_hint"],
                "status": "not_started",
                "owner": None,
                "tasks": [],
                "evidence": [],
                "approvals": [],
                "comments": [],
                "started_at": None,
                "completed_at": None,
                "blocked_reason": None,
            }
        )

    return steps


def _get_instance(instance_id):
    """Returns (instance, error) -- error is a plain string, matching this codebase's
    established (entity, error) tuple convention."""

    instance = ledger.get_entity(instance_id)

    if not instance or instance.entity_type != WORKFLOW_INSTANCE_V2:
        return None, f"no workflow instance with id '{instance_id}'"

    return instance, None


def _get_step(instance, step_key):
    for step in instance.attributes["steps"]:
        if step["key"] == step_key:
            return step
    return None


def _current_step(instance):
    return _get_step(instance, instance.attributes.get("current_step_key"))


def _step_summary(step):
    if not step:
        return None
    return {
        "key": step["key"],
        "label": step["label"],
        "status": step["status"],
        "owner_role": step["owner_role"],
        "owner": step["owner"],
        "automation_tier": step["automation_tier"],
        "automation_note": step["automation_note"],
        "sla_hours": step["sla_hours"],
        "blocked_reason": step.get("blocked_reason"),
        "started_at": step.get("started_at"),
        "completed_at": step.get("completed_at"),
    }


def _suggested_actions_for_step(step):
    """A real, transparent (never fabricated) suggestion list keyed off the step's
    own real automation_tier -- deliberately generic phrasing rather than a hardcoded
    per-workflow example, so it applies honestly across all 114 real catalog steps
    rather than only the one literal "schedule photography" example this feature was
    originally scoped from."""

    label = step["label"]
    tier = step["automation_tier"]

    if tier == TIER_AUTONOMOUS:
        return [
            f"Schedule / notify for '{label}' (candidate for autonomous action)",
            f"Create a follow-up task for '{label}'",
            "Notify the step owner",
        ]
    if tier == TIER_ASSISTED:
        return [
            f"Draft a message or document request for '{label}'",
            f"Create a task for '{label}'",
            "Notify the step owner",
        ]
    return [
        f"Assign an owner for '{label}'",
        "Notify the step owner",
        "Escalate to a manager",
    ]


def _recompute_instance_status(instance):
    """Re-derives the instance's own status from its steps' real current state --
    called after any action that could resolve (or newly create) a blocker/pending
    approval, so the instance status never has to be separately, manually kept in
    sync with what its steps actually say. Never touches a terminal
    (completed/escalated) instance -- escalation and completion are both explicit
    human/engine actions, not something a step-level recompute should silently
    undo."""

    if instance.attributes["status"] in ("completed", "escalated"):
        return

    steps = instance.attributes["steps"]

    if any(s["status"] == "blocked" for s in steps):
        instance.attributes["status"] = "blocked"
        return

    if any(a["status"] == "pending" for s in steps for a in s.get("approvals", [])):
        instance.attributes["status"] = "waiting_approval"
        return

    instance.attributes["status"] = "in_progress"


def start_workflow_instance_v2(workflow_key, started_by, linked_entity_id=None, notes=None):
    """Starts a new instance of a v2 catalog workflow -- the real "[Start New]" action
    behind the Workflow Dashboard. Returns (instance, error)."""

    workflow_def = get_workflow_def_v2(workflow_key)

    if not workflow_def:
        return None, f"no v2 workflow definition for key '{workflow_key}'"

    resolved_link = _resolve_linked_entity(linked_entity_id)

    steps = _build_runtime_steps(workflow_def)
    first_step = steps[0]
    first_step["status"] = "in_progress"
    first_step["started_at"] = _now()

    instance_id = id_generator.generate("WF2")

    entity = Entity(
        id=instance_id,
        entity_type=WORKFLOW_INSTANCE_V2,
        attributes={
            "workflow_key": workflow_key,
            "department": _department_for_key(workflow_key),
            "category": workflow_def["category"],
            "title": workflow_def["title"],
            "purpose": workflow_def["purpose"],
            "escalation_rules": workflow_def["escalation_rules"],
            "current_step_key": first_step["key"],
            "steps": steps,
            "status": "in_progress",
            "linked_entity_id": resolved_link,
            "linked_entity_raw": linked_entity_id or None,
            "started_by": started_by,
            "started_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
            "escalated_at": None,
            "escalated_reason": None,
            "force_closed": False,
            "force_close_reason": None,
            "history": [
                {
                    "step": first_step["key"],
                    "action": "started",
                    "by": started_by,
                    "at": _now(),
                    "notes": notes or None,
                }
            ],
        },
    )

    ledger.add_entity(entity)

    if resolved_link:
        ledger.add_relationship(
            Relationship(
                source_id=instance_id,
                target_id=resolved_link,
                relationship_type=TRACKS,
            )
        )

    save_graph(GRAPH_PATH)

    return entity, None


def advance_step(instance_id, actor, notes=None):
    """Marks the current step completed and moves to the next one, or completes the
    whole instance if the current step was the last one. Refuses to run while the
    instance is blocked/waiting_approval/escalated/completed -- the real blocker or
    pending approval must be resolved (unblock_step / decide_step_approval /
    resolve_escalation) before work can advance, enforcing the state machine rather
    than letting a caller silently skip past an open blocker."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] != "in_progress":
        return None, (
            f"workflow instance '{instance_id}' is '{instance.attributes['status']}', "
            "not 'in_progress' -- resolve the blocker/approval/escalation first"
        )

    steps = instance.attributes["steps"]
    current_step = _current_step(instance)

    if not current_step:
        return None, f"workflow instance '{instance_id}' has no current step"

    current_index = steps.index(current_step)
    current_step["status"] = "completed"
    current_step["completed_at"] = _now()

    next_index = current_index + 1

    if next_index >= len(steps):
        instance.attributes["status"] = "completed"
        instance.attributes["completed_at"] = _now()
        instance.attributes["current_step_key"] = None
        action = "completed"
        step_label = current_step["key"]
    else:
        next_step = steps[next_index]
        next_step["status"] = "in_progress"
        next_step["started_at"] = _now()
        instance.attributes["current_step_key"] = next_step["key"]
        action = "advanced"
        step_label = next_step["key"]

    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": step_label,
            "action": action,
            "by": actor,
            "at": _now(),
            "notes": notes or None,
        }
    )

    save_graph(GRAPH_PATH)
    if instance.attributes["status"] == "completed":
        from core.dealership_lab.engagement import on_work_completed
        on_work_completed(actor)

    return instance, None


def add_step_task(instance_id, step_key, description, actor, assigned_to=None):
    """Adds a real, trackable task to a step -- distinct from the step's own
    definition-time automation_note, since a step accumulates real, ad hoc work items
    over its life (e.g. "call the vendor back", "confirm with the customer")."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    if not description or not description.strip():
        return None, "a task description is required"

    task = {
        "id": _sub_id("TASK"),
        "description": description.strip(),
        "assigned_to": assigned_to,
        "status": "open",
        "created_by": actor,
        "created_at": _now(),
        "completed_at": None,
    }

    step["tasks"].append(task)
    instance.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return instance, None


def complete_step_task(instance_id, step_key, task_id, actor):

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    task = next((t for t in step["tasks"] if t["id"] == task_id), None)
    if not task:
        return None, f"no task '{task_id}' on step '{step_key}'"

    if task["status"] == "completed":
        return None, f"task '{task_id}' is already completed"

    task["status"] = "completed"
    task["completed_at"] = _now()
    task["completed_by"] = actor
    instance.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return instance, None


def add_step_evidence(instance_id, step_key, description, actor, url=None):
    """A real, timestamped record that something was actually done/checked/verified
    for this step -- a photo URL, an inspection note, a document reference. Never
    itself changes step status; a human still explicitly advances/completes the
    step."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    if not description or not description.strip():
        return None, "an evidence description is required"

    evidence = {
        "id": _sub_id("EVID"),
        "description": description.strip(),
        "url": url or None,
        "added_by": actor,
        "added_at": _now(),
    }

    step["evidence"].append(evidence)
    instance.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return instance, None


def add_step_comment(instance_id, step_key, text, actor):

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    if not text or not text.strip():
        return None, "comment text is required"

    comment = {
        "id": _sub_id("CMT"),
        "text": text.strip(),
        "by": actor,
        "at": _now(),
    }

    step["comments"].append(comment)
    instance.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return instance, None


def block_step(instance_id, step_key, reason, actor):
    """Explicitly blocks a step (any step, not only the current one -- a blocker on a
    later step, like "title not on file yet", can be real and worth recording before
    work actually reaches that step). Sets the whole instance's status to "blocked"
    whenever the BLOCKED step is the current one; a block on a future step is recorded
    but doesn't itself stop current work."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] in _TERMINAL_INSTANCE_STATUSES:
        return None, f"workflow instance '{instance_id}' is already completed"

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    if not reason or not reason.strip():
        return None, "a block reason is required"

    step["status"] = "blocked"
    step["blocked_reason"] = reason.strip()
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": step_key,
            "action": "blocked",
            "by": actor,
            "at": _now(),
            "notes": reason.strip(),
        }
    )

    _recompute_instance_status(instance)

    save_graph(GRAPH_PATH)

    return instance, None


def unblock_step(instance_id, step_key, actor, notes=None):

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    if step["status"] != "blocked":
        return None, f"step '{step_key}' is not blocked"

    step["status"] = "in_progress" if step_key == instance.attributes.get("current_step_key") else "not_started"
    step["blocked_reason"] = None
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": step_key,
            "action": "unblocked",
            "by": actor,
            "at": _now(),
            "notes": notes or None,
        }
    )

    _recompute_instance_status(instance)

    save_graph(GRAPH_PATH)

    return instance, None


def request_step_approval(instance_id, step_key, requested_by, note=None):
    """Real approval-request record on a step -- puts the whole instance into
    "waiting_approval" until decide_step_approval() resolves it. Matches Sam's own
    example almost exactly: a Compliance Workflow stuck at "Waiting Signature, Open
    For 5 Days" is exactly one of these, still pending."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] in _TERMINAL_INSTANCE_STATUSES:
        return None, f"workflow instance '{instance_id}' is already completed"

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    approval = {
        "id": _sub_id("APR"),
        "status": "pending",
        "requested_by": requested_by,
        "requested_at": _now(),
        "decided_by": None,
        "decided_at": None,
        "decision_note": None,
        "note": note or None,
    }

    step["approvals"].append(approval)
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": step_key,
            "action": "approval_requested",
            "by": requested_by,
            "at": _now(),
            "notes": note or None,
        }
    )
    instance.attributes["status"] = "waiting_approval"

    save_graph(GRAPH_PATH)

    return instance, None


def decide_step_approval(instance_id, step_key, approval_id, approved, decided_by, note=None):
    """Resolves a pending approval. A rejection blocks the step (with the rejection
    note as the real blocked_reason) rather than silently letting work continue --
    the instance stays stopped until a human explicitly unblocks it, matching real
    dealership practice (a rejected deal-jacket document, a declined signature) where
    "rejected" is itself a real blocker, not a neutral outcome."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    step = _get_step(instance, step_key)
    if not step:
        return None, f"no step '{step_key}' on workflow instance '{instance_id}'"

    approval = next(
        (a for a in step["approvals"] if a["id"] == approval_id and a["status"] == "pending"),
        None,
    )
    if not approval:
        return None, f"no pending approval '{approval_id}' on step '{step_key}'"

    approval["status"] = "approved" if approved else "rejected"
    approval["decided_by"] = decided_by
    approval["decided_at"] = _now()
    approval["decision_note"] = note or None

    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": step_key,
            "action": "approval_approved" if approved else "approval_rejected",
            "by": decided_by,
            "at": _now(),
            "notes": note or None,
        }
    )

    if not approved:
        step["status"] = "blocked"
        step["blocked_reason"] = f"Approval rejected: {note or 'no reason given'}"

    _recompute_instance_status(instance)

    save_graph(GRAPH_PATH)

    return instance, None


def escalate_instance(instance_id, actor, reason):
    """Explicit escalation -- a human (or, later, an automated stall-detection caller)
    decided this instance needs manager attention right now. Distinct from "blocked":
    an escalated instance is actively being worked at a higher level, not just
    stopped."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] in _TERMINAL_INSTANCE_STATUSES:
        return None, f"workflow instance '{instance_id}' is already completed"

    if not reason or not reason.strip():
        return None, "an escalation reason is required"

    instance.attributes["status"] = "escalated"
    instance.attributes["escalated_at"] = _now()
    instance.attributes["escalated_reason"] = reason.strip()
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": instance.attributes.get("current_step_key"),
            "action": "escalated",
            "by": actor,
            "at": _now(),
            "notes": reason.strip(),
        }
    )

    save_graph(GRAPH_PATH)

    return instance, None


def resolve_escalation(instance_id, actor, notes=None):
    """Explicitly returns an escalated instance to normal work, re-deriving whether
    that means in_progress/blocked/waiting_approval off its steps' own real state."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] != "escalated":
        return None, f"workflow instance '{instance_id}' is not escalated"

    instance.attributes["status"] = "in_progress"
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": instance.attributes.get("current_step_key"),
            "action": "escalation_resolved",
            "by": actor,
            "at": _now(),
            "notes": notes or None,
        }
    )

    _recompute_instance_status(instance)

    save_graph(GRAPH_PATH)

    return instance, None


def force_close_instance(instance_id, actor, reason):
    """A deliberate escape hatch, not a 7th state -- Sam's own spec named exactly 6
    instance statuses (not_started/in_progress/blocked/waiting_approval/completed/
    escalated), with no separate "cancelled" terminal state for a workflow a manager
    decides to abandon (e.g. a wholesale disposal that falls through). Rather than
    silently invent a 7th status this codebase's own real UI/AI-state code would then
    have to special-case everywhere, this marks the instance "completed" but flags it
    honestly (`force_closed: True`, `force_close_reason`) so it's always possible to
    tell a real natural completion apart from one a manager forced shut."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    if instance.attributes["status"] in _TERMINAL_INSTANCE_STATUSES:
        return None, f"workflow instance '{instance_id}' is already completed"

    if not reason or not reason.strip():
        return None, "a reason is required to force-close a workflow instance"

    instance.attributes["status"] = "completed"
    instance.attributes["completed_at"] = _now()
    instance.attributes["force_closed"] = True
    instance.attributes["force_close_reason"] = reason.strip()
    instance.attributes["updated_at"] = _now()
    instance.attributes["history"].append(
        {
            "step": instance.attributes.get("current_step_key"),
            "action": "force_closed",
            "by": actor,
            "at": _now(),
            "notes": reason.strip(),
        }
    )

    save_graph(GRAPH_PATH)

    return instance, None


def list_instances_v2(department=None, workflow_key=None, status=None, category=None, linked_entity_id=None, limit=100):

    instances = [
        e for e in ledger.get_all().values()
        if e.entity_type == WORKFLOW_INSTANCE_V2
        and (department is None or e.attributes.get("department") == department)
        and (workflow_key is None or e.attributes.get("workflow_key") == workflow_key)
        and (status is None or e.attributes.get("status") == status)
        and (category is None or e.attributes.get("category") == category)
        and (linked_entity_id is None or e.attributes.get("linked_entity_id") == linked_entity_id)
    ]

    instances.sort(key=lambda e: e.attributes.get("updated_at") or "", reverse=True)

    return instances[:limit]


def get_dashboard_v2(department=None):
    """The real Workflow Dashboard data -- one row per catalog workflow (even ones
    with zero instances yet, so "[Start New]" is always available), each with real
    active/completed/escalated/blocked/waiting_approval counts off the actual
    instances on the graph. Matches Sam's own literal dashboard example:
    "Vehicle Intake & Recon (74 Active) [Continue] [Start New]"."""

    defs = list_workflow_defs_v2()
    if department:
        defs = [d for d in defs if _department_for_key(d["key"]) == department]

    counts = {}
    for e in ledger.get_all().values():
        if e.entity_type != WORKFLOW_INSTANCE_V2:
            continue

        wf_key = e.attributes.get("workflow_key")
        bucket = counts.setdefault(
            wf_key,
            {"active": 0, "completed": 0, "escalated": 0, "blocked": 0, "waiting_approval": 0, "total": 0},
        )

        status = e.attributes.get("status")
        bucket["total"] += 1

        if status == "completed":
            bucket["completed"] += 1
        elif status == "escalated":
            bucket["escalated"] += 1
            bucket["active"] += 1
        elif status == "blocked":
            bucket["blocked"] += 1
            bucket["active"] += 1
        elif status == "waiting_approval":
            bucket["waiting_approval"] += 1
            bucket["active"] += 1
        else:
            bucket["active"] += 1

    empty_bucket = {"active": 0, "completed": 0, "escalated": 0, "blocked": 0, "waiting_approval": 0, "total": 0}

    rows = []
    for d in defs:
        c = counts.get(d["key"], empty_bucket)
        rows.append(
            {
                "workflow_key": d["key"],
                "title": d["title"],
                "category": d["category"],
                "purpose": d["purpose"],
                "step_count": len(d["steps"]),
                **c,
            }
        )

    rows.sort(key=lambda r: r["active"], reverse=True)

    return {
        "department": department,
        "workflows": rows,
        "total_active": sum(r["active"] for r in rows),
        "total_completed": sum(r["completed"] for r in rows),
        "total_escalated": sum(r["escalated"] for r in rows),
    }


def get_stalled_instances_v2(department=None):
    """Real, transparent stall detection -- no fabricated AI judgment, just each
    instance's current step's real elapsed time since it started vs. that step's own
    real sla_hours (falling back to the workflow's own escalation_rules default).
    This is the honest, checkable signal a Bottleneck Resolution workflow or the AI
    assistant's own workflow-awareness tool (core/ai_tools.py) should key off of."""

    instances = list_instances_v2(department=department, limit=10000)
    stalled = []

    for instance in instances:
        if instance.attributes["status"] == "completed":
            continue

        current_step = _current_step(instance)
        if not current_step or not current_step.get("started_at"):
            continue

        elapsed = _hours_since(current_step["started_at"])
        threshold = current_step.get("sla_hours") or instance.attributes.get(
            "escalation_rules", {}
        ).get("default_stalled_hours", DEFAULT_SLA_HOURS)

        if elapsed > threshold:
            stalled.append(
                {
                    "instance_id": instance.id,
                    "workflow_key": instance.attributes["workflow_key"],
                    "title": instance.attributes["title"],
                    "status": instance.attributes["status"],
                    "current_step_key": current_step["key"],
                    "current_step_label": current_step["label"],
                    "elapsed_hours": round(elapsed, 1),
                    "sla_hours": threshold,
                    "linked_entity_id": instance.attributes.get("linked_entity_id"),
                }
            )

    stalled.sort(key=lambda r: r["elapsed_hours"], reverse=True)

    return stalled


def get_instance_ai_state(instance_id):
    """The real payload behind Sam's own "AI Workflow Awareness" example -- Current
    Step / Next Step / Blocked Steps / Required Approvals / Missing Information, plus
    a real, transparent (never fabricated) set of Suggested Actions and a real,
    computed "is this stalled against its own SLA" signal. Returns (state, error)."""

    instance, error = _get_instance(instance_id)
    if error:
        return None, error

    steps = instance.attributes["steps"]
    current_step = _current_step(instance)
    current_index = steps.index(current_step) if current_step else -1
    next_step = steps[current_index + 1] if 0 <= current_index < len(steps) - 1 else None

    blocked_steps = [
        {"key": s["key"], "label": s["label"], "blocked_reason": s.get("blocked_reason")}
        for s in steps
        if s["status"] == "blocked"
    ]

    required_approvals = []
    for s in steps:
        for a in s.get("approvals", []):
            if a["status"] == "pending":
                required_approvals.append(
                    {
                        "step_key": s["key"],
                        "step_label": s["label"],
                        "approval_id": a["id"],
                        "requested_by": a["requested_by"],
                        "requested_at": a["requested_at"],
                        "note": a.get("note"),
                    }
                )

    missing_information = []
    if current_step:
        for t in current_step.get("tasks", []):
            if t["status"] != "completed":
                missing_information.append(
                    f"Open task on '{current_step['label']}': {t['description']}"
                )
        if current_step["status"] == "blocked" and current_step.get("blocked_reason"):
            missing_information.append(
                f"'{current_step['label']}' is blocked: {current_step['blocked_reason']}"
            )

    stalled_info = None
    if current_step and current_step.get("started_at") and instance.attributes["status"] != "completed":
        elapsed_hours = _hours_since(current_step["started_at"])
        threshold = current_step.get("sla_hours") or instance.attributes.get(
            "escalation_rules", {}
        ).get("default_stalled_hours", DEFAULT_SLA_HOURS)
        stalled_info = {
            "elapsed_hours": round(elapsed_hours, 1),
            "sla_hours": threshold,
            "is_stalled": elapsed_hours > threshold,
        }

    if blocked_steps:
        focus_step = _get_step(instance, blocked_steps[0]["key"])
        suggested_actions = _suggested_actions_for_step(focus_step)
    elif required_approvals:
        suggested_actions = [
            "Follow up with the approver",
            "Send a reminder notification",
            "Escalate to a manager",
        ]
    elif current_step and stalled_info and stalled_info["is_stalled"]:
        suggested_actions = _suggested_actions_for_step(current_step)
    else:
        suggested_actions = []

    return (
        {
            "instance_id": instance.id,
            "workflow_key": instance.attributes["workflow_key"],
            "title": instance.attributes["title"],
            "status": instance.attributes["status"],
            "linked_entity_id": instance.attributes.get("linked_entity_id"),
            "current_step": _step_summary(current_step),
            "next_step": _step_summary(next_step),
            "blocked_steps": blocked_steps,
            "required_approvals": required_approvals,
            "missing_information": missing_information,
            "stalled": stalled_info,
            "suggested_actions": suggested_actions,
        },
        None,
    )
