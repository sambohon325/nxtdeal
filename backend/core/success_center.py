"""Success Center -- NXTDeal-INTERNAL client-success / account-management
platform (2026-07-23). NOT a dealership department: this is the platform the
NXTDeal client-success team itself runs to manage the portfolio of DEALER
accounts that use NXTDeal. Its job is the account-manager's own workflow --
Quarterly Business Reviews (QBRs), success objectives, active initiatives, and
open recommendations -- one record set per dealer account.

WHY A NEW DEALER ENTITY (not an existing tenant/account type): NXTDeal is
deliberately SINGLE-TENANT -- "one NXTDeal instance per dealer" (see the
NXTDeal Hub / Multi-Tenant Architecture section of CLAUDE.md, and
core/entity_types.py's SYSTEM_CONFIG/SSO_CONFIG notes, both of which point out
that multi-dealer is "the Hub's job, not this instance's"). A full grep of
core/entity_types.py confirms NO dealer/tenant/account entity type exists in
this graph: NetworkPeerSnapshot is only a clearly-labelled SIMULATED blind
peer-KPI record, not a real dealer-account object. So this module models each
managed dealer account as its OWN first-class graph entity (entity_type
"SuccessDealer", id prefix "SDLR") -- the same "if the entity doesn't exist
yet, create it as an ordinary entity in the same ledger" rule every other
module in this codebase follows.

GRAPH-NATIVE, no separate store: each QBR / objective / initiative /
recommendation is its own ordinary graph Entity (entity_type SuccessQBR /
SuccessObjective / SuccessInitiative / SuccessRecommendation) linked back to
its dealer account via a plain `dealer_id` attribute, exactly the
linked-entity convention core/communications_hub.py's Communication (linked by
`linked_entity_id`) and core/lead_tasks.py's LeadTask already established --
not a foreign key, not a parallel JSON store. Each is its own entity rather
than an inline list on the dealer because each accumulates its own real
lifecycle over time (a recommendation is opened then resolved; an initiative
moves planned -> in_progress -> completed), the same "own lifecycle -> own
entity" reasoning OperationsTask/DamageReport/Payment/StrategicInitiative
already used elsewhere in this codebase. The dataclasses below (QBR /
Objective / Initiative / Recommendation) are the typed record schema; each is
persisted as an Entity's attributes via save_graph().

Follows the per-mutation save_graph() convention core/pipeline_state.py /
core/customer_journey.py / core/communications_hub.py already established for
low/moderate-frequency, human-driven mutations -- logging a QBR or resolving a
recommendation is a single human action, not a bulk job, so a direct save on
every mutating call is the right, safe choice.

The QBR Insights AI (generate_qbr_insights) is an isolated, kill-switched
OpenAI call following core/customer_journey.py's generate_journey_recommendation
pattern exactly (a dedicated no-tool-calling client, an is_feature_enabled()/
record_call_attempt() gate, a try/except around the real API call, and an
honest deterministic fallback_qbr_insights() for when the call can't be
reached -- this sandbox has consistently shown no outbound OpenAI network
access, so the fallback path is what actually fires here today).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Own IDGenerator instance, same convention as core/communications_hub.py. The
# Success Center's own id prefixes aren't in IDGenerator's canonical counter
# dict yet (that's a shared file the parent wires) -- self-register them here so
# this module is fully standalone-green today. Parent: add SDLR/SCQBR/SCOBJ/
# SCINI/SCREC to core/id_generator.py's counters for canonical consistency.
id_generator = IDGenerator()
for _prefix in ("SDLR", "SCQBR", "SCOBJ", "SCINI", "SCREC"):
    id_generator.counters.setdefault(_prefix, 0)

# Local entity-type strings (see module docstring for why these aren't in
# core/entity_types.py -- parent may add them there for canonical consistency,
# but the strings are what's load-bearing and this module owns them).
DEALER = "SuccessDealer"
QBR = "SuccessQBR"
OBJECTIVE = "SuccessObjective"
INITIATIVE = "SuccessInitiative"
RECOMMENDATION = "SuccessRecommendation"

PRIORITIES = ["high", "medium", "low"]
INITIATIVE_STATUSES = ["planned", "in_progress", "completed", "on_hold"]

REC_OPEN = "open"
REC_RESOLVED = "resolved"


def _now():

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Typed record schema (persisted as Entity attributes via save_graph()).
# ---------------------------------------------------------------------------

@dataclass
class QBRRecord:
    id: str
    dealer_id: str
    period: str
    notes: str = ""
    created_at: str = ""


@dataclass
class ObjectiveRecord:
    id: str
    dealer_id: str
    title: str
    target: str = ""
    created_at: str = ""


@dataclass
class InitiativeRecord:
    id: str
    dealer_id: str
    title: str
    status: str = "planned"
    created_at: str = ""


@dataclass
class RecommendationRecord:
    id: str
    dealer_id: str
    text: str
    priority: str = "medium"
    status: str = REC_OPEN
    created_at: str = ""
    resolved_at: str = None
    resolved_by: str = None


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------

def _get_dealer_or_raise(dealer_id):

    entity = ledger.get_entity(dealer_id)

    if not entity or entity.entity_type != DEALER:
        raise ValueError(f"No dealer account found with id {dealer_id}.")

    return entity


def _records_for(dealer_id, entity_type):

    results = []
    for entity in ledger.get_all().values():
        if entity.entity_type != entity_type:
            continue
        if entity.attributes.get("dealer_id") != dealer_id:
            continue
        results.append(entity)

    results.sort(key=lambda e: e.attributes.get("created_at") or "")
    return results


def _brief(entity):

    return {"id": entity.id, **entity.attributes}


def _dealer_brief(dealer):

    attrs = dealer.attributes
    return {
        "dealer_id": dealer.id,
        "name": attrs.get("name"),
        "notes": attrs.get("notes", ""),
        "created_at": attrs.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Dealer accounts.
# ---------------------------------------------------------------------------

def create_dealer(name, notes=""):
    """Creates a new managed dealer account (a SuccessDealer entity). Returns the
    dealer brief. Raises ValueError on an empty name."""

    if not name or not str(name).strip():
        raise ValueError("A dealer account must have a non-empty name.")

    dealer_id = id_generator.generate("SDLR")

    dealer = Entity(
        id=dealer_id,
        entity_type=DEALER,
        attributes={
            "name": name,
            "notes": notes or "",
            "created_at": _now(),
        },
    )
    ledger.add_entity(dealer)
    save_graph(GRAPH_PATH)

    return _dealer_brief(dealer)


def list_dealers():
    """Every managed dealer account as a brief, most-recently-created first."""

    dealers = [e for e in ledger.get_all().values() if e.entity_type == DEALER]
    dealers.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [_dealer_brief(d) for d in dealers]


# ---------------------------------------------------------------------------
# QBRs / Objectives / Initiatives / Recommendations.
# ---------------------------------------------------------------------------

def create_qbr(dealer_id, period, notes=""):
    """Logs a Quarterly Business Review record for one dealer account. Raises
    ValueError on an unknown dealer or an empty period."""

    _get_dealer_or_raise(dealer_id)

    if not period or not str(period).strip():
        raise ValueError("A QBR must have a non-empty period (e.g. 'Q3 2026').")

    record = QBRRecord(
        id=id_generator.generate("SCQBR"),
        dealer_id=dealer_id,
        period=period,
        notes=notes or "",
        created_at=_now(),
    )

    entity = Entity(id=record.id, entity_type=QBR, attributes={
        "dealer_id": record.dealer_id,
        "period": record.period,
        "notes": record.notes,
        "created_at": record.created_at,
    })
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _brief(entity)


def add_objective(dealer_id, title, target=""):
    """Adds a success objective for one dealer account. Raises ValueError on an
    unknown dealer or an empty title."""

    _get_dealer_or_raise(dealer_id)

    if not title or not str(title).strip():
        raise ValueError("An objective must have a non-empty title.")

    record = ObjectiveRecord(
        id=id_generator.generate("SCOBJ"),
        dealer_id=dealer_id,
        title=title,
        target=target or "",
        created_at=_now(),
    )

    entity = Entity(id=record.id, entity_type=OBJECTIVE, attributes={
        "dealer_id": record.dealer_id,
        "title": record.title,
        "target": record.target,
        "created_at": record.created_at,
    })
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _brief(entity)


def add_initiative(dealer_id, title, status="planned"):
    """Adds an active initiative for one dealer account. Raises ValueError on an
    unknown dealer, an empty title, or an invalid status."""

    _get_dealer_or_raise(dealer_id)

    if not title or not str(title).strip():
        raise ValueError("An initiative must have a non-empty title.")

    if status not in INITIATIVE_STATUSES:
        raise ValueError(
            f"Invalid initiative status '{status}'. Must be one of: "
            + ", ".join(INITIATIVE_STATUSES)
            + "."
        )

    record = InitiativeRecord(
        id=id_generator.generate("SCINI"),
        dealer_id=dealer_id,
        title=title,
        status=status,
        created_at=_now(),
    )

    entity = Entity(id=record.id, entity_type=INITIATIVE, attributes={
        "dealer_id": record.dealer_id,
        "title": record.title,
        "status": record.status,
        "created_at": record.created_at,
    })
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _brief(entity)


def add_recommendation(dealer_id, text, priority="medium"):
    """Adds an open recommendation for one dealer account. Raises ValueError on
    an unknown dealer, empty text, or an invalid priority."""

    _get_dealer_or_raise(dealer_id)

    if not text or not str(text).strip():
        raise ValueError("A recommendation must have non-empty text.")

    if priority not in PRIORITIES:
        raise ValueError(
            f"Invalid priority '{priority}'. Must be one of: "
            + ", ".join(PRIORITIES)
            + "."
        )

    record = RecommendationRecord(
        id=id_generator.generate("SCREC"),
        dealer_id=dealer_id,
        text=text,
        priority=priority,
        status=REC_OPEN,
        created_at=_now(),
        resolved_at=None,
        resolved_by=None,
    )

    entity = Entity(id=record.id, entity_type=RECOMMENDATION, attributes={
        "dealer_id": record.dealer_id,
        "text": record.text,
        "priority": record.priority,
        "status": record.status,
        "created_at": record.created_at,
        "resolved_at": record.resolved_at,
        "resolved_by": record.resolved_by,
    })
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _brief(entity)


def list_open_recommendations(dealer_id):
    """Every still-open recommendation for one dealer account, most-recent-first.
    Raises ValueError on an unknown dealer."""

    _get_dealer_or_raise(dealer_id)

    open_recs = [
        e for e in _records_for(dealer_id, RECOMMENDATION)
        if e.attributes.get("status") == REC_OPEN
    ]
    open_recs.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [_brief(e) for e in open_recs]


def resolve_recommendation(dealer_id, rec_id, resolved_by=None):
    """Marks one recommendation resolved. Raises ValueError on an unknown dealer,
    an unknown recommendation, a recommendation that belongs to a different
    dealer, or one that's already resolved."""

    _get_dealer_or_raise(dealer_id)

    entity = ledger.get_entity(rec_id)
    if (
        not entity
        or entity.entity_type != RECOMMENDATION
        or entity.attributes.get("dealer_id") != dealer_id
    ):
        raise ValueError(
            f"No recommendation found with id {rec_id} for dealer {dealer_id}."
        )

    if entity.attributes.get("status") == REC_RESOLVED:
        raise ValueError(f"Recommendation {rec_id} is already resolved.")

    entity.attributes["status"] = REC_RESOLVED
    entity.attributes["resolved_at"] = _now()
    entity.attributes["resolved_by"] = resolved_by

    save_graph(GRAPH_PATH)

    return _brief(entity)


