"""
ACL layer for core/strategic_planning.py (Readiness reframe, item #9).
Viewing is deliberately broad -- every real role -- matching the same
"everyone can see" precedent core/performance_readiness_api.py/
core/business_health_api.py already established for Readiness: read-only,
non-sensitive forward-looking planning data. Mutating (creating/editing
Objectives and Initiatives, budgets, status changes, the Performance
Readiness sync action) is ADMIN/OPERATIONS-only, matching
core/system_config_api.py's own established convention for anything that
edits planning/config-adjacent data.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.strategic_planning import (
    STRATEGIC_DEPARTMENTS,
    TRACKING_TYPE_CATALOG,
    create_objective,
    get_objective,
    list_objectives,
    update_objective,
    update_objective_progress,
    update_objective_budget,
    cancel_objective,
    reopen_objective,
    sync_objective_to_monthly_goal,
    get_quarterly_rollup,
    create_initiative,
    get_initiative,
    list_initiatives,
    update_initiative_status,
    update_initiative_progress,
    update_initiative_budget,
    get_strategic_planning_overview,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS)


def _denied():
    return {"error": "You don't have access to Strategic Planning data."}


def _mutate_denied():
    return {"error": "Admin/Operations role required to edit Strategic Planning data."}


def get_strategic_planning_overview_api(role, quarter=None, year=None):
    if role not in _ALL_ROLES:
        return _denied()
    return get_strategic_planning_overview(quarter=quarter, year=year)


def get_strategic_planning_catalog_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return {
        "departments": list(STRATEGIC_DEPARTMENTS),
        "tracking_type_catalog": TRACKING_TYPE_CATALOG,
    }


def get_quarterly_rollup_api(role, quarter=None, year=None):
    if role not in _ALL_ROLES:
        return _denied()
    return get_quarterly_rollup(quarter=quarter, year=year)


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------

def create_objective_api(role, employee_id, quarter, year, department, title, **fields):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return create_objective(quarter, year, department, title, employee_id, **fields)


def get_objective_api(role, objective_id):
    if role not in _ALL_ROLES:
        return _denied()
    return get_objective(objective_id)


def list_objectives_api(role, quarter=None, year=None, department=None):
    if role not in _ALL_ROLES:
        return _denied()
    return list_objectives(quarter=quarter, year=year, department=department)


def update_objective_api(role, employee_id, objective_id, **fields):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_objective(objective_id, employee_id, **fields)


def update_objective_progress_api(role, employee_id, objective_id, progress_pct):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_objective_progress(objective_id, progress_pct, employee_id)


def update_objective_budget_api(role, employee_id, objective_id, budget_allocated=None, budget_spent=None):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_objective_budget(objective_id, employee_id, budget_allocated=budget_allocated, budget_spent=budget_spent)


def cancel_objective_api(role, employee_id, objective_id):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return cancel_objective(objective_id, employee_id)


def reopen_objective_api(role, employee_id, objective_id):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return reopen_objective(objective_id, employee_id)


def sync_objective_to_monthly_goal_api(role, employee_id, objective_id):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return sync_objective_to_monthly_goal(objective_id, employee_id)


# ---------------------------------------------------------------------------
# Initiatives
# ---------------------------------------------------------------------------

def create_initiative_api(role, employee_id, name, department, tracking_type, **fields):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return create_initiative(name, department, tracking_type, employee_id, **fields)


def get_initiative_api(role, initiative_id):
    if role not in _ALL_ROLES:
        return _denied()
    return get_initiative(initiative_id)


def list_initiatives_api(role, department=None, status=None, tracking_type=None):
    if role not in _ALL_ROLES:
        return _denied()
    return list_initiatives(department=department, status=status, tracking_type=tracking_type)


def update_initiative_status_api(role, employee_id, initiative_id, status):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_initiative_status(initiative_id, status, employee_id)


def update_initiative_progress_api(role, employee_id, initiative_id, progress_pct):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_initiative_progress(initiative_id, progress_pct, employee_id)


def update_initiative_budget_api(role, employee_id, initiative_id, budget_allocated=None, budget_spent=None):
    if role not in _MUTATE_ROLES:
        return _mutate_denied()
    return update_initiative_budget(initiative_id, employee_id, budget_allocated=budget_allocated, budget_spent=budget_spent)
