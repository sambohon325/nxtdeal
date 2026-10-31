"""Inventory Advertising Engine (2026-07-23) -- auto ad campaigns driven
directly from the real Vehicle inventory already in the graph.

GRAPH-NATIVE, single source of truth: every campaign this module builds is an
ordinary Entity in the same ledger as everything else (entity_type
"InventoryAdCampaign", id prefix "IADCAMP"), linked to the real Vehicle it
advertises via a `vehicle_id` attribute -- NOT a separate campaign store, and
NOT a copied snapshot of the vehicle's price/photos (the vehicle's real
Year/Make/Model/Trim/Price are resolved live off the linked Vehicle entity at
read time, the same no-parallel-inventory-copy rule core/advertising.py's
`linked_vehicle_ids` and core/social_posts.py already established).

Deliberately DISTINCT from core/advertising.py's AdCampaign (session 83, a
manually-built Meta/Google campaign with its own launch/pause lifecycle) and
from core/campaigns.py's Campaign (the email/SMS customer-lifecycle engine).
This module is the "inventory drives the ad" half: given a vehicle (or a whole
class of vehicles -- aged units, price-dropped units) it AUTO-generates a
ready-to-edit campaign spec (headline / body / target_audience /
suggested_daily_budget) with zero manual copywriting, across five channels
(meta, google, retargeting, price_drop, aged_inventory).

HONEST real-vs-simulated split, matching this codebase's session-110 disclosure
convention: which real vehicles qualify for a campaign is 100% REAL (a genuine
query over real Vehicle entities -- unsold units, units with a real recorded
price drop, units past an age threshold). The generated ad SPEC is a real,
persisted record. But the ad-PLATFORM output is honestly SIMULATED -- no real
Meta Ads / Google Ads API is connected anywhere in this codebase (same gap
core/advertising.py already discloses), so this module NEVER launches, spends,
or delivers a real ad. It generates campaign specs/copy and a clearly-labeled
SIMULATED estimated-reach figure (deterministically seeded per campaign id, the
same hashlib convention core/pricing_desk.py/core/communications_hub.py already
use, so the same campaign always reads the same reach rather than fresh noise).

Vehicle listing age: no acquisition/stock-date field exists on Vehicle in this
codebase (the same finding core/inventory_overview.py/core/pricing_desk.py
already documented). aged_inventory_campaigns() therefore prefers a REAL age
whenever one is available (a real `days_in_stock` attribute, or a real
`DateInStock`/`DateAcquired` date), and only falls back to the SAME
deterministic simulated listing age core/pricing_desk.py's Age-Based Adjustment
already computes when no real date exists -- clearly flagging `age_is_estimated`
on every campaign so an estimated age is never presented as a real one.

The AI half (generate_ad_copy) is a real, isolated, kill-switched OpenAI call
following core/communications_hub.py's/core/customer_journey.py's established
isolated-wizard-with-fallback pattern exactly (a dedicated no-tool-calling
client, an is_feature_enabled()/record_call_attempt() gate on feature key
`inventory_ad_copy` / flag `inventory_ad_copy_enabled`, a try/except around the
real API call, and an honest, non-AI fallback for when the call can't be reached
-- this sandbox has consistently shown no outbound OpenAI network access, so the
fallback path is what actually fires here today).

Follows the per-mutation save_graph() convention core/pricing_desk.py/
core/communications_hub.py/core/customer_journey.py already established for
low/moderate-frequency, graph-mutating calls.
"""

import hashlib
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# New entity type / id prefix for this module. Kept as local constants rather
# than editing the shared core/entity_types.py / core/id_generator.py (reported
# to the parent for canonical wiring) -- Entity.entity_type is a plain string
# and IDGenerator.counters is a plain dict, so a module-local registration keeps
# this file self-contained and its tests standalone-green without touching a
# shared file. setdefault() below never clobbers a value the parent may later add.
INVENTORY_AD_CAMPAIGN = "InventoryAdCampaign"
ID_PREFIX = "IADCAMP"

id_generator = IDGenerator()
id_generator.counters.setdefault(ID_PREFIX, 0)

