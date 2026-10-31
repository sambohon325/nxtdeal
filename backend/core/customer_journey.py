"""Customer Journey Engine -- slice 1 (2026-07-22): the graph-native stage-
tracking backbone. Tracks each real Customer through the dealership lifecycle
(Awareness -> Lead -> Appointment -> Sale -> Service -> Loyalty -> Repeat).

GRAPH-NATIVE, single source of truth: journey state is stored DIRECTLY as
attributes on the existing Customer entity, exactly the way
core/pipeline_state.py stores pipeline state on a Lead -- NOT a separate
JSON store, not a new entity type. Two attributes are written:

    journey_stage    - the customer's current lifecycle stage (one of STAGES)
    journey_history  - an ordered list of {stage, timestamp, note} entries,
                       one appended on every stage change (initial set,
                       explicit set, or advance)

This mirrors core/pipeline_state.py's "attributes on the entity itself, saved
by the same core/storage.py save_graph() that already persists everything
else" convention -- but unlike pipeline_state (which deliberately keeps only
current state and leans on the audit log for history), a customer's journey
history is small, bounded, and directly useful to read back per customer, so
it's kept inline on the entity as journey_history rather than reconstructed
from an external log.

Follows the per-mutation save_graph() convention core/pipeline_state.py/
core/communications_hub.py already established for low/moderate-frequency,
human-driven mutations -- a single stage change is one human action, not a
bulk job, so a direct save on every mutating call is the right, safe choice.

Slice 1 is deliberately backend-only and AI-free (no OpenAI call, no
frontend) -- later slices add journey intelligence/automation on top of this
same real, persisted backbone.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Ordered lifecycle stages -- the sequence a customer moves through. Order is
# load-bearing: advance_journey() steps to the next stage in this exact list,
# and FORWARD_TRANSITIONS below is derived from it.
AWARENESS = "AWARENESS"
LEAD = "LEAD"
APPOINTMENT = "APPOINTMENT"
SALE = "SALE"
SERVICE = "SERVICE"
LOYALTY = "LOYALTY"
REPEAT = "REPEAT"

STAGES = [
    AWARENESS,
    LEAD,
    APPOINTMENT,
    SALE,
    SERVICE,
    LOYALTY,
    REPEAT,
]

# Allowed forward transitions -- each stage maps to the single next stage it
# advances into, or None for the terminal stage. Derived from STAGES' order so
# the two can never drift apart. advance_journey() consults this; the explicit
# set_journey_stage() is a deliberate override path that may set any valid
# stage (a correction, or a jump), not just the next one.
FORWARD_TRANSITIONS = {
    stage: (STAGES[index + 1] if index + 1 < len(STAGES) else None)
    for index, stage in enumerate(STAGES)
}


def _now():

    return datetime.now(timezone.utc).isoformat()


def _get_customer_or_raise(customer_id):

    entity = ledger.get_entity(customer_id)

    if not entity or entity.entity_type != CUSTOMER:
        raise ValueError(f"No customer found with id {customer_id}.")

    return entity


def _validate_stage(stage):

    if stage not in STAGES:
        raise ValueError(
            f"Invalid journey stage '{stage}'. Must be one of: "
            + ", ".join(STAGES)
            + "."
        )


def _customer_name(customer):

    attrs = customer.attributes

    name = attrs.get("Name")
    if name:
        return name

    first = attrs.get("FirstName") or ""
    last = attrs.get("LastName") or ""
    full = f"{first} {last}".strip()

    return full or None


def _journey_brief(customer):

    attrs = customer.attributes

    return {
        "customer_id": customer.id,
        "name": _customer_name(customer),
        "journey_stage": attrs.get("journey_stage"),
        "journey_history": list(attrs.get("journey_history") or []),
    }


def get_customer_journey(customer_id):
    """The real journey record for one customer -- current stage plus full
    stage history. Raises ValueError on an unknown customer / non-customer
    id."""

    customer = _get_customer_or_raise(customer_id)

    return _journey_brief(customer)


def set_journey_stage(customer_id, stage, note=""):
    """Sets a customer's current journey stage to any valid stage (an explicit
    override -- start, correction, or jump -- not restricted to the next stage
    like advance_journey). Appends a real {stage, timestamp, note} entry to the
    customer's journey_history and persists. Raises ValueError on an unknown
    customer or an invalid stage."""

    customer = _get_customer_or_raise(customer_id)
    _validate_stage(stage)

    history = customer.attributes.get("journey_history") or []
    history.append({
        "stage": stage,
        "timestamp": _now(),
        "note": note or "",
    })

    customer.attributes["journey_stage"] = stage
    customer.attributes["journey_history"] = history

    save_graph(GRAPH_PATH)

    return _journey_brief(customer)


def advance_journey(customer_id, note=""):
    """Moves a customer to the NEXT stage in STAGES order. A customer not yet
    in the journey (no journey_stage) starts at the first stage (AWARENESS).
    Raises ValueError on an unknown customer, or when the customer is already
    at the final stage (REPEAT) and there is nowhere further to advance."""

    customer = _get_customer_or_raise(customer_id)

    current = customer.attributes.get("journey_stage")

    if current is None:
        next_stage = STAGES[0]
    else:
        next_stage = FORWARD_TRANSITIONS.get(current)
        if next_stage is None:
            raise ValueError(
                f"Customer {customer_id} is already at the final journey "
                f"stage ('{current}') and cannot be advanced further."
            )

    return set_journey_stage(customer_id, next_stage, note=note)


def list_customers_in_stage(stage):
    """Every customer currently sitting in the given stage, as journey briefs.
    Raises ValueError on an invalid stage."""

    _validate_stage(stage)

    results = []
    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue
        if entity.attributes.get("journey_stage") == stage:
            results.append(_journey_brief(entity))

    return results


def get_journey_overview():
    """Real, live-computed counts -- one per stage (seeded to 0 for every real
    stage even when empty, same convention core/communications_hub.py's
    by_channel already established) plus the total number of customers
    currently tracked in the journey."""

    by_stage = {stage: 0 for stage in STAGES}
    total = 0

    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue

        stage = entity.attributes.get("journey_stage")
        if stage in by_stage:
            by_stage[stage] += 1
            total += 1

    return {
        "stages": list(STAGES),
        "counts_by_stage": by_stage,
        "total_customers_in_journey": total,
    }


# ---------------------------------------------------------------------------
# AI Journey Recommendation -- slice 2 (2026-07-22): an isolated, kill-switched
# OpenAI call recommending one customer's next best action, mirroring
# core/communications_hub.py's generate_ai_summary() pattern exactly (a
# dedicated no-tool-calling client, an is_feature_enabled()/record_call_attempt()
# gate, a try/except around the real API call, and an honest, non-AI
# fallback_journey_recommendation() for when the call can't be reached -- this
# sandbox has consistently shown no outbound OpenAI network access, so the
# fallback path is what actually fires here today).
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

RECOMMENDATION_SYSTEM_PROMPT = (
    "You are an assistant recommending the single next best marketing/sales "
    "action for one dealership customer, based ONLY on their current lifecycle "
    "journey stage and stage history. The ordered stages are Awareness -> Lead "
    "-> Appointment -> Sale -> Service -> Loyalty -> Repeat. Return ONLY a JSON "
    "object with exactly these keys: recommended_action (a short imperative "
    "phrase naming the single next best action), reason (1-2 sentences grounded "
    "strictly in the given stage/history, never inventing a fact not present), "
    "suggested_timing (a short phrase such as 'within 2 weeks'), and "
    "suggested_campaign (a short campaign name to enroll the customer in, or an "
    "empty string if none applies). Do not include any commentary outside the "
    "JSON object."
)

# Stage -> a plain, honest next best action, used by the non-AI fallback below.
_NEXT_BEST_ACTION = {
    AWARENESS: "Send an introductory offer and capture their contact details",
    LEAD: "Follow up to qualify the lead and book an appointment",
    APPOINTMENT: "Confirm the appointment and prepare a tailored vehicle shortlist",
    SALE: "Complete delivery and schedule their first service touchpoint",
    SERVICE: "Check in on the service experience and invite a review",
    LOYALTY: "Offer a loyalty perk and gauge repeat-purchase interest",
    REPEAT: "Nurture the relationship with referral and upgrade offers",
}


def _recommendation_user_content(brief):

    name = brief.get("name") or "the customer"
    stage = brief.get("journey_stage") or "no recorded stage yet"
    history = brief.get("journey_history") or []

    lines = [
        f"Customer: {name}",
        f"Current journey stage: {stage}",
        f"Ordered lifecycle stages: {', '.join(STAGES)}",
    ]

    if history:
        lines.append("Journey history (oldest first):")
        for entry in history:
            note = entry.get("note")
            line = f"- {entry.get('stage')} at {entry.get('timestamp')}"
            if note:
                line += f" ({note})"
            lines.append(line)
    else:
        lines.append("Journey history: none recorded yet.")

    return "\n".join(lines) + "\n"


def fallback_journey_recommendation(brief):
    """Plain, non-AI placeholder recommendation -- used when the AI call is
    disabled or fails, same pattern as core/communications_hub.py's
    fallback_summary(). Grounded in the customer's real current stage, never
    inventing a detail."""

    stage = brief.get("journey_stage")
    action = _NEXT_BEST_ACTION.get(
        stage, "Reach out to re-engage the customer and establish their current stage"
    )
    stage_label = stage or "no recorded stage"

    return {
        "recommended_action": action,
        "reason": (
            f"The customer is currently at the {stage_label} stage; this is the "
            "standard next best action for that stage."
        ),
        "suggested_timing": "within 2 weeks",
        "suggested_campaign": "",
    }


def generate_journey_recommendation(customer_id):
    """Real, isolated OpenAI call recommending one customer's next best action
    from their current journey stage + history. Returns a structured dict with
    keys recommended_action / reason / suggested_timing / suggested_campaign
    (plus an ai_generated flag). On success the recommendation is stored back
    onto the customer's own journey_recommendation attribute and persisted; on
    disabled/failure it returns an honest fallback (never stored, since it's not
    a real AI result) so the caller always has something usable.

    Raises ValueError on an unknown customer / non-customer id, exactly like the
    slice-1 journey functions.

    AI Management: checks the real 'customer_journey_recommendation' kill switch
    (core/ai_management.py, customer_journey_recommendation_enabled flag) before
    attempting -- mirrors core/communications_hub.py's generate_ai_summary()."""

    customer = _get_customer_or_raise(customer_id)
    brief = _journey_brief(customer)

    if not is_feature_enabled("customer_journey_recommendation"):
        record_call_attempt("customer_journey_recommendation", "blocked")
        fallback = fallback_journey_recommendation(brief)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": RECOMMENDATION_SYSTEM_PROMPT},
                {"role": "user", "content": _recommendation_user_content(brief)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("customer_journey_recommendation", "succeeded")
        raw = json.loads(response.choices[0].message.content)

        # Parse STRICTLY from the model's JSON -- never invent a field it didn't
        # return (an absent key falls back to an empty string, not a guess).
        recommendation = {
            "recommended_action": str(raw.get("recommended_action") or ""),
            "reason": str(raw.get("reason") or ""),
            "suggested_timing": str(raw.get("suggested_timing") or ""),
            "suggested_campaign": str(raw.get("suggested_campaign") or ""),
            "ai_generated": True,
        }

        entity = ledger.get_entity(customer_id)
        entity.attributes["journey_recommendation"] = recommendation
        save_graph(GRAPH_PATH)

        return recommendation

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("customer_journey_recommendation", "fell_back", detail=str(exc))
        fallback = fallback_journey_recommendation(brief)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback
