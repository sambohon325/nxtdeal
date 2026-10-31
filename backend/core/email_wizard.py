"""
Email / SMS setup wizard -- AI content generation (2026-07-15, session 79). Sam: "It
should have an Ai build an email wizard as well as a traditional drag and drop
modual." Mirrors core/website_wizard.py's approach exactly: a handful of campaign
basics (goal, audience description, tone, channel) in, real ready-to-edit draft copy
out, rather than the marketer typing a subject line and body copy from a blank page.

Deliberately its own module, separate from core/ai_assistant.py (the main tool-calling
graph assistant) and core/help_api.py/core/website_wizard.py (the other single-purpose
wizards) -- same isolation reasoning as those: a single-purpose, no-tool-access OpenAI
call that can never become a side-channel around ai_tools.py's role-based graph ACL.
Uses the same OpenAI client/model as the rest of this codebase (see
core/ai_assistant.py's docstring for the "staying on OpenAI" decision).

Requests a JSON object back (response_format={"type": "json_object"}) so
core/email_templates_api.py's create_from_wizard_api() can assemble a real
EmailTemplate from a predictable shape instead of parsing free text -- same technique
core/website_wizard.py already established.
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

EMAIL_SYSTEM_PROMPT = (
    "You are a copywriter for a car dealership's marketing team, drafting a real, "
    "ready-to-edit marketing email. Given a campaign goal, an audience description, "
    "and a tone, return ONLY a JSON object with exactly these keys: "
    "subject (<=9 words, no clickbait/ALL CAPS), preheader (<=12 words, the preview "
    "text shown next to the subject line), heading (<=8 words, the email's main "
    "headline), body (2-4 short sentences, specific to the goal and audience given, "
    "do not invent specific prices/APRs/inventory details that weren't provided), "
    "cta_text (<=4 words, e.g. 'Schedule Service' or 'View Inventory'). Do not include "
    "any commentary outside the JSON object."
)

SMS_SYSTEM_PROMPT = (
    "You are a copywriter for a car dealership's marketing team, drafting a real, "
    "ready-to-edit SMS marketing text. Given a campaign goal, an audience "
    "description, and a tone, return ONLY a JSON object with exactly one key: "
    "sms_body -- a single SMS message under 320 characters, no more than one emoji, "
    "specific to the goal and audience given, ending with a short opt-out note like "
    "'Reply STOP to opt out.' Do not include any commentary outside the JSON object."
)


def _user_content(brief):

    goal = (brief or {}).get("goal") or "a general dealership announcement"
    audience = (brief or {}).get("audience_description") or "our customer database"
    tone = (brief or {}).get("tone") or "friendly and professional"

    return (
        f"Campaign goal: {goal}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n"
    )


def generate_email_copy(brief):
    """brief: {goal, audience_description, tone}. Returns a dict with subject/
    preheader/heading/body/cta_text, or a dict with an 'error' key if OpenAI can't be
    reached -- callers fall back to fallback_copy() rather than failing the wizard.

    AI Management: checks the real 'email_sms_wizard' kill switch
    (core/ai_management.py, ai_email_wizard_enabled flag) before attempting."""

    if not is_feature_enabled("email_sms_wizard"):
        record_call_attempt("email_sms_wizard", "blocked")
        return {"error": "AI email wizard is currently disabled by your administrator.", "disabled": True}

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EMAIL_SYSTEM_PROMPT},
                {"role": "user", "content": _user_content(brief)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("email_sms_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises into the wizard
        record_call_attempt("email_sms_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def generate_sms_copy(brief):
    """brief: {goal, audience_description, tone}. Returns {"sms_body": "..."} or a
    dict with an 'error' key -- same fallback contract as generate_email_copy().

    AI Management: shares the 'email_sms_wizard' kill switch with generate_email_copy()
    -- one wizard, one flag, two channels."""

    if not is_feature_enabled("email_sms_wizard"):
        record_call_attempt("email_sms_wizard", "blocked")
        return {"error": "AI SMS wizard is currently disabled by your administrator.", "disabled": True}

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SMS_SYSTEM_PROMPT},
                {"role": "user", "content": _user_content(brief)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("email_sms_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001
        record_call_attempt("email_sms_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def fallback_copy(brief, channel):
    """Plain, non-AI placeholder copy -- used when the AI call fails (no API key
    configured, network error, etc.) so the wizard still produces a usable draft
    instead of erroring out entirely, same pattern as
    core/website_wizard.py's fallback_copy()."""

    goal = (brief or {}).get("goal") or "an update from our dealership"

    if channel == "sms":
        return {
            "sms_body": f"Hi! {goal}. Reply STOP to opt out.",
        }

    return {
        "subject": "An update from our dealership",
        "preheader": goal[:80],
        "heading": "We Have News For You",
        "body": (
            f"We wanted to reach out about {goal}. Replace this placeholder text with "
            "your real message before sending."
        ),
        "cta_text": "Learn More",
    }
