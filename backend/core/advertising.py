"""
Advertising -- Meta/Google ad campaigns with inventory integration (session 83). Sam:
"we also need to have an advertising dash, this will be a advertising tool to start
meta and google ad campaings that include inventory and allow ai recommendations /
buidling, or granular control."

An AdCampaign is an ordinary graph entity (core/entity_types.py's AD_CAMPAIGN),
distinct from core/campaigns.py's Campaign (NXTDeal's own email/SMS/direct-mail
customer-lifecycle engine -- a different real-world object with different fields:
platform, budget, targeting, ad creative). Tied to the Employee who built it and
optionally real Vehicle entities via `linked_vehicle_ids` (id only, resolved live at
read time, same no-parallel-inventory-copy rule as core/social_posts.py).

This sandbox has no real path to the Meta/Google Ads APIs, so "launching" is an
honestly-labeled SIMULATED action -- launch_ad_campaign() stamps real status/
timestamps on a real graph record, exactly like core/campaigns.py's
activate_campaign()/core/social_posts.py's publish_post(). No real ad spend, no real
delivery -- impressions/clicks/CPC/ROAS are explicitly not_yet_tracked (see
core/advertising_api.py) rather than fabricated.

generate_ad_recommendation() is the "AI recommendations" half of Sam's ask -- an
isolated, no-tool-access OpenAI call (same isolation pattern as
core/email_wizard.py/core/website_wizard.py/core/reputation.py's auto-respond bot)
that drafts real headline/primary-text/targeting suggestions from a brief; a plain
fallback covers the case OpenAI can't be reached. create_ad_campaign() itself accepts
either that draft or fully manual, granular input -- "AI recommendations... or
granular control" is a single code path, not two parallel ones.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import AD_CAMPAIGN, VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.ai_management import is_feature_enabled, record_call_attempt
from core import integrations_registry

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 83) --
# every real ad campaign ever created, edited, launched, paused, completed, or
# cancelled had been silently discarded on server restart. Fixed below: every
# mutating function now saves directly.

load_dotenv()

client = LazyOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PLATFORMS = ["meta", "google"]

OBJECTIVES = [
    {"key": "traffic", "name": "Website Traffic"},
    {"key": "leads", "name": "Lead Generation"},
    {"key": "awareness", "name": "Brand Awareness"},
    {"key": "inventory", "name": "Inventory / Vehicle Listings"},
]

_EDITABLE_FIELDS = {
    "name", "objective", "headline", "primary_text", "description", "disclaimer",
    "daily_budget", "targeting", "linked_vehicle_ids",
}

RECOMMENDATION_SYSTEM_PROMPT = (
    "You are a paid-media strategist for a car dealership, drafting a real, "
    "ready-to-edit Meta or Google ad. Given a platform, objective, audience "
    "description, and optional vehicle details, return ONLY a JSON object with "
    "exactly these keys: headline (<=8 words), primary_text (2-3 sentences, no "
    "invented prices/APRs/offers beyond what was given), description (<=15 words, a "
    "secondary line), disclaimer (a short, honest disclaimer -- e.g. 'Price excludes "
    "tax, title, and dealer fees. See dealer for details.' -- required whenever "
    "pricing or financing terms are mentioned, per Reg Z advertising rules), and "
    "targeting_suggestion (<=20 words describing a real targeting approach: location "
    "radius, age range, interests). Do not include any commentary outside the JSON "
    "object."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_platforms():
    return list(PLATFORMS)


def list_objectives():
    return list(OBJECTIVES)


def _valid_vehicle_ids(ids):
    return [v for v in (ids or []) if ledger.get_entity(v) and ledger.get_entity(v).entity_type == VEHICLE]


def generate_ad_recommendation(brief):
    """brief: {platform, objective, audience_description, vehicle_description}.
    Returns a dict with headline/primary_text/description/disclaimer/
    targeting_suggestion, or a dict with an 'error' key if OpenAI can't be reached --
    callers fall back to fallback_recommendation() rather than failing the flow."""

    if not is_feature_enabled("advertising_ai"):
        record_call_attempt("advertising_ai", "blocked")
        return {"error": "AI ad recommendations are currently disabled by your administrator.", "disabled": True}

    platform = (brief or {}).get("platform", "meta")
    objective = (brief or {}).get("objective", "traffic")
    audience = (brief or {}).get("audience_description") or "local car buyers"
    vehicle_desc = (brief or {}).get("vehicle_description") or ""

    user_content = (
        f"Platform: {platform}\nObjective: {objective}\nAudience: {audience}\n"
        f"Vehicle(s): {vehicle_desc or 'not specified'}\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": RECOMMENDATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        record_call_attempt("advertising_ai", "succeeded")
        return json.loads(response.choices[0].message.content)

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back
        record_call_attempt("advertising_ai", "fell_back", detail=str(exc))
        return {"error": str(exc)}


def fallback_recommendation(brief):
    """Plain, non-AI placeholder -- used when the AI call fails, same pattern as
    core/email_wizard.py's fallback_copy()."""

    objective = (brief or {}).get("objective", "traffic")

    return {
        "headline": "Discover Your Next Vehicle Today",
        "primary_text": (
            f"We're running a {objective} campaign -- replace this placeholder text "
            "with your real message before launching."
        ),
        "description": "Visit us or browse online.",
        "disclaimer": "Price excludes tax, title, and dealer fees. See dealer for details.",
        "targeting_suggestion": "25-mile radius around the dealership, ages 25-64, interest in autos.",
    }


