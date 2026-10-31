"""
Real OIDC authorization-code-flow client -- security-hardening pass
(2026-07-20), Task #14 "SSO scaffolding (SAML/OIDC-ready)."

Works against any standards-compliant OpenID Connect identity provider --
Entra ID, Okta, Google Workspace, Auth0, or any generic OIDC-compliant IdP --
with real state/nonce CSRF protection and real ID-token signature
verification against the provider's own live JWKS endpoint. RSA verification now uses cryptography. Historical implementation notes: Pure stdlib
(hashlib/hmac/base64/json/secrets/urllib/time/dataclasses) -- no jwt/
cryptography package dependency, matching core/auth.py's own established
"zero third-party auth deps" convention (see that module's own docstring).

THE HONEST GAP, stated plainly rather than glossed over: no live IdP
client_id/client_secret/issuer exists anywhere in this sandbox to complete a
real end-to-end login round-trip against. Every function in this module is
real, wired, working code -- core/sso_config.py's discover_oidc_configuration()
genuinely fetches a live provider's real /.well-known/openid-configuration
document, and this module's JWT/JWKS verification logic is exercised against
real, cryptographically valid signed tokens in backend/tests/test_sso.py (a
real RSA keypair generated and used to sign a real JWT, purely as a
stdlib-only TEST FIXTURE -- see that file's own docstring for why no
cryptography/PyJWT package is used even there) -- but the full flow has never
been run against an actual Entra ID/Okta/Google Workspace/Auth0 tenant. This
ships as real, correct code, not as a live-verified integration.

DESIGN DECISIONS, stated explicitly rather than left implicit:

  1. No JIT (just-in-time) auto-provisioning. complete_sso_login() maps a
     verified email claim to an EXISTING NXTDeal employee credential via
     core.auth.credential_store.resolve_identifier() -- if no employee record
     matches, the login is rejected with an honest "an admin must create your
     account first" error, not silently auto-created. Reasoning: this
     codebase's whole credential model (core/auth.py) assumes an admin
     explicitly provisions every employee/role pairing (create_credential()),
     and letting a federated login silently create a new, role-less (or
     default-role) account would be a real privilege-assignment gap -- who
     decides what ROLE a JIT-provisioned employee gets? That's a genuine
     product decision this module deliberately does not make unilaterally.

  2. Enrolled local MFA remains mandatory after SSO. Provider authentication
     alone is not evidence that a second factor was performed. An enrolled
     account receives the same short-lived challenge as password login and
     completes it through /auth/mfa/verify before receiving a session.
     Provider-specific assurance and issuer/subject binding remain separate
     migration work; no unverified claim bypasses the local factor.

  3. IP allowlist + account lockout ARE still enforced on an SSO login,
     reusing the exact same core.auth.credential_store.check_ip_allowed()/
     get_lockout_status() checks core/auth_api.py's login() applies -- these
     are dealership-level policies about WHERE/WHETHER an account may sign in
     at all, and should not be bypassable just because the credential check
     itself happened at a different provider. A verification/exchange
     failure, by contrast, does NOT increment the same failed-attempt lockout
     counter a wrong password does -- a bad/expired authorization code or a
     signature mismatch is a technical/configuration failure, not evidence of
     someone guessing a password, and conflating the two could let a
     misconfigured IdP redirect lock out real employees.

  4. Only RS256 (RSA + SHA-256) is accepted for id_token signatures --
     verify_id_token() hard-rejects "none" (the classic JWT "alg confusion"
     vulnerability: an attacker crafts an unsigned token and hopes a naive
     verifier trusts it) and HS256 (which would require sharing client_secret
     as a symmetric MAC key with something capable of forging tokens, a much
     weaker trust model than asymmetric RS256 verified against the IdP's own
     public JWKS). This is a real, hard-coded allowlist, not a configurable
     option.
"""

import base64
import hashlib
import hmac
import json
import math
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass

