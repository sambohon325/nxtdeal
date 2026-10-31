"""
NXTDeal Hub -- "Dealer Management" rebuild (2026-07-19), the Overview screen.

Sam's ask: real KPIs (Total Dealers, Trial Dealers, Active Dealers, Multi-Rooftop
Groups, Network Members, Enterprise Accounts) plus a real Dealer Lifecycle Funnel
(Lead -> Demo -> Trial -> Provisioning -> Active -> Expansion -> Churn Risk).

Deliberately a pure COMPOSITION layer over hub_core/dealer_registry.py's real roster --
same "real, never fabricated" discipline as every rules-based
composition module across NXTDeal's own Intelligence Network/Readiness rebuilds this
same session. This sandbox is genuinely single-tenant today (one real, adopted dealer,
DLR-00001) -- every count below will honestly read mostly 0/1 until more real dealers
are provisioned or adopted. That is not a bug in this module; it's the honest state of
this Hub's own registry, and nothing here pads it to look bigger than it is.
"""

from collections import Counter

from hub_core.dealer import LIFECYCLE_FUNNEL_STAGES
from hub_core.dealer_registry import registry as dealer_registry


def _is_enterprise(dealer):
    """"Enterprise Accounts" -- real plan_tier match. plan_tier is a free-text field
    (create_dealer_api's own default is "Standard"), not an enum, so this is a
    case-insensitive substring-free exact match against the one real tier name Sam's
    own spec names ("Enterprise") rather than guessing at a full tier catalog that
    doesn't exist anywhere in this codebase yet."""

    return (dealer.plan_tier or "").strip().lower() == "enterprise"


def get_dealer_management_overview():

    dealers = dealer_registry.list_all()

    total_dealers = len(dealers)

    status_counts = Counter(d.status for d in dealers)

    trial_dealers = status_counts.get("trial", 0)
    active_dealers = status_counts.get("active", 0)

    network_members = len([d for d in dealers if d.network_opt_in])

    enterprise_accounts = len([d for d in dealers if _is_enterprise(d)])

    # Multi-Rooftop Groups -- a real group name shared by 2+ dealers in the registry
    # (one owner operating more than one rooftop/location under this Hub). A dealer
    # with a `group` set but no sibling dealer under the same group name is real, but
    # not yet a genuine MULTI-rooftop group as far as this Hub can see -- reported
    # separately below rather than silently counted as one.
    group_counter = Counter(d.group for d in dealers if d.group)
    multi_rooftop_groups = len([name for name, count in group_counter.items() if count >= 2])
    single_location_named_groups = len(
        [name for name, count in group_counter.items() if count == 1]
    )

    funnel = []
    for stage in LIFECYCLE_FUNNEL_STAGES:
        funnel.append({
            "stage": stage,
            "label": stage.replace("_", " ").title(),
            "count": status_counts.get(stage, 0),
        })

    suspended_count = status_counts.get("suspended", 0)

    return {
        "kpis": {
            "total_dealers": total_dealers,
            "trial_dealers": trial_dealers,
            "active_dealers": active_dealers,
            "multi_rooftop_groups": multi_rooftop_groups,
            "network_members": network_members,
            "enterprise_accounts": enterprise_accounts,
        },
        "lifecycle_funnel": funnel,
        "suspended_count": suspended_count,
        "single_location_named_groups": single_location_named_groups,
        "status_breakdown": dict(status_counts),
        "note": (
            "Every figure here is a real, direct count off this Hub's own dealer "
            "registry (hub/storage/dealers.json) -- no simulated or projected data. "
            "This environment is genuinely single-tenant today (one real, adopted "
            "dealer), so most of these will honestly read 0 or 1 until more real "
            "dealers are provisioned or adopted. 'Multi-Rooftop Groups' counts only "
            "group names shared by 2+ dealers; single_location_named_groups reports "
            "dealers with a group name set but no sibling rooftop yet, tracked "
            "separately rather than folded into the multi-rooftop count."
        ),
    }
