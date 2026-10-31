"""
ACL layer for core/general_ledger.py (2026-07-17, session 112 follow-up) -- imported
directly into api/app.py's route handlers, same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows.

Role rule: matches core/loan_accounting_api.py's own narrow role set exactly --
viewing AND every mutation (sync, generate, delete) are ADMIN/OPERATIONS/FINANCE
only. This is the dealership's general ledger; no SALES/MARKETING/SERVICE access.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.general_ledger import (
    get_chart_of_accounts,
    sync_real_entries,
    generate_simulated_entries,
    delete_entry,
    get_general_ledger,
    get_trial_balance,
    get_income_statement,
    get_balance_sheet,
)


_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to the general ledger with your current role -- "
    "Admin, Operations, or Finance can."
}


def get_chart_of_accounts_api(role):

    if role not in _ROLES:
        return _FORBIDDEN

    return {"accounts": get_chart_of_accounts()}


def sync_real_entries_api(role, synced_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return sync_real_entries(synced_by)


def generate_simulated_entries_api(role, year, month, generated_by, floorplan_exposure=0.0):

    if role not in _ROLES:
        return _FORBIDDEN

    return generate_simulated_entries(year, month, generated_by, floorplan_exposure)


def delete_entry_api(role, entry_id, deleted_by):

    if role not in _ROLES:
        return _FORBIDDEN

    return delete_entry(entry_id, deleted_by)


def get_general_ledger_api(role, account_number=None, start_date=None, end_date=None, limit=200, offset=0):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_general_ledger(account_number, start_date, end_date, limit=limit, offset=offset)


def get_trial_balance_api(role, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_trial_balance(start_date, end_date)


def get_income_statement_api(role, start_date=None, end_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_income_statement(start_date, end_date)


def get_balance_sheet_api(role, as_of_date=None):

    if role not in _ROLES:
        return _FORBIDDEN

    return get_balance_sheet(as_of_date)