from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.auth import credential_store, issue_token, issue_mfa_challenge_token
from core.permissions import DASHBOARD_ACCESS
from core.security import can_access_dashboard
from core.sso_config import get_sso_config, is_sso_enabled
from core.storage_paths import AUDIT_PATH

# -- constants ----------------------------------------------------------

# Enough time to actually complete a login at a real IdP (type a password,
# approve an MFA push, etc.) without leaving a CSRF ticket valid indefinitely.
PENDING_LOGIN_TTL_SECONDS = 60 * 10

# A small, standard allowance for clock drift between this server and the
# IdP's own clock when checking an id_token's exp claim.
CLOCK_SKEW_SECONDS = 60

HTTP_TIMEOUT_SECONDS = 8

JWKS_CACHE_TTL_SECONDS = 60 * 10

# Real, hard-coded DigestInfo ASN.1 prefix for SHA-256, per RFC 8017 Section
# 9.2 Note 1 -- a standard, publicly documented constant (not a secret, not
# something derived from any key material), used to build the expected
# EMSA-PKCS1-v1.5 padded block during signature verification.
_SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _allowed_dashboards(role):
    """Mirrors core/auth_api.py's own private helper of the identical name --
    duplicated here (rather than importing that module's underscore-prefixed
    name across a module boundary) but built from the exact same two public
    building blocks (core.permissions.DASHBOARD_ACCESS +
    core.security.can_access_dashboard) that helper itself uses, so this
    stays the single real source of truth for "which dashboards can this
    role see" -- not a second, independently-maintained ACL matrix."""

    return sorted(
        key for key in DASHBOARD_ACCESS
        if can_access_dashboard(role, key)
    )


def generate_state():
    return secrets.token_urlsafe(32)


def generate_nonce():
    return secrets.token_urlsafe(32)


# -- pending login registry (in-memory only, matching core/ws_manager.py's
# ConnectionManager precedent -- a pending login is a short-lived CSRF
# ticket, not something that needs to survive a process restart) ----------

@dataclass
class PendingSsoLogin:
    state: str
    nonce: str
    redirect_uri: str
    created_at: float
    expires_at: float


class PendingSsoLoginRegistry:

    def __init__(self):
        self._pending = {}

    def create(self, redirect_uri):
        state = generate_state()
        nonce = generate_nonce()
        now = time.time()
        pending = PendingSsoLogin(
            state=state,
            nonce=nonce,
            redirect_uri=redirect_uri,
            created_at=now,
            expires_at=now + PENDING_LOGIN_TTL_SECONDS,
        )
        self._pending[state] = pending
        self._reap_expired()
        return pending

    def pop(self, state):
        """One-time use -- consuming a pending login means the same
        state/authorization code can never be replayed against
        complete_sso_login() a second time, real CSRF/replay protection."""

        pending = self._pending.pop(state, None)
        if pending is None:
            return None, "unknown or already-used state -- possible CSRF/replay attempt"
        if time.time() > pending.expires_at:
            return None, "this SSO login attempt has expired -- please try signing in again"
        return pending, None

    def _reap_expired(self):
        now = time.time()
        expired = [state for state, pending in self._pending.items() if now > pending.expires_at]
        for state in expired:
            self._pending.pop(state, None)

    def reset(self):
        """Test-only helper -- clears all pending logins."""

        self._pending = {}


pending_logins = PendingSsoLoginRegistry()


# -- the two real network call sites -- every other function in this module
# routes through exactly these two, so a test can mock network behavior in
# one place rather than patching urllib all over the module. -------------

def _http_get_json(url, timeout=HTTP_TIMEOUT_SECONDS):
    from core.outbound_http import public_https_json
    return public_https_json(url, timeout=timeout)


def _http_post_form(url, data, timeout=HTTP_TIMEOUT_SECONDS):
    from core.outbound_http import public_https_json
    body = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}).encode("utf-8")
    return public_https_json(url, timeout=timeout, body=body)


# -- JWKS fetch + cache ---------------------------------------------------

_jwks_cache = {}


