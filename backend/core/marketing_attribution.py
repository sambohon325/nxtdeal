"""
core/marketing_attribution.py -- the capstone of Sam's Marketing Growth Platform
reframe (session 113): Attribution Engine + Marketing ROI Dashboard + Vehicle
Attribution, explicitly named as most valuable "once other channels are feeding
it real event data" -- which is now true after the CRM (Customer 360/Smart
Audiences/Lead Scoring), PURLs, and Email/SMS (personalization/A-B/revenue)
slices this same rebuild arc already shipped.

Structural honesty, restated before anything else: core/marketing_menu.py's own
overview()/`_campaigns()` have flagged since session 62 that "Leads/Deals aren't
linked back to the Campaign that generated them yet -- no true multi-touch
attribution is computed." That gap (no Campaign<->Lead/Deal touchpoint
relationship anywhere in this codebase) is real and is NOT invented here. What
this module builds instead is the strongest REAL signal this codebase actually
has for attribution: `Lead.Source` -- a single, first-touch field set at intake
time and, as of sessions 84/85/93/105/106/111 (plus this same session's own
PURL slice), populated by essentially every real marketing/sales workflow
(PURL, Orphan Owner Mining, Service Handoff, Trigger Alert, Event, Walk-In,
Phone-Up, Referral, Website, Autotrader -- core/lead_intake.py's
VALID_SOURCES). Channel Mix & ROI by Source is real, HONEST first-touch
attribution -- not multi-touch, said so plainly rather than oversold.

Revenue is computed once, consistently, in this module's own
`_funded_deal_gross_since()` (identical Price - Cost gross-profit basis to
core/marketing_menu.py's `_funded_deal_gross()`/core/campaign_analytics.py's
`_funded_deal_revenue()`) rather than mixing bases already established
elsewhere in this codebase -- core/purls.py's own `get_purl_analytics()`
happens to use a DIFFERENT basis (full Vehicle.Price, not gross profit) for
its own per-PURL card. This module reuses that existing function verbatim for
the PURL ROI rollup (so a PURL's number here always matches what its own
board already shows) but flags the basis mismatch explicitly rather than
silently blending two incompatible numbers into one total.

Every Lead's real revenue is resolved through BECAME/GENERATED_LEAD identity
resolution -- core/lead_scoring.py's `_resolve_identity()`, reused directly
rather than reimplemented, since a Lead itself never funds a Deal, only the
real Customer it becomes does.

Vehicle Attribution cross-references two real, PERSISTED "what's being
marketed" signals -- inventory_ads Campaign make/model targeting params
(Campaign.attributes["params"]) and SocialPost.linked_vehicle_ids (session 83)
-- against real funded-Deal sales by the sold vehicle's own Make/Model. A real
correlation between marketing attention and sales outcome, not a claim that
any specific post/campaign caused any specific sale. Deliberately does NOT
attempt to attribute PURL Inventory Matches -- that offer is computed LIVE on
every fetch (core/purls.py's `get_personalized_offer()`/`_inventory_matches()`)
and never persisted, so there is no historical record of which vehicles were
actually shown to which PURL visitor to attribute against.
"""

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE, CAMPAIGN, SOCIAL_POST
from core.lead_scoring import _resolve_identity


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _vehicles_by_id():
    return {v.id: v for v in _entities(VEHICLE)}


def _funded_deal_gross_since(customer_ids, since_iso, vehicles_by_id):
    """Real gross (Price - Cost) across real funded Deals for any of these real
    customer ids, optionally dated on/after since_iso (None = no floor)."""

    total = 0.0
    count = 0

    if not customer_ids:
        return total, count

    for d in _entities(DEAL):
        if d.attributes.get("status") != "funded":
            continue
        if d.attributes.get("customer_id") not in customer_ids:
            continue
        if since_iso:
            funded_at = d.attributes.get("funded_at") or ""
            if funded_at < since_iso:
                continue

        vehicle = vehicles_by_id.get(d.attributes.get("vehicle_id"))
        if vehicle:
            total += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
        count += 1

    return total, count


# ---------------------------------------------------------------------------
# Channel Mix & ROI by Lead Source (real, honest first-touch attribution)
# ---------------------------------------------------------------------------

