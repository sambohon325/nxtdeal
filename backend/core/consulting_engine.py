"""
core/consulting_engine.py -- the "AI Consulting Engine" (2026-07-23), the
strategic centerpiece of the NXTDeal deck (NXTDeal deck: "software + human
consultants" -> "software + an AI consulting organization"). Sam's vision: a
user asks a plain business question -- "Why are service sales down?", "Where
are we losing the most gross profit?" -- and gets back a structured CONSULTING
answer with four parts: Analysis, Root Cause, Opportunity, and a concrete
Action Plan. It LIVES INSIDE Network (this dealer's relationship to the whole
NXTDeal network), one step up from Network's own per-department AI Advisors:
where an Advisor answers one department's question, the Consulting Engine
composes a whole-store, cross-department strategic consultation.

This module INVENTS NO NEW METRICS. It is a pure COMPOSITION layer over the
real analysis NXTDeal already computes, exactly the same "compose already-real
modules, never recompute, never fabricate a number" discipline that
core/ai_business_analyst.py (Readiness' AI Business Analyst) and
core/network_advisors.py (Network's AI Advisors) both already established -- and
it reuses THOSE modules' own real fact-gatherers and sentence builders directly
rather than duplicating them:

  - Analysis  <- core/ai_business_analyst.py's whole-business gather_facts() +
    topic-matched fallback (or, for a department-scoped consultation,
    core/network_advisors.py's real per-department benchmark + gap facts).
  - Root Cause <- core/network_advisors.py's _sentences_root_causes (department)
    or core/ai_business_analyst.py's _sentences_risk / _sentences_recommendations
    (whole-store) -- the real, already-computed risk + gap root-cause material.
  - Opportunity <- core/network_opportunity_value.py's real dollar-denominated
    largest-opportunities + total-identified-opportunity math.
  - Action Plan <- core/readiness_recommendations.py's real, rule-triggered
    Executive Recommendations feed + (department-scoped) the real curated
    playbook library's currently-active plays.

AI path: gated on is_feature_enabled("ai_consulting_engine") +
record_call_attempt (core/ai_management.py, ai_consulting_engine_enabled flag),
same isolated-client / strict-JSON / never-invent-a-number pattern as
core/communications_hub.py's generate_ai_summary(). The model is given ONLY the
pre-composed real FACTS block and asked to phrase the four sections from it.

Deterministic fallback (feature disabled, OpenAI unreachable -- true for every
call in this sandbox -- or malformed model output): a real, grounded four-part
consultation built entirely from the composed sentence builders above, marked
ai_generated=False. Never a generic "AI unavailable" message.

Each consultation is logged graph-natively as a lightweight Consultation
entity (id prefix CONSULT) so get_consulting_overview() can show recent ones.
Logging is best-effort and never breaks a consultation.
"""

import json
import os

from datetime import datetime, timezone

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt
from core.dealeros import ledger
from core.entities import Entity
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core import ai_business_analyst as aba
from core import network_advisors as na
from core.network_advisors import ADVISOR_DEPARTMENTS
from core.readiness_recommendations import get_recommendations_overview
from core.network_opportunity_value import (
    get_largest_opportunities,
    get_total_identified_opportunity,
)

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

id_generator = IDGenerator()

# Consultation entity_type is a local literal (a free-form string on the
# generic Entity) rather than a new core/entity_types.py constant -- the record
# is a lightweight, best-effort audit breadcrumb for the overview, not a
# first-class domain entity with its own consumers.
CONSULTATION = "Consultation"

STARTER_QUESTIONS = [
    "Why are service sales down?",
    "Where are we losing the most gross profit?",
    "What should we do to improve our sales close rate?",
    "Why is inventory readiness declining?",
    "Where is our single biggest dollar opportunity across the store?",
]

