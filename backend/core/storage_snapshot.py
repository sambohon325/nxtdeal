"""
Real, lightweight, read-only storage/database instrumentation for the
Infrastructure & Platform Operations rebuild, slice 2 of 4 (NXTDeal Hub --
Clusters/Databases/Storage/Backups/Disaster Recovery).

Same honesty posture as core/platform_metrics.py (slice 1): this sandbox is
a single tenant process with a single JSON-file-based storage layer -- no
real database replication, no separate analytics warehouse, no AI vector
store. Fabricating CPU/replication-lag/multi-node storage telemetry would
be a materially different, riskier kind of dishonesty than this codebase's
"simulate a real market/peer-data gap, disclose it" policy (session 110) --
that policy covers external data this system genuinely can't obtain,
NOT operational/infrastructure telemetry a real person could act on.

What IS real and buildable: this process's own actual file sizes and real
entity/relationship/event/credential counts, right off disk -- exactly what
a real "Databases"/"Storage" screen needs to be honest rather than fake.

Deliberately reports counts only, never file CONTENTS -- credential_count
is a plain integer (how many employees have a login on file), not a single
username/hash. Nothing here is more sensitive than core/platform_metrics.py's
own request counters, so it's exposed through the identical
DEALEROS_NETWORK_KEY server-to-server gate (see
core/storage_snapshot_network_api.py).
"""

import json
import os
from datetime import datetime, timezone

from core.dealeros import ledger
from core.storage_paths import (
    GRAPH_PATH,
    AUDIT_PATH,
    CREDENTIALS_PATH,
    uploads_dir,
    backups_dir,
    storage_dir,
)


def _safe_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _safe_mtime_iso(path):
    try:
        return datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc
        ).isoformat()
    except OSError:
        return None


def _credential_count():
    """A plain count of employees with a login on file -- deliberately NOT
    reading usernames, password hashes, or anything beyond the top-level key
    count of the real credentials.json dict."""

    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        return len(data) if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _audit_event_count():
    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        return len(data) if isinstance(data, list) else None
    except (OSError, ValueError):
        return None


def _dir_summary(directory):
    """Real file count + total byte size for every regular file directly
    inside `directory` (non-recursive -- every real directory this module
    scans, uploads/backups, is flat). Returns zeros, not an error, for a
    directory that doesn't exist yet (e.g. no chat attachment has ever been
    uploaded on a fresh tenant) -- an honest, real "nothing here yet," not a
    fabricated non-zero placeholder."""

    if not os.path.isdir(directory):
        return {"file_count": 0, "total_size_bytes": 0, "latest_file": None, "latest_modified_at": None}

    entries = []
    for name in os.listdir(directory):
        full_path = os.path.join(directory, name)
        if os.path.isfile(full_path):
            entries.append((name, full_path))

    total_size = 0
    latest_name = None
    latest_mtime = -1

    for name, full_path in entries:
        size = _safe_size(full_path) or 0
        total_size += size
        mtime = os.path.getmtime(full_path) if os.path.exists(full_path) else -1
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_name = name

    return {
        "file_count": len(entries),
        "total_size_bytes": total_size,
        "latest_file": latest_name,
        "latest_modified_at": (
            datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
            if latest_mtime >= 0
            else None
        ),
    }


def get_storage_snapshot():
    """Real, aggregate, non-PII storage/database facts about THIS tenant
    process's own storage directory (backend/core/storage_paths.py's
    storage_dir() -- "storage" for today's one real dealer, or
    "storage/tenants/{dealer_id}" for a provisioned tenant). No PII, no raw
    credential data, no entity content -- counts and sizes only."""

    entity_count = len(ledger.entities)
    relationship_count = len(ledger.relationships)

    uploads_summary = _dir_summary(uploads_dir())
    backups_summary = _dir_summary(backups_dir())

    return {
        "storage_dir": storage_dir(),
        "graph_json": {
            "size_bytes": _safe_size(GRAPH_PATH),
            "entity_count": entity_count,
            "relationship_count": relationship_count,
            "last_modified_at": _safe_mtime_iso(GRAPH_PATH),
        },
        "audit_json": {
            "size_bytes": _safe_size(AUDIT_PATH),
            "event_count": _audit_event_count(),
            "last_modified_at": _safe_mtime_iso(AUDIT_PATH),
        },
        "credentials_json": {
            "size_bytes": _safe_size(CREDENTIALS_PATH),
            "credential_count": _credential_count(),
        },
        "uploads": uploads_summary,
        "backups": backups_summary,
        "note": (
            "This tenant's REAL, and only, data store is a set of plain "
            "JSON files on disk (graph.json/audit.json/credentials.json) "
            "plus flat file directories for uploads/backups -- there is no "
            "separate Replica, Analytics, Warehouse, or AI Data Store "
            "anywhere in this deployment; every read and write in this "
            "codebase goes through this one in-memory ledger, persisted to "
            "this one graph.json. Sizes/counts above are real, read "
            "directly off disk at request time, never fabricated or "
            "simulated."
        ),
    }
