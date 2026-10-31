"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 4 of 5: Integrations Center.

Sam's ask: "INTEGRATIONS CENTER -- dealer specific. Active Integrations:
Google/Microsoft/Meta/CDK/DealerTrack/RouteOne/Xtime. Connection Health:
Healthy/Warning/Failed. Data Flow: Inbound/Outbound, Sync Frequency."

Decision (documented, not silently assumed): this is a Hub-side, honest MANUAL
record, the same class of decision hub_core/dealer_onboarding.py's own module
docstring already made for 5 of its 7 steps, for two independent reasons:

  1. The tenant's own real integration model (backend/core/data_connections.py's
     Connection entity) has no concept of a NAMED third-party provider at all --
     it's scoped to a plain (connection_type: csv|api, department) pair with a
     freeform `name` string. There is no "Google"/"Microsoft"/"Meta"/"CDK"/
     "DealerTrack"/"RouteOne"/"Xtime" catalog anywhere in the tenant codebase to
     read from -- Sam's named-provider list simply isn't backed by real tenant
     data today, so no live tenant-side read could honestly produce it.

  2. Even setting (1) aside, Connection.endpoint_url is real per-dealer
     operational detail (a live API endpoint, potentially embedding an internal
     hostname or, depending how a dealer configures it, more) -- a materially
     different exposure than the coarse, bucketed KPI aggregate hub_core/
     network_snapshot.py's build_anonymous_snapshot() already established as
     safe to expose under the shared DEALEROS_NETWORK_KEY. Rather than invent a
     new, less-clearly-safe tenant-side read this session, Integrations Center
     stays a real, useful, NXTDeal-staff-recorded record -- exactly the same
     "real feature on its own, not a placeholder standing in for something
     better" framing dealer_onboarding.py's own manual steps already use.

  (Compare hub/hub_core/dealer_ai_management.py, built the same session: THAT module
  DOES add a new tenant-side route, because AI Management's real underlying data
  -- a static feature catalog + 4 plain integer call-attempt counters, no
  endpoint URLs, no freeform names -- is genuinely as coarse/safe as the
  already-shipped anonymous-snapshot precedent. The two menu items landed on
  different real/manual splits because their underlying tenant data has a
  genuinely different risk shape, not because of an inconsistent standard.)

