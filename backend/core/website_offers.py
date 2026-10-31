"""Read-only projections of approved website offers in the current dealership ledger.
No copied campaigns, coupon records or inventory: edits use the website review flow.
"""
from datetime import date
from core import websites
from core.entity_types import WEBSITE
from core.website_revisions import public_version
from core.website_studio import render_studio_events


def active(item, today):
    return bool(item.get("enabled") and (not item.get("start") or item["start"] <= today)
                and (not item.get("end") or item["end"] >= today))


def offers_for_site(website, today=None):
    site = public_version(website)
    if not site:
        return []
    day = (today or date.today()).isoformat()
    config = site.attributes.get("studio_config") or {}
    custom = config.get("lone_star") or config.get("approved_template") or {}
    base = {"website_id": site.id, "website_name": custom.get("name") or site.attributes.get("name"),
            "website_url": "/site/" + site.id}
    result = []
    event = custom.get("event") or {}
    if active(event, day):
        inventory = websites.get_live_inventory(limit=100000)
        vehicles = [v for v in inventory if event.get("target") == "all" or str(v.get("body_type", "")).lower() == event.get("bodyType", "").lower()]
        result.append({**base, "id": site.id + ":event", "kind": "event", **{k: event.get(k, "") for k in ("title", "titleEs", "summary", "summaryEs", "terms", "termsEs", "start", "end")}, "vehicles": vehicles})
    for event in render_studio_events(site, today=today):
        result.append({**base, "id": site.id+":"+event["id"], "kind": "event", "title": event["title"], "titleEs": event["title_es"], "summary": event["summary"], "summaryEs": event["summary_es"], "terms": event["terms"], "termsEs": event["terms_es"], "start": event["starts_on"], "end": event["ends_on"], "vehicles": event["vehicles"]})
    for coupon in custom.get("coupons", []):
        if active(coupon, day):
            result.append({**base, **coupon, "id": site.id+":coupon:"+coupon["id"], "kind": "coupon", "vehicles": []})
    return result


def published_offers(today=None):
    return {"offers": [offer for site in websites.ledger.get_all().values() if site.entity_type == WEBSITE for offer in offers_for_site(site, today)]}


def garage_offers(token):
    from core.garage import _resolve_customer
    _, error = _resolve_customer(token)
    if error:
        return error
    return published_offers()
