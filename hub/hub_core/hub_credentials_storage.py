"""
NXTDeal Hub -- persistence for the Hub's own admin login credentials
(hub/storage/hub_credentials.json).

Real per-employee Hub login (2026-07-23) replaces the old single shared-secret
gate (NXTDEAL_HUB_KEY, hub/app.py's _check_hub_key). This is the Hub-side mirror
of backend/core/auth_storage.py -- same atomic-write + truncation-tolerant load,
and it persists the exact same structure: hub_core.auth.credential_store.credentials,
a flat mapping employee_id -> {salt, hash, role, must_change_password, created_by,
created_at, email}. salt/hash are PBKDF2 (hub_core/auth.py); no plaintext password
is ever written here.

Why its own file (not reusing backend/core/auth_storage.py or backend's
credentials.json): hub/ deploys as its own isolated Coolify app whose Base
Directory is `hub/`, so it cannot import the sibling backend/ package at runtime
(see hub_core/auth.py's and hub_core/secrets.py's own module docstrings for the
full reasoning). The Hub's staff credentials are also a separate population from
any one dealer tenant's employee credentials. Kept in sync with
backend/core/auth_storage.py if that hardening ever changes.
"""

import json
import os

from hub_core.auth import credential_store


def save_hub_credentials(filepath):
    """Atomic write: dump to a temp file in the same directory, then os.replace()
    (atomic on the same filesystem). hub_credentials.json holds every Hub admin's
    password salt/hash and is loaded at process start (hub/app.py's lifespan) -- a
    process killed mid-write must never leave a truncated file that fails to parse
    and locks everyone out of the Hub. Same discipline as
    backend/core/auth_storage.py's save_credentials()."""

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(credential_store.credentials, file, indent=4)

    os.replace(tmp_path, filepath)


def _recover_partial_object(text):
    """Best-effort salvage of a truncated JSON object of records -- mirrors
    backend/core/auth_storage.py's _recover_partial_object() exactly.
    hub_credentials.json is a flat mapping employee_id -> record object; an
    interrupted write leaves a well-formed prefix of complete pairs followed by a
    half-written final pair. Trims back to the last complete top-level record and
    closes the outer object. Returns {} if nothing is salvageable."""

    close = text.rfind("}")

    while close != -1:

        candidate = text[:close + 1] + "}"

        try:
            recovered = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            close = text.rfind("}", 0, close)
            continue

        if isinstance(recovered, dict):
            return recovered

        return {}

    return {}


def load_hub_credentials(filepath):
    """Load persisted Hub credentials into the module-level credential_store (and
    rebuild its email index) via CredentialStore.load_credentials(). A missing file
    is a no-op (first boot). A corrupt/truncated file must never stop the Hub from
    booting (that would also lock everyone out of Hub login) -- recover whatever
    complete records survived and carry on."""

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            raw = file.read()
    except FileNotFoundError:
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = _recover_partial_object(raw)
        print(
            "WARNING: hub/storage/hub_credentials.json was corrupt or truncated; "
            "recovered {} complete credential record(s) and continued.".format(len(data))
        )

    credential_store.load_credentials(data)
