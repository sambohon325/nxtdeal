"""
NXTDeal Hub -- persistence for the Backups honest-manual log
(hub/storage/dealer_backups_log.json). Same atomic-write + truncated-JSON-
recovery convention as hub/hub_core/dealer_integrations_storage.py.
"""

import json
import os

from hub_core.dealer_backups import registry, DealerBackupLogEntry


def save_dealer_backups_log(filepath):

    data = [entry.to_dict() for entry in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_backups_log(filepath):

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
            "WARNING: hub/storage/dealer_backups_log.json was corrupt or "
            "truncated; recovered {} complete record(s) and continued.".format(len(data))
        )

    if not isinstance(data, list):
        raise ValueError("Backup log must contain a list of entries")
    staged = []
    seen = set()
    for entry_data in data:
        if (not isinstance(entry_data, dict) or
                any(not isinstance(entry_data.get(key), str) or not entry_data[key].strip()
                    for key in ("log_id", "dealer_id"))):
            raise ValueError("Backup log contains an invalid entry")
        if entry_data["log_id"] in seen:
            raise ValueError("Backup log contains duplicate entry IDs")
        seen.add(entry_data["log_id"])
        staged.append(DealerBackupLogEntry.from_dict(entry_data))

    # Parse and validate the complete candidate before changing live registry state.
    for entry in staged:
        registry.add(entry)

    registry.recover_counter()


def _recover_partial_array(text):
    """Mirrors hub/hub_core/dealer_integrations_storage.py's
    _recover_partial_array exactly."""

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
