"""
Thin ACL layer for core/ai_management.py -- imported directly into api/app.py's
route handlers, same "no service layer indirection" convention every other
`*_api.py` module in this codebase follows.

Role rule: ADMIN/OPERATIONS-only, matching core/administration_menu.py's own
established `_ADMIN_ONLY_ERROR` convention for this whole department -- toggling
whether a platform-wide AI feature runs at all is exactly the kind of "runs the
platform" control this Control Center rebuild reserves for Administration.
"""

from core.ai_management import (
    AI_FEATURE_CATALOG,
    get_ai_management_overview,
    get_call_stats,
    set_feature_enabled,
)
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_ai_management_overview_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_ai_management_overview(role)


def get_ai_feature_catalog_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"features": AI_FEATURE_CATALOG}


def get_ai_call_stats_api(role, feature_key=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"stats": get_call_stats(feature_key=feature_key)}


def set_ai_feature_enabled_api(role, employee_id, feature_key, enabled):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_feature_enabled(feature_key, enabled, employee_id)