def get_success_overview(dealer_id):
    """The real, live-computed account-health overview for one dealer: open
    recommendations counted by priority (seeded to 0 for every priority even
    when empty, same convention core/communications_hub.py's by_channel already
    established), the objective list, initiatives counted by status, and the
    latest/upcoming QBR. Raises ValueError on an unknown dealer.

    NXTDeal-INTERNAL account-management view -- see this module's own docstring
    for why this is a Success-team screen over a portfolio of dealer accounts,
    not a dealership department dashboard.

    latest_qbr is the most-recently-logged QBR (max created_at). upcoming_qbr is
    honestly None here: QBR records are logged as reviews are held, and this
    module deliberately doesn't fabricate a future-scheduled QBR with a date it
    was never given -- same honest not-yet convention the rest of this codebase
    follows, rather than inventing one. The full qbr history is returned so a
    caller can derive its own scheduling view."""

    dealer = _get_dealer_or_raise(dealer_id)

    # Open recommendations by priority.
    open_by_priority = {p: 0 for p in PRIORITIES}
    open_total = 0
    for e in _records_for(dealer_id, RECOMMENDATION):
        if e.attributes.get("status") != REC_OPEN:
            continue
        priority = e.attributes.get("priority")
        if priority in open_by_priority:
            open_by_priority[priority] += 1
        open_total += 1

    # Objectives.
    objectives = [_brief(e) for e in _records_for(dealer_id, OBJECTIVE)]

    # Initiatives by status.
    initiatives = _records_for(dealer_id, INITIATIVE)
    initiatives_by_status = {s: 0 for s in INITIATIVE_STATUSES}
    for e in initiatives:
        status = e.attributes.get("status")
        if status in initiatives_by_status:
            initiatives_by_status[status] += 1

    # QBRs -- chronological; latest = most recent by created_at.
    qbrs = _records_for(dealer_id, QBR)
    latest_qbr = _brief(qbrs[-1]) if qbrs else None

    return {
        "dealer_id": dealer.id,
        "name": dealer.attributes.get("name"),
        "open_recommendations_by_priority": open_by_priority,
        "open_recommendations_total": open_total,
        "objectives": objectives,
        "objectives_count": len(objectives),
        "initiatives_by_status": initiatives_by_status,
        "initiatives_count": len(initiatives),
        "latest_qbr": latest_qbr,
        "upcoming_qbr": None,
        "qbr_count": len(qbrs),
    }


