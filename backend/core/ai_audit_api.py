"""
Thin ACL layer for core/ai_audit.py -- imported directly into api/app.py's
route handlers, same "no service layer indirection" convention every other
`*_api.py` module in this codebase follows.

Role rule: ADMIN/OPERATIONS-only, matching core/ai_management_api.py's own
established gate for this whole Administration Control Center "AI
Management" surface -- a durable, per-call log of what the AI did and on
whose behalf is exactly the kind of platform-oversight data this rebuild
reserves for Administration, same reasoning as the kill-switch toggle
itself.
"""

from core.ai_audit import get_ai_audit_dashboard, list_ai_actions, flush_ai_audit_log
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_ai_audit_dashboard_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_ai_audit_dashboard()


def list_ai_actions_api(role, feature_key=None, actor=None, outcome=None, limit=100):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"actions": list_ai_actions(feature_key=feature_key, actor=actor, outcome=outcome, limit=limit)}


def flush_ai_audit_log_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return flush_ai_audit_log()
