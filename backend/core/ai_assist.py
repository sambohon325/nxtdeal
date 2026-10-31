"""Generic inline AI text-assist (2026-07-23) -- one small, reusable text
transform every text field across NXTDeal can call to draft, rewrite,
shorten, expand, re-tone, or grammar-clean the copy in that field.

Deliberately ONE generic function rather than a per-field wizard: unlike
core/email_wizard.py (Email/SMS campaign copy), core/website_wizard.py
(website sections), or core/social_caption_wizard.py (social captions) --
each of which is a purpose-built generator for its own department's screen --
this is the single "AI assist" button that appears inline next to any text
input (a subject line, a note, a description, a template body), so it's one
action-parameterized function, not twenty near-duplicate ones.

Follows core/communications_hub.py's generate_ai_summary() /
core/customer_journey.py's generate_journey_recommendation() pattern exactly:
a dedicated no-tool-calling OpenAI client, an is_feature_enabled()/
record_call_attempt() gate, a try/except around the real API call, and --
this module's own emphasis -- an honest, non-LLM DETERMINISTIC FALLBACK that
does a real rule-based text transformation rather than returning a blank "AI
unavailable" message. This sandbox has consistently shown no outbound OpenAI
network access, so the fallback path is what actually fires here today; it is
built to still return genuinely useful, transformed text.

Every assist is injected with this dealer's own brand tone/voice/style
guidelines (core/system_config.py's get_brand_settings()) as context, so all
generated/rewritten copy comes out on-brand. When a caller doesn't pass a
tone, the dealer's saved brand_tone is used as the default.
"""

import json
import os
import re

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt
from core.system_config import get_brand_settings

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

# The real actions an inline assist button offers. `generate` writes new copy
# for a described field (uses `context`); every other action transforms the
# `text` the field already holds.
ACTIONS = ("generate", "rewrite", "shorten", "expand", "retone", "grammar")

# Brand tones a caller may request -- kept in sync with
# core/system_config.py's BRAND_TONES (the same fixed vocabulary the brand
# settings picker offers).
TONES = ("Professional", "High Energy", "Direct", "Friendly")

# Number of leading sentences `shorten` keeps in the deterministic fallback.
_SHORTEN_SENTENCES = 1


ASSIST_SYSTEM_PROMPT = (
    "You are an inline writing assistant for a car dealership's staff software. "
    "You help employees write and refine the text in a single field (an email "
    "subject line, a customer note, a vehicle description, a template body, "
    "etc.). You will be told the ACTION to perform and given the dealership's "
    "own brand voice to stay on-brand. Return ONLY a JSON object with exactly "
    "one key, `result` (a string containing the finished text and nothing "
    "else). Never add commentary, labels, or quotation marks around the text. "
    "Actions: generate = write new text for the described field; rewrite = "
    "improve the given text while keeping its meaning; shorten = make the given "
    "text more concise; expand = add helpful detail to the given text; retone = "
    "rewrite the given text in the requested tone without changing the facts; "
    "grammar = fix spelling, grammar, punctuation, and spacing only, changing "
    "nothing else."
)


def _brand_context(tone):
    """Resolves the effective tone (caller-supplied or the dealer's saved
    brand default) plus the dealer's free-text brand voice/style guidelines.
    Returns (effective_tone, brand_settings_dict)."""

    brand = get_brand_settings()
    effective_tone = tone or brand.get("brand_tone") or "Professional"
    return effective_tone, brand


def _assist_user_content(text, action, effective_tone, brand, context):

    lines = [f"Action: {action}", f"Desired tone: {effective_tone}"]

    brand_voice = (brand.get("brand_voice") or "").strip()
    style_guidelines = (brand.get("style_guidelines") or "").strip()
    if brand_voice:
        lines.append(f"Brand voice: {brand_voice}")
    if style_guidelines:
        lines.append(f"Style guidelines: {style_guidelines}")

    if action == "generate":
        lines.append(f"Field to write: {context or 'a short piece of text'}")
        if text and text.strip():
            lines.append(f"Existing draft to build from: {text}")
    else:
        lines.append(f"Text: {text}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Deterministic, non-LLM fallback transforms -- real text operations, never a
# blank "AI unavailable" message.
# ---------------------------------------------------------------------------

def _split_sentences(text):
    """Splits into sentences on ./!/? boundaries, keeping the terminator.
    Returns a list of trimmed, non-empty sentence strings."""

    parts = re.findall(r"[^.!?]+[.!?]*", text)
    return [p.strip() for p in parts if p.strip()]


def _clean_whitespace(text):
    """Collapses runs of whitespace and trims -- shared by several fallbacks."""

    return re.sub(r"\s+", " ", text).strip()


def _fallback_grammar(text):
    """Basic, real cleanup: normalize whitespace, capitalize the first letter
    and the start of each sentence, remove spaces before punctuation, and
    ensure terminal punctuation."""

    cleaned = _clean_whitespace(text)
    # Remove spaces before ,.!?;: and collapse duplicate terminal punctuation.
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)

    sentences = _split_sentences(cleaned)
    if not sentences:
        return cleaned

    rebuilt = []
    for sentence in sentences:
        if sentence and sentence[0].islower():
            sentence = sentence[0].upper() + sentence[1:]
        rebuilt.append(sentence)

    result = " ".join(rebuilt)
    if result and result[-1] not in ".!?":
        result += "."
    return result


