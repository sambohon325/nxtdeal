"""AI Audit router -- security-hardening pass (2026-07-20), Task #5 "Build
comprehensive AI action audit trail." Real, durable, per-call AiActionLog
records on top of core/ai_management.py's own in-memory-only call-attempt
counters -- see core/ai_audit.py's own module docstring for the full design
(why this is added to the ledger on every call but not saved to disk on
every call, and the honest scope note on which features have a real `actor`
threaded through as of this pass).

Follows api/routers/ai_management.py's own established pattern exactly:
a self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py. ADMIN/
OPERATIONS-only throughout, matching that same domain's gate.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.ai_audit_api import (
    get_ai_audit_dashboard_api,
    list_ai_actions_api,
    flush_ai_audit_log_api,
)


router = APIRouter()


@router.get("/ai-audit/dashboard")
def ai_audit_dashboard_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ai_audit_dashboard_api(payload["role"])


@router.get("/ai-audit/actions")
def ai_audit_actions_route(
    feature_key: str = None,
    actor: str = None,
    outcome: str = None,
    limit: int = 100,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_ai_actions_api(
        payload["role"], feature_key=feature_key, actor=actor, outcome=outcome, limit=limit
    )


@router.post("/ai-audit/flush")
def ai_audit_flush_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return flush_ai_audit_log_api(payload["role"])
