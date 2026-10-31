"""Lender Intelligence router -- real per-lender scorecards (approval rate/
avg offered APR/avg turnaround) + a real submission log + a real, transparent
rules-based lender recommendation, computed off the real, append-only
lender_submission_history list core/deals.py's submit_to_lender()/
record_lender_decision() write to (Finance's "Lender Intelligence" Top Menu
item).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.

core/lender_intelligence_api.py's own module docstring covers the ACL
reasoning: viewing matches core/deals_api.py's own _BOARD_VIEW_ROLES exactly
(ADMIN/OPERATIONS/SALES/FINANCE) -- no mutation lives in this module at all,
submitting/deciding stays entirely inside Deal Desk's own existing routes.
Static /lender-intelligence/* paths only -- no dynamic {id}-shaped path here
to worry about shadowing.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.lender_intelligence_api import (
    get_dashboard_overview_api as get_lender_intelligence_overview_api,
    get_lender_scorecards_api,
    get_submission_log_api,
    get_lender_recommendation_api,
)


router = APIRouter()


@router.get("/lender-intelligence/overview")
def lender_intelligence_overview(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lender_intelligence_overview_api(payload["role"])


@router.get("/lender-intelligence/scorecards")
def lender_intelligence_scorecards(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lender_scorecards_api(payload["role"])


@router.get("/lender-intelligence/submissions")
def lender_intelligence_submissions(lender_id: str = None, limit: int = 200, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_submission_log_api(payload["role"], lender_id=lender_id, limit=limit)


@router.get("/lender-intelligence/recommendation")
def lender_intelligence_recommendation(deal_id: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lender_recommendation_api(payload["role"], deal_id=deal_id)
