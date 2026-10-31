"""
The Lead Record (Sales sub-menu spec, session 92 follow-up). Sam's Prospects ask:
"When opening a prospect: Customer Profile, Activity Timeline, Communication Hub
(Call/Text/Email/Video, all logged automatically), Task Management, Customer Notes,
Next Best Action."

Assembles a single real view from pieces that already exist (the Lead entity itself,
core/ai_tools.py's role-filtered one-hop traversal, core/audit_api.py's real
"workflow_transition" events, core/field_notes.py's CRM-category notes, and
core/lead_tasks.py's follow-ups) rather than inventing a parallel store. The one new
piece of logic here is next_best_action() -- a small, honestly-labeled rules engine
computed off real signals already on the graph (days in current pipeline state,
whether any communication has been logged, overdue tasks), NOT a fabricated
AI/email-open-tracking recommendation like Sam's own example illustrated ("customer
opened pricing email") -- no email-open-tracking data model exists anywhere in this
codebase, so that exact signal can't be honestly computed. This gives the same kind
of actionable nudge using data that's actually real.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD
from core.ai_tools import get_entity_by_id, get_related_entities
from core.field_notes import list_field_notes
from core.lead_tasks import list_tasks

COMMUNICATION_CATEGORIES = {"call", "text", "email", "video"}
NOTE_CATEGORIES = {"objection", "family", "competitor", "payment_goal", "general"}


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _days_since(ts):
    dt = _parse(ts)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_now() - dt).days


def next_best_action(lead, communications, open_tasks, overdue_tasks):
    """Real, rules-based -- not an LLM call, not a fabricated engagement signal.
    Checked in priority order; the first match wins."""

    state = lead.attributes.get("PipelineState")

    if state in ("SOLD", "LOST"):
        return {"action": "None", "reason": f"This lead is already {state.lower()}."}

    if overdue_tasks:
        t = overdue_tasks[0]
        return {
            "action": f"Overdue: {t.attributes.get('description') or t.attributes.get('task_type')}",
            "reason": f"{len(overdue_tasks)} task(s) past due, oldest due {t.attributes.get('due_at')}.",
            "basis": "real_task_data",
        }

    if not communications:
        days = _days_since(lead.attributes.get("PipelineCreatedAt"))
        return {
            "action": "Call now",
            "reason": f"No call/text/email/video has been logged for this lead yet{f' ({days} days since it entered the pipeline)' if days is not None else ''}.",
            "basis": "real_communication_log",
        }

    days_in_state = _days_since(lead.attributes.get("PipelineStateSince"))

    if state in ("CONTACTED", "APPOINTMENT_SET", "VISITED", "PROPOSAL", "NEGOTIATION") and days_in_state is not None and days_in_state >= 2 and not open_tasks:
        return {
            "action": "Follow up today",
            "reason": f"Lead has been in {state} for {days_in_state} day(s) with no open follow-up task scheduled.",
            "basis": "real_pipeline_state_data",
        }

    if open_tasks:
        t = open_tasks[0]
        return {
            "action": f"Upcoming: {t.attributes.get('description') or t.attributes.get('task_type')}",
            "reason": f"Due {t.attributes.get('due_at')}.",
            "basis": "real_task_data",
        }

    return {"action": "On track", "reason": "No overdue tasks or contact gaps detected right now.", "basis": "real_pipeline_state_data"}


def get_lead_record(role, lead_id):

    lead_result = get_entity_by_id(role, lead_id)

    if "error" in lead_result:
        return lead_result

    entity = ledger.get_entity(lead_id)

    if not entity or entity.entity_type != LEAD:
        return {"error": "Lead not found"}

    related = get_related_entities(role, lead_id)

    all_notes = list_field_notes(linked_entity_id=lead_id, limit=200)
    communications = [n for n in all_notes if n.attributes.get("category") in COMMUNICATION_CATEGORIES]
    notes = [n for n in all_notes if n.attributes.get("category") in NOTE_CATEGORIES]

    tasks = list_tasks(lead_id=lead_id)
    open_tasks = [t for t in tasks if not t.attributes.get("completed")]
    now_iso = _now().isoformat()
    overdue_tasks = [t for t in open_tasks if t.attributes.get("due_at") and t.attributes["due_at"] < now_iso]

    def _note_brief(n):
        return {
            "id": n.id,
            "category": n.attributes.get("category"),
            "body": n.attributes.get("body"),
            "created_by": n.attributes.get("created_by"),
            "created_at": n.attributes.get("created_at"),
        }

    def _task_brief(t):
        return {
            "id": t.id,
            "task_type": t.attributes.get("task_type"),
            "description": t.attributes.get("description"),
            "due_at": t.attributes.get("due_at"),
            "completed": t.attributes.get("completed"),
            "completed_at": t.attributes.get("completed_at"),
            "assigned_to": t.attributes.get("assigned_to"),
        }

    # Activity Timeline -- merges real pipeline-transition audit events with the real
    # communication/note log and task lifecycle events, one chronological feed.
    from core.audit_api import list_audit_events

    timeline = []

    for event in list_audit_events(entity_id=lead_id):
        timeline.append({
            "type": event["event_type"],
            "summary": event["summary"],
            "actor": event["actor"],
            "timestamp": event["timestamp"],
            "details": event["details"],
        })

    for n in all_notes:
        category = n.attributes.get("category")
        kind = "communication" if category in COMMUNICATION_CATEGORIES else "note"
        timeline.append({
            "type": kind,
            "summary": f"{category}: {(n.attributes.get('body') or '')[:140]}",
            "actor": n.attributes.get("created_by"),
            "timestamp": n.attributes.get("created_at"),
            "details": {"category": category},
        })

    for t in tasks:
        timeline.append({
            "type": "task_created",
            "summary": f"Task created: {t.attributes.get('description') or t.attributes.get('task_type')}",
            "actor": t.attributes.get("created_by"),
            "timestamp": t.attributes.get("created_at"),
            "details": {"due_at": t.attributes.get("due_at")},
        })
        if t.attributes.get("completed"):
            timeline.append({
                "type": "task_completed",
                "summary": f"Task completed: {t.attributes.get('description') or t.attributes.get('task_type')}",
                "actor": t.attributes.get("completed_by"),
                "timestamp": t.attributes.get("completed_at"),
                "details": {},
            })

    timeline.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    return {
        "lead": lead_result,
        "related_entities": related,
        "communications": [_note_brief(n) for n in communications],
        "notes": [_note_brief(n) for n in notes],
        "tasks": [_task_brief(t) for t in tasks],
        "open_task_count": len(open_tasks),
        "overdue_task_count": len(overdue_tasks),
        "timeline": timeline,
        "next_best_action": next_best_action(entity, communications, open_tasks, overdue_tasks),
        "not_yet_tracked": {
            "preferred_communication_method": "No preferred-contact-method field exists on Lead yet.",
            "trade_information": "Trade details aren't captured until a Deal is desked (see the Deals submenu's Trade Appraisal).",
            "credit_status": "No credit data is captured on a Lead -- only on a Customer, post-conversion.",
        },
    }
