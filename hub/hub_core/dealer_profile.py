"""
NXTDeal Hub -- "Dealer Management" rebuild (2026-07-19).

Sam's proposed Hub structure reframes the old flat "Dealers" tab as a real
Salesforce-Trust-style Dealer Record: Dealer Profile (group/oem/location count/
industry type), Subscription Info (plan tier/active modules/renewal date/seat count),
and NXTDeal Version (current release/beta programs) -- see hub_core/dealer.py's own
2026-07-19 docstring entry for the additive Dealer dataclass fields this module
mutates.

Matches hub_core/provisioning.py's own set_dealer_status()/set_dealer_api_base_url()
convention exactly: look up the dealer, validate, mutate in place, re-add to the
registry (DealerRegistry.add() is upsert-by-id, so this is just "replace"), return
(dealer_dict, error). Caller (hub_core/dealers_api.py) is responsible for calling
save_dealers() afterward, same division of responsibility as every other mutating
function in this module.
"""

from hub_core.dealer import VALID_INDUSTRY_TYPES, VALID_REGIONS
from hub_core.dealer_registry import registry


def update_dealer_profile(
    dealer_id,
    group=None,
    oem=None,
    location_count=None,
    industry_type=None,
    region=None
):
    """Updates Dealer Profile fields. Every argument is optional -- only the fields
    the caller actually passes get changed, same "partial update" convention
    hub_core/websites.py's update_admin_settings() already established for this
    codebase's broader Website Builder module. None means "leave unchanged" for
    optional string fields; group/oem can be explicitly cleared by passing an empty
    string, which is intentionally distinct from omitting the argument."""

    dealer = registry.get(dealer_id)

    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if group is not None:
        dealer.group = group.strip() or None

    if oem is not None:
        dealer.oem = oem.strip() or None

    if location_count is not None:
        try:
            location_count = int(location_count)
        except (TypeError, ValueError):
            return None, "location_count must be a whole number"
        if location_count < 1:
            return None, "location_count must be at least 1"
        dealer.location_count = location_count

    if industry_type is not None:
        if industry_type not in VALID_INDUSTRY_TYPES:
            return None, f"industry_type must be one of {VALID_INDUSTRY_TYPES}"
        dealer.industry_type = industry_type

    if region is not None:
        # Empty string is a deliberate, explicit "clear it -- back to
        # unassigned" action, same convention as group/oem above -- distinct
        # from omitting the argument entirely (which leaves it unchanged).
        region = region.strip() or None
        if region is not None and region not in VALID_REGIONS:
            return None, f"region must be one of {VALID_REGIONS} (or blank to clear)"
        dealer.region = region

    registry.add(dealer)

    return dealer.to_dict(), None


def update_dealer_subscription(
    dealer_id,
    plan_tier=None,
    active_modules=None,
    renewal_date=None,
    seat_count=None
):
    """Updates Subscription Info. active_modules is a real list Sam's later Licensing/
    Modules slice (Module Management + Feature Flags) is expected to grow real
    per-module logic on top of -- this slice only stores the flat list, it doesn't
    gate any real feature behind it yet (that's explicitly the next slice's job, not
    guessed at here)."""

    dealer = registry.get(dealer_id)

    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if plan_tier is not None:
        plan_tier = plan_tier.strip()
        if not plan_tier:
            return None, "plan_tier cannot be blank"
        dealer.plan_tier = plan_tier

    if active_modules is not None:
        if not isinstance(active_modules, list) or not all(
            isinstance(item, str) for item in active_modules
        ):
            return None, "active_modules must be a list of strings"
        dealer.active_modules = active_modules

    if renewal_date is not None:
        dealer.renewal_date = renewal_date.strip() or None

    if seat_count is not None:
        try:
            seat_count = int(seat_count)
        except (TypeError, ValueError):
            return None, "seat_count must be a whole number"
        if seat_count < 0:
            return None, "seat_count cannot be negative"
        dealer.seat_count = seat_count

    registry.add(dealer)

    return dealer.to_dict(), None


def update_dealer_version(dealer_id, current_release=None, beta_programs=None):
    """Updates NXTDeal Version info. current_release is a plain, hand-entered
    string (e.g. "2026.07.19") -- there is no real build/release-tagging pipeline
    anywhere in this codebase to read this from automatically, so it's recorded
    manually here rather than fabricated as auto-detected."""

    dealer = registry.get(dealer_id)

    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    if current_release is not None:
        dealer.current_release = current_release.strip() or None

    if beta_programs is not None:
        if not isinstance(beta_programs, list) or not all(
            isinstance(item, str) for item in beta_programs
        ):
            return None, "beta_programs must be a list of strings"
        dealer.beta_programs = beta_programs

    registry.add(dealer)

    return dealer.to_dict(), None
