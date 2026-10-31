import hashlib
import json

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Tamper-evidence via hash chaining (security-hardening pass, 2026-07-20, Tier 1
# "Audit Logging" -- meet/exceed a real tamper-evident audit trail). Every event's
# `hash` covers its own content PLUS the previous event's hash, so altering,
# deleting, reordering, or inserting an event anywhere in history changes every
# hash after it -- detectable by recomputing the chain (see
# core/audit_integrity.py's verify_chain()). GENESIS_HASH is the fixed "no prior
# event" anchor the very first real event's prev_hash should equal.
#
# Real, stated limits (same "disclose the actual gap" convention this codebase
# holds everywhere else): this detects retroactive tampering WITHIN one
# audit.json file, and -- paired with audit_integrity.py's separate checkpoint
# file -- detects wholesale replacement/truncation of that file between saves.
# It does NOT provide true immutability against an attacker with write access
# to every file on disk who recomputes the whole chain from scratch (that needs
# write-once/external storage -- a real anchor point outside this process, e.g.
# a WORM store or an external timestamping service -- out of scope for this
# pass, flagged rather than pretended).
GENESIS_HASH = "0" * 64


def _canonical_event_payload(event_id, event_type, entity_id, actor, summary,
                              details, timestamp, prev_hash):
    """Deterministic JSON encoding of exactly the fields that make one event
    what it is (sort_keys=True so field order never changes the hash;
    default=str so any non-JSON-native value in `details` still hashes
    consistently rather than raising)."""

    payload = {
        "id": event_id,
        "event_type": event_type,
        "entity_id": entity_id,
        "actor": actor,
        "summary": summary,
        "details": details,
        "timestamp": timestamp,
        "prev_hash": prev_hash,
    }

    return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")


def compute_event_hash(event_id, event_type, entity_id, actor, summary,
                        details, timestamp, prev_hash):
    """SHA-256 of this event's own content chained to prev_hash -- same
    fast-hash convention core/api_keys.py/core/mfa.py already use for
    high-entropy/structural data (as opposed to core/auth.py's deliberately
    slow PBKDF2 for human-chosen passwords)."""

    payload = _canonical_event_payload(
        event_id, event_type, entity_id, actor, summary, details, timestamp,
        prev_hash
    )

    return hashlib.sha256(payload).hexdigest()


@dataclass
class AuditEvent:
    id: str
    event_type: str
    entity_id: Optional[str]
    actor: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Both computed by AuditLog.record()/load_events(), never set directly by a
    # caller -- default "" means "predates hash chaining" (a real, pre-existing
    # event loaded from an audit.json written before this feature shipped),
    # distinguished from real tampering by core/audit_integrity.py's
    # verify_chain() rather than flagged as broken.
    prev_hash: str = ""
    hash: str = ""


class AuditLog:

    def __init__(self):
        self.events: List[AuditEvent] = []
        self._counter = 0

    def record(
        self,
        event_type,
        summary,
        entity_id=None,
        actor="system",
        details=None
    ):

        self._counter += 1

        event_id = f"AUDIT-{self._counter:05}"
        details = details or {}
        timestamp = datetime.now(timezone.utc).isoformat()
        prev_hash = self.events[-1].hash if self.events else GENESIS_HASH

        # A legacy (unhashed) tail event means we can't honestly claim this
        # new event chains back to real prior history -- still hash-chain it
        # (so everything from here forward is verifiable), anchored on
        # GENESIS_HASH rather than an empty string, since prev_hash is always
        # a real 64-char value once a chain starts.
        if not prev_hash:
            prev_hash = GENESIS_HASH

        event_hash = compute_event_hash(
            event_id, event_type, entity_id, actor, summary, details,
            timestamp, prev_hash
        )

        event = AuditEvent(
            id=event_id,
            event_type=event_type,
            entity_id=entity_id,
            actor=actor,
            summary=summary,
            details=details,
            timestamp=timestamp,
            prev_hash=prev_hash,
            hash=event_hash
        )

        self.events.append(event)

        return event

    def get_all(self):
        return list(self.events)

    def get_for_entity(self, entity_id):
        return [
            event for event in self.events
            if event.entity_id == entity_id
        ]

    def get_by_actor(self, actor):
        return [
            event for event in self.events
            if event.actor == actor
        ]

    def get_by_type(self, event_type):
        return [
            event for event in self.events
            if event.event_type == event_type
        ]

    def reset(self):
        """Clear all events in place (used by tests). Does not touch disk."""

        self.events = []
        self._counter = 0

    def load_events(self, events):
        """Replace in-memory events with a list already loaded from disk
        (used by audit_storage.load_audit_log), preserving the counter so
        newly recorded events don't collide with restored ids. Trusts each
        event's own stored hash/prev_hash verbatim -- recomputing them here
        would defeat the point of a tamper check; core/audit_integrity.py's
        verify_chain() is the real place that recomputation happens."""

        self.events = list(events)

        highest = 0

        for event in self.events:

            try:
                suffix = int(event.id.split("-")[-1])
            except (ValueError, IndexError):
                continue

            highest = max(highest, suffix)

        self._counter = highest


audit_log = AuditLog()
