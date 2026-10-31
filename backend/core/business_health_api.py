"""
core/business_health_api.py -- ACL layer for Readiness' new "Business Health" Top
Menu item (core/business_health.py). Deliberately open to every real role (ADMIN,
OPERATIONS, SALES, MARKETING, SERVICE, FINANCE) -- this is exec-layer data every
department head plus ADMIN/OPERATIONS would legitimately want visibility into,
matching the precedent core/data_connections_api.py's readiness_predictions_api()
already established for the pre-existing Readiness module ("Sam: everyone can see
tomorrow, a week, a month, a quarter" -- predictions are read-only, non-sensitive
forward-looking figures, not the compensation-adjacent data core/employee_value.py
gates more tightly). Business Health is read-only composition, same shape -- no
mutation functions exist here at all.

The individual sub-signals composed inside core/business_health.py keep their OWN
already-real ACL where one exists (Collections/Portfolio Quality stay ADMIN/
OPERATIONS/FINANCE-gated at core/collections_api.py's/core/loan_servicing_api.py's
own layer; Marketing ROI stays ADMIN/OPERATIONS/MARKETING-gated at core/
marketing_attribution_api.py's own layer) -- this module's own gate is deliberately
just "is this a real role at all," not a second, redundant restriction on top.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.business_health import (
    get_business_health_overview,
    sales_health,
    service_health,
    finance_health,
    marketing_health,
    inventory_health,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

_DEPARTMENT_FUNCTIONS = {
    "sales": sales_health,
    "service": service_health,
    "finance": finance_health,
    "marketing": marketing_health,
    "inventory": inventory_health,
}


def _denied():
    return {"error": "You don't have access to Business Health data."}


def get_business_health_overview_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_business_health_overview(role)


def get_business_health_department_api(role, department):
    if role not in _ALL_ROLES:
        return _denied()

    fn = _DEPARTMENT_FUNCTIONS.get((department or "").lower())
    if not fn:
        return {"error": f"Unknown department '{department}' -- expected one of {sorted(_DEPARTMENT_FUNCTIONS.keys())}."}

    return fn(role)
