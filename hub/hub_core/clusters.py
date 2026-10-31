"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
Clusters.

Sam's spec: "CLUSTERS -- future-proof this now. Track: US East/US Central/
US West/Canada/Europe. Per Cluster: CPU/Memory/Network/Latency/Storage.
Auto Scale: Current Nodes/Max Nodes/Growth Trend."

Checked honestly before writing anything: this sandbox runs exactly ONE Hub
process and today's real dealer tenant(s) as plain single processes on one
machine -- there is no real container orchestrator, no real multi-region
deployment, no real per-node CPU/memory/network telemetry anywhere in this
codebase. Fabricating any of that would be exactly the kind of
infrastructure dishonesty this whole 4-slice rebuild is scoped to avoid
(see backend/core/platform_metrics.py's own module docstring for the fuller
reasoning, and CLAUDE.md's Infrastructure & Platform Operations entry for
the standing instruction).

What this module builds instead is a REAL, honest "deployment topology"
view -- a real "cluster" here means "the real dealer tenants grouped by
their own, honestly-labeled `region` field" (hub/hub_core/dealer.py's new,
additive, optional field -- see that module's own docstring), not a
fabricated multi-node infrastructure cluster. Every dealer that predates
this field, or hasn't been assigned a region yet, is honestly grouped under
"unassigned" rather than guessed into one of Sam's five named regions.

Per-cluster metrics, one at a time, real-vs-honest-gap:
  - Node count (Current Nodes) -- REAL: literally the count of dealers
    grouped into that region (this deployment is process-per-tenant, so
    one dealer IS one real "node" in the loosest honest sense of the word).
  - Reachable/Unreachable/Not Configured -- REAL, off hub/hub_core/
    server_health.py's live reachability check, filtered to that region's
    dealers.
  - Avg Latency -- REAL, averaged only across dealers in that region that
    were actually reachable on the last check (server_health.py's own
    per-dealer latency_ms).
  - CPU / Memory / Network -- HONEST GAP, stated plainly: there is no
    remote-process resource-telemetry mechanism anywhere in this codebase
    (no agent, no Prometheus/Grafana-style exporter) -- a real dealer
    tenant's CPU/memory usage is simply not observable from the Hub today.
  - Storage -- see the dedicated Storage/Databases panels (hub_core/
    hub_storage_status.py / hub_core/databases.py) for the real per-tenant
    figures; this module cross-links rather than duplicating that fetch.
  - Auto Scale (Current Nodes/Max Nodes/Growth Trend) -- Current Nodes is
    the same real dealer count above. Max Nodes is an HONEST GAP (no
    auto-scaling mechanism of any kind exists -- one process per dealer,
    started manually per docs/DEPLOYMENT.md). Growth Trend IS real and
    meaningful even at small scale: a real, computed cumulative count of
    dealer signups over time off every dealer's own real `created_at`
    timestamp -- reported at the PLATFORM level (not per-region), since
    with today's real n (1-2 dealers total) a per-region growth curve would
    be a real number technically, but a statistically meaningless one; the
    platform-wide curve is the honest, useful signal at this scale.
"""

from collections import defaultdict

from hub_core.dealer import VALID_REGIONS
from hub_core.dealer_registry import registry as dealer_registry
from hub_core.server_health import get_server_health_overview


_REGION_LABELS = {
    "us_east": "US East",
    "us_central": "US Central",
    "us_west": "US West",
    "canada": "Canada",
    "europe": "Europe",
    "unassigned": "Unassigned / Not Yet Regionalized",
}


def _region_key(dealer):
    return dealer.region if dealer.region in VALID_REGIONS else "unassigned"


def _growth_trend():
    """Real cumulative dealer-signup count by month, off every dealer's own
    real created_at timestamp. Platform-wide, not per-region -- see this
    module's own docstring for why a per-region curve would be
    statistically meaningless at today's real scale."""

    dealers = dealer_registry.list_all()

    by_month = defaultdict(int)
    for dealer in dealers:
        month_key = (dealer.created_at or "")[:7]  # "YYYY-MM"
        if month_key:
            by_month[month_key] += 1

    months_sorted = sorted(by_month.keys())
    points = []
    cumulative = 0
    for month in months_sorted:
        cumulative += by_month[month]
        points.append({"month": month, "new_dealers": by_month[month], "cumulative_dealers": cumulative})

    return {
        "points": points,
        "total_dealers": len(dealers),
        "basis": "real_dealer_signup_history",
        "note": (
            "A real, computed cumulative dealer-signup curve off every "
            "dealer's own real created_at timestamp -- reported at the "
            f"platform level across all {len(dealers)} real registered "
            "dealer(s), not per-region (a per-region growth curve would be "
            "real but statistically meaningless at today's small scale)."
        ),
    }


