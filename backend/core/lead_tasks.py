"""
Lead follow-up task management (Sales sub-menu spec, session 92 follow-up). Sam:
"Task Management: Create: Call tomorrow, Send pricing, Schedule appraisal, Follow up
after demo." A LeadTask is an ordinary graph entity tied to a Lead via `lead_id` --
distinct from core/bot_tasks.py's auto-generated per-role nudges (a different concept
entirely: those are computed suggestions, these are things a salesperson or manager
explicitly asked to be reminded of).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import LEAD_TASK, LEAD
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 92
# follow-up) -- every real lead task ever created or completed had been silently
# discarded on server restart. Fixed below: every mutating function now saves directly.

TASK_TYPES = ["call", "send_pricing", "schedule_appraisal", "follow_up_after_demo", "custom"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_task(lead_id, task_type, description, due_at, created_by, assigned_to=None):

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {"error": f"Lead '{lead_id}' not found"}

    if task_type not in TASK_TYPES:
        return {"error": f"task_type must be one of {TASK_TYPES}"}

    task_id = id_generator.generate("LTASK")

    entity = Entity(
        id=task_id,
        entity_type=LEAD_TASK,
        attributes={
            "lead_id": lead_id,
            "task_type": task_type,
            "description": description or "",
            "due_at": due_at,
            "completed": False,
            "completed_at": None,
            "completed_by": None,
            "created_by": created_by,
            "assigned_to": assigned_to or created_by,
            "created_at": _now(),
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_task(task_id):

    entity = ledger.get_entity(task_id)

    if entity and entity.entity_type == LEAD_TASK:
        return entity

    return None


def complete_task(task_id, completed_by):

    task = get_task(task_id)

    if not task:
        return {"error": "Task not found"}

    if task.attributes.get("completed"):
        return {"error": "Task is already completed"}

    task.attributes["completed"] = True
    task.attributes["completed_at"] = _now()
    task.attributes["completed_by"] = completed_by

    save_graph(GRAPH_PATH)

    return task


def list_tasks(lead_id=None, assigned_to=None, include_completed=True):

    tasks = [e for e in ledger.get_all().values() if e.entity_type == LEAD_TASK]

    if lead_id:
        tasks = [t for t in tasks if t.attributes.get("lead_id") == lead_id]

    if assigned_to:
        tasks = [t for t in tasks if t.attributes.get("assigned_to") == assigned_to]

    if not include_completed:
        tasks = [t for t in tasks if not t.attributes.get("completed")]

    tasks.sort(key=lambda t: t.attributes.get("due_at") or t.attributes.get("created_at") or "")

    return tasks


def list_overdue_tasks(lead_id=None, assigned_to=None, as_of=None):
    """Open tasks whose due_at has already passed -- the real signal
    core/lead_record.py's Next Best Action rules engine uses, plus whatever a
    dashboard wants for an "overdue follow-ups" count. `assigned_to` added
    (session 94 follow-up, Sales Overview) so a per-employee "My Tasks" widget and a
    team-wide "Overdue Follow Ups" manager view can both filter without a second
    query path."""

    as_of = as_of or _now()

    return [
        t for t in list_tasks(lead_id=lead_id, assigned_to=assigned_to, include_completed=False)
        if t.attributes.get("due_at") and t.attributes["due_at"] < as_of
    ]
