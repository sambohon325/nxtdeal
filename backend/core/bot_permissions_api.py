"""
core/bot_permissions_api.py -- security-hardening pass (2026-07-20), Task #7.
Thin ACL wrapper over core/bot_permissions.py's real default-deny engine,
matching core/permissions_registry_api.py's own established style exactly:
viewing the catalog/effective-capability set is broad (ADMIN/OPERATIONS,
plus a self-view carve-out for an employee looking at their own effective
capabilities -- informational, no HR-risk content, same reasoning
core/permissions_registry_api.py's own self-view carve-out already uses);
granting/revoking a capability is ADMIN-only, matching
core/ai_kill_switch_api.py's own stricter mutate gate for this same class
of "can this bot do something unattended" decision.
"""

from core.permissions import ADMIN, OPERATIONS
from core import bot_permissions

_VIEW_ROLES = (ADMIN, OPERATIONS)
_VIEW_ONLY_ERROR = {"error": "Admin/Operations role required."}
_ADMIN_ONLY_ERROR = {"error": "Admin role required."}


def list_bot_capability_catalog_api(role):
    if role not in _VIEW_ROLES:
        return _VIEW_ONLY_ERROR
    return {"catalog": bot_permissions.list_capability_catalog()}


def get_effective_bot_capabilities_api(role, requesting_employee_id, target_employee_id=None, department=None):
    """A caller may always see their OWN effective capabilities (self-view
    carve-out, matching core/permissions_registry_api.py's own precedent);
    seeing someone ELSE's requires ADMIN/OPERATIONS."""

    effective_target = target_employee_id or requesting_employee_id

    if effective_target != requesting_employee_id and role not in _VIEW_ROLES:
        return _VIEW_ONLY_ERROR

    return {
        "employee_id": effective_target,
        "department": department,
        "capabilities": bot_permissions.get_effective_capabilities(
            effective_target, department=department
        ),
    }


def list_bot_capability_grants_api(role, scope, scope_target=None):
    if role not in _VIEW_ROLES:
        return _VIEW_ONLY_ERROR
    if scope not in bot_permissions.VALID_SCOPES:
        return {"error": f"Unknown scope '{scope}' -- must be one of {bot_permissions.VALID_SCOPES}"}
    return {"grants": bot_permissions.list_grants_for_scope(scope, scope_target)}


def list_all_bot_capability_grants_api(role):
    if role not in _VIEW_ROLES:
        return _VIEW_ONLY_ERROR
    return {"grants": bot_permissions.list_all_grants()}


def set_bot_capability_grant_api(role, employee_id, capability_key, scope, granted, scope_target=None, reason=""):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return bot_permissions.grant_capability(
        capability_key=capability_key,
        scope=scope,
        granted=granted,
        granted_by=employee_id,
        scope_target=scope_target,
        reason=reason,
    )


def revoke_bot_capability_grant_api(role, employee_id, grant_id):
    if role != ADMIN:
        return _ADMIN_ONLY_ERROR
    return bot_permissions.revoke_grant(grant_id, employee_id)