def _fallback_shorten(text):
    """Trim to the first N sentences; if there's only one sentence, keep it."""

    sentences = _split_sentences(_clean_whitespace(text))
    if not sentences:
        return _clean_whitespace(text)
    return " ".join(sentences[:_SHORTEN_SENTENCES])


def _fallback_expand(text):
    """Append a tasteful, generic follow-on sentence -- a real transformation
    (the output is genuinely longer and still reads naturally), without
    fabricating any specific fact about the dealership."""

    base = _clean_whitespace(text)
    if base and base[-1] not in ".!?":
        base += "."
    addition = "Please let us know if you have any questions -- we're happy to help."
    return f"{base} {addition}".strip()


def _fallback_transform(text, action, effective_tone, context):
    """Real, rule-based transform used when the AI call is disabled or fails.
    Returns (result_str, note_str). Never returns a blank/generic-unavailable
    message -- always genuinely transformed or clearly-marked text."""

    stripped = (text or "").strip()

    if action == "grammar":
        return _fallback_grammar(stripped), (
            "AI is unavailable; applied a rule-based grammar/whitespace cleanup instead."
        )

    if action == "shorten":
        return _fallback_shorten(stripped), (
            "AI is unavailable; trimmed to the leading sentence(s) instead."
        )

    if action == "expand":
        return _fallback_expand(stripped), (
            "AI is unavailable; appended a generic closing sentence instead."
        )

    if action == "retone":
        # Can't genuinely re-tone without a model -- return the cleaned input
        # unchanged, clearly marked, rather than fabricating a tone shift.
        return _clean_whitespace(stripped), (
            f"AI is unavailable; returned your text unchanged (requested tone: "
            f"{effective_tone})."
        )

    if action == "rewrite":
        return _clean_whitespace(stripped), (
            "AI is unavailable; returned your text with a whitespace cleanup only."
        )

    # generate -- no source text to transform; echo any existing draft (or a
    # clearly-marked placeholder based on the described field) rather than a
    # blank.
    if stripped:
        return _clean_whitespace(stripped), (
            "AI is unavailable; returned your existing draft unchanged."
        )
    field = (context or "this field").strip()
    return f"[Draft for {field}]", (
        "AI is unavailable; returned a placeholder -- please write this field "
        "manually or try again when AI is enabled."
    )


def assist_text(text, action, tone=None, context=None, role=None):
    """Generic inline text-assist. Returns a dict:

        {"result": str, "action": action, "ai_generated": bool, "note"?: str}

    action must be one of ACTIONS. For `generate`, `context` describes the
    field to write (and `text` may be an empty/partial draft); for every other
    action, `text` is the input to transform. `tone` (one of TONES) is
    optional -- it defaults to the dealer's saved brand_tone
    (core/system_config.py's get_brand_settings()). `role` is accepted for
    call-site symmetry / auditing and isn't used to gate here (the ACL layer
    in core/ai_assist_api.py does that).

    Gates on the real 'ai_assist' kill switch (core/ai_management.py,
    ai_assist_enabled flag). On disabled/failure, returns a real, rule-based
    DETERMINISTIC transform (ai_generated=False + a note), never a blank."""

    if action not in ACTIONS:
        return {
            "result": "",
            "action": action,
            "ai_generated": False,
            "error": f"Invalid action '{action}'. Must be one of: {', '.join(ACTIONS)}.",
        }

    # Empty-text guard: every action except `generate` needs real input text.
    if action != "generate" and (not text or not str(text).strip()):
        return {
            "result": "",
            "action": action,
            "ai_generated": False,
            "error": f"Action '{action}' requires non-empty text to transform.",
        }

    effective_tone, brand = _brand_context(tone)

    if not is_feature_enabled("ai_assist"):
        record_call_attempt("ai_assist", "blocked")
        result, note = _fallback_transform(text, action, effective_tone, context)
        return {
            "result": result,
            "action": action,
            "ai_generated": False,
            "note": note,
        }

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ASSIST_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _assist_user_content(text, action, effective_tone, brand, context),
                },
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("ai_assist", "succeeded")
        raw = json.loads(response.choices[0].message.content)
        result = str(raw.get("result") or "").strip()

        # An empty model result is treated as a failure and falls back, so the
        # caller never gets a blank.
        if not result:
            raise ValueError("Model returned an empty result.")

        return {
            "result": result,
            "action": action,
            "ai_generated": True,
        }

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("ai_assist", "fell_back", detail=str(exc))
        result, note = _fallback_transform(text, action, effective_tone, context)
        return {
            "result": result,
            "action": action,
            "ai_generated": False,
            "note": note,
        }
