"""
core/data_health_api.py -- ACL layer for core/data_health.py. ADMIN/OPERATIONS
only, matching this item's own historical gate (the pre-existing
core/readiness_menu.py's data_health() has always been effectively
ADMIN/OPERATIONS-only, since every branch flows through
core/data_connections_api.py's CONNECTION_ROLES) -- Data Health surfaces
integration configuration and dealership-wide data-integrity detail (customer
duplicate groups, contract completeness gaps), not the read-only
forward-looking figures Business Health/Enterprise Risk Center/
Recommendations/Overview are deliberately open to every role for.
"""

from core.permissions import ADMIN, OPERATIONS
from core.data_health import (
    get_data_health_overview,
    integration_monitoring,
    data_completeness,
    data_accuracy,
    data_freshness,
)

_ROLES = (ADMIN, OPERATIONS)

_DENIED = {
    "error": "You don't have access to Data Health with your current role -- "
    "Admin or Operations can review integration/data-integrity detail."
}


def get_data_health_overview_api(role):
    if role not in _ROLES:
        return _DENIED
    return get_data_health_overview(role)


def get_integration_monitoring_api(role):
    if role not in _ROLES:
        return _DENIED
    return integration_monitoring(role)


def get_data_completeness_api(role):
    if role not in _ROLES:
        return _DENIED
    return data_completeness()


def get_data_accuracy_api(role):
    if role not in _ROLES:
        return _DENIED
    return data_accuracy(role)


def get_data_freshness_api(role):
    if role not in _ROLES:
        return _DENIED
    return data_freshness(role)
