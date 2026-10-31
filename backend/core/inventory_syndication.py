"""
core/inventory_syndication.py -- Inventory Syndication, a new 9th item on
Inventory's Top Menu (2026-07-19, autonomous continuation on Sam's bare "lets
keep going" -- the third of the three still-open six-pillar items flagged at
the end of the Lender Intelligence slice, picked over Executive Command
Center (would substantially duplicate the Readiness rebuild's own Business
Health/Enterprise Risk Center/AI Business Analyst) and Digital Inspections'
remaining asks (its own stated deferred item, the Customer-Facing Approval
Center, was already shipped in a later Service slice, leaving no clear,
non-duplicative gap to close there).

This module is deliberately a COMPOSITION layer over two already-real engines
built in prior sessions, not a new signal-detection pass or a third-party
integration:

1. Feed Sync Status ROLLUP (SIMULATED, honestly labeled) -- core/
   merchandising.py's get_feed_status(vehicle_id) has existed since the
   Inventory rebuild's Merchandising slice, but it was always PER-VEHICLE
   only (surfaced inside one vehicle's own Vehicle Detail modal) -- nothing
   anywhere aggregated it dealership-wide into a real feed-health board a
   marketing/inventory manager could actually work from. get_feed_health_
   rollup() calls that exact same function once per real unsold vehicle and
   aggregates synced/pending/error counts per platform, plus a real,
   drill-down list of which specific vehicles are currently erroring on each
   platform -- the literal "which listings are broken right now" view no
   per-vehicle screen could answer. Still SIMULATED underneath (no real
   Cars.com/AutoTrader/CarGurus/CarFax connection exists anywhere in this
   system), and says so at every level.

2. Cross-Platform Lead Performance (REAL) -- reuses core/
   marketing_attribution.py's get_channel_mix() verbatim (the real Lead.
   Source-grouped first-touch revenue/conversion engine, Marketing Growth
   Platform rebuild, session 113), filtered down to just the channels that
   are genuine third-party syndication platforms. This is the real, honest
   answer to "is our AutoTrader/Cars.com/CarGurus spend actually producing
   leads and revenue" -- a question the feed-sync half above cannot answer
   on its own, since knowing a listing is "synced" says nothing about
   whether it's generating business.

   The mapping between FEED_PLATFORMS (core/merchandising.py's fixed 4-item
   syndication-feed list) and the real Lead.Source catalog (core/
   lead_intake.py's VALID_SOURCES) is NOT a clean 1:1 -- checked directly
   against the live seed graph before writing anything (Website 229, Walk-In
   142, Phone Inquiry 132, Referral 115, Autotrader 109, Cars.com 95,
   Facebook Marketplace 59, Service Drive 59, CarGurus 31, Trade Show 30,
   ...). Three real, honest mismatches are stated explicitly rather than
   silently forced into alignment:
     - "AutoTrader" (feed platform) vs. "Autotrader" (real Lead.Source) --
       a genuine capitalization mismatch in this codebase's own historical
       data, mapped deliberately in SYNDICATION_SOURCE_MAP rather than
       treated as two different things.
     - "CarFax Listings" has a real feed-sync mechanism but NO matching
       Lead.Source anywhere -- reported as a platform with feed data but no
       lead-attribution data, not silently dropped or force-matched.
     - "Facebook Marketplace" has a real, substantial Lead.Source (59 real
       leads) but no corresponding FEED_PLATFORMS entry -- reported as a
       real channel with lead-attribution data but no feed-sync mechanism,
       same honest-gap treatment.

3. Listing Completeness Risk (REAL) -- a genuinely new real check: which
   currently-SYNCED (per the simulated feed mechanism) vehicles have no real
   photo and/or no real description on file (core/merchandising.py's own
   missing_photos/missing_comments checks, cross-referenced here for the
   first time against feed-sync state) -- a real, actionable "we're actively
   advertising an incomplete listing" risk list, not a fabricated metric.

Bulk Republish (SIMULATED, same honest-simulation precedent as
core/campaigns.py's activate_campaign()/core/social_posts.py's
publish_post()/core/merchandising.py's own publish_to_feed()) is the one
real mutation this module adds: republish_platform() calls that exact same
per-vehicle publish_to_feed() once for every real unsold vehicle currently
pending/error on a given platform -- a genuinely useful bulk action built by
reusing the existing per-vehicle mechanism, not a new one.
"""

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.merchandising import (
    FEED_PLATFORMS,
    SIMULATED_BASIS,
    _vehicle_images,
    get_feed_status,
    publish_to_feed,
)
from core.workflow_tab_data import _unsold_vehicles, _safe_float

