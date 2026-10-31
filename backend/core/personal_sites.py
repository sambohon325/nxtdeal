"""
Personal URL microsites (2026-07-15/16, session 85) -- the 'personal url functionality
that takes the look and feel of the website and can be deployed by the sales rep or
marketing / events' piece of Sam's Website Builder overhaul.

Scoping decision, made autonomously after an AskUserQuestion tool call failed
(AbortError) and was not retried -- documented here rather than silently assumed: a
PersonalSite is ONE personal landing page per employee (headline/bio/photo/contact/
featured vehicles/a contact form), not a full multi-page mirror of the dealership site.
This matches how real personal-URL products in this space actually work (an agent bio/
landing page, not a whole second website per employee) and keeps the build scoped. If
Sam wants a fuller per-employee site later, this module's shape (one entity, a fixed
set of personalization fields) is the piece that would need to grow, not the surrounding
architecture.

'Takes the look and feel of the website' is implemented as a LIVE borrow, not a copy:
get_personal_site_rendered() reads its `parent_website_id` Website's admin_settings
(branding_mode/oem_name/oem_logo_url) live at render time, same no-parallel-copy rule
as core/websites.py's inventory/car-builder sections. Featured vehicles are resolved
the same way -- a list of Vehicle IDs, resolved to real live attributes at render time,
never a stored snapshot.

No approval workflow here (unlike core/websites.py's Website, which needs MARKETING/
ADMIN sign-off before it's public) -- Sam's framing was self-service ('deployed by the
sales rep'), so an employee can create and activate their own personal site
immediately; core/personal_sites_api.py's ACL still lets ADMIN manage/deactivate any
employee's page.
"""

import re
from urllib.parse import urlsplit
from copy import deepcopy
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import PERSONAL_SITE, WEBSITE, VEHICLE, WEBSITE_ANALYTICS_EVENT
from core.lead_intake import create_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 85) --
# every real personal site ever created, edited, or activated, and every lead its
# contact form ever captured, had been silently discarded on server restart. Fixed
# below: every mutating function now saves directly. record_personal_site_view() is
# left as the same deliberate high-frequency exception core/websites.py's
# record_page_view() already established -- see that function's own comment.

STATUSES = ["draft", "active", "inactive"]

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$")

