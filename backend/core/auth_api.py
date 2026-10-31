from core.administration_access import is_system_admin, can_manage_account
from core.auth import (
    credential_store,
    issue_token,
    verify_token,
    generate_temp_password,
    validate_password_strength,
    issue_mfa_challenge_token,
    is_mfa_challenge_token,
)

from core.auth_storage import (
    save_credentials
)

from core.audit import audit_log

from core.audit_storage import (
    save_audit_log
)

from core.storage_paths import (
    AUDIT_PATH,
    CREDENTIALS_PATH
)

from core.permissions import (
    ADMIN,
    OPERATIONS,
    SALES,
    MARKETING,
    SERVICE,
    FINANCE,
    BDC,
    DASHBOARD_ACCESS
)

from core.security import (
    can_access_dashboard
)


VALID_ROLES = (
    ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC
)


def _admin_session_ready(payload):
    if not payload or is_mfa_challenge_token(payload):
        return False
    record = credential_store.get_record(payload.get("employee_id"))
    return bool(record and not record.get("must_change_password"))


def _allowed_dashboards(role):
    """Every DASHBOARD_ACCESS key this role can open, computed server-side from the same
    single source of truth core/security.py's can_access_dashboard() already enforces on
    every /dashboard/* route and on chat's suggested_dashboard (core/ai_api.py). Attached
    to login()/whoami() so the frontend can hide/disable UI (e.g. /workspace's department
    tabs) for dashboards a role can't see, without duplicating the ACL matrix client-side —
    see BUILD_QUEUE.md's "Role-aware workspace tabs" entry."""

    return sorted(
        key for key in DASHBOARD_ACCESS
        if can_access_dashboard(role, key)
    )


