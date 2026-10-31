"""
AI caption generation for the Social & Reputation post builder (2026-07-18, Marketing
Growth Platform follow-up -- closes the one gap session 91's own build explicitly
flagged as open: "AI caption generation (no backend endpoint for it exists yet, unlike
Email/SMS's email_wizard.py)").

Same isolated, no-tool-calling OpenAI client pattern as core/email_wizard.py/
core/website_wizard.py/core/reputation.py's auto-respond bot/core/website_chat.py's AI
Receptionist -- a single-purpose call that can never become a side-channel around
core/ai_tools.py's role-based graph ACL. Grounded in a real linked vehicle's actual
attributes when one is provided (never invents a price, VIN, or trim), same
never-fabricate-inventory-detail discipline every other AI-drafting feature in this
codebase follows. Platform-aware -- a real per-platform tone/length/hashtag convention
(X's character limit, Instagram's hashtag-heavy style, LinkedIn's professional register,
etc.) rather than one generic caption reused everywhere.
"""

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PLATFORM_GUIDANCE = {
    "facebook": "Facebook: 1-3 short sentences, warm and conversational, 0-2 hashtags.",
    "instagram": "Instagram: short, visual, energetic caption, 3-6 relevant hashtags at the end.",
    "x": "X (Twitter): a single punchy line, under 260 characters total, 0-2 hashtags.",
    "linkedin": "LinkedIn: a more professional register, 2-4 sentences, no more than 1 hashtag.",
    "tiktok": "TikTok: short, casual, trend-aware caption, 2-4 hashtags, can use 1 emoji.",
}

CAPTION_SYSTEM_PROMPT = (
    "You are a social media copywriter for a car dealership. Given a platform, a goal, "
    "an optional tone, and optional real vehicle details, write ONE ready-to-post "
    "caption for that platform. If vehicle details are provided, reference ONLY those "
    "exact details (year/make/model/trim/price) -- never invent a price, VIN, feature, "
    "or financing term that wasn't given to you. If no vehicle details are provided, "
    "write a general dealership caption for the stated goal instead. Follow the "
    "platform's own real style/length/hashtag convention described below. Return ONLY "
    "a JSON object with one key: caption."
)


def _vehicle_context(vehicle):

    if not vehicle:
        return "(no specific vehicle -- write a general dealership caption)"

    parts = [str(vehicle.get(k)) for k in ("year", "make", "model", "trim") if vehicle.get(k)]
    line = " ".join(parts) or "a vehicle in stock"

    if vehicle.get("price") is not None:
        line += f" -- ${vehicle['price']}"

    return f"Real vehicle to feature: {line}"


def generate_caption(platform, goal=None, tone=None, vehicle=None):
    """platform: one of core/social_posts.py's PLATFORMS. goal/tone: plain strings.
    vehicle: an optional dict shaped like core/social_posts.py's resolve_linked_
    vehicles()/search_inventory_for_post() output (year/make/model/trim/price).

    Returns {"caption": "..."} on success, or a dict with an 'error' key on any
    OpenAI/network/parse failure -- callers fall back to fallback_caption() rather
    than failing the builder, same contract as core/email_wizard.py."""

    if not is_feature_enabled("social_caption_wizard"):
        record_call_attempt("social_caption_wizard", "blocked")
        return {"error": "AI caption generation is currently disabled by your administrator.", "disabled": True}

    guidance = PLATFORM_GUIDANCE.get(platform, "Write a short, platform-appropriate caption.")
    goal_text = goal or "promote the dealership"
    tone_text = tone or "friendly and upbeat"

    user_content = (
        f"Platform: {platform}\n"
        f"Platform style guidance: {guidance}\n"
        f"Goal: {goal_text}\n"
        f"Tone: {tone_text}\n"
        f"{_vehicle_context(vehicle)}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)
        caption = (parsed.get("caption") or "").strip()

        if not caption:
            record_call_attempt("social_caption_wizard", "fell_back", detail="Empty caption returned")
            return {"error": "Empty caption returned"}

        record_call_attempt("social_caption_wizard", "succeeded")
        return {"caption": caption}

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises into the builder
        record_call_attempt("social_caption_wizard", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def fallback_caption(platform, goal=None, vehicle=None):
    """Plain, non-AI placeholder caption -- used when the AI call fails (no API key
    configured, network error, etc.) so the builder still produces something usable
    instead of erroring out, same pattern as core/email_wizard.py's fallback_copy()."""

    goal_text = goal or "check out what's new at our dealership"

    if vehicle:
        parts = [str(vehicle.get(k)) for k in ("year", "make", "model", "trim") if vehicle.get(k)]
        line = " ".join(parts) or "this vehicle"
        price = f" -- ${vehicle['price']}" if vehicle.get("price") is not None else ""
        return {"caption": f"Take a look at this {line}{price}, available now. Stop by or reach out to learn more!"}

    return {"caption": f"We wanted to share: {goal_text}. Reach out to learn more!"}
