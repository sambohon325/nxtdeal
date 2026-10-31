"""
NXTDeal Hub (session 50) -- persistence for the dealer registry, matching backend/core/
storage.py's atomic-write convention (temp file + os.replace()) exactly, since this file
(hub/storage/dealers.json) is just as boot-critical to the Hub as graph.json is to a
tenant backend.
"""

import json
import os

from hub_core.dealer_registry import registry
from hub_core.dealer import Dealer


def save_dealers(filepath):

    data = [dealer.to_dict() for dealer in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealers(filepath):

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            raw = file.read()
    except FileNotFoundError:
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Same reasoning as backend/core/audit_storage.py's _recover_partial_object --
        # a truncated dealers.json must never stop the Hub from booting. dealers.json is
        # a flat JSON array here (not an object), so the salvage is simpler: trim back
        # to the last complete top-level record.
        data = _recover_partial_array(raw)
        print(
            "WARNING: hub/storage/dealers.json was corrupt or truncated; "
            "recovered {} complete dealer records and continued.".format(len(data))
        )

    for dealer_data in data:
        registry.add(Dealer.from_dict(dealer_data))

    registry.id_generator.recover_from(registry.list_all())


def _recover_partial_array(text):
    """Best-effort salvage of a truncated JSON array of dealer records. Mirrors
    backend/core/audit_storage.py's _recover_partial_object, adapted for a top-level
    array instead of a top-level object."""

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
