"""
NXTDeal Hub -- "Dealer Management" rebuild, slice 5 of 5: Network Membership
(the "Network" menu item).

Sam's ask: real Network Tier / Benchmark Access / Contribution Level / Score
per dealer, on top of Dealer.network_opt_in (already real, a plain boolean).

REAL: Network Tier (new field, HONEST MANUAL DATA ENTRY -- same class as
hub/hub_core/dealer_migration.py's own "a human records what's real" convention,
since no automatic tier-assignment signal exists anywhere in this codebase)
and Benchmark Access (a real, transparent, rules-derived boolean: opted_in
AND tier != "none").

CONTRIBUTION LEVEL / SCORE -- the hard one, checked carefully before writing
anything. hub/storage/network_snapshots.json (hub/hub_core/network_snapshot.py)
is DELIBERATELY keyed only by an anonymous, locally-generated pseudonym
(backend/core/network_pseudonym.py) that is NEVER derived from dealer_id and
is stored in a file completely separate from hub/storage/dealers.json --
this is the whole point of the anonymization design (see that module's own
docstring: "not even we can tell who's actual data it is"). There is
therefore NO honest way to look up "how many snapshots has THIS dealer
personally contributed" or "how fresh is THIS dealer's own snapshot" --
doing so would require joining pseudonym back to dealer_id, which is exactly
the boundary this whole mechanism exists to prevent. Per-dealer Contribution
Level / Score are reported as {"computable_per_dealer": False, "reason":
...} -- an honest gap, never a fabricated number.

Two real, non-identifying signals are shown instead, neither of which
crosses that boundary:

  1. A real per-dealer PROXY -- hub/hub_core/dealer_onboarding.py's own
     "network_connected" step already live-verifies, on demand, that THIS
     dealer's own /network/anonymous-snapshot endpoint responds correctly
     (see that module's _check_network_connected -- the pseudonym is read
     only to confirm it's well-formed, NEVER stored or logged there
     either). Reused directly here as "pipeline connectivity," explicitly
     labeled as proof the CAPABILITY works, not proof a snapshot was ever
     actually collected/stored by the Hub.
  2. A real NETWORK-WIDE AGGREGATE -- the same two-counts pattern
     hub/hub_core/noc.py's own network_coverage signal already established
     (opted-in active dealer count vs. total anonymized snapshots ever
     collected, network-wide) -- reused verbatim here rather than a third,
     less careful re-derivation of the same real numbers.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.dealer_onboarding import _check_network_connected
from hub_core.network_snapshot import registry as network_snapshot_registry


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


NETWORK_TIERS = ["none", "standard", "premium", "enterprise"]

NETWORK_TIER_LABELS = {
    "none": "Not a Network Member",
    "standard": "Standard",
    "premium": "Premium",
    "enterprise": "Enterprise",
}

# Judgment call, stated plainly: benchmark access follows tier for every
# tier above "none" -- there is no real, separately-gated benchmark-access
# flag anywhere else in this codebase to defer to instead, so this is a
# simple, transparent rule rather than a second manually-entered field.
_BENCHMARK_ACCESS_TIERS = {"standard", "premium", "enterprise"}

DEFAULT_TIER = "standard"


@dataclass
class NetworkMembershipConfig:
    dealer_id: str
    tier: str = DEFAULT_TIER
    updated_by: str = "nxtdeal_staff"
    updated_at: str = ""

    def to_dict(self):
        return {
            "dealer_id": self.dealer_id,
            "tier": self.tier,
            "tier_label": NETWORK_TIER_LABELS[self.tier],
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return NetworkMembershipConfig(
            dealer_id=data["dealer_id"],
            tier=data.get("tier", DEFAULT_TIER),
            updated_by=data.get("updated_by", "nxtdeal_staff"),
            updated_at=data.get("updated_at", _now_iso()),
        )


class NetworkMembershipRegistry:

    def __init__(self):
        self.configs: Dict[str, NetworkMembershipConfig] = {}

    def get(self, dealer_id):
        return self.configs.get(dealer_id)

    def add(self, config: NetworkMembershipConfig):
        self.configs[config.dealer_id] = config

    def list_all(self):
        return sorted(self.configs.values(), key=lambda c: c.dealer_id)

    def reset(self):
        self.configs = {}


registry = NetworkMembershipRegistry()


def _effective_config(dealer_id):

    stored = registry.get(dealer_id)
    if stored:
        return stored

    return NetworkMembershipConfig(
        dealer_id=dealer_id,
        tier=DEFAULT_TIER,
        updated_by="system_default",
        updated_at="",
    )


def _network_wide_contribution_signal():
    """The real, two-counts aggregate -- mirrors hub/hub_core/noc.py's own
    network_coverage signal exactly, never a per-dealer join."""

    dealers = dealer_registry.list_all()
    active_opted_in = [
        d for d in dealers if d.network_opt_in and d.status not in ("suspended",)
    ]

    return {
        "opted_in_active_dealers": len(active_opted_in),
        "total_anonymized_snapshots_collected": len(network_snapshot_registry.list_all()),
        "note": (
            "A network-wide aggregate only -- two plain counts, never a "
            "per-dealer join (see this module's own docstring for why that "
            "join is architecturally impossible by design)."
        ),
    }


def set_network_tier(dealer_id, tier, updated_by="nxtdeal_staff"):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if tier not in NETWORK_TIERS:
        return None, f"'{tier}' is not a valid network tier -- must be one of {NETWORK_TIERS}"

    config = NetworkMembershipConfig(
        dealer_id=dealer_id,
        tier=tier,
        updated_by=updated_by,
        updated_at=_now_iso(),
    )
    registry.add(config)

    return config, None


def get_dealer_network_membership(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    config = _effective_config(dealer_id)

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "network_opt_in": dealer.network_opt_in,
        "tier": config.to_dict(),
        "benchmark_access": bool(dealer.network_opt_in) and config.tier in _BENCHMARK_ACCESS_TIERS,
        "contribution": {
            "computable_per_dealer": False,
            "reason": (
                "Network snapshots are keyed only by an anonymous, locally-"
                "generated pseudonym never derived from dealer_id and stored "
                "in a separate file from the dealer registry -- deliberately, "
                "by design, so joining a specific stored snapshot back to a "
                "specific dealer is not possible without breaking that "
                "anonymity boundary. See hub_core/network_pseudonym.py and "
                "hub/hub_core/network_snapshot.py's own docstrings."
            ),
            "pipeline_connectivity_proxy": (
                "Use 'Recheck Pipeline' -- a live, on-demand check that this "
                "dealer's own /network/anonymous-snapshot endpoint responds "
                "correctly (reuses hub/hub_core/dealer_onboarding.py's existing "
                "Network Connected check). Proves the CAPABILITY works, not "
                "that a snapshot was ever actually collected/stored."
            ),
            "network_wide_aggregate": _network_wide_contribution_signal(),
        },
    }, None


def recheck_pipeline_connectivity(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    ok, detail = _check_network_connected(dealer)

    return {
        "dealer_id": dealer_id,
        "reachable": bool(ok),
        "detail": detail,
        "checked_at": _now_iso(),
    }, None


def list_all_network_membership_summaries():

    summaries = []
    for dealer in dealer_registry.list_all():
        config = _effective_config(dealer.dealer_id)
        summaries.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "network_opt_in": dealer.network_opt_in,
            "tier": config.tier,
            "tier_label": NETWORK_TIER_LABELS[config.tier],
            "benchmark_access": bool(dealer.network_opt_in) and config.tier in _BENCHMARK_ACCESS_TIERS,
        })

    return summaries
