"""
ACL layer for core/lending_compliance.py (2026-07-17, session 112 follow-up) --
OFAC/SDN screening + IRS Form 8300 cash reporting, imported directly into
api/app.py's route handlers, same "no service layer indirection" convention every
other `*_api.py` module in this codebase follows.

Role rule: viewing (dashboard/status/obligations) is the broad board-view set
core/deals_api.py's own _BOARD_VIEW_ROLES already establishes for deal-adjacent data
(ADMIN/OPERATIONS/SALES/FINANCE) -- a salesperson desking a deal legitimately needs to
see whether OFAC screening is blocking their funding. Recording a cash payment is
narrower, ADMIN/OPERATIONS/SALES/FINANCE (a desk-adjacent action -- a salesperson
genuinely takes payments at the desk). Recording an OFAC screening result and filing
Form 8300 are both compliance-officer actions, narrower still: ADMIN/OPERATIONS/
FINANCE, matching core/fi_products_api.py's own narrower _FI_ROLES precedent for
"presenting/deciding" vs. board-wide viewing.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE
from core.lending_compliance import (
    get_ofac_screening_status,
    record_ofac_screening,
    record_cash_payment,
    get_form_8300_status,
    file_form_8300,
    get_form_8300_obligations,
    get_lending_compliance_dashboard,
)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_CASH_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_COMPLIANCE_OFFICER_ROLES = (ADMIN, OPERATIONS, FINANCE)

_VIEW_FORBIDDEN = {
    "error": "You don't have access to lending compliance data with your current role -- "
    "Admin, Operations, Sales, or Finance can view it."
}
_COMPLIANCE_FORBIDDEN = {
    "error": "You don't have access to record this with your current role -- "
    "Admin, Operations, or Finance can."
}


def get_lending_compliance_dashboard_api(role):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return get_lending_compliance_dashboard()


def get_ofac_screening_status_api(role, deal_id):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return get_ofac_screening_status(deal_id)


def record_ofac_screening_api(role, deal_id, cleared, screened_by, notes=""):

    if role not in _COMPLIANCE_OFFICER_ROLES:
        return _COMPLIANCE_FORBIDDEN

    return record_ofac_screening(deal_id, cleared, screened_by, notes)


def record_cash_payment_api(role, deal_id, amount, payment_date, recorded_by):

    if role not in _CASH_ROLES:
        return _VIEW_FORBIDDEN

    return record_cash_payment(deal_id, amount, payment_date, recorded_by)


def get_form_8300_status_api(role, deal_id):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return get_form_8300_status(deal_id)


def file_form_8300_api(role, deal_id, filed_by, filing_date=None):

    if role not in _COMPLIANCE_OFFICER_ROLES:
        return _COMPLIANCE_FORBIDDEN

    return file_form_8300(deal_id, filed_by, filing_date)


def get_form_8300_obligations_api(role, status=None):

    if role not in _VIEW_ROLES:
        return _VIEW_FORBIDDEN

    return {"obligations": get_form_8300_obligations(status)}
