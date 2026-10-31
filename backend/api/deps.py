"""Shared route-auth helpers extracted out of api/app.py (CAF-00120,
god_file_app_py -- splitting the 14,800+-line monolith into routers).

Why this module exists: api/app.py is being split into domain-scoped
FastAPI routers under api/routers/*.py. Every one of those router files
needs the SAME `_authenticate`/`_require_admin`/`_authorize_dashboard`
helpers app.py's own route handlers already call on every request. Those
helpers can't stay defined inside app.py itself, because app.py is what
calls `app.include_router(...)` on each new router module -- a router
file that tried `from api.app import _authenticate` would create a real
circular import (app.py needs the router loaded to include it; the router
would need app.py fully loaded to get _authenticate). Extracting the
helpers here first, with no dependency on app.py itself, breaks that
cycle: both app.py's own remaining inline routes and every new router
module import from here.

Behavior is unchanged from the original app.py definitions -- this is a
pure move, not a rewrite. See api/app.py's own historical comments (still
left in place at the original call sites) for the full reasoning behind
the always-200 `{"error": "..."}` shape instead of raising
HTTPException/401, and for the real API-key fallback in _authenticate.
"""

from core.auth import credential_store, verify_token, is_mfa_challenge_token
from core.api_keys import verify_api_key
from core.permissions import ADMIN
from core.security import can_access_dashboard
import time


def _bearer_token(authorization):
    """Pulls the token out of an `Authorization: Bearer <token>` header. Used by
    /auth/whoami, /auth/admin/credentials, and /auth/change-password — these three are
    intentionally on the header convention (not the `?token=` query-param convention the
    rest of this API still uses for GET requests) since tokens in query strings can leak
    into server/proxy logs. See BUILD_QUEUE.md Phase 9 for the full note."""

    if not authorization:
        return None

    parts = authorization.split(" ", 1)

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def _authenticate(authorization):
    """Route-protection helper (Phase 9 wrap-up). Returns (payload, error) — error is None
    on success, otherwise a dict in the same `{"error": "..."}` / always-200 shape every
    other auth failure in this file already uses (see login/whoami/create_credential in
    core/auth_api.py) — kept consistent rather than switching to HTTPException/401 for just
    these routes. Callers: `payload, error = _authenticate(authorization); if error: return
    error`."""

    token = _bearer_token(authorization)

    if not token:

        return None, {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    payload = verify_token(token)

    # MFA challenge tickets (security-hardening pass, 2026-07-20,
    # core/auth.py's issue_mfa_challenge_token()) are real, validly-signed
    # tokens -- but they're only ever meant to authenticate ONE call,
    # POST /auth/mfa/verify, never a normal API request. Treating one as
    # invalid here (same as a bad/expired token) is what makes that scoping
    # real rather than just a naming convention: a challenge ticket
    # intercepted in transit can't be replayed against any protected route.
    if payload and is_mfa_challenge_token(payload):
        payload = None

    if not payload:

        # Real API-key fallback (Administration Control Center rebuild,
        # "Identity & Access" item, core/api_keys.py) -- a bearer value that
        # isn't a valid session token is also tried as a real, active,
        # non-revoked API key before failing. Gives generate_api_key_api()'s
        # keys real teeth (they genuinely authenticate a request) rather than
        # a management screen with nothing behind it.
        api_key_payload = verify_api_key(token)

        if api_key_payload:
            return api_key_payload, None

        return None, {
            "error": "Invalid or expired token"
        }

    # Onboarding/recovery endpoints use their own narrowly scoped auth helpers.
    # A temporary password must not grant access to business data or actions.
    record = credential_store.get_record(payload.get("employee_id"))
    if not record or record.get("must_change_password"):
        return None, {"error": "Password change required"}

    return payload, None


def _require_admin(authorization):
    """Same as _authenticate, but additionally requires the ADMIN role — used for the
    audit endpoints, which are privileged (who-did-what logs) same as
    POST /auth/admin/credentials already is."""

    payload, error = _authenticate(authorization)

    if error:

        return None, error

    if payload["role"] != ADMIN:

        return None, {
            "error": "Admin role required"
        }

    return payload, None


def _require_recent_admin(authorization):
    """Credential/privilege mutations require a recent interactive admin login."""
    payload, error = _require_admin(authorization)
    if error:
        return None, error
    authenticated = payload.get("authenticated_at")
    if (type(authenticated) is not int
            or not 0 <= time.time() - authenticated <= 300
            or (credential_store.is_mfa_enabled(payload["employee_id"])
                and payload.get("mfa_authenticated") is not True)):
        return None, {"error": "Sign in again and complete any required MFA before managing users.",
                      "code": "fresh_login_required"}
    return payload, None


def _authorize_dashboard(authorization, dashboard_key):
    """Same as _authenticate, but additionally checks core/permissions.py's
    DASHBOARD_ACCESS for the given dashboard_key (see that dict's comment for where the
    per-department assumptions came from — Sam-approved starting point, not a spec).
    `dashboard_key` is a fixed string passed by each route below, never user input."""

    payload, error = _authenticate(authorization)

    if error:

        return None, error

    if not can_access_dashboard(payload["role"], dashboard_key):

        return None, {
            "error": f"Forbidden: your role cannot access the '{dashboard_key}' dashboard"
        }

    return payload, None
