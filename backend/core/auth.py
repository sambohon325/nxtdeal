"""
Phase 9 — Authentication core.

Design decision (confirmed with Sam 2026-07-12): build simple session-token auth
ourselves rather than an external identity provider.

Credentials are deliberately kept in their own store (core/storage.py: credentials.json),
NOT as attributes on Employee entities in the graph. Employee entities are free-form,
CSV-imported records (see imports/employee_import.py) that get serialized whole via
/entity/{id} and /search — password hashes must never end up in that blast radius.
An employee_id here is expected to match an EMPLOYEE entity's id in the graph, but this
module doesn't require the entity to exist (keeps auth decoupled/testable).

Tokens are a minimal stdlib-only signed-token scheme (hmac + base64, no external JWT
library — this repo has zero third-party auth deps today and requirements.txt is already
unverified against a real environment, so not adding another unverified dependency on top
of that). If Sam later wants real JWT (for interop with other services), swap
core.auth.issue_token/verify_token's internals — callers only depend on those two
functions, not the token format.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import time
from datetime import datetime, timedelta, timezone

from core.mfa import (
    generate_totp_secret,
    build_otpauth_uri,
    verify_totp_code,
    generate_recovery_codes,
    hash_recovery_code,
    verify_and_consume_recovery_code,
)
from core.secrets import get_secret

# Account lockout policy (Administration Control Center rebuild, "Security"
# item, continued). A real, honest, small policy -- 5 wrong passwords in a row
# locks the account for 15 minutes, reusing this same real login_failed signal
# core/audit.py has recorded since Phase 9. Not configurable per-employee (no
# ask for that granularity was made) -- one real, dealership-wide policy.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Minimal, real password policy (Administration Control Center rebuild) --
# enforced on self-service change_password() only; admin-issued temp passwords
# (generate_temp_password()) already exceed this by construction.
MIN_PASSWORD_LENGTH = 8


def validate_password_strength(password):
    """Returns None if the password passes, else a plain error string. A real,
    minimal policy: length + at least one letter + one digit -- not a
    fabricated "strength score," just a checkable rule."""

    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit."
    return None


# In a real deployment this MUST come from an environment variable
# (backend/.env is already gitignored) — never commit a real secret.
# Falling back to a fixed dev-only value so the module works out of the box locally.
# Reads through core/secrets.py's real chokepoint (Task #13, 2026-07-20) rather than
# os.environ directly, so a production deployment still running on this dev fallback
# is centrally, automatically detectable (core/secrets.get_secrets_posture()) instead
# of only discoverable by reading this module's own source.
_SECRET_ENV_VAR = "DEALEROS_AUTH_SECRET"
_DEV_FALLBACK_SECRET = "dev-only-insecure-secret-change-me"

TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 hours

# MFA challenge tokens (security-hardening pass, 2026-07-20) are issued after
# a correct password but BEFORE a real session token, when the employee has
# MFA enabled -- a short-lived, narrowly-scoped ticket that's only ever
# accepted by POST /auth/mfa/verify, never as a bearer token for any other
# route (api/deps.py's _authenticate() explicitly rejects any token carrying
# purpose="mfa_challenge"). 5 minutes is enough time to open an authenticator
# app and type a code, short enough that a leaked challenge token (e.g. from
# a proxy log, since this one travels in a request body rather than a header
# -- see POST /auth/mfa/verify) is a narrow window, not a standing risk.
MFA_CHALLENGE_TTL_SECONDS = 60 * 5


def _secret():

    return get_secret(_SECRET_ENV_VAR, _DEV_FALLBACK_SECRET).encode("utf-8")


def hash_password(password, salt=None):
    """Returns (salt_hex, hash_hex). Store both."""

    if salt is None:
        salt = os.urandom(16)

    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000
    )

    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, hash_hex):

    _, computed = hash_password(password, salt_hex)

    return hmac.compare_digest(computed, hash_hex)


_TEMP_PASSWORD_ALPHABET = (
    string.ascii_uppercase
    + string.ascii_lowercase
    + string.digits
)


def generate_temp_password(length=12):
    """A random, admin-distributable temp password — used for both the bulk CSV import
    and the one-by-one admin-add flow. Not meant to be memorized; the employee is expected
    to change it via change_password() on first login (see CredentialStore.set_credential's
    must_change_password flag, default True)."""

    return "".join(
        secrets.choice(_TEMP_PASSWORD_ALPHABET)
        for _ in range(length)
    )


def _credential_binding(employee_id, role):
    record = credential_store.get_record(employee_id)
    if not record or record.get("role") != role:
        raise ValueError("A current dealer credential is required")
    binding_fields = [record["salt"], record["hash"], record["role"], record.get("role_version", 0)]
    # Preserve existing sessions until an MFA change actually occurs. Never bind
    # to recovery-code contents: consuming a code must not revoke other sessions.
    if record.get("mfa_version", 0):
        binding_fields.append(record["mfa_version"])
    value = json.dumps(binding_fields, separators=(",", ":"))
    return hmac.new(_secret(), ("dealer-session-v1:" + value).encode(), hashlib.sha256).hexdigest()


def issue_token(employee_id, role, *, fresh_auth=False, mfa_authenticated=False):

    payload = {
        "employee_id": employee_id,
        "role": role,
        "credential_binding": _credential_binding(employee_id, role),
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + TOKEN_TTL_SECONDS
    }

    # Only completed interactive password/MFA login sets this proof. Other token
    # issuance (including password-change replacement) must not imply fresh login.
    if fresh_auth is True:
        payload["authenticated_at"] = int(time.time())
        if mfa_authenticated is True:
            payload["mfa_authenticated"] = True

    payload_bytes = json.dumps(payload).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")

    signature = hmac.new(
        _secret(),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"{payload_b64}.{signature}"


def verify_token(token):
    """Returns the payload dict if valid and unexpired, else None."""

    # Tokens emitted here are ASCII. Reject malformed headers before string HMAC
    # comparison, which raises TypeError for non-ASCII input.
    if not isinstance(token, str) or not token.isascii():
        return None

    try:
        payload_b64, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None

    expected_signature = hmac.new(
        _secret(),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(
            base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        )
    except (ValueError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("expires_at"), (int, float)):
        return None
    if not payload["expires_at"] >= time.time():
        return None
    if not isinstance(payload.get("employee_id"), str) or not isinstance(payload.get("role"), str):
        return None
    binding = payload.get("credential_binding")
    if not isinstance(binding, str) or not binding.isascii():
        return None
    try:
        current = _credential_binding(payload["employee_id"], payload["role"])
    except ValueError:
        return None
    if not hmac.compare_digest(binding, current):
        return None
    return payload


def issue_mfa_challenge_token(employee_id, role):
    """A real token, same signing mechanism as issue_token() (so verify_token()
    validates it identically -- no second signature scheme to maintain), but
    tagged purpose="mfa_challenge" and given a much shorter TTL
    (MFA_CHALLENGE_TTL_SECONDS, not TOKEN_TTL_SECONDS). Carries `role` too so
    core/auth_api.py's verify_mfa_login() can issue the real session token
    immediately on a correct code, without a second credential_store lookup."""

    payload = {
        "employee_id": employee_id,
        "role": role,
        "purpose": "mfa_challenge",
        "credential_binding": _credential_binding(employee_id, role),
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + MFA_CHALLENGE_TTL_SECONDS
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")

    signature = hmac.new(
        _secret(),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"{payload_b64}.{signature}"


def is_mfa_challenge_token(payload):
    """True if a verify_token()'d payload is an MFA challenge ticket rather
    than a real session token -- used by api/deps.py's _authenticate() to
    make sure a challenge token can never authenticate a normal API request,
    and by core/auth_api.py's verify_mfa_login() to make sure a REAL session
    token can't be replayed at the MFA-verify endpoint."""

    return bool(payload) and payload.get("purpose") == "mfa_challenge"


