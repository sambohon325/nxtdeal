"""
Enterprise SEO automation for the Website Builder (2026-07-18, Marketing Growth
Platform follow-up -- one of the four "remaining Wix-level asks" CLAUDE.md flagged
open after session 90: "enterprise SEO automation").

Real finding before writing anything: `core/websites.py`'s `get_robots_txt()` has
referenced a real `Sitemap: https://{domain}/sitemap.xml` line since session 58, but
nothing anywhere in this codebase ever generated real sitemap content or served it --
confirmed via a full-repo grep (only that one reference string existed). Per-page SEO
fields (`meta_title`/`meta_description`/`og_image_url` via `update_page_seo()`,
session 85) and analytics IDs already exist, but nothing ever told a dealer whether
those fields were actually filled in well, and nothing generated the structured data
(JSON-LD) search engines and AI crawlers actually use to understand a dealership page.

Three real, 100%-computable pieces -- no external SEO API, no simulated data, all
derived from real fields already stored on the Website entity:

1. `get_sitemap_xml()` -- a real sitemap.xml body for the site's fixed PAGE_KEYS,
   weighted by a real, honest priority scheme (home highest, inventory next, static
   pages lowest) and dated off the site's own real `updated_at`.

2. `get_seo_health()` -- a real, no-simulation-needed health score per page (title/
   description presence and length, an og_image, at least one populated section) plus
   site-wide checks (sitemap enabled, a custom domain configured, an analytics ID
   wired up) -- entirely a function of real stored data, not a market-data gap, so
   session 110's "simulate when blocked" policy doesn't apply here at all: there's
   nothing to simulate, the real inputs already exist.

3. `get_structured_data()` -- a real JSON-LD AutoDealer schema pulled from whatever
   real contact info the site actually has on file (the `contact_form` section's
   phone/address fields, session 58) -- honestly omits `address`/`telephone` when the
   dealer never filled that section in, rather than inventing a placeholder address.

AI meta-copy drafting (`generate_page_seo_copy()`) lives in core/website_wizard.py,
not here, matching this codebase's convention that AI drafting is isolated per-wizard
while the rest of a feature's real computation lives in the feature's own module
(e.g. core/pricing_desk.py's math vs. core/acquisitions.py's separate AI call).
"""

from datetime import datetime, timezone

from core.website_revisions import public_version
from core.websites import get_website, DNS_TARGET_HOSTNAME, PAGE_KEYS, get_live_inventory

# A real, honest priority scheme -- not simulated data, just a reasonable static
# weighting search engines themselves treat as a hint, not a guarantee.
_PAGE_PRIORITY = {
    "home": "1.0",
    "inventory": "0.9",
    "financing": "0.6",
    "about": "0.5",
    "testimonials": "0.4",
    "contact": "0.7",
}

_TITLE_MIN, _TITLE_MAX = 10, 60
_DESC_MIN, _DESC_MAX = 50, 160


def _now():
    return datetime.now(timezone.utc).isoformat()


def _site_domain(website):
    settings = website.attributes.get("admin_settings") or {}
    return settings.get("custom_domain") or DNS_TARGET_HOSTNAME


