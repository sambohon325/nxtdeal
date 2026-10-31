"""
ACL layer for core/loan_accounting.py (2026-07-17, session 112 follow-up) -- imported
directly into api/app.py's route handlers, same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows.

Role rule: this is a controller/back-office surface, narrower than most of this arc's
other modules -- viewing AND every mutating action (post, close, reopen) are
ADMIN/OPERATIONS/FINANCE only, matching core/loan_servicing_api.py's/
core/payments_api.py's own narrow role set exactly (the same sensitive balance/ledger
detail those modules already gate this way). No SALES -- a salesperson has no reason
to see or touch the general ledger.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.loan_accounting import (
    get_loan_accounting_summary,
    get_daily_ledger,
    get_unposted_payments,
    post_payment_to_ledger,
    post_all_due,
    close_accounting_period,
    reopen_accounting_period,
    list_periods,
)


_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to loan accounting with your current role -- "
    "Admin, Operations, or Finance can."
}


def get_loan_accounting_summary_api(role, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_loan_accounting_summary(start_date, end_date)


def get_daily_ledger_api(role, payment_date):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_daily_ledger(payment_date)


def get_unposted_payments_api(role):

    if role not in _ROLES:
        return _FORBIDDEN

    return {"unposted": get_unposted_payments()}


def post_payment_to_ledger_api(role, payment_id, posted_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return post_payment_to_ledger(payment_id, posted_by)


def post_all_due_api(role, payment_date, posted_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return post_all_due(payment_date, posted_by)


def close_accounting_period_api(role, year, month, closed_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return close_accounting_period(year, month, closed_by)


def reopen_accounting_period_api(role, year, month, reopened_by):

    if role != ADMIN:
        return {"error": "Only an admin can reopen a closed accounting period."}

    return reopen_accounting_period(year, month, reopened_by)


def list_periods_api(role):

    if role not in _ROLES:
        return _FORBIDDEN

    return {
        "periods": [
            {"period_key": p.attributes.get("period_key"), "status": p.attributes.get("status"), "closed_by": p.attributes.get("closed_by"), "closed_at": p.attributes.get("closed_at")}
            for p in list_periods()
        ]
    }
