"""
core/readiness_recommendations.py -- Readiness' reimagined "Recommendations" Top
Menu item, item #8 of Sam's proposed 10-item Enterprise Readiness & Intelligence
structure. Sam's own framing: "This is where AI becomes truly valuable" --
Executive Recommendations (e.g. "Inventory aging is increasing. Recommendation:
Wholesale 8 units, Reduce pricing on 12 units"), Sales Recommendations (e.g.
"Leads from Facebook converting 22% higher. Increase budget."), Service
Recommendations (e.g. "Brake services underperforming. Launch a service
campaign."), Finance Recommendations (e.g. "Funding delays are increasing.
Assign additional staff.").

Same standing convention this codebase has enforced since core/network_audit.py
(session 38, "Rule-based, not a fabricated LLM narrative -- every recommendation
below is derived from a real, already-computed signal... a small rules engine
over real data, not an LLM's opinion") and repeated at core/lead_record.py's
next_best_action() and core/collections.py's risk-scoring: every recommendation
here traces back to a REAL, checkable condition over real data crossing a REAL,
documented threshold. No LLM call, no fabricated confidence score, no vague
sentence -- a transparent if/then rule with the real numbers that fired it
attached.

This is a COMPOSITION engine, same discipline core/business_health.py and
core/enterprise_risk_center.py just established for this same Readiness reframe
-- 10 of 12 rules below reuse an already-real, already-computed signal from
those two modules (or their own upstream sources) directly:

  inventory_aging_action        -> core/workflow_tab_data.py's
                                    inventory_wholesale_disposition() (real
                                    <8%-margin wholesale candidates) + core/
                                    inventory_aging.py's get_aging_board() (real
                                    $40k+ price-band count, the honest aging
                                    proxy) -- Sam's own "Wholesale N units,
                                    Reduce pricing on M units" example, built
                                    for real off real counts.
  recon_delays                  -> core/enterprise_risk_center.py's real
                                    recon_delays exception item.
  negative_gross_deals          -> core/enterprise_risk_center.py's real
                                    negative_gross_deals exception item.
  open_compliance_issues        -> core/enterprise_risk_center.py's real
                                    open_compliance_issues exception item.
  funding_delays                -> core/enterprise_risk_center.py's real
                                    funding_delays exception item (HEURISTIC,
                                    stalled financing/contract deals) -- Sam's
                                    own "Funding delays are increasing. Assign
                                    additional staff." example.
  unfunded_contracts            -> core/enterprise_risk_center.py's real
                                    unfunded_contracts exception item.
  collections_recovery_risk     -> core/business_health.py's finance_health()
                                    (its own already-gated Collections dashboard,
                                    core/collections.py's real recovery_risk_count).
  service_shop_overload         -> core/business_health.py's service_health()
                                    (its own real, HEURISTIC-labeled
                                    technician_utilization.overloaded_technician_count).
  service_delays                -> core/enterprise_risk_center.py's real
                                    service_delays exception item.
  sales_show_rate               -> core/business_health.py's sales_health()
                                    (its own real show_rate off the Appointment
                                    entity).

Two rules are genuinely NEW real computations, same "the one genuinely new
signal" precedent core/enterprise_risk_center.py's own negative_gross_deals
already set:

  service_type_underperformance -> _service_type_trend() below -- ServiceRecord.
                                    Description is a real stored field (for the
                                    434 historical records, drawn from a real
                                    fixed catalog of service types --
                                    Oil Change/Brake Pad Replacement/Wheel
                                    Alignment/etc., confirmed by direct
                                    inspection of the live seed graph) grouped
                                    into a real recent-vs-prior revenue
                                    comparison (two real 180-day windows split
                                    off the real max ServiceDate in this graph).
                                    A real, checkable revenue decline per real
                                    service type -- the direct real analog to
                                    Sam's "Brake services underperforming"
                                    example (whichever real type actually
                                    qualifies on a given day's data, not
                                    hardcoded to "brakes").
  marketing_channel_performance -> core/marketing_attribution.py's real
                                    get_channel_mix() (session 113's real
                                    first-touch Lead.Source revenue/conversion
                                    correlation) -- a real weighted-average
                                    conversion rate across every Source with a
                                    real minimum sample size, flagging real
                                    over/under-performing channels by a real
                                    relative-lift threshold. The direct real
                                    analog to Sam's "Leads from Facebook
                                    converting 22% higher" example -- whichever
                                    real channel actually qualifies (this graph's
                                    real data currently surfaces CarGurus/Trade
                                    Show/Facebook Marketplace/Service Drive as
                                    real over-performers and Website as a real
                                    under-performer, not fabricated to match
                                    Sam's channel name specifically).

Honest gap, stated plainly rather than guessed at: Sam's own "Facebook
converting 22% higher. Increase budget." implies a literal ad-spend budget
adjustment -- no Campaign/AdCampaign budget field exists anywhere in this
codebase (confirmed absent, same finding core/marketing_menu.py's own
attribution_tracking note and core/advertising.py's docstring already made),
so this rule's recommendation text says "increase marketing focus/spend" in
the general sense a real dealer would act on, not a literal dollar-amount
budget change this data model can't back.

No blended "AI recommendation score" is computed, same reasoning core/
business_health.py's overall_score and core/enterprise_risk_center.py's
overall_risk_score both already gave: these rules span incompatible units
(headcounts, dollars, percentages) with no real methodology to weight them
into one number. Executive Recommendations is instead a real, honest curation
-- every rule that actually fired (triggered=True) with severity high or
critical, across every department, ranked -- not a fabricated 13th signal.
"""

