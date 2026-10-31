"""
ACL layer for core/customer_360.py -- imported directly into api/app.py's route
handlers, same "no service layer indirection" convention every other `*_api.py`
module in this codebase follows.

Role rule: matches core/permissions.py's own CUSTOMER access set exactly (broad --
ADMIN/OPERATIONS/SALES/MARKETING/SERVICE/FINANCE all legitimately care about a
customer's real record), since Customer 360 is fundamentally a Customer-entity view
and shouldn't be gated any narrower than viewing the Customer itself already is.
core/ai_tools.py's own role-filtered get_entity_by_id()/get_related_entities() (used
internally by core/customer_360.py) still apply their own per-field/per-related-type
filtering on top of this -- this is just the outer gate.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.customer_360 import get_customer_360


_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to Customer 360 with your current role."
}


def get_customer_360_api(role, customer_id, employee_id=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_customer_360(role, customer_id, employee_id=employee_id)
