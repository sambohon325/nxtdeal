"""
core/loan_servicing_api.py -- ACL layer for core/loan_servicing.py. Loan/borrower
detail is sensitive financial + PII data (address, employment/income, credit score,
contract balance), so both viewing and mutating are scoped to the same narrow role set
core/permissions.py's ENTITY_ACCESS already uses for FINANCE_CONTRACT itself:
ADMIN/OPERATIONS/FINANCE. No SALES/SERVICE/MARKETING access, unlike the broader
6-role view sets other Finance-adjacent modules (Pricing Desk, Vehicle Lifecycle) use
-- a loan's real balance and borrower detail isn't something Sales or Service needs to
see through this surface, distinct from the Deal itself (which Sales legitimately
desks and views through core/deals_api.py's own broader board-view roles).
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.loan_servicing import (
    get_loan_detail,
    get_loan_financials,
    get_loan_timeline,
    get_loan_status,
    set_loan_status,
    get_simulated_payment_status,
    get_portfolio_dashboard,
    compute_amortization_schedule,
    LOAN_STATUSES,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Loan Servicing / Portfolio"}


def get_loan_detail_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_loan_detail(loan_id)


def get_loan_financials_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_loan_financials(loan_id)


def get_loan_timeline_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_loan_timeline(loan_id)


def get_loan_status_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    status = get_loan_status(loan_id)
    if isinstance(status, dict) and "error" in status:
        return status
    return {"loan_id": loan_id, "loan_status": status}


def set_loan_status_api(role, employee_id, loan_id, status, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return set_loan_status(loan_id, status, employee_id, reason=reason)


def get_simulated_payment_status_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_simulated_payment_status(loan_id)


def get_portfolio_dashboard_api(role, bucket=None, limit=100):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_portfolio_dashboard(bucket=bucket, limit=limit)


def compute_amortization_schedule_api(role, principal, apr, term_months):
    """A standalone what-if amortization calculator -- useful for a loan that doesn't
    exist yet (e.g. checking terms before funding), not just an existing loan_id."""

    if role not in _VIEW_ROLES:
        return _denied()
    schedule = compute_amortization_schedule(principal, apr, term_months)
    return {"principal": principal, "apr": apr, "term_months": term_months, "schedule": schedule}
