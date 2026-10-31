"""
File Manager / DAM (Bumper parity, 2026-07-25). core/media_library.py is an image-only
curated library; core/documents.py stores raw file bytes but with a conservative allowlist
(no video/audio) and is scoped to per-record attachments. Bumper's File Manager is a
general digital-asset catalog across every media type. This module is that catalog: a
FileAsset entity records a multi-type file (image/video/audio/document/other) by metadata +
a hosted URL or storage reference, with free-form categories, tags, and search.

Catalog, not blob store: like media_library, a FileAsset references a URL/path rather than
holding bytes -- byte storage stays with core/documents.py. Categories are dealer-defined
free text (deliberately NOT media_library's fixed CATEGORY_LABELS vocabulary), so the DAM
can grow folders without touching that module's fixed set.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import FILE_ASSET
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


MEDIA_TYPES = ("image", "video", "audio", "document", "other")


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_file(file_id):
    e = ledger.get_entity(file_id)
    return e if e and e.entity_type == FILE_ASSET else None


def _all_files():
    return [e for e in ledger.get_all().values() if e.entity_type == FILE_ASSET and not e.attributes.get("deleted")]


def _brief(entity):
    a = entity.attributes
    return {
        "id": entity.id,
        "name": a.get("name"),
        "media_type": a.get("media_type"),
        "url": a.get("url"),
        "category": a.get("category"),
        "tags": a.get("tags", []),
        "size_bytes": a.get("size_bytes"),
        "content_type": a.get("content_type"),
        "description": a.get("description", ""),
        "uploaded_by": a.get("uploaded_by"),
        "created_at": a.get("created_at"),
    }


def add_file(name, media_type, url, uploaded_by, category="general", tags=None, size_bytes=None,
             content_type=None, description=""):
    if not (name or "").strip():
        return {"error": "name is required"}
    if media_type not in MEDIA_TYPES:
        return {"error": f"media_type must be one of {MEDIA_TYPES}"}
    if not (url or "").strip():
        return {"error": "url (or storage reference) is required"}
    entity = Entity(
        id=id_generator.generate("FASSET"),
        entity_type=FILE_ASSET,
        attributes={
            "name": name.strip(),
            "media_type": media_type,
            "url": url.strip(),
            "category": (category or "general").strip() or "general",
            "tags": list(tags or []),
            "size_bytes": size_bytes,
            "content_type": content_type,
            "description": description or "",
            "uploaded_by": uploaded_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _brief(entity)


def list_files(media_type=None, category=None, query=None):
    if media_type and media_type not in MEDIA_TYPES:
        return {"error": f"media_type must be one of {MEDIA_TYPES}"}
    out = _all_files()
    if media_type:
        out = [f for f in out if f.attributes.get("media_type") == media_type]
    if category:
        out = [f for f in out if (f.attributes.get("category") or "").lower() == category.lower()]
    if query:
        q = query.lower()
        out = [
            f for f in out
            if q in (f.attributes.get("name", "") + " " + f.attributes.get("description", "")
                     + " " + " ".join(f.attributes.get("tags", []))).lower()
        ]
    return [_brief(f) for f in sorted(out, key=lambda f: f.attributes.get("created_at", ""), reverse=True)]


def update_file(file_id, patch):
    f = get_file(file_id)
    if not f:
        return {"error": "File not found"}
    allowed = {"name", "category", "tags", "description", "url", "media_type", "content_type", "size_bytes"}
    if "media_type" in (patch or {}) and patch["media_type"] not in MEDIA_TYPES:
        return {"error": f"media_type must be one of {MEDIA_TYPES}"}
    for k, v in (patch or {}).items():
        if k in allowed:
            f.attributes[k] = v
    f.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return _brief(f)


def remove_file(file_id):
    f = get_file(file_id)
    if not f:
        return {"error": "File not found"}
    f.attributes["deleted"] = True
    f.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"removed": file_id}


def list_categories():
    counts = {}
    for f in _all_files():
        cat = f.attributes.get("category") or "general"
        counts[cat] = counts.get(cat, 0) + 1
    return [{"category": c, "count": n} for c, n in sorted(counts.items())]


def storage_summary():
    """Counts + total bytes per media type -- the DAM header stats."""
    by_type = {mt: {"count": 0, "bytes": 0} for mt in MEDIA_TYPES}
    for f in _all_files():
        mt = f.attributes.get("media_type", "other")
        if mt not in by_type:
            mt = "other"
        by_type[mt]["count"] += 1
        by_type[mt]["bytes"] += f.attributes.get("size_bytes") or 0
    total = sum(v["count"] for v in by_type.values())
    return {"total": total, "by_media_type": by_type}