def login(identifier, password, client_ip=None):
    """`identifier` may be an employee_id or an email address (login-by-email support,
    2026-07-13 session 20) — resolved once via credential_store.resolve_identifier() and
    used as the canonical employee_id for everything after (token payload, audit trail,
    response body), so callers downstream never need to know which form was typed in.

    `client_ip` is optional (Administration Control Center rebuild, "Security" item) --
    when supplied and the employee has a non-empty ip_allowlist configured, a request
    from an IP outside that allowlist is rejected before a password is even checked.
    Account lockout (5 failed attempts -> 15 minute lock, core/auth.py's
    MAX_FAILED_ATTEMPTS/LOCKOUT_MINUTES) is checked the same way, before authenticate()
    runs -- a locked account doesn't get a fresh "wrong password" attempt counted
    against it while already locked."""

    employee_id = credential_store.resolve_identifier(
        identifier
    )

    if client_ip and not credential_store.check_ip_allowed(employee_id, client_ip):

        audit_log.record(
            event_type="login_blocked_ip",
            summary=f"Login blocked for {employee_id} -- IP {client_ip} not on allowlist",
            entity_id=employee_id,
            actor=employee_id,
            details={"client_ip": client_ip}
        )

        save_audit_log(AUDIT_PATH)

        return {"error": "Login not allowed from this network."}

    lockout = credential_store.get_lockout_status(employee_id)

    if lockout["locked"]:

        audit_log.record(
            event_type="login_blocked_locked",
            summary=f"Login blocked for {employee_id} -- account locked until {lockout['locked_until']}",
            entity_id=employee_id,
            actor=employee_id
        )

        save_audit_log(AUDIT_PATH)

        return {"error": f"Account is locked until {lockout['locked_until']} after too many failed attempts."}

    role = credential_store.authenticate(
        identifier,
        password
    )

    if not role:

        credential_store.record_failed_login(employee_id)
        save_credentials(CREDENTIALS_PATH)

        audit_log.record(
            event_type="login_failed",
            summary=f"Failed login attempt for {employee_id}",
            entity_id=employee_id,
            actor=employee_id
        )

        save_audit_log(
            AUDIT_PATH
        )

        return {
            "error": "Invalid credentials"
        }

    # MFA gate (security-hardening pass, 2026-07-20): a correct password is no
    # longer sufficient on its own for an employee with MFA enabled -- issue a
    # short-lived challenge ticket instead of a real session token, and stop
    # here. The frontend hands that ticket + a TOTP/recovery code to
    # POST /auth/mfa/verify (verify_mfa_login() below), which is the only
    # place a real token gets issued from this point forward. Everything
    # below this block (audit "login_success", the real token, allowed
    # dashboards) is unchanged for an employee who hasn't enabled MFA.
    if credential_store.is_mfa_enabled(employee_id):

        challenge_token = issue_mfa_challenge_token(employee_id, role)

        audit_log.record(
            event_type="login_mfa_challenge_issued",
            summary=f"{employee_id} passed password check -- MFA code required",
            entity_id=employee_id,
            actor=employee_id
        )

        save_audit_log(AUDIT_PATH)

        return {
            "mfa_required": True,
            "mfa_challenge_token": challenge_token,
            "employee_id": employee_id
        }

    # Password-only accounts have now completed authentication. MFA accounts
    # clear failures only after the second factor succeeds, never on challenge issuance.
    credential_store.record_successful_login(employee_id)
    save_credentials(CREDENTIALS_PATH)

    token = issue_token(
        employee_id,
        role,
        fresh_auth=True
    )

    record = credential_store.get_record(employee_id)

    must_change_password = bool(
        record and record.get("must_change_password")
    )

    audit_log.record(
        event_type="login_success",
        summary=f"{employee_id} logged in as {role}",
        entity_id=employee_id,
        actor=employee_id,
        details={"role": role}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return {
        "token": token,
        "employee_id": employee_id,
        "role": role,
        "must_change_password": must_change_password,
        "allowed_dashboards": _allowed_dashboards(role)
    }


def verify_mfa_login(mfa_challenge_token, code):
    """The second step of login for an MFA-enabled employee -- takes the
    short-lived challenge ticket login() issued plus a real TOTP code (or a
    recovery code) and, on success, issues the real session token login()
    would otherwise have issued directly. Returns the identical response
    shape login() returns on a non-MFA success, plus `mfa_method`
    ("totp"/"recovery") so the frontend can warn the employee when they just
    burned a recovery code.

    A wrong code counts toward the SAME account-lockout counter a wrong
    password does (core/auth.py's MAX_FAILED_ATTEMPTS) -- brute-forcing the
    second factor is exactly as real a risk as brute-forcing the password,
    and this codebase already has a real lockout mechanism sitting right
    there to reuse rather than build a second one."""

    payload = verify_token(mfa_challenge_token)

    if not payload or not is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired MFA challenge -- please log in again"
        }

    employee_id = payload["employee_id"]
    role = payload["role"]

    lockout = credential_store.get_lockout_status(employee_id)

    if lockout["locked"]:

        return {
            "error": f"Account is locked until {lockout['locked_until']} after too many failed attempts."
        }

    ok, method = credential_store.verify_mfa_code(employee_id, code)

    if not ok:

        credential_store.record_failed_login(employee_id)
        save_credentials(CREDENTIALS_PATH)

        audit_log.record(
            event_type="login_mfa_failed",
            summary=f"Failed MFA code for {employee_id}",
            entity_id=employee_id,
            actor=employee_id
        )

        save_audit_log(AUDIT_PATH)

        return {
            "error": "Invalid authentication code"
        }

    credential_store.record_successful_login(employee_id)

    # A matched recovery code mutates credential_store's in-memory state
    # (the used code is removed) -- persist regardless of which method
    # matched, same "save on every state-changing branch" discipline the
    # rest of this file already follows.
    save_credentials(CREDENTIALS_PATH)

    token = issue_token(employee_id, role, fresh_auth=True, mfa_authenticated=True)

    record = credential_store.get_record(employee_id)

    must_change_password = bool(
        record and record.get("must_change_password")
    )

    audit_log.record(
        event_type="login_success",
        summary=f"{employee_id} logged in as {role} (MFA via {method})",
        entity_id=employee_id,
        actor=employee_id,
        details={"role": role, "mfa_method": method}
    )

    save_audit_log(AUDIT_PATH)

    return {
        "token": token,
        "employee_id": employee_id,
        "role": role,
        "must_change_password": must_change_password,
        "allowed_dashboards": _allowed_dashboards(role),
        "mfa_method": method
    }


def begin_mfa_enrollment(token):
    """Self-service: any employee with a REAL session token (not an MFA
    challenge ticket -- is_mfa_challenge_token() guards against a stolen/
    replayed challenge ticket being used here) can start enrolling
    themselves in MFA. Returns a fresh TOTP secret + otpauth:// URI for the
    frontend to render as a QR code (client-side, no image library needed on
    this side -- same precedent session 113's PURL Platform already
    established for QR rendering). Not yet active -- see
    confirm_mfa_enrollment()."""

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    employee_id = payload["employee_id"]

    result = credential_store.begin_mfa_enrollment(employee_id)

    if "error" in result:
        return result

    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="mfa_enrollment_started",
        summary=f"{employee_id} started MFA enrollment",
        entity_id=employee_id,
        actor=employee_id
    )

    save_audit_log(AUDIT_PATH)

    return {
        "employee_id": employee_id,
        **result
    }


