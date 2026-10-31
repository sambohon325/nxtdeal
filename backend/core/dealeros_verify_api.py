"""
core/dealeros_verify_api.py -- API layer for NXTDeal Verify (2026-07-24). Two audiences,
two postures:

  * STAFF (role-gated, read-only): viewing the verification roster, one session, the summary,
    and the trust-ladder catalog is open to any authenticated role -- non-sensitive
    operational insight, the same posture as the fleet/workforce/connect views. Staff never
    perform a customer's verification for them here.

  * CUSTOMER (public, token-as-credential): the actual verification actions (start, add
    contact, request/confirm a code, submit identity, submit a credit app) are unauthenticated
    and driven by the session's unguessable token -- exactly the payments.py Customer Payment
    Portal pattern. There is NO role gate on these; the token IS the credential, and every such
    action is recorded against dealeros_verify.CUSTOMER_SENTINEL, never an employee id. These
    are called from the /public/verify/* routes in api/app.py.
"""

from core import dealeros_verify as verify


# ------------------------------------------------------------------------------------
# Staff, read-only (any authenticated role).
# ------------------------------------------------------------------------------------

def get_verify_dashboard_api(role):
    return {
        "summary": verify.verification_summary(),
        "recent": verify.list_verifications(limit=25)["verifications"],
        "catalog": verify.capability_catalog(),
    }


def list_verifications_api(role, tier=None, limit=100):
    return verify.list_verifications(tier=tier, limit=limit)


def get_verification_api(role, verf_id):
    view = verify.get_verification(verf_id)
    if not view:
        return {"error": f"No verification found with id {verf_id}"}
    return view


def get_verify_catalog_api(role):
    return verify.capability_catalog()


# ------------------------------------------------------------------------------------
# Customer, public (token-as-credential -- no role gate).
# ------------------------------------------------------------------------------------

def _resolve_token(token):
    """token -> verification id, or None. The token is the customer's only credential."""
    view = verify.get_verification_by_token(token)
    return view["id"] if view else None


def public_start_verification(email=None, phone=None):
    """Begin a session. Returns the created view PLUS the session_token the client must keep
    and present on every subsequent call."""
    result = verify.start_verification(email=email, phone=phone)
    if "error" in result:
        return result
    # Surface the token (the view deliberately omits it) so the client can continue.
    from core.dealeros import ledger
    entity = ledger.get_entity(result["verification"]["id"])
    return {
        "verification": result["verification"],
        "session_token": entity.attributes["session_token"],
    }


def public_get_verification(token):
    view = verify.get_verification_by_token(token)
    return view if view else {"error": "Invalid or unknown verification token"}


def public_set_contact(token, email=None, phone=None):
    vid = _resolve_token(token)
    if not vid:
        return {"error": "Invalid or unknown verification token"}
    return verify.set_contact(vid, email=email, phone=phone)


def public_request_code(token, channel):
    vid = _resolve_token(token)
    if not vid:
        return {"error": "Invalid or unknown verification token"}
    if channel not in ("email", "sms"):
        return {"error": "channel must be 'email' or 'sms'"}
    # The core implementation returns the challenge itself as dev_code. That is
    # useful in isolated tests, but is not proof that a visitor owns a contact.
    return _provider_unavailable()


def public_confirm_code(token, channel, code):
    vid = _resolve_token(token)
    if not vid:
        return {"error": "Invalid or unknown verification token"}
    if channel not in ("email", "sms"):
        return {"error": "channel must be 'email' or 'sms'"}
    return _provider_unavailable()


def public_submit_identity(token, license_number, selfie_provided=True):
    vid = _resolve_token(token)
    if not vid:
        return {"error": "Invalid or unknown verification token"}
    return _provider_unavailable()


def public_submit_credit(token, credit_app_id):
    vid = _resolve_token(token)
    if not vid:
        return {"error": "Invalid or unknown verification token"}
    return _provider_unavailable()


def _provider_unavailable():
    """Fail closed until the public flow has a real provider-backed verifier.

    Internal simulation helpers remain available to isolated tests. Do not add a
    production environment toggle that turns simulation into identity evidence.
    """
    return {"error": "Customer verification is not available yet. Please contact the dealership.",
            "reason": "provider_unavailable"}
