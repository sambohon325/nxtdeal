"""
NXTDeal Hub -- persistence for the feature-flag override registry
(hub/storage/feature_flags.json). Same atomic-write + truncated-JSON-recovery
convention as every other Hub sub-registry (hub/hub_core/dealer_storage.py /
hub/hub_core/network_snapshot_storage.py / hub/hub_core/dealer_modules_storage.py) --
temp file + os.replace(), best-effort salvage of a truncated array on load.

A SEPARATE file from hub/storage/dealers.json, same "distinct concern, own
file, one bad write can't corrupt the other" reasoning as every other Hub
sub-registry.
"""

import json
import os

from hub_core.feature_flags import registry, FeatureFlagOverride


def save_feature_flags(filepath):

    data = [override.to_dict() for override in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_feature_flags(filepath):

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
            "WARNING: hub/storage/feature_flags.json was corrupt or truncated; "
            "recovered {} complete override(s) and continued.".format(len(data))
        )

    for override_data in data:
        registry.add(FeatureFlagOverride.from_dict(override_data))

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
