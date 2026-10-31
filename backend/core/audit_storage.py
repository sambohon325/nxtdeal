import json
import os

from core.audit import AuditEvent, audit_log


def save_audit_log(filepath):

    from core.storage import demo_persistence_disabled
    if demo_persistence_disabled():  # demo tenant never persists
        return

    data = []

    for event in audit_log.get_all():

        data.append({
            "id": event.id,
            "event_type": event.event_type,
            "entity_id": event.entity_id,
            "actor": event.actor,
            "summary": event.summary,
            "details": event.details,
            "timestamp": event.timestamp,
            "prev_hash": event.prev_hash,
            "hash": event.hash
        })

    # Write atomically: dump to a temp file in the same directory, then os.replace()
    # (atomic on the same filesystem). A process killed / timed out mid-write can then
    # only ever leave the stale-but-complete previous file or the temp file behind,
    # never a truncated audit.json — which is what left the file corrupt and blocked
    # the whole backend from booting in a prior session.

    # Ensure the tenant's storage dir exists — a fresh tenant may audit an action before any
    # save_graph has created it (same hardening save_graph already has), else this 500s.
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)

    tmp_path = filepath + ".tmp"

    with open(
        tmp_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )

    os.replace(
        tmp_path,
        filepath
    )

    # Tamper-evidence checkpoint (security-hardening pass, 2026-07-20) -- a
    # small, separate file recording the chain's real tail hash every time
    # the audit log is actually persisted. Deliberately a second file, not a
    # field inside audit.json itself: an attacker who edits/replaces
    # audit.json wholesale (not just one event inside it) would need to also
    # recompute and rewrite this checkpoint to hide it, since
    # core/audit_integrity.py's verify_against_checkpoint() compares the
    # currently-loaded chain's tail hash against whatever this file says the
    # tail SHOULD be as of the last real save. Best-effort: if this write
    # fails for any reason, the real audit.json write above has already
    # succeeded and is not rolled back -- a missing/stale checkpoint degrades
    # to "can't confirm continuity," not "audit logging is broken."
    try:
        from core.audit_integrity import write_checkpoint
        write_checkpoint(filepath)
    except Exception:
        pass


def _recover_partial_array(text):
    """Best-effort salvage of a truncated JSON array of objects.

    Matches the exact corruption seen when a write is interrupted: a well-formed
    prefix of complete `{...}` entries followed by a dangling `},` (or a half-written
    final entry) with no closing `]`. Trims back to the last complete top-level
    object and closes the array, so every fully-written audit entry is recovered and
    only the partial trailing one is dropped. Returns [] if nothing is salvageable."""

    last_close = text.rfind("}")

    if last_close == -1:

        return []

    candidate = text[:last_close + 1] + "]"

    try:

        return json.loads(candidate)

    except (json.JSONDecodeError, ValueError):

        return []


def load_audit_log(filepath):

    try:

        with open(
            filepath,
            "r",
            encoding="utf-8"
        ) as file:

            raw = file.read()

    except FileNotFoundError:

        return

    try:

        data = json.loads(raw)

    except (json.JSONDecodeError, ValueError):

        # A truncated / corrupt audit log must never stop the backend from booting.
        # Recover whatever complete entries survived and carry on.
        data = _recover_partial_array(raw)

        print(
            "WARNING: storage/audit.json was corrupt or truncated; "
            "recovered {} complete audit entries and continued.".format(len(data))
        )

    events = [
        AuditEvent(
            id=item["id"],
            event_type=item["event_type"],
            entity_id=item.get("entity_id"),
            actor=item.get("actor", "system"),
            summary=item.get("summary", ""),
            details=item.get("details", {}),
            timestamp=item.get("timestamp"),
            # Absent on any event recorded before the hash-chain feature
            # shipped -- "" is the real, documented "unverifiable legacy
            # event" signal core/audit_integrity.py's verify_chain() checks
            # for, not a bug.
            prev_hash=item.get("prev_hash", ""),
            hash=item.get("hash", "")
        )
        for item in data
    ]

    audit_log.load_events(events)
