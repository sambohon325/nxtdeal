"""
Thin ACL layer for core/workflow_automation.py -- imported directly into
api/app.py's route handlers, same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows.

Role rule: ADMIN/OPERATIONS-only across every function here, matching
core/administration_menu.py's own established `_ADMIN_ONLY_ERROR` convention
for this whole department -- a platform-wide rule that auto-creates tasks
or sends DMs unattended is exactly the kind of "runs the platform" action
this Control Center rebuild's own admin.pdf framing reserves for
Administration, not a broader per-department action.
"""

from core.workflow_automation import (
    create_rule,
    list_rules,
    get_rule,
    set_rule_active,
    update_rule,
    delete_rule,
    list_executions,
    evaluate_rules,
    get_automation_dashboard,
    TRIGGER_CATALOG,
    ACTION_CATALOG,
)
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def _serialize(entity):
    if isinstance(entity, dict):
        return entity
    return {"id": entity.id, **entity.attributes}


def get_automation_dashboard_api(role, run_now=True):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_automation_dashboard(run_now=run_now)


def get_automation_catalog_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"triggers": TRIGGER_CATALOG, "actions": ACTION_CATALOG}


def list_rules_api(role, active_only=False):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"rules": [_serialize(r) for r in list_rules(active_only=active_only)]}


def create_rule_api(role, employee_id, name, trigger_type, trigger_params, action_type, action_params, description=""):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    result = create_rule(
        name=name,
        trigger_type=trigger_type,
        trigger_params=trigger_params,
        action_type=action_type,
        action_params=action_params,
        created_by=employee_id,
        description=description,
    )
    return _serialize(result)


def get_rule_api(role, rule_id):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    rule = get_rule(rule_id)
    if not rule:
        return {"error": "Rule not found"}
    return _serialize(rule)


def set_rule_active_api(role, employee_id, rule_id, is_active):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return _serialize(set_rule_active(rule_id, is_active, employee_id))


def update_rule_api(role, employee_id, rule_id, name=None, description=None, trigger_params=None, action_params=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return _serialize(update_rule(
        rule_id, employee_id, name=name, description=description,
        trigger_params=trigger_params, action_params=action_params,
    ))


def delete_rule_api(role, rule_id):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return delete_rule(rule_id)


def list_executions_api(role, rule_id=None, limit=100):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"executions": [_serialize(e) for e in list_executions(rule_id=rule_id, limit=limit)]}


def run_rules_now_api(role, rule_id=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return evaluate_rules(rule_id=rule_id)
