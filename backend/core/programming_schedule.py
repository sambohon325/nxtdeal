"""Programming Schedule tracker for NXTDeal development (2026-10-24).

A work-tracking system that lets the development team see:
  - What's been built (completed work items)
  - What's left to program (todo / in-progress items)
  - Bugs to work on (bug-type items)
  - Security issues (security-type items)
  - Who's assigned to each item (team assignment)

Items live as PROGRAMMING_SCHEDULE entities in the dealer graph (keyed PS-{id}),
so they are visible to anyone with Dealer Admin/Operations access and persisted
through the same ledger/storage machinery as the rest of NXTDeal.

Each item tracks:
  - type: feature | bug | security | tech-debt
  - phase: Phase 0..7 (the production bridge roadmap phase)
  - status: todo | in_progress | in_review | done | deployed | pushed_live | blocked
  - ci_commit_sha: commit SHA linked to CI run
  - ci_passed: boolean, whether CI passed on this commit
  - deployment_run_id: linked DEPLOYMENT_RUN entity id
  - coolify_deployment_id: Coolify deployment UUID
  - pushed_live_at: ISO timestamp when deployed to production
  - priority: low | medium | high | critical
  - assignee: backend | frontend | devops | sample | unassigned
  - progress: 0-100 integer
  - est_hours / logged_hours
  - depends_on: list of PS-{id} references
  - security_severity: if type=security: low | medium | high | critical
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Any

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import PROGRAMMING_SCHEDULE

# Valid enum values
ITEM_TYPES = ("feature", "bug", "security", "tech-debt")
PHASES = ("Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6", "Phase 7")
STATUSES = ("todo", "in_progress", "in_review", "done", "deployed", "pushed_live", "blocked")
PRIORITIES = ("low", "medium", "high", "critical")
ASSIGNEES = ("backend", "frontend", "devops", "sample", "unassigned")
SECURITY_SEVERITIES = ("low", "medium", "high", "critical")
RESOURCE_ROUTES = ("local", "vps", "sam_only")
OWNERS = ("auto", "sam", "backend", "frontend", "devops", "sample")

# Worker identifiers for the three-machine fleet (Section 4/6)
WORKERS = ("desktop", "mac", "vps")

# Run outcomes for ScheduleRun entities
RUN_OUTCOMES = ("completed", "partial", "failed", "abandoned")

# Status transitions tracked in ScheduleEvent
EVENT_TYPES = ("created", "status_change", "claimed", "lease_renewed",
               "completed", "lease_expired", "note_added", "resource_added",
               "hours_added", "reconciled")

# Lease duration: 90 minutes, extended by heartbeat (Section 1)
LEASE_DURATION_MINUTES = 90


def _now():
    return datetime.now(timezone.utc).isoformat()


def _item_id(title: str) -> str:
    """Build a deterministic entity ID from the item title slug."""
    slug = title.lower().strip().replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return f"PS-{slug[:60]}"


def _default_attributes(**overrides) -> dict[str, Any]:
    return {
        "title": "",
        "description": "",
        "type": "feature",
        "phase": "Phase 0",
        "status": "todo",
        "priority": "medium",
        "assignee": "unassigned",
        "est_hours": 0,
        "logged_hours": 0,
        "progress": 0,
        "depends_on": [],
        "security_severity": None,
        "work_notes": [],
        "resources": [],
        "resource_route": "local",
        "owner": "auto",
        "ci_commit_sha": None,
        "ci_passed": None,
        "deployment_run_id": None,
        "coolify_deployment_id": None,
        "pushed_live_at": None,
        "claimed_by": None,
        "claimed_at": None,
        "lease_expires_at": None,
        "created_at": _now(),
        "updated_at": _now(),
        **overrides,
    }


def _validate(attrs: dict[str, Any]) -> dict[str, Any] | None:
    """Return an error dict if invalid, None if valid."""
    if not attrs.get("title"):
        return {"error": "title is required"}
    if attrs["type"] not in ITEM_TYPES:
        return {"error": f"Invalid type '{attrs['type']}'. Valid: {list(ITEM_TYPES)}"}
    if attrs["phase"] not in PHASES:
        return {"error": f"Invalid phase '{attrs['phase']}'. Valid: {list(PHASES)}"}
    if attrs["status"] not in STATUSES:
        return {"error": f"Invalid status '{attrs['status']}'. Valid: {list(STATUSES)}"}
    if attrs["priority"] not in PRIORITIES:
        return {"error": f"Invalid priority '{attrs['priority']}'. Valid: {list(PRIORITIES)}"}
    if attrs["assignee"] not in ASSIGNEES:
        return {"error": f"Invalid assignee '{attrs['assignee']}'. Valid: {list(ASSIGNEES)}"}
    if attrs.get("type") == "security" and attrs.get("security_severity") not in SECURITY_SEVERITIES:
        return {"error": f"security_severity must be one of {list(SECURITY_SEVERITIES)} for security items"}
    if attrs.get("resource_route") not in RESOURCE_ROUTES:
        return {"error": f"Invalid resource_route '{attrs.get('resource_route')}'. Valid: {list(RESOURCE_ROUTES)}"}
    if attrs.get("owner") not in OWNERS:
        return {"error": f"Invalid owner '{attrs.get('owner')}'. Valid: {list(OWNERS)}"}
    if attrs.get("claimed_by") is not None and attrs.get("claimed_by") not in WORKERS:
        return {"error": f"Invalid claimed_by '{attrs.get('claimed_by')}'. Valid: {list(WORKERS)}"}
    if not isinstance(attrs["progress"], int) or not (0 <= attrs["progress"] <= 100):
        return {"error": "progress must be an integer 0-100"}
    if attrs["est_hours"] < 0 or attrs["logged_hours"] < 0:
        return {"error": "est_hours and logged_hours must be non-negative"}
    return None


def _save():
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)


def get_item(item_id: str) -> dict[str, Any] | None:
    """Return the full item dict, or None."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return None
    return {"id": entity.id, **dict(entity.attributes)}


