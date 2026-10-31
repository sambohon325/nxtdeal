"""
Vendored copy of backend/core/auth.py's password-hashing primitives (session 87).

Why this duplicates code instead of importing across directories: hub/hub_core/provisioning.py
originally reached into backend/core/auth.py at runtime via a sys.path shim (see git
history / hub/tests/test_hub_provisioning.py's older docstring), which works fine locally
where both hub/ and backend/ sit side by side on disk. It does NOT work once hub/ is
deployed as its own isolated Coolify app with Base Directory `hub/` -- Nixpacks/Coolify's
monorepo build only packages the contents of that one subdirectory into the image, so the
sibling backend/ directory this shim depended on simply isn't present in the built
container at runtime, crashing hub/app.py on startup (`ModuleNotFoundError: No module
named 'hub_core.auth'` -- confirmed as the live cause of hub.dealeros.xyz's crash loop when
first deployed for real). Since hub_core/auth.py is entirely stdlib (no third-party deps), the
safe fix is a straight copy rather than restructuring Coolify's build to somehow span two
directories.

Password-hashing primitives remain compatible with backend/core/auth.py. Hub
session tokens now additionally bind to the current Hub credential; this is an
intentional Hub-only extension and does not change tenant credential provisioning.
If the password-hashing scheme,
token format, or CredentialStore's interface ever changes there, mirror the change here
too -- hub/hub_core/provisioning.py's create_dealer()/adopt_dealer() call generate_temp_password()
and hash a tenant's first ADMIN credential with these exact primitives so a freshly
provisioned dealer's own running instance (using the real backend/core/auth.py) can verify
logins against it. A mismatch here would silently produce credentials the dealer's own
backend can't authenticate.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import time
from datetime import datetime, timezone

from hub_core.secrets import get_secret


# In a real deployment this MUST come from an environment variable
# (backend/.env is already gitignored) — never commit a real secret.
# Falling back to a fixed dev-only value so the module works out of the box locally.
# Reads through hub_core/secrets.py's real chokepoint (Task #13, 2026-07-20) rather
# than os.environ directly -- still entirely stdlib/same-package, so this doesn't
# reintroduce the cross-directory import this whole file exists to avoid.
_SECRET_ENV_VAR = "DEALEROS_AUTH_SECRET"
_DEV_FALLBACK_SECRET = "dev-only-insecure-secret-change-me"

TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 hours


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


def _credential_binding(record):
    # Keyed digest binds sessions to current credentials without exposing password
    # hashes in a readable token. Rotating salt/hash or role revokes old sessions.
    value = json.dumps([record['salt'], record['hash'], record['role']], separators=(',', ':'))
    return hmac.new(_secret(), ('hub-session-v1:' + value).encode(), hashlib.sha256).hexdigest()


def issue_token(employee_id, role):

    record = credential_store.get_record(employee_id)
    if not record or record.get('role') != role:
        raise ValueError('A current Hub credential is required')
    payload = {
        "credential_binding": _credential_binding(record),
        "employee_id": employee_id,
        "role": role,
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + TOKEN_TTL_SECONDS
    }

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

    if not isinstance(payload, dict) or not isinstance(payload.get('expires_at'), (int, float)):
        return None
    if payload['expires_at'] < time.time():
        return None
    if not isinstance(payload.get('employee_id'), str) or not isinstance(payload.get('role'), str):
        return None
    record = credential_store.get_record(payload['employee_id'])
    binding = payload.get('credential_binding')
    if (not record or record.get('role') != payload.get('role')
            or not isinstance(binding, str) or not binding.isascii()
            or not hmac.compare_digest(binding, _credential_binding(record))):
        return None
    return payload


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
            "email": resolved_email
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

    def list_records(self):
        """Every credential record, sorted by employee_id for stable output — salt/hash
        deliberately excluded (password data must never leave this module, same rule
        get_record()'s docstring calls out for its callers). Backs the admin roster view
        (hub_core/auth_api.py's list_credentials()) — see BUILD_QUEUE.md's "Employee
        Directory / Admin Roster View" entry."""

        return [
            {
                "employee_id": employee_id,
                "role": record["role"],
                "must_change_password": record.get("must_change_password", False),
                "created_by": record.get("created_by"),
                "created_at": record.get("created_at"),
                "email": record.get("email"),
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
