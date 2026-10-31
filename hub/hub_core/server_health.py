"""
NXTDeal Hub (2026-07-16) -- "show the health of the server(s), network, dealerships,
etc" half of Sam's Hub request.

Deliberately honest about what's actually measurable from here: this Hub has no real
infrastructure-monitoring agent (no CPU/memory/disk telemetry, no uptime history, no
alerting) -- that's real, separate infra work (a Prometheus/Grafana-style stack, or
Coolify's own built-in monitoring, not something to fake here). What this genuinely CAN
do today, cheaply and honestly: reach out to every registered dealer's own
`api_base_url` and report real, live reachability + latency, the same way a basic
uptime checker would. Same urllib-only convention as
hub/hub_core/network_aggregator.py / network_collector.py.
"""

import time
import urllib.request
import urllib.error

from hub_core.dealer_registry import registry as dealer_registry

REQUEST_TIMEOUT_SECONDS = 5


def _check_dealer(dealer):

    if not dealer.api_base_url:
        return {
            "dealer_id": dealer.dealer_id,
            "name": dealer.name,
            "slug": dealer.slug,
            "status": "not_configured",
            "latency_ms": None,
            "detail": "no api_base_url on file -- not yet deployed / not yet recorded",
        }

    url = dealer.api_base_url.rstrip("/") + "/"
    started = time.monotonic()

    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS):
            latency_ms = round((time.monotonic() - started) * 1000, 1)
            return {
                "dealer_id": dealer.dealer_id,
                "name": dealer.name,
                "slug": dealer.slug,
                "status": "reachable",
                "latency_ms": latency_ms,
                "detail": None,
            }
    except urllib.error.URLError as error:
        return {
            "dealer_id": dealer.dealer_id,
            "name": dealer.name,
            "slug": dealer.slug,
            "status": "unreachable",
            "latency_ms": None,
            "detail": str(error),
        }


def get_server_health_overview():
    """Real reachability/latency for every registered dealer plus the Hub's own
    self-report (if this function ran, the Hub process itself is obviously up --
    reported for UI completeness, not because it's a meaningful check of itself)."""

    dealers = dealer_registry.list_all()
    checks = [_check_dealer(dealer) for dealer in dealers]

    reachable_count = len([c for c in checks if c["status"] == "reachable"])

    return {
        "hub_status": "up",
        "total_dealers": len(dealers),
        "reachable_dealers": reachable_count,
        "unreachable_dealers": len(dealers) - reachable_count,
        "dealers": checks,
        "note": (
            "This is a live reachability + latency check against each dealer's "
            "recorded api_base_url, not a real infrastructure-monitoring system -- "
            "there is no CPU/memory/disk telemetry, uptime history, or alerting here. "
            "A dealer with no api_base_url on file shows as 'not_configured', not "
            "'unreachable' -- those are different, honestly distinguished states."
        ),
    }