def get_channel_mix():

    vehicles_by_id = _vehicles_by_id()
    leads = _entities(LEAD)

    by_source = {}

    for lead in leads:
        source = lead.attributes.get("Source") or "Unknown"
        bucket = by_source.setdefault(source, {
            "source": source,
            "lead_count": 0,
            "sold_count": 0,
            "revenue": 0.0,
            "funded_deals_count": 0,
        })
        bucket["lead_count"] += 1

        if lead.attributes.get("PipelineState") == "SOLD":
            bucket["sold_count"] += 1

        identity = _resolve_identity(lead.id)
        revenue, deal_count = _funded_deal_gross_since(identity["customer_ids"], None, vehicles_by_id)
        bucket["revenue"] += revenue
        bucket["funded_deals_count"] += deal_count

    results = []
    for bucket in by_source.values():
        bucket["revenue"] = round(bucket["revenue"], 2)
        bucket["conversion_rate"] = round(bucket["sold_count"] / bucket["lead_count"] * 100, 1) if bucket["lead_count"] else 0.0
        bucket["revenue_per_lead"] = round(bucket["revenue"] / bucket["lead_count"], 2) if bucket["lead_count"] else 0.0
        results.append(bucket)

    results.sort(key=lambda b: b["revenue"], reverse=True)

    return {
        "basis": "real_first_touch_not_multi_touch",
        "disclaimer": (
            "Revenue is a real correlation -- gross-profit (Price - Cost) funded Deals "
            "for the Customer each Lead became, with no timing floor -- grouped by each "
            "Lead's own real, single first-touch Source field. This is real first-touch "
            "attribution, not proven multi-touch attribution: no Campaign<->Lead/Deal "
            "touchpoint relationship exists anywhere in this codebase (see "
            "core/marketing_menu.py's own attribution_tracking note)."
        ),
        "channels": results,
        "total_leads": len(leads),
        "total_revenue": round(sum(b["revenue"] for b in results), 2),
    }


# ---------------------------------------------------------------------------
# Marketing ROI Dashboard -- composes the channel mix above with the two
# already-real per-channel revenue engines this rebuild arc already shipped
# (Campaign revenue, PURL revenue), rather than a third/fourth computation.
# ---------------------------------------------------------------------------

def get_marketing_roi_dashboard():

    from core.campaigns import list_campaigns
    from core.campaign_analytics import get_campaign_revenue
    from core.purls import list_purls, get_purl_analytics

    channel_mix = get_channel_mix()

    campaigns = [c for c in list_campaigns() if c.attributes.get("status") in ("active", "completed")]
    campaign_rows = []
    campaign_total_revenue = 0.0

    for c in campaigns:
        rev = get_campaign_revenue(c.id)
        if isinstance(rev, dict) and rev.get("eligible"):
            campaign_total_revenue += rev["revenue"]
            campaign_rows.append({
                "campaign_id": c.id,
                "name": c.attributes.get("name"),
                "campaign_type": c.attributes.get("campaign_type"),
                "channel": c.attributes.get("channel"),
                "revenue": rev["revenue"],
                "funded_deals_count": rev["funded_deals_count"],
                "leads_sold_count": rev["leads_sold_count"],
            })

    campaign_rows.sort(key=lambda r: r["revenue"], reverse=True)

    purl_list = list_purls().get("purls", [])
    purl_rows = []
    purl_total_revenue = 0.0

    for p in purl_list:
        analytics = get_purl_analytics(p["id"])
        if isinstance(analytics, dict) and "correlated_since_creation" in analytics:
            rev = analytics["correlated_since_creation"]["revenue"]
            purl_total_revenue += rev
            purl_rows.append({
                "purl_id": p["id"],
                "revenue": rev,
                "visits": analytics.get("visits", 0),
                "lead_generated": analytics.get("lead_generated", False),
            })

    purl_rows.sort(key=lambda r: r["revenue"], reverse=True)

    return {
        "channel_mix": channel_mix,
        "campaign_roi": {
            "basis": "real_but_not_proven_causal",
            "disclaimer": (
                "Same audience-since-activation correlation core/campaign_analytics.py's "
                "get_campaign_revenue() computes per campaign, summed here across every "
                "activated/completed campaign. Gross-profit basis (Price - Cost)."
            ),
            "total_revenue": round(campaign_total_revenue, 2),
            "campaigns": campaign_rows[:25],
        },
        "purl_roi": {
            "basis": "real_but_not_proven_causal",
            "disclaimer": (
                "Same per-PURL correlation core/purls.py's get_purl_analytics() computes, "
                "summed here across every PURL. NOTE: this uses full Vehicle.Price as its "
                "revenue basis (not gross profit) -- a different basis from campaign_roi "
                "above, inherited as-is from that module's own existing computation rather "
                "than silently reconciled here."
            ),
            "total_revenue": round(purl_total_revenue, 2),
            "purls": purl_rows[:25],
        },
    }


