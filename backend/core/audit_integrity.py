"""
core/audit_integrity.py -- Tamper-evidence verification for the audit log
(security-hardening pass, 2026-07-20, Tier 1 "Audit Logging").

Two real, distinct checks, both built on core/audit.py's own hash-chain
fields (AuditEvent.prev_hash/hash, GENESIS_HASH, compute_event_hash()):

1. verify_chain() -- walks the in-memory (or a supplied) event list and
   recomputes each event's hash from its own claimed content plus the
   previous event's hash. A mismatch means one of:
     - "content_tampered": this specific event's own fields were altered
       after being recorded (its stored hash no longer matches what its
       content actually hashes to).
     - "broken_link": this event's prev_hash doesn't match the actual hash
       of whatever event precedes it (an event was deleted, reordered, or a
       new one was spliced in without updating the chain correctly).
     - "broken_genesis": the very first event in a chain with no legacy
       history before it doesn't anchor on GENESIS_HASH.
   Events with no hash at all (empty string) predate this feature shipping
   -- reported as "unverifiable_legacy_events", a real, honest gap, not
   flagged as tampering.

2. verify_against_checkpoint() -- compares the currently-loaded chain's real
   tail hash against a separate checkpoint file (write_checkpoint(), called
   automatically by core/audit_storage.py's save_audit_log() on every real
   save). This is what catches WHOLESALE replacement or truncation of
   audit.json between saves -- verify_chain() alone only checks internal
   consistency, so if the whole file were swapped for an entirely different
   (but internally self-consistent) fake chain, verify_chain() would report
   "valid" on its own. The checkpoint is what an attacker would ALSO have to
   forge to hide that swap.

Real, stated limits (same "disclose the actual gap, don't pretend" convention
this codebase holds everywhere else): this is tamper-EVIDENCE, not true
immutability. An attacker with write access to every file on disk who
recomputes the entire chain from scratch (audit.json AND the checkpoint file,
consistently) leaves no internal trace either check can catch -- genuine
immutability needs a write-once/external anchor point (a WORM store, a
separate signing service, an append-only remote log) outside this process,
which is real infrastructure this sandbox doesn't have and is out of scope
for this pass. What IS real: any tampering that ISN'T also accompanied by a
correct, consistent rewrite of the checkpoint file gets caught, and any
tampering with an individual historical event's content (without also
recomputing every hash after it) gets caught by verify_chain() alone.
"""

import json
import os
from datetime import datetime, timezone

from core.audit import GENESIS_HASH, compute_event_hash, audit_log
from core.storage_paths import storage_path

_CHECKPOINT_FILENAME = "audit_chain_checkpoint.json"


def _checkpoint_path():
    """Resolved fresh on every call (matching core/storage_paths.py's own
    documented convention) so a tenant switch mid-process still checkpoints
    the right directory."""

    return storage_path(_CHECKPOINT_FILENAME)


def verify_chain(events=None):
    """Recomputes and checks the hash chain across `events` (defaults to
    every event currently loaded in-memory). Returns a real, structured
    report -- never raises on a broken chain, since this needs to run safely
    as a read-only diagnostic even against a genuinely tampered log."""

    events = list(events) if events is not None else audit_log.get_all()

    issues = []
    verified_count = 0
    unverifiable_count = 0
    expected_prev = None
    seen_first_hashed_event = False

    for event in events:

        if not event.hash:
            # Predates hash chaining entirely -- can't verify its content,
            # and can't know what a "real" prev_hash chain looked like
            # before this feature shipped. Not tampering.
            unverifiable_count += 1
            continue

        if expected_prev is None:
            # First hash-chained event we've encountered. If nothing
            # unverifiable came before it, this really is the start of the
            # chain and must anchor on GENESIS_HASH -- a real, meaningfully
            # stronger check on the common case (today's production
            # audit.json, which starts fresh at event 1 under this feature).
            # If legacy events DID precede it, we can't hold it to that
            # standard -- just trust its own claimed prev_hash as the new
            # anchor point going forward.
            if unverifiable_count == 0 and event.prev_hash != GENESIS_HASH:
                issues.append({
                    "event_id": event.id,
                    "issue_type": "broken_genesis",
                    "detail": (
                        "This is the first event in the log, but its "
                        "prev_hash does not equal the real genesis anchor -- "
                        "the chain may have been replaced or forged."
                    )
                })

            expected_prev = event.prev_hash

        elif event.prev_hash != expected_prev:
            issues.append({
                "event_id": event.id,
                "issue_type": "broken_link",
                "detail": (
                    "prev_hash does not match the actual hash of the "
                    "preceding event -- an event may have been deleted, "
                    "reordered, or inserted."
                )
            })

        recomputed = compute_event_hash(
            event.id, event.event_type, event.entity_id, event.actor,
            event.summary, event.details, event.timestamp, event.prev_hash
        )

        if recomputed != event.hash:
            issues.append({
                "event_id": event.id,
                "issue_type": "content_tampered",
                "detail": (
                    "Recomputing this event's hash from its own stored "
                    "fields does not match its stored hash -- this event's "
                    "content was altered after being recorded."
                )
            })
        else:
            verified_count += 1

        expected_prev = event.hash

    return {
        "valid": len(issues) == 0,
        "total_events": len(events),
        "verified_events": verified_count,
        "unverifiable_legacy_events": unverifiable_count,
        "issues": issues
    }