class CredentialStore:

    def __init__(self):
        self.credentials = {}
        # Secondary lookup, lowercased email -> employee_id, so login can accept either
        # (see resolve_identifier/authenticate below). Rebuilt from self.credentials on
        # load_credentials(), kept in sync by set_credential() — not persisted separately,
        # storage/credentials.json only stores self.credentials, each record's own "email"
        # field is enough to rebuild this on process start.
        self.email_index = {}

    def set_credential(
        self,
        employee_id,
        password,
        role,
        must_change_password=True,
        created_by=None,
        email=None
    ):
        """must_change_password defaults to True because the two ways credentials get
        created (imports/credential_import.py's bulk import, and the admin one-by-one
        POST /auth/admin/credentials endpoint) both hand the employee a system-generated
        temp password — they're expected to set their own via change_password() on first
        login. Existing tests that call this positionally (employee_id, password, role)
        keep working unchanged; the new behavior only applies going forward.

        `email` is optional (login-by-email support, added 2026-07-13 session 20) — if
        omitted on a re-set (e.g. an admin-forced password reset), the existing email on
        file is preserved, same pattern as created_at below."""

        salt_hex, hash_hex = hash_password(password)

        existing = self.credentials.get(employee_id, {})

        resolved_email = email if email is not None else existing.get("email")

        self.credentials[employee_id] = {
            "salt": salt_hex,
            "hash": hash_hex,
            "role": role,
            "must_change_password": must_change_password,
            "created_by": created_by,
            "created_at": existing.get(
                "created_at",
                datetime.now(timezone.utc).isoformat()
            ),
            "email": resolved_email,
            # Account lockout + IP allowlist state (Administration Control
            # Center rebuild, "Security" item) -- preserved across a re-set
            # (e.g. an admin password reset) same as created_at/email above,
            # rather than silently clearing an existing lockout or allowlist.
            "failed_attempts": existing.get("failed_attempts", 0),
            "locked_until": existing.get("locked_until"),
            "ip_allowlist": existing.get("ip_allowlist", []),
            # MFA state (security-hardening pass, 2026-07-20) -- preserved
            # across a re-set (e.g. an admin password reset) same as every
            # other field above; a forced password reset must never silently
            # turn MFA off.
            "mfa_enabled": existing.get("mfa_enabled", False),
            "mfa_version": existing.get("mfa_version", 0),
            "mfa_secret": existing.get("mfa_secret"),
            "mfa_pending_secret": existing.get("mfa_pending_secret"),
            "mfa_pending_started_at": existing.get("mfa_pending_started_at"),
            "mfa_pending_attempts": existing.get("mfa_pending_attempts", 0),
            "mfa_recovery_codes": existing.get("mfa_recovery_codes", [])
        }

        previous_email = existing.get("email")

        if previous_email and previous_email.lower() != (resolved_email or "").lower():
            self.email_index.pop(previous_email.lower(), None)

        if resolved_email:
            self.email_index[resolved_email.lower()] = employee_id

    def resolve_identifier(self, identifier):
        """Login-by-email support (2026-07-13 session 20): `identifier` may be an
        employee_id or an email address. Returns the employee_id to authenticate against.
        If `identifier` doesn't match either an employee_id or a known email, it's
        returned unchanged — authenticate()/get_record() will then correctly miss, same
        as looking up any unknown employee_id today."""

        if identifier in self.credentials:
            return identifier

        return self.email_index.get(
            identifier.strip().lower(),
            identifier
        )

    def authenticate(self, identifier, password):
        """Returns the role string on success, None on failure. `identifier` may be an
        employee_id or an email address (see resolve_identifier)."""

        employee_id = self.resolve_identifier(identifier)

        record = self.credentials.get(employee_id)

        if not record:
            return None

        if not verify_password(password, record["salt"], record["hash"]):
            return None

        return record["role"]

    def get_lockout_status(self, employee_id):
        """Real, computed lockout state -- `locked_until` is only ever a
        stored timestamp, "currently locked" is always computed against the
        real clock at call time, not a stale stored boolean."""

        record = self.credentials.get(employee_id)
        if not record:
            return {"locked": False, "locked_until": None, "failed_attempts": 0}

        locked_until = record.get("locked_until")
        is_locked = bool(locked_until) and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc)

        return {
            "locked": is_locked,
            "locked_until": locked_until if is_locked else None,
            "failed_attempts": record.get("failed_attempts", 0),
        }

    def is_locked(self, employee_id):
        return self.get_lockout_status(employee_id)["locked"]

    def record_failed_login(self, employee_id):
        """Increments the real failed-attempt counter for a login attempt
        (called from core/auth_api.py's login(), NOT from authenticate()
        itself -- change_password()'s own old-password check also calls
        authenticate() and a wrong old-password there shouldn't count toward
        login lockout, a genuinely different action). Locks the account for
        MAX_FAILED_ATTEMPTS_MINUTES once MAX_FAILED_ATTEMPTS is reached."""

        record = self.credentials.get(employee_id)
        if not record:
            return

        record["failed_attempts"] = record.get("failed_attempts", 0) + 1

        if record["failed_attempts"] >= MAX_FAILED_ATTEMPTS:
            record["locked_until"] = (
                datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            ).isoformat()

    def record_successful_login(self, employee_id):
        record = self.credentials.get(employee_id)
        if not record:
            return

        record["failed_attempts"] = 0
        record["locked_until"] = None

    def unlock(self, employee_id):
        """Real admin action -- clears a lockout early rather than waiting out
        LOCKOUT_MINUTES."""

        record = self.credentials.get(employee_id)
        if not record:
            return False

        record["failed_attempts"] = 0
        record["locked_until"] = None
        return True

    def set_ip_allowlist(self, employee_id, ip_list):
        """An empty list means unrestricted (the default for every existing
        credential) -- a real, per-employee allowlist an admin can optionally
        turn on, not a platform-wide gate."""

        record = self.credentials.get(employee_id)
        if not record:
            return False

        record["ip_allowlist"] = list(ip_list or [])
        return True

    def check_ip_allowed(self, employee_id, client_ip):
        """True if unrestricted (empty allowlist) or the real allowlist
        contains this exact client IP. No CIDR/wildcard matching -- a plain,
        honest exact-match allowlist, not a fabricated more-sophisticated
        rule this codebase has no real network topology to justify."""

        record = self.credentials.get(employee_id)
        if not record:
            return True

        allowlist = record.get("ip_allowlist") or []
        if not allowlist:
            return True

        return client_ip in allowlist

    def is_mfa_enabled(self, employee_id):

        record = self.credentials.get(employee_id)
        return bool(record and record.get("mfa_enabled"))

    def mfa_recovery_codes_remaining(self, employee_id):

        record = self.credentials.get(employee_id)
        return len(record.get("mfa_recovery_codes") or []) if record else 0

    def begin_mfa_enrollment(self, employee_id):
        """Generates a fresh TOTP secret and stores it as `mfa_pending_secret`
        -- NOT yet enabled. Enrollment only takes effect once
        confirm_mfa_enrollment() is called with a real code produced by that
        secret, proving the employee's authenticator app actually has it
        (protects against enrolling a secret the employee never successfully
        scanned/entered, which would otherwise lock them out on their very
        next login). Calling this again before confirming discards the
        previous pending secret and starts over -- no harm, since it was
        never activated."""

        record = self.credentials.get(employee_id)
        if not record:
            return {"error": f"No credential exists for {employee_id}"}

        if record.get("mfa_enabled"):
            return {"error": "MFA is already enabled. Use the existing recovery process before enrolling a replacement authenticator."}

        secret = generate_totp_secret()
        record["mfa_pending_secret"] = secret
        record["mfa_pending_started_at"] = time.time()
        record["mfa_pending_attempts"] = 0

        return {
            "secret": secret,
            "otpauth_uri": build_otpauth_uri(secret, employee_id),
            "expires_in_seconds": 600,
        }

    def confirm_mfa_enrollment(self, employee_id, code):
        """Verifies `code` against the pending secret from
        begin_mfa_enrollment(); on success, activates MFA for real
        (mfa_enabled=True, mfa_secret=the now-confirmed secret) and issues a
        fresh set of recovery codes -- returned in plaintext exactly once,
        only their hashes are ever stored (same discipline every other
        one-time-secret in this codebase follows)."""

        record = self.credentials.get(employee_id)
        if not record:
            return {"error": f"No credential exists for {employee_id}"}

        # Also reject pending secrets retained by older versions or a competing
        # enrollment: a session alone cannot replace an active second factor.
        if record.get("mfa_enabled"):
            return {"error": "MFA is already enabled. An active authenticator cannot be replaced through enrollment."}

        pending = record.get("mfa_pending_secret")
        if not pending:
            return {"error": "No MFA enrollment in progress -- call begin_mfa_enrollment first"}

        started = record.get("mfa_pending_started_at")
        attempts = record.get("mfa_pending_attempts", 0)
        if (type(started) not in (int, float) or not 0 <= time.time() - started < 600
                or type(attempts) is not int or not 0 <= attempts < 5):
            record["mfa_pending_secret"] = None
            record["mfa_pending_started_at"] = None
            record["mfa_pending_attempts"] = 0
            return {"error": "MFA setup expired or reached its attempt limit. Start enrollment again."}

        if not verify_totp_code(pending, code):
            record["mfa_pending_attempts"] = attempts + 1
            if attempts + 1 >= 5:
                record["mfa_pending_secret"] = None
                record["mfa_pending_started_at"] = None
            return {"error": "Invalid authentication code"}

        recovery_codes = generate_recovery_codes()

        record["mfa_secret"] = pending
        record["mfa_pending_secret"] = None
        record["mfa_pending_started_at"] = None
        record["mfa_pending_attempts"] = 0
        record["mfa_enabled"] = True
        record["mfa_version"] = record.get("mfa_version", 0) + 1
        record["mfa_recovery_codes"] = [hash_recovery_code(c) for c in recovery_codes]

        return {
            "success": True,
            "reauthentication_required": True,
            "recovery_codes": recovery_codes,
        }

    def disable_mfa(self, employee_id):
        """Turns MFA off and clears every MFA-related field -- a genuinely
        fresh enrollment is required to turn it back on (no secret/recovery
        state survives a disable). Returns False if no credential exists."""

        record = self.credentials.get(employee_id)
        if not record:
            return False

        if record.get("mfa_enabled") or record.get("mfa_secret") or record.get("mfa_pending_secret"):
            record["mfa_version"] = record.get("mfa_version", 0) + 1
        record["mfa_enabled"] = False
        record["mfa_secret"] = None
        record["mfa_pending_secret"] = None
        record["mfa_pending_started_at"] = None
        record["mfa_pending_attempts"] = 0
        record["mfa_recovery_codes"] = []

        return True

    def verify_mfa_code(self, employee_id, code):
        """Checks `code` against the employee's real, active TOTP secret
        first; if that fails, tries it as a single-use recovery code.
        Returns (True, "totp"), (True, "recovery"), or (False, None). A
        matched recovery code is consumed (removed from the stored list) as
        a side effect of this call -- callers that get (True, "recovery")
        back are responsible for persisting the store afterward (same
        "mutate now, caller saves" convention every other mutating method on
        this class already follows -- see core/auth_api.py's callers)."""

        record = self.credentials.get(employee_id)
        if not record or not record.get("mfa_enabled"):
            return False, None

        secret = record.get("mfa_secret")
        if secret and verify_totp_code(secret, code):
            return True, "totp"

        ok, remaining = verify_and_consume_recovery_code(
            code, record.get("mfa_recovery_codes") or []
        )

        if ok:
            record["mfa_recovery_codes"] = remaining
            return True, "recovery"

        return False, None

    def get_record(self, employee_id):
        """Full credential record (minus nothing — callers that need to keep secrets out
        of API responses are responsible for not echoing salt/hash back). Returns None if
        the employee has no credential."""

        return self.credentials.get(employee_id)

    def change_password(self, employee_id, old_password, new_password):
        """Verifies old_password first — this method is for a logged-in user changing
        their own password, not an admin reset. Returns True on success, False if the
        employee doesn't exist or old_password is wrong. Clears must_change_password."""

        if self.authenticate(employee_id, old_password) is None:
            return False

        record = self.credentials[employee_id]

        self.set_credential(
            employee_id,
            new_password,
            record["role"],
            must_change_password=False,
            created_by=record.get("created_by")
        )

        return True

    def set_role(self, employee_id, role):
        """Reassign a role without touching the password (admin role-change flow, Bumper
        parity 2026-07-25). Returns True on success, False if the employee has no
        credential. The caller is responsible for validating `role` and persisting."""

        record = self.credentials.get(employee_id)
        if not record:
            return False
        if record["role"] != role:
            # A later promotion back to the former role must not revive tokens
            # revoked by this transition. Persisted with the credential record.
            record["role_version"] = record.get("role_version", 0) + 1
            record["role"] = role
        return True

    def list_records(self):
        """Every credential record, sorted by employee_id for stable output — salt/hash
        deliberately excluded (password data must never leave this module, same rule
        get_record()'s docstring calls out for its callers). Backs the admin roster view
        (core/auth_api.py's list_credentials()) — see BUILD_QUEUE.md's "Employee
        Directory / Admin Roster View" entry."""

        return [
            {
                "employee_id": employee_id,
                "role": record["role"],
                "must_change_password": record.get("must_change_password", False),
                "created_by": record.get("created_by"),
                "created_at": record.get("created_at"),
                "email": record.get("email"),
                "mfa_enabled": bool(record.get("mfa_enabled")),
            }
            for employee_id, record in sorted(self.credentials.items())
        ]

    def load_credentials(self, credentials):
        self.credentials = dict(credentials)

        self.email_index = {}

        for employee_id, record in self.credentials.items():

            email = record.get("email")

            if email:
                self.email_index[email.lower()] = employee_id

    def reset(self):
        """Clear all credentials in place (used by tests). Does not touch disk."""

        self.credentials = {}
        self.email_index = {}


credential_store = CredentialStore()
