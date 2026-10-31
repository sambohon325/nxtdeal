"""Call Coaching router -- core/call_coaching.py's rules-based Coaching Score
engine (Phase 2: Communications Platform, AI Voice + BDC Center -- 2026-07-22).
Sam named this feature twice (AI Voice: "Coaching ... Sentiment"; BDC Center:
"Coaching * Call Scoring * QA") -- both served by this one router, since it's
the same real signal viewed from two audiences. See core/call_coaching.py's
own docstring for the full rubric/scope reasoning.

Follows api/routers/call_center.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py. Static paths
(scorable/scored/stats) are registered before the dynamic /{call_id} paths,
same ordering discipline call_center.py's own router already follows.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.call_coaching_api import (
    get_call_coaching_api,
    get_coaching_stats_api,
    list_scorable_calls_api,
    list_scored_calls_api,
    score_call_api,
)


router = APIRouter()


@router.get("/call-coaching/scorable")
def call_coaching_scorable_route(department: str = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_scorable_calls_api(payload["role"], department=department, limit=limit)


@router.get("/call-coaching/scored")
def call_coaching_scored_route(
    department: str = None,
    assigned_to: str = None,
    limit: int = 100,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_scored_calls_api(
        payload["role"], department=department, assigned_to=assigned_to, limit=limit
    )


@router.get("/call-coaching/stats")
def call_coaching_stats_route(department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_coaching_stats_api(payload["role"], department=department)


@router.get("/call-coaching/{call_id}")
def call_coaching_get_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_call_coaching_api(payload["role"], call_id)


@router.post("/call-coaching/{call_id}/score")
def call_coaching_score_route(call_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return score_call_api(payload["role"], call_id, payload["employee_id"])
