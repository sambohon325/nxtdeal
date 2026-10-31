"""
NXTDeal Hub (2026-07-16) -- pulls each opted-in dealer's anonymized snapshot and stores
it, keyed only by pseudonym.

This is the Hub-side half of Sam's "encrypted so not even we can tell who's actual
data it is" ask. The full chain, end to end:

  1. Each dealer's own backend generates a random, locally-held pseudonym the first
     time it's needed (backend/core/network_pseudonym.py) -- never derived from
     dealer_id, never transmitted anywhere except as the opaque token itself.
  2. That backend computes its own real KPIs (hub_core/department_intelligence.py, the
     same engine every other NXTDeal dashboard uses) and rounds them to a coarse
     bucket before they ever leave the process (backend/core/network_snapshot.py).
  3. The Hub pulls that bucketed, pseudonym-tagged payload over HTTP (this file) and
     stores it keyed ONLY by pseudonym (hub/hub_core/network_snapshot.py's registry) --
     hub/storage/dealers.json (the identifiable registry: name, contact info,
     dealer_id) and hub/storage/network_snapshots.json (the anonymized metrics) are
     two separate files, and nothing in this codebase ever joins them back together.

What this genuinely achieves: even a NXTDeal engineer with full read access to every
file on the Hub's server cannot map a stored network snapshot back to a specific
dealership, because the pseudonym was never derived from anything the Hub knows and no
mapping between the two was ever recorded anywhere.

What this does NOT achieve (stated plainly, not glossed over): the Hub still knows
WHICH dealers it successfully reached this pass (dealer_id, from the registry it
already has) even though it can't tell which pseudonym belongs to which -- so
`dealers_reporting`/`dealers_unreachable` counts are honest operational telemetry, not
part of the anonymized metrics themselves. And this is a snapshot-per-fetch model, not
a running trend store yet -- a real day-over-day trend view (mirroring
backend/core/kpi_snapshots.py) is real, valuable future work, deliberately out of scope
for this pass so the core privacy mechanism could ship first and be reviewed on its own.

Reuses hub/hub_core/network_aggregator.py's exact urllib-only HTTP pattern (no third-party
dependency) -- this is the third module in this codebase to follow that convention.
"""

import json
import urllib.request
import urllib.error

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.network_snapshot import registry as snapshot_registry, NetworkSnapshot, now_iso
from hub_core.secrets import get_secret

REQUEST_TIMEOUT_SECONDS = 5

_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"


def _fetch_snapshot(dealer):
    """Best-effort GET {api_base_url}/network/anonymous-snapshot for one dealer.
    Returns (data, error) -- one unreachable dealer must never break collection for
    every other dealer, same defensive shape as network_aggregator.py's
    _fetch_dealer_benchmark."""

    if not dealer.api_base_url:
        return None, "no api_base_url on file (not yet deployed / not yet recorded)"

    url = dealer.api_base_url.rstrip("/") + "/network/anonymous-snapshot"
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
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.URLError as error:
        return None, f"unreachable: {error}"
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad response: {error}"


def collect_network_snapshots():
    """One pass over every opted-in, active dealer. Returns a summary dict (never
    raises) -- same honesty posture as network_aggregator.py's network_overview():
    `dealers_reporting`/`dealers_unreachable` counts are real operational telemetry
    about THIS collection pass, not a claim about the anonymized data itself."""

    opted_in = [
        dealer for dealer in dealer_registry.list_all()
        if dealer.network_opt_in and dealer.status == "active"
    ]

    reporting = 0
    unreachable = []

    for dealer in opted_in:

        data, error = _fetch_snapshot(dealer)

        if error:
            # dealer_id here is real operational telemetry about THIS collection pass
            # (which dealers were reachable), never stored alongside the anonymized
            # snapshot data itself -- see this module's docstring.
            unreachable.append({"dealer_id": dealer.dealer_id, "reason": error})
            continue

        if not isinstance(data, dict) or "error" in data:
            reason = data.get("error", "malformed response") if isinstance(data, dict) else "malformed response"
            unreachable.append({"dealer_id": dealer.dealer_id, "reason": reason})
            continue

        # A dealer that responds 200 with a well-formed-looking-but-incomplete body must not crash
        # the whole pass (this function's contract is "never raises"). Skip + record it instead.
        missing = [k for k in ("pseudonym", "submitted_at", "departments") if data.get(k) is None]
        if missing:
            unreachable.append({"dealer_id": dealer.dealer_id, "reason": f"malformed snapshot (missing {', '.join(missing)})"})
            continue

        snapshot_registry.upsert(
            NetworkSnapshot(
                pseudonym=data["pseudonym"],
                submitted_at=data["submitted_at"],
                collected_at=now_iso(),
                departments=data["departments"],
            )
        )
        reporting += 1

    return {
        "total_dealers": len(dealer_registry.list_all()),
        "opted_in_dealers": len(opted_in),
        "dealers_reporting": reporting,
        "dealers_unreachable": unreachable,
        "total_snapshots_stored": len(snapshot_registry.list_all()),
        "note": (
            "dealers_reporting/dealers_unreachable are honest telemetry about THIS "
            "collection pass (which dealer instances responded), tracked by dealer_id "
            "since the Hub already knows who it tried to reach -- never stored "
            "alongside the anonymized snapshot data itself, which is keyed only by "
            "pseudonym. See hub_core/network_collector.py's module docstring for the full "
            "privacy design."
        ),
    }
