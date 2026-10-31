"""
Persistence for dealer infrastructure-provisioning state (2026-07-24) — a flat
{dealer_id: record} store at storage/provisioning.json, mirroring dealer_storage. A record
tracks a dealer's Coolify app uuids, public URLs, status (provisioning/deploying/failed), any
warnings, and the last error. Kept separate from the Dealer dataclass so provisioning state can
evolve without touching the registry schema. Atomic write + tolerant load, same as the others.
"""

import json
import os

_records = {}

PROVISIONING_PATH = "storage/provisioning.json"


def get(dealer_id):
    return _records.get(dealer_id)


def put(dealer_id, record):
    _records[dealer_id] = record


def all_records():
    return dict(_records)


def reset():
    _records.clear()


def save_provisioning(filepath):
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_records, f, indent=4)
    os.replace(tmp, filepath)


def load_provisioning(filepath):
    global _records
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = {}
    _records = data if isinstance(data, dict) else {}