SYSTEM_PROMPT = (
    "You are a senior automotive-retail management consultant advising a car "
    "dealership's leadership team. You will be given a block of REAL, already-"
    "computed facts about this dealership (labeled FACTS below) and a business "
    "question. Produce a structured consulting answer in four parts, using ONLY "
    "the facts provided -- you MUST NOT invent, estimate, or alter any number, "
    "percentage, count, or dollar figure that isn't already present in FACTS. If "
    "FACTS doesn't contain enough information for a section, say so plainly rather "
    "than guessing. Return ONLY a JSON object with exactly these keys: "
    "analysis (2-4 sentences stating what the data shows), "
    "root_cause (2-4 sentences on the most likely drivers, grounded in the facts), "
    "opportunity (2-4 sentences quantifying the upside, using only the dollar "
    "figures present in FACTS), "
    "action_plan (a JSON array of 3-6 short, concrete next-step strings), and "
    "confidence_note (one short sentence on how grounded/certain this answer is)."
)


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 -- a sub-module's own {"error": ...} dict is fine; a raw exception isn't
        return {}


# ---------------------------------------------------------------------------
# Real fact gathering -- pure composition of already-real modules.
# ---------------------------------------------------------------------------

def _gather(role, department):
    """Composes the real facts every consultation draws on. For a department-
    scoped consultation, uses core/network_advisors.py's per-department
    benchmark/gap/playbook facts; otherwise core/ai_business_analyst.py's
    whole-business health/risk/recommendations/forecasts facts. Both paths
    additionally pull the real readiness recommendation feed and the real
    dollar-denominated opportunity sizing -- every call guarded, every sub-
    module degrading to its own real {"error": ...} dict rather than raising."""

    facts = {"department": department}

    if department:
        facts["department_facts"] = _safe(na.gather_department_facts, department, role)
    else:
        facts["business_facts"] = _safe(aba.gather_facts, role)

    facts["recommendations"] = _safe(get_recommendations_overview, role)
    facts["opportunity"] = _safe(get_largest_opportunities, role, 5)
    facts["opportunity_totals"] = _safe(get_total_identified_opportunity, role)

    return facts


# ---------------------------------------------------------------------------
# The four consulting sections -- each composed from already-real sentence
# builders in ai_business_analyst / network_advisors / the opportunity-value
# and recommendation feeds. No new computation, no fabricated number.
# ---------------------------------------------------------------------------

def _section_analysis(question, facts):
    department = facts.get("department")
    if department:
        df = facts.get("department_facts") or {}
        sentences = na._sentences_benchmark(df) + na._sentences_gaps(df)
        return " ".join(sentences)

    bf = facts.get("business_facts") or {}
    # ai_business_analyst's own topic-matched fallback IS a real, grounded,
    # question-relevant analysis paragraph.
    return aba._format_fallback_answer(question, bf)


def _section_root_cause(facts):
    department = facts.get("department")
    if department:
        df = facts.get("department_facts") or {}
        return " ".join(na._sentences_root_causes(df))

    bf = facts.get("business_facts") or {}
    sentences = aba._sentences_risk(bf) + aba._sentences_recommendations(bf)
    return " ".join(sentences)


def _section_opportunity(facts):
    out = []

    opp = facts.get("opportunity") or {}
    largest = opp.get("largest_opportunities") or [] if isinstance(opp, dict) else []
    for g in largest[:3]:
        annualized = g.get("annualized_dollar_impact")
        if isinstance(annualized, (int, float)) and annualized:
            out.append(
                f"{g.get('department_title')} {g.get('label')}: an estimated "
                f"${annualized:,.0f}/yr opportunity (this store at {g.get('this_store')} "
                f"vs. peer average {g.get('peer_average')})."
            )

    totals = facts.get("opportunity_totals") or {}
    total_annual = totals.get("total_annualized_opportunity") if isinstance(totals, dict) else None
    if isinstance(total_annual, (int, float)) and total_annual:
        out.append(
            f"Total identified annualized opportunity across benchmarked departments "
            f"is approximately ${total_annual:,.0f} (SIMULATED peer basis)."
        )

    department = facts.get("department")
    if department:
        out.extend(na._sentences_gaps(facts.get("department_facts") or {}))

    if not out:
        out.append(
            "No dollar-denominated opportunity is currently identified from the "
            "available benchmark data."
        )

    return " ".join(out)