# ---------------------------------------------------------------------------
# Vehicle Attribution
# ---------------------------------------------------------------------------

def get_vehicle_attribution():

    vehicles_by_id = _vehicles_by_id()

    marketed = {}

    for c in _entities(CAMPAIGN):
        if c.attributes.get("campaign_type") != "inventory_ads":
            continue
        params = c.attributes.get("params") or {}
        make = (params.get("make") or "").strip()
        model = (params.get("model") or "").strip()
        if not make and not model:
            continue
        key = (make or "Any Make", model or "Any Model")
        bucket = marketed.setdefault(key, {"make": key[0], "model": key[1], "campaign_mentions": 0, "social_mentions": 0})
        bucket["campaign_mentions"] += 1

    for post in _entities(SOCIAL_POST):
        for vid in (post.attributes.get("linked_vehicle_ids") or []):
            v = vehicles_by_id.get(vid)
            if not v:
                continue
            key = (v.attributes.get("Make") or "Unknown", v.attributes.get("Model") or "Unknown")
            bucket = marketed.setdefault(key, {"make": key[0], "model": key[1], "campaign_mentions": 0, "social_mentions": 0})
            bucket["social_mentions"] += 1

    sold_by_make_model = {}

    for d in _entities(DEAL):
        if d.attributes.get("status") != "funded":
            continue
        v = vehicles_by_id.get(d.attributes.get("vehicle_id"))
        if not v:
            continue
        key = (v.attributes.get("Make") or "Unknown", v.attributes.get("Model") or "Unknown")
        bucket = sold_by_make_model.setdefault(key, {"funded_count": 0, "gross_revenue": 0.0})
        bucket["funded_count"] += 1
        bucket["gross_revenue"] += _safe_float(v.attributes.get("Price")) - _safe_float(v.attributes.get("Cost"))

    all_keys = set(marketed.keys()) | set(sold_by_make_model.keys())

    rows = []
    for key in all_keys:
        m = marketed.get(key, {"campaign_mentions": 0, "social_mentions": 0})
        s = sold_by_make_model.get(key, {"funded_count": 0, "gross_revenue": 0.0})
        rows.append({
            "make": key[0],
            "model": key[1],
            "campaign_mentions": m["campaign_mentions"],
            "social_mentions": m["social_mentions"],
            "funded_deals_count": s["funded_count"],
            "gross_revenue": round(s["gross_revenue"], 2),
            "marketed": (m["campaign_mentions"] + m["social_mentions"]) > 0,
        })

    rows.sort(key=lambda r: (r["gross_revenue"], r["campaign_mentions"] + r["social_mentions"]), reverse=True)

    marketed_and_sold = [r for r in rows if r["marketed"] and r["funded_deals_count"] > 0]
    marketed_not_sold = [r for r in rows if r["marketed"] and r["funded_deals_count"] == 0]
    sold_not_marketed = [r for r in rows if not r["marketed"] and r["funded_deals_count"] > 0]

    return {
        "basis": "real_but_not_proven_causal",
        "disclaimer": (
            "Marketing signals are real, persisted records -- inventory_ads Campaign "
            "make/model targeting params and SocialPost.linked_vehicle_ids -- cross-"
            "referenced against real funded Deals by the sold vehicle's own Make/Model. "
            "A real correlation between marketing attention and sales outcome, not proof "
            "any specific post or campaign caused any specific sale. PURL Inventory "
            "Matches are deliberately excluded -- that offer is computed live on every "
            "fetch and never persisted, so there is no historical record to attribute "
            "against."
        ),
        "rows": rows[:50],
        "marketed_and_sold_count": len(marketed_and_sold),
        "marketed_not_sold_count": len(marketed_not_sold),
        "sold_not_marketed_count": len(sold_not_marketed),
    }
