"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 3 of 5: Migration Tracking
(the second half of the "Provisioning" menu item -- see
hub_core/dealer_onboarding.py for the first half, the Onboarding Center).

Sam's ask: "Migration Tracking, from: CDK / Reynolds / Tekion / DealerSocket /
VinSolutions / HubSpot. Migration Readiness: Customer Records 98%, Inventory
100%, Service 92%. Go-Live Tracker: Blocked / At Risk / Ready."

HONEST SCOPE, stated plainly: no source-system connector exists anywhere in
this codebase for CDK/Reynolds/Tekion/DealerSocket/VinSolutions/HubSpot (or
any DMS/CRM), and no per-category record-count comparison mechanism exists
to auto-compute a real migration-completeness percentage. Sam's own example
numbers (98% / 100% / 92%) are illustrative targets from his spec, not real
figures to fabricate or reproduce. Both `migrating_from` and every readiness
percentage below are therefore HONEST MANUAL DATA ENTRY -- a NXTDeal staffer
records the real percentage they've personally observed/verified during an
actual migration effort. Same "real record, not a live measurement" honesty
class as hub/hub_core/dealer_modules.py's own module-toggle configuration.

The Go-Live Tracker status (Blocked / At Risk / Ready), by contrast, IS a
real, transparent, RULE-BASED computation -- once a human has recorded real
readiness percentages, deriving a real status off real (if manually entered)
numbers is a genuinely computable thing, not fabrication. Thresholds, stated
plainly so this is never a black box:

  - READY:   every one of the 3 required categories (Customer Records,
    Inventory, Service) has been recorded, AND every recorded value is
    >= READY_THRESHOLD_PCT (95%).
  - BLOCKED: ANY recorded category is below BLOCKED_THRESHOLD_PCT (80%) --
    a hard floor that overrides everything else, regardless of how many
    categories are still missing.
  - AT_RISK: everything else -- covers both "every recorded category clears
    80% but at least one is still below 95%" AND "one or more of the 3
    required categories has no readiness percentage recorded at all yet."
    Incomplete data can never honestly resolve to READY, even if what has
    been recorded so far looks good.
  - NOT_STARTED: no readiness percentage has been recorded for ANY category
    yet -- its own distinct state, not folded into "blocked" (which implies
    an actively identified problem) or "at_risk" (which implies partial
    progress already made).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


MIGRATION_SOURCES = [
    "cdk",
    "reynolds",
    "tekion",
    "dealersocket",
    "vinsolutions",
    "hubspot",
    "none",
    "other",
]

MIGRATION_SOURCE_LABELS = {
    "cdk": "CDK Global",
    "reynolds": "Reynolds & Reynolds",
    "tekion": "Tekion",
    "dealersocket": "DealerSocket",
    "vinsolutions": "VinSolutions",
    "hubspot": "HubSpot",
    "none": "No prior system (net-new)",
    "other": "Other",
}

READINESS_CATEGORIES = ["customer_records", "inventory", "service"]

READINESS_CATEGORY_LABELS = {
    "customer_records": "Customer Records",
    "inventory": "Inventory",
    "service": "Service",
}

READY_THRESHOLD_PCT = 95.0
BLOCKED_THRESHOLD_PCT = 80.0

GO_LIVE_STATUSES = ["not_started", "blocked", "at_risk", "ready"]


@dataclass
class DealerMigrationStatus:
    dealer_id: str
    migrating_from: Optional[str] = None
    migrating_from_other_note: Optional[str] = None
    readiness: Dict[str, float] = field(default_factory=dict)
    readiness_notes: Dict[str, str] = field(default_factory=dict)
    updated_by: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "migrating_from": self.migrating_from,
            "migrating_from_other_note": self.migrating_from_other_note,
            "readiness": self.readiness,
            "readiness_notes": self.readiness_notes,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerMigrationStatus(
            dealer_id=data["dealer_id"],
            migrating_from=data.get("migrating_from"),
            migrating_from_other_note=data.get("migrating_from_other_note"),
            readiness=dict(data.get("readiness", {})),
            readiness_notes=dict(data.get("readiness_notes", {})),
            updated_by=data.get("updated_by"),
            updated_at=data.get("updated_at", _now_iso()),
        )