def _section_action_plan(facts):
    """A list of concrete steps -- the real Executive Recommendations feed
    (every rule triggered at high/critical severity) plus, for a department
    consultation, that department's real currently-active curated playbooks."""

    steps = []

    rec = facts.get("recommendations") or {}
    exec_recs = rec.get("executive_recommendations") or [] if isinstance(rec, dict) else []
    for item in exec_recs[:4]:
        recommendation = item.get("recommendation")
        if recommendation:
            title = item.get("title")
            steps.append(f"{title}: {recommendation}" if title else recommendation)

    department = facts.get("department")
    if department:
        df = facts.get("department_facts") or {}
        for pb in (df.get("playbooks") or []):
            if pb.get("is_currently_active"):
                steps.append(f'Run the "{pb["title"]}" playbook -- {pb["summary"]}')

    if not steps:
        steps.append(
            "No high- or critical-severity recommendations are currently triggered "
            "-- maintain current operations and re-run this consultation after the "
            "next data refresh."
        )

    return steps[:6]


def _sources(facts):
    department = facts.get("department")
    sources = []
    if department:
        sources.append(
            "network_advisors.gather_department_facts (peer benchmark, gap "
            "analysis, root causes, curated playbooks)"
        )
    else:
        sources.append(
            "ai_business_analyst.gather_facts (business health, enterprise risk "
            "center, recommendations, forecasts)"
        )
    sources.append("readiness_recommendations.get_recommendations_overview (Executive Recommendations)")
    sources.append(
        "network_opportunity_value.get_largest_opportunities / "
        "get_total_identified_opportunity (dollar-denominated opportunity)"
    )
    return sources


_CONFIDENCE_NOTE = (
    "Every figure in this consultation is composed directly from NXTDeal's own "
    "already-computed data -- no number is invented. Peer benchmarks and the "
    "dollar-opportunity sizing are on a SIMULATED peer basis (real once a second "
    "NXTDeal dealer connects); some operational metrics are heuristic/simulated "
    "as labeled by their source modules."
)


def build_facts_text(question, facts):
    """The FACTS block sent to OpenAI -- every section built from the exact
    same real sentence builders the fallback path uses, so the AI-phrased
    consultation and the deterministic fallback are always grounded in the
    identical real numbers."""

    return "\n\n".join([
        "[ANALYSIS]\n" + _section_analysis(question, facts),
        "[ROOT CAUSE]\n" + _section_root_cause(facts),
        "[OPPORTUNITY]\n" + _section_opportunity(facts),
        "[ACTION PLAN CANDIDATES]\n" + " ".join(_section_action_plan(facts)),
    ])


def _build_fallback(question, department, facts):
    return {
        "question": question,
        "department": department,
        "analysis": _section_analysis(question, facts),
        "root_cause": _section_root_cause(facts),
        "opportunity": _section_opportunity(facts),
        "action_plan": _section_action_plan(facts),
        "confidence_note": _CONFIDENCE_NOTE,
        "sources": _sources(facts),
        "ai_generated": False,
    }


# ---------------------------------------------------------------------------
# Best-effort graph-native logging of each consultation.
# ---------------------------------------------------------------------------

def _log_consultation(result, role):
    try:
        consult_id = id_generator.generate("CONSULT")
        entity = Entity(
            id=consult_id,
            entity_type=CONSULTATION,
            attributes={
                "question": result.get("question"),
                "department": result.get("department"),
                "ai_generated": result.get("ai_generated"),
                "requested_by_role": role,
                "created_at": _now(),
            },
        )
        ledger.add_entity(entity)
        save_graph(GRAPH_PATH)
    except Exception:  # noqa: BLE001 -- logging is a breadcrumb, never load-bearing
        pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_recent_consultations(limit=10):
    consultations = [
        e for e in ledger.entities.values() if e.entity_type == CONSULTATION
    ]
    consultations.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [
        {
            "id": e.id,
            "question": e.attributes.get("question"),
            "department": e.attributes.get("department"),
            "ai_generated": e.attributes.get("ai_generated"),
            "created_at": e.attributes.get("created_at"),
        }
        for e in consultations[:limit]
    ]


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

