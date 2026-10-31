"""
Social media post builder + content calendar (session 83). Sam: "we need to have an
appliaction like hootsuit where you can post to facebook, instagram, X, LinkedIn,
tiktok, etc with a social content calendar... a built in social media post builder
that includes dropping in inventory."

A SocialPost is an ordinary graph entity (core/entity_types.py's SOCIAL_POST), tied to
the Employee who built it and optionally to real Vehicle entities via
`linked_vehicle_ids` -- only the id is stored, never a copied snapshot of the vehicle's
price/photo, same no-parallel-inventory-copy rule core/websites.py's inventory_grid
section and car-builder configurator already established (resolve_linked_vehicles()
below queries the graph live).

This sandbox has no real path to the Facebook/Instagram/X/LinkedIn/TikTok APIs, so
"publishing" is an honestly-labeled SIMULATED action -- publish_post() stamps real
status/timestamps on a real graph record, exactly like core/campaigns.py's
activate_campaign() simulates a send. No content actually reaches those platforms.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import SOCIAL_POST, VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 83) --
# every real social post ever created, edited, published, or cancelled had been
# silently discarded on server restart. Fixed below: every mutating function now saves
# directly.

PLATFORMS = ["facebook", "instagram", "x", "linkedin", "tiktok"]

STATUSES = ["draft", "scheduled", "published", "cancelled"]

_EDITABLE_FIELDS = {"platform", "content", "media_url", "linked_vehicle_ids", "scheduled_time", "target_date"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_platforms():
    return list(PLATFORMS)


def create_post(created_by, platform, content, media_url=None, linked_vehicle_ids=None, scheduled_time=None, target_date=None):
    """target_date (plain 'YYYY-MM-DD', optional) is the content-calendar day a draft is
    planned for -- separate from scheduled_time, which is the real auto-publish
    timestamp. A post can carry a target_date and still be status='draft' (an idea
    parked on a specific day, not queued to send); scheduled_time is what actually
    promotes a post to 'scheduled', unchanged from before. This is what lets
    get_calendar() below show drafts on the day they were planned for, not just
    posts that are already scheduled/published."""

    if platform not in PLATFORMS:
        return {"error": f"Unknown platform '{platform}' -- choose one of {PLATFORMS}"}

    post_id = id_generator.generate("SOC")

    entity = Entity(
        id=post_id,
        entity_type=SOCIAL_POST,
        attributes={
            "platform": platform,
            "content": content or "",
            "media_url": media_url,
            "linked_vehicle_ids": [v for v in (linked_vehicle_ids or []) if ledger.get_entity(v) and ledger.get_entity(v).entity_type == VEHICLE],
            "status": "scheduled" if scheduled_time else "draft",
            "scheduled_time": scheduled_time,
            "target_date": target_date,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "published_at": None,
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_post(post_id):

    entity = ledger.get_entity(post_id)

    if entity and entity.entity_type == SOCIAL_POST:
        return entity

    return None


def update_post(post_id, patch):
    """Whole-patch, same discipline as core/campaigns.py's update_campaign() --
    content/scheduling fields only, status transitions stay exclusively gated behind
    publish_post()/cancel_post() below."""

    entity = get_post(post_id)

    if not entity:
        return None

    for key, value in (patch or {}).items():

        if key not in _EDITABLE_FIELDS:
            continue

        if key == "linked_vehicle_ids":
            value = [v for v in (value or []) if ledger.get_entity(v) and ledger.get_entity(v).entity_type == VEHICLE]

        entity.attributes[key] = value

    if patch.get("scheduled_time") and entity.attributes.get("status") == "draft":
        entity.attributes["status"] = "scheduled"

    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def publish_post(post_id):
    """SIMULATED publish -- see module docstring. Real graph state, no real platform
    delivery."""

    entity = get_post(post_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("draft", "scheduled"):
        return {"error": f"Post is already '{entity.attributes.get('status')}'"}

    entity.attributes["status"] = "published"
    entity.attributes["published_at"] = _now()
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def cancel_post(post_id):

    entity = get_post(post_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("draft", "scheduled"):
        return {"error": f"Post is already '{entity.attributes.get('status')}'"}

    entity.attributes["status"] = "cancelled"
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def list_posts(platform=None, status=None, created_by=None):

    posts = [e for e in ledger.get_all().values() if e.entity_type == SOCIAL_POST]

    if platform:
        posts = [p for p in posts if p.attributes.get("platform") == platform]

    if status:
        posts = [p for p in posts if p.attributes.get("status") == status]

    if created_by:
        posts = [p for p in posts if p.attributes.get("created_by") == created_by]

    posts.sort(key=lambda p: p.attributes.get("scheduled_time") or p.attributes.get("created_at") or "", reverse=True)

    return posts


def get_calendar(start_date=None, end_date=None):
    """The content calendar -- every draft/scheduled/published post (never cancelled)
    that has a resolvable calendar day, grouped by date, within [start_date, end_date]
    (inclusive, ISO date strings). The calendar day is scheduled_time's date if the post
    is actually scheduled, published_at's date if it already went out, otherwise
    target_date -- the day a draft was planned for on the calendar even though it isn't
    queued to send yet. No stored calendar entity -- computed live off real SocialPost
    records, same "no parallel store" rule as every other menu-item aggregate in this
    codebase."""

    posts = [
        p for p in ledger.get_all().values()
        if p.entity_type == SOCIAL_POST and p.attributes.get("status") in ("draft", "scheduled", "published")
    ]

    by_date = {}
    counted = 0

    for p in posts:

        when = p.attributes.get("scheduled_time") or p.attributes.get("published_at") or p.attributes.get("target_date")

        if not when:
            continue

        date_key = when[:10]

        if start_date and date_key < start_date:
            continue

        if end_date and date_key > end_date:
            continue

        counted += 1

        by_date.setdefault(date_key, []).append({
            "id": p.id,
            "platform": p.attributes.get("platform"),
            "content": (p.attributes.get("content") or "")[:120],
            "status": p.attributes.get("status"),
            "scheduled_time": p.attributes.get("scheduled_time"),
            "target_date": p.attributes.get("target_date"),
        })

    return {"by_date": by_date, "total": counted}


def resolve_linked_vehicles(post_id):
    """Live-resolves a post's linked_vehicle_ids against real Vehicle entities at read
    time (id/year/make/model/trim/price/image), same no-parallel-inventory-copy rule as
    core/websites.py's get_live_inventory()."""

    entity = get_post(post_id)

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