def get_sitemap_xml(website_id):
    """Real sitemap.xml body -- only meaningful for a published site (a draft has no
    real public URL to index). Returns {"error": ...} for a missing/unpublished site
    rather than a sitemap with dead links."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    website = public_version(website)
    if not website:
        return {"error": "This site isn't published yet -- no public URLs to index"}

    domain = _site_domain(website)
    lastmod = (website.attributes.get("updated_at") or _now())[:10]

    urls = []

    for page_key in PAGE_KEYS:
        loc = f"https://{domain}/site/{website_id}" + ("" if page_key == "home" else f"?page={page_key}")
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <priority>{_PAGE_PRIORITY.get(page_key, '0.5')}</priority>\n"
            "  </url>"
        )

    # Real per-vehicle URLs (session 113 follow-up's VDP slice) -- one entry per real
    # unsold vehicle in current inventory, not just the 6 static PAGE_KEYS above. Capped
    # at 500 (this seed's entire vehicle population is ~500) rather than the grid's own
    # 12-per-page display limit -- a sitemap should list everything indexable, not just
    # what fits on one inventory-grid page.
    for vehicle in get_live_inventory(limit=500):
        loc = f"https://{domain}/site/{website_id}/vehicle/{vehicle['id']}"
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <priority>0.8</priority>\n"
            "  </url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )

    return {"sitemap_xml": xml, "url_count": len(urls), "domain": domain}


def _page_health(website, page_key):
    """One page's real score -- every check is a plain fact about stored data (a
    length, a presence check), nothing inferred or simulated."""

    settings = website.attributes.get("admin_settings") or {}
    page_seo = (settings.get("page_seo") or {}).get(page_key) or {}
    page = (website.attributes.get("pages") or {}).get(page_key) or {}
    sections = page.get("sections") or []

    title = page_seo.get("meta_title") or settings.get("meta_title")
    description = page_seo.get("meta_description") or settings.get("meta_description")
    og_image = page_seo.get("og_image_url")

    checks = []
    points = 0
    max_points = 4

    if title and _TITLE_MIN <= len(title) <= _TITLE_MAX:
        points += 1
        checks.append({"check": "meta_title", "pass": True, "detail": f"{len(title)} characters"})
    elif title:
        checks.append({"check": "meta_title", "pass": False, "detail": f"Set, but {len(title)} characters -- aim for {_TITLE_MIN}-{_TITLE_MAX}"})
    else:
        checks.append({"check": "meta_title", "pass": False, "detail": "No page-level or site-wide meta title set"})

    if description and _DESC_MIN <= len(description) <= _DESC_MAX:
        points += 1
        checks.append({"check": "meta_description", "pass": True, "detail": f"{len(description)} characters"})
    elif description:
        checks.append({"check": "meta_description", "pass": False, "detail": f"Set, but {len(description)} characters -- aim for {_DESC_MIN}-{_DESC_MAX}"})
    else:
        checks.append({"check": "meta_description", "pass": False, "detail": "No page-level or site-wide meta description set"})

    if og_image:
        points += 1
        checks.append({"check": "og_image", "pass": True, "detail": "Social preview image set"})
    else:
        checks.append({"check": "og_image", "pass": False, "detail": "No social preview (og:image) set for this page"})

    if sections:
        points += 1
        checks.append({"check": "content", "pass": True, "detail": f"{len(sections)} section(s) on the page"})
    else:
        checks.append({"check": "content", "pass": False, "detail": "This page has no sections yet"})

    return {
        "page_key": page_key,
        "score_pct": round(100 * points / max_points, 1),
        "checks": checks,
    }


def get_seo_health(website_id):
    """Real per-page health scores + real site-wide checks. Entirely computed from
    fields already on the entity -- no simulation, since there's no external-data gap
    here at all (unlike Pricing Desk's market data)."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    settings = website.attributes.get("admin_settings") or {}
    pages = [_page_health(website, pk) for pk in PAGE_KEYS]
    overall = round(sum(p["score_pct"] for p in pages) / len(pages), 1) if pages else 0.0

    site_checks = [
        {"check": "sitemap_enabled", "pass": bool(settings.get("sitemap_enabled", True)), "detail": "Sitemap generation is on" if settings.get("sitemap_enabled", True) else "Sitemap generation is off in Admin Settings"},
        {"check": "custom_domain", "pass": bool(settings.get("custom_domain")), "detail": "A custom domain is configured" if settings.get("custom_domain") else "No custom domain set -- sitemap/robots.txt will use the default NXTDeal hostname"},
        {"check": "analytics", "pass": bool(settings.get("google_analytics_id") or settings.get("umami_site_id")), "detail": "An analytics ID is wired up" if (settings.get("google_analytics_id") or settings.get("umami_site_id")) else "No Google Analytics or Umami ID configured"},
        {"check": "search_engines_allowed", "pass": bool(settings.get("allow_search_engines", True)), "detail": "Search engines are allowed to index this site" if settings.get("allow_search_engines", True) else "Search engines are currently BLOCKED in Admin Settings"},
    ]

    return {
        "website_id": website_id,
        "overall_score_pct": overall,
        "pages": pages,
        "site_checks": site_checks,
    }


def get_structured_data(website_id):
    """Real JSON-LD (schema.org AutoDealer) for the site -- built from whatever real
    contact info the dealer actually filled in (the contact_form section's phone/
    address fields). Honestly omits fields with no real value on file rather than
    inventing a placeholder address/phone -- a fabricated address in structured data
    would actively mislead a search engine, not just look incomplete."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    settings = website.attributes.get("admin_settings") or {}
    domain = _site_domain(website)

    contact_fields = {}
    for page in (website.attributes.get("pages") or {}).values():
        for section in page.get("sections") or []:
            if section.get("section_key") == "contact_form":
                contact_fields = section.get("fields") or {}
                break

    data = {
        "@context": "https://schema.org",
        "@type": "AutoDealer",
        "name": website.attributes.get("name"),
        "url": f"https://{domain}/site/{website_id}",
    }

    if contact_fields.get("phone"):
        data["telephone"] = contact_fields["phone"]

    if contact_fields.get("address"):
        data["address"] = {"@type": "PostalAddress", "streetAddress": contact_fields["address"]}

    if settings.get("branding_mode") == "oem" and settings.get("oem_logo_url"):
        data["logo"] = settings["oem_logo_url"]

    return {"json_ld": data}