def write_checkpoint(audit_filepath=None):
    """Persists the chain's real current tail hash to a small, separate
    file. Called automatically by core/audit_storage.py's save_audit_log()
    on every real save -- not usually called directly. Atomic write (temp
    file + os.replace()), matching every other storage write in this
    codebase, so an interrupted checkpoint write can never leave a
    truncated/corrupt checkpoint file behind."""

    events = audit_log.get_all()
    tail = events[-1] if events else None

    checkpoint = {
        "event_count": len(events),
        "last_event_id": tail.id if tail else None,
        "last_hash": tail.hash if tail else GENESIS_HASH,
        "checkpointed_at": datetime.now(timezone.utc).isoformat()
    }

    path = _checkpoint_path()
    tmp_path = path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(checkpoint, file, indent=4)

    os.replace(tmp_path, path)

    return checkpoint


def read_checkpoint():
    """The last-persisted checkpoint, or None if it's never been written
    (a brand new tenant, or one provisioned before this feature shipped)."""

    path = _checkpoint_path()

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def verify_against_checkpoint():
    """Compares the currently-loaded chain's real tail against the last
    persisted checkpoint. This is the check that catches a whole-file
    replacement or truncation of audit.json between saves -- verify_chain()
    alone can't, since a wholesale swap for a different but internally
    self-consistent fake chain would still "pass" that check on its own."""

    events = audit_log.get_all()
    tail = events[-1] if events else None
    current_hash = tail.hash if tail else GENESIS_HASH
    current_count = len(events)

    checkpoint = read_checkpoint()

    if checkpoint is None:

        if current_count == 0:
            # Nothing has ever been recorded and no checkpoint exists --
            # genuinely the initial state, not a red flag.
            return {
                "status": "ok",
                "detail": "No audit history and no checkpoint yet -- initial state."
            }

        return {
            "status": "checkpoint_missing",
            "detail": (
                f"{current_count} event(s) are loaded in memory but no "
                "checkpoint file exists on disk -- either this is the "
                "first save since the feature shipped, or the checkpoint "
                "file was deleted/never restored alongside a backup."
            )
        }

    if checkpoint.get("last_hash") == current_hash and checkpoint.get("event_count") == current_count:
        return {
            "status": "ok",
            "detail": "Currently loaded chain tail matches the last persisted checkpoint.",
            "checkpoint": checkpoint
        }

    return {
        "status": "checkpoint_mismatch",
        "detail": (
            "The currently loaded audit chain's tail does not match the "
            "last persisted checkpoint -- audit.json may have been "
            "replaced, restored from an older backup, or edited outside "
            "of the normal save_audit_log() path since the checkpoint was "
            "last written."
        ),
        "checkpoint": checkpoint,
        "current_event_count": current_count,
        "current_last_hash": current_hash
    }


def full_integrity_report():
    """The combined, real answer to "is the audit log trustworthy right
    now" -- both checks composed into one payload. Backing
    GET /audit/integrity."""

    chain_result = verify_chain()
    checkpoint_result = verify_against_checkpoint()

    overall_ok = chain_result["valid"] and checkpoint_result["status"] == "ok"

    return {
        "overall_status": "ok" if overall_ok else "issues_detected",
        "chain": chain_result,
        "checkpoint": checkpoint_result
    }
