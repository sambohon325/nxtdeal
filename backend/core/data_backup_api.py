"""
Thin ACL layer for core/data_backup.py -- ADMIN/OPERATIONS-only for every
action, matching this whole department's established convention. Restoring a
backup is the single most consequential real action in this entire
Administration rebuild (it overwrites the live graph.json and reloads it
in-process) -- deliberately kept ADMIN-only, narrower than this module's other
OPERATIONS-inclusive actions.
"""

from core.data_backup import (
    export_entity_type_csv,
    list_exportable_entity_types,
    create_backup,
    list_backups,
    restore_backup,
)
from core.permissions import ADMIN, OPERATIONS

_ROLES = (ADMIN, OPERATIONS)
_FORBIDDEN = {"error": "Admin/Operations role required."}
_ADMIN_ONLY = {"error": "Only ADMIN can restore a backup."}


def list_exportable_entity_types_api(role):
    if role not in _ROLES:
        return _FORBIDDEN
    return {"entity_types": list_exportable_entity_types()}


def export_entity_type_csv_api(role, entity_type):
    if role not in _ROLES:
        return None, _FORBIDDEN
    return export_entity_type_csv(entity_type)


def create_backup_api(role, employee_id, label=""):
    if role not in _ROLES:
        return _FORBIDDEN
    return create_backup(employee_id, label=label)


def list_backups_api(role):
    if role not in _ROLES:
        return _FORBIDDEN
    return {"backups": list_backups()}


def restore_backup_api(role, employee_id, backup_id):
    if role != ADMIN:
        return _ADMIN_ONLY
    return restore_backup(backup_id, employee_id)
