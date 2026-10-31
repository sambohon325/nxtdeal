"""
Thin ACL layer for core/bdc.py. Role gate is ADMIN/OPERATIONS/SALES plus the dedicated
BDC role (2026-07-25 Bumper parity). BDC reps historically carried the SALES role and
still can, but a dealer can now staff a dedicated BDC role that sees this queue without
the rest of the sales desk.
"""

from core.bdc import (
    get_bdc_dashboard,
    get_untouched_queue,
    get_response_time_stats,
    get_qualification_queue,
    get_handoff_candidates,
)
from core.permissions import ADMIN, OPERATIONS, SALES, BDC

_BDC_ROLES = (ADMIN, OPERATIONS, SALES, BDC)


def get_bdc_dashboard_api(role):

    if role not in _BDC_ROLES:
        return {"error": "You don't have access to the BDC queue"}

    return get_bdc_dashboard()


def get_untouched_queue_api(role):

    if role not in _BDC_ROLES:
        return {"error": "You don't have access to the BDC queue"}

    queue = get_untouched_queue()

    return {"count": len(queue), "leads": queue}


def get_qualification_queue_api(role):

    if role not in _BDC_ROLES:
        return {"error": "You don't have access to the BDC queue"}

    queue = get_qualification_queue()

    return {"count": len(queue), "leads": queue}


def get_handoff_candidates_api(role):

    if role not in _BDC_ROLES:
        return {"error": "You don't have access to the BDC queue"}

    candidates = get_handoff_candidates()

    return {"count": len(candidates), "leads": candidates}