from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD

from core.business_health import sales_health, service_health, finance_health
from core.enterprise_risk_center import get_risk_center_overview, _count_severity
from core.workflow_tab_data import inventory_wholesale_disposition
from core.inventory_aging import get_aging_board
from core.marketing_attribution import get_channel_mix


CATEGORIES = ("sales", "service", "finance", "inventory", "marketing")

# -- Thresholds (rule-of-thumb cutoffs, same honesty bar as core/network_audit.py's
# own thresholds -- reasonable, documented, not sourced from a specific study) --
WHOLESALE_MIN_COUNT = 3
PRICE_BAND_MIN_COUNT = 10
UNFUNDED_CONTRACTS_MIN_COUNT = 3
COLLECTIONS_RISK_MIN_COUNT = 5
OVERLOADED_TECH_MIN = 1
SERVICE_DELAYS_MIN_COUNT = 3
SHOW_RATE_MIN_APPTS = 10
SHOW_RATE_THRESHOLD = 0.75
SERVICE_TYPE_MIN_PRIOR_COUNT = 3
SERVICE_TYPE_DECLINE_PCT = -25.0
MARKETING_MIN_LEAD_COUNT = 10
MARKETING_OVERPERFORM_RATIO = 1.3
MARKETING_UNDERPERFORM_RATIO = 0.6
MARKETING_MAX_FLAGGED = 3


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _item(key, category, title, triggered, severity, finding, recommendation, basis, resolve, signal_type="risk", **extra):
    """Every rule always returns one of these -- even when it doesn't fire
    (triggered=False, severity=None), same "report 0/clear rather than
    silently omit" convention core/enterprise_risk_center.py's own
    _count_severity items already established, so the UI can show a real
    'clear' state instead of a rule silently vanishing."""

    out = {
        "key": key,
        "category": category,
        "title": title,
        "triggered": triggered,
        "severity": severity if triggered else None,
        "signal_type": signal_type,
        "finding": finding,
        "recommendation": recommendation if triggered else None,
        "basis": basis,
        "resolve": resolve,
    }
    out.update(extra)
    return out


