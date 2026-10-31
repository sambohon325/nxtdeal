"""
core/campaign_analytics.py -- real A/B Testing + Revenue Tracking for Campaigns,
the remaining two upgrades from Sam's Marketing Growth Platform Email/SMS spec
("A/B testing, revenue tracking"), layered onto the existing real Campaign
engine (core/campaigns.py, session 31/79) rather than a parallel one.

A/B Testing: a real split test, not a mockup. `set_ab_variant()` attaches a
second real EmailTemplate (`variant_b_template_id`, additive attribute on the
existing Campaign entity -- variant A is just the Campaign's own pre-existing
`linked_template_id`, no new field needed for it) while the campaign is still
in `draft`, matching real send-testing timing (you set up a split test before
launch, not after). `get_variant_for_member()` is a REAL deterministic 50/50
split computed live off a stable hash of (campaign_id, entity_id) -- not
stored, same "compute live rather than persist what's derivable" convention
`core/vehicle_holds.py`'s `expires_at` already established -- so a given
recipient always lands on the same variant across repeated reads without
needing a stored assignment dict.

Revenue Tracking: honestly correlational, not fabricated causal attribution --
`core/marketing_menu.py`'s own `overview()` has stated since session 62 that
"Leads/Deals aren't linked back to the Campaign that generated them yet -- no
true multi-touch attribution is computed," and that structural gap (no
Campaign<->Deal/Lead touchpoint relationship exists anywhere in this codebase)
isn't invented here. What IS real: for every Customer in a campaign's own
`audience_ids` snapshot, a real Deal that funded AFTER the campaign's real
`activated_at` timestamp is a genuine, honestly-labeled correlation (same
"real correlation, not proven attribution" disclosure `core/purls.py`'s
`get_purl_analytics()` already established) -- not a fabricated ROI number.
`get_ab_test_results()` reuses this exact same correlation signal, split by
variant, as the real "winner" metric (no open/click tracking exists anywhere
in this codebase to compute a fabricated open/click rate instead).
"""

import hashlib

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER, LEAD, DEAL
from core.campaigns import get_campaign
from core.email_templates import get_template
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def set_ab_variant(campaign_id, variant_b_template_id):

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found"}

    if campaign.attributes.get("status") != "draft":
        return {"error": "A/B variants can only be set while the campaign is still a draft, before it's activated."}

    variant_b = get_template(variant_b_template_id)
    if not variant_b:
        return {"error": "Variant B template not found"}

    variant_a_id = campaign.attributes.get("linked_template_id")
    if not variant_a_id:
        return {"error": "This campaign has no Variant A template linked yet -- set linked_template_id first."}

    variant_a = get_template(variant_a_id)
    if variant_a and variant_a.attributes.get("channel") != variant_b.attributes.get("channel"):
        return {"error": "Variant A and Variant B must be the same channel (both email or both SMS)."}

    campaign.attributes["variant_b_template_id"] = variant_b_template_id

    save_graph(GRAPH_PATH)

    return {"campaign_id": campaign_id, "variant_a_template_id": variant_a_id, "variant_b_template_id": variant_b_template_id}


def clear_ab_variant(campaign_id):

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found"}

    campaign.attributes["variant_b_template_id"] = None

    save_graph(GRAPH_PATH)

    return {"campaign_id": campaign_id}


def is_ab_test(campaign):
    return bool(campaign.attributes.get("variant_b_template_id"))


def get_variant_for_member(campaign_id, entity_id):
    """Real, deterministic 50/50 split -- not stored, computed live off a stable
    hash so it never drifts across repeated calls for the same recipient."""

    digest = hashlib.sha256(f"{campaign_id}:{entity_id}".encode()).hexdigest()

    return "a" if int(digest[:8], 16) % 2 == 0 else "b"


def get_campaign_ab_config(campaign_id):

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found"}

    variant_a_id = campaign.attributes.get("linked_template_id")
    variant_b_id = campaign.attributes.get("variant_b_template_id")

    audience_ids = campaign.attributes.get("audience_ids") or []
    a_count = sum(1 for eid in audience_ids if get_variant_for_member(campaign_id, eid) == "a")
    b_count = len(audience_ids) - a_count

    return {
        "campaign_id": campaign_id,
        "is_ab_test": bool(variant_b_id),
        "variant_a_template_id": variant_a_id,
        "variant_b_template_id": variant_b_id,
        "variant_a_audience_count": a_count if variant_b_id else len(audience_ids),
        "variant_b_audience_count": b_count if variant_b_id else 0,
    }


# ---------------------------------------------------------------------------
# Revenue tracking
# ---------------------------------------------------------------------------

