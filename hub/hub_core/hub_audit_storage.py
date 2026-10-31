"""
NXTDeal Hub -- persistence for the Hub-side audit log
(hub/storage/hub_audit.json). Same atomic-write + truncated-JSON-recovery
convention as every other Hub sub-registry (hub/hub_core/dealer_onboarding_storage.py,
hub/hub_core/dealer_modules_storage.py) -- temp file + os.replace(), best-effort
salvage of a truncated top-level array on load.
"""

import json
import os

from hub_core.hub_audit import hub_audit_log, HubAuditEvent


def save_hub_audit_log(filepath):

    data = [_raw(event) for event in hub_audit_log.get_all()]

    tmp_path = filepath + ".tmp"

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(tmp_path, filepath)


def _raw(event):
    """Full round-trippable shape (unlike HubAuditEvent.to_dict(), which adds
    derived category/category_label fields for API responses) -- stores only
    the real stored fields, category is always re-derived on load."""

    return {
        "id": event.id,
        "event_type": event.event_type,
        "dealer_id": event.dealer_id,
        "actor": event.actor,
        "summary": event.summary,
        "details": event.details,
        "timestamp": event.timestamp,
    }


def load_hub_audit_log(filepath):

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
            "WARNING: hub/storage/hub_audit.json was corrupt or truncated; "
            "recovered {} record(s) and continued.".format(len(data))
        )

    events = [HubAuditEvent.from_dict(item) for item in data]
    hub_audit_log.load_events(events)


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
