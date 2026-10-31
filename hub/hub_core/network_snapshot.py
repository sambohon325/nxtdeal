"""
NXTDeal Hub (2026-07-16) -- the anonymized-snapshot record + in-memory registry.

Deliberately keyed ONLY by pseudonym, never dealer_id -- this is a genuinely separate
store from hub/hub_core/dealer_registry.py's Dealer records, not a second index into the
same data. See hub/hub_core/network_collector.py's module docstring for the full privacy
design and backend/core/network_pseudonym.py for where the pseudonym itself comes from.

Mirrors hub/hub_core/dealer_registry.py's DealerRegistry singleton pattern (plain dict,
imported instance, no ORM) -- same convention this whole codebase uses throughout.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict


@dataclass
class NetworkSnapshot:
    pseudonym: str
    submitted_at: str
    collected_at: str
    departments: Dict

    def to_dict(self):
        return {
            "pseudonym": self.pseudonym,
            "submitted_at": self.submitted_at,
            "collected_at": self.collected_at,
            "departments": self.departments,
        }

    @staticmethod
    def from_dict(data):
        return NetworkSnapshot(**data)


class NetworkSnapshotRegistry:
    """Holds only the LATEST snapshot per pseudonym -- a real day-over-day trend store
    (mirroring backend/core/kpi_snapshots.py's approach for a single dealer) is real,
    valuable, future work, deliberately not built this pass. See
    hub/hub_core/network_collector.py's docstring for why."""

    def __init__(self):
        self.snapshots: Dict[str, NetworkSnapshot] = {}

    def upsert(self, snapshot: NetworkSnapshot):
        self.snapshots[snapshot.pseudonym] = snapshot

    def get(self, pseudonym):
        """Added for Network Connect (hub_core/network_connect_api.py) -- looking
        up "my own latest submission" by the pseudonym the caller itself
        holds. Does not weaken the anonymization design: this is a lookup BY
        the secret the caller already possesses, not a reverse lookup FROM
        an identity, same "possession is the access control" property this
        whole registry already had via upsert()."""
        return self.snapshots.get(pseudonym)

    def list_all(self):
        return sorted(self.snapshots.values(), key=lambda s: s.pseudonym)

    def reset(self):
        self.snapshots = {}


registry = NetworkSnapshotRegistry()


def now_iso():
    return datetime.now(timezone.utc).isoformat()
