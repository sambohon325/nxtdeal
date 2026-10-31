"""
core/payments_api.py -- ACL layer for core/payments.py. Same narrow role set as
core/loan_servicing_api.py (ADMIN/OPERATIONS/FINANCE) for every staff-side function --
payment/balance/borrower data is sensitive financial detail, same reasoning already
established for Portfolio. The Customer Payment Portal's public functions
(get_public_portal_view/submit_public_payment/submit_public_payoff_request) have NO
ACL wrapper at all -- they're genuinely unauthenticated, called directly from
api/app.py's /public/* routes, same convention as core/approval_center.py /
core/appointment_scheduling.py.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.payments import (
    record_payment,
    list_payments_for_loan,
    get_real_payment_summary,
    create_auto_draft,
    set_auto_draft_status,
    list_auto_drafts,
    run_due_auto_drafts,
    create_promise_to_pay,
    get_promise_status,
    list_promises_to_pay,
    record_extension,
    record_deferral,
    list_payment_adjustments,
    request_payoff,
    fulfill_payoff_request,
    list_payoff_requests,
    generate_payment_portal_link,
    get_payment_portal_link_status,
    revoke_payment_portal_link,
    get_payments_dashboard,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Payments"}


def record_payment_api(role, employee_id, loan_id, amount, method, payment_date=None, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_payment(loan_id, amount, method, employee_id, payment_date=payment_date, notes=notes)


def list_payments_for_loan_api(role, loan_id, include_declined=True):
    if role not in _VIEW_ROLES:
        return _denied()
    payments = list_payments_for_loan(loan_id, include_declined=include_declined)
    return {"loan_id": loan_id, "count": len(payments), "payments": [{**p.attributes, "id": p.id} for p in payments]}


def get_real_payment_summary_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    summary = get_real_payment_summary(loan_id)
    if summary is None:
        return {"loan_id": loan_id, "has_real_payments": False}
    return {"loan_id": loan_id, "has_real_payments": True, **summary}


def create_auto_draft_api(role, employee_id, loan_id, amount, method, day_of_month):
    if role not in _MUTATE_ROLES:
        return _denied()
    return create_auto_draft(loan_id, amount, method, day_of_month, employee_id)


def set_auto_draft_status_api(role, employee_id, draft_id, status):
    if role not in _MUTATE_ROLES:
        return _denied()
    return set_auto_draft_status(draft_id, status, employee_id)


def list_auto_drafts_api(role, loan_id=None, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    drafts = list_auto_drafts(loan_id=loan_id, status=status)
    return {"count": len(drafts), "drafts": [{**d.attributes, "id": d.id} for d in drafts]}


def run_due_auto_drafts_api(role, employee_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return run_due_auto_drafts(employee_id)


def create_promise_to_pay_api(role, employee_id, loan_id, promise_date, amount, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return create_promise_to_pay(loan_id, promise_date, amount, reason, employee_id)


def get_promise_status_api(role, ptp_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_promise_status(ptp_id)


def list_promises_to_pay_api(role, loan_id=None, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return {"promises": list_promises_to_pay(loan_id=loan_id, status=status)}


def record_extension_api(role, employee_id, loan_id, new_next_due_date, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_extension(loan_id, new_next_due_date, reason, employee_id)


def record_deferral_api(role, employee_id, loan_id, months, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_deferral(loan_id, months, reason, employee_id)


def list_payment_adjustments_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return {"loan_id": loan_id, "adjustments": list_payment_adjustments(loan_id)}


def request_payoff_api(role, employee_id, loan_id, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return request_payoff(loan_id, employee_id, notes=notes)


def fulfill_payoff_request_api(role, employee_id, loan_id, request_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return fulfill_payoff_request(loan_id, request_id, employee_id)


def list_payoff_requests_api(role, loan_id=None, status=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return {"requests": list_payoff_requests(loan_id=loan_id, status=status)}


def generate_payment_portal_link_api(role, employee_id, loan_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return generate_payment_portal_link(loan_id, employee_id)


def get_payment_portal_link_status_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_payment_portal_link_status(loan_id)


def revoke_payment_portal_link_api(role, employee_id, loan_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return revoke_payment_portal_link(loan_id, employee_id)


def get_payments_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_payments_dashboard()