def list_items(phase: str | None = None, assignee: str | None = None,
               status: str | None = None, item_type: str | None = None,
               priority: str | None = None,
               resource_route: str | None = None,
               owner: str | None = None) -> list[dict[str, Any]]:
    """List items with optional filters. Unfiltered returns all."""
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        a = entity.attributes
        if phase and a.get("phase") != phase:
            continue
        if assignee and a.get("assignee") != assignee:
            continue
        if status and a.get("status") != status:
            continue
        if item_type and a.get("type") != item_type:
            continue
        if priority and a.get("priority") != priority:
            continue
        if resource_route and a.get("resource_route") != resource_route:
            continue
        if owner and a.get("owner") != owner:
            continue
        results.append({"id": entity.id, **dict(a)})
    # Sort by phase order, then priority, then status
    phase_order = {p: i for i, p in enumerate(PHASES)}
    priority_order = {p: i for i, p in enumerate(PRIORITIES)}
    status_order = {s: i for i, s in enumerate(STATUSES)}
    results.sort(key=lambda r: (
        phase_order.get(r.get("phase", ""), 99),
        -priority_order.get(r.get("priority", ""), 0),
        status_order.get(r.get("status", ""), 99),
        r.get("title", ""),
    ))
    return results


def create_item(title: str, description: str = "", item_type: str = "feature",
                phase: str = "Phase 0", priority: str = "medium",
                assignee: str = "unassigned", est_hours: float = 0,
                depends_on: list[str] | None = None,
                security_severity: str | None = None,
                resource_route: str = "local",
                owner: str = "auto") -> dict[str, Any]:
    """Create a new programming schedule item."""
    attrs = _default_attributes(
        title=title, description=description, type=item_type, phase=phase,
        priority=priority, assignee=assignee, est_hours=est_hours,
        depends_on=depends_on or [], security_severity=security_severity,
        resource_route=resource_route, owner=owner,
    )
    err = _validate(attrs)
    if err:
        return err
    item_id = _item_id(title)
    if ledger.get_entity(item_id):
        return {"error": f"Item '{item_id}' already exists"}
    entity = Entity(id=item_id, entity_type=PROGRAMMING_SCHEDULE, attributes=attrs)
    ledger.add_entity(entity)
    _save()
    return {"id": item_id, **attrs}


