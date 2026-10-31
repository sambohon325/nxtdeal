"""
NXTDeal Hub -- persistence for the per-dealer AI Management snapshot registry
(hub/storage/dealer_ai_snapshots.json). Same atomic-write + truncated-JSON-
recovery convention as every other Hub sub-registry.
"""

import json
import os

from hub_core.dealer_ai_management import registry, DealerAiSnapshot


def save_dealer_ai_snapshots(filepath):

    data = [snapshot.to_dict() for snapshot in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_ai_snapshots(filepath):

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
            "WARNING: hub/storage/dealer_ai_snapshots.json was corrupt or "
            "truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    for snapshot_data in data:
        registry.add(DealerAiSnapshot.from_dict(snapshot_data))


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
