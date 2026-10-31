"""
ACL layer for Readiness' "Performance Readiness" item (core/
performance_readiness.py). Viewing is deliberately broad -- every real role
(ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE) -- matching the same
"everyone can see tomorrow, a week, a month, a quarter" precedent core/
data_connections_api.py's readiness_predictions_api() and core/
business_health_api.py already established: read-only, non-sensitive
forward-looking performance data, not the compensation-adjacent data core/
employee_value.py gates more tightly. Goal-SETTING stays entirely in core/
system_config_api.py (ADMIN/OPERATIONS-only) -- not duplicated here, since
the goal itself is stored on the SystemConfig singleton, not a Performance
Readiness entity.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.performance_readiness import (
    get_performance_readiness_overview,
    get_department_performance_readiness,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to Performance Readiness data."}


def get_performance_readiness_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_performance_readiness_overview()


def get_performance_readiness_department_api(role, department):
    if role not in _ALL_ROLES:
        return _denied()
    return get_department_performance_readiness(department)