PROVIDER_CATALOG is Sam's own 7-item list plus one extensibility escape hatch
("other" -- a dealer's own bespoke integration, freeform-labeled) -- adding an
8th named provider later is a one-line catalog entry, not a schema change.

Same dataclass + singleton-registry + matching *_storage.py convention as every
other Hub sub-registry (hub/hub_core/dealer_modules.py is the most direct
precedent) -- a per-dealer LIST of DealerIntegration records (not a fixed
7-slot merge like Module Management's effective-modules pattern), since a real
dealer only has SOME of these providers configured, not all of them at some
shared default state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


PROVIDER_CATALOG = [
    {"key": "google", "label": "Google", "category": "ads_analytics"},
    {"key": "microsoft", "label": "Microsoft", "category": "ads_analytics"},
    {"key": "meta", "label": "Meta", "category": "ads_analytics"},
    {"key": "cdk", "label": "CDK Global", "category": "dms"},
    {"key": "dealertrack", "label": "DealerTrack", "category": "fi"},
    {"key": "routeone", "label": "RouteOne", "category": "fi"},
    {"key": "xtime", "label": "Xtime", "category": "service_scheduling"},
    {"key": "other", "label": "Other / Custom", "category": "other"},
]

PROVIDER_KEYS = {entry["key"] for entry in PROVIDER_CATALOG}
PROVIDER_LABEL = {entry["key"]: entry["label"] for entry in PROVIDER_CATALOG}

VALID_HEALTH_STATUSES = ["healthy", "warning", "failed"]
VALID_DATA_FLOWS = ["inbound", "outbound", "bidirectional"]
SYNC_FREQUENCY_PRESETS = ["real_time", "hourly", "daily", "weekly", "manual"]


@dataclass
class DealerIntegration:
    integration_id: str
    dealer_id: str
    provider_key: str
    custom_label: Optional[str] = None
    connection_health: str = "healthy"
    data_flow: str = "bidirectional"
    sync_frequency: str = "daily"
    active: bool = True
    notes: Optional[str] = None
    created_by: str = "nxtdeal_staff"
    created_at: str = field(default_factory=_now_iso)
    updated_by: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)

    def label(self):
        if self.provider_key == "other" and self.custom_label:
            return self.custom_label
        return PROVIDER_LABEL.get(self.provider_key, self.provider_key)

    def to_dict(self):
        return {
            "integration_id": self.integration_id,
            "dealer_id": self.dealer_id,
            "provider_key": self.provider_key,
            "custom_label": self.custom_label,
            "connection_health": self.connection_health,
            "data_flow": self.data_flow,
            "sync_frequency": self.sync_frequency,
            "active": self.active,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return DealerIntegration(
            integration_id=data["integration_id"],
            dealer_id=data["dealer_id"],
            provider_key=data.get("provider_key", "other"),
            custom_label=data.get("custom_label"),
            connection_health=data.get("connection_health", "healthy"),
            data_flow=data.get("data_flow", "bidirectional"),
            sync_frequency=data.get("sync_frequency", "daily"),
            active=data.get("active", True),
            notes=data.get("notes"),
            created_by=data.get("created_by", "nxtdeal_staff"),
            created_at=data.get("created_at", _now_iso()),
            updated_by=data.get("updated_by"),
            updated_at=data.get("updated_at", _now_iso()),
        )


class DealerIntegrationRegistry:

    def __init__(self):
        self.records: Dict[str, DealerIntegration] = {}
        self.counter = 0

    def add(self, record: DealerIntegration):
        self.records[record.integration_id] = record

    def get(self, integration_id):
        return self.records.get(integration_id)

    def remove(self, integration_id):
        return self.records.pop(integration_id, None)

    def list_for_dealer(self, dealer_id):
        return sorted(
            (r for r in self.records.values() if r.dealer_id == dealer_id),
            key=lambda r: r.created_at,
        )

    def list_all(self):
        return sorted(self.records.values(), key=lambda r: r.integration_id)

    def next_id(self):
        self.counter += 1
        return f"INTG-{self.counter:05}"

    def recover_counter(self):
        """Same idea as hub/hub_core/dealer.py's DealerIDGenerator.recover_from() --
        bump the counter to at least the highest integration_id number already on
        file, so a Hub restart never reissues an existing id."""

        highest = 0
        for record in self.records.values():
            try:
                number = int(record.integration_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            highest = max(highest, number)
        self.counter = max(self.counter, highest)

    def reset(self):
        self.records = {}
        self.counter = 0


registry = DealerIntegrationRegistry()


def add_integration(dealer_id, provider_key, connection_health="healthy",
                     data_flow="bidirectional", sync_frequency="daily",
                     active=True, notes=None, custom_label=None,
                     created_by="nxtdeal_staff"):

    if not dealer_registry.get(dealer_id):
        return None, f"no dealer with id '{dealer_id}'"

    if provider_key not in PROVIDER_KEYS:
        return None, f"unknown provider_key '{provider_key}' -- must be one of {sorted(PROVIDER_KEYS)}"

    if connection_health not in VALID_HEALTH_STATUSES:
        return None, f"unknown connection_health '{connection_health}' -- must be one of {VALID_HEALTH_STATUSES}"

    if data_flow not in VALID_DATA_FLOWS:
        return None, f"unknown data_flow '{data_flow}' -- must be one of {VALID_DATA_FLOWS}"

    record = DealerIntegration(
        integration_id=registry.next_id(),
        dealer_id=dealer_id,
        provider_key=provider_key,
        custom_label=custom_label if provider_key == "other" else None,
        connection_health=connection_health,
        data_flow=data_flow,
        sync_frequency=sync_frequency,
        active=bool(active),
        notes=notes,
        created_by=created_by,
        updated_by=created_by,
    )

    registry.add(record)

    return record, None


def update_integration(integration_id, updated_by="nxtdeal_staff", **fields):

    record = registry.get(integration_id)
    if not record:
        return None, f"no integration with id '{integration_id}'"

    if fields.get("connection_health") is not None:
        if fields["connection_health"] not in VALID_HEALTH_STATUSES:
            return None, f"unknown connection_health -- must be one of {VALID_HEALTH_STATUSES}"
        record.connection_health = fields["connection_health"]

    if fields.get("data_flow") is not None:
        if fields["data_flow"] not in VALID_DATA_FLOWS:
            return None, f"unknown data_flow -- must be one of {VALID_DATA_FLOWS}"
        record.data_flow = fields["data_flow"]

    if fields.get("sync_frequency") is not None:
        record.sync_frequency = fields["sync_frequency"]

    if fields.get("active") is not None:
        record.active = bool(fields["active"])

    if fields.get("notes") is not None:
        record.notes = fields["notes"]

    if fields.get("custom_label") is not None:
        record.custom_label = fields["custom_label"]

    record.updated_by = updated_by
    record.updated_at = _now_iso()

    registry.add(record)

    return record, None


def remove_integration(integration_id):
    record = registry.remove(integration_id)
    if not record:
        return None, f"no integration with id '{integration_id}'"
    return record, None


def get_dealer_integrations(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    records = registry.list_for_dealer(dealer_id)

    by_health = {"healthy": 0, "warning": 0, "failed": 0}
    for r in records:
        if r.active:
            by_health[r.connection_health] = by_health.get(r.connection_health, 0) + 1

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "integrations": [
            {**r.to_dict(), "label": r.label()} for r in records
        ],
        "active_count": len([r for r in records if r.active]),
        "by_health": by_health,
        "note": (
            "Honest manual data entry by NXTDeal staff -- no real tenant-side "
            "integration provider catalog exists (backend/core/"
            "data_connections.py's Connection model has no Google/Microsoft/"
            "Meta/CDK/DealerTrack/RouteOne/Xtime concept at all), so this is a "
            "real, useful Hub-side record, not a live read of the tenant's own "
            "state. See hub_core/dealer_integrations.py's module docstring for the "
            "full reasoning."
        ),
    }, None
