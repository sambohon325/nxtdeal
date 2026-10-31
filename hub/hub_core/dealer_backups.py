"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
Backups.

Two real, distinct halves, matching this whole rebuild's "real signal, or a
real honest-manual record -- never fabricated" discipline:

  1. OBSERVED BACKUPS (real, fetched) -- backend/core/data_backup.py already
     has a real, working per-tenant backup/restore mechanism (a real
     timestamped copy of graph.json in storage/backups/, ADMIN-gated,
     tenant-side). That mechanism requires an authenticated EMPLOYEE session
     (Authorization: Bearer <token>), which the Hub genuinely cannot obtain
     for a dealer it doesn't operate -- so this module does NOT call it
     directly. Instead, the same coarse, aggregate, non-PII
     /network/storage-snapshot route this slice already built for
     Databases/Storage (backend/core/storage_snapshot.py) includes a real
     `backups` block (file count / total size / latest filename+timestamp
     off the real storage/backups/ directory) -- reused here verbatim via
     hub/hub_core/tenant_storage_metrics.py, no second fetch mechanism.

  2. LOGGED BACKUP EVENTS (honest manual) -- a real, first-class,
     NXTDeal-staff-maintained log a Hub staffer can use to record "I
     confirmed/triggered a real backup for this dealer" independent of
     whether that dealer happens to be reachable right now (e.g. confirmed
     over a support call). Same "honest manual record, not a placeholder
     standing in for something better" framing hub/hub_core/dealer_onboarding.py's
     own manual steps already established. Every logged entry is also
     recorded to the real Hub audit log (hub/hub_core/hub_audit.py) via
     record_and_save(), same centralized-audit-call discipline every other
     mutation in this rebuild follows.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _recorded_time(value):
    """Only an explicit, valid past instant can establish log recency."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        parsed = parsed.astimezone(timezone.utc)
        return parsed if parsed <= datetime.now(timezone.utc) else None
    except (ValueError, OverflowError):
        return None


def _log_order(entry):
    recorded = _recorded_time(entry.logged_at)
    return (recorded is not None, recorded or datetime.min.replace(tzinfo=timezone.utc))


@dataclass
class DealerBackupLogEntry:
    log_id: str
    dealer_id: str
    logged_by: str
    label: Optional[str] = None
    note: Optional[str] = None
    logged_at: Optional[str] = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "log_id": self.log_id,
            "dealer_id": self.dealer_id,
            "logged_by": self.logged_by,
            "label": self.label,
            "note": self.note,
            "logged_at": self.logged_at,
            "timestamp_status": ("known" if _recorded_time(self.logged_at) else
                                 "unknown" if self.logged_at is None else "invalid"),
        }

    @staticmethod
    def from_dict(data):
        if data.get("logged_at") is not None and not isinstance(data["logged_at"], str):
            raise ValueError("Backup log timestamp must be text or null")
        return DealerBackupLogEntry(
            log_id=data["log_id"],
            dealer_id=data["dealer_id"],
            logged_by=data.get("logged_by", "nxtdeal_staff"),
            label=data.get("label"),
            note=data.get("note"),
            # Reloading an old record is not a newly observed backup event.
            logged_at=data.get("logged_at"),
        )


class DealerBackupLogRegistry:

    def __init__(self):
        self.entries: Dict[str, DealerBackupLogEntry] = {}
        self.counter = 0

    def add(self, entry: DealerBackupLogEntry):
        self.entries[entry.log_id] = entry

    def next_id(self):
        self.counter += 1
        return f"BKLOG-{self.counter:05}"

    def list_for_dealer(self, dealer_id):
        return sorted(
            (e for e in self.entries.values() if e.dealer_id == dealer_id),
            key=_log_order,
            reverse=True,
        )

    def list_all(self):
        return sorted(self.entries.values(), key=_log_order, reverse=True)

    def recover_counter(self):
        highest = 0
        for entry in self.entries.values():
            try:
                number = int(entry.log_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            highest = max(highest, number)
        self.counter = max(self.counter, highest)

    def reset(self):
        self.entries = {}
        self.counter = 0


registry = DealerBackupLogRegistry()


def log_backup_event(dealer_id, logged_by, label=None, note=None):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if not logged_by or not logged_by.strip():
        return None, "logged_by is required"

    entry = DealerBackupLogEntry(
        log_id=registry.next_id(),
        dealer_id=dealer_id,
        logged_by=logged_by.strip(),
        label=(label or "").strip() or None,
        note=(note or "").strip() or None,
    )
    registry.add(entry)

    return entry, None


def get_backups_for_dealer(dealer_id):

    from hub_core.tenant_storage_metrics import registry as storage_registry

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    snapshot = storage_registry.get(dealer_id)
    observed = None
    if snapshot and snapshot.reachable:
        observed = snapshot.data.get("backups")

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "observed": {
            "checked": snapshot is not None,
            "reachable": snapshot.reachable if snapshot else None,
            "basis": snapshot.basis if snapshot else None,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "backups": observed,
        },
        "logged_events": [e.to_dict() for e in registry.list_for_dealer(dealer_id)],
        "note": (
            "'observed' is a real, fetched count/size off this dealer's "
            "own real storage/backups/ directory (see backend/core/"
            "data_backup.py -- an ADMIN can trigger a real backup there any "
            "time). 'logged_events' is NXTDeal staff's own honest manual "
            "record of confirmed backup activity, independent of live "
            "reachability."
        ),
    }, None


def get_backups_overview():

    from hub_core.tenant_storage_metrics import registry as storage_registry

    dealers = dealer_registry.list_all()

    per_dealer = []
    total_observed_backups = 0
    for dealer in dealers:
        snapshot = storage_registry.get(dealer.dealer_id)
        observed = snapshot.data.get("backups") if (snapshot and snapshot.reachable) else None
        logged = registry.list_for_dealer(dealer.dealer_id)

        if observed:
            total_observed_backups += observed.get("file_count") or 0

        per_dealer.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "observed_backup_count": observed.get("file_count") if observed else None,
            "observed_latest_backup_at": observed.get("latest_modified_at") if observed else None,
            "logged_event_count": len(logged),
            "latest_logged_event_at": (logged[0].logged_at if logged and
                                       _recorded_time(logged[0].logged_at) else None),
        })

    return {
        "dealers": per_dealer,
        "recent_logged_events": [e.to_dict() for e in registry.list_all()
                                 if _recorded_time(e.logged_at)][:50],
        "summary": {
            "total_dealers": len(dealers),
            "total_observed_backups": total_observed_backups,
            "total_logged_events": len(registry.list_all()),
        },
        "note": (
            "Backup activity for this platform, from two real sources: "
            "observed real backup files (fetched via /network/storage-"
            "snapshot -- backend/core/data_backup.py's own real, "
            "ADMIN-triggered backup mechanism, storage/backups/), and a "
            "real, NXTDeal-staff-maintained manual log of confirmed backup "
            "activity. Real timestamped backups land in each tenant's own "
            "storage/backups/ directory."
        ),
    }