# Real feed platform -> real Lead.Source mapping, checked against the live
# seed graph before writing anything (see module docstring for the honest
# mismatches this deliberately does NOT paper over).
SYNDICATION_SOURCE_MAP = {
    "Cars.com": "Cars.com",
    "AutoTrader": "Autotrader",
    "CarGurus": "CarGurus",
    # "CarFax Listings" has no matching real Lead.Source -- omitted here on
    # purpose, reported separately as a feed-only platform below.
}

# A real Lead.Source with no corresponding FEED_PLATFORMS entry -- reported
# as a lead-only channel, not silently dropped and not force-mapped onto an
# unrelated feed platform.
UNMAPPED_LEAD_SOURCES = ("Facebook Marketplace",)


def _vehicle_brief(v):
    price = _safe_float(v.attributes.get("Price"))
    return {
        "vehicle_id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "price": price or None,
    }


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


# ---------------------------------------------------------------------------
# Feed Sync Status rollup (SIMULATED, honestly labeled)
# ---------------------------------------------------------------------------

def get_feed_health_rollup(error_drilldown_limit=25):
    unsold = _unsold_vehicles()

    per_platform = {
        platform: {"platform": platform, "synced": 0, "pending": 0, "error": 0, "error_vehicles": []}
        for platform in FEED_PLATFORMS
    }

    incomplete_but_synced = []

    for v in unsold:
        status = get_feed_status(v.id)
        has_photos = len(_vehicle_images(v.id)) > 0
        has_description = bool((v.attributes.get("description") or "").strip())

        any_synced = False

        for entry in status["feeds"]:
            bucket = per_platform[entry["platform"]]
            bucket[entry["status"]] += 1
            if entry["status"] == "synced":
                any_synced = True
            if entry["status"] == "error" and len(bucket["error_vehicles"]) < error_drilldown_limit:
                bucket["error_vehicles"].append(_vehicle_brief(v))

        if any_synced and (not has_photos or not has_description):
            incomplete_but_synced.append({
                **_vehicle_brief(v),
                "has_photos": has_photos,
                "has_description": has_description,
            })

    return {
        "total_unsold": len(unsold),
        "platforms": list(per_platform.values()),
        "listing_completeness_risk": {
            "count": len(incomplete_but_synced),
            "vehicles": incomplete_but_synced[:error_drilldown_limit],
            "note": (
                "REAL -- vehicles currently synced to at least one feed platform "
                "(per the simulated feed mechanism below) that are missing a real "
                "photo and/or a real description on file. Advertising an "
                "incomplete listing is a real, actionable risk regardless of the "
                "feed connection itself being simulated."
            ),
        },
        "basis": SIMULATED_BASIS,
        "disclaimer": (
            "Feed sync status (synced/pending/error counts and the per-platform "
            "error drill-down) is SIMULATED -- no real connection to Cars.com/"
            "AutoTrader/CarGurus/CarFax or any other third-party listing feed "
            "exists in this system yet. Listing Completeness Risk above is REAL, "
            "computed from real photo/description data cross-referenced against "
            "the simulated sync state."
        ),
    }


# ---------------------------------------------------------------------------
# Cross-Platform Lead Performance (REAL)
# ---------------------------------------------------------------------------

