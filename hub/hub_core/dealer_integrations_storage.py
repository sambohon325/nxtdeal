"""
NXTDeal Hub -- persistence for the per-dealer Integrations Center registry
(hub/storage/dealer_integrations.json). Same atomic-write + truncated-JSON-
recovery convention as hub/hub_core/dealer_modules_storage.py -- temp file +
os.replace(), best-effort salvage of a truncated top-level array on load so a
corrupt file can never block the Hub from booting.

A SEPARATE file from hub/storage/dealers.json on purpose, same reasoning every
other Hub sub-registry in this codebase already follows.
"""

import json
import os

from hub_core.dealer_integrations import registry, DealerIntegration


def save_dealer_integrations(filepath):

    data = [record.to_dict() for record in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_integrations(filepath):

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
            "WARNING: hub/storage/dealer_integrations.json was corrupt or "
            "truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    for record_data in data:
        registry.add(DealerIntegration.from_dict(record_data))

    registry.recover_counter()


def _recover_partial_array(text):
    """Mirrors hub/hub_core/dealer_modules_storage.py's _recover_partial_array exactly."""

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
