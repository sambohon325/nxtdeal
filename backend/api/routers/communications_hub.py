"""Communications Hub router -- core/communications_hub.py's first-class
Communication log (recording/transcript/sentiment simulation, follow-ups,
real AI summaries). See that module's own docstring for the full "why a new
entity, not a FieldNote" reasoning and the composition-not-replacement
relationship with core/unified_communications.py.

Follows api/routers/ai_kill_switch.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.communications_hub_api import (
    complete_follow_up_api,
    generate_ai_summary_api,
    get_communication_api,
    get_communications_hub_overview_api,
    get_communications_stats_api,
    list_communications_api,
    log_communication_api,
)


router = APIRouter()


class LogCommunicationRequest(BaseModel):

    department: str
    channel: str
    direction: str
    body: str
    linked_entity_id: str | None = None
    duration_seconds: int | None = None
    follow_up_required: bool = False
    follow_up_due_at: str | None = None
    follow_up_note: str | None = None


@router.post("/communications-hub/log")
def communications_hub_log_route(request: LogCommunicationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_communication_api(
        payload["employee_id"],
        department=request.department,
        channel=request.channel,
        direction=request.direction,
        body=request.body,
        linked_entity_id=request.linked_entity_id,
        duration_seconds=request.duration_seconds,
        follow_up_required=request.follow_up_required,
        follow_up_due_at=request.follow_up_due_at,
        follow_up_note=request.follow_up_note,
    )


@router.get("/communications-hub/overview")
def communications_hub_overview_route(
    department: str = None, channel: str = None, authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_communications_hub_overview_api(payload["role"], department=department, channel=channel)


@router.get("/communications-hub/stats")
def communications_hub_stats_route(department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_communications_stats_api(payload["role"], department=department)


@router.get("/communications-hub/list")
def communications_hub_list_route(
    department: str = None,
    channel: str = None,
    linked_entity_id: str = None,
    follow_up_pending_only: bool = False,
    limit: int = 200,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_communications_api(
        payload["role"],
        department=department,
        channel=channel,
        linked_entity_id=linked_entity_id,
        follow_up_pending_only=follow_up_pending_only,
        limit=limit,
    )


@router.get("/communications-hub/{comm_id}")
def communications_hub_get_route(comm_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_communication_api(payload["role"], comm_id)


@router.post("/communications-hub/{comm_id}/complete-follow-up")
def communications_hub_complete_follow_up_route(comm_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_follow_up_api(payload["role"], payload["employee_id"], comm_id)


@router.post("/communications-hub/{comm_id}/generate-ai-summary")
def communications_hub_generate_ai_summary_route(comm_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_ai_summary_api(payload["role"], comm_id)
