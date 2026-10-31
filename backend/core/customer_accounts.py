"""
Customer accounts — NXTDeal's first customer-facing login (2026-07-24, Sam: the customer
app "should just be able to sign in with whatever they created for their profile online /
through the dealers website / portal, or if they need to sign up there, or with a qr code
provided by the service department signage").

Each dealer runs its own NXTDeal backend (one deployment per dealer — see
docs/DEPLOYMENT.md), so a customer account naturally lives with, and is scoped to, that
dealer. An account is an email + password that maps to a CRM Customer/Lead record.

Design decisions (Sam's picks):
  • "Build in NXTDeal" — accounts + credentials are native here, not federated from an
    external site. The dealer's NXTDeal-built portal/website uses the same accounts.
  • "Match + verify" — on sign-up we look for an existing Customer/Lead with the same
    email or phone. If we find one we DON'T attach the account to it (which would expose
    that person's vehicles/service/equity) until the customer proves they own the channel
    with a one-time code. Unmatched sign-ups just start an empty account.

Security posture mirrors employees:
  • Password salt/hash live in a SEPARATE store (customer_credentials.json via
    core/customer_accounts_storage.py), NEVER in the graph. The graph holds only the
    non-secret CustomerAccount profile entity (email, linked customer id, verified flags).
  • Customer bearer tokens are DOMAIN-SEPARATED from employee tokens: signed with the same
    HMAC construction but a ":customer"-suffixed secret, so a customer token can never
    validate on an employee route (core/auth.verify_token) and vice-versa.

OTP delivery supports opt-in Private Email and Twilio Verify adapters. Provider codes
are never returned to callers. The legacy simulation seam exposes a development code
only with an explicit opt-in and cannot establish provider-bound companion authority.
"""

from copy import deepcopy

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import threading
from functools import wraps
from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import CUSTOMER, LEAD, CUSTOMER_ACCOUNT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.audit import audit_log
from core.auth import hash_password, verify_password, validate_password_strength, _secret
from core import integrations_registry

# OTP config — mirrors core/dealeros_verify.py so the two feel identical.
OTP_TTL_SECONDS = 600          # 10 minutes
OTP_MAX_ATTEMPTS = 5
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — a customer app session, not a staff one.

CUSTOMER_SENTINEL = "customer_via_app"

# Bounded process-local serialization: no growing lock map and no claim of
# cross-worker transactions. Provider calls for an account cannot overlap.
_CHALLENGE_LOCKS = tuple(threading.RLock() for _ in range(128))
_SIGNUP_LOCK = threading.RLock()
_SESSION_STATE_LOCK = threading.RLock()


def _restore_account_attributes(account, previous):
    # Challenge rollback must not undo a logout that persisted concurrently.
    with _SESSION_STATE_LOCK:
        version = account.attributes.get("session_version", 0)
        if version > previous.get("session_version", 0):
            previous["session_version"] = version
        account.attributes = previous


def _challenge_lock(account_id):
    bucket = hashlib.sha256(str(account_id).encode("utf-8")).digest()[0] % len(_CHALLENGE_LOCKS)
    return _CHALLENGE_LOCKS[bucket]


def _serialized_challenge(function):
    @wraps(function)
    def wrapped(account_id, *args, **kwargs):
        with _challenge_lock(account_id):
            return function(account_id, *args, **kwargs)
    return wrapped


def _expose_link_code():
    """SECURITY: the account-link one-time code proves the sign-up owns the MATCHED record's
    channel, so it must go ONLY to that record's real contact — never back to the caller. The
    code is surfaced in the API response ONLY when an operator explicitly opts in (local
    testing), never by default, even while delivery is simulated. Without this gate, returning
    dev_code let anyone who knew a customer's phone/email take over that customer's record."""
    from core.json_graph_repository import demo_persistence_disabled
    return demo_persistence_disabled() and os.environ.get("DEALEROS_EXPOSE_LINK_CODE") == "1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(email):
    return email.strip().lower() if isinstance(email, str) and len(email) <= 254 else ""