# ---------------------------------------------------------------------------
# QBR Insights AI -- isolated, kill-switched OpenAI call, core/customer_journey.py's
# generate_journey_recommendation() pattern exactly (a dedicated no-tool-calling
# client, an is_feature_enabled()/record_call_attempt() gate, a try/except around
# the real API call, and an honest, non-AI fallback_qbr_insights() for when the
# call can't be reached -- this sandbox has consistently shown no outbound OpenAI
# network access, so the fallback path is what actually fires here today).
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

# Feature key (core/ai_management.py AI_FEATURE_CATALOG) / flag (core/system_config.py
# FEATURE_FLAGS) this AI feature's kill switch is backed by -- parent wires both.
QBR_INSIGHTS_FEATURE_KEY = "success_qbr_insights"

QBR_INSIGHTS_SYSTEM_PROMPT = (
    "You are a NXTDeal client-success account manager's assistant preparing "
    "talking points for a Quarterly Business Review (QBR) with a dealership "
    "that uses the NXTDeal platform. Given the dealer's current success "
    "objectives, active initiatives, and open recommendations, return ONLY a "
    "JSON object with exactly these keys: summary (2-3 short sentences, a plain "
    "factual recap of the account's current success posture, never inventing a "
    "detail not present in the given data), talking_points (a JSON array of up "
    "to 5 short strings, each a single concrete discussion point grounded "
    "strictly in the given objectives/initiatives/recommendations), and "
    "suggested_focus (one short sentence naming the single most important area "
    "to focus the QBR on, or an empty string if none stands out). Do not "
    "include any commentary outside the JSON object."
)


