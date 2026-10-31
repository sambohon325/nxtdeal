"""
Website setup wizard -- AI content generation (2026-07-14, session 58). Sam: "let ai
write the content and set it up" -- the wizard takes a handful of dealership basics
(name, address, phone, hours, branding mode, social links) and drafts real page copy
instead of the dealer typing a hero headline, an about-us paragraph, financing pitch
copy, and sample testimonials by hand.

Deliberately its own module, separate from core/ai_assistant.py (the main tool-calling
graph assistant) and core/help_api.py (the in-app help assistant) -- same isolation
reasoning as help_api.py's docstring: this is a single-purpose, no-tool-access OpenAI
call, so it can never become a side-channel around ai_tools.py's role-based graph ACL.
Uses the same OpenAI client/model as those two modules (see core/ai_assistant.py's
docstring for the "staying on OpenAI" decision).

Requests a JSON object back (response_format={"type": "json_object"}) rather than
parsing free text, so core/websites.py's create_website_from_wizard() can assemble
sections from a predictable shape instead of a brittle regex over prose.
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

SYSTEM_PROMPT = (
    "You are a copywriter for car dealership websites. Given a dealership's basic "
    "details, draft short, real, ready-to-publish website copy. Return ONLY a JSON "
    "object with exactly these keys: "
    "hero_headline (<=8 words), hero_subheadline (<=16 words), "
    "about_heading (<=6 words), about_body (2-3 sentences, warm and specific to the "
    "dealership name/location given, no invented awards or claims), "
    "financing_heading (<=6 words), financing_body (2-3 sentences pitching financing "
    "or in-house options generically -- do not invent specific APR/rate numbers), "
    "testimonials (a string of exactly 3 lines, each formatted 'Name | Quote', short "
    "plausible sample customer quotes clearly generic enough to be replaced later), "
    "contact_heading (<=6 words). Do not include any commentary outside the JSON "
    "object."
)


def generate_wizard_copy(dealership_info, mode="traditional"):
    """dealership_info: {dealership_name, address, phone, hours, branding_mode
    ('independent'|'oem'), oem_name, tone}. Returns a dict matching SYSTEM_PROMPT's
    key list, or a dict with an 'error' key if OpenAI can't be reached -- callers
    (core/websites.py's create_website_from_wizard) fall back to plain placeholder
    copy rather than failing the whole wizard when that happens."""

    name = (dealership_info or {}).get("dealership_name") or "the dealership"
    address = (dealership_info or {}).get("address") or ""
    hours = (dealership_info or {}).get("hours") or ""
    branding_mode = (dealership_info or {}).get("branding_mode") or "independent"
    oem_name = (dealership_info or {}).get("oem_name") or ""
    tone = (dealership_info or {}).get("tone") or "friendly and local"

    if not is_feature_enabled("website_wizard"):
        record_call_attempt("website_wizard", "blocked")
        return {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}

    user_content = (
        f"Dealership name: {name}\n"
        f"Address: {address}\n"
        f"Hours: {hours}\n"
        f"Branding: {'OEM-affiliated (' + oem_name + ')' if branding_mode == 'oem' and oem_name else 'Independent dealership'}\n"
        f"Site mode: {'DealerGPT stripped-down build-your-car configurator' if mode == 'dealer_gpt' else 'traditional full dealership site'}\n"
        f"Tone: {tone}\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("website_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises into the wizard
        record_call_attempt("website_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


SECTION_REGEN_SYSTEM_PROMPT = (
    "You are a copywriter for car dealership websites, rewriting ONE section of a "
    "site. Return ONLY a JSON object whose keys are exactly the field keys given, each "
    "mapped to fresh replacement text appropriate for that field's label. Keep each "
    "value roughly the same length/format as a typical value for that kind of field. "
    "Do not invent specific prices, APRs, awards, or claims. Do not include any "
    "commentary outside the JSON object."
)


def regenerate_section_copy(section_name, text_fields, dealership_name=None, tone=None, instructions=None):
    """Per-section AI rewrite (session 85) -- Sam: 'each template section should have
    ai writing abilities.' Deliberately narrower than generate_wizard_copy(): the
    caller (core/websites.py's regenerate_section()) passes only that ONE section's
    ai_writable text fields (see SECTION_TEMPLATES' per-field `ai_writable` flag) --
    image URLs, phone numbers, filter settings, and legally-sensitive fields like an
    OEM disclaimer are never sent here, so there's no risk of the AI silently rewriting
    something factual or compliance-sensitive it was never asked about.

    text_fields: list of {"key", "label", "current_value"}.
    Returns {field_key: new_text, ...} on success, or {"error": ...} on failure --
    callers should keep the section's existing values when this errors, same fallback
    discipline as fallback_copy()."""

    name = dealership_name or "the dealership"
    tone = tone or "friendly and local"

    field_list = "\n".join(
        f"- {f['key']} ({f['label']}): current value: {f.get('current_value') or '(empty)'}"
        for f in (text_fields or [])
    )

    if not field_list:
        return {"error": "No AI-writable fields on this section"}

    if not is_feature_enabled("website_wizard"):
        record_call_attempt("website_wizard", "blocked")
        return {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}

    user_content = (
        f"Dealership name: {name}\n"
        f"Tone: {tone}\n"
        f"Website section: {section_name}\n"
        f"Rewrite these fields with fresh, ready-to-publish copy:\n{field_list}\n"
        + (f"Extra instructions: {instructions}\n" if instructions else "")
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SECTION_REGEN_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("website_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- falls back, never raises into the builder
        record_call_attempt("website_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


SEO_COPY_SYSTEM_PROMPT = (
    "You are an SEO copywriter for a car dealership website, writing ONE page's meta "
    "title and meta description. Given the dealership name, the page's purpose, and a "
    "short summary of that page's real content, return ONLY a JSON object with exactly "
    "two keys: meta_title (a real, honest title, 40-60 characters, include the "
    "dealership name if it fits naturally) and meta_description (a real, honest "
    "summary, 120-158 characters, no invented prices/APRs/awards/claims that weren't "
    "given to you). Do not include any commentary outside the JSON object."
)


def generate_page_seo_copy(dealership_name, page_key, page_summary=None):
    """AI meta title/description drafting (session 113 follow-up's enterprise SEO
    automation slice) -- grounded in the page's own real content summary (passed in
    by the caller, e.g. a page's real section headings/body text), never invents
    specifics on its own. Returns {"meta_title": ..., "meta_description": ...} or a
    dict with an 'error' key -- callers fall back to fallback_seo_copy() rather than
    failing the SEO panel, same contract as every other wizard function above."""

    if not is_feature_enabled("website_wizard"):
        record_call_attempt("website_wizard", "blocked")
        return {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}

    name = dealership_name or "the dealership"
    summary = page_summary or f"the {page_key} page of a car dealership website"

    user_content = (
        f"Dealership name: {name}\n"
        f"Page: {page_key}\n"
        f"Real content summary: {summary}\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SEO_COPY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("website_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises into the SEO panel
        record_call_attempt("website_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def fallback_seo_copy(dealership_name, page_key):
    """Plain, non-AI placeholder meta copy -- used when generate_page_seo_copy() fails,
    same pattern as fallback_copy() below."""

    name = dealership_name or "Our Dealership"
    label = page_key.replace("_", " ").title()

    return {
        "meta_title": f"{label} | {name}"[:60],
        "meta_description": (
            f"Visit the {label} page at {name} to learn more. Replace this placeholder "
            "description with your own real page summary."
        )[:158],
    }


VEHICLE_DESC_SYSTEM_PROMPT = (
    "You are a copywriter for a car dealership's Vehicle Detail Page. Given a "
    "dealership name and a vehicle's real on-file attributes (year, make, model, "
    "trim, color, condition, mileage, price), write ONE short, ready-to-publish "
    "description (3-5 sentences) that highlights the vehicle using ONLY the "
    "attributes given -- never invent a feature, option, award, or condition detail "
    "that wasn't provided. Return ONLY a JSON object with exactly one key, "
    "'description'. Do not include any commentary outside the JSON object."
)


def generate_vehicle_description(dealership_name, vehicle_attrs):
    """AI Vehicle Detail Page description (session 113 follow-up's VDP slice) --
    grounded strictly in the vehicle's own real attributes, passed in by the caller
    (core/websites.py's generate_vehicle_page_description()). Returns
    {"description": str} or a dict with an 'error' key -- callers fall back to
    fallback_vehicle_description() rather than leaving the VDP blank, same contract
    as every other wizard function above."""

    name = dealership_name or "the dealership"
    attrs = vehicle_attrs or {}

    fact_lines = "\n".join(
        f"- {label}: {attrs.get(key)}"
        for key, label in (
            ("Year", "Year"), ("Make", "Make"), ("Model", "Model"),
            ("Trim", "Trim"), ("Color", "Color"), ("Condition", "Condition"),
            ("Mileage", "Mileage"), ("Price", "Price"),
        )
        if attrs.get(key)
    )

    if not is_feature_enabled("website_wizard"):
        record_call_attempt("website_wizard", "blocked")
        return {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}

    user_content = f"Dealership name: {name}\nVehicle attributes:\n{fact_lines}\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VEHICLE_DESC_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("website_wizard", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises into the VDP
        record_call_attempt("website_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def fallback_vehicle_description(vehicle_attrs):
    """Plain, non-AI placeholder VDP description -- used when
    generate_vehicle_description() fails, same pattern as fallback_copy()/
    fallback_seo_copy() below. Built only from real, on-file fields -- never invents
    anything a real AI draft wouldn't have either."""

    attrs = vehicle_attrs or {}
    parts = [str(attrs.get(k)) for k in ("Year", "Make", "Model", "Trim") if attrs.get(k)]
    title = " ".join(parts) or "This vehicle"

    sentences = [f"{title} is available now."]

    if attrs.get("Condition"):
        sentences.append(f"Condition: {attrs['Condition']}.")

    if attrs.get("Mileage"):
        sentences.append(f"{attrs['Mileage']:,} miles." if isinstance(attrs.get("Mileage"), (int, float)) else f"Mileage: {attrs['Mileage']}.")

    if attrs.get("Color"):
        sentences.append(f"Exterior color: {attrs['Color']}.")

    sentences.append("Contact us for full details and to schedule a test drive.")

    return " ".join(sentences)


def fallback_copy(dealership_info):
    """Plain, non-AI placeholder copy -- used when generate_wizard_copy() fails (no
    API key configured, network error, etc.) so the wizard still produces a usable
    draft site rather than erroring out entirely."""

    name = (dealership_info or {}).get("dealership_name") or "Our Dealership"

    return {
        "hero_headline": f"Welcome to {name}",
        "hero_subheadline": "Quality vehicles, honest service.",
        "about_heading": "About Us",
        "about_body": f"{name} is committed to helping you find the right vehicle at a fair price. Replace this placeholder text with your dealership's real story.",
        "financing_heading": "Get Pre-Approved",
        "financing_body": "We work with a range of lenders to help find financing that fits your budget. Replace this placeholder text with your real financing details.",
        "testimonials": (
            "Sample Customer | Great experience, would buy here again.\n"
            "Sample Customer | The team made the process easy.\n"
            "Sample Customer | Found exactly what I was looking for."
        ),
        "contact_heading": "Get In Touch",
    }
