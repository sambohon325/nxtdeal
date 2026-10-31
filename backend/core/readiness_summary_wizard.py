"""
core/readiness_summary_wizard.py -- OPTIONAL isolated OpenAI polish step for
Readiness' new Overview Executive Summary (core/readiness_overview.py). Same
isolation pattern as core/email_wizard.py/core/website_wizard.py/
core/social_caption_wizard.py: a single-purpose, no-tool-calling OpenAI call
that can never become a side-channel around core/ai_tools.py's role-based
graph ACL.

Deliberately narrow scope: this module NEVER generates facts. It receives an
already-computed, already-fact-checked plain-English summary (built entirely
from real Business Health / Enterprise Risk Center / Recommendations data by
core/readiness_overview.py's _build_raw_summary()) and asks the model to
smooth the PHRASING only -- the system prompt explicitly forbids inventing or
altering any number, department name, or count. The honest fallback (used
whenever OpenAI can't be reached, which is every time in this sandbox per
this session's own AI Management findings -- confirmed no outbound network
path to the OpenAI API exists here) is the original real templated summary,
completely unchanged and fully readable on its own -- polish is a nice-to-have
layer on top of a summary that is already correct and complete without it,
not a required step.

AI Management: checks the real 'readiness_executive_summary' kill switch
(core/ai_management.py, ai_readiness_summary_enabled flag) before attempting,
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
    "leadership team. You will be given a plain, already-fact-checked summary "
    "built entirely from real computed data. Your ONLY job is to smooth the "
    "phrasing -- make it read naturally, in 2-4 short sentences, in the voice "
    "of a business analyst. You MUST NOT invent, add, remove, or alter any "
    "number, percentage, department name, count, or specific finding -- every "
    "fact in your output must already be present in the input text. Do not add "
    "commentary, opinions, or recommendations that weren't already there. "
    "Return ONLY a JSON object with exactly one key: summary (the polished "
    "text)."
)


def polish_executive_summary(raw_summary_text):
    """raw_summary_text: the real, already-correct templated summary string.
    Returns {"summary": "...", } on success, or a dict with an 'error' key if
    OpenAI can't be reached / the feature is disabled -- callers fall back to
    the original raw_summary_text unchanged, never failing the Overview page."""

    if not raw_summary_text:
        return {"error": "No summary text to polish."}

    if not is_feature_enabled("readiness_executive_summary"):
        record_call_attempt("readiness_executive_summary", "blocked")
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

        record_call_attempt("readiness_executive_summary", "succeeded")
        parsed = json.loads(response.choices[0].message.content)

        if not parsed.get("summary"):
            return {"error": "AI polish returned no summary text."}

        return parsed

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("readiness_executive_summary", "fell_back", detail=str(exc))
        return {"error": str(exc)}
