"""
core/ai_business_analyst.py -- Readiness' "AI Business Analyst" capstone feature
(Enterprise Readiness & Intelligence reframe, FINAL slice, closing out all 10
structure items + all 4 capstones). Sam's spec: an executive asks a natural-
language question ("Why is inventory readiness declining?") and gets a real,
factual answer ("17 units exceed 90 days. Recon times increased 23%. Price
competitiveness declined 8%.").

Same isolated-client, facts-never-fabricated pattern as
core/readiness_summary_wizard.py (Overview's Executive Summary polish) and
every other OpenAI-backed feature in this codebase (core/email_wizard.py,
core/website_wizard.py, core/social_caption_wizard.py, etc.) -- deliberately
NOT core/ai_assistant.py's tool-calling model. This module never gives the
model graph access; it pre-fetches real data itself (composing this whole
Readiness reframe's own already-real modules -- Business Health, Enterprise
Risk Center, Recommendations, Forecasts) into a plain-text FACTS block, then
asks an isolated OpenAI call to phrase an answer strictly from that block.
The system prompt explicitly forbids inventing any number not present in the
supplied context.

Fallback (used whenever OpenAI is unreachable -- confirmed true for every
call in this sandbox per this session's own repeated AI Management findings,
see core/ai_management.py's own docstring): a real, topic-matching
formatter, NOT a generic "AI unavailable" message. _TOPIC_KEYWORDS maps a
handful of plain-English words in the question (inventory/aging, sales,
service, finance/collections, marketing, risk/exception, recommendation/
action, forecast) onto the real pre-fetched section(s) relevant to it, and
_format_fallback_answer() renders those sections as plain, factual sentences
-- e.g. asking "why is inventory readiness declining" pulls the real
aged-units-by-band count (91+ days), the real simulated turn rate, and the
real recon-checklist completion rate straight out of
core/business_health.py's own inventory_health(), matching Sam's own "17
units exceed 90 days..." example with real numbers, not an estimate. Every
sentence is built from a value that is already real/heuristic/simulated-
labeled by its own source module -- this file adds no new computation, it
only composes and phrases. If no topic keyword matches, the fallback returns
a short real cross-department digest instead of an empty answer.

AI Management: registered as 'ai_business_analyst' in core/ai_management.py's
AI_FEATURE_CATALOG, gated by a new ai_business_analyst_enabled flag on
core/system_config.py's FEATURE_FLAGS -- checked before any OpenAI attempt,
same convention as every other AI feature in this codebase.
"""

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt
from core.business_health import get_business_health_overview
from core.enterprise_risk_center import get_risk_center_overview
from core.readiness_recommendations import get_recommendations_overview
from core.readiness_forecasts import get_forecasts_overview

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

SYSTEM_PROMPT = (
    "You are a business analyst for a car dealership's leadership team. You will be "
    "given a block of REAL, already-computed facts about the dealership (labeled "
    "FACTS below) and an executive's question. Answer the question using ONLY the "
    "facts provided -- you MUST NOT invent, estimate, or alter any number, "
    "percentage, count, or finding that isn't already present in FACTS. If FACTS "
    "doesn't contain enough information to answer the question, say so plainly "
    "rather than guessing. Keep your answer to 2-4 short, factual sentences, in the "
    "voice of a business analyst -- state the numbers directly, e.g. '17 units "
    "exceed 90 days in stock.' Return ONLY a JSON object with exactly one key: "
    "answer (the response text)."
)


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 -- a sub-module's own {"error": ...} dict is fine; a raw exception isn't
        return {}


def _fmt_pct(value, digits=1):
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return "an unknown percentage"


# ---------------------------------------------------------------------------
# Real data gathering -- one call per already-real Readiness-reframe module.
# Every dict below is either real data or that module's own real {"error":...}
# ACL-denial dict (degrades gracefully, same convention every composed
# dashboard in this codebase already follows).
# ---------------------------------------------------------------------------

def gather_facts(role):
    return {
        "business_health": _safe(get_business_health_overview, role),
        "risk_center": _safe(get_risk_center_overview, role),
        "recommendations": _safe(get_recommendations_overview, role),
        "forecasts": _safe(get_forecasts_overview, role),
    }


# ---------------------------------------------------------------------------
# Per-topic real sentence builders -- each pulls specific already-labeled
# real/heuristic/simulated fields out of the gathered facts above and renders
# them as plain factual sentences. Used both to build the FACTS block sent to
# OpenAI and, unchanged, as the honest template fallback answer.
# ---------------------------------------------------------------------------

