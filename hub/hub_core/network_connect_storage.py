"""
NXTDeal Hub -- persistence for the Network Connect account registry
(hub/storage/network_connect_accounts.json). Same atomic-write +
truncated-JSON-recovery convention as every other Hub sub-registry
(hub/hub_core/dealer_storage.py / hub/hub_core/dealer_modules_storage.py) -- temp
file + os.replace(), best-effort salvage of a truncated top-level array on
load so a corrupt file can never block the Hub from booting.

A SEPARATE file from hub/storage/dealers.json AND from
hub/storage/network_snapshots.json on purpose -- the identified account
record and the anonymized KPI pool must never live in the same file, same
reasoning hub_core/network_connect.py's own module docstring states plainly.
"""

import json
import os

from hub_core.network_connect import registry, NetworkConnectAccount


def save_network_connect_accounts(filepath):

    data = [account.to_dict() for account in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_network_connect_accounts(filepath):

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            raw = file.read()
    except FileNotFoundError:
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = _recover_partial_array(raw)
        print(
            "WARNING: hub/storage/network_connect_accounts.json was corrupt "
            "or truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    for account_data in data:
        registry.add(NetworkConnectAccount.from_dict(account_data))

    registry.id_generator.recover_from(registry.list_all())


def _recover_partial_array(text):
    """Mirrors hub/hub_core/dealer_storage.py's _recover_partial_array exactly."""

    close = text.rfind("}")

    while close != -1:

        candidate = text[:close + 1] + "]"

        try:
            recovered = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            close = text.rfind("}", 0, close)
            continue

        if isinstance(recovered, list):
            return recovered

        return []

    return []