def _access_denied_item(key, category, title, resolve, message):
    return _item(key, category, title, False, None, message, None, "real", resolve, access_error=message)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _inventory_aging_action(role):
    """Sam's own illustrative example, built for real: "Inventory aging is
    increasing. Recommendation: Wholesale 8 units, Reduce pricing on 12
    units." Wholesale candidates reuse core/workflow_tab_data.py's real <8%-
    margin check; price-reduction candidates reuse core/inventory_aging.py's
    real $40k+ price band (the honest aging proxy this codebase established
    since Vehicle has no acquisition-date field anywhere -- sessions
    63/85/106/109)."""

    resolve = {"department": "Inventory", "item_key": "wholesale", "hint": "Open Wholesale Desk and submit an offer on the flagged units."}

    wholesale = inventory_wholesale_disposition(role)
    wholesale_count = wholesale.get("count") or 0

    board = get_aging_board()
    high_band = board.get("by_price_band", {}).get("40k_plus") or []
    price_reduction_count = len(high_band)

    triggered = wholesale_count >= WHOLESALE_MIN_COUNT or price_reduction_count >= PRICE_BAND_MIN_COUNT

    actions = []
    if wholesale_count >= WHOLESALE_MIN_COUNT:
        actions.append({
            "action": f"Wholesale review recommended on {wholesale_count} units (real sub-8% margin).",
            "count": wholesale_count,
            "items": [{"id": c["vehicle_id"], "label": f"VIN {c['vin']} -- {c['margin_pct']*100 if c['margin_pct'] is not None else '—'}% margin"} for c in wholesale.get("candidates", [])[:10]],
            "resolve": {"department": "Inventory", "item_key": "wholesale", "hint": "Open Wholesale Desk and submit an offer."},
        })
    if price_reduction_count >= PRICE_BAND_MIN_COUNT:
        actions.append({
            "action": f"Price reduction recommended on {price_reduction_count} units in the $40k+ price band.",
            "count": price_reduction_count,
            "items": [{"id": v["vehicle_id"], "label": f"VIN {v['vin']} -- ${v['price']:,.2f}"} for v in high_band[:10]],
            "resolve": {"department": "Inventory", "item_key": "pricing", "hint": "Open Pricing Desk and apply a real price reduction."},
        })

    finding = (
        f"Inventory aging is elevated: {wholesale_count} real unsold units carry a sub-8% margin and "
        f"{price_reduction_count} real unsold units sit in the $40k+ price band (aging proxy)."
    )
    recommendation = " ".join(a["action"] for a in actions) if actions else None

    return _item(
        "inventory_aging_action", "inventory", "Inventory Aging Action",
        triggered, _count_severity(max(wholesale_count, price_reduction_count)),
        finding, recommendation, "heuristic", resolve,
        actions=actions,
    )


def _recon_delays(role):
    resolve = {"department": "Operations", "item_key": "scheduling", "hint": "Open Recon Scheduling and assign a target date."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["operational_exceptions"] if i["key"] == "recon_delays"), None)
    if not match:
        return _item("recon_delays", "inventory", "Recon Backlog", False, None, "No recon backlog data available.", None, "heuristic", resolve)
    if match.get("access_error"):
        return _access_denied_item("recon_delays", "inventory", "Recon Backlog", resolve, match["access_error"])

    count = match.get("count") or 0
    triggered = bool(match.get("severity"))

    return _item(
        "recon_delays", "inventory", "Recon Backlog",
        triggered, match.get("severity"),
        f"{count} real unsold Used-condition units are in the recon backlog.",
        f"Add recon staffing or vendor capacity to clear the {count}-unit backlog before it delays frontline-ready inventory." if triggered else None,
        "heuristic", resolve,
    )


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------