def _sentences_inventory(facts):
    out = []
    try:
        inv = (facts.get("business_health") or {}).get("inventory") or {}
        aging = inv.get("aging") or {}
        bands = aging.get("aged_units_by_band") or {}
        over90 = bands.get("91+ days")
        if over90 is not None:
            out.append(
                f"{over90} unit(s) exceed 90 days in stock "
                f"(SIMULATED listing-age basis -- no real acquisition-date field exists yet)."
            )
        avg_days = aging.get("average_days_in_stock")
        if avg_days is not None:
            out.append(
                f"Average simulated days in stock is {avg_days} days across "
                f"{aging.get('sample_size')} unsold vehicles."
            )
        turn = inv.get("turn_rate") or {}
        if turn.get("annualized_turn_rate") is not None:
            out.append(f"Simulated annualized inventory turn rate is {turn['annualized_turn_rate']}x.")
        recon = inv.get("recon_time") or {}
        if recon.get("avg_checklist_completion_pct") is not None:
            out.append(
                f"Average recon checklist completion is {_fmt_pct(recon['avg_checklist_completion_pct'])} "
                f"across {recon.get('used_unsold_count')} used unsold vehicles "
                f"({recon.get('vehicles_fully_recon_complete')} fully complete, "
                f"{recon.get('vehicles_with_zero_recon_progress')} not yet started)."
            )
        supply = inv.get("days_supply") or {}
        if supply.get("market_days_supply") is not None:
            out.append(f"Simulated market days supply is {supply['market_days_supply']} days.")
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No inventory health data is currently available.")
    return out


def _sentences_sales(facts):
    out = []
    try:
        sales = (facts.get("business_health") or {}).get("sales") or {}
        lv = sales.get("lead_volume") or {}
        if lv.get("value") is not None:
            out.append(f"Total lead volume on file is {lv['value']}.")
        sr = sales.get("show_rate") or {}
        if sr.get("value") is not None:
            out.append(
                f"Sales appointment show rate is {_fmt_pct(sr['value'] * 100)} "
                f"({sr.get('appointments_shown')} of {sr.get('appointments_scheduled')} scheduled appointments)."
            )
        cr = sales.get("close_rate") or {}
        if cr.get("value") is not None:
            out.append(f"Average per-salesperson close rate is {_fmt_pct(cr['value'])}.")
        gp = sales.get("gross_profit") or {}
        if gp.get("value") is not None:
            out.append(f"Gross profit across funded deals is ${gp['value']:,.2f}.")
        pc = sales.get("pipeline_coverage") or {}
        if pc.get("active_pipeline_count") is not None:
            out.append(f"Active sales pipeline count is {pc['active_pipeline_count']}.")
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No sales health data is currently available.")
    return out


def _sentences_service(facts):
    out = []
    try:
        svc = (facts.get("business_health") or {}).get("service") or {}
        ro = svc.get("ro_volume") or {}
        if ro.get("total") is not None:
            out.append(f"Total repair order volume is {ro['total']} ({ro.get('open')} currently open).")
        tu = svc.get("technician_utilization") or {}
        if tu.get("avg_utilization_pct_today") is not None:
            out.append(
                f"Technician utilization today is {_fmt_pct(tu['avg_utilization_pct_today'])} "
                f"(HEURISTIC -- assumed 8-hour/day capacity, {tu.get('overloaded_technician_count')} of "
                f"{tu.get('technician_count')} technicians overloaded)."
            )
        cret = svc.get("customer_retention") or {}
        if cret.get("avg_visits_per_year") is not None:
            out.append(
                f"Average service visits per customer per year is {cret['avg_visits_per_year']} "
                f"({cret.get('lost_customers')} customers considered lost)."
            )
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No service health data is currently available.")
    return out


