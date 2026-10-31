"""Review snapshots and serialized writes for the existing Website ledger.

The lock matches the backend's single-process in-memory tenant graph. It is not a
distributed database lock; multi-worker deployments need a transactional store.
"""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
import json
from threading import RLock

WEBSITE_WRITE_LOCK = RLock()
CONTENT_KEYS = ("name", "mode", "pages", "admin_settings", "studio_config", "vehicle_pages")


def content_snapshot(website):
    return deepcopy({key: website.attributes.get(key) for key in CONTENT_KEYS})


def fingerprint(snapshot):
    return sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def freeze_review(website):
    snapshot = content_snapshot(website)
    website.attributes["review_snapshot"] = snapshot
    website.attributes["review_fingerprint"] = fingerprint(snapshot)


def review_is_current(website):
    snapshot = website.attributes.get("review_snapshot")
    expected = website.attributes.get("review_fingerprint")
    return bool(snapshot and expected and fingerprint(snapshot) == expected and fingerprint(content_snapshot(website)) == expected)


def serialized_website_write(function):
    @wraps(function)
    def serialized(*args, **kwargs):
        with WEBSITE_WRITE_LOCK:
            return function(*args, **kwargs)
    return serialized


def studio_content_write(function):
    """Block every core content mutation of a reviewed/published studio site."""
    @wraps(function)
    def guarded(website_id, *args, **kwargs):
        from core.websites import get_website
        with WEBSITE_WRITE_LOCK:
            website = get_website(website_id)
            if website and website.attributes.get("studio_config") and website.attributes.get("status") not in ("draft", "rejected"):
                return {"error": "This reviewed website version is read-only. Return it to a draft before editing."}
            return function(website_id, *args, **kwargs)
    return guarded



def has_public_version(website):
    if not website:
        return False
    if website.attributes.get("status") == "published":
        return True
    snapshot = website.attributes.get("published_snapshot")
    return bool(website.attributes.get("studio_config") and snapshot and website.attributes.get("published_fingerprint") == fingerprint(snapshot))


def public_version(website):
    """Detach approved content from an in-progress successor draft."""
    if not has_public_version(website):
        return None
    from core.entities import Entity
    attrs = deepcopy(website.attributes)
    if attrs.get("published_snapshot"):
        attrs.update(deepcopy(attrs["published_snapshot"]))
        attrs["status"] = "published"
        attrs["updated_at"] = attrs.get("published_at") or attrs.get("updated_at")
    return Entity(id=website.id, entity_type=website.entity_type, attributes=attrs)


def rollback_website_transition(function):
    """Keep an unsuccessful review transition out of the in-memory public view."""
    @wraps(function)
    def guarded(website_id, *args, **kwargs):
        from core.websites import get_website
        with WEBSITE_WRITE_LOCK:
            site = get_website(website_id)
            before = deepcopy(site.attributes) if site else None
            try:
                return function(website_id, *args, **kwargs)
            except Exception:
                if site and before is not None:
                    site.attributes.clear()
                    site.attributes.update(before)
                raise
    return guarded
