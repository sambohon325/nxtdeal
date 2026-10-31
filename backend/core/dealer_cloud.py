"""Dealer-owned storage. Rclone is a transport, never a mounted app filesystem.

Operator-provisioned, tenant-specific remotes keep OAuth credentials outside the graph.
Only opaque connection IDs are accepted from browsers. No shell or arbitrary rclone RC.
Backups are encrypted before transfer and verified by a complete remote readback.
"""
import asyncio
from core.worker_io import run_worker_io
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
import zipfile

from core.storage_paths import storage_dir

MAX_ARCHIVE = 128 * 1024 * 1024
MAX_PHOTO = 10 * 1024 * 1024
_lock = threading.Lock()
_transfers = threading.BoundedSemaphore(2)
_task = None


class CloudError(ValueError):
    pass


def connections():
    """Trusted deployment configuration, separate for each tenant process."""
    try:
        data = json.loads(os.getenv("NXTDEAL_CLOUD_CONNECTIONS", "{}"))
        if not isinstance(data, dict):
            raise ValueError()
        for key, row in data.items():
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key):
                raise ValueError()
            if row.get("provider") not in {"google_drive", "onedrive", "dropbox", "s3"}:
                raise ValueError()
            # Remote and root are operator-owned. Browser input cannot override them.
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", row["remote"]):
                raise ValueError()
            if not re.fullmatch(r"[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*", row["root"]):
                raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise CloudError("Cloud connection configuration is invalid.") from None