def get_clusters_overview():

    dealers = dealer_registry.list_all()
    health = get_server_health_overview()
    latency_by_dealer_id = {
        c["dealer_id"]: c["latency_ms"] for c in health["dealers"] if c["status"] == "reachable"
    }
    status_by_dealer_id = {c["dealer_id"]: c["status"] for c in health["dealers"]}

    groups = defaultdict(list)
    for dealer in dealers:
        groups[_region_key(dealer)].append(dealer)

    clusters = []

    # Report every one of Sam's five named regions even if empty (real,
    # honest "0 dealers here yet"), plus "unassigned" only if it's
    # non-empty (no point reporting an empty unassigned bucket alongside
    # five empty named ones -- but unassigned genuinely has data today).
    region_keys = list(VALID_REGIONS)
    if groups.get("unassigned"):
        region_keys.append("unassigned")

    for region_key in region_keys:
        region_dealers = groups.get(region_key, [])

        reachable = len([d for d in region_dealers if status_by_dealer_id.get(d.dealer_id) == "reachable"])
        unreachable = len([d for d in region_dealers if status_by_dealer_id.get(d.dealer_id) == "unreachable"])
        not_configured = len([d for d in region_dealers if status_by_dealer_id.get(d.dealer_id) == "not_configured"])

        latencies = [latency_by_dealer_id[d.dealer_id] for d in region_dealers if d.dealer_id in latency_by_dealer_id]
        avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

        clusters.append({
            "region_key": region_key,
            "region_label": _REGION_LABELS.get(region_key, region_key),
            "current_nodes": len(region_dealers),
            "reachable": reachable,
            "unreachable": unreachable,
            "not_configured": not_configured,
            "dealers": [{"dealer_id": d.dealer_id, "name": d.name, "slug": d.slug} for d in region_dealers],
            "metrics": {
                "avg_latency_ms": avg_latency,
                "latency_basis": "real_live_reachability_check" if latencies else "no_reachable_dealers_to_measure",
                "cpu": None,
                "memory": None,
                "network": None,
                "resource_telemetry_note": (
                    "CPU/Memory/Network are an honest gap -- no remote-process "
                    "resource-telemetry mechanism (agent, Prometheus/Grafana-"
                    "style exporter, etc.) exists anywhere in this codebase. A "
                    "real dealer tenant's CPU/memory usage is not observable "
                    "from the Hub today, so this is stated plainly rather than "
                    "fabricated."
                ),
            },
            "auto_scale": {
                "current_nodes": len(region_dealers),
                "max_nodes": None,
                "auto_scale_note": (
                    "No auto-scaling mechanism exists anywhere in this "
                    "codebase -- this is a process-per-tenant deployment "
                    "(see CLAUDE.md's NXTDeal Hub section), one process per "
                    "dealer, started manually per docs/DEPLOYMENT.md. "
                    "'Max Nodes' is an honest gap, not a fabricated ceiling."
                ),
            },
        })

    down_regions = len([c for c in clusters if c["unreachable"] > 0])

    return {
        "clusters": clusters,
        "growth_trend": _growth_trend(),
        "summary": {
            "total_dealers": len(dealers),
            "regions_with_dealers": len([c for c in clusters if c["current_nodes"] > 0]),
            "regions_with_unreachable_dealers": down_regions,
        },
        "note": (
            "A real, honest 'deployment topology' view, not a fabricated "
            "multi-region infrastructure picture. A 'cluster' here means "
            "'real dealer tenants grouped by their own, optional, honestly-"
            "labeled region field' (hub/hub_core/dealer.py) -- process-per-"
            "tenant, one dealer is one real process, not a real multi-node "
            "cluster. Sam's own illustrative region names describe the "
            "eventual multi-region vision; assigning a dealer a region "
            "today does NOT mean that dealer is actually hosted there yet. "
            "See hub_core/hub_storage_status.py / hub_core/databases.py for the "
            "real per-tenant Storage figures referenced above."
        ),
    }