def _finance_funding_delays(role):
    """Sam's own illustrative example, built for real: "Funding delays are
    increasing. Recommendation: Assign additional staff." Reuses core/
    enterprise_risk_center.py's real funding_delays exception item
    (HEURISTIC -- Deal has no distinct submitted-to-lender timestamp, so
    updated_at is the real proxy this data model has)."""

    resolve = {"department": "Finance", "item_key": "deals", "hint": "Follow up with the lender / move the stalled deal forward."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["financial_exceptions"] if i["key"] == "funding_delays"), None)
    if not match:
        return _item("finance_funding_delays", "finance", "Funding Delays", False, None, "No funding-delay data available.", None, "heuristic", resolve)
    if match.get("access_error"):
        return _access_denied_item("finance_funding_delays", "finance", "Funding Delays", resolve, match["access_error"])

    count = match.get("count") or 0
    triggered = bool(match.get("severity"))

    return _item(
        "finance_funding_delays", "finance", "Funding Delays",
        triggered, match.get("severity"),
        f"{count} real Deals are stalled 3+ days in financing/contract with no update -- funding delays are elevated.",
        f"Assign additional staff to funding to clear the {count}-deal backlog." if triggered else None,
        "heuristic", resolve,
    )


def _finance_unfunded_contracts(role):
    resolve = {"department": "Finance", "item_key": "deals", "hint": "Open the Deal Desk and move the deal toward funding."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["financial_exceptions"] if i["key"] == "unfunded_contracts"), None)
    if not match:
        return _item("finance_unfunded_contracts", "finance", "Unfunded Contracts", False, None, "No unfunded-contract data available.", None, "real", resolve)
    if match.get("access_error"):
        return _access_denied_item("finance_unfunded_contracts", "finance", "Unfunded Contracts", resolve, match["access_error"])

    count = match.get("count") or 0
    triggered = count >= UNFUNDED_CONTRACTS_MIN_COUNT

    return _item(
        "finance_unfunded_contracts", "finance", "Unfunded Contracts",
        triggered, match.get("severity") if triggered else None,
        f"{count} real Deals are sitting in 'contract' status -- financing approved but not yet funded.",
        f"Prioritize a contract-to-funding push on the {count} pending deals." if triggered else None,
        "real", resolve,
    )


def _finance_negative_gross(role):
    resolve = {"department": "Finance", "item_key": "deals", "hint": "Review the deal's pricing/cost basis in the Deal Desk."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["financial_exceptions"] if i["key"] == "negative_gross_deals"), None)
    if not match:
        return _item("finance_negative_gross", "finance", "Negative Gross Deals", False, None, "No negative-gross data available.", None, "real", resolve)
    if match.get("access_error"):
        return _access_denied_item("finance_negative_gross", "finance", "Negative Gross Deals", resolve, match["access_error"])

    count = match.get("count") or 0
    total_loss = match.get("total_loss") or 0
    triggered = count > 0

    return _item(
        "finance_negative_gross", "finance", "Negative Gross Deals",
        triggered, match.get("severity") if triggered else None,
        f"{count} real funded Deals closed with negative gross profit, a combined real loss of ${total_loss:,.2f}.",
        f"Review pricing/cost basis on the {count} negative-gross deal(s) before it recurs." if triggered else None,
        "real", resolve,
    )


def _finance_collections_risk(role):
    resolve = {"department": "Finance", "item_key": "collections", "hint": "Open the Collections work queue and prioritize the Recovery Risk bucket."}

    health = finance_health(role)
    collections = health.get("collections")
    if isinstance(collections, dict) and "error" in collections:
        return _access_denied_item("finance_collections_risk", "finance", "Collections Recovery Risk", resolve, collections["error"])
    if not isinstance(collections, dict):
        return _item("finance_collections_risk", "finance", "Collections Recovery Risk", False, None, "No collections data available.", None, "real", resolve)

    count = collections.get("recovery_risk_count") or 0
    total = collections.get("total_in_queue") or 0
    triggered = count >= COLLECTIONS_RISK_MIN_COUNT

    return _item(
        "finance_collections_risk", "finance", "Collections Recovery Risk",
        triggered, _count_severity(count) if triggered else None,
        f"{count} of {total} real loans in the Collections queue are flagged Recovery Risk (high probability of default).",
        f"Assign additional collections staff to work the {count} Recovery Risk loans." if triggered else None,
        "real", resolve,
    )