def run_consultation(question, role, department=None):
    """Always returns a real, structured four-part consultation -- OpenAI
    phrasing is additive, never load-bearing. Every number, AI-phrased or
    fallback, traces back to an already-real/heuristic/simulated-labeled figure
    from the composed modules -- never fabricated by the model."""

    if not question or not question.strip():
        return {"error": "Ask a business question first."}

    if department is not None and department not in ADVISOR_DEPARTMENTS:
        return {"error": f"Unknown department '{department}' -- must be one of {ADVISOR_DEPARTMENTS}."}

    facts = _gather(role, department)
    fallback = _build_fallback(question, department, facts)

    if not is_feature_enabled("ai_consulting_engine"):
        record_call_attempt("ai_consulting_engine", "blocked")
        result = {
            **fallback,
            "note": (
                "AI composition is currently disabled by your administrator -- "
                "showing the real, fact-grounded consultation directly."
            ),
        }
        _log_consultation(result, role)
        return result

    facts_text = build_facts_text(question, facts)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"FACTS:\n{facts_text}\n\nQUESTION: {question}"},
            ],
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)

        analysis = parsed.get("analysis")
        root_cause = parsed.get("root_cause")
        opportunity = parsed.get("opportunity")
        action_plan = parsed.get("action_plan")

        if not (analysis and root_cause and opportunity
                and isinstance(action_plan, list) and action_plan):
            raise ValueError("AI response missing one or more required consulting sections.")

        record_call_attempt("ai_consulting_engine", "succeeded")

        result = {
            "question": question,
            "department": department,
            "analysis": analysis,
            "root_cause": root_cause,
            "opportunity": opportunity,
            "action_plan": [str(step) for step in action_plan],
            "confidence_note": parsed.get("confidence_note") or _CONFIDENCE_NOTE,
            "sources": _sources(facts),
            "ai_generated": True,
        }
        _log_consultation(result, role)
        return result

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("ai_consulting_engine", "fell_back", detail=str(exc))
        result = {
            **fallback,
            "note": (
                f"AI composition unavailable ({exc}) -- showing the real, "
                "fact-grounded consultation directly."
            ),
        }
        _log_consultation(result, role)
        return result


def get_consulting_overview(role):
    """Suggested starter questions + a short summary of what data the engine
    can draw on right now (which departments are available for a scoped
    consultation, and whether the real readiness-recommendation and
    dollar-opportunity feeds currently have data)."""

    recommendations = _safe(get_recommendations_overview, role)
    opportunity_totals = _safe(get_total_identified_opportunity, role)

    rec_present = (
        isinstance(recommendations, dict)
        and "error" not in recommendations
        and bool((recommendations.get("kpi") or {}).get("total_rules"))
    )
    triggered = (
        (recommendations.get("kpi") or {}).get("triggered_count")
        if isinstance(recommendations, dict) else None
    )

    opportunity_present = (
        isinstance(opportunity_totals, dict) and "error" not in opportunity_totals
    )
    total_annual = (
        opportunity_totals.get("total_annualized_opportunity")
        if opportunity_present else None
    )

    return {
        "starter_questions": STARTER_QUESTIONS,
        "departments_available": list(ADVISOR_DEPARTMENTS),
        "data_sources": {
            "readiness_recommendations_present": rec_present,
            "triggered_recommendation_count": triggered,
            "network_opportunity_present": opportunity_present,
            "total_annualized_opportunity": total_annual,
        },
        "recent_consultations": list_recent_consultations(limit=10),
        "note": (
            "The AI Consulting Engine composes NXTDeal's own already-computed "
            "analysis into a four-part consulting answer (Analysis, Root Cause, "
            "Opportunity, Action Plan). Ask a whole-store question, or pass a "
            "department to scope the consultation. AI phrasing is optional polish "
            "over an always-real, fact-grounded answer -- never load-bearing."
        ),
    }