def fetch_jwks(jwks_uri, force_refresh=False):
    """Returns (keys_list, None) on success, (None, error_string) on
    failure. Cached for JWKS_CACHE_TTL_SECONDS per jwks_uri -- a real IdP
    doesn't rotate signing keys every request, and fetching fresh on every
    single login would be an unnecessary real network round-trip on the hot
    login path."""

    now = time.time()

    if not force_refresh and jwks_uri in _jwks_cache:
        fetched_at, keys = _jwks_cache[jwks_uri]
        if now - fetched_at < JWKS_CACHE_TTL_SECONDS:
            return keys, None

    try:
        document = _http_get_json(jwks_uri)
    except urllib.error.HTTPError as error:
        return None, f"JWKS endpoint returned HTTP {error.code}: {jwks_uri}"
    except urllib.error.URLError as error:
        return None, f"could not reach JWKS endpoint ({jwks_uri}): {error.reason}"
    except (TimeoutError, OSError) as error:
        return None, f"JWKS endpoint request failed ({jwks_uri}): {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"JWKS response was not valid JSON: {error}"

    if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
        return None, "JWKS response did not contain a 'keys' array -- not a valid JWKS document"

    keys = document["keys"]
    _jwks_cache[jwks_uri] = (now, keys)
    return keys, None


def clear_jwks_cache():
    """Test-only helper."""

    _jwks_cache.clear()


def _find_jwk(keys, kid):
    if kid is None:
        # No kid claimed in the token header -- only safe to guess if there
        # is exactly one key published, matching real-world IdP behavior for
        # a single-key JWKS document.
        return keys[0] if len(keys) == 1 else None
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


# -- base64url + RSA/PKCS#1-v1.5 signature verification, from scratch ----