def db():
    path = Path(storage_dir()) / "cloud-control.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=DELETE")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, started REAL, state TEXT, body TEXT);
      CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY, body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS leases(id INTEGER PRIMARY KEY CHECK(id=1), until REAL NOT NULL);
    """)
    os.chmod(path, 0o600)
    return con


def settings(con):
    row = con.execute("SELECT body FROM settings WHERE id=1").fetchone()
    return json.loads(row[0]) if row else {
        "photo_connection": "", "backup_connection": "", "interval_hours": 24,
        "retention_days": 30, "enabled": False, "public_key": "", "next_run": None,
    }


def transport(connection, action, name, content=None, limit=MAX_ARCHIVE + 1024*1024):
    row = connections().get(connection)
    config = Path(os.getenv("NXTDEAL_RCLONE_CONFIG", ""))
    executable = os.getenv("NXTDEAL_RCLONE_BINARY", "rclone")
    if not row or not config.is_absolute() or not config.is_file() or not shutil.which(executable):
        raise CloudError("Connect this dealer's cloud account before using storage.")
    if action not in {"rcat", "cat"} or not re.fullmatch(r"(?:backups|photos|checks)/[a-zA-Z0-9_.-]+", name):
        raise CloudError("Invalid cloud object.")
    target = f"{row['remote']}:{row['root']}/{name}"
    args = [executable, action, target, "--config", str(config), "--retries", "1",
            "--low-level-retries", "1", "--timeout", "45s", "--contimeout", "15s"]
    if action == "cat":
        args += ["--count", str(limit + 1)]
    # Do not log provider stderr: it can contain paths and credential diagnostics.
    if not _transfers.acquire(blocking=False):
        raise CloudError("Cloud transfer capacity is busy. Try again shortly.")
    try:
        result = subprocess.run(args, input=content, capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CloudError("Cloud transfer failed or timed out; inspect the run before retrying.") from None
    finally:
        _transfers.release()
    if result.returncode or len(result.stdout) > limit:
        raise CloudError("Cloud transfer failed or exceeded its size limit.")
    return result.stdout


def key_from_pem(pem):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    try:
        key = load_pem_public_key(pem.encode())
        if not isinstance(key, RSAPublicKey) or key.key_size < 3072:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise CloudError("Use a dealer-owned RSA public recovery key of at least 3072 bits.") from None


def encrypt_archive(payload, pem):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    key = key_from_pem(pem)
    secret, nonce = os.urandom(32), os.urandom(12)
    wrapped = key.encrypt(secret, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    header = {"format": "nxtdeal-backup-v1", "wrapped_key": base64.b64encode(wrapped).decode(),
              "nonce": base64.b64encode(nonce).decode()}
    aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    return aad + b"\n" + AESGCM(secret).encrypt(nonce, payload, aad)


def archive():
    """File-stable tenant capture; never advertise cross-file transactional consistency.

    SQLite uses its backup API. Credentials/config data are encrypted with the archive.
    External photos are references only. Legacy local uploads are retained in recovery.
    OAuth configuration/recovery private keys must be provisioned outside this directory.
    """
    root = Path(storage_dir()).resolve()
    def files():
        out = []
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if rel.parts[0] in {"backups", ".cache"}:
                continue
            if path.is_symlink():
                raise CloudError("Backup refused: tenant storage contains a symbolic link.")
            if path.is_file() and not path.name.endswith((".tmp", "-wal", "-shm", "-journal")):
                out.append(path)
        return sorted(out)
    paths = files()
    if root / "graph.json" not in paths:
        raise CloudError("No dealership graph exists to back up.")
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    if sum(s[0] for s in before.values()) > MAX_ARCHIVE or len(paths) > 10000:
        raise CloudError("Tenant exceeds this backup worker's capture limit; configure a larger snapshot worker.")
    buffer, manifest, size = io.BytesIO(), [], 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            name = path.relative_to(root).as_posix()
            if path.suffix in {".sqlite", ".sqlite3", ".db"}:
                with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as source, sqlite3.connect(":memory:") as dest:
                    source.backup(dest)
                    data = dest.serialize()
            else:
                with path.open("rb") as stream:
                    data = stream.read(MAX_ARCHIVE + 1)
            size += len(data)
            if size > MAX_ARCHIVE:
                raise CloudError("Backup capture exceeded its size limit.")
            if path.suffix == ".json":
                json.loads(data)  # refuse a partially-written/invalid JSON file
            manifest.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            z.writestr("data/" + name, data)
        if files() != paths or any((p.stat().st_size, p.stat().st_mtime_ns) != before[p] for p in paths):
            raise CloudError("Data changed during capture. Backup was not uploaded; retry when writes are quiet.")
        z.writestr("manifest.json", json.dumps({"format": 1, "captured_at": time.time(),
            "consistency": "file-stable; not a cross-file transaction or system image",
            "external_photo_bytes_included": False, "files": manifest}))
    return buffer.getvalue(), len(manifest)


def status():
    with db() as con:
        value = settings(con)
        rows = con.execute("SELECT * FROM runs ORDER BY started DESC LIMIT 30").fetchall()
    return {"settings": value, "connections": [{"id": k, "provider": r["provider"],
        "label": str(r.get("label", k))[:100], "status": "configured_not_verified"} for k, r in connections().items()],
        "worker_enabled": os.getenv("NXTDEAL_CLOUD_BACKUPS_ENABLED") == "true",
        "runs": [{"id": r["id"], "started": r["started"], "state": r["state"], **json.loads(r["body"])} for r in rows],
        "scope": "Tenant files and app configuration; external image references, not photo copies. No server/OS image.",
        "restore_verified": False}


def configure(values, actor):
    available = connections()
    for field in ("photo_connection", "backup_connection"):
        if values[field] and values[field] not in available:
            raise CloudError("Choose a configured dealer connection.")
    if values["public_key"]:
        key_from_pem(values["public_key"])
    if values["enabled"] and (not values["backup_connection"] or not values["public_key"]):
        raise CloudError("Select a backup connection and recovery public key before scheduling.")
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        values = {**values, "updated_by": actor, "updated_at": time.time(),
                  "next_run": time.time() + values["interval_hours"] * 3600 if values["enabled"] else None}
        if con.execute("SELECT 1 FROM leases WHERE until>?", (time.time(),)).fetchone():
            raise CloudError("A backup is running; wait before changing its destination.")
        con.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (json.dumps(values),))
    return status()


def run_backup(actor="scheduler", due=False):
    if os.getenv("NXTDEAL_CLOUD_BACKUPS_ENABLED") != "true":
        raise CloudError("Cloud backup worker is not activated on this deployment.")
    if not _lock.acquire(blocking=False):
        raise CloudError("A cloud operation is already running.")
    run_id = uuid.uuid4().hex
    started = time.time()
    try:
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            value = settings(con)
            if due and (not value["enabled"] or not value["next_run"] or value["next_run"] > started):
                return None
            if con.execute("SELECT 1 FROM leases WHERE until>?", (started,)).fetchone():
                raise CloudError("Another worker has a backup in progress.")
            if not value["backup_connection"] or not value["public_key"]:
                raise CloudError("Choose a backup destination and recovery public key first.")
            con.execute("INSERT OR REPLACE INTO leases VALUES(1,?)", (started + 3600,))
            con.execute("UPDATE runs SET state='interrupted' WHERE state='running'")
            details = {"actor": actor, "connection": value["backup_connection"], "object": f"backups/{run_id}.nxtbackup"}
            con.execute("INSERT INTO runs VALUES(?,?,?,?)", (run_id, started, "running", json.dumps(details)))
            value["next_run"] = started + value["interval_hours"] * 3600 if value["enabled"] else None
            con.execute("INSERT OR REPLACE INTO settings VALUES(1,?)", (json.dumps(value),))
        try:
            payload, count = archive()
            encrypted = encrypt_archive(payload, value["public_key"])
            details.update(bytes=len(encrypted), files=count, sha256=hashlib.sha256(encrypted).hexdigest())
            # Persist reconciliation evidence before egress: an upload may succeed
            # even if this process dies before readback or the final receipt save.
            with db() as con:
                con.execute("UPDATE runs SET body=? WHERE id=?", (json.dumps(details), run_id))
            transport(value["backup_connection"], "rcat", details["object"], encrypted)
            actual = transport(value["backup_connection"], "cat", details["object"])
            if hashlib.sha256(actual).hexdigest() != details["sha256"]:
                raise CloudError("Remote readback did not match. This backup is not verified.")
            details.update(verified_at=time.time(), retention_review_at=started + value["retention_days"] * 86400,
                           restore_verified=False)
            state = "verified_transfer"
        except Exception:
            state = "failed_or_uncertain"
            details["error"] = "Backup did not verify. A remote object may exist; no automatic retry or deletion was performed."
        with db() as con:
            con.execute("UPDATE runs SET state=?,body=? WHERE id=?", (state, json.dumps(details), run_id))
            con.execute("DELETE FROM leases WHERE id=1")
        return {"id": run_id, "state": state, **details}
    finally:
        _lock.release()


def upload_photo(vehicle_id, content, actor, origin):
    from core.merchandising import _get_vehicle, add_vehicle_image
    if not _get_vehicle(vehicle_id):
        raise CloudError("Vehicle not found.")
    if not content or len(content) > MAX_PHOTO:
        raise CloudError("Choose a JPEG, PNG or WebP photo up to 10 MB.")
    if content.startswith(b"\xff\xd8\xff"):
        mime, ext = "image/jpeg", "jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime, ext = "image/png", "png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        mime, ext = "image/webp", "webp"
    else:
        raise CloudError("Only JPEG, PNG and WebP images are accepted.")
    with db() as con:
        connection = settings(con)["photo_connection"]
    if not connection:
        raise CloudError("An administrator must select dealer-owned photo storage first.")
    photo_id = uuid.uuid4().hex
    name = f"photos/{photo_id}.{ext}"
    transport(connection, "rcat", name, content)
    actual = transport(connection, "cat", name, limit=MAX_PHOTO)
    digest = hashlib.sha256(content).hexdigest()
    if hashlib.sha256(actual).hexdigest() != digest:
        raise CloudError("Photo did not verify in cloud storage; no vehicle reference was added.")
    url = f"{origin}/public/vehicle-photos/{photo_id}"
    result = add_vehicle_image(vehicle_id, url, actor)
    if "error" in result:
        raise CloudError(result["error"])
    with db() as con:
        con.execute("INSERT INTO photos VALUES(?,?)", (photo_id, json.dumps({"connection": connection,
            "object": name, "vehicle_id": vehicle_id, "image_id": result["image"]["id"],
            "mime": mime, "sha256": digest, "created_by": actor, "created_at": time.time()})))
    return result


def read_photo(photo_id):
    from core.dealeros import ledger
    from core.merchandising import _get_vehicle
    with db() as con:
        row = con.execute("SELECT body FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        raise CloudError("Photo not found.")
    item = json.loads(row[0])
    linked = any(r.source_id == item["vehicle_id"] and r.target_id == item["image_id"] and r.relationship_type == "HAS_IMAGE" for r in ledger.get_relationships())
    if not _get_vehicle(item["vehicle_id"]) or not ledger.get_entity(item["image_id"]) or not linked:
        raise CloudError("Photo no longer published.")
    content = transport(item["connection"], "cat", item["object"], limit=MAX_PHOTO)
    if hashlib.sha256(content).hexdigest() != item["sha256"]:
        raise CloudError("Cloud photo changed; add a new verified reference.")
    return content, item["mime"]


async def _loop():
    while True:
        try:
            if os.getenv("NXTDEAL_CLOUD_BACKUPS_ENABLED") == "true":
                await run_worker_io(run_backup, due=True)
        except Exception:
            # No provider output, filesystem paths or credentials in application logs.
            import logging
            logging.getLogger(__name__).warning("Cloud backup worker could not run; inspect backup status.")
        await asyncio.sleep(60)


def start():
    global _task
    if _task is None:
        _task = asyncio.create_task(_loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _task
    task = _task
    if task is not None:
        task.cancel()
        # Retain ownership during thread drain so a repeated start cannot overlap.
        def release(completed):
            global _task
            if _task is completed:
                _task = None
        if task.done():
            release(task)
        else:
            task.add_done_callback(release)
    return task
