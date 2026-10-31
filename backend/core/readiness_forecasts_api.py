"""
ACL layer for Readiness' "Forecasts" item (core/readiness_forecasts.py) and the
Readiness Timeline capstone. Viewing is deliberately broad -- every real role
(ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE) -- matching the same
"everyone can see tomorrow, a week, a month, a quarter" precedent
core/data_connections_api.py's readiness_predictions_api() and every other module in
this Readiness reframe (core/business_health_api.py, core/performance_readiness_api.py,
etc.) already established: read-only, non-sensitive forward-looking/trend data.
Individual sub-signals composed inside (Collections/Portfolio Performance) keep their
own, narrower ADMIN/OPERATIONS/FINANCE gate at their own layer and degrade gracefully
for a caller outside that role set -- not re-gated here.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.readiness_forecasts import (
    get_forecasts_overview,
    sales_forecast,
    service_forecast,
    inventory_forecast,
    finance_forecast,
    get_readiness_timeline_overview,
    get_readiness_timeline_department,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

_DEPARTMENT_FUNCTIONS = {
    "sales": sales_forecast,
    "service": service_forecast,
    "inventory": inventory_forecast,
    "finance": finance_forecast,
}


def _denied():
    return {"error": "You don't have access to Readiness Forecasts data."}


def get_forecasts_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_forecasts_overview(role)


def get_forecasts_department_api(role, department):
    if role not in _ALL_ROLES:
        return _denied()
    fn = _DEPARTMENT_FUNCTIONS.get((department or "").lower())
    if not fn:
        return {"error": f"Unknown department '{department}' for Forecasts -- expected one of {sorted(_DEPARTMENT_FUNCTIONS.keys())}."}
    return fn(role)


def get_readiness_timeline_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_readiness_timeline_overview()


def get_readiness_timeline_department_api(role, department):
    if role not in _ALL_ROLES:
        return _denied()
    result = get_readiness_timeline_department(department)
    if result is None:
        return {"error": f"No real historical trend source exists for department '{department}'."}
    return result