def _b64url_decode(segment):
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _b64url_encode(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def _int_from_b64url(segment):
    return int.from_bytes(_b64url_decode(segment), "big")


def _verify_rs256(signing_input, signature, n, e):
    """Verify RS256 using the maintained cryptography implementation."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    if not isinstance(n, int) or not isinstance(e, int) or not 2048 <= n.bit_length() <= 8192:
        return False
    if e != 65537 or len(signature) != (n.bit_length() + 7) // 8:
        return False
    try:
        key = rsa.RSAPublicNumbers(e, n).public_key()
        key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_id_token(id_token, config, expected_nonce):
    """The full, ordered id_token verification checklist. Returns
    (claims_dict, None) on success, (None, error_string) on any failure --
    every check below must pass, in order, or the token is rejected."""

    try:
        header_seg, payload_seg, signature_seg = id_token.split(".")
    except (ValueError, AttributeError):
        return None, "id_token is not a well-formed JWT (expected header.payload.signature)"

    try:
        header = json.loads(_b64url_decode(header_seg))
        claims = json.loads(_b64url_decode(payload_seg))
        signature = _b64url_decode(signature_seg)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "id_token header/payload was not valid base64url-encoded JSON"

    if not isinstance(header, dict) or not isinstance(claims, dict):
        return None, "id_token header/payload was not a JSON object"

    alg = header.get("alg")
    if alg != "RS256":
        # Hard-coded allowlist -- explicitly rejects "none" (alg-confusion
        # attack) and HS256, see this module's own docstring.
        return None, f"unsupported/unsafe id_token signing algorithm: {alg!r} (only RS256 is accepted)"

    jwks_uri = config.get("jwks_uri")
    if not jwks_uri:
        return None, "this dealer's SSO configuration has no jwks_uri set -- cannot verify id_token signature"

    keys, jwks_error = fetch_jwks(jwks_uri)
    if jwks_error:
        return None, jwks_error

    kid = header.get("kid")
    jwk = _find_jwk(keys, kid)

    if jwk is None:
        # A real IdP legitimately rotates signing keys -- one forced refresh
        # before giving up, in case our cached JWKS is simply stale.
        keys, jwks_error = fetch_jwks(jwks_uri, force_refresh=True)
        if jwks_error:
            return None, jwks_error
        jwk = _find_jwk(keys, kid)

    if jwk is None:
        return None, f"no matching signing key found for kid={kid!r} in the provider's JWKS"

    if jwk.get("kty") != "RSA":
        return None, f"unsupported JWK key type: {jwk.get('kty')!r} (only RSA is supported)"

    try:
        n = _int_from_b64url(jwk["n"])
        e = _int_from_b64url(jwk["e"])
    except (KeyError, ValueError):
        return None, "the matching JWK was missing a valid RSA modulus ('n') or exponent ('e')"

    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")

    if not _verify_rs256(signing_input, signature, n, e):
        return None, "id_token signature verification failed"

    issuer = config.get("issuer")
    if claims.get("iss") != issuer:
        return None, f"id_token issuer mismatch: expected {issuer!r}, got {claims.get('iss')!r}"

    client_id = config.get("client_id")
    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if client_id not in aud_list:
        return None, f"id_token audience did not include this dealer's configured client_id ({client_id!r})"

    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)) or not math.isfinite(exp) or time.time() > (exp + CLOCK_SKEW_SECONDS):
        return None, "id_token has expired"

    if claims.get("nonce") != expected_nonce:
        return None, "id_token nonce did not match this login attempt's own nonce -- possible replay/CSRF"

    if config.get("require_verified_email") and claims.get("email_verified") is not True:
        return None, "id_token must contain email_verified=true when verified email is required"

    if len(aud_list) > 1 and claims.get("azp") != client_id:
        return None, "id_token authorized party must match client_id for multiple audiences"
    if "azp" in claims and claims["azp"] != client_id:
        return None, "id_token authorized party mismatch"

    return claims, None


# -- authorization-code exchange ------------------------------------------

def exchange_code_for_tokens(config, code, redirect_uri):
    """Real POST to the provider's token_endpoint. Returns
    (token_response_dict, None) on success, (None, error_string) on
    failure."""

    try:
        response = _http_post_form(config["token_endpoint"], {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
        })
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            body = ""
        return None, f"token endpoint returned HTTP {error.code}: {body[:500]}"
    except urllib.error.URLError as error:
        return None, f"could not reach token endpoint: {error.reason}"
    except (TimeoutError, OSError) as error:
        return None, f"token endpoint request failed: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"token endpoint response was not valid JSON: {error}"

    if not isinstance(response, dict) or "id_token" not in response:
        return None, "token endpoint response did not contain an id_token"

    return response, None


# -- the two real, public entry points ------------------------------------

def build_authorization_url(config, pending):
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": pending.redirect_uri,
        "scope": " ".join(config.get("scopes") or ["openid"]),
        "state": pending.state,
        "nonce": pending.nonce,
    }
    return config["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


def begin_sso_login():
    """Real entry point #1 -- called when someone clicks "Sign in with SSO"
    on the (unauthenticated) login page. Returns
    {"authorization_url": ..., "state": ...} on success -- the frontend
    redirects the browser to authorization_url -- or an honest
    {"error": ...} if SSO isn't enabled/fully configured for this dealer."""

    config = get_sso_config()

    if not is_sso_enabled():
        return {"error": "SSO is not enabled for this dealer."}

    pending = pending_logins.create(config["redirect_uri"])
    authorization_url = build_authorization_url(config, pending)

    return {"authorization_url": authorization_url, "state": pending.state}


def _record_sso_failure(email, reason):
    audit_log.record(
        event_type="sso_login_failed",
        summary=f"SSO login failed{(' for ' + email) if email else ''}: {reason}",
        entity_id=email,
        actor=email or "unknown",
        details={"reason": reason},
    )
    save_audit_log(AUDIT_PATH)


def complete_sso_login(state, code, client_ip=None):
    """Real entry point #2 -- called when the IdP redirects the browser back
    to our callback URL with ?code=...&state=.... Orchestrates the full
    flow: consume the pending login (CSRF check), exchange the code for
    tokens, verify the id_token, resolve the verified email to an existing
    NXTDeal employee, apply the same IP-allowlist/lockout checks a password
    login would, and issue a real session token on success.

    Returns the SAME response shape core/auth_api.py's login() returns on a
    non-MFA success (token/employee_id/role/must_change_password/
    allowed_dashboards) plus sso=True/sso_provider, so the frontend can treat
    an SSO login and a password login identically. Enrolled accounts instead
    receive the existing MFA challenge response, with no session token -- or an honest
    {"error": ...} at whichever step failed."""

    config = get_sso_config()

    if not config.get("enabled"):
        return {"error": "SSO is not enabled for this dealer."}

    pending, pending_error = pending_logins.pop(state)
    if pending_error:
        return {"error": pending_error}

    token_response, exchange_error = exchange_code_for_tokens(config, code, pending.redirect_uri)
    if exchange_error:
        _record_sso_failure(None, exchange_error)
        return {"error": f"SSO login failed: {exchange_error}"}

    claims, verify_error = verify_id_token(token_response["id_token"], config, pending.nonce)
    if verify_error:
        _record_sso_failure(None, verify_error)
        return {"error": f"SSO login failed: {verify_error}"}

    email = claims.get("email")
    if not email:
        _record_sso_failure(None, "id_token did not include an email claim")
        return {"error": "SSO login failed: the identity provider did not return an email address."}

    employee_id = credential_store.resolve_identifier(email)
    record = credential_store.get_record(employee_id)

    if not record:
        # No JIT auto-provisioning -- see this module's own docstring for why.
        _record_sso_failure(email, f"no NXTDeal employee account found for email '{email}'")
        return {
            "error": (
                f"SSO login failed: no NXTDeal account exists for {email}. "
                "An admin must create your account before you can sign in with SSO."
            )
        }

    if client_ip and not credential_store.check_ip_allowed(employee_id, client_ip):
        audit_log.record(
            event_type="sso_login_blocked_ip",
            summary=f"SSO login blocked for {employee_id} -- IP {client_ip} not on allowlist",
            entity_id=employee_id,
            actor=employee_id,
            details={"client_ip": client_ip},
        )
        save_audit_log(AUDIT_PATH)
        return {"error": "Login not allowed from this network."}

    lockout = credential_store.get_lockout_status(employee_id)
    if lockout["locked"]:
        audit_log.record(
            event_type="sso_login_blocked_locked",
            summary=f"SSO login blocked for {employee_id} -- account locked until {lockout['locked_until']}",
            entity_id=employee_id,
            actor=employee_id,
        )
        save_audit_log(AUDIT_PATH)
        return {"error": f"Account is locked until {lockout['locked_until']} after too many failed attempts."}

    role = record["role"]
    if credential_store.is_mfa_enabled(employee_id):
        challenge = issue_mfa_challenge_token(employee_id, role)
        audit_log.record(
            event_type="sso_login_mfa_challenge_issued",
            summary=f"{employee_id} passed SSO verification -- local MFA required",
            entity_id=employee_id,
            actor=employee_id,
            details={"provider": config.get("provider")},
        )
        save_audit_log(AUDIT_PATH)
        return {
            "mfa_required": True,
            "mfa_challenge_token": challenge,
            "employee_id": employee_id,
            "sso": True,
            "sso_provider": config.get("provider"),
        }
    token = issue_token(employee_id, role)

    audit_log.record(
        event_type="sso_login_success",
        summary=f"{employee_id} logged in as {role} via SSO ({config.get('provider')})",
        entity_id=employee_id,
        actor=employee_id,
        details={"role": role, "provider": config.get("provider"), "email": email},
    )
    save_audit_log(AUDIT_PATH)

    return {
        "token": token,
        "employee_id": employee_id,
        "role": role,
        "must_change_password": bool(record.get("must_change_password")),
        "allowed_dashboards": _allowed_dashboards(role),
        "sso": True,
        "sso_provider": config.get("provider"),
    }
