"""
core/data_backup.py -- Administration's "Data Management" item (Administration
Control Center rebuild, continued): real per-entity-type CSV export and a real
graph.json snapshot/backup/restore action.

Export is genuinely real: `export_entity_type_csv()` writes a real CSV of every
entity of a given type currently on the graph (flattening each entity's own
attributes dict into columns) -- useful today (a real admin can pull a real CSV
of every Vendor/Customer/Vehicle/etc.), not a fabricated capability.

Backup/restore wraps the SAME `core/storage.py` save_graph/load_graph functions
every other module in this codebase already depends on -- a "backup" is a real
timestamped copy of the tenant's own storage/graph.json living in
storage/backups/ (core/storage_paths.py's backups_dir(), tenant-aware), and
"restore" is a real file copy back over the live graph.json followed by a real
replacement of the in-memory graph with the preflight-parsed snapshot. A DataBackup entity is
just the real, listable record of that file (filename/size/who/when) -- the
snapshot itself is a plain file on disk, not reinvented as graph data.

Honest scope note: this is NOT a scheduled/automatic backup system (no such
scheduler exists here, same "explicit human action, not a background job"
precedent this codebase's other near-miss automation asks -- e.g. Payments'
auto-draft "run due drafts now" -- already established) -- an admin triggers a
backup explicitly via create_backup().
"""

import csv
import io
import json
import os
import shutil
import tempfile
from uuid import uuid4
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DATA_BACKUP

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, backups_dir
from core.spreadsheet_export import spreadsheet_cell


def _now():
    return datetime.now(timezone.utc).isoformat()


# --- CSV export ---

def export_entity_type_csv(entity_type):
    """Returns (filename, csv_text) for every entity of `entity_type` currently
    on the graph. Column set is the union of every attribute key seen across
    all matching entities (some entities of the same type carry slightly
    different attribute sets, e.g. a historical CSV-imported record vs. one
    created through the live app) -- missing values render as an empty cell
    rather than erroring."""

    entities = [e for e in ledger.get_all().values() if e.entity_type == entity_type]
    if not entities:
        return None, {"error": f"No entities of type '{entity_type}' exist on this graph."}

    columns = ["id"]
    seen = set(columns)
    for e in entities:
        for key in e.attributes:
            if key not in seen:
                seen.add(key)
                columns.append(key)

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow([spreadsheet_cell(key) for key in columns])
    for e in entities:
        row = {"id": e.id}
        for key in columns[1:]:
            value = e.attributes.get(key)
            row[key] = json.dumps(value) if isinstance(value, (dict, list)) else value
        writer.writerow([spreadsheet_cell(row.get(key)) for key in columns])

    filename = f"{entity_type}_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return filename, buffer.getvalue()


def list_exportable_entity_types():
    """Every entity type actually present on the graph right now, with a real
    count -- so the frontend offers a real, populated list, not a guess."""

    counts = {}
    for e in ledger.get_all().values():
        counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


# --- Backup / restore ---

def create_backup(created_by, label=""):
    directory = backups_dir()
    os.makedirs(directory, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"graph_{timestamp}_{uuid4().hex}.json"
    dest_path = os.path.join(directory, filename)

    if not os.path.exists(GRAPH_PATH):
        return {"error": f"No graph file exists at '{GRAPH_PATH}' to back up."}

    # Never overwrite a prior recovery point, even for same-second requests.
    # Exclusive creation also fails safely if a generated name already exists.
    with open(dest_path, "xb") as destination:
        try:
            with open(GRAPH_PATH, "rb") as source:
                shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        except Exception:
            destination.close()
            os.unlink(dest_path)
            raise
    from core.loyalty_program import backup_database
    loyalty_path = backup_database(os.path.join(directory, filename.replace("graph_", "loyalty_").replace(".json", ".sqlite3")))
    size_bytes = os.path.getsize(dest_path)

    backup_id = id_generator.generate("BKUP")
    entity = Entity(
        id=backup_id,
        entity_type=DATA_BACKUP,
        attributes={
            "filename": filename,
            "path": dest_path,
            "loyalty_path": loyalty_path,
            "size_bytes": size_bytes,
            "label": label,
            "created_by": created_by,
            "created_at": _now(),
            "restored_at": None,
            "restored_by": None,
        },
    )
    previous = ledger.get_entity(backup_id)
    ledger.add_entity(entity)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        # Keep the completed recovery file, but do not advertise an unrecorded
        # backup as successfully registered. IDs remain consumed for retry.
        if ledger.get_entity(backup_id) is entity:
            if previous is None:
                ledger.entities.pop(backup_id, None)
            else:
                ledger.entities[backup_id] = previous
        raise
    return {"id": entity.id, **entity.attributes}


def list_backups():
    backups = [e for e in ledger.get_all().values() if e.entity_type == DATA_BACKUP]
    backups.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in backups]


def restore_backup(backup_id, restored_by):
    from core.loyalty_program import configured
    if configured():
        return {"error": "Loyalty accounting is active. Restore the graph and its paired loyalty database together during maintenance; graph-only restore is disabled."}
    entity = ledger.get_entity(backup_id)
    if not entity or entity.entity_type != DATA_BACKUP:
        return {"error": f"Backup '{backup_id}' not found"}

    source_path = entity.attributes.get("path")
    if not source_path or not os.path.exists(source_path):
        return {"error": f"Backup file for '{backup_id}' no longer exists on disk."}

    # Stage beside the live file, parse those exact bytes, then replace it.
    # Copy/validation failures cannot truncate the live recovery target.
    from core.json_graph_repository import JsonGraphRepository

    class RestoreRepository(JsonGraphRepository):
        def add_entity(self, candidate):
            # The general loader overwrites duplicate IDs. A recovery snapshot
            # must not silently discard one of two conflicting records.
            if candidate.id in self.entities:
                raise ValueError("Duplicate entity ID in recovery snapshot")
            super().add_entity(candidate)

    staged_path = None
    try:
        descriptor, staged_path = tempfile.mkstemp(
            prefix=".restore-", suffix=".json", dir=os.path.dirname(os.path.abspath(GRAPH_PATH)))
        with os.fdopen(descriptor, "wb") as destination:
            with open(source_path, "rb") as source:
                shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        try:
            restored = RestoreRepository(ledger.tenant)
            if not restored.load(staged_path):
                return {"error": "Backup file is unavailable; live data was not changed."}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return {"error": "Backup file could not be validated; live data was not changed."}
        os.replace(staged_path, GRAPH_PATH)
        staged_path = None
    finally:
        if staged_path is not None:
            os.unlink(staged_path)
    # Restore replaces the graph; the general legacy loader merges/appends.
    # Install the already-parsed snapshot so repeated restores cannot retain
    # post-snapshot entities or duplicate relationships in memory.
    ledger.entities = restored.entities
    ledger.relationships = restored.relationships
    from core.storage import _recover_id_counters
    _recover_id_counters()

    # Re-fetch the entity after replacement (the snapshot replaces the in-memory
    # ledger wholesale) so this restore record itself survives the restore --
    # a restore that overwrote itself out of existence would be a real bug.
    restored_entity = ledger.get_entity(backup_id)
    if restored_entity:
        restored_entity.attributes["restored_at"] = _now()
        restored_entity.attributes["restored_by"] = restored_by
        save_graph(GRAPH_PATH)
        return {"id": restored_entity.id, **restored_entity.attributes}

    return {
        "warning": (
            f"Restored graph.json from '{backup_id}', but that backup predates "
            "this DataBackup record's own creation and it no longer exists in the "
            "restored graph -- the restore itself succeeded."
        )
    }