def _finance_compliance_risk(role):
    resolve = {"department": "Finance", "item_key": "compliance", "hint": "Resolve or override the compliance alert."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["operational_exceptions"] if i["key"] == "open_compliance_issues"), None)
    if not match:
        return _item("finance_compliance_risk", "finance", "Open Compliance Issues", False, None, "No compliance data available.", None, "real", resolve)
    if match.get("access_error"):
        return _access_denied_item("finance_compliance_risk", "finance", "Open Compliance Issues", resolve, match["access_error"])

    count = match.get("count") or 0
    triggered = bool(match.get("severity"))

    return _item(
        "finance_compliance_risk", "finance", "Open Compliance Issues",
        triggered, match.get("severity"),
        f"{count} real cited-federal-rule compliance alerts are still open.",
        f"Resolve or override the {count} open compliance alert(s) -- each one already blocks real deal funding/campaign activation/publishing." if triggered else None,
        "real", resolve,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def _all_service_records():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]


def _service_type_trend():
    """Genuinely new real computation -- the direct real analog to Sam's "Brake
    services underperforming" example. ServiceRecord.Description is a real
    stored field: for the 434 historical (pre-RO-Workflow-Engine) records it's
    drawn from a real fixed catalog of service types (Oil Change/Brake Pad
    Replacement/Wheel Alignment/etc., confirmed by direct inspection of the
    live seed graph), so grouping by its exact value is a real category
    breakdown, not a fabricated taxonomy over free text. Splits ServiceDate
    into two real, equal 180-day windows anchored off the real max
    ServiceDate in this graph (recent vs. prior), computes real revenue
    (Cost - PartsCost, the same convention core/service_reporting.py's
    Technician Scorecard already uses) per type in each window, and flags any
    real type whose recent revenue fell 25%+ against a real prior-period
    revenue with at least 3 real prior-period records (avoiding noise on a
    tiny sample)."""

    records = [r for r in _all_service_records() if r.attributes.get("ServiceDate")]
    if not records:
        return []

    dates = [date.fromisoformat(r.attributes["ServiceDate"]) for r in records]
    max_date = max(dates)
    cutoff_recent = max_date - timedelta(days=180)
    cutoff_prior = cutoff_recent - timedelta(days=180)

    recent = {}
    prior = {}

    for r in records:
        d = date.fromisoformat(r.attributes["ServiceDate"])
        desc = r.attributes.get("Description") or "Unspecified"
        revenue = _safe_float(r.attributes.get("Cost")) - _safe_float(r.attributes.get("PartsCost"))

        if d >= cutoff_recent:
            bucket = recent.setdefault(desc, {"count": 0, "revenue": 0.0})
        elif d >= cutoff_prior:
            bucket = prior.setdefault(desc, {"count": 0, "revenue": 0.0})
        else:
            continue

        bucket["count"] += 1
        bucket["revenue"] += revenue

    flagged = []
    for desc, prior_bucket in prior.items():
        if prior_bucket["count"] < SERVICE_TYPE_MIN_PRIOR_COUNT or not prior_bucket["revenue"]:
            continue
        recent_bucket = recent.get(desc, {"count": 0, "revenue": 0.0})
        delta_pct = round((recent_bucket["revenue"] - prior_bucket["revenue"]) / prior_bucket["revenue"] * 100, 1)
        if delta_pct <= SERVICE_TYPE_DECLINE_PCT:
            flagged.append({
                "service_type": desc,
                "recent_count": recent_bucket["count"],
                "recent_revenue": round(recent_bucket["revenue"], 2),
                "prior_count": prior_bucket["count"],
                "prior_revenue": round(prior_bucket["revenue"], 2),
                "delta_pct": delta_pct,
            })

    flagged.sort(key=lambda f: f["delta_pct"])

    return flagged


