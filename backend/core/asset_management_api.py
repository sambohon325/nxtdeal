"""
core/asset_management_api.py -- ACL layer for core/asset_management.py. Same narrow
role set as the rest of this arc (ADMIN/OPERATIONS/FINANCE) for both viewing and
mutating -- title/lien/insurance/collateral-valuation detail is the same sensitive
borrower/collateral information those other modules already gate this way.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.asset_management import (
    get_lien_status,
    update_lienholder,
    release_lien,
    get_insurance_status,
    update_insurance,
    get_collateral_valuation,
    get_asset_summary,
    get_asset_portfolio_dashboard,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Asset Management"}


def get_lien_status_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_lien_status(loan_id)


def update_lienholder_api(role, employee_id, loan_id, lienholder_name):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_lienholder(loan_id, lienholder_name, employee_id)


def release_lien_api(role, employee_id, loan_id, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return release_lien(loan_id, employee_id, reason=reason)


def get_insurance_status_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_insurance_status(loan_id)


def update_insurance_api(role, employee_id, loan_id, carrier, policy_number, expiration_date, loss_payee_confirmed):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_insurance(loan_id, carrier, policy_number, expiration_date, loss_payee_confirmed, employee_id)


def get_collateral_valuation_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_collateral_valuation(loan_id)


def get_asset_summary_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_asset_summary(loan_id)


def get_asset_portfolio_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_asset_portfolio_dashboard()