def get_syndication_lead_performance():
    from core.marketing_attribution import get_channel_mix

    channel_mix = get_channel_mix()
    by_source = {c["source"]: c for c in channel_mix["channels"]}

    platform_rows = []
    for platform, source in SYNDICATION_SOURCE_MAP.items():
        row = by_source.get(source)
        if row:
            platform_rows.append({"platform": platform, "lead_source": source, **row})
        else:
            platform_rows.append({
                "platform": platform,
                "lead_source": source,
                "lead_count": 0,
                "sold_count": 0,
                "revenue": 0.0,
                "funded_deals_count": 0,
                "conversion_rate": 0.0,
                "revenue_per_lead": 0.0,
            })

    platform_rows.sort(key=lambda r: r["revenue"], reverse=True)

    feed_only_platforms = [p for p in FEED_PLATFORMS if p not in SYNDICATION_SOURCE_MAP]
    lead_only_sources = [
        {"source": s, **by_source[s]} for s in UNMAPPED_LEAD_SOURCES if s in by_source
    ]

    return {
        "platform_performance": platform_rows,
        "total_syndication_revenue": round(sum(r["revenue"] for r in platform_rows), 2),
        "total_syndication_leads": sum(r["lead_count"] for r in platform_rows),
        "feed_only_platforms": feed_only_platforms,
        "lead_only_channels": lead_only_sources,
        "basis": "real_first_touch_not_multi_touch",
        "disclaimer": (
            "Real first-touch attribution (core/marketing_attribution.py's "
            "get_channel_mix(), Lead.Source-grouped, gross-profit funded-Deal "
            "revenue) filtered to the platforms this system also tracks a "
            "simulated feed-sync status for. 'CarFax Listings' has real feed-"
            "sync tracking but no matching Lead.Source anywhere in this "
            "codebase, listed under feed_only_platforms rather than force-"
            "mapped. 'Facebook Marketplace' has a real, substantial Lead.Source "
            "but no corresponding feed-sync platform, listed under "
            "lead_only_channels for the same reason."
        ),
    }


# ---------------------------------------------------------------------------
# Bulk Republish (SIMULATED action, real per-vehicle mechanism reused)
# ---------------------------------------------------------------------------

def republish_platform(platform, published_by):
    if platform not in FEED_PLATFORMS:
        return {"error": f"platform must be one of {FEED_PLATFORMS}"}

    unsold = _unsold_vehicles()
    republished = []

    for v in unsold:
        status = get_feed_status(v.id)
        entry = next((f for f in status["feeds"] if f["platform"] == platform), None)
        if entry and entry["status"] in ("pending", "error"):
            result = publish_to_feed(v.id, platform, published_by)
            if "error" not in result:
                republished.append(v.id)

    return {
        "platform": platform,
        "republished_count": len(republished),
        "republished_vehicle_ids": republished,
        "basis": SIMULATED_BASIS,
        "disclaimer": (
            f"SIMULATED bulk republish -- a real recorded action against every "
            f"real unsold vehicle currently pending/erroring on {platform}, but "
            f"no real syndication to {platform} occurs in this system."
        ),
    }


# ---------------------------------------------------------------------------
# Composed overview
# ---------------------------------------------------------------------------

def get_syndication_overview():
    feed_health = get_feed_health_rollup()
    lead_performance = get_syndication_lead_performance()

    total_errors = sum(p["error"] for p in feed_health["platforms"])
    total_pending = sum(p["pending"] for p in feed_health["platforms"])

    return {
        "total_unsold_vehicles": feed_health["total_unsold"],
        "total_listing_errors": total_errors,
        "total_listing_pending": total_pending,
        "listing_completeness_risk_count": feed_health["listing_completeness_risk"]["count"],
        "total_syndication_revenue": lead_performance["total_syndication_revenue"],
        "total_syndication_leads": lead_performance["total_syndication_leads"],
        "feed_health": feed_health,
        "lead_performance": lead_performance,
    }