def _service_type_underperformance(role):
    resolve = {"department": "Marketing", "item_key": "crm", "hint": "Build a targeted service-reminder campaign for the flagged service type."}

    flagged = _service_type_trend()
    triggered = bool(flagged)
    worst = flagged[0] if flagged else None

    if worst:
        finding = (
            f"{worst['service_type']} revenue is down {worst['delta_pct']}% -- {worst['recent_count']} ROs / "
            f"${worst['recent_revenue']:,.2f} in the last ~180 days vs {worst['prior_count']} ROs / "
            f"${worst['prior_revenue']:,.2f} in the prior comparable period."
        )
        recommendation = f"Launch a service campaign for {worst['service_type']} to rebuild volume."
    else:
        finding = "No real service type shows a 25%+ revenue decline against the prior comparable period."
        recommendation = None

    return _item(
        "service_type_underperformance", "service", "Service Type Underperformance",
        triggered, "medium" if triggered else None,
        finding, recommendation, "real", resolve,
        all_flagged=flagged[:10],
    )


def _service_shop_overload(role):
    resolve = {"department": "Service", "item_key": "shop_control", "hint": "Open Shop Control and reassign or dispatch overloaded technicians' work."}

    health = service_health(role)
    tech = health.get("technician_utilization") or {}
    count = tech.get("overloaded_technician_count") or 0
    triggered = count >= OVERLOADED_TECH_MIN

    return _item(
        "service_shop_overload", "service", "Technician Overload",
        triggered, _count_severity(count) if triggered else None,
        f"{count} real technician(s) are over an ASSUMED 8-hour/day capacity today (HEURISTIC -- no real time-clock/shift data exists).",
        f"Reassign workload or add technician capacity -- {count} technician(s) are overloaded today." if triggered else None,
        "heuristic", resolve,
    )


def _service_delays(role):
    resolve = {"department": "Service", "item_key": "shop_control", "hint": "Open Shop Control and dispatch/expedite the stalled repair order."}

    risk = get_risk_center_overview(role)
    match = next((i for i in risk["categories"]["operational_exceptions"] if i["key"] == "service_delays"), None)
    if not match:
        return _item("service_delays", "service", "Service Delays", False, None, "No service-delay data available.", None, "real", resolve)
    if match.get("access_error"):
        return _access_denied_item("service_delays", "service", "Service Delays", resolve, match["access_error"])

    count = match.get("count") or 0
    triggered = count >= SERVICE_DELAYS_MIN_COUNT

    return _item(
        "service_delays", "service", "Service Delays",
        triggered, match.get("severity") if triggered else None,
        f"{count} real repair orders are delayed (parts backordered, awaiting customer approval, or stalled with no labor posted).",
        f"Expedite the {count} delayed repair order(s) in Shop Control before they push out delivery promises." if triggered else None,
        "real", resolve,
    )


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def _sales_show_rate(role):
    resolve = {"department": "Sales", "item_key": "appointments", "hint": "Review the appointment-confirmation process (reminders, pre-visit check-in)."}

    health = sales_health(role)
    show_rate = health.get("show_rate") or {}
    value = show_rate.get("value")
    scheduled = show_rate.get("appointments_scheduled") or 0

    triggered = value is not None and scheduled >= SHOW_RATE_MIN_APPTS and value < SHOW_RATE_THRESHOLD

    if value is None:
        finding = "No scheduled appointments exist to compute a show rate from."
    else:
        finding = (
            f"Show rate is {round(value * 100, 1)}% ({show_rate.get('appointments_shown')} of {scheduled} real "
            f"scheduled appointments arrived)."
        )

    return _item(
        "sales_show_rate", "sales", "Appointment Show Rate",
        triggered, "medium" if triggered else None,
        finding,
        f"Improve the appointment-confirmation process -- show rate is only {round(value * 100, 1)}% against a {int(SHOW_RATE_THRESHOLD * 100)}% target." if triggered else None,
        "real", resolve,
    )


