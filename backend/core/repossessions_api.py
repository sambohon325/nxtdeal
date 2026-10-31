"""
core/repossessions_api.py -- ACL layer for core/repossessions.py. Same narrow role
set as core/loan_servicing_api.py/core/payments_api.py/core/collections_api.py
(ADMIN/OPERATIONS/FINANCE) for both viewing and mutating -- repossession work touches
the same sensitive borrower/balance detail those modules already gate this way.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.repossessions import (
    get_referral_queue,
    create_case,
    assign_agent,
    record_location,
    record_recovery,
    record_storage,
    record_disposition,
    redeem_case,
    cancel_case,
    compute_deficiency_balance,
    get_case,
    list_cases,
    get_repossessions_dashboard,
    get_recovery_stats,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Repossessions"}


def get_referral_queue_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_referral_queue()


def create_case_api(role, employee_id, loan_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = create_case(loan_id, employee_id, reason=reason)
    if isinstance(result, dict) and "error" in result:
        return result
    return {"id": result.id, **result.attributes}


def assign_agent_api(role, employee_id, case_id, agent_name, agency="", phone=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(assign_agent(case_id, agent_name, employee_id, agency=agency, phone=phone))


def record_location_api(role, employee_id, case_id, location, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(record_location(case_id, location, employee_id, notes=notes))


def record_recovery_api(role, employee_id, case_id, recovered_date=None, condition="", odometer=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(record_recovery(case_id, employee_id, recovered_date=recovered_date, condition=condition, odometer=odometer))


def record_storage_api(role, employee_id, case_id, storage_facility, storage_start_date=None, daily_rate=0.0, transport_cost=0.0):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(record_storage(case_id, storage_facility, employee_id, storage_start_date=storage_start_date, daily_rate=daily_rate, transport_cost=transport_cost))


def record_disposition_api(role, employee_id, case_id, disposition_type, sale_price, sale_date=None, buyer="", notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(record_disposition(case_id, disposition_type, sale_price, employee_id, sale_date=sale_date, buyer=buyer, notes=notes))


def redeem_case_api(role, employee_id, case_id, redemption_amount, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(redeem_case(case_id, redemption_amount, employee_id, notes=notes))


def cancel_case_api(role, employee_id, case_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return _serialize(cancel_case(case_id, employee_id, reason=reason))


def compute_deficiency_balance_api(role, case_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return compute_deficiency_balance(case_id)


def get_case_api(role, case_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_case(case_id)


def list_cases_api(role, status=None, loan_id=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_cases(status=status, loan_id=loan_id)


def get_repossessions_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_repossessions_dashboard()


def get_recovery_stats_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_recovery_stats()


def _serialize(result):
    if isinstance(result, dict):
        return result
    return {"id": result.id, **result.attributes}
