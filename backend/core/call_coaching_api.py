"""Thin ACL layer for core/call_coaching.py's rules-based Coaching Score engine
(Phase 2: Communications Platform, AI Voice + BDC Center -- 2026-07-22). Same
"no service layer indirection" convention as every other *_api.py module in this
codebase, and mirrors core/call_center_api.py's own exact ACL shape one level up.

Viewing (scorable/scored queues, stats, a single call's coaching data) and the
one mutating action (scoring a call) all use the same broad VIEW_ROLES tuple
core/call_center_api.py/core/communications_hub_api.py already established for
this exact cross-department Communications surface -- reviewing/scoring a call
is the same class of everyday staff/coach action as logging a Communication or
managing a Call already is. No narrower role tier is carved out here."""

from core.call_coaching import (
    get_call_coaching,
    get_coaching_stats,
    list_scorable_calls,
    list_scored_calls,
    score_call,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING", "SERVICE", "FINANCE")


def score_call_api(role, call_id, scored_by):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to score a call."}

    call, error = score_call(call_id, scored_by)
    if error:
        return {"error": error}

    return call


def get_call_coaching_api(role, call_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view call coaching data."}

    result, error = get_call_coaching(call_id)
    if error:
        return {"error": error}

    return result


def list_scorable_calls_api(role, department=None, limit=100):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the scorable-calls queue."}

    return list_scorable_calls(department=department, limit=limit)


def list_scored_calls_api(role, department=None, assigned_to=None, limit=100):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view scored calls."}

    return list_scored_calls(department=department, assigned_to=assigned_to, limit=limit)


def get_coaching_stats_api(role, department=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view coaching stats."}

    return get_coaching_stats(department=department)
