"""
core/network_summary_wizard.py -- OPTIONAL isolated OpenAI polish step for
Network's new Overview/Opportunities Executive Summary
(core/network_opportunity_value.py). Same isolation pattern as
core/email_wizard.py/core/website_wizard.py/core/social_caption_wizard.py/
core/readiness_summary_wizard.py: a single-purpose, no-tool-calling OpenAI
call that can never become a side-channel around core/ai_tools.py's
role-based graph ACL.

Deliberately narrow scope: this module NEVER generates facts. It receives an
already-computed, already-fact-checked plain-English summary (built entirely
from real network percentile/dollar-opportunity/audit-recommendation data by
core/network_opportunity_value.py's _build_raw_executive_summary()) and asks
the model to smooth the PHRASING only -- the system prompt explicitly
forbids inventing or altering any number, department name, percentage, or
dollar figure. The honest fallback (used whenever OpenAI can't be reached,
which is every time in this sandbox per this codebase's own repeated AI
Management findings -- confirmed no outbound network path to the OpenAI API
exists here) is the original real templated summary, completely unchanged
and fully readable on its own -- polish is a nice-to-have layer on top of a
summary that is already correct and complete without it, not a required
step.

AI Management: checks the real 'network_executive_summary' kill switch
(core/ai_management.py, ai_network_summary_enabled flag) before attempting,
same convention as every other OpenAI-backed feature in this codebase.
"""

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

POLISH_SYSTEM_PROMPT = (
    "You are an editor polishing an executive summary for a car dealership's "
    "leadership team, in a '24/7 AI 20 Group' network-benchmarking product. "
    "You will be given a plain, already-fact-checked summary built entirely "
    "from real computed data -- percentile rank, peer-benchmark gaps, and "
    "dollar-opportunity figures. Your ONLY job is to smooth the phrasing -- "
    "make it read naturally, in 2-4 short sentences, in the voice of a "
    "business analyst. You MUST NOT invent, add, remove, or alter any "
    "number, percentage, dollar figure, department name, or specific "
    "finding -- every fact in your output must already be present in the "
    "input text. Do not add commentary, opinions, or recommendations that "
    "weren't already there. Return ONLY a JSON object with exactly one key: "
    "summary (the polished text)."
)


def polish_network_executive_summary(raw_summary_text):
    """raw_summary_text: the real, already-correct templated summary string.
    Returns {"summary": "...", } on success, or a dict with an 'error' key if
    OpenAI can't be reached / the feature is disabled -- callers fall back to
    the original raw_summary_text unchanged, never failing the Overview/
    Opportunities page."""

    if not raw_summary_text:
        return {"error": "No summary text to polish."}

    if not is_feature_enabled("network_executive_summary"):
        record_call_attempt("network_executive_summary", "blocked")
        return {"error": "AI summary polish is currently disabled by your administrator.", "disabled": True}

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": raw_summary_text},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("network_executive_summary", "succeeded")
        parsed = json.loads(response.choices[0].message.content)

        if not parsed.get("summary"):
            return {"error": "AI polish returned no summary text."}

        return parsed

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("network_executive_summary", "fell_back", detail=str(exc))
        return {"error": str(exc)}
