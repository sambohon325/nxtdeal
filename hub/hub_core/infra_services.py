"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 1 of 4:
Services panel.

Two real halves, both real request/error/latency telemetry, no fabricated
CPU/node/cluster data:

  - The Hub's OWN route-group metrics (hub/hub_core/hub_platform_metrics.py) --
    always real-time, no fetch needed, since the Hub reads its own
    in-process counters directly.
  - Each dealer TENANT's own route-group metrics, fetched ON DEMAND via a
    live GET to that dealer's real, newly-added
    /network/platform-metrics-snapshot (backend/core/platform_metrics.py),
    gated by the same DEALEROS_NETWORK_KEY shared secret every other
    Hub<->tenant server-to-server route already uses (see hub/hub_core/
    dealer_ai_management.py / hub/hub_core/dealer_support.py for the identical
    established fetch pattern this module mirrors).

Deliberately NOT persisted to disk, unlike hub/hub_core/dealer_ai_management.py's
DealerAiSnapshot / hub/hub_core/dealer_support.py's DealerOperationalSnapshot --
a considered simplification, not an oversight: the underlying counters this
module reports are THEMSELVES in-memory/ephemeral on the tenant side
(hub_core/platform_metrics.py resets to zero on every tenant restart), so
persisting a snapshot OF that ephemeral data past this Hub process's own
restart would misrepresent it as more durable than it actually is. The last-
fetched snapshot lives in memory only and is gone the moment this Hub
process restarts too -- click "Recheck" again after a restart.
"""

import json
import urllib.error
import urllib.request

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.secrets import get_secret


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"
_REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class DealerPlatformMetricsSnapshot:
    dealer_id: str
    fetched_at: Optional[str] = None
    reachable: bool = False
    error: Optional[str] = None
    data: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "fetched_at": self.fetched_at,
            "reachable": self.reachable,
            "error": self.error,
            "data": self.data,
        }


class _SnapshotRegistry:

    def __init__(self):
        self.snapshots: Dict[str, DealerPlatformMetricsSnapshot] = {}

    def get(self, dealer_id):
        return self.snapshots.get(dealer_id)

    def add(self, snapshot: DealerPlatformMetricsSnapshot):
        self.snapshots[snapshot.dealer_id] = snapshot

    def list_all(self):
        return sorted(self.snapshots.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.snapshots = {}


registry = _SnapshotRegistry()


def _fetch_platform_metrics(dealer):
    """Live GET {api_base_url}/network/platform-metrics-snapshot. Mirrors
    hub/hub_core/dealer_ai_management.py's _fetch_ai_snapshot / hub/hub_core/
    dealer_support.py's _fetch_operational_snapshot exactly."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/platform-metrics-snapshot"
    # Reads through hub_core/secrets.py's real chokepoint (Task #13, 2026-07-20)
    # rather than os.environ directly.
    network_key = get_secret(_NETWORK_KEY_ENV_VAR, _DEV_FALLBACK_KEY)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-NXTDeal-Network-Key": network_key,
            },
        )
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"

    if "error" in data:
        return None, data["error"]

    if "groups" not in data:
        return None, "reachable, but the response was missing 'groups' -- not treated as valid"

    return data, None


def recheck_dealer_platform_metrics(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    data, error = _fetch_platform_metrics(dealer)

    snapshot = DealerPlatformMetricsSnapshot(
        dealer_id=dealer_id,
        fetched_at=_now_iso(),
        reachable=data is not None,
        error=error,
        data=data or {},
    )

    registry.add(snapshot)

    return snapshot, None


def get_dealer_platform_metrics(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    snapshot = registry.get(dealer_id)

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "snapshot": snapshot.to_dict() if snapshot else {
            "dealer_id": dealer_id,
            "fetched_at": None,
            "reachable": False,
            "error": None,
            "data": {},
        },
    }, None


def get_services_overview():
    """Composes the Hub's own real, always-live metrics with a summary list
    of every registered dealer's LAST-KNOWN (not live-refetched on every
    page load -- see this module's own docstring) platform metrics
    snapshot status."""

    from hub_core.hub_platform_metrics import get_hub_platform_metrics_snapshot

    hub_metrics = get_hub_platform_metrics_snapshot()

    dealer_summaries = []
    for dealer in dealer_registry.list_all():
        snapshot = registry.get(dealer.dealer_id)
        dealer_summaries.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "checked": snapshot is not None,
            "reachable": snapshot.reachable if snapshot else None,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "error": snapshot.error if snapshot else None,
            "group_count": len(snapshot.data.get("groups", {})) if snapshot and snapshot.reachable else 0,
        })

    return {
        "hub_metrics": hub_metrics,
        "dealers": dealer_summaries,
        "note": (
            "Hub metrics (above) are always real-time -- same process, no "
            "fetch needed. Each dealer's metrics (below) are LAST-KNOWN, "
            "not live -- use GET /hub/infra/services/{dealer_id} for the "
            "full per-group breakdown, and POST .../recheck to pull a "
            "fresh snapshot. Neither the Hub's own counters nor a fetched "
            "dealer snapshot survive a Hub restart -- see this module's "
            "and hub_core/hub_platform_metrics.py's own docstrings."
        ),
    }
