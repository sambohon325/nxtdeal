"""
Bulk-creates login credentials from a CSV of employees. See run_credential_import.py at
the repo root for the actual command-line entry point — this module just does the work,
matching the imports/employee_import.py convention (a plain function the caller decides
how to run/report).
"""

import csv

from core.auth import (
    credential_store,
    generate_temp_password
)

from core.audit import audit_log

from core.auth_api import VALID_ROLES


def import_credentials(csv_path, created_by="bulk_import"):
    """CSV must have an `employee_id` column and a `role` column (role is matched
    case-insensitively against core/permissions.py's role constants). An `email` column
    is optional (login-by-email support, 2026-07-13 session 20) — if present and non-empty
    for a row, that employee can log in with either their employee_id or that email
    afterward. Validates every row before creating anything — either the whole file
    imports cleanly, or nothing does, so partial/confusing imports can't happen. Raises
    ValueError listing every bad row if validation fails. Returns a list of
    {employee_id, role, temp_password, email} dicts on success — the caller
    (run_credential_import.py) is responsible for printing that report and for calling
    save_credentials()/save_audit_log(), same as core/auth_api.py's create_credential()
    does for the single-add path."""

    rows = []
    errors = []

    # utf-8-sig (not utf-8) so a BOM — which Windows tools like PowerShell's
    # `Out-File -Encoding utf8` and Notepad add by default — doesn't silently corrupt
    # the first header field. Behaves identically to utf-8 when there's no BOM.
    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for line_number, row in enumerate(reader, start=2):  # header is line 1

            employee_id = (row.get("employee_id") or "").strip()
            role = (row.get("role") or "").strip().upper()

            if not employee_id:
                errors.append(f"Line {line_number}: missing employee_id")
                continue

            if role not in VALID_ROLES:
                errors.append(
                    f"Line {line_number} ({employee_id}): unknown role '{role}'. "
                    f"Valid roles: {', '.join(VALID_ROLES)}"
                )
                continue

            email = (row.get("email") or "").strip() or None

            rows.append({
                "employee_id": employee_id,
                "role": role,
                "email": email
            })

    if errors:

        raise ValueError(
            "Credential import aborted — fix these rows and re-run:\n"
            + "\n".join(errors)
        )

    report = []

    for row in rows:

        temp_password = generate_temp_password()

        credential_store.set_credential(
            row["employee_id"],
            temp_password,
            row["role"],
            must_change_password=True,
            created_by=created_by,
            email=row["email"]
        )

        audit_log.record(
            event_type="credential_created",
            summary=(
                f"Credential created for {row['employee_id']} "
                f"({row['role']}) via bulk import"
            ),
            entity_id=row["employee_id"],
            actor=created_by,
            details={"role": row["role"]}
        )

        report.append({
            "employee_id": row["employee_id"],
            "role": row["role"],
            "temp_password": temp_password,
            "email": row["email"]
        })

    return report
