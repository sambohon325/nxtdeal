#!/usr/bin/env python3
"""
create_demo_account.py -- creates (or unlocks) a NXTDeal login credential.

WHERE TO RUN THIS: on whichever machine/container actually serves the
account you want to affect. Running it in a local checkout only touches
that checkout's own local storage/credentials.json -- it has no effect on
a separately-deployed server (e.g. the live dealer1.dealeros.xyz Coolify
app), since storage/*.json is gitignored and each deployment has its own
persistent volume. To create a demo account on the LIVE site, run this
from Coolify's "Execute Command" panel (or via SSH) for that app, from
inside its `backend/` directory.

Usage (run from inside backend/, i.e. same directory as api/app.py):

    # Create a brand-new demo account (default role ADMIN, id DEMO-USER):
    python3 create_demo_account.py

    # Customize the id/role:
    python3 create_demo_account.py --id DEMO-CANADA --role ADMIN

    # Unlock (and optionally reset the password of) an existing account
    # that's currently locked out from too many failed login attempts --
    # e.g. your own real account, after a coworker mistyped the password
    # a few times:
    python3 create_demo_account.py --unlock EMP-00001
    python3 create_demo_account.py --unlock EMP-00001 --reset-password

Prints the resulting username/password exactly once -- nothing is echoed
back on a later run. The created/reset account has must_change_password
set, matching every other credential this codebase creates (bulk import,
the admin add-one-by-one endpoint) -- whoever logs in with the printed
temp password will be prompted to set their own on first login.
"""

import argparse
import json
import os
import sys

from core.auth import credential_store, generate_temp_password
from core.auth_storage import save_credentials
from core.storage_paths import CREDENTIALS_PATH
from core.auth_api import VALID_ROLES


def load_existing():
    """Load whatever credentials already exist on this server first, so we
    never wipe out real accounts -- mirrors api/app.py's own boot sequence
    (load_credentials() before any mutation)."""

    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            credential_store.load_credentials(json.load(f))


def create_demo(employee_id, role):

    load_existing()

    if employee_id in credential_store.credentials:
        print(
            f"'{employee_id}' already exists -- refusing to overwrite it "
            f"(pick a different --id, or use --unlock if you meant to "
            f"reset it instead).",
            file=sys.stderr,
        )
        sys.exit(1)

    temp_password = generate_temp_password()

    credential_store.set_credential(
        employee_id,
        temp_password,
        role,
        must_change_password=True,
        created_by="demo_account_script",
    )

    save_credentials(CREDENTIALS_PATH)

    print("Demo account created.")
    print(f"  Username: {employee_id}")
    print(f"  Password: {temp_password}")
    print(f"  Role:     {role}")
    print("  (must change password on first login)")


def unlock_account(employee_id, reset_password):

    load_existing()

    record = credential_store.get_record(employee_id)
    if record is None:
        print(f"No credential exists for '{employee_id}'.", file=sys.stderr)
        sys.exit(1)

    credential_store.unlock(employee_id)

    if reset_password:
        temp_password = generate_temp_password()
        credential_store.set_credential(
            employee_id,
            temp_password,
            record["role"],
            must_change_password=True,
            created_by=record.get("created_by"),
        )
    else:
        temp_password = None

    save_credentials(CREDENTIALS_PATH)

    print(f"'{employee_id}' unlocked.")
    if temp_password:
        print(f"  New password: {temp_password}")
        print("  (must change password on next login)")
    else:
        print("  Existing password left unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--id",
        default="DEMO-USER",
        help="employee_id / username for the new demo account (default: DEMO-USER)",
    )
    parser.add_argument(
        "--role",
        default="ADMIN",
        choices=sorted(VALID_ROLES),
        help="role for the new demo account (default: ADMIN)",
    )
    parser.add_argument(
        "--unlock",
        metavar="EMPLOYEE_ID",
        help="instead of creating a new account, unlock this existing one "
        "(clears failed-attempt lockout)",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="only valid with --unlock -- also issue a new temp password",
    )
    args = parser.parse_args()

    if args.unlock:
        unlock_account(args.unlock, args.reset_password)
    else:
        create_demo(args.id, args.role)


if __name__ == "__main__":
    main()
