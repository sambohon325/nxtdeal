"""
ACL layer for core/lead_scoring.py -- imported directly into api/app.py's route
handlers, same "no service layer indirection" convention every other `*_api.py`
module in this codebase follows.

Role rule: matches core/permissions.py's own LEAD access set -- ADMIN/OPERATIONS/
SALES/MARKETING -- lead scoring is a Sales-and-Marketing-shared prioritization
signal, no broader than viewing a Lead itself already is.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING
from core.lead_scoring import compute_score, leaderboard


_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)

_FORBIDDEN = {"error": "You don't have access to Lead Scoring with your current role."}


def compute_score_api(role, entity_id):
    if role not in _ROLES:
        return _FORBIDDEN
    return compute_score(entity_id)


def leaderboard_api(role, limit=50):
    if role not in _ROLES:
        return _FORBIDDEN
    return leaderboard(limit)