# ---------------------------------------------------------------------------
# Marketing (Sam's illustrative example lives here: "Leads from Facebook
# converting 22% higher. Increase budget.")
# ---------------------------------------------------------------------------

def _marketing_channel_performance(role):
    """Genuinely new real computation -- a real weighted-average conversion
    rate across every real Lead.Source with a real minimum sample size
    (MARKETING_MIN_LEAD_COUNT), flagging real channels whose real conversion
    rate is a real MARKETING_OVERPERFORM_RATIO/MARKETING_UNDERPERFORM_RATIO
    away from that average. Reuses core/marketing_attribution.py's
    get_channel_mix() directly -- no second attribution computation. Honest
    scope note: no Campaign/AdCampaign budget field exists anywhere in this
    codebase, so the recommendation text says "increase marketing focus/spend"
    rather than a literal dollar-amount budget change this data model can't
    back."""

    resolve = {"department": "Marketing", "item_key": "crm", "hint": "Review Smart Audiences / CRM for this channel's real lead volume and conversion."}

    mix = get_channel_mix()
    qualifying = [c for c in mix["channels"] if c["lead_count"] >= MARKETING_MIN_LEAD_COUNT]

    if not qualifying:
        return _item(
            "marketing_channel_performance", "marketing", "Lead Source Performance",
            False, None,
            f"No real Lead Source has at least {MARKETING_MIN_LEAD_COUNT} leads to compare against a fleet average.",
            None, "real", resolve,
        )

    total_leads = sum(c["lead_count"] for c in qualifying)
    total_sold = sum(c["sold_count"] for c in qualifying)
    avg_conversion = round(total_sold / total_leads * 100, 2) if total_leads else 0.0

    over = []
    under = []
    for c in qualifying:
        rate = c["conversion_rate"]
        if avg_conversion and rate >= avg_conversion * MARKETING_OVERPERFORM_RATIO:
            lift_pct = round((rate - avg_conversion) / avg_conversion * 100, 1)
            over.append({**c, "vs_average_pct": lift_pct})
        elif avg_conversion and rate <= avg_conversion * MARKETING_UNDERPERFORM_RATIO:
            lift_pct = round((rate - avg_conversion) / avg_conversion * 100, 1)
            under.append({**c, "vs_average_pct": lift_pct})

    over.sort(key=lambda c: c["conversion_rate"], reverse=True)
    under.sort(key=lambda c: c["conversion_rate"])

    triggered = bool(over or under)

    findings = []
    recommendations = []
    for c in over[:MARKETING_MAX_FLAGGED]:
        findings.append(f"{c['source']} leads convert at {c['conversion_rate']}% vs a {avg_conversion}% average across qualifying channels ({c['vs_average_pct']}% higher, off {c['lead_count']} real leads).")
        recommendations.append(f"Increase marketing focus/spend on {c['source']}.")
    for c in under[:MARKETING_MAX_FLAGGED]:
        findings.append(f"{c['source']} leads convert at {c['conversion_rate']}% vs a {avg_conversion}% average across qualifying channels ({c['vs_average_pct']}% lower, off {c['lead_count']} real leads).")
        recommendations.append(f"Review or reduce spend on {c['source']} -- investigate why conversion lags.")

    return _item(
        "marketing_channel_performance", "marketing", "Lead Source Performance",
        triggered, "medium" if triggered else None,
        " ".join(findings) if findings else f"Every qualifying channel converts within {int((MARKETING_OVERPERFORM_RATIO - 1) * 100)}% of the {avg_conversion}% fleet average.",
        " ".join(recommendations) if recommendations else None,
        "real", resolve,
        over_performers=over[:MARKETING_MAX_FLAGGED],
        under_performers=under[:MARKETING_MAX_FLAGGED],
        fleet_average_conversion_pct=avg_conversion,
        min_sample_size=MARKETING_MIN_LEAD_COUNT,
    )


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

