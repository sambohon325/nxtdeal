"""Customer-owned companion data requires a revocable session and bound provider proof.

No matching by caller-supplied contact and no legacy simulated Verify authority.
This resolver does not enable HTTP routes or certify live provider configuration.
"""
from datetime import datetime, timezone

from core import customer_accounts as accounts
from core.dealeros import ledger
from core.entity_types import CUSTOMER


def resolve_customer(token):
    payload = accounts.verify_customer_token(token)
    if not payload:
        return None, {"error": "Sign in to continue.", "reason": "token"}
    account = accounts.get_account(payload["account_id"])
    return resolve_linked_customer(account)


def resolve_linked_customer(account):
    """Check current CRM authority for an account, including account summaries."""
    denied = (None, {"error": "Verify your contact to view your account.", "reason": "unverified"})
    if account is None or account.attributes.get("status") != "active":
        return denied
    attributes = account.attributes
    proof = attributes.get("link_proof")
    customer_id = attributes.get("linked_customer_id")
    if not isinstance(proof, dict) or not isinstance(customer_id, str):
        return denied
    customer = ledger.get_entity(customer_id)
    if customer is None or customer.entity_type != CUSTOMER or proof.get("customer_id") != customer_id:
        return denied
    try:
        verified_at = datetime.fromisoformat(proof["verified_at"].replace("Z", "+00:00"))
        if verified_at.tzinfo is None or verified_at > datetime.now(timezone.utc):
            return denied
    except (KeyError, AttributeError, ValueError, TypeError, OverflowError):
        return denied
    if proof.get("channel") == "email" and proof.get("provider") == "privateemail":
        contact = accounts._customer_email(customer)
        verified = attributes.get("email_verified") is True
    elif proof.get("channel") == "sms" and proof.get("provider") == "twilio_verify":
        contact = accounts._customer_sms_destination(customer)
        verified = attributes.get("phone_verified") is True
    else:
        return denied
    if not verified or not contact or proof.get("recipient") != contact:
        return denied
    return customer_id, None
