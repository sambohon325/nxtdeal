"""Thin ACL layer for core/communications_hub.py's first-class Communication
log (recording/transcript/sentiment simulation, follow-ups, real AI
summaries) -- same "no service layer indirection" convention as every other
*_api.py module in this codebase.

Logging a communication (log_communication_api) is open to ANY authenticated
role, matching core/field_notes_api.py's own established precedent exactly
("any authenticated role can log a field note ... there's no approval step
to gate") -- a Communication is the same class of everyday staff action a
FieldNote already is, just with a richer shape.

Viewing (get/list/stats/overview) and the two mutating actions that act on
an ALREADY-logged communication (complete_follow_up, generate_ai_summary)
use the same broad VIEW_ROLES tuple core/unified_communications_api.py
already established for this exact cross-department Communications Hub
screen -- every real role can see/act on it, since this is a staff-facing
view of already-real, already-permitted contact logs, no new sensitive data
exposed beyond what each source module already allows its own department to
see."""

from core.communications_hub import (
    CHANNELS,
    DIRECTIONS,
    complete_follow_up,
    generate_ai_summary,
    get_communication,
    get_communications_hub_overview,
    get_communications_stats,
    list_communications,
    log_communication,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def log_communication_api(
    employee_id,
    department,
    channel,
    direction,
    body,
    linked_entity_id=None,
    duration_seconds=None,
    follow_up_required=False,
    follow_up_due_at=None,
    follow_up_note=None,
):

    comm, error = log_communication(
        department=department,
        channel=channel,
        direction=direction,
        body=body,
        created_by=employee_id,
        linked_entity_id=linked_entity_id,
        duration_seconds=duration_seconds,
        follow_up_required=follow_up_required,
        follow_up_due_at=follow_up_due_at,
        follow_up_note=follow_up_note,
    )

    if error:
        return {"error": error}

    return comm


def get_communication_api(role, comm_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view this communication."}

    comm, error = get_communication(comm_id)
    if error:
        return {"error": error}

    return comm


def list_communications_api(
    role,
    department=None,
    channel=None,
    linked_entity_id=None,
    follow_up_pending_only=False,
    limit=200,
):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view communications."}

    return list_communications(
        department=department,
        channel=channel,
        linked_entity_id=linked_entity_id,
        follow_up_pending_only=follow_up_pending_only,
        limit=limit,
    )


def complete_follow_up_api(role, employee_id, comm_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to complete a follow-up."}

    comm, error = complete_follow_up(comm_id, employee_id)
    if error:
        return {"error": error}

    return comm


def get_communications_stats_api(role, department=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view communications stats."}

    return get_communications_stats(department=department)


def generate_ai_summary_api(role, comm_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate an AI summary."}

    summary, error = generate_ai_summary(comm_id)
    if error:
        return {"error": error}

    return summary


def get_communications_hub_overview_api(role, department=None, channel=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the Communications Hub."}

    return get_communications_hub_overview(role, department=department, channel=channel)
