"""
NXTDeal Hub -- persistence for the per-dealer onboarding-checklist registry
(hub/storage/dealer_onboarding.json). Same atomic-write + truncated-JSON-
recovery convention as hub/hub_core/dealer_modules_storage.py / hub/hub_core/
dealer_storage.py -- temp file + os.replace(), best-effort salvage of a
truncated top-level array on load so a corrupt file can never block the Hub
from booting.

A SEPARATE file from hub/storage/dealers.json / dealer_modules.json /
feature_flags.json on purpose, same "own concern, own file" convention every
other Hub sub-registry in this codebase already follows.
"""

import json
import os

from hub_core.dealer_onboarding import registry, DealerOnboardingStatus


def save_dealer_onboarding(filepath):

    data = [status.to_dict() for status in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_onboarding(filepath):

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
            "WARNING: hub/storage/dealer_onboarding.json was corrupt or truncated; "
            "recovered {} record(s) and continued.".format(len(data))
        )

    for status_data in data:
        registry.add(DealerOnboardingStatus.from_dict(status_data))


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