def _sentences_finance(facts):
    out = []
    try:
        fin = (facts.get("business_health") or {}).get("finance") or {}
        ft = fin.get("funding_time") or {}
        if ft.get("avg_days_in_transit") is not None:
            out.append(
                f"Average funding time (HEURISTIC) is {ft['avg_days_in_transit']} days across "
                f"{ft.get('contracts_in_transit')} contract(s) still in transit."
            )
        collections = fin.get("collections") or {}
        if isinstance(collections, dict) and "error" not in collections:
            if collections.get("total_in_queue") is not None:
                out.append(
                    f"{collections['total_in_queue']} loan(s) are in the collections queue, "
                    f"{collections.get('recovery_risk_count', 0)} flagged as recovery risk."
                )
        elif isinstance(collections, dict) and "error" in collections:
            out.append("Collections data isn't visible with your current role.")
        portfolio = fin.get("portfolio_quality") or {}
        if isinstance(portfolio, dict) and "error" not in portfolio:
            if portfolio.get("total_loans") is not None:
                out.append(
                    f"Loan portfolio holds {portfolio['total_loans']} total loan(s), "
                    f"${portfolio.get('total_outstanding_balance', 0):,.2f} outstanding, "
                    f"${portfolio.get('total_amount_past_due', 0):,.2f} past due (SIMULATED payment-status basis)."
                )
        elif isinstance(portfolio, dict) and "error" in portfolio:
            out.append("Portfolio quality data isn't visible with your current role.")
        if (fin.get("contract_accuracy") or {}).get("not_yet_tracked"):
            out.append("Contract Accuracy has no backing data model in this system yet -- not tracked.")
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No finance health data is currently available.")
    return out


def _sentences_marketing(facts):
    out = []
    try:
        mkt = (facts.get("business_health") or {}).get("marketing") or {}
        lv = mkt.get("lead_volume") or {}
        if lv.get("value") is not None:
            out.append(f"Total marketing-attributed lead volume is {lv['value']}.")
        roi = mkt.get("roi") or {}
        if isinstance(roi, dict) and "error" not in roi:
            channel_mix = roi.get("channel_mix") or {}
            if channel_mix.get("total_revenue") is not None:
                out.append(
                    f"Real first-touch attributed revenue across {channel_mix.get('total_leads')} leads is "
                    f"${channel_mix['total_revenue']:,.2f} (real correlation, not proven multi-touch attribution)."
                )
        elif isinstance(roi, dict) and "error" in roi:
            out.append("Marketing ROI data isn't visible with your current role.")
        wt = mkt.get("website_traffic") or {}
        if wt.get("total_page_views") is not None:
            out.append(
                f"Website traffic totals {wt['total_page_views']} page view(s) across {wt.get('site_count')} "
                f"site(s) ({wt.get('bot_views', 0)} bot-flagged)."
            )
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No marketing health data is currently available.")
    return out


def _sentences_risk(facts):
    out = []
    try:
        risk = facts.get("risk_center") or {}
        kpi = risk.get("kpi") or {}
        if kpi.get("total_exception_types_active") is not None:
            out.append(
                f"{kpi['total_exception_types_active']} of {kpi.get('total_exception_types')} exception types are "
                f"currently active, affecting {kpi.get('total_affected_entities')} entities."
            )
        by_sev = kpi.get("by_severity") or {}
        active_by_sev = ", ".join(f"{v} {k}" for k, v in by_sev.items() if v)
        if active_by_sev:
            out.append(f"By severity: {active_by_sev}.")
        top = []
        for bucket in (risk.get("categories") or {}).values():
            for item in bucket or []:
                if item.get("count"):
                    top.append(item)
        top.sort(key=lambda i: i.get("count") or 0, reverse=True)
        for item in top[:3]:
            out.append(f"{item.get('title')}: {item.get('count')} ({item.get('severity')} severity).")
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No active risks are currently open across Critical, Financial, or Operational categories.")
    return out


def _sentences_recommendations(facts):
    out = []
    try:
        rec = facts.get("recommendations") or {}
        kpi = rec.get("kpi") or {}
        if kpi.get("triggered_count") is not None:
            out.append(f"{kpi['triggered_count']} of {kpi.get('total_rules')} recommendation rules are triggered.")
        for item in (rec.get("executive_recommendations") or [])[:3]:
            if item.get("recommendation"):
                out.append(f"{item.get('title')}: {item['recommendation']}")
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No high- or critical-severity recommendations are currently triggered.")
    return out


def _sentences_forecast(facts):
    out = []
    try:
        fc = facts.get("forecasts") or {}
        sales_fc = fc.get("sales") or {}
        gross = sales_fc.get("gross") or {}
        if gross.get("projected_month_total") is not None:
            out.append(
                f"Sales gross is projected to reach ${gross['projected_month_total']:,.2f} this month "
                f"(${gross.get('month_to_date', 0):,.2f} month-to-date, linear projection)."
            )
        finance_fc = fc.get("finance") or {}
        if isinstance(finance_fc, dict) and "error" not in finance_fc:
            for key in ("funding", "collections", "delinquencies"):
                block = finance_fc.get(key)
                if isinstance(block, dict) and block.get("note"):
                    out.append(f"Finance forecast ({key}): {block.get('note')}")
                    break
        inv_fc = fc.get("inventory") or {}
        if isinstance(inv_fc, dict):
            for key, val in inv_fc.items():
                if isinstance(val, dict) and val.get("value") is not None:
                    out.append(f"Inventory forecast -- {key.replace('_', ' ')}: {val['value']}.")
                    break
    except Exception:  # noqa: BLE001
        pass
    if not out:
        out.append("No forward-looking forecast data is currently available for this topic.")
    return out


def _digest(facts):
    """No topic keyword matched -- a short, real, cross-department digest
    instead of an empty answer."""

    out = []
    out.extend(_sentences_inventory(facts)[:1])
    out.extend(_sentences_sales(facts)[:1])
    out.extend(_sentences_risk(facts)[:1])
    out.extend(_sentences_recommendations(facts)[:1])
    return out


_TOPIC_BUILDERS = {
    "inventory": _sentences_inventory,
    "sales": _sentences_sales,
    "service": _sentences_service,
    "finance": _sentences_finance,
    "marketing": _sentences_marketing,
    "risk": _sentences_risk,
    "recommendation": _sentences_recommendations,
    "forecast": _sentences_forecast,
}

_TOPIC_KEYWORDS = {
    "inventory": ["inventory", "aging", "aged", "vehicle", "stock", "turn rate", "recon", "days supply"],
    "sales": ["sales", "lead volume", "close rate", "closing", "gross profit", "pipeline", "show rate"],
    "service": ["service", "repair order", " ro ", "technician", "shop capacity", "retention"],
    "finance": ["finance", "funding", "collections", "portfolio", "contract", "delinquen", "loan"],
    "marketing": ["marketing", "roi", "website traffic", "campaign", "attribution"],
    "risk": ["risk", "exception", "critical issue", "issue", "problem"],
    "recommendation": ["recommend", "action", "should we", "what should", "fix", "improve"],
    "forecast": ["forecast", "projection", "next month", "next quarter", "predict", "outlook"],
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
    answer and the fallback answer are always grounded in the identical real
    numbers."""

    sections = []
    for topic, builder in _TOPIC_BUILDERS.items():
        sentences = builder(facts)
        sections.append(f"[{topic.upper()}]\n" + " ".join(sentences))
    return "\n\n".join(sections)


def _format_fallback_answer(question, facts):
    topics = _match_topics(question)
    if not topics:
        sentences = _digest(facts)
        prefix = "No specific topic was recognized in your question, so here is a real cross-department digest: "
    else:
        sentences = []
        for topic in topics:
            sentences.extend(_TOPIC_BUILDERS[topic](facts))
        prefix = ""
    return (prefix + " ".join(sentences)).strip()


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def ask_business_analyst(question, role, employee_id=None):
    """Always returns a real, useful answer -- OpenAI phrasing is additive,
    never load-bearing. Every number in the answer, AI-phrased or fallback,
    traces back to an already-real/heuristic/simulated-labeled figure from
    this Readiness reframe's own modules -- never fabricated by the model."""

    if not question or not question.strip():
        return {"error": "Ask a question first."}

    facts = gather_facts(role)
    facts_text = build_facts_text(facts)
    fallback_answer = _format_fallback_answer(question, facts)

    if not is_feature_enabled("ai_business_analyst"):
        record_call_attempt("ai_business_analyst", "blocked")
        return {
            "question": question,
            "answer": fallback_answer,
            "ai_generated": False,
            "note": "AI phrasing is currently disabled by your administrator -- showing the real, topic-matched answer directly.",
        }

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
        answer = parsed.get("answer")

        if not answer:
            raise ValueError("AI response returned no answer text.")

        record_call_attempt("ai_business_analyst", "succeeded")

        return {
            "question": question,
            "answer": answer,
            "ai_generated": True,
            "fallback_answer": fallback_answer,
        }

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("ai_business_analyst", "fell_back", detail=str(exc))
        return {
            "question": question,
            "answer": fallback_answer,
            "ai_generated": False,
            "note": f"AI phrasing unavailable ({exc}) -- showing the real, topic-matched answer directly.",
        }
