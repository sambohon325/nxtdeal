"""
core/service_customers_api.py -- ACL layer for core/service_customers.py.
Viewing matches the RO Workflow Engine's own broad view-role set (Sales
cares about a customer's service history/warranty status, Finance cares
about declined-service revenue at risk) -- there's no mutation in this
module at all (Customer 360/Retention/Lost Customer Recovery/Declined
Services are all read views; the one real action, logging a follow-up
communication, already has its own ACL via core/repair_orders_api.py's
log_ro_communication_api), so there's no narrower mutate-role set to define.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.service_customers import (
    get_customer_360,
    get_retention_metrics,
    get_lost_customer_recovery,
    get_declined_services,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)


def _forbidden():
    return {"error": "Forbidden: insufficient role for this view."}


def get_customer_360_api(role, customer_id):
    if role not in _VIEW_ROLES:
        return _forbidden()
    return get_customer_360(customer_id)


def get_retention_metrics_api(role, customer_id):
    if role not in _VIEW_ROLES:
        return _forbidden()
    return get_retention_metrics(customer_id)


def get_lost_customer_recovery_api(role):
    if role not in _VIEW_ROLES:
        return _forbidden()
    return get_lost_customer_recovery()


def get_declined_services_api(role):
    if role not in _VIEW_ROLES:
        return _forbidden()
    return get_declined_services()
