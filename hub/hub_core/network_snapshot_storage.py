"""
NXTDeal Hub (2026-07-16) -- persistence for the anonymized network snapshot registry.
Same atomic-write + truncated-JSON-recovery convention as hub/hub_core/dealer_storage.py
(temp file + os.replace(), best-effort salvage of a truncated array on load).

hub/storage/network_snapshots.json is a SEPARATE file from hub/storage/dealers.json on
purpose -- keeping the anonymized metrics store physically separate from the
identifiable dealer registry is a small but real part of the "not even we can tell
whose data it is" posture: there's no single file an engineer could open to see both a
dealer's name and their real numbers side by side.
"""

import json
import os

from hub_core.network_snapshot import registry, NetworkSnapshot


def save_network_snapshots(filepath):

    data = [snapshot.to_dict() for snapshot in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_network_snapshots(filepath):

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
            "WARNING: hub/storage/network_snapshots.json was corrupt or truncated; "
            "recovered {} complete snapshot(s) and continued.".format(len(data))
        )

    for snapshot_data in data:
        registry.upsert(NetworkSnapshot.from_dict(snapshot_data))


def _recover_partial_array(text):
    """Mirrors hub/hub_core/dealer_storage.py's _recover_partial_array exactly -- same
    truncated-top-level-array salvage strategy."""

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