def update_item(item_id: str, **fields) -> dict[str, Any]:
    """Patch an item. Returns the updated item or an error."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    # Merge fields into attributes, then validate
    new_attrs = {**dict(entity.attributes), **fields}
    # Ensure required fields exist for validation
    for key, default in _default_attributes().items():
        if key not in new_attrs:
            new_attrs[key] = default
    err = _validate(new_attrs)
    if err:
        return err
    entity.attributes = new_attrs
    entity.attributes["updated_at"] = _now()
    _save()
    return {"id": item_id, **{k: v for k, v in new_attrs.items() if k != "id"}}


def update_progress(item_id: str, progress: int) -> dict[str, Any]:
    """Quick progress update. Auto-advances status if progress hits 0 or 100."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    if not isinstance(progress, int) or not (0 <= progress <= 100):
        return {"error": "progress must be an integer 0-100"}
    entity.attributes["progress"] = progress
    entity.attributes["updated_at"] = _now()
    if progress >= 100 and entity.attributes["status"] != "done":
        entity.attributes["status"] = "in_review"
    elif 0 < progress < 100 and entity.attributes["status"] == "todo":
        entity.attributes["status"] = "in_progress"
    elif progress == 0 and entity.attributes["status"] == "in_progress":
        entity.attributes["status"] = "todo"
    _save()
    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


def assign_item(item_id: str, assignee: str) -> dict[str, Any]:
    """Assign an item to a team. Returns updated item."""
    if assignee not in ASSIGNEES:
        return {"error": f"Invalid assignee '{assignee}'. Valid: {list(ASSIGNEES)}"}
    return update_item(item_id, assignee=assignee)


def set_status(item_id: str, status: str) -> dict[str, Any]:
    """Set an item's status."""
    if status not in STATUSES:
        return {"error": f"Invalid status '{status}'. Valid: {list(STATUSES)}"}
    return update_item(item_id, status=status)


def add_hours(item_id: str, hours: float) -> dict[str, Any]:
    """Log development hours on an item."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    if hours <= 0:
        return {"error": "hours must be positive"}
    entity.attributes["logged_hours"] = entity.attributes.get("logged_hours", 0) + hours
    entity.attributes["updated_at"] = _now()
    _save()
    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


def add_work_note(item_id: str, note: str) -> dict[str, Any]:
    """Append a work-note entry to an item (what work has been applied)."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    if not note.strip():
        return {"error": "note must not be empty"}
    notes = entity.attributes.get("work_notes", [])
    notes.append({"timestamp": _now(), "note": note.strip()})
    entity.attributes["work_notes"] = notes
    entity.attributes["updated_at"] = _now()
    _save()
    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


def add_resource(item_id: str, resource: str) -> dict[str, Any]:
    """Attach a resource (file path, credential ref, access key, etc.) to an item."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    if not resource.strip():
        return {"error": "resource must not be empty"}
    resources = entity.attributes.get("resources", [])
    resources.append(resource.strip())
    entity.attributes["resources"] = resources
    entity.attributes["updated_at"] = _now()
    _save()
    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


def get_by_route(route: str) -> list[dict[str, Any]]:
    """Return items assigned to a specific resource_route (local, vps, sam_only)."""
    return list_items(resource_route=route)


def set_route(item_id: str, route: str, owner: str | None = None) -> dict[str, Any]:
    """Update the resource_route and optionally the owner for an item."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}
    if route not in RESOURCE_ROUTES:
        return {"error": f"Invalid route '{route}'. Valid: {list(RESOURCE_ROUTES)}"}
    entity.attributes["resource_route"] = route
    if owner is not None:
        if owner not in OWNERS:
            return {"error": f"Invalid owner '{owner}'. Valid: {list(OWNERS)}"}
        entity.attributes["owner"] = owner
    entity.attributes["updated_at"] = _now()
    _save()
    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


