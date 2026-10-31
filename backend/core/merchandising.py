"""
core/merchandising.py -- Inventory department's "Merchandising" item
(Inventory rebuild, sixth slice). inventory.pdf's own framing: digital
inventory presentation. Missing Photos was already real (and honestly a
genuine 100% for years -- zero Image entities existed anywhere in this seed
graph despite the HAS_IMAGE relationship type existing since early
sessions). Missing Comments, VDP Health Scores, Inventory Feed Status,
Featured Vehicles, and Frontline Ready Units were all honest
`not_yet_tracked` gaps.

This slice is a deliberate MIX, same "simulate only a genuine external-world
gap, build everything else for real" rule Lot Management established:

REAL (an internal capability nobody had built, not external data):
  - Image upload -- `add_vehicle_image()` creates a real Image entity + a
    real HAS_IMAGE relationship, the first thing in this codebase to ever
    populate that relationship type. Closes the "zero photos" gap for real,
    not with a fabricated photo count.
  - Description/comments -- a real `description` attribute on Vehicle.
  - Featured Vehicles -- a real `featured` flag + toggle.
  - Frontline Ready Units -- reuses the same real lifecycle_status count
    core/inventory_overview.py already established for Overview, not a
    second computation.

SIMULATED (a genuine external-world gap -- no real VDP-analytics platform
or third-party listing-feed integration, e.g. Cars.com/AutoTrader/CarGurus,
is connected anywhere in this system):
  - VDP Health Score -- a composite that deliberately blends REAL inputs
    (has_photos, has_description, is_featured -- all real booleans this
    module now tracks) with one SIMULATED engagement proxy (a deterministic
    per-vehicle page-view estimate), same "real floor, simulated ceiling"
    shape core/pricing_desk.py's recommendation already established.
  - Feed Sync Status -- a SIMULATED per-vehicle sync state against a fixed
    list of real-world listing platforms this system has no actual
    connection to.
  - publish_to_feed() -- a SIMULATED action (a real recorded state
    transition, no real syndication happens), same honest-simulation
    precedent core/campaigns.py's activate_campaign() and
    core/social_posts.py's publish_post() already established.
"""

import hashlib
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import VEHICLE, IMAGE
from core.relationship_types import HAS_IMAGE
from core.relationships import Relationship
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_tab_data import _unsold_vehicles, _safe_float

SIMULATED_BASIS = "simulated_market_data"

FEED_PLATFORMS = ("Cars.com", "AutoTrader", "CarGurus", "CarFax Listings")
FEED_STATUSES = ("synced", "pending", "error")

_DISCLAIMER_VDP = (
    "VDP Health Score blends REAL inputs (has photos, has a description, is "
    "featured) with a SIMULATED page-view/engagement proxy -- no real "
    "VDP-analytics platform is connected in this system yet."
)

_DISCLAIMER_FEED = (
    "SIMULATED -- no real connection to Cars.com/AutoTrader/CarGurus/CarFax "
    "or any other third-party listing feed exists in this system yet. "
    "Deterministically generated per vehicle so the same vehicle reads the "
    "same simulated sync status on repeat calls."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def _seeded_int(seed_str, low, high):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest, 16) % span)


def _vehicle_images(vehicle_id):
    images = []
    for rel in ledger.get_relationships():
        if rel.source_id == vehicle_id and rel.relationship_type == HAS_IMAGE:
            img = ledger.get_entity(rel.target_id)
            if img and img.entity_type == IMAGE:
                images.append({"id": img.id, "url": img.attributes.get("URL"), "caption": img.attributes.get("Caption", "")})
    return images


def _vehicle_brief(v):
    price = _safe_float(v.attributes.get("Price"))
    return {
        "vehicle_id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "price": price or None,
    }


# --- Photos (REAL) ---