def _normalize_phone(phone):
    if not isinstance(phone, str) or len(phone) > 32 or not phone.isascii():
        return ""
    return "".join(ch for ch in phone if ch in "0123456789")


# =====================================================================================
# Credential store (separate from the graph, mirroring core/auth.CredentialStore)
# =====================================================================================

class CustomerCredentialStore:
    """email(lowercased) -> {account_id, email, salt, hash}. Persisted to
    customer_credentials.json, loaded at boot — never in the graph."""

    def __init__(self):
        self.credentials = {}

    def set_credential(self, email, account_id, password):
        email_key = _normalize_email(email)
        salt_hex, hash_hex = hash_password(password)
        self.credentials[email_key] = {
            "account_id": account_id,
            "email": email_key,
            "salt": salt_hex,
            "hash": hash_hex,
        }

    def authenticate(self, email, password):
        record = self.credentials.get(_normalize_email(email))
        if not record:
            return None
        if not verify_password(password, record["salt"], record["hash"]):
            return None
        return record["account_id"]

    def has_email(self, email):
        return _normalize_email(email) in self.credentials

    def load_credentials(self, data):
        self.credentials = data or {}

    def reset(self):
        self.credentials = {}


customer_credential_store = CustomerCredentialStore()


# =====================================================================================
# Customer tokens — domain-separated from employee tokens
# =====================================================================================

def _customer_secret():
    return _secret() + b":customer"


def issue_customer_token(account_id):
    # Never sign a version that is only temporarily visible during logout save.
    with _SESSION_STATE_LOCK:
        return _issue_customer_token_locked(account_id)


