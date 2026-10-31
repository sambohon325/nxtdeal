"""Validated design settings on the existing tenant-scoped Website draft.

This module never creates inventory, leads, or a second website record. Publication
still belongs to websites_api and its existing reviewer/compliance gates.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse

from core import websites
from core.websites_api import _can_edit_content, _serialize_website
from core.website_revisions import serialized_website_write


def catalogue():
    return json.loads((Path(__file__).parent / "website_studio_catalogue.json").read_text(encoding="utf-8"))


def _text(value, label, limit=4000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} must be text of at most {limit} characters")
    return value.strip()


def _url(value, *, artwork=False):
    value = _text(value, "Image or social URL", 2048)
    if not value:
        return value
    if artwork:
        from core.media_uploads import KEY_PATTERN
        prefix = "/public/media-library/"
        if value.startswith(prefix) and KEY_PATTERN.fullmatch(value[len(prefix):]):
            return value
    parsed = urlparse(value)
    if value.startswith("/website-studio/assets/") and ".." not in value:
        return value
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Use an HTTPS image or social URL")
    return value


def validate_config(value):
    if not isinstance(value, dict):
        raise ValueError("Design settings must be an object")
    allowed = {"version", "theme_id", "language", "social_links", "events", "backgrounds", "lone_star", "approved_template"}
    if set(value) - allowed:
        raise ValueError("Unknown design setting")
    if type(value.get("version")) is not int or value.get("version") != 1:
        raise ValueError("Unsupported design settings version")
    library = catalogue()
    if value.get("theme_id") not in {t["id"] for t in library["themes"]}:
        raise ValueError("Choose an approved website design")
    if value.get("language", "en") not in {"en", "es"}:
        raise ValueError("Language must be English or Spanish")
    clean = {"version": 1, "theme_id": value["theme_id"], "language": value.get("language", "en")}
    social = value.get("social_links", {})
    platforms = {"facebook", "instagram", "youtube", "tiktok", "x", "linkedin", "threads", "pinterest", "whatsapp", "yelp", "snapchat"}
    if not isinstance(social, dict) or set(social) - platforms:
        raise ValueError("Unsupported social platform")
    clean["social_links"] = {key: _url(url) for key, url in social.items()}
    backgrounds = value.get("backgrounds", {})
    if not isinstance(backgrounds, dict) or set(backgrounds) - {"about", "financing", "trade", "contact", "service"}:
        raise ValueError("Unsupported background section")
    clean["backgrounds"] = {key: _url(url, artwork=True) for key, url in backgrounds.items()}
    events = value.get("events", [])
    if not isinstance(events, list) or len(events) > 46:
        raise ValueError("Choose at most 46 events")
    event_ids = {e["id"] for e in library["events"]}
    seen = set()
    clean["events"] = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Each event must be an object")
        allowed_event = {"template_id", "enabled", "title", "title_es", "summary", "summary_es", "terms", "terms_es", "starts_on", "ends_on", "banner_url", "image_url", "vehicle_ids"}
        if set(event) - allowed_event:
            raise ValueError("Unknown event setting")
        key = event.get("template_id")
        if key not in event_ids or key in seen:
            raise ValueError("Choose a valid, unique event template")
        seen.add(key)
        if type(event.get("enabled", False)) is not bool:
            raise ValueError("Event enabled must be true or false")
        item = {"template_id": key, "enabled": event.get("enabled", False)}
        for field in ("title", "title_es", "summary", "summary_es", "terms", "terms_es"):
            if field in event:
                item[field] = _text(event[field], field)
        for field in ("starts_on", "ends_on"):
            raw = _text(event.get(field, ""), field, 10)
            if raw:
                try:
                    if date.fromisoformat(raw).isoformat() != raw:
                        raise ValueError()
                except ValueError:
                    raise ValueError("Event dates must use YYYY-MM-DD") from None
            item[field] = raw
        if item["starts_on"] and item["ends_on"] and item["ends_on"] < item["starts_on"]:
            raise ValueError("Event end date cannot precede its start")
        for field in ("banner_url", "image_url"):
            if field in event:
                item[field] = _url(event[field], artwork=True)
        ids = event.get("vehicle_ids", [])
        if not isinstance(ids, list) or len(ids) > 500:
            raise ValueError("Choose at most 500 inventory vehicles")
        item["vehicle_ids"] = list(dict.fromkeys(_text(v, "Vehicle ID", 128) for v in ids))
        clean["events"].append(item)
    if "lone_star" in value:
        if clean["theme_id"] != "lone-star":
            raise ValueError("Lone Star settings require the Lone Star design")
        clean["lone_star"] = validate_lone_star(value["lone_star"])
    if "approved_template" in value:
        if "lone_star" in value:
            raise ValueError("Use one customization settings object")
        clean["approved_template"] = validate_lone_star(value["approved_template"])
    return clean


def validate_lone_star(value):
    if not isinstance(value, dict):
        raise ValueError("Lone Star settings must be an object")
    allowed = {"name", "headline", "intro", "story", "hero", "teamPhoto", "locations", "socials", "backgrounds", "event", "coupons"}
    if set(value) - allowed:
        raise ValueError("Unknown Lone Star setting")
    result = {key: _text(value.get(key, ""), key, 4000) for key in ("name", "headline", "intro", "story")}
    for key in ("hero", "teamPhoto"):
        result[key] = _url(value.get(key, ""), artwork=True)
    for key in ("socials", "backgrounds"):
        raw = value.get(key, {})
        names = {"trade", "contact"} if key == "backgrounds" else {"Facebook", "Instagram", "YouTube", "TikTok", "X", "LinkedIn", "Threads", "Pinterest", "Snapchat", "WhatsApp"}
        if not isinstance(raw, dict) or set(raw) - names:
            raise ValueError("Invalid Lone Star links")
        result[key] = {k: _url(v, artwork=key == "backgrounds") for k, v in raw.items()}
    locations = value.get("locations", [])
    if not isinstance(locations, list) or len(locations) > 50:
        raise ValueError("Choose at most 50 locations")
    result["locations"] = []
    ids = set()
    names = set()
    for location in locations:
        if not isinstance(location, dict) or set(location) - {"id", "name", "address", "phone", "hours"}:
            raise ValueError("Invalid location")
        item = {k: _text(location.get(k, ""), k, 1000) for k in ("id", "name", "address", "phone", "hours")}
        if not item["id"] or not item["name"] or item["id"] in ids or item["name"].casefold() in names or not item["address"]:
            raise ValueError("Locations need unique IDs and names")
        ids.add(item["id"])
        names.add(item["name"].casefold())
        result["locations"].append(item)
    event = value.get("event", {})
    allowed_event = {"template", "enabled", "bannerEnabled", "title", "titleEs", "summary", "summaryEs", "terms", "termsEs", "start", "end", "target", "bodyType", "banner", "event"}
    if not isinstance(event, dict) or set(event) - allowed_event:
        raise ValueError("Invalid Lone Star event")
    if event.get("template") not in {e["id"] for e in catalogue()["events"]}:
        raise ValueError("Choose a valid event")
    cleaned = {k: _text(v, k) for k, v in event.items() if k not in {"enabled", "bannerEnabled"}}
    for key in ("enabled", "bannerEnabled"):
        if type(event.get(key)) is not bool:
            raise ValueError("Event switches must be true or false")
        cleaned[key] = event[key]
    for key in ("banner", "event"):
        cleaned[key] = _url(event.get(key, ""), artwork=True)
    if event.get("target") not in {"all", "type"} or event.get("bodyType") not in {"Truck", "SUV", "Coupe", "Sedan", ""}:
        raise ValueError("Choose valid event inventory eligibility")
    for key in ("start", "end"):
        if event.get(key) and date.fromisoformat(event[key]).isoformat() != event[key]:
            raise ValueError("Use YYYY-MM-DD event dates")
    if event.get("start") and event.get("end") and event["end"] < event["start"]:
        raise ValueError("Event end date cannot precede its start")
    result["event"] = cleaned
    if "coupons" in value:
        result["coupons"] = validate_coupons(value["coupons"])
    return result


@serialized_website_write
def update_studio_api(role, employee_id, website_id, config, expected_revision):
    website = websites.get_website(website_id)
    if not website:
        return {"error": "Website not found"}
    if not _can_edit_content(role, employee_id, website):
        return {"error": "You don't have access to edit this site"}
    if website.attributes.get("status") not in {"draft", "rejected"}:
        return {"error": "Only draft or rejected sites can change design settings"}
    revision = website.attributes.get("studio_revision", 0)
    if type(expected_revision) is not int or revision != expected_revision:
        return {"error": "This design changed in another session. Reload before saving."}
    try:
        clean = validate_config(config)
        # References must point to canonical, unsold inventory in this tenant.
        inventory_ids = {str(v["id"]) for v in websites.get_live_inventory(limit=100000)}
        for event in clean["events"]:
            if set(event["vehicle_ids"]) - inventory_ids:
                raise ValueError("An event vehicle is unavailable in this dealership's inventory")
    except (ValueError, TypeError) as error:
        # Validation details contain only our fixed labels, never record contents.
        return {"error": str(error)}
    before = deepcopy(website.attributes)
    website.attributes["studio_config"] = deepcopy(clean)
    website.attributes["studio_revision"] = revision + 1
    website.attributes["updated_at"] = websites._now()
    websites._log_history(website, "studio_design_updated", employee_id)
    try:
        websites.save_graph(websites.GRAPH_PATH)
    except Exception:
        website.attributes.clear()
        website.attributes.update(before)
        raise
    return _serialize_website(website)


def render_studio_events(website, today=None):
    """Resolve public offer copy and eligible stock afresh, never cached sample cars."""
    config = website.attributes.get("studio_config") or {}
    templates = {event["id"]: event for event in catalogue()["events"]}
    today = (today or date.today()).isoformat()
    inventory = {str(vehicle["id"]): vehicle for vehicle in websites.get_live_inventory(limit=100000)}
    result = []
    for saved in config.get("events", []):
        if not saved.get("enabled") or saved.get("template_id") not in templates:
            continue
        if saved.get("starts_on") and today < saved["starts_on"]:
            continue
        if saved.get("ends_on") and today > saved["ends_on"]:
            continue
        template = templates[saved["template_id"]]
        result.append({
            "id": template["id"],
            "title": saved.get("title", template["title"]),
            "title_es": saved.get("title_es", template["titleEs"]),
            "summary": saved.get("summary", template["summary"]),
            "summary_es": saved.get("summary_es", template["summaryEs"]),
            "terms": saved.get("terms", template["terms"]),
            "terms_es": saved.get("terms_es", template["termsEs"]),
            "starts_on": saved.get("starts_on", ""),
            "ends_on": saved.get("ends_on", ""),
            "banner_url": saved.get("banner_url") or template["banner"],
            "image_url": saved.get("image_url") or template["image"],
            "image_alt": template["imageAlt"],
            "image_alt_es": template["imageAltEs"],
            "background": template["bg"],
            "accent": template["accent"],
            "vehicles": [inventory[key] for key in saved.get("vehicle_ids", []) if key in inventory],
        })
    return result


def studio_inventory_api(role, employee_id, website_id):
    website = websites.get_website(website_id)
    if not website or not _can_edit_content(role, employee_id, website):
        return {"error": "You don't have access to this site's inventory settings"}
    return websites.get_live_inventory(limit=100000)


@serialized_website_write
def create_studio_api(employee_id, name, theme_id, request_id, mode="traditional"):
    """Create one canonical draft; retries with the same owner/key return it."""
    from uuid import UUID
    try:
        name = _text(name, "Site name", 160)
        if not name:
            raise ValueError("A site name is required")
        request_id = str(UUID(request_id))
        config = validate_config({"version": 1, "theme_id": theme_id})
        if mode not in websites.MODES:
            raise ValueError("Choose a valid website experience")
    except (ValueError, TypeError, AttributeError) as error:
        return {"error": str(error)}
    for site in websites.list_websites(created_by=employee_id):
        if site.attributes.get("requested_by") == employee_id and site.attributes.get("studio_creation_key") == request_id:
            # Also retries a previous persistence failure without another record.
            websites.save_graph(websites.GRAPH_PATH)
            return _serialize_website(site)
    pages = websites._empty_pages()
    def section(page, key, **fields):
        pages[page]["sections"].append({"section_key": key, "fields": fields, "locked": False})
    section("home", "hero_banner", headline="Find your next drive.", subheadline="Explore our inventory and connect with our team.", cta_text="Explore inventory")
    section("home", "car_builder", heading="Find your next vehicle", intro_text="Explore options from our current inventory.")
    section("home", "inventory_grid", limit=6)
    section("home", "financing_info", heading="Let's talk financing", body="Contact our team to discuss available financing options.")
    section("home", "contact_form", heading="Let's talk cars", phone="", address="")
    section("inventory", "inventory_grid", limit=48)
    section("about", "text_block", heading="About us", body="Tell customers about your dealership, your team, and the community you serve.")
    section("financing", "financing_info", heading="Explore financing", body="Contact our team to discuss available financing options.")
    section("financing", "trade_evaluation", heading="Value your trade", intro_text="Tell us about your current vehicle.")
    section("contact", "contact_form", heading="How can we help?", phone="", address="")
    site = websites.create_website(name, employee_id, mode, _skip_save=True)
    site.attributes.update({"pages": pages, "studio_config": config, "studio_revision": 1, "studio_creation_key": request_id})
    websites._log_history(site, "studio_created", employee_id, notes=theme_id)
    websites.save_graph(websites.GRAPH_PATH)
    return _serialize_website(site)


@serialized_website_write
def start_draft_api(role, employee_id, website_id):
    """Edit the same canonical site while its immutable approved version stays live."""
    from core.website_revisions import has_public_version
    site = websites.get_website(website_id)
    if not site or not _can_edit_content(role, employee_id, site):
        return {"error": "You don't have access to edit this site"}
    if not site.attributes.get("studio_config") or not site.attributes.get("published_snapshot") or not has_public_version(site):
        return {"error": "This website does not have an approved studio version"}
    status = site.attributes.get("status")
    if status in ("draft", "rejected"):
        return _serialize_website(site)  # Retry never discards edits already made.
    if status != "published":
        return {"error": "This draft is already awaiting review"}
    before = deepcopy(site.attributes)
    site.attributes.update(deepcopy(site.attributes["published_snapshot"]))
    site.attributes["status"] = "draft"
    site.attributes["studio_revision"] = int(site.attributes.get("studio_revision", 0)) + 1
    site.attributes.pop("review_snapshot", None)
    site.attributes.pop("review_fingerprint", None)
    site.attributes["updated_at"] = websites._now()
    websites._log_history(site, "draft_started", employee_id)
    try:
        websites.save_graph(websites.GRAPH_PATH)
    except Exception:
        site.attributes.clear()
        site.attributes.update(before)
        raise
    return _serialize_website(site)


def public_inventory_api(website_id, *, page=1, page_size=12, location_id=None, query=None, make=None, max_price=None):
    """Page the current tenant's canonical public stock, filtering before slicing."""
    from core.website_revisions import has_public_version
    from core.dealeros import ledger
    if not has_public_version(websites.get_website(website_id)):
        return {"error": "Site not found"}
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 48:
        return {"error": "Choose a valid inventory page"}
    query = str(query or "").strip().casefold()[:100]
    vehicles = websites.get_live_inventory(make=make, max_price=max_price, limit=len(ledger.get_all()) + 1)
    if query:
        vehicles = [v for v in vehicles if query in " ".join(str(v.get(k) or "") for k in ("year", "make", "model", "trim")).casefold()]
    locations = {}
    for vehicle in vehicles:
        key = vehicle["location_id"] or "unassigned"
        if key not in locations:
            locations[key] = {"id": key, "name": vehicle["location_name"] or "Confirm location with dealer", "count": 0}
        locations[key]["count"] += 1
    if location_id:
        vehicles = [v for v in vehicles if (v["location_id"] or "unassigned") == location_id]
    vehicles.sort(key=lambda v: v["id"])
    total = len(vehicles)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    start = (page - 1) * page_size
    return {"vehicles": vehicles[start:start + page_size], "total": total, "page": page,
            "page_size": page_size, "pages": pages, "locations": sorted(locations.values(), key=lambda item: item["name"])}


def validate_coupons(coupons):
    if not isinstance(coupons, list) or len(coupons) > 30:
        raise ValueError("Add at most 30 service coupons")
    seen = set()
    result = []
    for coupon in coupons:
        fields = {"id", "enabled", "title", "titleEs", "summary", "summaryEs", "terms", "termsEs", "code", "start", "end"}
        if not isinstance(coupon, dict) or set(coupon) - fields:
            raise ValueError("Invalid service coupon")
        item = {k: _text(coupon.get(k, ""), k, 100 if k in ("id", "code") else 4000) for k in fields - {"enabled"}}
        if not item["id"] or item["id"] in seen or not item["title"]:
            raise ValueError("Each coupon needs a unique ID and title")
        if type(coupon.get("enabled")) is not bool:
            raise ValueError("Coupon enabled must be true or false")
        item["enabled"] = coupon["enabled"]
        for field in ("start", "end"):
            if item[field] and date.fromisoformat(item[field]).isoformat() != item[field]:
                raise ValueError("Use YYYY-MM-DD coupon dates")
        if item["start"] and item["end"] and item["end"] < item["start"]:
            raise ValueError("Coupon end date cannot precede its start")
        seen.add(item["id"])
        result.append(item)
    return result