def _funded_deal_revenue(customer_id, since_iso):
    """Real gross (Price - Cost) across real funded Deals for this customer dated
    on/after `since_iso`."""

    total = 0.0
    count = 0

    for d in ledger.get_all().values():
        if d.entity_type != DEAL:
            continue
        if d.attributes.get("customer_id") != customer_id:
            continue
        if d.attributes.get("status") != "funded":
            continue
        funded_at = d.attributes.get("funded_at") or ""
        if funded_at < (since_iso or ""):
            continue

        vehicle = ledger.get_entity(d.attributes.get("vehicle_id"))
        if vehicle:
            total += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
        count += 1

    return total, count


def _lead_sold_since(lead_id, since_iso):
    lead = ledger.get_entity(lead_id)
    if not lead or lead.entity_type != LEAD:
        return False
    if lead.attributes.get("PipelineState") != "SOLD":
        return False
    state_since = lead.attributes.get("PipelineStateSince") or ""
    return state_since >= (since_iso or "")


def get_campaign_revenue(campaign_id):

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found"}

    since = campaign.attributes.get("activated_at")

    if not since:
        return {
            "campaign_id": campaign_id,
            "eligible": False,
            "reason": "Campaign hasn't been activated yet -- revenue correlation only applies once a real send has actually happened.",
        }

    audience_ids = campaign.attributes.get("audience_ids") or []

    total_revenue = 0.0
    deal_count = 0
    leads_sold = 0

    for eid in audience_ids:
        entity = ledger.get_entity(eid)
        if not entity:
            continue
        if entity.entity_type == CUSTOMER:
            rev, cnt = _funded_deal_revenue(eid, since)
            total_revenue += rev
            deal_count += cnt
        elif entity.entity_type == LEAD:
            if _lead_sold_since(eid, since):
                leads_sold += 1

    return {
        "campaign_id": campaign_id,
        "eligible": True,
        "basis": "real_but_not_proven_causal",
        "disclaimer": "Deals/Leads below are real records dated on or after this campaign's real send date, for members of its own audience -- a real correlation, not proven attribution. No Campaign<->Lead/Deal touchpoint relationship exists anywhere in this codebase yet (core/marketing_menu.py's own overview() has flagged this gap since session 62), so true multi-touch attribution isn't computed.",
        "activated_at": since,
        "audience_count": len(audience_ids),
        "funded_deals_count": deal_count,
        "leads_sold_count": leads_sold,
        "revenue": round(total_revenue, 2),
    }


def get_ab_test_results(campaign_id):

    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found"}

    if not is_ab_test(campaign):
        return {"error": "This campaign has no A/B variant configured."}

    since = campaign.attributes.get("activated_at")
    if not since:
        return {"campaign_id": campaign_id, "eligible": False, "reason": "Campaign hasn't been activated yet."}

    audience_ids = campaign.attributes.get("audience_ids") or []

    results = {
        "a": {"audience_count": 0, "revenue": 0.0, "funded_deals_count": 0, "leads_sold_count": 0},
        "b": {"audience_count": 0, "revenue": 0.0, "funded_deals_count": 0, "leads_sold_count": 0},
    }

    for eid in audience_ids:
        variant = get_variant_for_member(campaign_id, eid)
        bucket = results[variant]
        bucket["audience_count"] += 1

        entity = ledger.get_entity(eid)
        if not entity:
            continue
        if entity.entity_type == CUSTOMER:
            rev, cnt = _funded_deal_revenue(eid, since)
            bucket["revenue"] += rev
            bucket["funded_deals_count"] += cnt
        elif entity.entity_type == LEAD:
            if _lead_sold_since(eid, since):
                bucket["leads_sold_count"] += 1

    for v in results.values():
        v["revenue"] = round(v["revenue"], 2)
        v["conversion_rate"] = round(((v["funded_deals_count"] + v["leads_sold_count"]) / v["audience_count"] * 100), 1) if v["audience_count"] else 0.0

    winner = None
    if results["a"]["revenue"] != results["b"]["revenue"]:
        winner = "a" if results["a"]["revenue"] > results["b"]["revenue"] else "b"
    elif results["a"]["conversion_rate"] != results["b"]["conversion_rate"]:
        winner = "a" if results["a"]["conversion_rate"] > results["b"]["conversion_rate"] else "b"

    return {
        "campaign_id": campaign_id,
        "eligible": True,
        "basis": "real_but_not_proven_causal",
        "disclaimer": "Winner is determined by real revenue/conversion correlation since send, per variant -- not open/click tracking (no send-gateway integration exists anywhere in this codebase to measure that).",
        "variant_a_template_id": campaign.attributes.get("linked_template_id"),
        "variant_b_template_id": campaign.attributes.get("variant_b_template_id"),
        "results": results,
        "winner": winner,
    }