# The five real channels this engine builds for.
CHANNELS = ["meta", "google", "retargeting", "price_drop", "aged_inventory"]

SIMULATED_BASIS = "simulated_ad_platform_output"

SIMULATED_DISCLAIMER = (
    "SIMULATED -- no real Meta Ads / Google Ads API is connected in this "
    "environment. This is a generated, ready-to-edit campaign SPEC (copy, "
    "audience, suggested budget) and a deterministically-seeded estimated-reach "
    "figure, never a launched, spending, or delivered ad."
)

AGE_ESTIMATE_DISCLAIMER = (
    "ESTIMATED listing age -- no real acquisition/stock-date field was present "
    "on this vehicle, so the same deterministic simulated listing age "
    "core/pricing_desk.py's Age-Based Adjustment uses was substituted. Real "
    "days_in_stock / DateInStock data is preferred whenever present."
)

# Rule-based per-channel baseline daily budget (USD) before the price-tier bump.
_CHANNEL_BASE_BUDGET = {
    "meta": 25,
    "google": 30,
    "retargeting": 15,
    "price_drop": 20,
    "aged_inventory": 18,
}

# Rule-based baseline target audience per channel.
_CHANNEL_AUDIENCE = {
    "meta": (
        "In-market local car shoppers 25-64 within a 25-mile radius, "
        "interest-targeted to auto intenders and lookalikes of recent buyers."
    ),
    "google": (
        "High-intent search audience querying the make/model and "
        "'cars for sale near me' within the dealership's primary market."
    ),
    "retargeting": (
        "Prior website / VDP visitors who engaged but did not convert in the "
        "last 30 days, plus abandoned-lead re-engagement."
    ),
    "price_drop": (
        "Price-sensitive shoppers and prior viewers of this specific unit, plus "
        "lookalikes of buyers who responded to recent price reductions."
    ),
    "aged_inventory": (
        "Broad local value-seeker audience to accelerate turn on a unit that has "
        "been on the lot longer than target."
    ),
}

