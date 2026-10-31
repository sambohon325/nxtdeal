"""
core/network_advisors.py -- Network's "AI Advisors" capstone (2026-07-18,
Intelligence Network reframe, slice 6). Sam's ask: 5 real, department-specific
Q&A advisors a dealer can ask questions of directly.

Same isolated-client, facts-never-fabricated pattern as core/
ai_business_analyst.py (Readiness' own AI Business Analyst, this codebase's
most direct precedent) and every other OpenAI-backed feature here (core/
email_wizard.py, core/website_wizard.py, core/social_caption_wizard.py) --
deliberately NOT core/ai_assistant.py's tool-calling model. This module never
gives the model graph access; it pre-fetches real per-department data itself
(this exact department's own real benchmark comparison, gap analysis, root
causes, and curated playbooks -- all built earlier in this same reframe) into
a plain-text FACTS block, then asks an isolated OpenAI call to phrase an
answer strictly from that block. The system prompt explicitly forbids
inventing any number not present in the supplied context.

ONE ENGINE, FIVE LENSES -- deliberately not 5 hand-duplicated modules.
`ask_department_advisor(department, question, role)` is parametrized by
department (sales/service/parts/fi/bhph -- the 5 real departments
core/network_benchmark.py's benchmark_department()/benchmark_bhph() cover;
"executive" is deliberately excluded, same treatment core/network_root_
cause.py's get_root_causes() already gives it, since executive KPIs are a
cross-department rollup with no advisor-specific facts of their own to add
beyond what the other 5 advisors already cover).

Fallback (used whenever OpenAI is unreachable -- confirmed true for every
call in this sandbox, same finding core/ai_management.py's own docstring and
every other AI feature built this session already made): a real,
topic-matching formatter, not a generic "AI unavailable" message -- same
_TOPIC_KEYWORDS/_format_fallback_answer() shape core/ai_business_analyst.py
established, scoped down to one department's own real facts.

AI Management: registered as 'network_advisors' in core/ai_management.py's
AI_FEATURE_CATALOG, gated by a new network_advisors_enabled flag on
core/system_config.py's FEATURE_FLAGS -- checked before any OpenAI attempt,
same convention as every other AI feature in this codebase.
"""

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt
from core.network_api import get_network_benchmark_api
from core.network_menu import gap_analysis
from core.network_root_cause import get_root_causes
from core.network_playbooks import PLAYBOOK_CATALOG

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

ADVISOR_DEPARTMENTS = ["sales", "service", "parts", "fi", "bhph"]

_DEPARTMENT_TITLE = {
    "sales": "Sales",
    "service": "Service",
    "parts": "Parts",
    "fi": "F&I",
    "bhph": "BHPH / Loan Portfolio",
}

_SYSTEM_PROMPT_TEMPLATE = (
    "You are a {title} department advisor for a car dealership. You will be given a "
    "block of REAL, already-computed facts about this dealership's {title} "
    "department (labeled FACTS below) and a question. Answer using ONLY the facts "
    "provided -- you MUST NOT invent, estimate, or alter any number, percentage, "
    "count, or finding that isn't already present in FACTS. If FACTS doesn't contain "
    "enough information to answer the question, say so plainly rather than guessing. "
    "Keep your answer to 2-4 short, factual sentences, in the voice of a department "
    "advisor giving practical guidance. Return ONLY a JSON object with exactly one "
    "key: answer (the response text)."
)


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 -- a sub-module's own {"error": ...} dict is fine; a raw exception isn't
        return {}