def _issue_customer_token_locked(account_id):
    account = get_account(account_id)
    if account is None or account.attributes.get("status") != "active":
        raise ValueError("Active customer account required")
    payload = {
        "session_version": account.attributes.get("session_version", 0),
        "account_id": account_id,
        "kind": "customer",
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    signature = hmac.new(_customer_secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_customer_token(token):
    """Returns the payload if valid, unexpired, and signed with the CUSTOMER secret; else
    None. An employee token fails here (different secret), and this token fails on the
    employee verify_token for the same reason."""
    if not isinstance(token, str) or len(token) > 4096 or not token.isascii():
        return None
    try:
        payload_b64, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    if len(signature) != 64 or any(char not in "0123456789abcdef" for char in signature):
        return None
    expected = hmac.new(_customer_secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "customer":
        return None
    expires = payload.get("expires_at")
    if type(expires) not in (int, float) or not (0 < expires <= time.time() + TOKEN_TTL_SECONDS) or expires <= time.time():
        return None
    if not isinstance(payload.get("account_id"), str):
        return None
    account = get_account(payload["account_id"])
    if account is None or account.attributes.get("status") != "active":
        return None
    version = payload.get("session_version")
    if type(version) is not int or version != account.attributes.get("session_version", 0):
        return None
    return payload


def revoke_customer_sessions(account_id):
    with _SESSION_STATE_LOCK:
        return _revoke_customer_sessions_locked(account_id)


def _revoke_customer_sessions_locked(account_id):
    account = get_account(account_id)
    if account is None:
        return {"error": "Account not found."}
    present = "session_version" in account.attributes
    previous = account.attributes.get("session_version", 0)
    account.attributes["session_version"] = previous + 1
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        if present:
            account.attributes["session_version"] = previous
        else:
            account.attributes.pop("session_version", None)
        raise
    return {"revoked": True}


# =====================================================================================
# CRM matching
# =====================================================================================

def _customer_email(entity):
    for key in ("email", "Email", "email_address"):
        if entity.attributes.get(key):
            return _normalize_email(entity.attributes.get(key))
    return ""


def _customer_phone(entity):
    for key in ("phone", "Phone", "phone_number", "mobile", "cell"):
        if entity.attributes.get(key):
            return _normalize_phone(entity.attributes.get(key))
    return ""


def _find_matching_customer(email, phone):
    """Exact (not substring) match on email or phone against CUSTOMER/LEAD records. Returns
    the entity or None. Email match takes precedence over phone."""
    email_key = _normalize_email(email)
    phone_key = _normalize_phone(phone)
    phone_hit = None
    for entity in ledger.get_all().values():
        if entity.entity_type not in (CUSTOMER, LEAD):
            continue
        if email_key and _customer_email(entity) == email_key:
            return entity
        if phone_key and _customer_phone(entity) == phone_key:
            phone_hit = phone_hit or entity
    return phone_hit


def _matched_channel(record, email, phone):
    """Verify on the channel we actually matched on, so the code is sent to a contact the
    sign-up already proved they know — email if the record's email matched, else sms."""
    if record is None:
        return "email"
    if _customer_email(record) and _customer_email(record) == _normalize_email(email):
        return "email"
    if _customer_phone(record) and _customer_phone(record) == _normalize_phone(phone):
        return "sms"
    return "email"


def _customer_summary(customer_id):
    entity = ledger.get_entity(customer_id) if customer_id else None
    if entity is None:
        return None
    a = entity.attributes
    def text(value, limit):
        return value if isinstance(value, str) and len(value) <= limit else None
    name = text(a.get("name"), 200) or " ".join(filter(None, [
        text(a.get("first_name"), 100), text(a.get("last_name"), 100)])) or customer_id
    return {"customer_id": customer_id, "name": name,
            "email": text(a.get("email"), 254), "phone": text(a.get("phone"), 32)}


# =====================================================================================
# Account entity helpers
# =====================================================================================

def _account_brief(entity, include_token=None):
    from core.customer_identity import resolve_linked_customer
    customer_id, _ = resolve_linked_customer(entity)
    a = entity.attributes
    brief = {
        "account_id": entity.id,
        "email": a.get("email"),
        "name": a.get("name"),
        "phone": a.get("phone"),
        "linked_customer_id": customer_id,
        "linked": bool(customer_id),
        "pending_link": bool(a.get("pending_link_customer_id")),
        "email_verified": bool(a.get("email_verified")),
        "phone_verified": bool(a.get("phone_verified")),
    }
    if customer_id:
        brief["customer"] = _customer_summary(customer_id)
    if include_token:
        brief["token"] = include_token
    return brief


def get_account(account_id):
    entity = ledger.get_entity(account_id)
    if entity is None or entity.entity_type != CUSTOMER_ACCOUNT:
        return None
    return entity


# =====================================================================================
# Public operations
# =====================================================================================

def _create_account(email, password, name=None, phone=None):
    """Persist an account and optional pending CRM link, without provider I/O.

    Called under the signup lock; the record is not attached until confirmation.
    """
    email_key = _normalize_email(email)
    if not email_key or "@" not in email_key:
        return {"error": "Enter a valid email address."}
    pw_error = validate_password_strength(password)
    if pw_error:
        return {"error": pw_error}
    if customer_credential_store.has_email(email_key):
        return {"error": "An account with this email already exists — try signing in."}

    match = _find_matching_customer(email_key, phone)

    entity = Entity(
        id=id_generator.generate("CACC"),
        entity_type=CUSTOMER_ACCOUNT,
        attributes={
            "email": email_key,
            "name": name or None,
            "phone": phone or None,
            "linked_customer_id": None,
            "pending_link_customer_id": match.id if match else None,
            "email_verified": False,
            "phone_verified": False,
            "status": "active",
            "challenges": {},
            "created_at": _now(),
        },
    )
    ledger.add_entity(entity)
    try:
        customer_credential_store.set_credential(email_key, entity.id, password)
        save_graph(GRAPH_PATH)
        _save_customer_credentials()
    except Exception:
        # Roll back only this creation, never unrelated accounts or the ID
        # high-water mark. Cross-file/uncertain-write recovery is separate.
        if ledger.get_entity(entity.id) is entity:
            ledger.get_all().pop(entity.id, None)
        credential = customer_credential_store.credentials.get(email_key)
        if isinstance(credential, dict) and credential.get("account_id") == entity.id:
            customer_credential_store.credentials.pop(email_key, None)
        raise
    audit_log.record(
        event_type="customer_account_created",
        summary=f"Customer account {entity.id} created for {email_key}",
        entity_id=entity.id, actor=CUSTOMER_SENTINEL,
        details={"match_found": bool(match)},
    )

    token = issue_customer_token(entity.id)
    result = {"account": _account_brief(entity, include_token=token), "match_found": bool(match)}
    return result


def sign_up(email, password, name=None, phone=None):
    """Create an account, then request proof on its matched CRM contact channel."""
    # One shared credential file: serialize duplicate checks and creation across
    # all emails in this process. This does not coordinate multiple workers.
    with _SIGNUP_LOCK:
        result = _create_account(email, password, name=name, phone=phone)
    if "error" in result:
        return result
    entity = get_account(result["account"]["account_id"])
    match = ledger.get_entity(entity.attributes.get("pending_link_customer_id"))

    if match:
        # Verify on the channel we matched on, delivered to the matched record's contact.
        channel = _matched_channel(match, email, phone)
        issued = _issue_code(entity, channel)
        result["channel"] = channel
        if issued.get("error"):
            result["verification_note"] = issued["error"]
        else:
            result["delivery"] = issued.get("delivery")
            if issued.get("dev_code"):
                result["dev_code"] = issued["dev_code"]
    return result


def log_in(email, password):
    # Do not issue a session from a signup's temporary in-memory state while its
    # initial persistence is still in flight. Same-process boundary only.
    with _SIGNUP_LOCK:
        account_id = customer_credential_store.authenticate(email, password)
        if not account_id:
            return {"error": "Incorrect email or password."}
        entity = get_account(account_id)
        if entity is None or entity.attributes.get("status") != "active":
            return {"error": "This account is no longer available."}
        token = issue_customer_token(account_id)
        return {"account": _account_brief(entity, include_token=token)}


def _customer_sms_destination(record):
    # Do not guess a country code from a locally formatted CRM number.
    for key in ("phone", "Phone", "phone_number", "mobile", "cell"):
        value = record.attributes.get(key)
        if value:
            return value.strip() if isinstance(value, str) and len(value) <= 32 else ""
    return ""


def _issue_code(entity, channel):
    with _challenge_lock(entity.id):
        return _issue_code_locked(entity, channel)


def _issue_code_locked(entity, channel):
    """Generate + (simulated) deliver a 6-digit link code. The recipient is the MATCHED
    record's contact on file (pending_link_customer_id) — NEVER the account's self-asserted
    email/phone, which is what let an attacker who knew a victim's phone/email be sent the
    code and take over that customer's record. Returns {delivery, dev_code?} or {error}."""
    from core.workflow_readiness import simulation_block
    pending = entity.attributes.get("pending_link_customer_id")
    record = ledger.get_entity(pending) if pending else None
    recipient = ""
    if record is not None:
        recipient = _customer_email(record) if channel == "email" else _customer_phone(record)
    if not recipient:
        # No verifiable contact on the matched record for this channel — can't prove ownership.
        return {"error": f"No {channel} on file for the matching record — try the other channel."}

    if channel == "email" and os.environ.get("NXTDEAL_CUSTOMER_EMAIL_PROVIDER") == "privateemail":
        from core.privateemail_verification import PrivateEmailConfig, PrivateEmailVerification, valid_address
        config = PrivateEmailConfig.from_environment()
        if config is None or not valid_address(recipient):
            return {"error": "Email verification is not configured or the contact is invalid."}
        now = int(time.time())
        previous = entity.attributes.get("challenges", {}).get(channel, {})
        if now - previous.get("requested_at", 0) < 60:
            return {"error": "Please wait before requesting another code."}
        from core.customer_delivery_limits import delivery_budget
        if not delivery_budget.reserve(channel, recipient):
            return {"error": "Verification request limit reached. Please try again later."}
        code = f"{secrets.randbelow(1000000):06d}"
        nonce = secrets.token_hex(16)
        previous_attributes = deepcopy(entity.attributes)
        entity.attributes.setdefault("challenges", {})[channel] = {
            "provider": "privateemail", "customer_id": pending, "recipient": recipient,
            "nonce": nonce, "code_digest": _email_code_digest(nonce, code),
            "requested_at": now, "expires_at": now + OTP_TTL_SECONDS,
            "attempts": 0, "consumed": False,
        }
        try:
            save_graph(GRAPH_PATH)
        except Exception:
            _restore_account_attributes(entity, previous_attributes)
            raise
        # Save before sending, so an uncertain SMTP acknowledgement still leaves
        # a usable challenge if the customer actually receives the message.
        return PrivateEmailVerification(config).send_code(recipient, code)

    if os.environ.get("NXTDEAL_CUSTOMER_SMS_PROVIDER") == "twilio_verify":
        if channel != "sms":
            return {"error": "Email verification is not configured. Request an SMS code."}
        from core.twilio_sms_verification import VerifyConfig, TwilioSmsVerification
        config = VerifyConfig.from_environment()
        if config is None:
            return {"error": "SMS verification is not configured."}
        previous = entity.attributes.get("challenges", {}).get(channel, {})
        now = int(time.time())
        if now - previous.get("requested_at", 0) < 60:
            return {"error": "Please wait before requesting another code."}
        recipient = _customer_sms_destination(record)
        from core.customer_delivery_limits import delivery_budget
        if not delivery_budget.reserve(channel, recipient):
            return {"error": "Verification request limit reached. Please try again later."}
        delivery = TwilioSmsVerification(config).start(recipient)
        if delivery.get("error"):
            return delivery
        reused = (previous.get("provider") == "twilio_verify" and
                  previous.get("verification_sid") == delivery["verification_sid"])
        if reused and (previous.get("customer_id") != pending or previous.get("recipient") != recipient):
            return {"error": "Verification response reused a changed contact. Try again after it expires."}
        # No OTP is retained locally. Bind the provider proof to the original
        # CRM record and contact; changing either requires a fresh challenge.
        previous_attributes = deepcopy(entity.attributes)
        challenge = {
            "provider": "twilio_verify", "verification_sid": delivery["verification_sid"],
            "customer_id": pending, "recipient": recipient, "requested_at": now,
            "expires_at": now + OTP_TTL_SECONDS, "attempts": 0, "consumed": False,
        }
        if reused:
            # A provider resend may reuse the same code/verification. It must not
            # buy more guesses, extend local expiry or revive consumed proof.
            challenge.update(expires_at=previous["expires_at"],
                             attempts=previous.get("attempts", 0),
                             consumed=previous.get("consumed", False))
        entity.attributes.setdefault("challenges", {})[channel] = challenge
        try:
            save_graph(GRAPH_PATH)
        except Exception:
            _restore_account_attributes(entity, previous_attributes)
            raise
        return {"delivery": "pending", "provider": "twilio_verify"}

    if not integrations_registry.is_live("notifications"):
        blocked = simulation_block("customer_verification")
        if blocked:
            return blocked
    code = f"{secrets.randbelow(1000000):06d}"
    challenges = entity.attributes.setdefault("challenges", {})
    challenges[channel] = {
        "code": code,
        "expires_at": int(time.time()) + OTP_TTL_SECONDS,
        "attempts": 0,
        "consumed": False,
    }
    save_graph(GRAPH_PATH)
    delivery = integrations_registry.send_notification(
        recipient,
        {"type": "customer_link_code", "code": code},
        channels=(channel,) if channel in ("email", "sms") else ("email",),
    )
    simulated = bool(delivery.get("simulated", True)) if isinstance(delivery, dict) else True
    delivered = isinstance(delivery, dict) and not delivery.get("error") and delivery.get("simulated") is False and (
        delivery.get("sent") is True or delivery.get("status") in ("sent", "delivered", "accepted", "queued")
    )
    challenges[channel]["delivery_confirmed"] = delivered
    save_graph(GRAPH_PATH)
    if not delivered:
        blocked = simulation_block("customer_verification")
        if blocked:
            return blocked
    # The code is delivered to the matched record's real contact; the caller never sees it
    # unless an operator explicitly opted in (see _expose_link_code). This is what makes the
    # "match + verify" a real ownership check rather than a formality.
    return {
        "delivery": "simulated" if simulated else "sent",
        "dev_code": code if (simulated and _expose_link_code()) else None,
    }


def _email_code_digest(nonce, code):
    return hmac.new(_customer_secret(), ("email-link:" + nonce + ":" + code).encode("utf-8"),
                    hashlib.sha256).hexdigest()


@_serialized_challenge
def request_link_code(account_id, channel="email", *, expected_session_version=None):
    entity = get_account(account_id)
    if entity is None:
        return {"error": "Account not found."}
    if (entity.attributes.get("status") != "active" or
            (expected_session_version is not None and
             expected_session_version != entity.attributes.get("session_version", 0))):
        return {"error": "Your session expired — sign in again."}
    if not entity.attributes.get("pending_link_customer_id"):
        return {"error": "There's no matching record to link — nothing to verify."}
    if channel not in ("email", "sms"):
        return {"error": "Choose email or sms."}
    issued = _issue_code(entity, channel)
    if issued.get("error"):
        return issued
    out = {"channel": channel, "delivery": issued.get("delivery")}
    if issued.get("dev_code"):
        out["dev_code"] = issued["dev_code"]
    return out


@_serialized_challenge
def confirm_link_code(account_id, channel, code, *, expected_session_version=None):
    """Confirm the code and, on success, attach the pending CRM record to the account."""
    entity = get_account(account_id)
    if entity is None:
        return {"error": "Account not found."}
    session_version = entity.attributes.get("session_version", 0)
    if (entity.attributes.get("status") != "active" or
            (expected_session_version is not None and expected_session_version != session_version)):
        return {"error": "Your session expired — sign in again."}
    pending = entity.attributes.get("pending_link_customer_id")
    if not pending:
        return {"error": "There's no matching record to link."}
    challenge = entity.attributes.get("challenges", {}).get(channel)
    if not challenge:
        return {"error": "Request a code first."}
    if challenge.get("provider") not in ("twilio_verify", "privateemail") and challenge.get("delivery_confirmed") is not True:
        from core.workflow_readiness import simulation_block
        blocked = simulation_block("customer_verification")
        if blocked:
            return blocked
    if challenge.get("consumed"):
        return {"error": "That code was already used — request a new one."}
    if challenge.get("expires_at", 0) < time.time():
        return {"error": "That code expired — request a new one."}
    if challenge.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
        return {"error": "Too many attempts — request a new code."}

    challenge["attempts"] = challenge.get("attempts", 0) + 1
    if challenge.get("provider") == "privateemail":
        record = ledger.get_entity(pending)
        if (channel != "email" or os.environ.get("NXTDEAL_CUSTOMER_EMAIL_PROVIDER") != "privateemail"
                or record is None or challenge.get("customer_id") != pending
                or challenge.get("recipient") != _customer_email(record)):
            return {"error": "The verification contact changed or is unavailable. Request a new code."}
        save_graph(GRAPH_PATH)
        if (not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit()
                or not hmac.compare_digest(_email_code_digest(challenge["nonce"], code),
                                           challenge.get("code_digest", ""))):
            return {"error": "That code could not be verified."}
    elif challenge.get("provider") == "twilio_verify":
        from core.twilio_sms_verification import VerifyConfig, TwilioSmsVerification
        config = VerifyConfig.from_environment()
        record = ledger.get_entity(pending)
        if (channel != "sms" or os.environ.get("NXTDEAL_CUSTOMER_SMS_PROVIDER") != "twilio_verify"
                or config is None or record is None or
                challenge.get("customer_id") != pending or
                challenge.get("recipient") != _customer_sms_destination(record)):
            return {"error": "The verification contact changed or is unavailable. Request a new code."}
        # Persist the attempt before any external check, including provider failures.
        save_graph(GRAPH_PATH)
        proof = TwilioSmsVerification(config).check(challenge.get("verification_sid"), code)
        if proof.get("error"):
            return proof
        if proof.get("verified") is not True:
            return {"error": "That code could not be verified."}
    else:
        if (os.environ.get("NXTDEAL_CUSTOMER_SMS_PROVIDER") == "twilio_verify" or
                os.environ.get("NXTDEAL_CUSTOMER_EMAIL_PROVIDER") == "privateemail"):
            return {"error": "Request a new provider verification code."}
        if str(code).strip() != challenge.get("code"):
            save_graph(GRAPH_PATH)
            remaining = OTP_MAX_ATTEMPTS - challenge["attempts"]
            return {"error": f"That code isn't right. {max(remaining, 0)} attempts left."}

    if entity.attributes.get("session_version", 0) != session_version:
        return {"error": "Your session expired — sign in again."}

    if challenge.get("provider") in ("twilio_verify", "privateemail"):
        # A CRM edit or clock advance can happen while a provider request is in
        # flight. Recheck before committing any authority or customer summary.
        current_record = ledger.get_entity(pending)
        provider_enabled = (
            os.environ.get("NXTDEAL_CUSTOMER_EMAIL_PROVIDER") == "privateemail"
            if channel == "email" else
            os.environ.get("NXTDEAL_CUSTOMER_SMS_PROVIDER") == "twilio_verify"
        )
        current_contact = ("" if current_record is None else
                           _customer_email(current_record) if channel == "email" else
                           _customer_sms_destination(current_record))
        if (not provider_enabled or entity.attributes.get("status") != "active" or
                entity.attributes.get("pending_link_customer_id") != pending or
                entity.attributes.get("challenges", {}).get(channel) is not challenge or
                challenge.get("recipient") != current_contact or
                challenge.get("expires_at", 0) <= time.time()):
            return {"error": "Verification changed or expired. Request a new code."}

    previous_attributes = deepcopy(entity.attributes)
    challenge["consumed"] = True
    entity.attributes["linked_customer_id"] = pending
    entity.attributes["pending_link_customer_id"] = None
    if challenge.get("provider") in ("twilio_verify", "privateemail"):
        entity.attributes["link_proof"] = {
            "provider": challenge["provider"], "channel": channel,
            "customer_id": pending, "recipient": challenge["recipient"],
            "verified_at": _now(),
        }
    if channel == "email":
        entity.attributes["email_verified"] = True
    else:
        entity.attributes["phone_verified"] = True
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        _restore_account_attributes(entity, previous_attributes)
        raise
    audit_log.record(
        event_type="customer_account_linked",
        summary=f"Customer account {entity.id} linked to {pending} via {channel} code",
        entity_id=entity.id, actor=CUSTOMER_SENTINEL,
        details={"customer_id": pending, "channel": channel},
    )
    return {"account": _account_brief(entity), "linked": True}


def me(account_id):
    entity = get_account(account_id)
    if entity is None:
        return {"error": "Account not found."}
    return {"account": _account_brief(entity)}


# =====================================================================================
# Persistence hook (thin wrapper so the storage module owns the path/atomic write)
# =====================================================================================

def _save_customer_credentials():
    # Imported lazily to avoid a circular import at module load.
    from core import customer_accounts_storage
    customer_accounts_storage.save_customer_credentials(
        customer_accounts_storage.CUSTOMER_CREDENTIALS_PATH()
    )
