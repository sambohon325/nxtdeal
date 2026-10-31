"""Audit Center router -- Administration Control Center's final slice: a real
investigative workspace over the audit log every ~20+ modules across this
codebase already write to (core/audit.py's `audit_log` singleton), distinct
from the thin slices "Security"/"Systems"/"Governance" already surface: real
filtering/search, a real per-actor activity summary, and a real, transparent
RULES-based suspicious-activity flag list (no ML/LLM anomaly detection).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static paths registered before the one dynamic
/audit-center/actors/{actor} path, matching the original file's own
route-shadowing-avoidance ordering.

ADMIN/OPERATIONS-only throughout, matching this whole department's
established gate.
"""

from fastapi import APIRouter, Header
from fastapi.responses import PlainTextResponse

from api.deps import _authenticate

from core.audit_center_api import (
    get_audit_center_overview_api,
    get_event_catalog_api,
    search_audit_log_api,
    get_actor_activity_api,
    get_actor_timeline_api,
    get_suspicious_activity_api,
    export_audit_events_csv_api,
)


router = APIRouter()


@router.get("/audit-center/overview")
def audit_center_overview(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_audit_center_overview_api(payload["role"])


@router.get("/audit-center/event-catalog")
def audit_center_event_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_event_catalog_api(payload["role"])


@router.get("/audit-center/search")
def audit_center_search(
    entity_id: str = None,
    actor: str = None,
    event_type: str = None,
    category: str = None,
    date_from: str = None,
    date_to: str = None,
    query: str = None,
    limit: int = 200,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return search_audit_log_api(
        payload["role"],
        entity_id=entity_id,
        actor=actor,
        event_type=event_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        query=query,
        limit=limit,
    )


@router.get("/audit-center/export")
def audit_center_export(
    entity_id: str = None,
    actor: str = None,
    event_type: str = None,
    category: str = None,
    date_from: str = None,
    date_to: str = None,
    query: str = None,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    filename, content = export_audit_events_csv_api(
        payload["role"],
        entity_id=entity_id,
        actor=actor,
        event_type=event_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        query=query,
    )

    if filename is None:
        return content

    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit-center/actor-activity")
def audit_center_actor_activity(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_actor_activity_api(payload["role"], limit=limit)


@router.get("/audit-center/suspicious-activity")
def audit_center_suspicious_activity(off_hours_lookback_days: int = 7, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_suspicious_activity_api(payload["role"], off_hours_lookback_days=off_hours_lookback_days)


@router.get("/audit-center/actors/{actor}")
def audit_center_actor_timeline(actor: str, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_actor_timeline_api(payload["role"], actor, limit=limit)
