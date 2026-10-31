"""
core/media_library.py -- the dealership-wide shared image asset library (2026-07-23).
Sam: "We also need to have a shared image asset file system that's accessible from all
marketing related tools. This includes OEM approved images, logos, dealership logos and
branding, as well as inventory."

Graph-native like everything else -- a library image is an ordinary IMAGE entity in the
same core.ledger every other entity lives in (no new parallel media store), reusing the
IMAGE entity type + "IMG" id prefix that core/merchandising.py's vehicle photos already
use. The one distinguishing attribute is Scope="library": these are dealership-wide
assets not tied to a single vehicle or a single website's own image_library, so every
marketing tool (email builder, website builder, social, asset design) can pick from the
same shared pool.

Categories are a small fixed vocabulary Sam named. "inventory" is deliberately NOT a
manually-uploaded bucket -- inventory images already live in the graph as vehicle photos
(IMAGE entities linked to a Vehicle via the HAS_IMAGE relationship, core/merchandising.py).
list_library_images() MERGES those live vehicle photos into the "inventory" category at
read time rather than copying them, so the library always reflects the real, current
inventory photos with zero duplication -- the same "no parallel copy, render from the
graph" rule core/websites.py's inventory_grid section already follows.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import IMAGE, VEHICLE
from core.relationship_types import HAS_IMAGE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


# The fixed category vocabulary Sam named. "inventory" is a live, read-only view of
# vehicle photos (see module docstring) -- it can't be uploaded into directly.
CATEGORY_LABELS = {
    "oem_approved": "OEM Approved",
    "logos": "Logos",
    "dealership_branding": "Dealership Branding",
    "inventory": "Inventory",
    "general": "General",
}
LIBRARY_CATEGORIES = tuple(CATEGORY_LABELS.keys())
# Categories an admin/marketer can actually upload an image into (inventory excluded --
# those come from the vehicles themselves).
UPLOADABLE_CATEGORIES = ("oem_approved", "logos", "dealership_branding", "general")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _library_brief(entity):
    """One shared-library IMAGE entity → the flat dict the picker/board renders."""
    a = entity.attributes
    return {
        "id": entity.id,
        "url": a.get("URL"),
        "name": a.get("Caption") or "",
        "category": a.get("LibraryCategory") or "general",
        "tags": list(a.get("Tags") or []),
        "scope": "library",
        "uploaded_by": a.get("UploadedBy"),
        "created_at": a.get("UploadedAt"),
        "removable": True,
    }


def _vehicle_label(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    a = v.attributes
    parts = [a.get("Year"), a.get("Make"), a.get("Model")]
    label = " ".join(str(p) for p in parts if p)
    stock = a.get("StockNumber")
    return f"{label} (#{stock})" if stock else (label or None)


def _live_inventory_images(query=None):
    """Every vehicle photo currently in the graph (IMAGE linked to a Vehicle via
    HAS_IMAGE), surfaced under the 'inventory' category. Read-only, live -- never a
    stored copy. Deduped by image id."""

    q = (query or "").strip().lower()
    seen = set()
    out = []
    for rel in ledger.get_relationships():
        if rel.relationship_type != HAS_IMAGE:
            continue
        img = ledger.get_entity(rel.target_id)
        if not img or img.entity_type != IMAGE or img.id in seen:
            continue
        # A dealership-wide library image would never also be a vehicle photo, but
        # guard anyway so the two views never double-count.
        if img.attributes.get("Scope") == "library":
            continue
        seen.add(img.id)
        vehicle_label = _vehicle_label(rel.source_id)
        name = img.attributes.get("Caption") or vehicle_label or "Vehicle photo"
        if q and q not in name.lower() and q not in (vehicle_label or "").lower():
            continue
        out.append({
            "id": img.id,
            "url": img.attributes.get("URL"),
            "name": name,
            "category": "inventory",
            "tags": [t for t in [vehicle_label] if t],
            "scope": "inventory",
            "vehicle_id": rel.source_id,
            "vehicle": vehicle_label,
            "uploaded_by": img.attributes.get("UploadedBy"),
            "created_at": img.attributes.get("UploadedAt"),
            "removable": False,  # managed on the vehicle, not here
        })
    return out


def list_categories():
    """Every category with its label and a live count -- for the picker's tab row."""
    images = list_library_images()
    counts = {}
    for img in images:
        counts[img["category"]] = counts.get(img["category"], 0) + 1
    return [
        {"key": key, "label": label, "count": counts.get(key, 0)}
        for key, label in CATEGORY_LABELS.items()
    ]


def list_library_images(category=None, query=None):
    """The shared library. Dealership-wide uploaded assets (Scope='library') PLUS live
    vehicle photos merged in under 'inventory'. Optional category filter + a name/tag
    substring search. Most-recent-first."""

    if category is not None and category not in LIBRARY_CATEGORIES:
        return {"error": f"Unknown category '{category}'. Valid: {', '.join(LIBRARY_CATEGORIES)}."}

    q = (query or "").strip().lower()
    results = []

    # Dealership-wide uploaded library images.
    if category != "inventory":
        for entity in ledger.get_all().values():
            if entity.entity_type != IMAGE or entity.attributes.get("Scope") != "library":
                continue
            brief = _library_brief(entity)
            if category and brief["category"] != category:
                continue
            if q:
                hay = (brief["name"] + " " + " ".join(brief["tags"])).lower()
                if q not in hay:
                    continue
            results.append(brief)

    # Live inventory photos, merged in.
    if category in (None, "inventory"):
        results.extend(_live_inventory_images(query=query))

    results.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return results


def add_library_image(url, name, category, uploaded_by, tags=None, *, upload_key=None):
    """Add a dealership-wide image to the shared library (OEM art, a logo, branding).
    Returns the created image dict or a real {"error": ...}."""

    if not url or not str(url).strip():
        return {"error": "An image URL is required."}

    category = category or "general"
    if category not in UPLOADABLE_CATEGORIES:
        if category == "inventory":
            return {"error": "Inventory images come from vehicle photos; add them on the vehicle, not here."}
        return {"error": f"Unknown category '{category}'. Valid: {', '.join(UPLOADABLE_CATEGORIES)}."}

    clean_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

    image_id = id_generator.generate("IMG")
    image = Entity(
        id=image_id,
        entity_type=IMAGE,
        attributes={
            "URL": str(url).strip(),
            "Caption": str(name or "").strip(),
            "LibraryCategory": category,
            "Tags": clean_tags,
            "Scope": "library",
            "UploadedBy": uploaded_by,
            "UploadedAt": _now(),
        },
    )
    if upload_key is not None:
        image.attributes["PublicUploadKey"] = upload_key
    ledger.add_entity(image)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        ledger.entities.pop(image_id, None)
        raise
    return _library_brief(image)


def remove_library_image(image_id):
    """Delete a dealership-wide library image. Refuses to touch vehicle photos (those
    are managed on the vehicle). Returns {"removed": id} or a real {"error": ...}."""

    entity = ledger.get_entity(image_id)
    if not entity or entity.entity_type != IMAGE:
        return {"error": f"No image found with id {image_id}."}
    if entity.attributes.get("Scope") != "library":
        return {"error": "That image is a vehicle photo, not a shared-library asset; manage it on the vehicle."}

    # Same hard-delete convention as core/coaching.py / core/smart_audiences.py etc.
    del ledger.entities[image_id]
    save_graph(GRAPH_PATH)
    return {"removed": image_id}
