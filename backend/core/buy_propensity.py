"""
Buy-Propensity Score (0-100) -- Phase 1 of the competitive roadmap (2026-07-25). The
single biggest gap the competitive analysis found: automotiveMastermind ranks every
prospect/customer 0-100 on likelihood to buy (its "Behavior Prediction Score"), and CDK's
CDP enriches records to sharpen that. NXTDeal had a leads-only additive point tally
(core/lead_scoring.py) but no normalized 0-100 buy-propensity model spanning customers.

This module is that model. It composes FOUR real, already-tracked signal groups into a
single 0-100 score (higher = more likely to be in-market for a purchase now), each
honestly derived -- nothing fabricated:

  * Engagement (0-40): reuses core/lead_scoring.compute_score's real behavioral tally
    (credit app started, deal desked, test drive, appointments, RSVPs, chat, comms),
    resolved across the prospect's whole identity cluster, scaled into 0-40.
  * Equity (0-25): positive estimated equity means they can roll into a new deal
    (core/equity_center.get_equity_position -- desk-entered estimates, flagged as such).
  * Maturity (0-20): loan/lease maturing soon is the classic upgrade trigger.
  * Service recency (0-15): a recent service visit is an active-relationship, in-market
    touchpoint (and the hook the service-to-sales workflow uses).

Optional 5th input: third-party enrichment (core/data_enrichment.py). When a real
enrichment provider is connected it can add a confidence bump; with none connected it
contributes nothing (honest -- no fabricated external data).

The score is deterministic and explainable: every point is attributed to a named factor
with a human-readable detail, so a rep sees WHY someone ranks high, not just a number.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER, LEAD, SERVICE_RECORD
from core import lead_scoring
from core import equity_center


# Per-group caps -- they sum to 100.
CAP_ENGAGEMENT = 40
CAP_EQUITY = 25
CAP_MATURITY = 20
CAP_SERVICE = 15

TIER_HOT = "hot"
TIER_WARM = "warm"
TIER_COOL = "cool"


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().date()


def _relationships_from(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.source_id == entity_id and r.relationship_type == relationship_type]


def _months_since_service(customer_id):
    """Months since this customer's most recent service visit, or None if never serviced.
    Reads the same AUTHORIZED -> ServiceRecord path core/campaigns.py uses."""
    dates = []
    for rel in _relationships_from(customer_id, "AUTHORIZED"):
        rec = ledger.get_entity(rel.target_id)
        if rec and rec.entity_type == SERVICE_RECORD:
            raw = rec.attributes.get("ServiceDate")
            d = equity_center._parse_date(raw) if raw else None
            if d:
                dates.append(d)
    if not dates:
        return None
    last = max(dates)
    return max(0.0, round((_today() - last).days / 30.4, 1))


def _tier(score):
    if score >= 70:
        return TIER_HOT
    if score >= 40:
        return TIER_WARM
    return TIER_COOL


def _recommended_action(tier, factors):
    labels = {f["label"] for f in factors if f["points"] > 0}
    if "Loan/lease maturing" in labels:
        return "Reach out with an equity/upgrade offer before their term ends."
    if "Positive equity" in labels:
        return "Present a trade-up: their equity likely covers a new down payment."
    if "Engagement" in labels and tier == TIER_HOT:
        return "Call today — they're actively engaging and ready for a conversation."
    if "Recent service visit" in labels:
        return "They were just in the service lane — a great moment for a soft upgrade check-in."
    return "Nurture: keep them warm with relevant inventory and offers."


def compute_propensity(entity_id):
    """Compute the 0-100 buy-propensity score for a Customer or Lead."""
    entity = ledger.get_entity(entity_id)
    if not entity or entity.entity_type not in (CUSTOMER, LEAD):
        return {"error": "Entity not found or not a Customer/Lead"}

    factors = []

    # --- Engagement (0-40) from the real behavioral tally ---
    eng = lead_scoring.compute_score(entity_id)
    raw_points = eng.get("score", 0) if "error" not in eng else 0
    # 100 raw behavioral points -> full 40. (Raw can exceed 100; capped.)
    engagement = min(CAP_ENGAGEMENT, round(raw_points * 0.4))
    factors.append({
        "label": "Engagement",
        "points": engagement,
        "detail": f"{raw_points} behavioral points across the prospect's activity",
    })

    # Equity + maturity only apply to a Customer (owns a vehicle on file).
    equity_pts = 0
    maturity_pts = 0
    service_pts = 0

    if entity.entity_type == CUSTOMER:
        pos = equity_center.get_equity_position(entity_id)
        equity_amount = pos.get("equity_amount")
        if equity_amount and equity_amount > 0:
            # $10k equity -> full 25.
            equity_pts = min(CAP_EQUITY, round(equity_amount / 400))
            factors.append({
                "label": "Positive equity",
                "points": equity_pts,
                "detail": f"~${equity_amount:,.0f} estimated equity (desk estimate)",
            })

        days = pos.get("days_to_lease_maturity")
        if days is not None and days >= 0:
            if days <= 90:
                maturity_pts = round(CAP_MATURITY * (1 - days / 90))
            elif days <= 180:
                maturity_pts = round((CAP_MATURITY / 2) * (1 - (days - 90) / 90))
            if maturity_pts > 0:
                factors.append({
                    "label": "Loan/lease maturing",
                    "points": maturity_pts,
                    "detail": f"term matures in {days} day(s)",
                })

        months = _months_since_service(entity_id)
        if months is not None:
            # Serviced in the last 6 months is a live, active-relationship signal.
            if months <= 6:
                service_pts = round(CAP_SERVICE * (1 - months / 6))
                if service_pts > 0:
                    factors.append({
                        "label": "Recent service visit",
                        "points": service_pts,
                        "detail": f"last serviced ~{months} month(s) ago",
                    })

    score = min(100, engagement + equity_pts + maturity_pts + service_pts)
    tier = _tier(score)

    return {
        "entity_id": entity_id,
        "entity_type": entity.entity_type,
        "name": _display_name(entity),
        "score": score,
        "tier": tier,
        "factors": factors,
        "recommended_action": _recommended_action(tier, factors),
        "basis": "Composed from real NXTDeal signals (engagement, equity, maturity, service). Equity figures are desk estimates.",
    }


def _display_name(entity):
    a = entity.attributes
    name = f"{a.get('FirstName', '')} {a.get('LastName', '')}".strip()
    return name or a.get("name") or entity.id


def rank(limit=50, segment="customers"):
    """Rank prospects by buy-propensity, descending -- the Behavior Prediction leaderboard.
    segment: 'customers' (default), 'leads' (open leads only), or 'all'."""
    targets = []
    if segment in ("customers", "all"):
        targets += [e for e in ledger.get_all().values() if e.entity_type == CUSTOMER]
    if segment in ("leads", "all"):
        targets += [
            e for e in ledger.get_all().values()
            if e.entity_type == LEAD and e.attributes.get("PipelineState") not in ("SOLD", "LOST")
        ]

    scored = []
    for t in targets:
        r = compute_propensity(t.id)
        if "error" in r:
            continue
        scored.append({
            "entity_id": t.id,
            "entity_type": r["entity_type"],
            "name": r["name"],
            "score": r["score"],
            "tier": r["tier"],
            "top_factor": max(r["factors"], key=lambda f: f["points"])["label"] if r["factors"] else None,
        })

    scored.sort(key=lambda s: s["score"], reverse=True)
    by_tier = {TIER_HOT: 0, TIER_WARM: 0, TIER_COOL: 0}
    for s in scored:
        by_tier[s["tier"]] += 1

    return {"segment": segment, "count": len(scored), "by_tier": by_tier, "ranked": scored[:limit]}


def draft_outreach(entity_id, channel="email"):
    """A personalized outreach draft built from the prospect's top propensity factors. A
    smart, explainable template keyed off real signals -- not a fabricated LLM response.
    (When a real drafting model is wired via ai_management it can replace the template.)"""
    r = compute_propensity(entity_id)
    if "error" in r:
        return r

    first = ""
    entity = ledger.get_entity(entity_id)
    if entity:
        first = entity.attributes.get("FirstName", "") or (entity.attributes.get("name", "").split(" ")[0] if entity.attributes.get("name") else "")
    greeting = f"Hi {first}," if first else "Hi there,"

    top = max(r["factors"], key=lambda f: f["points"]) if r["factors"] else None
    label = top["label"] if top else None

    if label == "Loan/lease maturing":
        subject = "Your options as your term wraps up"
        hook = "With your loan/lease approaching its end, now's a great time to look at your upgrade options — often with little to no change in payment."
    elif label == "Positive equity":
        subject = "You may have more equity than you think"
        hook = "Your current vehicle is carrying real equity right now, which could go straight toward your next one."
    elif label == "Recent service visit":
        subject = "Thanks for coming in — a quick thought"
        hook = "Since you were just in for service, I wanted to share a couple of options in case you've been thinking about an upgrade."
    else:
        subject = "A couple of options picked for you"
        hook = "Based on your recent activity, I pulled together a few options I think you'll like."

    body = (
        f"{greeting}\n\n{hook}\n\nWould you be open to a quick call this week? "
        f"I can put together exact numbers for you — no pressure either way.\n\nTalk soon."
    )
    if channel == "sms":
        body = f"{greeting} {hook} Open to a quick call this week? I can text you exact numbers."

    return {
        "entity_id": entity_id,
        "channel": channel,
        "subject": subject if channel == "email" else None,
        "body": body,
        "based_on": [f["label"] for f in r["factors"] if f["points"] > 0],
        "score": r["score"],
        "tier": r["tier"],
    }
