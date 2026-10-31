"""
Thin ACL layer for core/ai_kill_switch.py -- security-hardening pass
(2026-07-20, Task #6). ADMIN/OPERATIONS-only throughout, matching
core/ai_management_api.py's own established gate for this whole AI
Management surface -- flipping an emergency kill switch is at least as
sensitive an action as toggling one individual feature flag.
"""

from core.permissions import ADMIN, OPERATIONS

from core.ai_kill_switch import (
    get_kill_switch_overview,
    set_dealer_wide_kill_switch,
    set_department_kill_switch,
    set_bot_kill_switch,
    set_workflow_automation_kill_switch,
    explain_ai_gate,
)

_ADMIN_ROLES = (ADMIN, OPERATIONS)
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_kill_switch_overview_api(role):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return get_kill_switch_overview()


def explain_ai_gate_api(role, feature_key):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return {"feature_key": feature_key, "gate": explain_ai_gate(feature_key)}


def set_dealer_wide_kill_switch_api(role, active, updated_by, reason=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_dealer_wide_kill_switch(active, updated_by, reason=reason)


def set_department_kill_switch_api(role, department, active, updated_by, reason=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_department_kill_switch(department, active, updated_by, reason=reason)


def set_bot_kill_switch_api(role, active, updated_by, reason=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_bot_kill_switch(active, updated_by, reason=reason)


def set_workflow_automation_kill_switch_api(role, active, updated_by, reason=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_workflow_automation_kill_switch(active, updated_by, reason=reason)
