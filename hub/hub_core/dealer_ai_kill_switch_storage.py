"""
NXTDeal Hub -- persistence for the AI Kill Switch emergency-push action log
(hub/storage/dealer_ai_kill_switch_actions.json). Same atomic-write +
truncated-JSON-recovery convention as hub_core/dealer_backups_storage.py.
"""

import json
import os

from hub_core.dealer_ai_kill_switch import registry, DealerKillSwitchAction


def save_dealer_ai_kill_switch_actions(filepath):

    data = [action.to_dict() for action in registry.list_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def load_dealer_ai_kill_switch_actions(filepath):

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
            "WARNING: hub/storage/dealer_ai_kill_switch_actions.json was "
            "corrupt or truncated; recovered {} complete record(s) and "
            "continued.".format(len(data))
        )

    for action_data in data:
        registry.add(DealerKillSwitchAction.from_dict(action_data))

    registry.recover_counter()


def _recover_partial_array(text):
    """Mirrors hub_core/dealer_backups_storage.py's _recover_partial_array
    exactly."""

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
