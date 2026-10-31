"""
Event Project Management + War Room (2026-07-18, Marketing Growth Platform -- the
"War Room, Project Management, Campaign Generator" items flagged as open at the end
of the Events dash's original build, session 84).

Project Management: a real planning checklist per Event -- vendor coordination,
staffing, day-of logistics -- distinct from RSVP tracking (who's coming) and the
Timeline (individual customer signals). An EventTask is its own first-class entity
(core/entity_types.py's EVENT_TASK), same "own lifecycle, not a dict on something
else" reasoning this codebase uses throughout (OperationsTask, DamageReport,
RepossessionCase, etc.) -- a real event accumulates many distinct planning items over
its life, each independently assignable/completable.

War Room: a real, composed live-operations view for one Event -- not a new data
source, a real-time roll-up of what's already tracked elsewhere: RSVP status breakdown
(core/dealership_events.py), planning-task completion (this module), and generated
promo campaigns (core/event_campaign_generator.py). "Live" check-in counting reuses
EventRSVP's existing "attended" status as the real check-in signal -- no new
check-in/kiosk mechanism is built here (flagged as still open in CLAUDE.md).
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import EVENT_TASK
from core.dealership_events import get_event, get_event_detail
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

TASK_STATUSES = ["open", "in_progress", "done", "blocked"]

_EDITABLE_FIELDS = {"title", "assignee_employee_id", "due_date", "notes"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(value):

    if not value:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def create_task(event_id, created_by, title, assignee_employee_id=None, due_date=None, notes=""):

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if not (title or "").strip():
        return {"error": "A task needs a title"}

    task_id = id_generator.generate("ETASK")

    entity = Entity(
        id=task_id,
        entity_type=EVENT_TASK,
        attributes={
            "event_id": event_id,
            "title": title.strip(),
            "assignee_employee_id": assignee_employee_id,
            "due_date": due_date,
            "notes": notes or "",
            "status": "open",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "completed_at": None,
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_task(task_id):

    entity = ledger.get_entity(task_id)

    if entity and entity.entity_type == EVENT_TASK:
        return entity

    return None


def update_task(task_id, patch):

    task = get_task(task_id)

    if not task:
        return {"error": "Task not found"}

    for key, value in (patch or {}).items():
        if key in _EDITABLE_FIELDS:
            task.attributes[key] = value

    task.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return task


def update_task_status(task_id, status):

    if status not in TASK_STATUSES:
        return {"error": f"status must be one of {', '.join(TASK_STATUSES)}"}

    task = get_task(task_id)

    if not task:
        return {"error": "Task not found"}

    task.attributes["status"] = status
    task.attributes["updated_at"] = _now()
    task.attributes["completed_at"] = _now() if status == "done" else None

    save_graph(GRAPH_PATH)

    return task


def delete_task(task_id):

    task = get_task(task_id)

    if not task:
        return {"error": "Task not found"}

    del ledger.entities[task_id]

    save_graph(GRAPH_PATH)

    return {"deleted": task_id}


def list_tasks_for_event(event_id, status=None):

    tasks = [
        e for e in ledger.get_all().values()
        if e.entity_type == EVENT_TASK and e.attributes.get("event_id") == event_id
    ]

    if status:
        tasks = [t for t in tasks if t.attributes.get("status") == status]

    tasks.sort(key=lambda t: (t.attributes.get("due_date") or "9999-99-99", t.attributes.get("created_at", "")))

    return tasks


def get_project_management_summary(event_id):
    """Real completion %, real by-status breakdown, real overdue count (a due_date in
    the past on a task that isn't done/blocked -- 'blocked' is excluded from overdue
    since it's an honest, already-flagged exception rather than silent slippage)."""

    tasks = list_tasks_for_event(event_id)

    by_status = {s: 0 for s in TASK_STATUSES}
    overdue = []

    for t in tasks:

        status = t.attributes.get("status", "open")
        by_status[status] = by_status.get(status, 0) + 1

        due = _parse_date(t.attributes.get("due_date"))

        if due and due < _today() and status not in ("done", "blocked"):
            overdue.append({"id": t.id, "title": t.attributes.get("title"), "due_date": t.attributes.get("due_date"), "assignee_employee_id": t.attributes.get("assignee_employee_id")})

    total = len(tasks)
    done = by_status.get("done", 0)

    return {
        "event_id": event_id,
        "total_tasks": total,
        "by_status": by_status,
        "completion_pct": round((done / total) * 100, 1) if total else None,
        "overdue_tasks": overdue,
        "overdue_count": len(overdue),
    }


def get_event_war_room(event_id):
    """A real, composed live-operations view -- not a new data source. Pulls the
    Event's own real RSVP summary (core/dealership_events.py's get_event_detail(),
    already-established shape), this module's own task-completion summary, and
    generated promo campaigns (core/event_campaign_generator.py, imported locally to
    avoid a circular import since that module imports get_event_war_room() nowhere,
    but does import from core.campaigns which this module doesn't otherwise touch).
    'Live' attendee counting reuses EventRSVP's real 'attended' status -- no separate
    check-in mechanism exists in this codebase (flagged, not built here)."""

    from core.event_campaign_generator import list_campaigns_for_event

    detail = get_event_detail(event_id)

    if isinstance(detail, dict) and "error" in detail:
        return detail

    event = detail["event"]
    rsvp_summary = detail["rsvp_summary"]
    rsvps = detail["rsvps"]

    checked_in = [r for r in rsvps if r.get("status") == "attended"]
    no_shows = [r for r in rsvps if r.get("status") == "no_show"]
    total_invited_or_confirmed = len(rsvps)

    pm = get_project_management_summary(event_id)
    campaigns = list_campaigns_for_event(event_id)
    from core.event_outcomes import summarize_event_outcomes
    outcomes = summarize_event_outcomes({c.id for c in campaigns})

    return {
        "event": event,
        "is_live": event.get("status") == "live",
        "rsvp_summary": rsvp_summary,
        "outcomes": outcomes,
        "attendance": {
            "total_roster": total_invited_or_confirmed,
            "checked_in_count": len(checked_in),
            "no_show_count": len(no_shows),
            "check_in_rate_pct": round((len(checked_in) / total_invited_or_confirmed) * 100, 1) if total_invited_or_confirmed else None,
            "basis": "Check-in totals come from attendees marked as attended in RSVP Management.",
        },
        "project_management": pm,
        "campaigns_generated": len(campaigns),
        "recent_campaigns": [
            {"id": c.id, "name": c.attributes.get("name"), "status": c.attributes.get("status"), "channel": c.attributes.get("channel")}
            for c in campaigns[:5]
        ],
    }