def confirm_mfa_enrollment(token, code):
    """Completes enrollment -- requires a real code from the authenticator
    app the employee just scanned begin_mfa_enrollment()'s QR code into,
    proving the secret actually reached them. On success, previous sessions
    are revoked and the employee must log in with their new second factor;
    10 real recovery codes are returned in plaintext exactly once."""

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    employee_id = payload["employee_id"]

    result = credential_store.confirm_mfa_enrollment(employee_id, code)

    # Failed attempts and expired pending secrets are security state too.
    save_credentials(CREDENTIALS_PATH)
    if "error" in result:
        return result

    audit_log.record(
        event_type="mfa_enabled",
        summary=f"{employee_id} enabled MFA",
        entity_id=employee_id,
        actor=employee_id
    )

    save_audit_log(AUDIT_PATH)

    return {
        "employee_id": employee_id,
        **result
    }


def _recent_mfa_session(payload):
    """Require completed second-factor sign-in, not just an enrolled account."""
    import math
    import time
    authenticated = payload.get("authenticated_at")
    actor = credential_store.get_record(payload["employee_id"])
    return bool(actor and not actor.get("must_change_password")
                and actor.get("mfa_enabled")
                and payload.get("mfa_authenticated") is True
                and type(authenticated) in (int, float)
                and math.isfinite(authenticated)
                and 0 <= time.time() - authenticated <= 300)


def disable_mfa(token, password):
    """Require recent completed MFA sign-in plus the current password.

    A bearer session and password alone must not remove the second factor.
    Lost-authenticator users can sign in with a recovery code; if every
    recovery code is lost too, use the administrator recovery path.
    """

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    employee_id = payload["employee_id"]

    if not _recent_mfa_session(payload):
        return {"error": "Sign in again with your authenticator or recovery code before disabling MFA.",
                "code": "fresh_mfa_required"}

    if credential_store.authenticate(employee_id, password) is None:

        return {
            "error": "Current password is incorrect"
        }

    credential_store.disable_mfa(employee_id)
    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="mfa_disabled",
        summary=f"{employee_id} disabled their own MFA",
        entity_id=employee_id,
        actor=employee_id
    )

    save_audit_log(AUDIT_PATH)

    return {
        "success": True,
        "reauthentication_required": True
    }


def admin_disable_mfa(admin_token, employee_id):
    """The real admin escape hatch -- for an employee who's lost both their
    authenticator device AND every recovery code. ADMIN-only, same gate as
    reset_password()/create_credential() above. Deliberately logged with a
    distinct event_type from the self-service path (mfa_disabled_by_admin,
    not mfa_disabled) so the audit trail always shows whether the employee
    or an admin turned a security control off."""

    admin_payload = verify_token(admin_token)
    if not can_manage_account(admin_payload, employee_id):
        return {"error": "Only NXTDeal system administrators can manage this account"}


    if not admin_payload or is_mfa_challenge_token(admin_payload):

        return {
            "error": "Invalid or expired token"
        }

    if admin_payload["role"] != ADMIN:

        return {
            "error": "Admin role required"
        }

    # Recovery removes another user's second factor. A long-lived bearer token
    # or password-only login is insufficient authorization for that action.
    if not _recent_mfa_session(admin_payload):
        return {"error": "Sign in again with an enrolled administrator authenticator or recovery code before resetting MFA.",
                "code": "fresh_admin_mfa_required"}

    if not credential_store.disable_mfa(employee_id):

        return {
            "error": f"No credential exists for {employee_id}"
        }

    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="mfa_disabled_by_admin",
        summary=f"{employee_id}'s MFA disabled by {admin_payload['employee_id']}",
        entity_id=employee_id,
        actor=admin_payload["employee_id"]
    )

    save_audit_log(AUDIT_PATH)

    return {
        "employee_id": employee_id,
        "mfa_enabled": False
    }


def get_mfa_status(token):
    """Self-service status check -- whether MFA is on, and how many recovery
    codes remain (so the frontend can nudge someone running low to
    re-enroll and get a fresh batch, since confirm_mfa_enrollment() always
    hands out a brand new set of 10)."""

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    employee_id = payload["employee_id"]

    return {
        "employee_id": employee_id,
        "mfa_enabled": credential_store.is_mfa_enabled(employee_id),
        "recovery_codes_remaining": credential_store.mfa_recovery_codes_remaining(employee_id)
    }


def whoami(token):

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    record = credential_store.get_record(payload["employee_id"])
    if not record:
        return {"error": "Invalid or expired token"}

    return {
        "employee_id": payload["employee_id"],
        "role": payload["role"],
        "must_change_password": bool(record.get("must_change_password")),
        "is_system_admin": is_system_admin(payload),
        "allowed_dashboards": _allowed_dashboards(payload["role"])
    }


def create_credential(
    admin_token,
    employee_id,
    role,
    temp_password=None,
    email=None
):
    """The admin one-by-one add flow (POST /auth/admin/credentials). Requires a valid,
    unexpired token belonging to an ADMIN. Generates a temp password if the caller
    doesn't supply one — either way, the plaintext is only ever returned in THIS response,
    once; it is not recoverable afterward (only its hash is stored). The admin is expected
    to relay it to the employee out of band; the employee must change it on first login
    (must_change_password=True, enforced by shared business-route authentication,
    credential administration and messaging sockets; recovery remains available).

    `email` is optional (login-by-email support, 2026-07-13 session 20) — if given, the
    employee can log in with either their employee_id or this email going forward."""

    admin_payload = verify_token(admin_token)
    if not can_manage_account(admin_payload, employee_id):
        return {"error": "Only NXTDeal system administrators can manage this account"}


    if not _admin_session_ready(admin_payload):

        return {
            "error": "Invalid or expired token"
        }

    if admin_payload["role"] != ADMIN:

        return {
            "error": "Admin role required"
        }

    if role not in VALID_ROLES:

        return {
            "error":
                f"Unknown role '{role}'. Valid roles: {', '.join(VALID_ROLES)}"
        }

    if email:
        owner = credential_store.email_index.get(email.strip().lower())
        if owner and owner != employee_id:
            return {"error": "This email already belongs to another login"}

    if temp_password is None:
        temp_password = generate_temp_password()

    credential_store.set_credential(
        employee_id,
        temp_password,
        role,
        must_change_password=True,
        created_by=admin_payload["employee_id"],
        email=email
    )

    save_credentials(
        CREDENTIALS_PATH
    )

    audit_log.record(
        event_type="credential_created",
        summary=f"Credential created for {employee_id} ({role}) by {admin_payload['employee_id']}",
        entity_id=employee_id,
        actor=admin_payload["employee_id"],
        details={"role": role}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return {
        "employee_id": employee_id,
        "role": role,
        "temp_password": temp_password,
        "must_change_password": True,
        "email": email
    }


def reset_password(admin_token, employee_id, temp_password=None):
    """Admin-forced password reset (closes the gap change_password() below used to flag —
    see BUILD_QUEUE.md session 19). For when an employee forgets/loses their password and
    can't complete change_password() themselves (that requires knowing the current
    password). Requires ADMIN, same check as create_credential(). Unlike
    create_credential(), this does NOT take a role — it preserves whatever role the
    employee already has, since resetting a password shouldn't be a chance to silently
    change someone's access level. Errors if no credential exists for employee_id yet (use
    create_credential() for a brand new account, not this). Generates a temp password if
    the caller doesn't supply one; forces must_change_password back to True, same as a
    freshly created account, and the plaintext is only ever returned in THIS response."""

    admin_payload = verify_token(admin_token)
    if not can_manage_account(admin_payload, employee_id):
        return {"error": "Only NXTDeal system administrators can manage this account"}


    if not _admin_session_ready(admin_payload):

        return {
            "error": "Invalid or expired token"
        }

    if admin_payload["role"] != ADMIN:

        return {
            "error": "Admin role required"
        }

    record = credential_store.get_record(employee_id)

    if not record:

        return {
            "error": f"No credential exists for {employee_id} — use create_credential "
                     "for a new account"
        }

    if temp_password is None:
        temp_password = generate_temp_password()

    credential_store.set_credential(
        employee_id,
        temp_password,
        record["role"],
        must_change_password=True,
        created_by=admin_payload["employee_id"]
    )

    save_credentials(
        CREDENTIALS_PATH
    )

    audit_log.record(
        event_type="credential_reset",
        summary=f"Password reset for {employee_id} by {admin_payload['employee_id']}",
        entity_id=employee_id,
        actor=admin_payload["employee_id"],
        details={"role": record["role"]}
    )

    save_audit_log(
        AUDIT_PATH
    )

    return {
        "employee_id": employee_id,
        "role": record["role"],
        "temp_password": temp_password,
        "must_change_password": True
    }


def list_credentials(admin_token):
    """Admin roster view (BUILD_QUEUE.md's "Employee Directory / Admin Roster View"
    entry). Closes a real gap that's existed since credential provisioning first landed
    (session 7): an admin could create or reset one credential at a time by typing an
    employee_id, but there was no way to see who actually has an account, what role
    they're on, or whether they still need to complete their forced first password
    change. Same admin-token-in-the-function-body check as create_credential()/
    reset_password() above (not api/app.py's _require_admin helper) — kept consistent
    with its two siblings in this file rather than switching patterns for just this one.
    Never returns salt/hash — see CredentialStore.list_records()."""

    admin_payload = verify_token(admin_token)

    if not _admin_session_ready(admin_payload):

        return {
            "error": "Invalid or expired token"
        }

    if admin_payload["role"] != ADMIN:

        return {
            "error": "Admin role required"
        }

    return [record for record in credential_store.list_records()
            if can_manage_account(admin_payload, record.get("employee_id"))]


def change_password(token, old_password, new_password):
    """Any authenticated employee changing their own password — including completing the
    forced first-login change. Requires knowing the current (temp or real) password; for
    an admin-forced reset when the employee can't provide that, see reset_password()
    above.

    Enforces the real password policy (Administration Control Center rebuild,
    "Security" item, core/auth.py's validate_password_strength()) before touching the
    stored credential -- a genuine, checkable rule (length + a letter + a digit), not a
    fabricated strength score."""

    payload = verify_token(token)

    if not payload or is_mfa_challenge_token(payload):

        return {
            "error": "Invalid or expired token"
        }

    employee_id = payload["employee_id"]

    policy_error = validate_password_strength(new_password)

    if policy_error:

        return {
            "error": policy_error
        }

    success = credential_store.change_password(
        employee_id,
        old_password,
        new_password
    )

    if not success:

        return {
            "error": "Current password is incorrect"
        }

    save_credentials(
        CREDENTIALS_PATH
    )

    audit_log.record(
        event_type="password_changed",
        summary=f"{employee_id} changed their password",
        entity_id=employee_id,
        actor=employee_id
    )

    save_audit_log(
        AUDIT_PATH
    )

    return {
        "success": True,
        "token": issue_token(employee_id, payload["role"])
    }


def get_lockout_status(admin_token, employee_id):
    """Real, computed lockout state for one employee (Administration Control Center
    rebuild, "Security" item) -- ADMIN/OPERATIONS, same as list_credentials()'s roster
    view but scoped to one employee's own account-security state."""

    admin_payload = verify_token(admin_token)

    if not _admin_session_ready(admin_payload):
        return {"error": "Invalid or expired token"}

    if admin_payload["role"] not in (ADMIN, OPERATIONS):
        return {"error": "Admin/Operations role required"}

    return {"employee_id": employee_id, **credential_store.get_lockout_status(employee_id)}


def unlock_account(admin_token, employee_id):
    """Real admin action -- clears an active lockout early rather than making the
    employee wait out LOCKOUT_MINUTES."""

    admin_payload = verify_token(admin_token)
    if not can_manage_account(admin_payload, employee_id):
        return {"error": "Only NXTDeal system administrators can manage this account"}


    if not _admin_session_ready(admin_payload):
        return {"error": "Invalid or expired token"}

    if admin_payload["role"] not in (ADMIN, OPERATIONS):
        return {"error": "Admin/Operations role required"}

    if not credential_store.unlock(employee_id):
        return {"error": f"No credential exists for {employee_id}"}

    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="account_unlocked",
        summary=f"{employee_id}'s account unlocked by {admin_payload['employee_id']}",
        entity_id=employee_id,
        actor=admin_payload["employee_id"]
    )

    save_audit_log(AUDIT_PATH)

    return {"employee_id": employee_id, "locked": False}


def set_ip_allowlist(admin_token, employee_id, ip_list):
    """Real, per-employee IP allowlist (Administration Control Center rebuild,
    "Security" item) -- an empty list means unrestricted (the default). ADMIN-only,
    narrower than most of this module's other ADMIN/OPERATIONS actions, since this
    can lock an employee out of the platform entirely if misconfigured."""

    admin_payload = verify_token(admin_token)
    if not can_manage_account(admin_payload, employee_id):
        return {"error": "Only NXTDeal system administrators can manage this account"}


    if not _admin_session_ready(admin_payload):
        return {"error": "Invalid or expired token"}

    if admin_payload["role"] != ADMIN:
        return {"error": "Admin role required"}

    if not credential_store.set_ip_allowlist(employee_id, ip_list):
        return {"error": f"No credential exists for {employee_id}"}

    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="ip_allowlist_changed",
        summary=f"IP allowlist for {employee_id} set by {admin_payload['employee_id']} ({len(ip_list or [])} entries)",
        entity_id=employee_id,
        actor=admin_payload["employee_id"],
        details={"ip_allowlist": ip_list}
    )

    save_audit_log(AUDIT_PATH)

    return {"employee_id": employee_id, "ip_allowlist": ip_list or []}
