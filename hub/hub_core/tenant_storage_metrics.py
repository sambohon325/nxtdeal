"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
the shared fetch engine behind BOTH the Databases panel (hub_core/databases.py)
and the Storage panel (hub_core/hub_storage_status.py) -- one real live-fetch
mechanism, two different presentations of the same real data, matching
hub_core/platform_status.py's own "compose already-real signals, don't
duplicate the fetch" precedent.

Two real signals, both honestly labeled with their own `basis`:

  1. LIVE TENANT NETWORK FETCH (basis="live_tenant_network_fetch") -- a live
     GET to {api_base_url}/network/storage-snapshot, gated by the same
     DEALEROS_NETWORK_KEY shared secret every other Hub<->tenant
     server-to-server route already uses. Mirrors hub/hub_core/infra_services.py's
     _fetch_platform_metrics()/hub/hub_core/dealer_ai_management.py's
     _fetch_ai_snapshot() exactly. This is the GENERAL mechanism -- it works
     for any dealer with a real, reachable api_base_url on file, wherever
     that dealer's process actually runs.

  2. HUB-LOCAL FILESYSTEM READ (basis="hub_local_filesystem_read_dev_only")
     -- a best-effort, DEV-ONLY fallback that only ever fires for a dealer
     whose storage_dir happens to be readable directly from THIS Hub
     process's own filesystem (true today only because this sandbox runs
     the Hub and the one real dealer tenant co-located on the same disk,
     Hub at hub/, tenant storage at ../backend/{storage_dir}/). This is
     NOT a general mechanism -- a real, separately-hosted production
     tenant's disk is not reachable this way at all, and this fallback is
     used ONLY when the live network fetch above didn't produce a result
     (no api_base_url on file, or genuinely unreachable), purely so today's
     one real, co-located dev tenant can show real numbers on this screen
     without requiring a full second `uvicorn` process to be stood up and
     wired with a real api_base_url first. Every response using this path
     says so plainly, both in `basis` and in a dedicated `dev_note` field.

Deliberately NOT persisted to disk, unlike hub/hub_core/dealer_ai_management.py's
DealerAiSnapshot -- same reasoning hub/hub_core/infra_services.py already
states: the underlying data is itself ephemeral/point-in-time on the tenant
side (a live disk read), so persisting a snapshot of it across a Hub
restart would misrepresent it as more durable than it is. The last-fetched
snapshot lives in memory only.
"""

import json
import os
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

# This Hub process is always run with hub/ as its cwd (see hub/app.py's own
# module docstring: "cd hub && python -m uvicorn app:app"). The tenant
# backend is a sibling directory, backend/, so a co-located tenant's own
# storage_dir ("storage" or "storage/tenants/DLR-00002") is reachable at
# this fixed relative offset ONLY when both processes genuinely share one
# filesystem -- true in this sandbox, not assumed true anywhere else.
_CO_LOCATED_BACKEND_ROOT = os.path.join("..", "backend")


@dataclass
class DealerStorageSnapshot:
    dealer_id: str
    fetched_at: Optional[str] = None
    reachable: bool = False
    basis: Optional[str] = None
    error: Optional[str] = None
    data: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "fetched_at": self.fetched_at,
            "reachable": self.reachable,
            "basis": self.basis,
            "error": self.error,
            "data": self.data,
        }


class _SnapshotRegistry:

    def __init__(self):
        self.snapshots: Dict[str, DealerStorageSnapshot] = {}

    def get(self, dealer_id):
        return self.snapshots.get(dealer_id)

    def add(self, snapshot: DealerStorageSnapshot):
        self.snapshots[snapshot.dealer_id] = snapshot

    def list_all(self):
        return sorted(self.snapshots.values(), key=lambda s: s.dealer_id)

    def reset(self):
        self.snapshots = {}


registry = _SnapshotRegistry()


def _fetch_via_network(dealer):
    """Live GET {api_base_url}/network/storage-snapshot. Mirrors
    hub/hub_core/infra_services.py's _fetch_platform_metrics() exactly."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file -- not yet deployed / not yet recorded"

    url = dealer.api_base_url.rstrip("/") + "/network/storage-snapshot"
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

    if "graph_json" not in data:
        return None, "reachable, but the response was missing 'graph_json' -- not treated as valid"

    return data, None


