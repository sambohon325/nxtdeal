"""
Persistence for customer login credentials (2026-07-24) — the customer-side twin of
core/auth_storage.py. Customer password salt/hashes live in their OWN file
(customer_credentials.json), never in the graph, exactly like employee credentials.json.
Atomic write + truncation-tolerant load, same hardening as the other boot-critical stores.
"""

import json
import os

from core.customer_accounts import customer_credential_store
from core.storage_paths import storage_path


def CUSTOMER_CREDENTIALS_PATH():
    # A function (not a module constant) so a tenant's DEALEROS_STORAGE_DIR / a test's
    # monkeypatched storage dir is read fresh on every call, matching storage_path()'s own
    # "resolve on every call" contract.
    return storage_path("customer_credentials.json")


def save_customer_credentials(filepath):
    from core.storage import demo_persistence_disabled
    if demo_persistence_disabled():  # demo tenant never persists
        return
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(customer_credential_store.credentials, file, indent=4)
    os.replace(tmp_path, filepath)


def _recover_partial_object(text):
    """Salvage the well-formed prefix of a truncated flat {email: record} object — same
    approach as core/auth_storage._recover_partial_object."""
    close = text.rfind("}")
    while close != -1:
        candidate = text[: close + 1] + "}"
        try:
            recovered = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            close = text.rfind("}", 0, close)
            continue
        return recovered if isinstance(recovered, dict) else {}
    return {}


def load_customer_credentials(filepath):
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
            "WARNING: customer_credentials.json was corrupt or truncated; "
            "recovered {} complete records and continued.".format(len(data))
        )
    customer_credential_store.load_credentials(data)
