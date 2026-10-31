"""
NXTDeal Hub -- the "NOC restructure" Sam proposed alongside the Network
department's own Intelligence Network reframe (task #8 of that 8-slice
autonomous rebuild). Sam's own framing for the Hub, restated here since this
module is the direct answer to it: "to show the health of the server(s),
network, dealerships, etc - and as the center of the NXTDeal network."

This is deliberately a COMPOSITION layer, not a new monitoring engine -- every
real piece already existed (hub/hub_core/server_health.py's real reachability/
latency checks, hub/hub_core/dealer_registry.py's real dealer roster,
hub/hub_core/network_analytics.py's real anonymized aggregate coverage). What
didn't exist: one unified status board a NXTDeal employee can actually open
first thing and immediately see "is anything on fire right now," plus a real,
transparent Alerts feed instead of three separate tabs someone has to
cross-reference by hand. Same "real, transparent rules engine, not fabricated
AI/ML" discipline as backend/core/network_audit.py and every rules-based
recommendation/alert engine built across NXTDeal's own Intelligence Network
reframe this same session -- every alert below traces to one specific,
checkable real condition, stated in its own `reason` field.

A hard, deliberate privacy boundary respected here: hub/hub_core/network_
collector.py's whole design point is that a collected KPI snapshot is keyed
ONLY by an anonymous pseudonym, never joinable back to a specific dealer_id
(see that module's own docstring). This module does NOT attempt a per-dealer
"has this dealer's data gone stale" alert, because building one would require
re-joining pseudonym to dealer_id -- the exact thing the anonymization design
exists to prevent. The only network-coverage signal here is an AGGREGATE
comparison (how many opted-in active dealers exist vs. how many anonymized
snapshots have ever been collected, network-wide) -- two counts, never a
per-dealer join.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.server_health import get_server_health_overview
from hub_core.network_analytics import compute_network_analytics


def _dealer_alerts(health):
    """Real, per-dealer reachability alerts -- reachability/latency is already
    real, identifiable operational telemetry (server_health.py checks each
    dealer's own recorded api_base_url directly), not part of the anonymized
    metrics registry, so per-dealer detail here doesn't touch the privacy
    boundary described in this module's own docstring."""

    alerts = []

    for dealer_check in health["dealers"]:

        if dealer_check["status"] == "unreachable":
            alerts.append({
                "severity": "critical",
                "category": "reachability",
                "dealer_id": dealer_check["dealer_id"],
                "dealer_name": dealer_check["name"],
                "title": f"{dealer_check['name']} is unreachable",
                "reason": (
                    f"A live HTTP check against this dealer's recorded api_base_url "
                    f"failed just now: {dealer_check.get('detail') or 'no further detail'}."
                ),
            })

        elif dealer_check["status"] == "not_configured":
            alerts.append({
                "severity": "warning",
                "category": "configuration",
                "dealer_id": dealer_check["dealer_id"],
                "dealer_name": dealer_check["name"],
                "title": f"{dealer_check['name']} has no api_base_url on file",
                "reason": (
                    "This dealer has no recorded API base URL, so the Hub cannot check "
                    "reachability or collect network snapshots for them -- either not yet "
                    "deployed, or deployed but never recorded on the Dealers tab."
                ),
            })

    return alerts


def get_noc_status_board():
    """The unified real-time status board -- one call, composing every already-
    real Hub signal (dealer roster, live server health, aggregate anonymized
    network coverage) plus a real, transparent Alerts feed derived from them.
    Never fabricates a health score or an alert with no real underlying
    condition -- see this module's own docstring for the privacy boundary this
    respects."""

    dealers = dealer_registry.list_all()
    health = get_server_health_overview()
    analytics = compute_network_analytics()

    active_dealers = [d for d in dealers if d.status == "active"]
    provisioning_dealers = [d for d in dealers if d.status == "provisioning"]
    suspended_dealers = [d for d in dealers if d.status == "suspended"]
    opted_in_active_dealers = [d for d in active_dealers if d.network_opt_in]

    alerts = _dealer_alerts(health)

    dealers_contributing = analytics.get("dealers_contributing", 0)

    if opted_in_active_dealers and dealers_contributing == 0:
        alerts.append({
            "severity": "info",
            "category": "network_coverage",
            "dealer_id": None,
            "dealer_name": None,
            "title": "No anonymized network snapshots have been collected yet",
            "reason": (
                f"{len(opted_in_active_dealers)} active, network-opted-in dealer(s) exist, "
                "but the anonymized snapshot registry has zero entries -- run a collection "
                "pass from the Network tab. This is an aggregate-only signal (never joined "
                "back to a specific dealer, per the anonymization design)."
            ),
        })

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))

    critical_count = len([a for a in alerts if a["severity"] == "critical"])
    warning_count = len([a for a in alerts if a["severity"] == "warning"])

    return {
        "overall_status": (
            "critical" if critical_count else "warning" if warning_count else "healthy"
        ),
        "dealer_counts": {
            "total": len(dealers),
            "active": len(active_dealers),
            "provisioning": len(provisioning_dealers),
            "suspended": len(suspended_dealers),
            "network_opted_in_active": len(opted_in_active_dealers),
        },
        "reachability": {
            "reachable": health["reachable_dealers"],
            "unreachable": health["unreachable_dealers"],
        },
        "network_coverage": {
            "dealers_contributing_anonymized_snapshots": dealers_contributing,
        },
        "alerts": alerts,
        "alert_counts": {
            "critical": critical_count,
            "warning": warning_count,
            "info": len(alerts) - critical_count - warning_count,
        },
        "note": (
            "overall_status is a real, transparent rollup off the alerts below -- "
            "'critical' if any dealer is unreachable, else 'warning' if any is "
            "misconfigured, else 'healthy'. Never a fabricated composite score. See "
            "this module's own docstring for the deliberate privacy boundary around "
            "network_coverage (aggregate-only, never joined to a specific dealer)."
        ),
    }