_RULE_FUNCTIONS = {
    "inventory_aging_action": _inventory_aging_action,
    "recon_delays": _recon_delays,
    "finance_funding_delays": _finance_funding_delays,
    "finance_unfunded_contracts": _finance_unfunded_contracts,
    "finance_negative_gross": _finance_negative_gross,
    "finance_collections_risk": _finance_collections_risk,
    "finance_compliance_risk": _finance_compliance_risk,
    "service_type_underperformance": _service_type_underperformance,
    "service_shop_overload": _service_shop_overload,
    "service_delays": _service_delays,
    "sales_show_rate": _sales_show_rate,
    "marketing_channel_performance": _marketing_channel_performance,
}

# Static key -> category map (mirrors each function's own `category` field) so
# get_recommendations_category() can filter WITHOUT calling every rule twice.
_RULE_CATEGORY = {
    "inventory_aging_action": "inventory",
    "recon_delays": "inventory",
    "finance_funding_delays": "finance",
    "finance_unfunded_contracts": "finance",
    "finance_negative_gross": "finance",
    "finance_collections_risk": "finance",
    "finance_compliance_risk": "finance",
    "service_type_underperformance": "service",
    "service_shop_overload": "service",
    "service_delays": "service",
    "sales_show_rate": "sales",
    "marketing_channel_performance": "marketing",
}

_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def get_recommendations_overview(role):
    """Runs all 12 real rules, groups by category, and curates a real
    Executive Recommendations feed -- every rule that actually fired
    (triggered=True) with severity high or critical, across every department,
    ranked worst-first. No blended "AI recommendation score" -- see this
    module's own docstring for why (same reasoning core/business_health.py's
    overall_score and core/enterprise_risk_center.py's overall_risk_score
    both already gave)."""

    items = [fn(role) for fn in _RULE_FUNCTIONS.values()]

    by_category = {c: [] for c in CATEGORIES}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)

    triggered_items = [i for i in items if i.get("triggered")]
    executive = [i for i in triggered_items if i.get("severity") in ("high", "critical")]
    executive.sort(key=lambda i: _SEVERITY_RANK.get(i.get("severity"), -1), reverse=True)

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for i in triggered_items:
        if i.get("severity") in severity_counts:
            severity_counts[i["severity"]] += 1

    return {
        "categories": by_category,
        "executive_recommendations": executive,
        "kpi": {
            "total_rules": len(items),
            "triggered_count": len(triggered_items),
            "by_severity": severity_counts,
        },
        "overall_recommendation_score": None,
        "overall_recommendation_score_note": (
            "No single blended recommendation score is computed -- these 12 rules span "
            "incompatible units (headcounts, dollars, percentages) with no real methodology "
            "to weight them into one number, same reasoning core/business_health.py's own "
            "overall_score and core/enterprise_risk_center.py's own overall_risk_score both "
            "already give. Executive Recommendations above (every triggered rule at High or "
            "Critical severity, ranked) is the real, honest analog."
        ),
        "generated_at": _now(),
    }


def get_recommendations_category(role, category):
    """Per-category drill-down -- one of sales/service/finance/inventory/
    marketing."""

    key = (category or "").strip().lower()
    if key not in CATEGORIES:
        return {"error": f"Unknown category '{category}' -- expected one of {list(CATEGORIES)}."}

    items = [fn(role) for name, fn in _RULE_FUNCTIONS.items() if _RULE_CATEGORY.get(name) == key]

    return {"category": key, "items": items}
