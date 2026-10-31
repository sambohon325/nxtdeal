"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 1 of 4:
Platform Status Board ("think Azure Status Page" -- Sam's own framing,
e.g. "NXTDeal Core: Operational, NXTDeal Marketing: Operational,
NXTDeal Finance: Performance Warning").

SERVICE-GROUP MAPPING, stated plainly rather than guessed at silently:
Sam's own illustrative "NXTDeal Marketing" example names a real NXTDeal
department, but nothing in a literal reading of it corresponds to a real,
independently-deployed service in THIS single-tenant-process deployment --
building a pseudo-service with a fabricated status for it would be exactly
the kind of infrastructure dishonesty this rebuild is scoped to avoid (see
hub_core/infra_overview.py's own docstring). Instead, this board is built
entirely on top of REAL request/error/latency counters (backend/core/
platform_metrics.py / hub/hub_core/hub_platform_metrics.py), grouped by which
real NXTDeal department/subsystem each already-existing route genuinely
belongs to -- when Sam's own example department names DO show up here
("Sales & Deal Desk," "Marketing Growth Platform," "Finance & Retail
Lending Platform," ...), it's because that's a real, checkable group of
real routes with real traffic against it, not a label invented for this
screen.

Composes three already-real signals, no new monitoring engine:
  - The Hub's OWN route-group metrics (hub_platform_metrics.py) -- always
    real-time, since the Hub reads its own in-process counters directly.
  - Each dealer tenant's LAST-KNOWN platform-metrics snapshot
    (infra_services.py) -- one status entry per real tenant-side
    department/subsystem group.
  - Real, live reachability (server_health.py) -- overrides a dealer's
    per-group statuses to "down" the instant that dealer itself stops
    responding, so a stale per-group snapshot from a now-offline dealer is
    never shown as if it were still live.

overall_status is a real, transparent rollup ("down" if anything is down,
else "degraded" if anything is degraded, else "performance_warning" if
anything is in that state, else "operational") -- never a fabricated
composite score, matching hub/hub_core/noc.py's own established precedent.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.server_health import get_server_health_overview
from hub_core.hub_platform_metrics import get_hub_platform_metrics_snapshot
from hub_core.infra_services import registry as services_registry


_SEVERITY_ORDER = {
    "down": 0,
    "degraded": 1,
    "performance_warning": 2,
    "unreachable": 3,
    "not_checked": 4,
    "no_traffic_yet": 5,
    "operational": 6,
}


def _hub_status_entries():

    snapshot = get_hub_platform_metrics_snapshot()
    entries = []

    for key, group in snapshot["groups"].items():
        entries.append({
            "service_id": f"hub.{key}",
            "service_label": f"NXTDeal Hub -- {group['label']}",
            "status": group["status"],
            "status_label": group["status_label"],
            "request_count": group["request_count"],
            "error_count": group["error_count"],
            "error_rate_pct": group["error_rate_pct"],
            "avg_latency_ms": group["avg_latency_ms"],
            "scope": "hub",
            "dealer_id": None,
        })

    return entries


def _dealer_status_entries(reachability_by_dealer_id):

    entries = []

    for dealer in dealer_registry.list_all():

        reachable_now = reachability_by_dealer_id.get(dealer.dealer_id)
        snapshot = services_registry.get(dealer.dealer_id)

        if reachable_now is False:
            entries.append({
                "service_id": f"tenant.{dealer.dealer_id}",
                "service_label": f"{dealer.name} -- NXTDeal (all subsystems)",
                "status": "down",
                "status_label": "Down (Unreachable)",
                "request_count": None,
                "error_count": None,
                "error_rate_pct": None,
                "avg_latency_ms": None,
                "scope": "tenant",
                "dealer_id": dealer.dealer_id,
            })
            continue

        if snapshot is None:
            entries.append({
                "service_id": f"tenant.{dealer.dealer_id}",
                "service_label": f"{dealer.name} -- NXTDeal",
                "status": "not_checked",
                "status_label": "Never Checked",
                "request_count": None,
                "error_count": None,
                "error_rate_pct": None,
                "avg_latency_ms": None,
                "scope": "tenant",
                "dealer_id": dealer.dealer_id,
            })
            continue

        if not snapshot.reachable or not snapshot.data.get("groups"):
            entries.append({
                "service_id": f"tenant.{dealer.dealer_id}",
                "service_label": f"{dealer.name} -- NXTDeal",
                "status": "unreachable",
                "status_label": "Unreachable (Last Check)",
                "request_count": None,
                "error_count": None,
                "error_rate_pct": None,
                "avg_latency_ms": None,
                "scope": "tenant",
                "dealer_id": dealer.dealer_id,
            })
            continue

        for key, group in snapshot.data["groups"].items():
            entries.append({
                "service_id": f"tenant.{dealer.dealer_id}.{key}",
                "service_label": f"{dealer.name} -- {group['label']}",
                "status": group["status"],
                "status_label": group["status_label"],
                "request_count": group["request_count"],
                "error_count": group["error_count"],
                "error_rate_pct": group["error_rate_pct"],
                "avg_latency_ms": group["avg_latency_ms"],
                "scope": "tenant",
                "dealer_id": dealer.dealer_id,
            })

    return entries


def get_platform_status_board():

    health = get_server_health_overview()

    reachability_by_dealer_id = {}
    for check in health["dealers"]:
        if check["status"] == "reachable":
            reachability_by_dealer_id[check["dealer_id"]] = True
        elif check["status"] == "unreachable":
            reachability_by_dealer_id[check["dealer_id"]] = False
        else:
            reachability_by_dealer_id[check["dealer_id"]] = None

    entries = _hub_status_entries() + _dealer_status_entries(reachability_by_dealer_id)

    down_count = len([e for e in entries if e["status"] == "down"])
    degraded_count = len([e for e in entries if e["status"] == "degraded"])
    warning_count = len([e for e in entries if e["status"] == "performance_warning"])
    unreachable_count = len([e for e in entries if e["status"] == "unreachable"])

    if down_count or unreachable_count:
        overall = "down"
    elif degraded_count:
        overall = "degraded"
    elif warning_count:
        overall = "performance_warning"
    else:
        overall = "operational"

    entries.sort(key=lambda e: (_SEVERITY_ORDER.get(e["status"], 9), e["service_label"]))

    return {
        "overall_status": overall,
        "entries": entries,
        "counts": {
            "down": down_count,
            "degraded": degraded_count,
            "performance_warning": warning_count,
            "unreachable": unreachable_count,
            "total": len(entries),
        },
        "note": (
            "Every entry is a real request/error/latency signal over "
            "actual HTTP traffic against a real, already-existing NXTDeal "
            "route group (see backend/core/platform_metrics.py's / hub/"
            "hub_core/hub_platform_metrics.py's own docstrings for the exact "
            "route-group mapping) -- never a fabricated pseudo-service. "
            "Hub entries are always real-time; tenant entries reflect each "
            "dealer's LAST-KNOWN snapshot (Services panel -> Recheck), "
            "with a real live reachability check overriding a dealer's "
            "per-group statuses to 'down' the moment that dealer itself "
            "stops responding, so stale per-group data is never shown as "
            "if still live. overall_status is a real, transparent rollup "
            "off the entries below, never a fabricated composite score."
        ),
    }