# Simulated impressions-per-dollar factor per channel, used only to seed the
# clearly-labeled estimated-reach figure in the overview.
_CHANNEL_REACH_FACTOR = {
    "meta": 70,
    "google": 45,
    "retargeting": 90,
    "price_drop": 60,
    "aged_inventory": 55,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seed_int(key, salt, mod):
    """Deterministic per-key pseudo-random int, same convention
    core/pricing_desk.py/core/communications_hub.py already established -- the
    same key always resolves to the same simulated value."""

    digest = hashlib.sha256(f"{key}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def _validate_channel(channel):
    if channel not in CHANNELS:
        raise ValueError(
            f"Invalid channel '{channel}'. Must be one of: " + ", ".join(CHANNELS) + "."
        )


def _get_vehicle_or_raise(vehicle_id):
    entity = ledger.get_entity(vehicle_id)
    if not entity or entity.entity_type != VEHICLE:
        raise ValueError(f"No vehicle found with id {vehicle_id}.")
    return entity


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vehicle_label(vehicle):
    attrs = vehicle.attributes
    parts = [
        str(attrs.get("Year") or "").strip(),
        str(attrs.get("Make") or "").strip(),
        str(attrs.get("Model") or "").strip(),
        str(attrs.get("Trim") or "").strip(),
    ]
    label = " ".join(p for p in parts if p)
    return label or f"Vehicle {vehicle.id}"


def _vehicle_price(vehicle):
    return _safe_float(vehicle.attributes.get("Price"))


def _unsold_vehicles():
    return [
        e
        for e in ledger.get_all().values()
        if e.entity_type == VEHICLE and not e.attributes.get("DateSold")
    ]


def _price_drop_info(vehicle):
    """Real price-drop detection. A vehicle counts as price-dropped if it carries
    an explicit real signal:
      - a `price_drop` boolean attribute set True, or
      - a `PreviousPrice`/`OriginalPrice` that is strictly greater than the
        current `Price`, or
      - a `price_history` list (core/inventory_aging.py's real append-only log)
        whose earliest recorded price is strictly greater than the current one.
    Returns (has_drop, from_price, to_price)."""

    attrs = vehicle.attributes
    current = _vehicle_price(vehicle)

    prior = _safe_float(attrs.get("PreviousPrice"))
    if prior is None:
        prior = _safe_float(attrs.get("OriginalPrice"))

    if prior is None:
        history = attrs.get("price_history")
        if isinstance(history, list) and history:
            prices = [
                _safe_float(h.get("price")) if isinstance(h, dict) else _safe_float(h)
                for h in history
            ]
            prices = [p for p in prices if p is not None]
            if prices:
                prior = max(prices)

    if prior is not None and current is not None and prior > current:
        return True, prior, current

    if attrs.get("price_drop") is True and current is not None:
        return True, prior if prior is not None else None, current

    return False, None, None


def _vehicle_age_days(vehicle):
    """Returns (age_days, is_estimated). Prefers a REAL days_in_stock attribute,
    then a real DateInStock/DateAcquired date, and only falls back to the same
    deterministic simulated listing age core/pricing_desk.py already uses when no
    real signal exists -- flagged is_estimated=True so it's never mistaken for a
    real age."""

    attrs = vehicle.attributes

    real_days = _safe_float(attrs.get("days_in_stock"))
    if real_days is not None and real_days >= 0:
        return int(real_days), False

    for date_key in ("DateInStock", "DateAcquired"):
        raw = attrs.get(date_key)
        if raw:
            parsed = _parse_date(raw)
            if parsed is not None:
                delta = (datetime.now(timezone.utc) - parsed).days
                if delta >= 0:
                    return delta, False

    # Fall back to the same deterministic simulated listing age Pricing uses.
    try:
        from core.pricing_desk import get_age_based_adjustment

        adj = get_age_based_adjustment(vehicle.id)
        if isinstance(adj, dict) and "estimated_listing_age_days" in adj:
            return int(adj["estimated_listing_age_days"]), True
    except Exception:  # noqa: BLE001 -- never let the pricing fallback break age derivation
        pass

    # Last-resort deterministic estimate, self-contained (mirrors Pricing's 1-130 band).
    return _seed_int(f"{vehicle.id}|age", "age", 130) + 1, True


def _parse_date(raw):
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    for candidate in (text, text.split("T")[0]):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Rule-based copy / budget baseline (used by generate_campaign and as the
# non-AI fallback for generate_ad_copy).
# ---------------------------------------------------------------------------

def _suggested_daily_budget(channel, price):
    """Rule-based baseline: a per-channel base plus a small price-tier bump
    (pricier units warrant a slightly higher daily spend). Deterministic, no
    randomness -- a simulated suggestion, not a real bid."""

    base = _CHANNEL_BASE_BUDGET.get(channel, 20)
    if price:
        # +$1/day per $2,500 of vehicle price, capped at +$40/day.
        bump = min(round(price / 2500.0), 40)
    else:
        bump = 0
    return int(base + bump)


def _baseline_copy(vehicle, channel, price, price_drop=None, age_days=None):
    """Rule-based headline/body baseline for one vehicle+channel. price_drop is
    (from_price, to_price) when known; age_days is an int when known."""

    label = _vehicle_label(vehicle)
    price_text = f"${int(price):,}" if price else "a great price"

    if channel == "price_drop":
        if price_drop and price_drop[0] and price_drop[1]:
            saved = int(price_drop[0] - price_drop[1])
            headline = f"Price Drop: {label} Now {price_text}"
            body = (
                f"Just reduced by ${saved:,} -- the {label} is now {price_text}. "
                "Priced to move, so don't wait. Contact us today for a test drive."
            )
        else:
            headline = f"Price Drop: {label} Now {price_text}"
            body = (
                f"We just lowered the price on this {label} to {price_text}. "
                "Priced to move -- contact us today before it's gone."
            )
    elif channel == "aged_inventory":
        headline = f"Special Savings on This {label}"
        body = (
            f"This {label} is ready for its new home at {price_text}. "
            "We've marked it for special savings -- reach out today for our best deal."
        )
    elif channel == "retargeting":
        headline = f"Still Thinking About the {label}?"
        body = (
            f"You viewed this {label} at {price_text}. It's still available -- "
            "let's get you behind the wheel. Reply to schedule a test drive."
        )
    elif channel == "google":
        headline = f"{label} for Sale -- {price_text}"
        body = (
            f"Shop this {label} at {price_text} at our dealership. Financing "
            "available. See photos, details, and book a test drive online."
        )
    else:  # meta
        headline = f"Meet Your Next Vehicle: {label}"
        body = (
            f"This {label} is available now for {price_text}. Local delivery and "
            "financing available -- message us to reserve your test drive."
        )

    disclaimer = (
        "Price excludes tax, title, and dealer fees. See dealer for details."
        if price
        else ""
    )

    return {
        "headline": headline,
        "body": body,
        "disclaimer": disclaimer,
    }


def _campaign_brief(entity):
    attrs = entity.attributes
    vehicle = ledger.get_entity(attrs.get("vehicle_id"))
    live_price = _vehicle_price(vehicle) if vehicle else attrs.get("price")
    live_label = _vehicle_label(vehicle) if vehicle else attrs.get("vehicle_label")

    return {
        "id": entity.id,
        "vehicle_id": attrs.get("vehicle_id"),
        "vehicle_label": live_label,
        "channel": attrs.get("channel"),
        "headline": attrs.get("headline"),
        "body": attrs.get("body"),
        "disclaimer": attrs.get("disclaimer"),
        "target_audience": attrs.get("target_audience"),
        "suggested_daily_budget": attrs.get("suggested_daily_budget"),
        "price": live_price,
        "age_days": attrs.get("age_days"),
        "age_is_estimated": attrs.get("age_is_estimated"),
        "price_drop_from": attrs.get("price_drop_from"),
        "price_drop_to": attrs.get("price_drop_to"),
        "ai_generated": attrs.get("ai_generated", False),
        "created_at": attrs.get("created_at"),
        "basis": SIMULATED_BASIS,
        "disclaimer_note": SIMULATED_DISCLAIMER,
    }


def _build_campaign(vehicle, channel, price_drop=None, age_days=None, age_is_estimated=None):
    """Builds, stores, and returns one InventoryAdCampaign brief for a vehicle +
    channel. Shared by generate_campaign / price_drop_campaigns /
    aged_inventory_campaigns."""

    price = _vehicle_price(vehicle)
    copy = _baseline_copy(vehicle, channel, price, price_drop=price_drop, age_days=age_days)

    campaign_id = id_generator.generate(ID_PREFIX)
    now = _now()

    attributes = {
        "vehicle_id": vehicle.id,
        "vehicle_label": _vehicle_label(vehicle),
        "channel": channel,
        "headline": copy["headline"],
        "body": copy["body"],
        "disclaimer": copy["disclaimer"],
        "target_audience": _CHANNEL_AUDIENCE.get(channel, ""),
        "suggested_daily_budget": _suggested_daily_budget(channel, price),
        "price": price,
        "age_days": age_days,
        "age_is_estimated": age_is_estimated,
        "price_drop_from": price_drop[0] if price_drop else None,
        "price_drop_to": price_drop[1] if price_drop else None,
        "ai_generated": False,
        "created_by": "inventory_advertising_engine",
        "created_at": now,
        "basis": SIMULATED_BASIS,
    }

    entity = Entity(id=campaign_id, entity_type=INVENTORY_AD_CAMPAIGN, attributes=attributes)
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _campaign_brief(entity)


def _existing_campaign_for(vehicle_id, channel):
    for e in ledger.get_all().values():
        if e.entity_type != INVENTORY_AD_CAMPAIGN:
            continue
        if e.attributes.get("vehicle_id") == vehicle_id and e.attributes.get("channel") == channel:
            return e
    return None


def generate_campaign(vehicle_id, channel):
    """Builds and stores one campaign spec (headline, body, target_audience,
    suggested_daily_budget) for a real vehicle on a given channel. Raises
    ValueError on an unknown vehicle or an invalid channel."""

    _validate_channel(channel)
    vehicle = _get_vehicle_or_raise(vehicle_id)

    price_drop = None
    age_days = None
    age_is_estimated = None

    if channel == "price_drop":
        has_drop, from_price, to_price = _price_drop_info(vehicle)
        if has_drop:
            price_drop = (from_price, to_price)
    elif channel == "aged_inventory":
        age_days, age_is_estimated = _vehicle_age_days(vehicle)

    return _build_campaign(
        vehicle,
        channel,
        price_drop=price_drop,
        age_days=age_days,
        age_is_estimated=age_is_estimated,
    )


def list_campaigns(channel=None, vehicle_id=None, limit=500):
    """Every stored InventoryAdCampaign as a brief, most-recent-first, optionally
    filtered by channel or vehicle."""

    results = []
    for e in ledger.get_all().values():
        if e.entity_type != INVENTORY_AD_CAMPAIGN:
            continue
        if channel and e.attributes.get("channel") != channel:
            continue
        if vehicle_id and e.attributes.get("vehicle_id") != vehicle_id:
            continue
        results.append(e)

    results.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [_campaign_brief(e) for e in results[:limit]]


def price_drop_campaigns():
    """Auto-builds a `price_drop` campaign for every unsold vehicle with a real
    recorded price drop that doesn't already have one. Returns the list of built
    campaign briefs (empty if nothing qualifies)."""

    built = []
    for vehicle in _unsold_vehicles():
        has_drop, from_price, to_price = _price_drop_info(vehicle)
        if not has_drop:
            continue
        if _existing_campaign_for(vehicle.id, "price_drop"):
            continue
        built.append(
            _build_campaign(vehicle, "price_drop", price_drop=(from_price, to_price))
        )
    return built


def aged_inventory_campaigns(days_threshold=60):
    """Auto-builds an `aged_inventory` campaign for every unsold vehicle whose
    (real-if-available, otherwise clearly-estimated) listing age exceeds
    days_threshold and doesn't already have one. Returns the list of built
    campaign briefs (empty if nothing qualifies)."""

    built = []
    for vehicle in _unsold_vehicles():
        age_days, age_is_estimated = _vehicle_age_days(vehicle)
        if age_days is None or age_days <= days_threshold:
            continue
        if _existing_campaign_for(vehicle.id, "aged_inventory"):
            continue
        built.append(
            _build_campaign(
                vehicle,
                "aged_inventory",
                age_days=age_days,
                age_is_estimated=age_is_estimated,
            )
        )
    return built


def _estimated_reach(entity):
    """Clearly-labeled SIMULATED estimated daily reach for one campaign --
    daily budget times a per-channel impressions-per-dollar factor, nudged by a
    deterministic per-campaign seed so identical budgets don't all read the same
    round number. Never a real delivery metric."""

    channel = entity.attributes.get("channel")
    budget = entity.attributes.get("suggested_daily_budget") or 0
    factor = _CHANNEL_REACH_FACTOR.get(channel, 50)
    jitter = 0.85 + (_seed_int(entity.id, "reach", 31) / 100.0)  # 0.85 - 1.15
    return int(budget * factor * jitter)


def get_advertising_overview():
    """Real, live-computed rollup: campaign counts by channel (every channel
    seeded to 0 even when empty, the same convention core/communications_hub.py's
    by_channel / core/customer_journey.py's counts_by_stage established), total
    campaigns, and a clearly-labeled SIMULATED total estimated daily reach."""

    by_channel = {c: 0 for c in CHANNELS}
    total = 0
    total_reach = 0

    for e in ledger.get_all().values():
        if e.entity_type != INVENTORY_AD_CAMPAIGN:
            continue
        channel = e.attributes.get("channel")
        if channel in by_channel:
            by_channel[channel] += 1
        total += 1
        total_reach += _estimated_reach(e)

    return {
        "channels": list(CHANNELS),
        "total_campaigns": total,
        "campaigns_by_channel": by_channel,
        "estimated_total_daily_reach": total_reach,
        "basis": SIMULATED_BASIS,
        "disclaimer": SIMULATED_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# AI Ad Copy -- isolated, kill-switched OpenAI call, core/communications_hub.py's
# / core/customer_journey.py's established pattern exactly.
# ---------------------------------------------------------------------------

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

AD_COPY_SYSTEM_PROMPT = (
    "You are a paid-media copywriter for a car dealership, drafting a real, "
    "ready-to-edit ad for one specific vehicle on one specific channel (meta, "
    "google, retargeting, price_drop, or aged_inventory). Given the vehicle "
    "details, the channel, and its baseline audience, return ONLY a JSON object "
    "with exactly these keys: headline (<=9 words), body (2-3 sentences, never "
    "inventing a price/APR/offer beyond what was given), target_audience (<=25 "
    "words describing a real targeting approach), and disclaimer (a short honest "
    "disclaimer -- e.g. 'Price excludes tax, title, and dealer fees.' -- whenever "
    "a price is mentioned, else an empty string). Do not include any commentary "
    "outside the JSON object."
)


def _ad_copy_user_content(vehicle, channel, price):
    label = _vehicle_label(vehicle)
    price_text = f"${int(price):,}" if price else "not specified"
    audience = _CHANNEL_AUDIENCE.get(channel, "local car shoppers")
    return (
        f"Vehicle: {label}\n"
        f"Price: {price_text}\n"
        f"Channel: {channel}\n"
        f"Baseline audience: {audience}\n"
    )


def fallback_ad_copy(vehicle, channel):
    """Plain, non-AI ad copy -- the same rule-based baseline generate_campaign
    uses, reshaped to the generate_ad_copy return contract. Used when the AI call
    is disabled or fails, same pattern as core/communications_hub.py's
    fallback_summary()."""

    price = _vehicle_price(vehicle)

    price_drop = None
    age_days = None
    if channel == "price_drop":
        has_drop, from_price, to_price = _price_drop_info(vehicle)
        if has_drop:
            price_drop = (from_price, to_price)
    elif channel == "aged_inventory":
        age_days, _ = _vehicle_age_days(vehicle)

    copy = _baseline_copy(vehicle, channel, price, price_drop=price_drop, age_days=age_days)

    return {
        "headline": copy["headline"],
        "body": copy["body"],
        "target_audience": _CHANNEL_AUDIENCE.get(channel, ""),
        "disclaimer": copy["disclaimer"],
    }


def generate_ad_copy(vehicle_id, channel):
    """Real, isolated OpenAI call drafting ready-to-edit ad copy (headline / body
    / target_audience / disclaimer, plus an ai_generated flag) for one real
    vehicle on one channel. Raises ValueError on an unknown vehicle / invalid
    channel. On disabled/failure returns an honest rule-based fallback (never
    stored, since it's not a real AI result) so the caller always has usable copy.

    AI Management: checks the real 'inventory_ad_copy' kill switch
    (core/ai_management.py, inventory_ad_copy_enabled flag) before attempting --
    mirrors core/communications_hub.py's generate_ai_summary()."""

    _validate_channel(channel)
    vehicle = _get_vehicle_or_raise(vehicle_id)

    if not is_feature_enabled("inventory_ad_copy"):
        record_call_attempt("inventory_ad_copy", "blocked")
        fallback = fallback_ad_copy(vehicle, channel)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback

    price = _vehicle_price(vehicle)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": AD_COPY_SYSTEM_PROMPT},
                {"role": "user", "content": _ad_copy_user_content(vehicle, channel, price)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("inventory_ad_copy", "succeeded")
        raw = json.loads(response.choices[0].message.content)

        # Parse STRICTLY from the model's JSON -- an absent key falls back to an
        # empty string, never a guess.
        copy = {
            "headline": str(raw.get("headline") or ""),
            "body": str(raw.get("body") or ""),
            "target_audience": str(raw.get("target_audience") or ""),
            "disclaimer": str(raw.get("disclaimer") or ""),
            "ai_generated": True,
        }
        return copy

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("inventory_ad_copy", "fell_back", detail=str(exc))
        fallback = fallback_ad_copy(vehicle, channel)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback
