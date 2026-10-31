"""
API layer for user/employee management (Bumper parity, 2026-07-25). Composes the
Employee-entity half (core/user_management.py) with the credential store (core/auth.py)
so an admin can create a working login in one call and reassign roles without a password
reset. All mutating actions are ADMIN-only, matching the existing credential-admin
posture (core/auth_api.create_credential); the read/roster views also allow OPERATIONS
(the "sees everything" supervisory role).
"""

from core import user_management
from core.auth import (
    credential_store,
    generate_temp_password,
)
from core.auth_storage import save_credentials
from core.auth_api import VALID_ROLES, _allowed_dashboards
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH, CREDENTIALS_PATH


# Human-facing descriptions for the role picker (Bumper users / NXTDeal onboarding staff
# need to know what each role means, not just its code).
ROLE_DESCRIPTIONS = {
    ADMIN: "Dealership administration -- staff accounts, dealership settings and business rules. NXTDeal system access is separately provisioned.",
    OPERATIONS: "Cross-department oversight -- sees every operational dashboard (not the audit log).",
    SALES: "Sales desk -- leads, pipeline, deals, the showroom floor.",
    MARKETING: "Marketing -- campaigns, audiences, advertising, loyalty.",
    SERVICE: "Fixed ops -- service records and the service dashboard.",
    FINANCE: "F&I -- finance contracts, lenders, loan servicing.",
    BDC: "Business Development Center -- speed-to-lead, untouched queue, appointment setting.",
}


def _can_manage(role):
    return role == ADMIN


def _can_view_roster(role):
    return role == ADMIN or role == OPERATIONS


def list_roles_api():
    """The assignable roles with descriptions and the dashboards each unlocks -- drives
    the create-user role picker and the Roles reference."""
    return {
        "roles": [
            {
                "role": r,
                "description": ROLE_DESCRIPTIONS.get(r, ""),
                "allowed_dashboards": _allowed_dashboards(r),
            }
            for r in VALID_ROLES
        ]
    }


def _serialize_user(entity, record):
    """Merge an Employee entity (may be None) and a credential record (may be None) into
    one roster row. salt/hash are never included."""
    a = entity.attributes if entity else {}
    return {
        "employee_id": (entity.id if entity else None) or (record.get("employee_id") if record else None),
        "name": user_management._display_name(entity) if entity else None,
        "first_name": a.get("FirstName"),
        "last_name": a.get("LastName"),
        "email": a.get("Email") or (record.get("email") if record else None),
        "department": a.get("Department"),
        "title": a.get("Title"),
        "role": record.get("role") if record else None,
        "has_login": record is not None,
        "must_change_password": record.get("must_change_password", False) if record else False,
    }


def list_users_api(role):
    """Roster: every Employee entity joined to its credential (role/login state), plus any
    credential that has no Employee entity (import-only logins). ADMIN/OPERATIONS."""
    if not _can_view_roster(role):
        return {"error": "You don't have access to the user roster"}

    employees = {e.id: e for e in user_management.list_employees()}
    records = {r["employee_id"]: r for r in credential_store.list_records()}

    rows = []
    seen = set()
    for emp_id, entity in sorted(employees.items()):
        rows.append(_serialize_user(entity, records.get(emp_id)))
        seen.add(emp_id)
    # Credentials with no Employee entity (e.g. seeded logins) -- surface them so an admin
    # isn't blind to a login that exists but has no directory record.
    for emp_id, record in sorted(records.items()):
        if emp_id not in seen:
            rows.append(_serialize_user(None, record))

    from core.administration_access import system_admin_context, reserved_system_admin
    if not system_admin_context.get():
        rows = [row for row in rows if not reserved_system_admin(row["employee_id"])]
    return {"users": rows, "count": len(rows)}


def create_user_api(role, actor_id, first_name, last_name, email, assigned_role, department="", title="", temp_password=None):
    """Create an Employee entity AND a login with a role, in one ADMIN action. Returns the
    temp password exactly once (only its hash is stored). The user must change it on first
    login (must_change_password=True)."""
    if not _can_manage(role):
        return {"error": "Admin role required to create users"}

    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    if not first_name or not last_name:
        return {"error": "first_name and last_name are required"}

    if assigned_role not in VALID_ROLES:
        return {"error": f"Unknown role '{assigned_role}'. Valid roles: {', '.join(VALID_ROLES)}"}

    email = (email or "").strip()
    if email and email.lower() in getattr(credential_store, "email_index", {}):
        return {"error": f"A login already exists for email '{email}'"}

    entity = user_management.create_employee(
        first_name, last_name, email, department=department, title=title, created_by=actor_id
    )

    from core.administration_access import reserved_system_admin
    if reserved_system_admin(entity.id):
        return {"error": "This identity is reserved for NXTDeal provisioning"}

    if temp_password is None:
        temp_password = generate_temp_password()

    credential_store.set_credential(
        entity.id,
        temp_password,
        assigned_role,
        must_change_password=True,
        created_by=actor_id,
        email=email or None,
    )
    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="user_created",
        summary=f"User {entity.id} ({assigned_role}) created by {actor_id}",
        entity_id=entity.id,
        actor=actor_id,
        details={"role": assigned_role, "department": department, "title": title},
    )
    save_audit_log(AUDIT_PATH)

    return {
        "employee_id": entity.id,
        "name": user_management._display_name(entity),
        "email": email,
        "role": assigned_role,
        "department": department,
        "title": title,
        "temp_password": temp_password,
        "must_change_password": True,
    }


def update_user_role_api(role, actor_id, target_employee_id, new_role):
    """Reassign a user's role without resetting their password. ADMIN only."""
    if not _can_manage(role):
        return {"error": "Admin role required to change roles"}

    if new_role not in VALID_ROLES:
        return {"error": f"Unknown role '{new_role}'. Valid roles: {', '.join(VALID_ROLES)}"}

    from core.administration_access import reserved_system_admin, system_admin_context
    if reserved_system_admin(target_employee_id) and not system_admin_context.get():
        return {"error": "Only NXTDeal system administrators can manage this account"}
    record = credential_store.get_record(target_employee_id)
    if not record:
        return {"error": f"No login found for '{target_employee_id}'"}

    old_role = record.get("role")
    if old_role == new_role:
        return {"error": f"User is already '{new_role}'"}

    credential_store.set_role(target_employee_id, new_role)
    save_credentials(CREDENTIALS_PATH)

    audit_log.record(
        event_type="user_role_changed",
        summary=f"Role for {target_employee_id} changed {old_role} -> {new_role} by {actor_id}",
        entity_id=target_employee_id,
        actor=actor_id,
        details={"old_role": old_role, "new_role": new_role},
    )
    save_audit_log(AUDIT_PATH)

    return {
        "employee_id": target_employee_id,
        "old_role": old_role,
        "new_role": new_role,
        "allowed_dashboards": _allowed_dashboards(new_role),
    }
