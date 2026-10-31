"""
Bulk-create login credentials for a list of employees.

Usage:
    python run_credential_import.py path/to/employees.csv

CSV format (header row required):
    employee_id,role,email
    EMP-00001,SALES,priya@dealership.example
    EMP-00002,SERVICE,

`email` is optional (login-by-email support, 2026-07-13 session 20) — leave it blank for
rows that shouldn't get one; those employees can still log in with just their employee_id.

Valid roles: ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE (core/permissions.py).

This is a trusted, local, one-off script — same convention as imports/employee_import.py
and the other backend/test_*.py runner scripts. It does NOT require an admin API token
because it runs directly against the backend's storage, not over HTTP. The HTTP-facing
equivalent (for adding one person at a time from an admin screen) is
POST /auth/admin/credentials, which DOES require a valid ADMIN token — see
core/auth_api.py's create_credential().

Temp passwords are printed ONCE, to this terminal, and are not recoverable afterward (only
their hash gets stored). Distribute them to each employee securely (not by committing them
anywhere) and have them change their password on first login via POST /auth/change-password
— the account stays flagged must_change_password=True until they do.
"""

import sys

from core.auth_storage import load_credentials, save_credentials
from core.audit_storage import save_audit_log
from imports.credential_import import import_credentials


def main():

    if len(sys.argv) != 2:
        print("Usage: python run_credential_import.py path/to/employees.csv")
        sys.exit(1)

    csv_path = sys.argv[1]

    # Load whatever credentials already exist so this doesn't clobber them.
    load_credentials("storage/credentials.json")

    report = import_credentials(csv_path)

    save_credentials("storage/credentials.json")
    save_audit_log("storage/audit.json")

    print()
    print(f"Created {len(report)} credential(s). Distribute these temp passwords securely")
    print("— they will not be shown again:")
    print()
    print(f"{'employee_id':<15}{'role':<12}{'email':<30}temp_password")
    print("-" * 75)

    for entry in report:
        email = entry.get("email") or "-"
        print(f"{entry['employee_id']:<15}{entry['role']:<12}{email:<30}{entry['temp_password']}")

    print()


if __name__ == "__main__":
    main()
