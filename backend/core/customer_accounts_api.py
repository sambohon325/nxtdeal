"""
Thin API layer for customer accounts (2026-07-24) — validate + call the real function +
shape the response, matching core/*_api.py convention. Also owns customer-token resolution
for the /customer/* routes (the customer twin of api/deps._authenticate).
"""

from core import customer_accounts


def _resolve_customer(authorization, include_session=False):
    """Bearer customer-token → account_id, or (None, error-dict). Domain-separated from
    employee tokens, so an employee bearer is rejected here just like a customer bearer is
    rejected on employee routes."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None, {"error": "Sign in to continue."}
    token = authorization.split(" ", 1)[1].strip()
    payload = customer_accounts.verify_customer_token(token)
    if not payload:
        return None, {"error": "Your session expired — sign in again."}
    return (payload if include_session else payload["account_id"]), None


def signup_api(email, password, name=None, phone=None):
    return customer_accounts.sign_up(email, password, name=name, phone=phone)


def login_api(email, password):
    return customer_accounts.log_in(email, password)


def request_link_code_api(authorization, channel="email"):
    session, error = _resolve_customer(authorization, include_session=True)
    if error:
        return error
    return customer_accounts.request_link_code(session["account_id"], channel=channel,
                                              expected_session_version=session["session_version"])


def confirm_link_code_api(authorization, channel, code):
    session, error = _resolve_customer(authorization, include_session=True)
    if error:
        return error
    return customer_accounts.confirm_link_code(session["account_id"], channel, code,
                                              expected_session_version=session["session_version"])


def me_api(authorization):
    account_id, error = _resolve_customer(authorization)
    if error:
        return error
    return customer_accounts.me(account_id)


def logout_api(authorization):
    account_id, error = _resolve_customer(authorization)
    if error:
        return error
    return customer_accounts.revoke_customer_sessions(account_id)