def get_vehicle_brief(vehicle_id):
    """Resolves a single real Vehicle id to the same brief shape
    resolve_linked_vehicles()/search_inventory_for_post() already use -- the AI
    caption wizard's grounding lookup (session 113 follow-up). Returns None for a
    missing id or a non-Vehicle entity, never a fabricated stand-in."""

    v = ledger.get_entity(vehicle_id)

    if not v or v.entity_type != VEHICLE:
        return None

    return {
        "id": v.id,
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "trim": v.attributes.get("Trim"),
        "price": v.attributes.get("Price"),
    }


def search_inventory_for_post(query=None, limit=20):
    """The post builder's "drop in inventory" picker -- real, live, unsold-only Vehicle
    search (same _unsold_vehicles()-shape filter as core/websites.py, kept as its own
    small query here rather than importing a private helper across modules)."""

    q = (query or "").strip().lower()

    results = []

    for v in ledger.get_all().values():

        if v.entity_type != VEHICLE or v.attributes.get("DateSold"):
            continue

        haystack = " ".join(str(v.attributes.get(k, "")) for k in ("Year", "Make", "Model", "Trim", "VIN", "StockNumber")).lower()

        if q and q not in haystack:
            continue

        results.append({
            "id": v.id,
            "year": v.attributes.get("Year"),
            "make": v.attributes.get("Make"),
            "model": v.attributes.get("Model"),
            "trim": v.attributes.get("Trim"),
            "price": v.attributes.get("Price"),
        })

        if len(results) >= limit:
            break

    return results