def _insights_user_content(dealer_brief, objectives, initiatives, open_recs):

    lines = [
        f"Dealer account: {dealer_brief.get('name') or dealer_brief.get('dealer_id')}",
        "",
        "Success objectives:",
    ]
    if objectives:
        for o in objectives:
            target = o.get("target")
            line = f"- {o.get('title')}"
            if target:
                line += f" (target: {target})"
            lines.append(line)
    else:
        lines.append("- none recorded yet")

    lines.append("")
    lines.append("Active initiatives:")
    if initiatives:
        for i in initiatives:
            lines.append(f"- {i.get('title')} [{i.get('status')}]")
    else:
        lines.append("- none recorded yet")

    lines.append("")
    lines.append("Open recommendations:")
    if open_recs:
        for r in open_recs:
            lines.append(f"- ({r.get('priority')}) {r.get('text')}")
    else:
        lines.append("- none open")

    return "\n".join(lines) + "\n"


def fallback_qbr_insights(dealer_brief, objectives, initiatives, open_recs):
    """Plain, non-AI deterministic QBR talking points -- used when the AI call is
    disabled or fails, same pattern as core/customer_journey.py's
    fallback_journey_recommendation(). Grounded strictly in the real
    objectives/initiatives/open-recs, never inventing a detail."""

    talking_points = []

    if objectives:
        talking_points.append(
            f"Review progress on {len(objectives)} success "
            f"objective{'s' if len(objectives) != 1 else ''}."
        )
    if initiatives:
        in_progress = sum(1 for i in initiatives if i.get("status") == "in_progress")
        talking_points.append(
            f"Check status on {len(initiatives)} active "
            f"initiative{'s' if len(initiatives) != 1 else ''} "
            f"({in_progress} in progress)."
        )
    if open_recs:
        high = sum(1 for r in open_recs if r.get("priority") == "high")
        talking_points.append(
            f"Address {len(open_recs)} open "
            f"recommendation{'s' if len(open_recs) != 1 else ''} "
            f"({high} high priority)."
        )
    if not talking_points:
        talking_points.append(
            "No objectives, initiatives, or open recommendations recorded yet -- "
            "use this QBR to establish them."
        )

    name = dealer_brief.get("name") or "this dealer account"
    suggested_focus = ""
    if open_recs:
        high_recs = [r for r in open_recs if r.get("priority") == "high"]
        if high_recs:
            suggested_focus = f"Resolving high-priority recommendations for {name}."

    return {
        "summary": (
            f"QBR prep for {name}: {len(objectives)} objective(s), "
            f"{len(initiatives)} active initiative(s), and "
            f"{len(open_recs)} open recommendation(s)."
        ),
        "talking_points": talking_points,
        "suggested_focus": suggested_focus,
    }


