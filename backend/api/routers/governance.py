"""Governance router -- Administration Control Center's "Compliance &
Governance" (enriched) Top Menu item.

core/governance.py composes core/compliance.py's cited-rules alert engine
and core/permissions_registry.py's tier-gated cross-department
ApprovalRequest hierarchy into one real governance workspace, plus a
governance-scoped slice of the audit log (core/audit_center.py's own
EVENT_CATEGORIES, Permissions/Approvals/Compliance buckets only). The
existing GET /menu/data?department=Administration&item_key=governance
route already serves core/administration_menu.py's governance(), which
now embeds this same data -- these dedicated routes exist for the bespoke
board's own drill-down views (a filtered action log, a standalone health
figure), same "bespoke board bypasses /menu/data for its own extra views"
precedent as /audit-center/*.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. All 5 paths are static (no dynamic path in this
block).

ADMIN/OPERATIONS-only throughout.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.governance_api import (
    get_governance_overview_api,
    get_compliance_governance_summary_api,
    get_approval_hierarchy_summary_api,
    get_governance_health_api,
    get_governance_action_log_api,
)


router = APIRouter()


@router.get("/governance/overview")
def governance_overview_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_governance_overview_api(payload["role"])


@router.get("/governance/compliance-summary")
def governance_compliance_summary_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_compliance_governance_summary_api(payload["role"])


@router.get("/governance/approval-hierarchy")
def governance_approval_hierarchy_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_approval_hierarchy_summary_api(payload["role"])


@router.get("/governance/health")
def governance_health_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_governance_health_api(payload["role"])


@router.get("/governance/action-log")
def governance_action_log_route(category: str = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_governance_action_log_api(payload["role"], category=category, limit=limit)
