"""Service Customers router -- fourth slice of Service's rebuild
(core/service_customers.py / core/service_customers_api.py).

Sam's spec: "Service should be relationship-driven" -- a Customer Service
Profile (Vehicles Owned/Service History/Warranty/Recall/Declined Services),
Customer Retention, Lost Customer Recovery, and Declined Services. See
core/service_customers.py's module docstring for the full reasoning.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 13,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/
response shapes, same auth flow. Static "/service-customers/lost-customer-
recovery" and "/service-customers/declined-services" registered before the
dynamic "/service-customers/{customer_id}" (and its own "/retention"
sibling), matching the original file's own route-shadowing-avoidance
ordering.
"""

from fastapi import APIRouter, Header

from api.deps import _authenticate

from core.service_customers_api import (
    get_customer_360_api as get_service_customer_360_api,
    get_retention_metrics_api as get_service_retention_metrics_api,
    get_lost_customer_recovery_api,
    get_declined_services_api,
)


router = APIRouter()


@router.get("/service-customers/lost-customer-recovery")
def service_lost_customer_recovery(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lost_customer_recovery_api(payload["role"])


@router.get("/service-customers/declined-services")
def service_declined_services(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_declined_services_api(payload["role"])


@router.get("/service-customers/{customer_id}")
def service_customer_360(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_service_customer_360_api(payload["role"], customer_id)


@router.get("/service-customers/{customer_id}/retention")
def service_customer_retention(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_service_retention_metrics_api(payload["role"], customer_id)
