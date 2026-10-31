"""
NXTDeal Hub (session 50) -- cross-network aggregation.

Sam: "[NXTDeal Hub] needs to act as a way ... to grab blind data to feed the NXTDeal
Network. It needs to act as a dashboard to see how the network is doing, and be able to
pull data / run business analysis based on metrics across the network."

This is deliberately a thin, honest stub for now: backend/core/network_benchmark.py
already computes real per-dealer percentile rank against *simulated* peer dealers
(seeded at boot, see its own docstring) because, in its own words, "no real second
NXTDeal dealer exists in this environment yet." The moment 2+ real tenants exist (real
Dealer records here with api_base_url set and network_opt_in=True), this module is
meant to replace that simulated seed with real cross-tenant aggregation -- but that's a
one-way door (real dealer data, even blind-labeled, is a different trust/privacy
posture than a simulated fixture) and deserves Sam's sign-off before it's wired into
backend/core/network_benchmark.py for real. Until then, this pulls whatever opted-in
tenants ARE reachable and reports honestly on what it found, rather than pretending to
have network-wide insight it doesn't have yet.

No third-party HTTP dependency (matches backend/core/data_connections.py's own
urllib-only API tester) -- this file is the second user of that same convention.
"""

import json
import urllib.request
import urllib.error

from hub_core.dealer_registry import registry

REQUEST_TIMEOUT_SECONDS = 5


def _fetch_dealer_benchmark(dealer):
    """Best-effort GET {api_base_url}/network/benchmark for one dealer. Returns
    (data, error) -- a single unreachable/misconfigured dealer must never break the
    whole network overview for every other dealer."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file (not yet deployed / not yet recorded)"

    url = dealer.api_base_url.rstrip("/") + "/network/benchmark"

    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.URLError as error:
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"


def network_overview():
    """One pass over every opted-in dealer. Returns a summary dict rather than raising,
    so a partially-reachable network still produces a useful dashboard instead of a
    500. `dealers_reporting` / `dealers_unreachable` let the Hub UI show honestly how
    much of the network it actually heard from this pass, rather than silently
    averaging over whoever happened to respond."""

    opted_in = [
        dealer for dealer in registry.list_all()
        if dealer.network_opt_in and dealer.status == "active"
    ]

    reporting = []
    unreachable = []

    for dealer in opted_in:

        data, error = _fetch_dealer_benchmark(dealer)

        if error:
            unreachable.append({"dealer_id": dealer.dealer_id, "reason": error})
            continue

        reporting.append({"dealer_id": dealer.dealer_id, "benchmark": data})

    return {
        "total_dealers": len(registry.list_all()),
        "opted_in_dealers": len(opted_in),
        "dealers_reporting": reporting,
        "dealers_unreachable": unreachable,
        "note": (
            "Real cross-tenant aggregation is limited to dealers with a recorded "
            "api_base_url that responded this pass. With 0-1 real dealers deployed, "
            "this will mostly be empty -- that's expected, not a bug. See this "
            "module's docstring for why backend/core/network_benchmark.py's simulated "
            "peer data hasn't been replaced by this yet."
        )
    }