def gather_department_facts(department, role):
    """Real per-department facts, composed entirely from already-real modules
    built earlier in this same reframe -- no new computation here, only
    filtering/composition:
      - benchmark: this dealer's own real KPIs + peer average + percentile
        rank for this department (core/network_benchmark.py, slice 1/2).
      - gaps: this department's own subset of gap_analysis()'s real gaps,
        each with the real direction/severity fix from slice 3.
      - playbooks: this department's own subset of the real curated library
        (core/network_playbooks.py, slice 5), each with a live-checked
        is_currently_active flag."""

    benchmark = _safe(get_network_benchmark_api, role, department)

    all_gaps = _safe(gap_analysis, role)
    # gap_analysis() doesn't degrade per-field for a denied role -- it returns one
    # top-level {"error": ...} dict, since the whole gap comparison depends on
    # NETWORK_ROLES-gated benchmark data. Track that honestly (gaps_access_denied)
    # rather than letting an empty department_gaps list read as "genuinely zero
    # gaps," same "surface the real denial, don't fake a zero" convention
    # core/business_health.py's own per-field degrade already established.
    gaps_access_denied = isinstance(all_gaps, dict) and "error" in all_gaps and "all_gaps" not in all_gaps
    department_gaps = (
        [g for g in all_gaps.get("all_gaps", []) if g["department"] == department]
        if isinstance(all_gaps, dict) and "all_gaps" in all_gaps
        else []
    )

    department_playbooks = []
    for pb in PLAYBOOK_CATALOG:
        if pb["department"] != department:
            continue
        finding = _safe(pb["diagnostic"])
        department_playbooks.append({
            "title": pb["title"],
            "summary": pb["summary"],
            "is_currently_active": finding is not None,
            "active_finding": finding,
        })

    return {
        "department": department,
        "benchmark": benchmark,
        "gaps": department_gaps,
        "gaps_access_denied": gaps_access_denied,
        "playbooks": department_playbooks,
    }


def _sentences_benchmark(facts):
    out = []
    bench = facts.get("benchmark") or {}
    if isinstance(bench, dict) and "error" not in bench and bench:
        pct = bench.get("percentile_rank")
        if pct is not None:
            out.append(f"This dealer's percentile rank in this department is {pct}.")
        primary_key = bench.get("primary_kpi")
        this_kpis = (bench.get("this_dealer") or {}).get("kpis") or {}
        if primary_key and primary_key in this_kpis:
            kpi = this_kpis[primary_key]
            out.append(f"Primary KPI ({kpi.get('label', primary_key)}) is {kpi.get('value')}.")
    elif isinstance(bench, dict) and "error" in bench:
        out.append("Benchmark data isn't visible with your current role.")
    if not out:
        out.append("No benchmark data is currently available for this department.")
    return out


def _sentences_gaps(facts):
    if facts.get("gaps_access_denied"):
        return ["Gap analysis data isn't visible with your current role."]
    out = []
    gaps = facts.get("gaps") or []
    opportunities = [g for g in gaps if g.get("is_opportunity")]
    opportunities.sort(key=lambda g: g.get("opportunity_gap") or 0, reverse=True)
    for g in opportunities[:3]:
        out.append(
            f"{g['label']}: this dealer is at {g['this_store']}, peer average is "
            f"{g['peer_average']} ({g.get('severity') or 'unranked'} severity opportunity)."
        )
    if not opportunities:
        out.append("No real trailing-peer-average opportunities are currently identified in this department.")
    return out


def _sentences_root_causes(facts):
    if facts.get("gaps_access_denied"):
        return ["Root-cause data isn't visible with your current role."]
    out = []
    gaps = facts.get("gaps") or []
    opportunities = [g for g in gaps if g.get("is_opportunity")]
    opportunities.sort(key=lambda g: g.get("opportunity_gap") or 0, reverse=True)
    for g in opportunities[:2]:
        rc = _safe(get_root_causes, g["department"], g["kpi"], g.get("label"))
        for cause in (rc.get("causes") or [])[:2]:
            out.append(f"Likely cause of the {g['label']} gap: {cause['finding']}")
    if not out:
        out.append("No specific root causes are currently flagged for this department's gaps.")
    return out


