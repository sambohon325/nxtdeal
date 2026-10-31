"""
core/operations_tasks.py -- the "Universal Operations Work Queue" from Sam's
Operations spec (session 106, "keep going" autonomous continuation, third slice
after Vehicles and Overview + Action Center). Sam's own framing: Operations needs
"Assign Owner (Inventory Manager, Title Clerk, Service Manager, Lot Manager,
Accounting), SLA Tracking with auto-escalation, Bulk Actions, and Workflow Actions"
-- not just the read-only exception reporting core/operations_menu.py's tasks()
already provides.

An OperationsTask is a real, first-class graph entity with its own lifecycle
(open -> in_progress -> closed), distinct from the additive-attribute convention
used for Vehicle Lifecycle -- a task isn't a property of one entity, it's its own
trackable unit of work, optionally *about* an entity (linked_entity_id, same plain-
attribute convention as FieldNote/LeadTask/Appointment/ManagerTO, not a foreign key).

SLA tracking is computed live off created_at (hours_open, is_overdue against a
per-priority SLA-hours table) -- same "compute live" convention as
core/vehicle_holds.py's expires_at, no background scheduler. "Auto-escalation" here
means is_overdue flips a task into visibly-escalated territory the moment it's
read/listed past its SLA window; it does not mean a background job silently
reassigns or pages anyone -- no scheduler infrastructure exists for that in this
codebase (core/bot_scheduler.py/compliance_scheduler.py are the only two precedents,
both intentionally narrow), and inventing a third was judged out of scope for one
autonomous slice. escalate_task() gives a human the explicit action instead.

Two ways a task gets created:
  1. Directly, by a person (create_task) -- an ordinary manual ticket.
  2. Synced (sync_derived_tasks) from real signals this codebase already computes
     elsewhere but only ever *reported*, never made actionable: wholesale
     candidates needing a transfer decision (core/inventory_menu.py's
     inventory_wholesale_disposition), lot-audit discrepancies needing
     confirmation (inventory_lot_audit), and open compliance alerts needing
     review (core/compliance_api.py's list_alerts_api) -- the exact three signal
     types core/operations_menu.py's tasks() already surfaces read-only. Syncing
     is idempotent, deduped by source_entity_id + task_type (same dedup precedent
     as core/compliance.py's run_full_scan()) so re-running it doesn't create
     duplicate tickets for a gap that's still open, and a closed derived task
     that would otherwise be re-derived stays closed (it's not resurrected).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import OPERATIONS_TASK

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# The 5 real owner buckets from Sam's spec. Deliberately plain strings, not a link
# to a real roster -- this codebase has no dedicated Inventory Manager/Lot Manager
# roles/titles distinct from generic Employee.Title free text (the same finding
# core/operations_overview.py's Workload Distribution already made and documented),
# so "Assign Owner" assigns to a real Employee id, and OWNER_BUCKETS is offered as
# a suggested categorization tag, not an enforced foreign key into a role table
# that doesn't exist.
OWNER_BUCKETS = ["Inventory Manager", "Title Clerk", "Service Manager", "Lot Manager", "Accounting", "Unassigned"]

TASK_TYPES = [
    "transfer_to_wholesale",
    "confirm_lot_audit",
    "review_compliance_exception",
    "title_processing",
    "recon_followup",
    # Inventory Aging Management (session 106 follow-up #4) -- three more real
    # workflow actions on top of the aging price-band board, reusing this same
    # generic task engine rather than a parallel one. See
    # core/inventory_aging.py for the actions that create these.
    "manager_review",
    "marketing_campaign_tie_in",
    "auction_assignment",
    # Documents (session 106 follow-up #6) -- requesting a missing document
    # (Deal Jacket/Buyer Order/Compliance File) that isn't specifically a
    # Title (which reuses the existing "title_processing" type above). See
    # core/document_workflows.py.
    "document_request",
    "custom",
]

STATUSES = ["open", "in_progress", "closed"]
PRIORITIES = ["low", "normal", "high", "urgent"]

# Hours-to-SLA-breach per priority -- a real, if simple, threshold table rather
# than one flat number for every task regardless of urgency.
SLA_HOURS = {
    "urgent": 4,
    "high": 24,
    "normal": 72,
    "low": 168,
}


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hours_open(task):
    created = _parse(task.attributes.get("created_at"))
    if not created:
        return None
    end = _parse(task.attributes.get("closed_at")) or _now()
    return round((end - created).total_seconds() / 3600, 1)


def _enrich(task):
    """Adds the two live-computed SLA fields to a task's returned attributes
    without mutating the stored entity -- same read-time-enrichment pattern
    core/vehicle_holds.py uses for expires_at."""

    hours_open = _hours_open(task)
    sla_hours = SLA_HOURS.get(task.attributes.get("priority", "normal"), SLA_HOURS["normal"])
    is_overdue = (
        task.attributes.get("status") != "closed"
        and hours_open is not None
        and hours_open > sla_hours
    )

    return Entity(
        id=task.id,
        entity_type=task.entity_type,
        attributes={
            **task.attributes,
            "hours_open": hours_open,
            "sla_hours": sla_hours,
            "is_overdue": is_overdue,
        },
    )


def serialize_task(task):
    """Flattens a raw OperationsTask Entity ({id, entity_type, attributes}) into
    a plain {id, **attributes} dict before it crosses an API boundary -- the
    same fix applied directly in core/operations_tasks_api.py (see that
    module's _serialize() for the full bug writeup: FastAPI's default JSON
    encoding of a bare Entity nests every real field one level deeper than
    the frontend expects). Any other module that calls create_task()/
    close_task()/etc. and hands the result straight to its own *_api.py layer
    (core/document_workflows.py's request_document(),
    core/inventory_aging.py's request_wholesale_review()/
    request_manager_review()/request_auction_assignment(),
    core/operations_scheduling.py's schedule_recon()) should serialize
    through this shared helper rather than duplicating the flatten logic, or
    leaking the raw Entity across the wire the same way operations_tasks_api.py
    used to."""

    if isinstance(task, dict):
        return task

    return {"id": task.id, **task.attributes}


def create_task(task_type, detail, created_by, priority="normal", owner_bucket="Unassigned",
                 assigned_to=None, linked_entity_id=None, source_entity_id=None, target_date=None,
                 _skip_save=False):

    if task_type not in TASK_TYPES:
        return {"error": f"task_type must be one of {TASK_TYPES}"}

    if priority not in PRIORITIES:
        return {"error": f"priority must be one of {PRIORITIES}"}

    if owner_bucket not in OWNER_BUCKETS:
        return {"error": f"owner_bucket must be one of {OWNER_BUCKETS}"}

    task_id = id_generator.generate("OTASK")

    entity = Entity(
        id=task_id,
        entity_type=OPERATIONS_TASK,
        attributes={
            "task_type": task_type,
            "detail": detail or "",
            "status": "open",
            "priority": priority,
            "owner_bucket": owner_bucket,
            "assigned_to": assigned_to,
            "linked_entity_id": linked_entity_id,
            "source_entity_id": source_entity_id,
            "derived": bool(source_entity_id),
            # Scheduling (session 106 follow-up #5) -- an optional real target/due
            # date distinct from the SLA hours_open/is_overdue clock (which always
            # counts from created_at). A scheduling action (e.g. "schedule this
            # vehicle's recon for the 20th") sets a concrete date a person picked,
            # not a computed SLA deadline. None for every other task type, same
            # optional-field convention as core/deals.py's trade_in.
            "target_date": target_date,
            "created_by": created_by,
            "created_at": _now_iso(),
            "started_at": None,
            "closed_at": None,
            "closed_by": None,
            "resolution_notes": "",
        },
    )

    ledger.add_entity(entity)
    # _skip_save (added for core/workflow_automation.py's evaluate_rules(), which
    # can fire this once per matched entity in a single pass) -- same batching
    # precedent as core/websites.py's create_website_from_wizard()/
    # core/dealership_events.py's publish_event(): every OTHER existing caller is
    # unaffected (default False, saves immediately as it always has).
    if not _skip_save:
        save_graph(GRAPH_PATH)

    return entity


def get_task(task_id):

    entity = ledger.get_entity(task_id)

    if entity and entity.entity_type == OPERATIONS_TASK:
        return _enrich(entity)

    return None


def _raw_task(task_id):
    entity = ledger.get_entity(task_id)
    if entity and entity.entity_type == OPERATIONS_TASK:
        return entity
    return None


def update_task(task_id, updated_by, status=None, priority=None, owner_bucket=None, assigned_to=None):

    task = _raw_task(task_id)

    if not task:
        return {"error": "Task not found"}

    if status is not None:
        if status not in STATUSES:
            return {"error": f"status must be one of {STATUSES}"}
        task.attributes["status"] = status
        if status == "in_progress" and not task.attributes.get("started_at"):
            task.attributes["started_at"] = _now_iso()
        if status == "closed":
            task.attributes["closed_at"] = _now_iso()
            task.attributes["closed_by"] = updated_by
        elif task.attributes.get("closed_at"):
            # Reopened -- clear the close stamp so hours_open resumes counting live.
            task.attributes["closed_at"] = None
            task.attributes["closed_by"] = None

    if priority is not None:
        if priority not in PRIORITIES:
            return {"error": f"priority must be one of {PRIORITIES}"}
        task.attributes["priority"] = priority

    if owner_bucket is not None:
        if owner_bucket not in OWNER_BUCKETS:
            return {"error": f"owner_bucket must be one of {OWNER_BUCKETS}"}
        task.attributes["owner_bucket"] = owner_bucket

    if assigned_to is not None:
        task.attributes["assigned_to"] = assigned_to

    save_graph(GRAPH_PATH)

    return _enrich(task)


def close_task(task_id, closed_by, resolution_notes=""):

    task = _raw_task(task_id)

    if not task:
        return {"error": "Task not found"}

    if task.attributes.get("status") == "closed":
        return {"error": "Task is already closed"}

    task.attributes["status"] = "closed"
    task.attributes["closed_at"] = _now_iso()
    task.attributes["closed_by"] = closed_by
    task.attributes["resolution_notes"] = resolution_notes or ""

    save_graph(GRAPH_PATH)

    return _enrich(task)


def escalate_task(task_id, escalated_by, notes=""):
    """The explicit human action standing in for "auto-escalation" -- bumps
    priority to urgent and stamps a note, rather than a background job silently
    reassigning work (see module docstring for why)."""

    task = _raw_task(task_id)

    if not task:
        return {"error": "Task not found"}

    if task.attributes.get("status") == "closed":
        return {"error": "Cannot escalate a closed task"}

    task.attributes["priority"] = "urgent"
    task.attributes["resolution_notes"] = (
        (task.attributes.get("resolution_notes") or "") +
        f"\n[escalated by {escalated_by} at {_now_iso()}] {notes}"
    ).strip()

    save_graph(GRAPH_PATH)

    return _enrich(task)


def list_tasks(status=None, owner_bucket=None, assigned_to=None, priority=None, overdue_only=False):

    tasks = [e for e in ledger.get_all().values() if e.entity_type == OPERATIONS_TASK]

    if status:
        tasks = [t for t in tasks if t.attributes.get("status") == status]

    if owner_bucket:
        tasks = [t for t in tasks if t.attributes.get("owner_bucket") == owner_bucket]

    if assigned_to:
        tasks = [t for t in tasks if t.attributes.get("assigned_to") == assigned_to]

    if priority:
        tasks = [t for t in tasks if t.attributes.get("priority") == priority]

    enriched = [_enrich(t) for t in tasks]

    if overdue_only:
        enriched = [t for t in enriched if t.attributes.get("is_overdue")]

    enriched.sort(key=lambda t: (
        {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(t.attributes.get("priority"), 2),
        t.attributes.get("created_at") or "",
    ))

    return enriched


def get_stats():

    tasks = list_tasks()
    open_tasks = [t for t in tasks if t.attributes.get("status") != "closed"]
    closed_tasks = [t for t in tasks if t.attributes.get("status") == "closed"]
    overdue = [t for t in open_tasks if t.attributes.get("is_overdue")]

    by_owner = {}
    for t in open_tasks:
        bucket = t.attributes.get("owner_bucket", "Unassigned")
        by_owner[bucket] = by_owner.get(bucket, 0) + 1

    return {
        "total": len(tasks),
        "open": len(open_tasks),
        "closed": len(closed_tasks),
        "overdue": len(overdue),
        "by_owner_bucket": by_owner,
    }


# --- Bulk actions -----------------------------------------------------------

def bulk_assign(task_ids, assigned_to, owner_bucket, updated_by):

    results = []
    for task_id in task_ids:
        results.append(update_task(task_id, updated_by, owner_bucket=owner_bucket, assigned_to=assigned_to))

    return results


def bulk_close(task_ids, closed_by, resolution_notes=""):

    results = []
    for task_id in task_ids:
        results.append(close_task(task_id, closed_by, resolution_notes=resolution_notes))

    return results


def bulk_reprioritize(task_ids, priority, updated_by):

    results = []
    for task_id in task_ids:
        results.append(update_task(task_id, updated_by, priority=priority))

    return results


# --- Derived-task sync -------------------------------------------------------

def _existing_source_ids(task_type):
    """Every non-closed derived task's source_entity_id for a given task_type --
    the dedup key sync_derived_tasks() checks against so re-running the sync
    doesn't spawn duplicate tickets for a gap that's still open."""

    return {
        t.attributes.get("source_entity_id")
        for t in ledger.get_all().values()
        if t.entity_type == OPERATIONS_TASK
        and t.attributes.get("task_type") == task_type
        and t.attributes.get("status") != "closed"
        and t.attributes.get("source_entity_id")
    }


def sync_derived_tasks(role):
    """Turns the three real signal types core/operations_menu.py's tasks() already
    surfaces read-only into real, trackable OperationsTasks -- idempotent, deduped
    by (task_type, source_entity_id). Returns how many new tasks were created per
    type, not the full task list (callers should follow with list_tasks())."""

    # Local imports to avoid a circular import at module load time
    # (operations_menu.py itself will come to depend on this module).
    from core.workflow_tab_data import inventory_wholesale_disposition, inventory_lot_audit
    from core.compliance_api import list_alerts_api

    created = {"transfer_to_wholesale": 0, "confirm_lot_audit": 0, "review_compliance_exception": 0}

    wholesale = inventory_wholesale_disposition(role)
    existing_wholesale = _existing_source_ids("transfer_to_wholesale")
    for candidate in wholesale.get("candidates", [])[:25] if isinstance(wholesale, dict) else []:
        vehicle_id = candidate.get("vehicle_id")
        if not vehicle_id or vehicle_id in existing_wholesale:
            continue
        create_task(
            task_type="transfer_to_wholesale",
            detail=f"{candidate.get('year')} {candidate.get('make')} {candidate.get('model')} -- "
                   f"{candidate.get('margin_pct')} margin, thin-margin wholesale candidate",
            created_by="system:operations_task_sync",
            priority="normal",
            owner_bucket="Inventory Manager",
            linked_entity_id=vehicle_id,
            source_entity_id=vehicle_id,
        )
        created["transfer_to_wholesale"] += 1

    lot_audit = inventory_lot_audit(role)
    existing_audit = _existing_source_ids("confirm_lot_audit")
    for discrepancy in lot_audit.get("discrepancies", [])[:25] if isinstance(lot_audit, dict) else []:
        vehicle_id = discrepancy.get("vehicle_id")
        if not vehicle_id or vehicle_id in existing_audit:
            continue
        create_task(
            task_type="confirm_lot_audit",
            detail=f"Marked sold with no PURCHASED relationship -- VIN {discrepancy.get('vin')}",
            created_by="system:operations_task_sync",
            priority="high",
            owner_bucket="Lot Manager",
            linked_entity_id=vehicle_id,
            source_entity_id=vehicle_id,
        )
        created["confirm_lot_audit"] += 1

    alerts = list_alerts_api(role, status="open")
    existing_alerts = _existing_source_ids("review_compliance_exception")
    if isinstance(alerts, dict) and "alerts" in alerts:
        for alert in alerts["alerts"][:25]:
            alert_id = alert.get("id")
            if not alert_id or alert_id in existing_alerts:
                continue
            create_task(
                task_type="review_compliance_exception",
                detail=f"{alert.get('law', alert.get('category', 'Compliance'))} -- severity {alert.get('severity')}",
                created_by="system:operations_task_sync",
                priority="urgent" if alert.get("severity") == "high" else "high",
                owner_bucket="Accounting",
                linked_entity_id=alert_id,
                source_entity_id=alert_id,
            )
            created["review_compliance_exception"] += 1

    return created