def add_vehicle_image(vehicle_id, image_url, added_by, caption=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    if not image_url or not image_url.strip():
        return {"error": "image_url is required"}
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(image_url.strip())
        if len(image_url) > 8192 or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return {"error": "Use an external image URL or upload to dealer-owned storage. Embedded image data is not stored."}
    except ValueError:
        return {"error": "Invalid image URL."}

    image_id = id_generator.generate("IMG")
    image = Entity(
        id=image_id,
        entity_type=IMAGE,
        attributes={
            "URL": image_url.strip(),
            "Caption": caption or "",
            "VehicleID": vehicle_id,
            "UploadedBy": added_by,
            "UploadedAt": _now(),
        },
    )
    ledger.add_entity(image)
    relationship = Relationship(
        source_id=vehicle_id, target_id=image_id, relationship_type=HAS_IMAGE,
        created_by=added_by, created_at=_now(),
    )
    ledger.add_relationship(relationship)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        if ledger.get_entity(image_id) is image:
            ledger.entities.pop(image_id, None)
        ledger.relationships[:] = [r for r in ledger.relationships if r is not relationship]
        return {"error": "Photo save was not confirmed. Refresh the vehicle before retrying; a cloud upload may already exist."}
    return {"vehicle_id": vehicle_id, "image": {"id": image_id, "url": image_url.strip(), "caption": caption}}


def list_vehicle_images(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    return {"vehicle_id": vehicle_id, "images": _vehicle_images(vehicle_id)}


# --- Description / Featured (REAL) ---


def _save_merchandising_attributes(vehicle, updates):
    missing = object()
    previous = {key: vehicle.attributes.get(key, missing) for key in updates}
    vehicle.attributes.update(updates)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        # Restore only fields still holding this write; preserve unrelated work.
        for key, attempted in updates.items():
            if vehicle.attributes.get(key, missing) != attempted:
                continue
            if previous[key] is missing:
                vehicle.attributes.pop(key, None)
            else:
                vehicle.attributes[key] = previous[key]
        return False
    return True

def update_description(vehicle_id, description, updated_by):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if not _save_merchandising_attributes(v, {"description": description,
            "description_updated_by": updated_by, "description_updated_at": _now()}):
        return {"error": "Description save was not confirmed. Refresh the vehicle before retrying."}
    return {"vehicle_id": vehicle_id, "description": description}


def set_featured(vehicle_id, featured, updated_by):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if not _save_merchandising_attributes(v, {"featured": bool(featured),
            "featured_updated_by": updated_by, "featured_updated_at": _now()}):
        return {"error": "Featured status save was not confirmed. Refresh the vehicle before retrying."}
    return {"vehicle_id": vehicle_id, "featured": bool(featured)}


def get_featured_vehicles():
    unsold = _unsold_vehicles()
    featured = [_vehicle_brief(v) for v in unsold if v.attributes.get("featured")]
    return {"count": len(featured), "vehicles": featured}


# --- VDP Health Score (REAL floor + SIMULATED ceiling) ---

def get_vdp_health(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    has_photos = len(_vehicle_images(vehicle_id)) > 0
    has_description = bool((v.attributes.get("description") or "").strip())
    is_featured = bool(v.attributes.get("featured"))

    simulated_views = _seeded_int(f"{vehicle_id}|vdp_views", 5, 400)
    simulated_lead_rate = round(_seeded_int(f"{vehicle_id}|vdp_leads", 0, 12) / 100.0, 3)

    real_points = (30 if has_photos else 0) + (25 if has_description else 0) + (10 if is_featured else 0)
    simulated_points = min(35, round(simulated_views / 400 * 35))
    score = real_points + simulated_points

    return {
        "vehicle_id": vehicle_id,
        "has_photos": has_photos,
        "has_description": has_description,
        "is_featured": is_featured,
        "simulated_page_views": simulated_views,
        "simulated_lead_conversion_rate": simulated_lead_rate,
        "health_score": score,
        "health_score_max": 100,
        "basis": "real+" + SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_VDP,
    }


# --- Feed Sync Status (SIMULATED) ---

def get_feed_status(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    feeds = []
    for platform in FEED_PLATFORMS:
        seed = f"{vehicle_id}|{platform}"
        # Weighted toward "synced" -- a real listing feed is synced most of
        # the time, occasionally pending a refresh, rarely erroring out.
        weight = _seeded_int(seed + "|weight", 0, 99)
        if weight < 75:
            status = "synced"
        elif weight < 90:
            status = "pending"
        else:
            status = "error"
        feeds.append({"platform": platform, "status": status})

    return {
        "vehicle_id": vehicle_id,
        "feeds": feeds,
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_FEED,
    }


def publish_to_feed(vehicle_id, platform, published_by):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    if platform not in FEED_PLATFORMS:
        return {"error": f"platform must be one of {FEED_PLATFORMS}"}

    log = v.attributes.get("feed_publish_log") or []
    entry = {"platform": platform, "published_by": published_by, "published_at": _now(), "simulated": True}
    log.append(entry)
    v.attributes["feed_publish_log"] = log
    save_graph(GRAPH_PATH)
    return {
        "vehicle_id": vehicle_id,
        "entry": entry,
        "basis": SIMULATED_BASIS,
        "disclaimer": "SIMULATED publish -- a real recorded action, but no real syndication to " + platform + " occurs in this system.",
    }


# --- Composed view + queue ---

def get_merchandising_view(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    return {
        "vehicle": _vehicle_brief(v),
        "images": _vehicle_images(vehicle_id),
        "description": v.attributes.get("description") or "",
        "featured": bool(v.attributes.get("featured")),
        "vdp_health": get_vdp_health(vehicle_id),
        "feed_status": get_feed_status(vehicle_id),
        "feed_publish_log": v.attributes.get("feed_publish_log") or [],
    }


def get_merchandising_queue(limit=25, offset=0):
    """Real worklist: unsold inventory ranked by worst REAL completeness
    first (no photos + no description sort to the top), each with its
    VDP Health Score attached."""
    unsold = _unsold_vehicles()

    def _completeness(v):
        has_photos = len(_vehicle_images(v.id)) > 0
        has_description = bool((v.attributes.get("description") or "").strip())
        return int(has_photos) + int(has_description)

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    ranked = sorted(unsold, key=lambda v: (_completeness(v), v.id))[offset:offset + limit]
    results = []
    for v in ranked:
        results.append({**_vehicle_brief(v), "vdp_health": get_vdp_health(v.id)})

    return {"count": len(results), "total": len(unsold), "offset": offset, "vehicles": results}