def _safe_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _fetch_via_local_filesystem(dealer):
    """DEV-ONLY best-effort fallback -- see this module's own docstring.
    Never raises; returns (None, reason) if the co-located path simply
    isn't there, which is the correct, expected outcome for any real,
    separately-hosted production tenant."""

    tenant_root = os.path.join(_CO_LOCATED_BACKEND_ROOT, dealer.storage_dir)
    graph_path = os.path.join(tenant_root, "graph.json")

    if not os.path.isfile(graph_path):
        return None, (
            f"no co-located graph.json found at a Hub-local relative path "
            f"('{graph_path}') -- this dev-only fallback only works when "
            f"the Hub and this dealer's tenant process share one "
            f"filesystem, which is not assumed true for a real, "
            f"separately-hosted production tenant"
        )

    try:
        import json as _json

        with open(graph_path, "r", encoding="utf-8") as file:
            graph = _json.load(file)

        entity_count = len(graph.get("entities", {})) if isinstance(graph, dict) else None
        relationship_count = len(graph.get("relationships", [])) if isinstance(graph, dict) else None

        audit_path = os.path.join(tenant_root, "audit.json")
        credentials_path = os.path.join(tenant_root, "credentials.json")
        backups_path = os.path.join(tenant_root, "backups")
        uploads_path = os.path.join(tenant_root, "uploads")

        audit_event_count = None
        if os.path.isfile(audit_path):
            try:
                with open(audit_path, "r", encoding="utf-8") as f:
                    audit_data = _json.load(f)
                audit_event_count = len(audit_data) if isinstance(audit_data, list) else None
            except (OSError, ValueError):
                pass

        credential_count = None
        if os.path.isfile(credentials_path):
            try:
                with open(credentials_path, "r", encoding="utf-8") as f:
                    cred_data = _json.load(f)
                credential_count = len(cred_data) if isinstance(cred_data, dict) else None
            except (OSError, ValueError):
                pass

        def _dir_total(directory):
            # Mirrors backend/core/storage_snapshot.py's own _dir_summary()
            # shape exactly (file_count/total_size_bytes/latest_file/
            # latest_modified_at) so a Backups/Disaster Recovery panel gets
            # a consistent shape regardless of whether the data came from
            # the real live network fetch or this dev-only local fallback --
            # a real bug caught live during this slice's own smoke test
            # (the two paths originally disagreed on shape).
            if not os.path.isdir(directory):
                return {"file_count": 0, "total_size_bytes": 0, "latest_file": None, "latest_modified_at": None}
            names = [n for n in os.listdir(directory) if os.path.isfile(os.path.join(directory, n))]
            total = 0
            latest_name = None
            latest_mtime = -1
            for n in names:
                full = os.path.join(directory, n)
                total += _safe_size(full) or 0
                mtime = os.path.getmtime(full) if os.path.exists(full) else -1
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_name = n
            return {
                "file_count": len(names),
                "total_size_bytes": total,
                "latest_file": latest_name,
                "latest_modified_at": (
                    datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
                    if latest_mtime >= 0
                    else None
                ),
            }

        data = {
            "storage_dir": dealer.storage_dir,
            "graph_json": {
                "size_bytes": _safe_size(graph_path),
                "entity_count": entity_count,
                "relationship_count": relationship_count,
            },
            "audit_json": {
                "size_bytes": _safe_size(audit_path),
                "event_count": audit_event_count,
            },
            "credentials_json": {
                "size_bytes": _safe_size(credentials_path),
                "credential_count": credential_count,
            },
            "uploads": _dir_total(uploads_path),
            "backups": _dir_total(backups_path),
            "note": (
                "Read directly off this Hub process's own local disk (dev-"
                "only co-located fallback) -- NOT a live network fetch. See "
                "'basis' and 'dev_note' on the wrapping snapshot."
            ),
        }

        return data, None

    except (OSError, ValueError) as error:
        return None, f"co-located read failed: {error}"


def recheck_dealer_storage(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    data, error = _fetch_via_network(dealer)
    basis = "live_tenant_network_fetch"
    dev_note = None

    if data is None:
        local_data, local_error = _fetch_via_local_filesystem(dealer)
        if local_data is not None:
            data = local_data
            basis = "hub_local_filesystem_read_dev_only"
            dev_note = (
                "The live tenant network fetch above failed or this dealer "
                "has no api_base_url on file, so this figure was instead "
                "read directly from this Hub process's own local disk -- a "
                "DEV-ONLY convenience that only works because this "
                "sandbox's Hub and this one dealer's tenant process happen "
                "to share the same filesystem. This does NOT work for a "
                "real, separately-hosted production tenant, which would "
                "correctly show 'not_configured'/'unreachable' instead. "
                f"(network fetch reason: {error})"
            )
            error = None

    snapshot = DealerStorageSnapshot(
        dealer_id=dealer_id,
        fetched_at=_now_iso(),
        reachable=data is not None,
        basis=basis if data is not None else None,
        error=error,
        data=data or {},
    )
    if dev_note:
        snapshot.data = {**snapshot.data, "_dev_note": dev_note}

    registry.add(snapshot)

    return snapshot, None


def get_dealer_storage(dealer_id):

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
            "basis": None,
            "error": None,
            "data": {},
        },
    }, None