PERSONALIZATION_FIELDS = [
    "headline",
    "subheadline",
    "bio",
    "photo_url",
    "phone",
    "email",
    "cta_text",
    "calendar_link",
    "review_link",
    "featured_vehicle_ids",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_personal_sites():
    return [e for e in ledger.get_all().values() if e.entity_type == PERSONAL_SITE]


def _log_history(site, action, by, notes=None):
    site.attributes.setdefault("history", []).append({
        "action": action,
        "by": by,
        "at": _now(),
        "notes": notes,
    })


def _slugify_ok(slug):
    return bool(slug) and bool(SLUG_PATTERN.match(slug.lower()))


def slug_available(slug, exclude_site_id=None):

    slug = (slug or "").strip().lower()

    for site in _all_personal_sites():

        if site.id == exclude_site_id:
            continue

        if (site.attributes.get("slug") or "").lower() == slug:
            return False

    return True


def create_personal_site(employee_id, slug, parent_website_id=None):

    slug = (slug or "").strip().lower()

    if not _slugify_ok(slug):
        return {"error": "Slug must be lowercase letters/numbers/hyphens, 2-50 characters, no leading/trailing hyphen"}

    if not slug_available(slug):
        return {"error": f"Slug '{slug}' is already taken"}

    if parent_website_id:

        parent = ledger.get_entity(parent_website_id)

        if not parent or parent.entity_type != WEBSITE:
            return {"error": "parent_website_id does not refer to a real Website"}

    site_id = id_generator.generate("PSITE")

    entity = Entity(
        id=site_id,
        entity_type=PERSONAL_SITE,
        attributes={
            "employee_id": employee_id,
            "parent_website_id": parent_website_id,
            "slug": slug,
            "status": "draft",
            "headline": None,
            "subheadline": None,
            "bio": None,
            "photo_url": None,
            "phone": None,
            "email": None,
            "cta_text": "Get In Touch",
            "calendar_link": None,
            "review_link": None,
            "featured_vehicle_ids": [],
            "history": [],
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    _log_history(entity, "created", employee_id, notes=f"slug={slug}")

    previous = ledger.get_entity(site_id)
    ledger.add_entity(entity)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        # Do not leave an unsaved page reserving its slug after a failed create.
        # Keep the consumed ID; restoring it could collide with later operations.
        if ledger.get_entity(site_id) is entity:
            if previous is None:
                ledger.entities.pop(site_id, None)
            else:
                ledger.entities[site_id] = previous
        raise

    return entity


def get_personal_site(site_id):

    entity = ledger.get_entity(site_id)

    if entity and entity.entity_type == PERSONAL_SITE:
        entity.attributes.setdefault("featured_vehicle_ids", [])
        entity.attributes.setdefault("history", [])
        return entity

    return None


def get_personal_site_by_slug(slug):

    slug = (slug or "").strip().lower()

    for site in _all_personal_sites():
        if (site.attributes.get("slug") or "").lower() == slug:
            return site

    return None


def update_personal_site(site_id, patch, by=None):
    """Merges only the whitelisted personalization fields -- employee_id/slug/status/
    parent_website_id are changed through their own dedicated functions, never this
    generic patch, same 'flat dict, whitelisted patch loop' shape as
    core/websites.py's update_admin_settings()."""

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not isinstance(patch, dict):
        return {"error": "Personalization patch must be an object"}

    if "review_link" in patch:
        link = patch["review_link"]
        if link not in (None, ""):
            try:
                if not isinstance(link, str) or len(link) > 2048 or re.search(r"[\x00-\x20\x7f\\]", link):
                    raise ValueError()
                parsed = urlsplit(link)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                    raise ValueError()
                parsed.port  # Reject malformed ports before publishing the destination.
            except ValueError:
                return {"error": "Review URL must be HTTPS without credentials or whitespace"}
        else:
            patch = {**patch, "review_link": None}

    if "featured_vehicle_ids" in patch:
        ids = patch["featured_vehicle_ids"]
        if (not isinstance(ids, list) or len(ids) > 24
                or any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in ids)):
            return {"error": "Featured vehicles must be a list of up to 24 nonempty vehicle IDs"}
        patch = {**patch, "featured_vehicle_ids": list(dict.fromkeys(ids))}

    previous = deepcopy(site.attributes)
    changed = []

    for key in PERSONALIZATION_FIELDS:
        if key in (patch or {}):
            site.attributes[key] = patch[key]
            changed.append(key)

    if changed:
        _log_history(site, "updated", by, notes=", ".join(changed))
        site.attributes["updated_at"] = _now()
        try:
            save_graph(GRAPH_PATH)
        except Exception:
            site.attributes = previous
            raise

    return site


def set_slug(site_id, new_slug, by=None):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    new_slug = (new_slug or "").strip().lower()

    if not _slugify_ok(new_slug):
        return {"error": "Slug must be lowercase letters/numbers/hyphens, 2-50 characters, no leading/trailing hyphen"}

    if not slug_available(new_slug, exclude_site_id=site_id):
        return {"error": f"Slug '{new_slug}' is already taken"}

    previous = deepcopy(site.attributes)
    old_slug = site.attributes.get("slug")
    site.attributes["slug"] = new_slug
    _log_history(site, "slug_changed", by, notes=f"{old_slug} -> {new_slug}")
    site.attributes["updated_at"] = _now()

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        site.attributes = previous
        raise

    return site


def set_parent_website(site_id, parent_website_id, by=None):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if parent_website_id:

        parent = ledger.get_entity(parent_website_id)

        if not parent or parent.entity_type != WEBSITE:
            return {"error": "parent_website_id does not refer to a real Website"}

    previous = deepcopy(site.attributes)
    site.attributes["parent_website_id"] = parent_website_id
    _log_history(site, "parent_website_changed", by, notes=parent_website_id)
    site.attributes["updated_at"] = _now()

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        site.attributes = previous
        raise

    return site


def set_personal_site_status(site_id, status, by=None):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if status not in STATUSES:
        return {"error": f"Unknown status '{status}' -- must be one of {STATUSES}"}

    previous = deepcopy(site.attributes)
    site.attributes["status"] = status
    _log_history(site, "status_changed", by, notes=status)
    site.attributes["updated_at"] = _now()

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        site.attributes = previous
        raise

    return site


def _resolve_featured_vehicles(vehicle_ids):
    """Live resolution, no parallel copy -- same rule as core/websites.py's
    get_live_inventory(). Skips any id that no longer resolves to a real, unsold
    Vehicle (sold or deleted since being featured) rather than showing stale data."""

    results = []

    if not isinstance(vehicle_ids, list):
        return results

    seen = set()
    for vehicle_id in vehicle_ids[:24]:
        if not isinstance(vehicle_id, str) or vehicle_id in seen:
            continue
        seen.add(vehicle_id)

        vehicle = ledger.get_entity(vehicle_id)

        if not vehicle or vehicle.entity_type != VEHICLE or vehicle.attributes.get("DateSold"):
            continue

        results.append({
            "id": vehicle.id,
            "year": vehicle.attributes.get("Year"),
            "make": vehicle.attributes.get("Make"),
            "model": vehicle.attributes.get("Model"),
            "trim": vehicle.attributes.get("Trim"),
            "price": vehicle.attributes.get("Price"),
            "mileage": vehicle.attributes.get("Mileage"),
        })

    return results


def get_personal_site_rendered(site_id):
    """Live-borrows the parent Website's branding (if any) rather than copying it --
    'takes the look and feel of the website' -- and resolves featured vehicles live."""

    site = get_personal_site(site_id)

    if not site:
        return None

    branding = {"branding_mode": "independent", "oem_name": None, "oem_logo_url": None}

    parent_id = site.attributes.get("parent_website_id")

    if parent_id:

        parent = ledger.get_entity(parent_id)

        if parent and parent.entity_type == WEBSITE:

            settings = parent.attributes.get("admin_settings") or {}

            branding = {
                "branding_mode": settings.get("branding_mode", "independent"),
                "oem_name": settings.get("oem_name"),
                "oem_logo_url": settings.get("oem_logo_url"),
            }

    return {
        "id": site.id,
        **{k: v for k, v in site.attributes.items() if k != "featured_vehicle_ids"},
        "featured_vehicles": _resolve_featured_vehicles(site.attributes.get("featured_vehicle_ids")),
        "branding": branding,
    }


def record_personal_site_view(site_id, viewer_ref=None):
    """Reuses the same WebsiteAnalyticsEvent entity type core/websites.py's
    record_page_view() writes -- PageKey is fixed to 'personal_site' and WebsiteID
    actually holds the PersonalSite's id, distinguishable from a real Website's page
    views by that fixed PageKey value rather than a second event type."""

    event_id = id_generator.generate("PVIEW")

    event = Entity(
        id=event_id,
        entity_type=WEBSITE_ANALYTICS_EVENT,
        attributes={
            "WebsiteID": site_id,
            "PageKey": "personal_site",
            "ViewerRef": viewer_ref,
            "Timestamp": _now(),
        },
    )

    ledger.add_entity(event)

    # Deliberate exception, same reasoning as core/websites.py's record_page_view() --
    # a high-frequency public view-log path, not saved per-event.

    return event


def get_personal_site_analytics(site_id):

    events = [
        e for e in ledger.get_all().values()
        if e.entity_type == WEBSITE_ANALYTICS_EVENT
        and e.attributes.get("WebsiteID") == site_id
        and e.attributes.get("PageKey") == "personal_site"
    ]

    by_day = {}

    for event in events:
        day = (event.attributes.get("Timestamp") or "")[:10]
        by_day[day] = by_day.get(day, 0) + 1

    return {
        "personal_site_id": site_id,
        "total_views": len(events),
        "by_day": dict(sorted(by_day.items())),
    }


def submit_personal_site_contact_form(site_id, name, email=None, phone=None, message=None):
    """The actual CRM tie for personal URLs -- a lead captured on a rep's own page is
    assigned DIRECTLY to that rep (site.attributes['employee_id']), via
    core/lead_intake.py's create_lead(), same 'Website' source as the main site's
    contact form."""

    site = get_personal_site(site_id)

    if not site or site.attributes.get("status") != "active":
        return {"error": "Personal site not found"}

    name = (name or "").strip()
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None
    if not name or not (email or phone):
        return {"error": "name and at least one of email/phone are required"}

    employee_id = site.attributes.get("employee_id")

    if not employee_id:
        return {"error": "This page has no owner to route the lead to"}

    parts = name.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    lead = create_lead(
        created_by=employee_id,
        first_name=first_name,
        last_name=last_name,
        source="Website",
        phone=phone,
        email=email,
        personal_site_id=site_id,
        message=message or "",
    )

    previous = deepcopy(site.attributes)
    _log_history(site, "contact_form_submitted", None, notes=f"lead={lead.id}")
    site.attributes["updated_at"] = _now()

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        # Intake already confirmed the durable lead, including page and message.
        # A secondary history failure must not tell the visitor to submit again.
        site.attributes = previous
        return {"lead_id": lead.id, "assigned_to": employee_id, "history_recorded": False}

    return {"lead_id": lead.id, "assigned_to": employee_id, "history_recorded": True}


def list_personal_sites(employee_id=None, status=None):

    sites = _all_personal_sites()

    if employee_id:
        sites = [s for s in sites if s.attributes.get("employee_id") == employee_id]

    if status:
        sites = [s for s in sites if s.attributes.get("status") == status]

    sites.sort(key=lambda s: (s.attributes.get("created_at", ""), s.id), reverse=True)

    return sites
