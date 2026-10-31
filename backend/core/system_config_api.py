"""
Thin ACL layer for core/system_config.py -- viewing is open to any authenticated
role (every department benefits from knowing the dealership's own business
hours/timezone), editing is ADMIN/OPERATIONS-only, matching this whole
department's established convention.
"""

from core.system_config import (
    get_system_config,
    update_organization_profile,
    add_location,
    remove_location,
    update_business_hours,
    update_defaults,
    set_feature_flag,
    FEATURE_FLAGS,
    get_department_goals,
    set_department_goal,
    clear_department_goal,
    GOAL_TRACKED_DEPARTMENTS,
    get_brand_settings,
    update_brand_settings,
    list_prompt_templates,
    add_prompt_template,
    remove_prompt_template,
    BRAND_TONES,
)
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
_ADMIN_ROLES = (ADMIN, OPERATIONS)
_FORBIDDEN = {"error": "You don't have access to this action."}
_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}


def get_system_config_api(role):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    result = get_system_config()
    from core.administration_access import system_admin_context
    result["can_manage_system"] = system_admin_context.get()
    if role not in _ADMIN_ROLES:
        result.pop("lobby_information", None)
    return result


def update_organization_profile_api(role, employee_id, **fields):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return update_organization_profile(employee_id, **fields)


def add_location_api(role, employee_id, name, address, is_primary=False):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return add_location(name, address, employee_id, is_primary=is_primary)


def remove_location_api(role, employee_id, index):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return remove_location(index, employee_id)


def update_business_hours_api(role, employee_id, day, hours):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return update_business_hours(day, hours, employee_id)


def update_defaults_api(role, employee_id, default_currency=None, default_timezone=None):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return update_defaults(employee_id, default_currency=default_currency, default_timezone=default_timezone)


def set_feature_flag_api(role, employee_id, flag, enabled):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_feature_flag(flag, enabled, employee_id)


def get_department_goals_api(role):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return {"goals": get_department_goals(), "tracked_departments": list(GOAL_TRACKED_DEPARTMENTS)}


def set_department_goal_api(role, employee_id, department, monthly_target):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return set_department_goal(department, monthly_target, employee_id)


def clear_department_goal_api(role, employee_id, department):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return clear_department_goal(department, employee_id)


# ---------------------------------------------------------------------------
# Brand settings + prompt templates (AI Management dashboard, 2026-07-23) --
# reads open to any authenticated role (every department benefits from the
# brand voice powering their own inline assist, and needs to browse saved
# prompt templates), writes ADMIN/OPERATIONS-only, matching this whole
# module's established ACL split.
# ---------------------------------------------------------------------------

def get_brand_settings_api(role):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return {"brand_settings": get_brand_settings(), "tones": list(BRAND_TONES)}


def update_brand_settings_api(role, employee_id, patch):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    result = update_brand_settings(patch, employee_id)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"brand_settings": result}


def list_prompt_templates_api(role):
    if role not in _ALL_ROLES:
        return _FORBIDDEN
    return {"prompt_templates": list_prompt_templates()}


def add_prompt_template_api(role, employee_id, name, body):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return add_prompt_template(name, body, employee_id)


def remove_prompt_template_api(role, employee_id, template_id):
    if role not in _ADMIN_ROLES:
        return _ADMIN_ONLY_ERROR
    return remove_prompt_template(template_id)