def generate_qbr_insights(dealer_id):
    """Real, isolated OpenAI call summarizing one dealer account's objectives,
    initiatives, and open recommendations into QBR talking points. Returns a
    structured dict (summary / talking_points / suggested_focus, plus an
    ai_generated flag). On success the insights are stored back onto the dealer
    account's own qbr_insights attribute and persisted; on disabled/failure it
    returns an honest fallback (never stored, since it's not a real AI result)
    so the caller always has something usable.

    Raises ValueError on an unknown dealer, exactly like the non-AI functions.

    AI Management: checks the real 'success_qbr_insights' kill switch
    (core/ai_management.py) before attempting -- mirrors core/customer_journey.py's
    generate_journey_recommendation()."""

    dealer = _get_dealer_or_raise(dealer_id)
    dealer_brief = _dealer_brief(dealer)
    objectives = [_brief(e) for e in _records_for(dealer_id, OBJECTIVE)]
    initiatives = [_brief(e) for e in _records_for(dealer_id, INITIATIVE)]
    open_recs = list_open_recommendations(dealer_id)

    if not is_feature_enabled(QBR_INSIGHTS_FEATURE_KEY):
        record_call_attempt(QBR_INSIGHTS_FEATURE_KEY, "blocked")
        fallback = fallback_qbr_insights(dealer_brief, objectives, initiatives, open_recs)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": QBR_INSIGHTS_SYSTEM_PROMPT},
                {"role": "user", "content": _insights_user_content(
                    dealer_brief, objectives, initiatives, open_recs
                )},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt(QBR_INSIGHTS_FEATURE_KEY, "succeeded")
        raw = json.loads(response.choices[0].message.content)

        # Parse STRICTLY from the model's JSON -- never invent a field it didn't
        # return (an absent key falls back to an empty value, not a guess).
        points = raw.get("talking_points")
        if not isinstance(points, list):
            points = []

        insights = {
            "summary": str(raw.get("summary") or ""),
            "talking_points": [str(p) for p in points],
            "suggested_focus": str(raw.get("suggested_focus") or ""),
            "ai_generated": True,
        }

        entity = ledger.get_entity(dealer_id)
        entity.attributes["qbr_insights"] = insights
        save_graph(GRAPH_PATH)

        return insights

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt(QBR_INSIGHTS_FEATURE_KEY, "fell_back", detail=str(exc))
        fallback = fallback_qbr_insights(dealer_brief, objectives, initiatives, open_recs)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback
