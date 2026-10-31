"""Equity Center (2026-07-23): the graph-native equity / trade-up opportunity
engine. Consolidates three closely-related dealership motions that were, until
now, only ever surfaced as HEURISTIC one-off signals scattered across
core/trigger_alerts.py's Timeline (its `equity_mining` and `lease_maturity`
scans) and core/customer_360.py's Trade-Equity panel:

    1. Equity mining     -- customers whose owned vehicle is worth more than
                            what they still owe (positive equity), a natural
                            trade-up / upgrade prospect.
    2. Lease maturity    -- customers whose current loan/lease matures soon and
                            who therefore need a next vehicle decision made.
    3. Trade / upgrade   -- the offer motion that turns 1 and 2 into a recorded
       opportunities        upgrade offer on the customer's own record.

GRAPH-NATIVE, single source of truth, exactly like core/customer_journey.py:
everything this module knows lives DIRECTLY as attributes on the existing
Customer entity, saved by the same core/storage.py save_graph() that already
persists everything else -- NOT a separate JSON store, not a new entity type.
Upgrade offers accumulate inline as an `equity_upgrade_offers` list on the
customer, the same "small, bounded, directly-useful-to-read-back per customer"
reasoning core/customer_journey.py used for journey_history.

HONEST REAL-vs-ESTIMATED SPLIT (session 110's disclosure convention): the
Customer entity in this codebase carries NO real amortization payoff quote and
NO real third-party market valuation -- no lender payoff API and no valuation
vendor (KBB, Black Book, MMR, etc.) is connected anywhere in this codebase. So
estimated_payoff and estimated_value are ESTIMATES: taken as explicit inputs on
the customer record (`estimated_payoff`, `estimated_value`) when a desk has
entered them, and every derived figure (equity_amount, status, total estimated
opportunity) is stamped `is_estimated: True` with an explicit `basis` and
`disclaimer`, never presented as a real payoff or a real appraisal. In
production these inputs would be fed from the finance ledger's real remaining
balance and a real valuation-vendor pull; here they are honest desk-entered
estimates.

RECORDING an upgrade offer (create_upgrade_offer) is 100% real -- a genuine,
timestamped, persisted employee action, the same class of real action
core/customer_journey.py's set_journey_stage() already is.

The AI upgrade-offer copy (generate_upgrade_offer) is a real, isolated,
kill-switched OpenAI call following core/customer_journey.py's
generate_journey_recommendation() pattern exactly (a dedicated no-tool-calling
client, an is_feature_enabled()/record_call_attempt() gate on feature key
'equity_upgrade_offer', a try/except around the real API call, and an honest,
non-AI fallback_upgrade_offer() grounded strictly in the customer's real
estimated equity position -- this sandbox has consistently shown no outbound
OpenAI network access, so the fallback path is what actually fires here today).

Per-mutation save_graph() convention (core/customer_journey.py /
core/communications_hub.py): recording an offer is one human action, not a bulk
job, so a direct save on every mutating call is the right, safe choice.
"""

from datetime import date, datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

id_generator = IDGenerator()
# Register this module's own id prefix on its own IDGenerator instance without
# touching the shared core/id_generator.py file (parent wires the permanent
# "EQOF": 0 counter). setdefault keeps generate("EQOF") from a KeyError.
id_generator.counters.setdefault("EQOF", 0)

# Equity status buckets.
POSITIVE = "positive"
NEGATIVE = "negative"
NEAR_EVEN = "near_even"
UNKNOWN = "unknown"

# |equity| at or under this dollar band reads as near_even rather than a real
# positive/negative call -- an estimate this close to zero can't honestly be
# called either way.
NEAR_EVEN_THRESHOLD = 500.0

# A loan/lease maturing within this many days is an active upgrade window.
LEASE_MATURITY_HORIZON_DAYS = 90

# Customer attribute keys this module reads/writes (all graph-native).
ESTIMATED_PAYOFF_KEY = "estimated_payoff"
ESTIMATED_VALUE_KEY = "estimated_value"
LEASE_MATURITY_KEY = "lease_maturity_date"
OFFERS_KEY = "equity_upgrade_offers"

ESTIMATE_BASIS = "desk_entered_estimate"
ESTIMATE_DISCLAIMER = (
    "ESTIMATED -- equity is derived from a desk-entered estimated payoff and "
    "estimated vehicle value. No real lender payoff quote and no third-party "
    "valuation vendor (e.g. KBB, Black Book, MMR) is connected in this "
    "environment; these figures are estimates for opportunity-spotting only, "
    "never a real payoff or a binding appraisal."
)


