"""
Thin ACL layer for core/governance.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: ADMIN/OPERATIONS-only across every function here, matching
core/administration_menu.py's own established `_ADMIN_ONLY_ERROR` convention
for this whole department (security()/systems()/governance() all use the
same gate) -- the compliance-alert detail, approval-request detail, and
cross-department action log this module surfaces all carry the kind of
sensitivity that shouldn't be broadly readable, same reasoning
core/audit_center_api.py already applied to its own overlapping event data.
"""

from core.governance import (
    get_compliance_governance_summary,
    get_approval_hierarchy_summary,
    get_governance_action_log,
    get_governance_health,
    get_governance_overview,
    GOVERNANCE_CATEGORIES,
)
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_governance_overview_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_governance_overview()


def get_compliance_governance_summary_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_compliance_governance_summary()


def get_approval_hierarchy_summary_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_approval_hierarchy_summary()


def get_governance_health_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_governance_health()


def get_governance_action_log_api(role, category=None, limit=100):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    if category and category not in GOVERNANCE_CATEGORIES:
        return {"error": f"Unknown governance category '{category}'. Valid: {list(GOVERNANCE_CATEGORIES)}"}
    return get_governance_action_log(category=category, limit=limit)