def create_ad_campaign(created_by, platform, objective, name, fields, linked_vehicle_ids=None):

    if platform not in PLATFORMS:
        return {"error": f"Unknown platform '{platform}' -- choose one of {PLATFORMS}"}

    if objective not in [o["key"] for o in OBJECTIVES]:
        return {"error": f"Unknown objective '{objective}'"}

    ad_id = id_generator.generate("AD")

    fields = fields or {}

    entity = Entity(
        id=ad_id,
        entity_type=AD_CAMPAIGN,
        attributes={
            "platform": platform,
            "objective": objective,
            "name": name or f"New {platform.title()} Campaign",
            "headline": fields.get("headline", ""),
            "primary_text": fields.get("primary_text", ""),
            "description": fields.get("description", ""),
            "disclaimer": fields.get("disclaimer", ""),
            "daily_budget": fields.get("daily_budget"),
            "targeting": fields.get("targeting") or {},
            "linked_vehicle_ids": _valid_vehicle_ids(linked_vehicle_ids),
            "ai_generated": bool(fields.get("ai_generated")),
            "status": "draft",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "launched_at": None,
            "paused_at": None,
            "completed_at": None,
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_ad_campaign(ad_id):

    entity = ledger.get_entity(ad_id)

    if entity and entity.entity_type == AD_CAMPAIGN:
        return entity

    return None


def update_ad_campaign(ad_id, patch):

    entity = get_ad_campaign(ad_id)

    if not entity:
        return None

    for key, value in (patch or {}).items():

        if key not in _EDITABLE_FIELDS:
            continue

        if key == "linked_vehicle_ids":
            value = _valid_vehicle_ids(value)

        entity.attributes[key] = value

    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def launch_ad_campaign(ad_id):
    """SIMULATED launch -- see module docstring. Real graph state, no real ad spend or
    delivery."""

    entity = get_ad_campaign(ad_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("draft", "paused"):
        return {"error": f"Campaign is '{entity.attributes.get('status')}', not draft/paused"}

    # Route the launch through the provider seam (Track B). With no `ads` adapter
    # registered this returns an honest simulated result; register one and the SAME call
    # site publishes to a real ad platform with zero changes here.
    dispatch = integrations_registry.publish_ad({
        "ad_id": ad_id,
        "platform": entity.attributes.get("platform"),
        "objective": entity.attributes.get("objective"),
        "name": entity.attributes.get("name"),
        "headline": entity.attributes.get("headline"),
        "primary_text": entity.attributes.get("primary_text"),
        "daily_budget": entity.attributes.get("daily_budget"),
        "targeting": entity.attributes.get("targeting"),
    })

    entity.attributes["status"] = "active"
    entity.attributes["launched_at"] = entity.attributes.get("launched_at") or _now()
    entity.attributes["updated_at"] = _now()
    entity.attributes["publish_mode"] = "live" if not dispatch.get("simulated") else "simulated"
    entity.attributes["publish_provider"] = dispatch.get("provider")

    save_graph(GRAPH_PATH)

    return entity


def pause_ad_campaign(ad_id):

    entity = get_ad_campaign(ad_id)

    if not entity:
        return None

    if entity.attributes.get("status") != "active":
        return {"error": f"Campaign is '{entity.attributes.get('status')}', not active"}

    entity.attributes["status"] = "paused"
    entity.attributes["paused_at"] = _now()
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def complete_ad_campaign(ad_id):

    entity = get_ad_campaign(ad_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("active", "paused"):
        return {"error": f"Campaign is '{entity.attributes.get('status')}', not active/paused"}

    entity.attributes["status"] = "completed"
    entity.attributes["completed_at"] = _now()
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def cancel_ad_campaign(ad_id):

    entity = get_ad_campaign(ad_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("draft", "paused"):
        return {"error": f"Campaign is '{entity.attributes.get('status')}', can only cancel a draft or paused campaign"}

    entity.attributes["status"] = "cancelled"
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def list_ad_campaigns(platform=None, status=None, created_by=None):

    campaigns = [e for e in ledger.get_all().values() if e.entity_type == AD_CAMPAIGN]

    if platform:
        campaigns = [c for c in campaigns if c.attributes.get("platform") == platform]

    if status:
        campaigns = [c for c in campaigns if c.attributes.get("status") == status]

    if created_by:
        campaigns = [c for c in campaigns if c.attributes.get("created_by") == created_by]

    campaigns.sort(key=lambda c: c.attributes.get("created_at") or "", reverse=True)

    return campaigns


def resolve_linked_vehicles(ad_id):

    entity = get_ad_campaign(ad_id)

    if not entity:
        return []

    vehicles = []

    for vid in entity.attributes.get("linked_vehicle_ids") or []:

        v = ledger.get_entity(vid)

        if not v or v.entity_type != VEHICLE:
            continue

        vehicles.append({
            "id": v.id,
            "year": v.attributes.get("Year"),
            "make": v.attributes.get("Make"),
            "model": v.attributes.get("Model"),
            "trim": v.attributes.get("Trim"),
            "price": v.attributes.get("Price"),
        })

    return vehicles
