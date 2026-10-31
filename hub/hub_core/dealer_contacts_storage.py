"""
NXTDeal Hub -- persistence for the per-dealer additional-contacts registry
(hub/storage/dealer_contacts.json). Same atomic-write + truncated-JSON-
recovery + id-counter-recovery convention as hub/hub_core/dealer_integrations_storage.py.
"""

import json
import os

from hub_core.dealer_contacts import registry, DealerContact


def save_dealer_contacts(filepath):

    data = [contact.to_dict() for contact in registry.contacts.values()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_contacts(filepath):

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
            "WARNING: hub/storage/dealer_contacts.json was corrupt or "
            "truncated; recovered {} record(s) and continued.".format(len(data))
        )

    for item in data:
        registry.add(DealerContact.from_dict(item))

    registry.recover_counter()


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
