"""Call Center router -- core/call_center.py's first-class Call entity (Phase 2:
Communications Platform, Voice -- 2026-07-22): inbound routing with least-busy
agent auto-assignment, outbound placement, reassignment, connect/end lifecycle,
missed-call handling, and simulated voicemail. See that module's own docstring
for the full recording/voicemail-simulation reasoning and its relationship to
core/communications_hub.py (every ended/voicemail call produces exactly one
Communication record there).

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.call_center_api import (
    connect_call_api,
    end_call_api,
    get_agent_workload_api,
    get_call_api,
    get_call_center_stats_api,
    list_calls_api,
    mark_missed_api,
    place_outbound_call_api,
    reassign_call_api,
    route_incoming_call_api,
    send_to_voicemail_api,
)


router = APIRouter()


class RouteIncomingCallRequest(BaseModel):

    department: str
    from_number: str
    to_number: str | None = None
    linked_entity_id: str | None = None


class PlaceOutboundCallRequest(BaseModel):

    department: str
    to_number: str
    from_number: str | None = None
    linked_entity_id: str | None = None


class ReassignCallRequest(BaseModel):

    employee_id: str


class EndCallRequest(BaseModel):

    notes: str | None = None
    duration_seconds: int | None = None


@router.post("/call-center/route-incoming")
def call_center_route_incoming_route(request: RouteIncomingCallRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return route_incoming_call_api(
        payload["role"],
        department=request.department,
        from_number=request.from_number,
        to_number=request.to_number,
        linked_entity_id=request.linked_entity_id,
        created_by=payload["employee_id"],
    )


@router.post("/call-center/place-outbound")
def call_center_place_outbound_route(request: PlaceOutboundCallRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return place_outbound_call_api(
        payload["role"],
        payload["employee_id"],
        department=request.department,
        to_number=request.to_number,
        from_number=request.from_number,
        linked_entity_id=request.linked_entity_id,
    )


@router.get("/call-center/agent-workload")
def call_center_agent_workload_route(department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_agent_workload_api(payload["role"], department=department)


@router.get("/call-center/stats")
def call_center_stats_route(department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_call_center_stats_api(payload["role"], department=department)


@router.get("/call-center/list")
def call_center_list_route(
    department: str = None,
    status: str = None,
    assigned_to: str = None,
    linked_entity_id: str = None,
    limit: int = 200,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_calls_api(
        payload["role"],
        department=department,
        status=status,
        assigned_to=assigned_to,
        linked_entity_id=linked_entity_id,
        limit=limit,
    )


@router.get("/call-center/{call_id}")
def call_center_get_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_call_api(payload["role"], call_id)


@router.post("/call-center/{call_id}/reassign")
def call_center_reassign_route(call_id: str, request: ReassignCallRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reassign_call_api(payload["role"], call_id, request.employee_id, payload["employee_id"])


@router.post("/call-center/{call_id}/connect")
def call_center_connect_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return connect_call_api(payload["role"], call_id)


@router.post("/call-center/{call_id}/end")
def call_center_end_route(call_id: str, request: EndCallRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return end_call_api(
        payload["role"],
        call_id,
        payload["employee_id"],
        notes=request.notes,
        duration_seconds=request.duration_seconds,
    )


@router.post("/call-center/{call_id}/mark-missed")
def call_center_mark_missed_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_missed_api(payload["role"], call_id)


@router.post("/call-center/{call_id}/send-to-voicemail")
def call_center_send_to_voicemail_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_to_voicemail_api(payload["role"], call_id)