class DealerMigrationRegistry:

    def __init__(self):
        self.statuses = {}

    def get(self, dealer_id):
        return self.statuses.get(dealer_id)

    def add(self, status: DealerMigrationStatus):
        self.statuses[status.dealer_id] = status

    def list_all(self):
        return sorted(self.statuses.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.statuses = {}


registry = DealerMigrationRegistry()


def compute_go_live_status(readiness):
    """Real, transparent rule over real (manually-entered) readiness
    percentages -- see this module's own docstring for the exact thresholds.
    Never raises; always returns a (status, reason) pair."""

    recorded = {
        key: value for key, value in (readiness or {}).items()
        if key in READINESS_CATEGORIES
    }

    if not recorded:
        return "not_started", "No migration-readiness percentages have been recorded yet."

    below_blocked = {key: value for key, value in recorded.items() if value < BLOCKED_THRESHOLD_PCT}
    if below_blocked:
        worst_key, worst_value = min(below_blocked.items(), key=lambda kv: kv[1])
        return "blocked", (
            f"{READINESS_CATEGORY_LABELS.get(worst_key, worst_key)} is at {worst_value}%, "
            f"below the {BLOCKED_THRESHOLD_PCT:.0f}% blocked threshold."
        )

    missing = [category for category in READINESS_CATEGORIES if category not in recorded]
    if missing:
        missing_labels = [READINESS_CATEGORY_LABELS.get(c, c) for c in missing]
        return "at_risk", (
            "No blocking issues among what's recorded so far, but readiness "
            "hasn't been recorded yet for: " + ", ".join(missing_labels) + "."
        )

    below_ready = {key: value for key, value in recorded.items() if value < READY_THRESHOLD_PCT}
    if below_ready:
        worst_key, worst_value = min(below_ready.items(), key=lambda kv: kv[1])
        return "at_risk", (
            "All 3 required categories recorded and clear of the blocked threshold, "
            f"but {READINESS_CATEGORY_LABELS.get(worst_key, worst_key)} is at "
            f"{worst_value}%, below the {READY_THRESHOLD_PCT:.0f}% ready threshold."
        )

    return "ready", (
        f"All {len(READINESS_CATEGORIES)} required categories recorded at or above "
        f"{READY_THRESHOLD_PCT:.0f}%."
    )


def _ensure_status(dealer_id):

    status = registry.get(dealer_id)

    if not status:
        status = DealerMigrationStatus(dealer_id=dealer_id)
        registry.add(status)

    return status


def get_migration_status(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    status = _ensure_status(dealer_id)
    go_live_status, go_live_reason = compute_go_live_status(status.readiness)

    readiness_out = []
    for category in READINESS_CATEGORIES:
        readiness_out.append({
            "key": category,
            "label": READINESS_CATEGORY_LABELS[category],
            "pct": status.readiness.get(category),
            "note": status.readiness_notes.get(category),
        })

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "migrating_from": status.migrating_from,
        "migrating_from_label": (
            MIGRATION_SOURCE_LABELS.get(status.migrating_from)
            if status.migrating_from else None
        ),
        "migrating_from_other_note": status.migrating_from_other_note,
        "readiness": readiness_out,
        "go_live_status": go_live_status,
        "go_live_reason": go_live_reason,
        "updated_by": status.updated_by,
        "updated_at": status.updated_at,
        "note": (
            "migrating_from and every readiness percentage are honest manual data "
            "entry -- no source-system connector or automatic record-count "
            "comparison exists anywhere in this codebase for CDK/Reynolds/Tekion/"
            "DealerSocket/VinSolutions/HubSpot. go_live_status IS a real, "
            "rule-based computation over those recorded numbers -- see "
            "hub_core/dealer_migration.py's own module docstring for the exact "
            f"thresholds (ready >= {READY_THRESHOLD_PCT:.0f}%, "
            f"blocked < {BLOCKED_THRESHOLD_PCT:.0f}%)."
        ),
    }, None


def set_migration_source(dealer_id, migrating_from, other_note=None, updated_by="nxtdeal_staff"):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if migrating_from is not None and migrating_from not in MIGRATION_SOURCES:
        return None, f"migrating_from must be one of {MIGRATION_SOURCES}"

    status = _ensure_status(dealer_id)
    status.migrating_from = migrating_from
    status.migrating_from_other_note = (
        (other_note or "").strip() or None if migrating_from == "other" else None
    )
    status.updated_by = updated_by
    status.updated_at = _now_iso()
    registry.add(status)

    result, _ = get_migration_status(dealer_id)
    return result, None


def set_readiness(dealer_id, category, pct, note=None, updated_by="nxtdeal_staff"):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if category not in READINESS_CATEGORIES:
        return None, f"category must be one of {READINESS_CATEGORIES}"

    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return None, "pct must be a number"

    if pct < 0 or pct > 100:
        return None, "pct must be between 0 and 100"

    status = _ensure_status(dealer_id)
    status.readiness[category] = round(pct, 1)
    if note is not None:
        status.readiness_notes[category] = note
    status.updated_by = updated_by
    status.updated_at = _now_iso()
    registry.add(status)

    result, _ = get_migration_status(dealer_id)
    return result, None


def list_all_migration_summaries():

    summaries = []
    for dealer in dealer_registry.list_all():
        result, _ = get_migration_status(dealer.dealer_id)
        summaries.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "slug": dealer.slug,
            "migrating_from": result["migrating_from"],
            "migrating_from_label": result["migrating_from_label"],
            "go_live_status": result["go_live_status"],
        })

    return summaries
