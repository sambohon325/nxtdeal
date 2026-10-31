"""
NXTDeal Hub -- persistence for the per-dealer module-toggle registry
(hub/storage/dealer_modules.json). Same atomic-write + truncated-JSON-recovery
convention as hub/hub_core/dealer_storage.py / hub/hub_core/network_snapshot_storage.py
-- temp file + os.replace(), best-effort salvage of a truncated top-level array
on load so a corrupt file can never block the Hub from booting.

A SEPARATE file from hub/storage/dealers.json on purpose, same reasoning every
other Hub sub-registry in this codebase already follows: module toggles are a
distinct concern from the core dealer record, and keeping them in their own
file means a bad write to one can never corrupt the other.
"""

import json
import os

from hub_core.dealer_modules import registry, DealerModuleConfig


def save_dealer_modules(filepath):

    data = [config.to_dict() for config in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_modules(filepath):

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
            "WARNING: hub/storage/dealer_modules.json was corrupt or truncated; "
            "recovered {} complete record(s) and continued.".format(len(data))
        )

    for config_data in data:
        registry.add(DealerModuleConfig.from_dict(config_data))


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