def get_dashboard() -> dict[str, Any]:
    """Return a dashboard summary: counts by phase, by assignee, by status, by type."""
    items = list_items()
    dashboard: dict[str, Any] = {
        "total": len(items),
        "by_phase": {},
        "by_assignee": {},
        "by_status": {},
        "by_type": {},
        "by_priority": {},
        "completed": 0,
        "remaining_hours": 0.0,
        "logged_hours": 0.0,
        "security_issues": 0,
        "blockers": 0,
        "deployed": 0,
        "pushed_live": 0,
    }
    # Statuses that count as "completable" for dashboard purposes
    COMPLETABLE_STATUSES = {"done", "deployed", "pushed_live"}
    for phase in PHASES:
        dashboard["by_phase"][phase] = {"total": 0, "done": 0, "remaining_hours": 0.0}
    for item in items:
        phase = item.get("phase", "")
        assignee = item.get("assignee", "unassigned")
        status = item.get("status", "todo")
        itype = item.get("type", "feature")
        priority = item.get("priority", "medium")
        est = item.get("est_hours", 0)
        logged = item.get("logged_hours", 0)
        dashboard["by_phase"].setdefault(phase, {"total": 0, "done": 0, "remaining_hours": 0.0})
        dashboard["by_phase"][phase]["total"] += 1
        if status in {"done", "deployed", "pushed_live"}:
            dashboard["by_phase"][phase]["done"] += 1
        else:
            dashboard["by_phase"][phase]["remaining_hours"] += max(0, est - logged)

        dashboard["by_assignee"][assignee] = dashboard["by_assignee"].get(assignee, 0) + 1
        dashboard["by_status"][status] = dashboard["by_status"].get(status, 0) + 1
        dashboard["by_type"][itype] = dashboard["by_type"].get(itype, 0) + 1
        dashboard["by_priority"][priority] = dashboard["by_priority"].get(priority, 0) + 1
        if itype == "security":
            dashboard["security_issues"] += 1

        if status == "blocked":
            dashboard["blockers"] += 1
        if status == "deployed":
            dashboard["deployed"] += 1
        if status == "pushed_live":
            dashboard["pushed_live"] += 1
        if status in {"done", "deployed", "pushed_live"}:
            dashboard["completed"] += 1
        dashboard["remaining_hours"] += max(0, est - logged) if status not in {"done", "deployed", "pushed_live"} else 0
        dashboard["logged_hours"] += logged

    # Add phase ordering to by_phase
    ordered_phases = {}
    for phase in PHASES:
        if phase in dashboard["by_phase"]:
            ordered_phases[phase] = dashboard["by_phase"][phase]
    dashboard["by_phase"] = ordered_phases

    return dashboard



# ---------------------------------------------------------------------------
# Schedule Runs (Section 1: schedule_runs entity type)
# ---------------------------------------------------------------------------

def _run_id(item_id: str, worker: str) -> str:
    """Generate a deterministic run ID from item + worker + timestamp."""
    from core.dealeros import ledger
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"SR-{item_id}-{worker}-{ts}"
    # If collision (same second), append counter
    counter = 1
    while run_id in ledger.entities:
        run_id = f"SR-{item_id}-{worker}-{ts}-{counter}"
        counter += 1
    return run_id


