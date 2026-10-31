"""
ACL layer for core/bank_reconciliation.py (2026-07-17, session 112 follow-up) --
imported directly into api/app.py's route handlers, same "no service layer
indirection" convention every other `*_api.py` module in this codebase follows.

Role rule: matches core/general_ledger_api.py's/core/loan_accounting_api.py's own
narrow role set exactly -- viewing AND every mutation (generate feed, confirm match,
mark reviewed) are ADMIN/OPERATIONS/FINANCE only.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.bank_reconciliation import (
    generate_simulated_bank_feed,
    get_reconciliation_status,
    confirm_match,
    mark_transaction_reviewed,
    list_transactions,
)


_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to bank reconciliation with your current role -- "
    "Admin, Operations, or Finance can."
}


def generate_simulated_bank_feed_api(role, generated_by, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return generate_simulated_bank_feed(generated_by, start_date, end_date)


def get_reconciliation_status_api(role, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_reconciliation_status(start_date, end_date)


def confirm_match_api(role, transaction_id, gl_entry_id, confirmed_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return confirm_match(transaction_id, gl_entry_id, confirmed_by)


def mark_transaction_reviewed_api(role, transaction_id, reviewed_by, note=""):

    if role not in _ROLES:
        return _FORBIDDEN

    return mark_transaction_reviewed(transaction_id, reviewed_by, note)


def list_transactions_api(role, status=None, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return {"transactions": list_transactions(status, start_date, end_date)}
