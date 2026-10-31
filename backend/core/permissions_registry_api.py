"""
Thin ACL layer for core/permissions_registry.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: managing the catalog/overrides (granting or revoking a permission
beyond someone's role default) is the sensitive, control-plane half of this
module -- ADMIN-only for granting/revoking, ADMIN/OPERATIONS for viewing the
full matrix/all overrides, matching core/administration_menu.py's own
established `_ADMIN_ONLY_ERROR` convention for this whole department.

Approval requests are deliberately NOT gated to Administration's own
ADMIN/OPERATIONS-only default -- any authenticated employee can request or
review one (any role legitimately might need manager/executive sign-off on
something), and the real teeth are the tier check inside
core/permissions_registry.py's approve_step() itself (an employee's own
Employee.Title, via core/bot_tasks.py's infer_tier()), not a coarse role gate
at this layer.
"""

from core.permissions_registry import (
    list_permission_catalog,
    get_effective_permissions,
    has_permission,
    list_overrides_for_employee,
    list_all_overrides,
    set_override,
    revoke_override,
    list_approval_chains,
    create_approval_request,
    approve_step,
    reject_step,
    cancel_request,
    get_approval_request,
    list_approval_requests,
    get_tier_distribution,
)
from core.auth import credential_store
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}
_FORBIDDEN = {"error": "You don't have access to this action."}


# --- Permission catalog / overrides ---

def list_permission_catalog_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    from core.administration_access import system_admin_context
    result = list_permission_catalog()
    if not system_admin_context.get() and "categories" in result:
        result["categories"] = [{**category, "permissions": [entry for entry in category["permissions"] if entry["key"] != "admin.view_audit"]} for category in result["categories"]]
    return result


def get_effective_permissions_api(role, employee_id, target_employee_id=None):
    """Any employee can see their own effective permissions; seeing someone
    else's requires ADMIN/OPERATIONS."""

    target = target_employee_id or employee_id
    if target != employee_id and role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    # The viewer's role authorizes inspection; defaults belong to the target.
    target_role = role if target == employee_id else (credential_store.get_record(target) or {}).get("role")
    return {"employee_id": target, "permissions": get_effective_permissions(target_role, target)}


def list_overrides_for_employee_api(role, employee_id, target_employee_id=None):
    target = target_employee_id or employee_id
    if target != employee_id and role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"employee_id": target, "overrides": list_overrides_for_employee(target)}


def list_all_overrides_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"overrides": list_all_overrides()}


def set_override_api(role, granted_by, target_employee_id, permission_key, granted, reason=""):
    if role != ADMIN:
        return {"error": "Only ADMIN can grant or revoke a permission override."}
    from core.administration_access import system_admin_context, reserved_system_admin
    if not system_admin_context.get() and (permission_key == "admin.view_audit" or reserved_system_admin(target_employee_id)):
        return {"error": "NXTDeal system permissions cannot be granted by dealership administrators"}
    return set_override(target_employee_id, permission_key, granted, granted_by, reason)


def revoke_override_api(role, actor_employee_id, override_id):
    if role != ADMIN:
        return {"error": "Only ADMIN can grant or revoke a permission override."}
    from core.administration_access import system_admin_context, reserved_system_admin
    existing = next((item for item in list_all_overrides() if item["id"] == override_id), None)
    if existing and reserved_system_admin(existing.get("employee_id")) and not system_admin_context.get():
        return {"error": "Only NXTDeal system administrators can manage this account"}
    return revoke_override(override_id, actor_employee_id)


# --- Approval hierarchy ---

def list_approval_chains_api(role):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return {"chains": list_approval_chains()}


def create_approval_request_api(role, employee_id, chain_key, subject, details="", entity_id=None):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return create_approval_request(chain_key, employee_id, subject, details=details, entity_id=entity_id)


def approve_step_api(role, employee_id, request_id, note=""):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return approve_step(request_id, employee_id, note=note)


def reject_step_api(role, employee_id, request_id, reason):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return reject_step(request_id, employee_id, reason)


def cancel_request_api(role, employee_id, request_id):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return cancel_request(request_id, employee_id)


def get_approval_request_api(role, request_id):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return get_approval_request(request_id)


def list_approval_requests_api(role, employee_id, status=None, mine_only=False, pending_for_me=False):
    if role not in _ALL_ROLES:
        return _FORBIDDEN

    if role in _ADMIN_ROLES and not mine_only and not pending_for_me:
        return {"requests": list_approval_requests(status=status)}

    requested_by = employee_id if mine_only else None
    pending_for = employee_id if pending_for_me else None
    return {"requests": list_approval_requests(status=status, requested_by=requested_by, pending_for_employee=pending_for)}


# --- Tier distribution ---

def get_tier_distribution_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_tier_distribution()