def create_run(item_id: str, worker: str, hermes_job_id: str | None = None,
               provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Create a ScheduleRun entity for a claimed item.

    Called by /claim after an item is claimed. The run starts in 'running'
    state with heartbeat_at = now. The lease on the parent PS item is set to
    90 minutes from now.
    """
    from core.dealeros import ledger
    from core.entities import Entity
    from core.entity_types import SCHEDULE_RUN

    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found or not a schedule item"}

    run_id = _run_id(item_id, worker)
    now = _now()
    lease_expiry = (datetime.now(timezone.utc) + timedelta(minutes=LEASE_DURATION_MINUTES)).isoformat()

    run_attrs = {
        "item_id": item_id,
        "worker": worker,
        "hermes_job_id": hermes_job_id,
        "provider": provider,
        "model": model,
        "started_at": now,
        "heartbeat_at": now,
        "finished_at": None,
        "outcome": "running",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cost_usd": 0.0,
        "commit_sha": None,
        "tests_summary": None,
        "notes": [],
    }

    # Atomically set the lease on the parent item + create the run
    entity.attributes["claimed_by"] = worker
    entity.attributes["claimed_at"] = now
    entity.attributes["lease_expires_at"] = lease_expiry
    entity.attributes["status"] = "in_progress"
    entity.attributes["updated_at"] = now

    ledger.add_entity(Entity(id=run_id, entity_type=SCHEDULE_RUN, attributes=run_attrs))
    _save()

    add_event(item_id, "claimed", worker,
              f"Claimed by {worker} for run {run_id}")
    return {"run_id": run_id, **{k: v for k, v in run_attrs.items()}}


def get_run(run_id: str) -> dict[str, Any] | None:
    """Return a schedule run dict, or None."""
    from core.dealeros import ledger
    from core.entity_types import SCHEDULE_RUN
    entity = ledger.get_entity(run_id)
    if not entity or entity.entity_type != SCHEDULE_RUN:
        return None
    return {"id": entity.id, **dict(entity.attributes)}


def list_runs(item_id: str | None = None, worker: str | None = None,
              outcome: str | None = None) -> list[dict[str, Any]]:
    """List schedule runs, optionally filtered by item, worker, or outcome."""
    from core.dealeros import ledger
    from core.entity_types import SCHEDULE_RUN
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != SCHEDULE_RUN:
            continue
        a = entity.attributes
        if item_id and a.get("item_id") != item_id:
            continue
        if worker and a.get("worker") != worker:
            continue
        if outcome and a.get("outcome") != outcome:
            continue
        results.append({"id": entity.id, **dict(a)})
    results.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return results


def heartbeat_run(run_id: str, input_tokens: int = 0, output_tokens: int = 0,
                  cache_read_tokens: int = 0, cost_usd: float = 0.0) -> dict[str, Any]:
    """Extend a run's lease and update token/cost counters.

    Called every few minutes by the worker. Resets lease_expires_at on the
    parent PS item to 90 min from now.
    """
    from core.dealeros import ledger

    run_entity = ledger.get_entity(run_id)
    if not run_entity:
        return {"error": f"Run '{run_id}' not found"}

    now = _now()
    run_entity.attributes["heartbeat_at"] = now
    if input_tokens:
        run_entity.attributes["input_tokens"] = run_entity.attributes.get("input_tokens", 0) + input_tokens
    if output_tokens:
        run_entity.attributes["output_tokens"] = run_entity.attributes.get("output_tokens", 0) + output_tokens
    if cache_read_tokens:
        run_entity.attributes["cache_read_tokens"] = run_entity.attributes.get("cache_read_tokens", 0) + cache_read_tokens
    if cost_usd:
        run_entity.attributes["cost_usd"] = round(run_entity.attributes.get("cost_usd", 0.0) + cost_usd, 6)

    # Extend the lease on the parent PS item
    item_id = run_entity.attributes.get("item_id")
    item_entity = ledger.get_entity(item_id)
    if item_entity and item_entity.entity_type == PROGRAMMING_SCHEDULE:
        worker = run_entity.attributes.get("worker")
        item_entity.attributes["lease_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=LEASE_DURATION_MINUTES)
        ).isoformat()
        item_entity.attributes["updated_at"] = now

    _save()
    add_event(item_id, "lease_renewed", run_entity.attributes.get("worker"),
              f"Heartbeat for run {run_id}")
    return {"id": run_id, **{k: v for k, v in run_entity.attributes.items()}}


def complete_run(run_id: str, outcome: str, commit_sha: str | None = None,
                 tests_summary: str | None = None, notes: str | None = None,
                 progress: int | None = None) -> dict[str, Any]:
    """Mark a schedule run as complete with outcome, commit, and test results.

    outcome must be one of RUN_OUTCOMES. If 'completed', the parent PS item's
    lease is released (claimed_by=None) so it can be claimed again if needed.
    """
    from core.dealeros import ledger

    if outcome not in RUN_OUTCOMES:
        return {"error": f"Invalid outcome '{outcome}'. Valid: {list(RUN_OUTCOMES)}"}

    run_entity = ledger.get_entity(run_id)
    if not run_entity:
        return {"error": f"Run '{run_id}' not found"}

    now = _now()
    run_entity.attributes["finished_at"] = now
    run_entity.attributes["outcome"] = outcome
    if commit_sha:
        run_entity.attributes["commit_sha"] = commit_sha
    if tests_summary:
        run_entity.attributes["tests_summary"] = tests_summary
    if notes:
        run_entity.attributes["notes"] = run_entity.attributes.get("notes", []) + [notes]

    # Release the lease on the parent PS item
    item_id = run_entity.attributes.get("item_id")
    item_entity = ledger.get_entity(item_id)
    if item_entity and item_entity.entity_type == PROGRAMMING_SCHEDULE:
        if outcome in ("completed", "abandoned"):
            item_entity.attributes["claimed_by"] = None
            item_entity.attributes["claimed_at"] = None
            item_entity.attributes["lease_expires_at"] = None
        if progress is not None:
            item_entity.attributes["progress"] = progress
        item_entity.attributes["updated_at"] = now

    _save()
    add_event(item_id, outcome, run_entity.attributes.get("worker"),
              f"Run {run_id} {outcome}" + (f" — {tests_summary}" if tests_summary else ""))
    return {"id": run_id, **{k: v for k, v in run_entity.attributes.items()}}


def release_expired_leases() -> int:
    """Release PS items whose lease has expired. Returns count released."""
    from core.dealeros import ledger

    now = datetime.now(timezone.utc)
    released = 0
    for entity_id in list(ledger.entities.keys()):
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        lease_exp = entity.attributes.get("lease_expires_at")
        if not lease_exp:
            continue
        try:
            exp_time = datetime.fromisoformat(lease_exp)
            if now > exp_time:
                entity.attributes["claimed_by"] = None
                entity.attributes["claimed_at"] = None
                entity.attributes["lease_expires_at"] = None
                entity.attributes["updated_at"] = _now()
                add_event(entity_id, "lease_expired", None,
                          f"Lease expired ({lease_exp})")
                released += 1
        except (ValueError, TypeError):
            continue
    if released:
        _save()
    return released


def get_active_runs() -> list[dict[str, Any]]:
    """Return all ScheduleRun entities with outcome == 'running'."""
    return list_runs(outcome="running")


# ---------------------------------------------------------------------------
# Schedule Events (Section 1: schedule_events entity type)
# ---------------------------------------------------------------------------

def add_event(item_id: str, event_type: str, actor: str | None,
              evidence: str) -> dict[str, Any]:
    """Append a ScheduleEvent to an item's audit trail."""
    from core.dealeros import ledger
    from core.entities import Entity
    from core.entity_types import SCHEDULE_EVENT

    if event_type not in EVENT_TYPES:
        return {"error": f"Invalid event_type '{event_type}'. Valid: {list(EVENT_TYPES)}"}

    # Verify the item exists
    item_entity = ledger.get_entity(item_id)
    if not item_entity or item_entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}

    now = _now()
    counter = 0
    # Build a sortable timestamp suffix from the datetime without relying on
    # int() parsing of a full ISO string (which contains +00:00 timezone).
    ts_suffix = now.replace("-", "").replace(":", "").replace(".", "").replace("+", "")
    while True:
        event_id = f"SE-{item_id}-{ts_suffix[:16]}-{counter:04d}"
        if event_id not in ledger.entities:
            break
        counter += 1

    event = Entity(
        id=event_id,
        entity_type=SCHEDULE_EVENT,
        attributes={
            "item_id": item_id,
            "event_type": event_type,
            "actor": actor,
            "evidence": evidence,
            "timestamp": now,
        }
    )
    ledger.add_entity(event)
    _save()
    return {"id": event_id, **dict(event.attributes)}


