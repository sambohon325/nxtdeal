"""
Thin ACL layer for core/api_keys.py. Employees may issue their own keys;
only ADMIN may issue another employee's credential. ADMIN/OPERATIONS may
inspect and revoke keys without acquiring the owner's authentication authority.
"""

from core.api_keys import (
    generate_api_key,
    revoke_api_key,
    list_api_keys_for_employee,
    list_all_api_keys,
)
from core.dealeros import ledger
from core.entity_types import API_KEY
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def generate_api_key_api(role, employee_id, target_employee_id=None, label=""):
    target = target_employee_id or employee_id
    # Issuance returns a bearer credential carrying the TARGET's role. Giving
    # Operations this administrative convenience lets it impersonate an Admin.
    if target != employee_id and role != ADMIN:
        return {"error": "Admin role required to create another employee's API key."}
    return generate_api_key(target, label, employee_id)


def revoke_api_key_api(role, employee_id, key_id):
    entity = ledger.get_entity(key_id)
    if not entity or entity.entity_type != API_KEY:
        return {"error": f"API key '{key_id}' not found"}

    if entity.attributes.get("employee_id") != employee_id and role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR

    return revoke_api_key(key_id, employee_id)


def list_api_keys_for_employee_api(role, employee_id, target_employee_id=None):
    target = target_employee_id or employee_id
    if target != employee_id and role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"employee_id": target, "keys": list_api_keys_for_employee(target)}


def list_all_api_keys_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"keys": list_all_api_keys()}
