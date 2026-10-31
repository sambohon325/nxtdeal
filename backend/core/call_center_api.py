"""Thin ACL layer for core/call_center.py's first-class Call entity (Phase 2:
Communications Platform, Voice -- 2026-07-22). Same "no service layer indirection"
convention as every other *_api.py module in this codebase, and mirrors
core/communications_hub_api.py's own exact ACL shape one level down.

Viewing (get/list/agent-workload/stats) and every mutating action (routing an
inbound call, placing an outbound call, reassigning, connecting, ending, marking
missed, sending to voicemail) all use the same broad VIEW_ROLES tuple
core/communications_hub_api.py/core/unified_communications_api.py already
established for this exact cross-department Communications surface -- a phone
call is the same class of everyday staff action logging a Communication already
is, just with a richer routing/lifecycle shape. No narrower role tier is carved
out here: Sales/Service/Finance/Marketing/Operations/Admin can all place, route,
and manage calls, matching how broadly this codebase already gates its other
real-time, staff-facing communication surfaces (chat sessions, field notes)."""

from core.call_center import (
    CALL_STATUSES,
    DEPARTMENTS,
    DIRECTIONS,
    connect_call,
    end_call,
    get_agent_workload,
    get_call,
    get_call_center_stats,
    list_calls,
    mark_missed,
    place_outbound_call,
    reassign_call,
    route_incoming_call,
    send_to_voicemail,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def route_incoming_call_api(role, department, from_number, to_number=None,
                              linked_entity_id=None, created_by="inbound_call_router"):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to route an incoming call."}

    call, error = route_incoming_call(
        department=department,
        from_number=from_number,
        to_number=to_number,
        linked_entity_id=linked_entity_id,
        created_by=created_by,
    )

    if error:
        return {"error": error}

    return call


def place_outbound_call_api(role, employee_id, department, to_number,
                              from_number=None, linked_entity_id=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to place an outbound call."}

    call, error = place_outbound_call(
        department=department,
        to_number=to_number,
        created_by=employee_id,
        from_number=from_number,
        linked_entity_id=linked_entity_id,
    )

    if error:
        return {"error": error}

    return call


def reassign_call_api(role, call_id, employee_id, reassigned_by):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to reassign a call."}

    call, error = reassign_call(call_id, employee_id, reassigned_by)
    if error:
        return {"error": error}

    return call


def connect_call_api(role, call_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to connect a call."}

    call, error = connect_call(call_id)
    if error:
        return {"error": error}

    return call


def end_call_api(role, call_id, ended_by, notes=None, duration_seconds=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to end a call."}

    call, error = end_call(call_id, ended_by, notes=notes, duration_seconds=duration_seconds)
    if error:
        return {"error": error}

    return call


def mark_missed_api(role, call_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to mark a call as missed."}

    call, error = mark_missed(call_id)
    if error:
        return {"error": error}

    return call


def send_to_voicemail_api(role, call_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to send a call to voicemail."}

    call, error = send_to_voicemail(call_id)
    if error:
        return {"error": error}

    return call


def get_call_api(role, call_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view this call."}

    call = get_call(call_id)
    if not call:
        return {"error": f"Call '{call_id}' not found."}

    return call


def list_calls_api(role, department=None, status=None, assigned_to=None,
                    linked_entity_id=None, limit=200):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view calls."}

    return list_calls(
        department=department,
        status=status,
        assigned_to=assigned_to,
        linked_entity_id=linked_entity_id,
        limit=limit,
    )


def get_agent_workload_api(role, department=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view agent workload."}

    return get_agent_workload(department=department)


def get_call_center_stats_api(role, department=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view Call Center stats."}

    return get_call_center_stats(department=department)
