"""
ACL for MySales adoption (Phase 6). Recording activity is self-service (a MySales rep pings
their own usage). The adoption summary + Readiness conversion signals are ADMIN/OPERATIONS
(the Hub/Readiness/growth tier).
"""

from core import mysales_adoption
from core.permissions import ADMIN, OPERATIONS

_READINESS_ROLES = (ADMIN, OPERATIONS)


def record_activity_api(role, employee_id, dealership_id=None, action="open", dealership_on_dealeros=False, rep_name=None):
    return mysales_adoption.record_activity(
        employee_id, dealership_id=dealership_id, action=action,
        dealership_on_dealeros=dealership_on_dealeros, rep_name=rep_name,
    )


def get_adoption_summary_api(role):
    if role not in _READINESS_ROLES:
        return {"error": "Admin/Operations role required for adoption analytics"}
    return mysales_adoption.get_adoption_summary()


def get_conversion_signals_api(role, min_reps=1):
    if role not in _READINESS_ROLES:
        return {"error": "Admin/Operations role required for conversion signals"}
    return mysales_adoption.get_conversion_signals(min_reps=min_reps)