def get_events(item_id: str) -> list[dict[str, Any]]:
    """Return all ScheduleEvent entities for a given item, ordered by timestamp."""
    from core.dealeros import ledger
    from core.entity_types import SCHEDULE_EVENT
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != SCHEDULE_EVENT:
            continue
        if entity.attributes.get("item_id") != item_id:
            continue
        results.append({"id": entity.id, **dict(entity.attributes)})
    results.sort(key=lambda r: r.get("timestamp", ""))
    return results


# ---------------------------------------------------------------------------
# Claim (Section 2 machine endpoint)
# ---------------------------------------------------------------------------

def _dependencies_done(item: dict[str, Any]) -> bool:
    """Check if all depends_on items are in a completable status."""
    for dep_id in item.get("depends_on", []):
        dep = get_item(dep_id)
        if dep is None:
            return False
        if dep["status"] not in ("done", "deployed", "pushed_live"):
            return False
    return True


def claim_item(route: str, worker: str) -> dict[str, Any]:
    """Atomically claim the next eligible item for a worker on a given route.

    Selection criteria:
      - resource_route matches the requested route (local|vps)
      - status == "todo"
      - resource_route != "sam_only" (never claimed by Hermes)
      - claimed_by is None (not already leased by another worker)
      - all depends_on items are done/deployed/pushed_live

    Ordering: phase, then priority (critical>high>medium>low), then est_hours asc.

    Returns the claimed item dict + run_id, or {"error": ...}.
    """
    from core.dealeros import ledger

    if route not in ("local", "vps"):
        return {"error": f"Invalid route '{route}'. Must be 'local' or 'vps'"}
    if worker not in WORKERS:
        return {"error": f"Invalid worker '{worker}'. Valid: {list(WORKERS)}"}

    # Release any expired leases first
    release_expired_leases()

    # Gather candidates
    candidates = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        a = entity.attributes
        if a.get("resource_route") != route:
            continue
        if a.get("status") != "todo":
            continue
        if a.get("claimed_by") is not None:
            continue
        if a.get("resource_route") == "sam_only":
            continue
        item = {"id": entity.id, **dict(a)}
        if not _dependencies_done(item):
            continue
        candidates.append(item)

    if not candidates:
        return {"error": "No eligible items available for this route"}

    # Sort: phase order, then priority descending (critical first), then est_hours asc
    phase_order = {p: i for i, p in enumerate(PHASES)}
    priority_order = {p: i for i, p in enumerate(PRIORITIES)}
    candidates.sort(key=lambda r: (
        phase_order.get(r.get("phase", ""), 99),
        -priority_order.get(r.get("priority", "medium"), 2),
        r.get("est_hours", 0),
        r.get("title", ""),
    ))

    item = candidates[0]
    item_id = item["id"]

    # Double-check lease is still None (could have been claimed between scan and set)
    entity = ledger.get_entity(item_id)
    if entity.attributes.get("claimed_by") is not None:
        return {"error": "Item was claimed by another worker — retry"}
    entity.attributes["claimed_by"] = worker
    entity.attributes["claimed_at"] = _now()
    entity.attributes["lease_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(minutes=LEASE_DURATION_MINUTES)
    ).isoformat()
    entity.attributes["status"] = "in_progress"
    entity.attributes["updated_at"] = _now()

    run_result = create_run(item_id, worker)
    if "error" in run_result:
        # Roll back the claim
        entity.attributes["claimed_by"] = None
        entity.attributes["claimed_at"] = None
        entity.attributes["lease_expires_at"] = None
        entity.attributes["status"] = "todo"
        _save()
        return run_result

    run_id = run_result["run_id"]
    item["claimed_by"] = worker
    item["claimed_at"] = _now()
    item["lease_expires_at"] = entity.attributes["lease_expires_at"]
    item["status"] = "in_progress"
    item["run_id"] = run_id
    return item