def _now():

    return datetime.now(timezone.utc).isoformat()


def _today():

    return datetime.now(timezone.utc).date()


def _get_customer_or_raise(customer_id):

    entity = ledger.get_entity(customer_id)

    if not entity or entity.entity_type != CUSTOMER:
        raise ValueError(f"No customer found with id {customer_id}.")

    return entity


def _customer_name(customer):

    attrs = customer.attributes

    name = attrs.get("Name")
    if name:
        return name

    first = attrs.get("FirstName") or ""
    last = attrs.get("LastName") or ""
    full = f"{first} {last}".strip()

    return full or None


def _to_float(value):

    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):

    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _equity_status(equity_amount):

    if equity_amount is None:
        return UNKNOWN
    if abs(equity_amount) <= NEAR_EVEN_THRESHOLD:
        return NEAR_EVEN
    if equity_amount > 0:
        return POSITIVE
    return NEGATIVE


def _position_for(customer):
    """Builds the estimated equity position dict for one already-loaded Customer
    entity. Every dollar figure is an estimate -- see ESTIMATE_DISCLAIMER."""

    attrs = customer.attributes

    payoff = _to_float(attrs.get(ESTIMATED_PAYOFF_KEY))
    value = _to_float(attrs.get(ESTIMATED_VALUE_KEY))

    if payoff is None or value is None:
        equity_amount = None
    else:
        equity_amount = round(value - payoff, 2)

    status = _equity_status(equity_amount)

    maturity = _parse_date(attrs.get(LEASE_MATURITY_KEY))
    if maturity is not None:
        days_to_lease_maturity = (maturity - _today()).days
    else:
        days_to_lease_maturity = None

    lease_maturing_soon = (
        days_to_lease_maturity is not None
        and 0 <= days_to_lease_maturity <= LEASE_MATURITY_HORIZON_DAYS
    )

    return {
        "customer_id": customer.id,
        "name": _customer_name(customer),
        "estimated_payoff": payoff,
        "estimated_value": value,
        "equity_amount": equity_amount,
        "status": status,
        "lease_maturity_date": attrs.get(LEASE_MATURITY_KEY),
        "days_to_lease_maturity": days_to_lease_maturity,
        "lease_maturing_soon": lease_maturing_soon,
        "has_estimate_inputs": payoff is not None and value is not None,
        "is_estimated": True,
        "basis": ESTIMATE_BASIS,
        "disclaimer": ESTIMATE_DISCLAIMER,
        "near_even_threshold": NEAR_EVEN_THRESHOLD,
        "lease_maturity_horizon_days": LEASE_MATURITY_HORIZON_DAYS,
    }


def get_equity_position(customer_id):
    """The estimated equity position for one customer -- estimated_payoff vs
    estimated_value giving equity_amount and a status in {positive, negative,
    near_even, unknown}. Every figure is an ESTIMATE (is_estimated=True, with a
    real basis/disclaimer). Raises ValueError on an unknown / non-customer id.

    A customer with no desk-entered estimated_payoff or estimated_value has
    equity_amount=None and status 'unknown' -- nothing is fabricated to fill
    the gap."""

    customer = _get_customer_or_raise(customer_id)

    return _position_for(customer)


def _opportunity_reason(position):

    reasons = []

    if position["status"] == POSITIVE:
        reasons.append(
            f"Positive estimated equity of ${position['equity_amount']:,.0f}"
        )

    if position["lease_maturing_soon"]:
        reasons.append(
            f"Loan/lease matures in {position['days_to_lease_maturity']} day(s)"
        )

    return "; ".join(reasons)


def list_equity_opportunities(horizon_days=LEASE_MATURITY_HORIZON_DAYS):
    """Every customer who is a real upgrade candidate: positive estimated equity
    AND/OR a loan/lease maturing within `horizon_days`. Each result carries a
    plain reason string, an `upgrade_ready` flag (True only when BOTH signals
    fire -- the strongest trade-up prospect), and the same estimate disclosure
    every position carries. Sorted strongest-first (upgrade_ready, then largest
    estimated equity)."""

    results = []

    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue

        position = _position_for(entity)

        positive_equity = position["status"] == POSITIVE
        # Honor a caller-supplied horizon that differs from the module default.
        days_out = position["days_to_lease_maturity"]
        lease_soon = days_out is not None and 0 <= days_out <= horizon_days
        position["lease_maturing_soon"] = lease_soon

        if not (positive_equity or lease_soon):
            continue

        upgrade_ready = positive_equity and lease_soon

        results.append({
            "customer_id": position["customer_id"],
            "name": position["name"],
            "status": position["status"],
            "equity_amount": position["equity_amount"],
            "lease_maturity_date": position["lease_maturity_date"],
            "days_to_lease_maturity": days_out,
            "lease_maturing_soon": lease_soon,
            "upgrade_ready": upgrade_ready,
            "reason": _opportunity_reason(position),
            "is_estimated": True,
            "basis": ESTIMATE_BASIS,
            "disclaimer": ESTIMATE_DISCLAIMER,
        })

    results.sort(
        key=lambda r: (
            r["upgrade_ready"],
            r["equity_amount"] if r["equity_amount"] is not None else float("-inf"),
        ),
        reverse=True,
    )

    return results


def create_upgrade_offer(customer_id, note=""):
    """Records a real, timestamped upgrade offer on the customer's own record
    (appended to the graph-native `equity_upgrade_offers` list) and persists it.
    Snapshots the customer's estimated equity position at offer time so the
    offer stays meaningful even if the estimate is later revised. Returns the
    created offer dict. Raises ValueError on an unknown / non-customer id."""

    customer = _get_customer_or_raise(customer_id)

    position = _position_for(customer)

    offer_id = id_generator.generate("EQOF")

    offer = {
        "id": offer_id,
        "customer_id": customer.id,
        "name": position["name"],
        "created_at": _now(),
        "note": note or "",
        "equity_amount": position["equity_amount"],
        "status": position["status"],
        "estimated_payoff": position["estimated_payoff"],
        "estimated_value": position["estimated_value"],
        "lease_maturity_date": position["lease_maturity_date"],
        "is_estimated": True,
        "basis": ESTIMATE_BASIS,
        "disclaimer": ESTIMATE_DISCLAIMER,
    }

    offers = customer.attributes.get(OFFERS_KEY) or []
    offers.append(offer)
    customer.attributes[OFFERS_KEY] = offers

    save_graph(GRAPH_PATH)

    return offer


