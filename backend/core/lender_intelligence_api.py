"""
ACL layer for core/lender_intelligence.py. Viewing is broad -- ADMIN/OPERATIONS/
SALES/FINANCE, matching core/deals_api.py's own `_BOARD_VIEW_ROLES` precedent
exactly, since this is the same "everyone on the deal desk board legitimately
wants to see it" reasoning that already covers Deal Desk viewing itself: a
salesperson wants to know which lender to submit to just as much as F&I does.
There is no mutation in this module at all -- submitting a deal to a lender and
recording that lender's decision both stay entirely inside Deal Desk's own
existing submit_to_lender_api()/record_lender_decision_api() flow; Lender
Intelligence only ever reads what that flow already recorded.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE

from core.lender_intelligence import (
    get_lender_scorecards,
    get_submission_log,
    get_lender_recommendation,
    get_dashboard_overview,
)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)


def get_dashboard_overview_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lender Intelligence"}

    return get_dashboard_overview()


def get_lender_scorecards_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lender Intelligence"}

    return {"scorecards": get_lender_scorecards()}


def get_submission_log_api(role, lender_id=None, limit=200):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lender Intelligence"}

    return {"submissions": get_submission_log(lender_id=lender_id, limit=limit)}


def get_lender_recommendation_api(role, deal_id=None):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lender Intelligence"}

    return get_lender_recommendation(deal_id=deal_id)
