"""
core/mfa.py -- Multi-factor authentication (TOTP, RFC 6238) for employee login.

Security-hardening pass (2026-07-20, per Sam's Tier 1 "MFA" requirement --
avoid SMS, prefer authenticator-app/security-key-class factors). This module
implements TOTP the same way core/auth.py implements session tokens: a
minimal, stdlib-only construction (hmac + base64 + struct) rather than a
third-party dependency (no `pyotp`), matching that module's own stated reason
("this repo has zero third-party auth deps today... not adding another
unverified dependency"). The algorithm is the real, standard one --
HMAC-SHA1-based HOTP (RFC 4226) stepped every 30 seconds (RFC 6238) -- so any
real authenticator app (Google Authenticator, Authy, 1Password, a hardware
TOTP token, etc.) works against it unmodified. SHA-1 is used here not because
it's cryptographically strong in general, but because it's the universal
default every real TOTP authenticator app expects; using SHA-256 would break
compatibility with the actual apps employees install. This is a lower-value
target for an attacker than password hashing (core/auth.py's PBKDF2 already
covers that) -- HOTP/TOTP's real security property is the shared secret plus
a 30-second validity window, not the choice of HMAC digest.

Pure/stateless only -- this module never touches core/auth.py's
CredentialStore or storage.  core/auth.py imports FROM here (its
CredentialStore gains the stateful enroll/verify/disable methods, calling
into these functions), never the reverse, so there's no import cycle and
core/auth.py's own "decoupled, stdlib-only" module boundary stays intact.

Recovery codes: 10 single-use codes generated at enrollment, shown exactly
once (same "plaintext only in this one response" discipline core/auth.py's
generate_temp_password()/core/api_keys.py's generate_api_key() already
established), hashed with the same SHA-256 convention core/api_keys.py uses
for key hashes (not PBKDF2 -- these are high-entropy random codes, not
human-chosen passwords, so a fast hash is fine and lets verification stay
cheap for something checked at every login).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1  # accept the current step +/- 1 (90s of real clock drift tolerance)

RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, avoids transcription errors


def generate_totp_secret(length_bytes=20):
    """A fresh, random base32-encoded shared secret -- 20 bytes (160 bits) is
    the RFC 4226-recommended minimum for HMAC-SHA1, matching what every real
    authenticator app expects."""

    raw = secrets.token_bytes(length_bytes)

    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(secret_b32, counter, digits=TOTP_DIGITS):
    """RFC 4226 HOTP -- truncated HMAC-SHA1 of a big-endian 8-byte counter,
    reduced to `digits` decimal digits."""

    # base32 requires padding back to a multiple of 8 chars before decoding.
    padded = secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded.upper())

    counter_bytes = struct.pack(">Q", counter)

    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()

    offset = digest[-1] & 0x0F
    truncated = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )

    return str(truncated % (10 ** digits)).zfill(digits)


def totp_now(secret_b32, for_time=None, step=TOTP_STEP_SECONDS, digits=TOTP_DIGITS):
    """The real, current TOTP code for this secret -- used by tests and by any
    future "show me the current code" debug path. Not exposed over the API
    (the server never needs to compute a code for display, only to verify
    one an employee's own authenticator app produced)."""

    if for_time is None:
        for_time = time.time()

    counter = int(for_time // step)

    return _hotp(secret_b32, counter, digits)


def verify_totp_code(secret_b32, code, for_time=None, step=TOTP_STEP_SECONDS,
                      digits=TOTP_DIGITS, window=TOTP_WINDOW):
    """True if `code` matches the real TOTP value for this secret at the
    current step, or any step within +/- `window` (real clock drift
    tolerance -- a phone's clock a few seconds off from the server's
    shouldn't lock someone out). Constant-time compare per candidate, same
    discipline core/auth.py's verify_password()/verify_token() already use
    for every other secret comparison in this codebase."""

    if not code or not code.isdigit():
        return False

    if for_time is None:
        for_time = time.time()

    current_counter = int(for_time // step)

    for offset in range(-window, window + 1):
        candidate = _hotp(secret_b32, current_counter + offset, digits)

        if hmac.compare_digest(candidate, code):
            return True

    return False


def build_otpauth_uri(secret_b32, account_name, issuer="NXTDeal"):
    """A standard `otpauth://totp/...` URI -- what a real authenticator app's
    QR-code scanner (or manual-entry flow) expects. This backend does not
    render a QR image itself; the frontend renders one client-side off this
    URI (this codebase's own established precedent -- session 113's PURL
    Platform used the npm `qrcode` package client-side for the identical
    reason: no native/image-rendering dependency needed on the Python side)."""

    label = urllib.parse.quote(f"{issuer}:{account_name}")

    params = urllib.parse.urlencode({
        "secret": secret_b32,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": str(TOTP_DIGITS),
        "period": str(TOTP_STEP_SECONDS),
    })

    return f"otpauth://totp/{label}?{params}"


def generate_recovery_codes(count=RECOVERY_CODE_COUNT):
    """Plaintext recovery codes -- shown exactly once, at enrollment. Format:
    XXXX-XXXX (8 real random characters from a transcription-safe alphabet,
    grouped for readability), matching the "not meant to be memorized, meant
    to be written down/stored securely" framing core/auth.py's
    generate_temp_password() already uses for temp passwords."""

    codes = []

    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")

    return codes


def _normalize_recovery_code(code):
    """Recovery codes are case-insensitive and dash-optional on entry --
    normalized before hashing/comparing so 'abcd-1234', 'ABCD1234', and
    'abcd 1234' all resolve to the same real code."""

    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def hash_recovery_code(code):
    """SHA-256 of the normalized code -- same fast-hash convention
    core/api_keys.py's _hash_key() uses for its own high-entropy random
    secrets (as opposed to core/auth.py's deliberately-slow PBKDF2 for
    human-chosen passwords, where slowness is the whole point)."""

    return hashlib.sha256(_normalize_recovery_code(code).encode("utf-8")).hexdigest()


def verify_and_consume_recovery_code(raw_code, hashed_codes):
    """Checks `raw_code` against the stored list of hashed, still-unused
    recovery codes. Returns (True, remaining_hashed_codes) with the matched
    code removed on success -- single-use, so a captured recovery code can't
    be replayed. Returns (False, hashed_codes) unchanged on no match."""

    if not raw_code or not hashed_codes:
        return False, hashed_codes

    target = hash_recovery_code(raw_code)

    for stored_hash in hashed_codes:
        if hmac.compare_digest(stored_hash, target):
            remaining = [h for h in hashed_codes if h != stored_hash]
            return True, remaining

    return False, hashed_codes