def _sentences_playbooks(facts):
    out = []
    playbooks = facts.get("playbooks") or []
    active = [p for p in playbooks if p["is_currently_active"]]
    for p in active[:3]:
        out.append(f"Active playbook: \"{p['title']}\" -- {p['summary']}")
    if not active:
        out.append("No curated playbooks are currently flagged as active for this department.")
    return out


_TOPIC_BUILDERS = {
    "benchmark": _sentences_benchmark,
    "gaps": _sentences_gaps,
    "causes": _sentences_root_causes,
    "playbooks": _sentences_playbooks,
}

_TOPIC_KEYWORDS = {
    "benchmark": ["rank", "percentile", "compare", "peer", "benchmark", "how are we doing"],
    "gaps": ["gap", "behind", "trailing", "opportunity", "losing"],
    "causes": ["why", "cause", "reason", "root cause", "what's causing"],
    "playbooks": ["what should", "how do i", "how do we", "fix", "improve", "playbook", "recommend"],
}


def _match_topics(question):
    q = f" {(question or '').lower()} "
    matched = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            matched.append(topic)
    return matched


def build_facts_text(facts):
    """The FACTS block sent to OpenAI -- every section built from the exact
    same real sentence builders the fallback path uses, so the AI-phrased
    answer and the fallback answer are always grounded in identical real
    numbers."""

    sections = []
    for topic, builder in _TOPIC_BUILDERS.items():
        sentences = builder(facts)
        sections.append(f"[{topic.upper()}]\n" + " ".join(sentences))
    return "\n\n".join(sections)


def _format_fallback_answer(question, facts):
    topics = _match_topics(question)
    if not topics:
        sentences = []
        for builder in _TOPIC_BUILDERS.values():
            sentences.extend(builder(facts)[:1])
        prefix = "No specific topic was recognized in your question, so here is a real digest: "
    else:
        sentences = []
        for topic in topics:
            sentences.extend(_TOPIC_BUILDERS[topic](facts))
        prefix = ""
    return (prefix + " ".join(sentences)).strip()


def ask_department_advisor(department, question, role, employee_id=None):
    """Always returns a real, useful answer -- OpenAI phrasing is additive,
    never load-bearing. Every number in the answer, AI-phrased or fallback,
    traces back to an already-real/heuristic/simulated-labeled figure from
    this Intelligence Network reframe's own modules -- never fabricated by
    the model."""

    if department not in ADVISOR_DEPARTMENTS:
        return {"error": f"Unknown advisor department '{department}' -- must be one of {ADVISOR_DEPARTMENTS}."}

    if not question or not question.strip():
        return {"error": "Ask a question first."}

    title = _DEPARTMENT_TITLE[department]
    facts = gather_department_facts(department, role)
    facts_text = build_facts_text(facts)
    fallback_answer = _format_fallback_answer(question, facts)

    if not is_feature_enabled("network_advisors"):
        record_call_attempt("network_advisors", "blocked")
        return {
            "department": department,
            "question": question,
            "answer": fallback_answer,
            "ai_generated": False,
            "note": "AI phrasing is currently disabled by your administrator -- showing the real, topic-matched answer directly.",
        }

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(title=title)},
                {"role": "user", "content": f"FACTS:\n{facts_text}\n\nQUESTION: {question}"},
            ],
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)
        answer = parsed.get("answer")

        if not answer:
            raise ValueError("AI response returned no answer text.")

        record_call_attempt("network_advisors", "succeeded")

        return {
            "department": department,
            "question": question,
            "answer": answer,
            "ai_generated": True,
            "fallback_answer": fallback_answer,
        }

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("network_advisors", "fell_back", detail=str(exc))
        return {
            "department": department,
            "question": question,
            "answer": fallback_answer,
            "ai_generated": False,
            "note": f"AI phrasing unavailable ({exc}) -- showing the real, topic-matched answer directly.",
        }


def list_advisors():
    """The real 5-advisor catalog -- what the frontend picker renders."""

    return [{"department": d, "title": _DEPARTMENT_TITLE[d]} for d in ADVISOR_DEPARTMENTS]
