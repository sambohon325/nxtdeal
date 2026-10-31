"""
Thin API-layer functions for Orphan Owner Mining (session 105 follow-up), imported
directly into api/app.py's route handlers -- same convention as every other
`*_api.py` module in this codebase.

Role rule: claiming an orphan owner (creating a real Lead and taking the
relationship) is ADMIN/OPERATIONS/SALES -- the same "desking-adjacent" role set
core/deals_api.py/credit_app_api.py/lost_sale_recovery_api.py already grant.
MARKETING is also allowed to view the queue and stats (but not claim) -- an unmined
pool of real owned vehicles with no salesperson attribution is exactly the kind of
audience Marketing's CRM already builds win-back campaigns against.
"""

from core.orphan_owner_mining import (
    get_orphan_owners,
    get_orphan_owner_detail,
    claim_orphan_owner,
    get_orphan_owner_stats,
)
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING


_ACTION_ROLES = (ADMIN, OPERATIONS, SALES)
_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)


def get_orphan_owners_api(role, limit=50, include_claimed=False):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Orphan Owner Mining"}

    return get_orphan_owners(limit=limit, include_claimed=include_claimed)


def get_orphan_owner_detail_api(role, customer_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Orphan Owner Mining"}

    return get_orphan_owner_detail(customer_id)


def claim_orphan_owner_api(role, employee_id, customer_id, note=None):

    if role not in _ACTION_ROLES:
        return {"error": "Only Sales/Operations/Admin can claim an orphan owner"}

    return claim_orphan_owner(customer_id, employee_id, note=note)


def get_orphan_owner_stats_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Orphan Owner Mining reporting"}

    return get_orphan_owner_stats()


def get_orphan_owner_dashboard_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to the Orphan Owner Mining dashboard"}

    return {
        "queue": get_orphan_owners(limit=25),
        "stats": get_orphan_owner_stats(),
    }