def get_equity_overview():
    """Real, live-computed counts across every customer: how many carry positive
    estimated equity, how many have a loan/lease maturing soon, how many are
    fully upgrade-ready (both), and the total estimated dollar opportunity (the
    sum of every positive estimated equity_amount). Every dollar figure is an
    ESTIMATE -- see ESTIMATE_DISCLAIMER."""

    positive_equity = 0
    negative_equity = 0
    near_even = 0
    lease_maturing_soon = 0
    upgrade_ready = 0
    customers_with_estimates = 0
    total_customers = 0
    total_estimated_opportunity = 0.0

    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue

        total_customers += 1
        position = _position_for(entity)

        if position["has_estimate_inputs"]:
            customers_with_estimates += 1

        is_positive = position["status"] == POSITIVE
        if is_positive:
            positive_equity += 1
            total_estimated_opportunity += position["equity_amount"]
        elif position["status"] == NEGATIVE:
            negative_equity += 1
        elif position["status"] == NEAR_EVEN:
            near_even += 1

        if position["lease_maturing_soon"]:
            lease_maturing_soon += 1

        if is_positive and position["lease_maturing_soon"]:
            upgrade_ready += 1

    return {
        "positive_equity": positive_equity,
        "negative_equity": negative_equity,
        "near_even": near_even,
        "lease_maturing_soon": lease_maturing_soon,
        "upgrade_ready": upgrade_ready,
        "customers_with_estimates": customers_with_estimates,
        "total_customers": total_customers,
        "total_estimated_opportunity": round(total_estimated_opportunity, 2),
        "lease_maturity_horizon_days": LEASE_MATURITY_HORIZON_DAYS,
        "is_estimated": True,
        "basis": ESTIMATE_BASIS,
        "disclaimer": ESTIMATE_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# AI Upgrade Offer -- isolated, kill-switched OpenAI call, core/customer_journey.py's
# generate_journey_recommendation() pattern exactly (dedicated no-tool-calling
# client, is_feature_enabled()/record_call_attempt() gate, try/except around the
# real call, honest non-AI fallback grounded strictly in the real estimated
# position -- this sandbox has no outbound OpenAI network path, so the fallback
# is what actually fires here today).
# ---------------------------------------------------------------------------

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

UPGRADE_OFFER_SYSTEM_PROMPT = (
    "You are an assistant drafting a short, friendly trade-up / upgrade offer "
    "message for one dealership customer, based ONLY on their estimated equity "
    "position (estimated vehicle value minus estimated payoff) and any "
    "approaching loan/lease maturity. Return ONLY a JSON object with exactly "
    "these keys: headline (a short subject-line-style hook), message (2-3 short "
    "sentences inviting them to explore an upgrade, never quoting the equity "
    "figure as a guaranteed or exact amount and never inventing a detail not "
    "given), and suggested_next_step (one short imperative phrase such as "
    "'Book an appraisal appointment'). Do not include any commentary outside "
    "the JSON object."
)


def _upgrade_offer_user_content(position):

    name = position.get("name") or "the customer"
    status = position.get("status") or UNKNOWN
    equity = position.get("equity_amount")
    days = position.get("days_to_lease_maturity")

    lines = [
        f"Customer: {name}",
        f"Estimated equity status: {status}",
    ]

    if equity is not None:
        lines.append(f"Estimated equity amount (value minus payoff): ${equity:,.0f}")
    else:
        lines.append("Estimated equity amount: not enough estimate inputs on file")

    if position.get("lease_maturing_soon") and days is not None:
        lines.append(f"Loan/lease matures in approximately {days} day(s)")

    lines.append(
        "Note: all figures are desk-entered ESTIMATES, not a real payoff quote "
        "or a binding appraisal."
    )

    return "\n".join(lines) + "\n"


def fallback_upgrade_offer(position):
    """Plain, non-AI placeholder upgrade offer -- used when the AI call is
    disabled or fails, same pattern as core/customer_journey.py's
    fallback_journey_recommendation(). Grounded strictly in the real estimated
    position, never inventing a detail or quoting the estimate as exact."""

    status = position.get("status")
    name = position.get("name") or "there"

    if status == POSITIVE:
        headline = "You may have upgrade options"
        message = (
            f"Hi {name}, based on an estimated look at your current vehicle, you "
            "may be in a strong position to consider an upgrade. Estimates only "
            "-- let's confirm the real numbers together."
        )
    elif position.get("lease_maturing_soon"):
        headline = "Your loan/lease is maturing soon"
        message = (
            f"Hi {name}, your current loan/lease looks to be maturing soon. It's "
            "a great time to explore your next vehicle before it does. Estimated "
            "timing only -- let's confirm the details."
        )
    else:
        headline = "Let's review your options"
        message = (
            f"Hi {name}, we'd be happy to review your current vehicle and walk "
            "through any upgrade options with you. All figures would be confirmed "
            "together first."
        )

    return {
        "headline": headline,
        "message": message,
        "suggested_next_step": "Book an appraisal appointment to confirm real numbers",
    }


def generate_upgrade_offer(customer_id):
    """Real, isolated OpenAI call drafting an upgrade-offer message for one
    customer, grounded strictly in their estimated equity position. Returns a
    structured dict (headline / message / suggested_next_step, plus an
    ai_generated flag). On success the draft is stored back onto the customer's
    own `equity_ai_upgrade_offer` attribute and persisted; on disabled/failure
    it returns an honest fallback (never stored, since it's not a real AI
    result). Raises ValueError on an unknown / non-customer id.

    AI Management: checks the real 'equity_upgrade_offer' kill switch
    (core/ai_management.py, equity_upgrade_offer_enabled flag) before
    attempting -- mirrors core/customer_journey.py's
    generate_journey_recommendation()."""

    customer = _get_customer_or_raise(customer_id)
    position = _position_for(customer)

    if not is_feature_enabled("equity_upgrade_offer"):
        record_call_attempt("equity_upgrade_offer", "blocked")
        fallback = fallback_upgrade_offer(position)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": UPGRADE_OFFER_SYSTEM_PROMPT},
                {"role": "user", "content": _upgrade_offer_user_content(position)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("equity_upgrade_offer", "succeeded")
        raw = json.loads(response.choices[0].message.content)

        offer = {
            "headline": str(raw.get("headline") or ""),
            "message": str(raw.get("message") or ""),
            "suggested_next_step": str(raw.get("suggested_next_step") or ""),
            "ai_generated": True,
        }

        entity = ledger.get_entity(customer_id)
        entity.attributes["equity_ai_upgrade_offer"] = offer
        save_graph(GRAPH_PATH)

        return offer

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("equity_upgrade_offer", "fell_back", detail=str(exc))
        fallback = fallback_upgrade_offer(position)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback
