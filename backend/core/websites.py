"""
Website / inventory builder (2026-07-13, session 32 -- phase 3 of the NXTDeal suite
integration) -- rebuilt into a real product (2026-07-14, session 58) per Sam: "on the
website creator, i want to have dealerOS create the website through a setup wizard...
default in a traditional dealership template... but also have a dealerGPT mode that
switches it to a stripped down dealer branded version of DriveFinder.xyz that they can
'build their car' into whats available on the lot... let ai write the content and set
it up. They can get more granular within in a canvas mode and edit each page/section
(we can lock stuff if we feel they'll mess it up)... from the admin side they can
control the DNS info... SEO, Bot stuff, and have Google / umami style analytics...
plug in their google id... facebook ads codes... code snippits... OEM branded elements
or run as an independant dealership."

Still the same graph-native rule as everything else here: a Website is one ordinary
Entity in the same ledger every other entity type lives in, tied to the Employee who
built it (and now, potentially several Employee owners). The Inventory page (and the
new DealerGPT "build your car" page) are still rendered live from the Vehicle entities
already in the graph every time the site is fetched -- no parallel inventory store.

What's genuinely new this session, and what's an honest non-integration (see each
section below):
  - `mode`: "traditional" | "dealer_gpt" -- same fixed PAGE_KEYS either way (so URLs/
    section-editing endpoints don't need to branch), but the wizard populates a
    stripped-down page set for dealer_gpt (home = car_builder + social links only,
    testimonials/financing left for the dealer to fill in later if they want them).
  - core/website_wizard.py (new) calls the same OpenAI integration core/ai_assistant.py
    already uses to draft real page copy from a few dealership basics, instead of the
    dealer typing every field by hand -- genuinely real content generation, not canned
    strings.
  - `locked` per section + `owners` list + an append-only `history` log on the entity
    (same shape as core/workflow_tracking.py's WorkflowInstance.history) -- real access
    control and a real audit trail, no new store.
  - `admin_settings`: custom_domain, SEO fields, bot/robots.txt controls, analytics IDs
    (Google Analytics / Umami / Facebook Pixel) + custom code snippets, and OEM vs.
    independent branding. DNS is the one deliberately-honest non-integration here: this
    environment has no real domain registrar/DNS API to call, so "DNS admin control"
    means storing the dealer's chosen custom_domain and generating the exact CNAME
    record + target hostname they need to create at their own registrar
    (get_dns_instructions()) -- not actually provisioning anything. Same honesty bar as
    core/data_connections.py's API connection tester or core/network_aggregator.py's
    "reachable vs. not" reporting.

Real, major data-loss bug found and fixed (2026-07-18, Marketing Growth Platform
data-gap-fill follow-up -- discovered via a codebase-wide grep sweep for the same bug
class already found repeatedly this session, see core/lead_conversion.py's docstring
for the running list) -- this entire module, the whole Website Builder, had ZERO
save_graph() calls anywhere since it shipped (session 32/58). Every real Website ever
created, every section added/edited/reordered/locked/removed, every owner added, every
SEO/admin-settings/mode change, and every submit/approve/reject had been silently
discarded on server restart. Fixed by adding save_graph(GRAPH_PATH) to every mutating
function below. record_page_view() is the one deliberate exception -- it's called on
every public page load, and this codebase's own established precedent
(core/trigger_alerts.py's run_scan()) is to avoid an unconditional save on a
potentially-high-frequency path; see that function's own comment for the reasoning.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import WEBSITE, VEHICLE, IMAGE, WEBSITE_ANALYTICS_EVENT
from core.website_wizard import generate_wizard_copy, fallback_copy, regenerate_section_copy
from core.lead_intake import create_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from copy import deepcopy
from core.website_revisions import has_public_version, public_version, rollback_website_transition, studio_content_write, serialized_website_write, freeze_review, review_is_current


# Fixed page set. Expanded session 58 (from the original 4 -- home/inventory/about/
# contact) to match Sam's "traditional dealership template" spec: testimonials, Google
# ratings, social links, and financing all need a home somewhere. `dealer_gpt` mode
# uses this exact same page set (no separate URL/section-editing shape to maintain) --
# the wizard just leaves testimonials/financing empty for that mode rather than the
# page keys themselves changing.
PAGE_KEYS = ["home", "inventory", "about", "testimonials", "financing", "contact"]

PAGE_LABELS = {
    "home": "Home",
    "inventory": "Inventory",
    "about": "About",
    "testimonials": "Testimonials",
    "financing": "Financing",
    "contact": "Contact",
}

MODES = ["traditional", "dealer_gpt"]

# The honest DNS non-integration -- there is no real registrar/DNS API in this
# environment, so "pointing the dealer's DNS at us" means giving them the exact record
# to create at whatever registrar they already use. A fixed, clearly-labeled constant
# rather than anything that pretends to be dynamically provisioned.
DNS_TARGET_HOSTNAME = "sites.nxtdeal.app"


# Fixed starter catalog, one entry per section a dealer site typically needs -- mirrors
# core/assets.py's ASSET_TEMPLATES/core/campaigns.py's CAMPAIGN_TYPES shape (fixed
# catalog + a small `fields` schema the frontend renders as a form). Every image field
# is a plain URL the dealer supplies -- there is no AI image generation anywhere in this
# module, matching Sam's explicit instruction from session 32 (still true this session).
SECTION_TEMPLATES = {
    "hero_banner": {
        "key": "hero_banner",
        "name": "Hero Banner",
        "description": "A full-width banner with a headline and background image.",
        "fields": [
            {"key": "headline", "label": "Headline", "type": "text", "required": True, "ai_writable": True},
            {"key": "subheadline", "label": "Subheadline", "type": "text", "required": False, "ai_writable": True},
            {"key": "image_url", "label": "Background Image URL", "type": "text", "required": False},
            {"key": "cta_text", "label": "Call to Action Text", "type": "text", "required": False, "ai_writable": True},
        ],
    },
    "text_block": {
        "key": "text_block",
        "name": "Text Block",
        "description": "A heading plus a paragraph of text -- dealership story, hours, policies.",
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "ai_writable": True},
            {"key": "body", "label": "Body Text", "type": "textarea", "required": True, "ai_writable": True},
        ],
    },
    "image_gallery": {
        "key": "image_gallery",
        "name": "Image Gallery",
        "description": "A row of dealer-supplied photos (showroom, staff, events).",
        "fields": [
            {"key": "image_urls", "label": "Image URLs (comma-separated)", "type": "textarea", "required": True},
        ],
    },
    "inventory_grid": {
        "key": "inventory_grid",
        "name": "Inventory Grid",
        "description": "A live, filterable grid of current inventory -- pulled from the graph, not a static list.",
        "fields": [
            {"key": "make", "label": "Filter: Make (optional)", "type": "text", "required": False},
            {"key": "max_price", "label": "Filter: Max Price (optional)", "type": "text", "required": False},
            {"key": "location_id", "label": "Location", "type": "text", "required": False},
            {"key": "limit", "label": "Max vehicles to show", "type": "text", "required": False, "default": 12},
        ],
    },
    "contact_form": {
        "key": "contact_form",
        "name": "Contact Info",
        "description": "Phone, address, and a heading for a contact/visit-us page.",
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "ai_writable": True},
            {"key": "phone", "label": "Phone", "type": "text", "required": False},
            {"key": "address", "label": "Address", "type": "text", "required": False},
        ],
    },
    # --- Added session 58 -- the "traditional dealership template" elements Sam named
    # (testimonials, Google ratings, social links, financing) plus OEM branding and the
    # DealerGPT "build your car" configurator.
    "testimonials_carousel": {
        "key": "testimonials_carousel",
        "name": "Testimonials",
        "description": "Customer quotes -- one per line, formatted as 'Name | Quote'.",
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "What Our Customers Say", "ai_writable": True},
            {"key": "testimonials", "label": "Testimonials (one per line: Name | Quote)", "type": "textarea", "required": True, "ai_writable": True},
        ],
    },
    "google_rating_badge": {
        "key": "google_rating_badge",
        "name": "Google Rating Badge",
        "description": "A summary badge showing the dealership's Google review rating.",
        "fields": [
            {"key": "rating_text", "label": "Rating summary (e.g. '4.8★ from 320 Google reviews')", "type": "text", "required": True},
            {"key": "google_place_id", "label": "Google Place ID (optional, for a live link)", "type": "text", "required": False},
        ],
    },
    "social_links": {
        "key": "social_links",
        "name": "Social Links",
        "description": "Links to the dealership's social profiles.",
        "fields": [
            {"key": "facebook_url", "label": "Facebook URL", "type": "text", "required": False},
            {"key": "instagram_url", "label": "Instagram URL", "type": "text", "required": False},
            {"key": "tiktok_url", "label": "TikTok URL", "type": "text", "required": False},
            {"key": "x_url", "label": "X / Twitter URL", "type": "text", "required": False},
        ],
    },
    "financing_info": {
        "key": "financing_info",
        "name": "Financing",
        "description": "A financing pitch plus a link to an application.",
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Get Pre-Approved", "ai_writable": True},
            {"key": "body", "label": "Body Text", "type": "textarea", "required": True, "ai_writable": True},
            {"key": "apply_url", "label": "Financing Application URL (optional)", "type": "text", "required": False},
        ],
    },
    "oem_branding_banner": {
        "key": "oem_branding_banner",
        "name": "OEM Branding",
        "description": "Manufacturer logo/name banner -- only meaningful when the site's branding mode is 'oem'.",
        "fields": [
            {"key": "oem_name", "label": "OEM / Manufacturer Name", "type": "text", "required": True},
            {"key": "oem_logo_url", "label": "OEM Logo URL", "type": "text", "required": False},
            {"key": "disclaimer", "label": "Disclaimer (e.g. 'Independently owned and operated')", "type": "text", "required": False},
        ],
    },
    "car_builder": {
        "key": "car_builder",
        "name": "Build Your Car (DealerGPT)",
        "description": (
            "A stripped-down configurator -- customers step through Make -> Model -> "
            "Trim against what's actually live on the lot. Rendered from the graph at "
            "fetch time (get_car_builder_options()), same 'no parallel inventory copy' "
            "rule as the Inventory Grid section."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Build Your Car", "ai_writable": True},
            {"key": "intro_text", "label": "Intro Text", "type": "textarea", "required": False, "ai_writable": True},
        ],
    },
    # Raw HTML drop-in (2026-07-23) -- Sam wants the same "drop in the HTML and it's
    # there" affordance the email builder has: a section whose single `html` field is
    # rendered verbatim by the frontend SiteSectionRenderer (dangerouslySetInnerHTML),
    # so an externally-designed block or embed pastes straight onto the page. Passed
    # through render_page() untouched like every other section's fields.
    "custom_html": {
        "key": "custom_html",
        "name": "Custom HTML",
        "description": "Paste in your own HTML (an externally-designed block or embed). Rendered exactly as written.",
        "fields": [
            {"key": "html", "label": "HTML", "type": "textarea", "required": True},
        ],
    },
    # --- Digital Retail widgets (2026-07-24, DR-5) -- the customer-facing self-service
    # surface. Each drops onto any page; the graph-backed ones (Ask NXTDeal, Payment
    # Builder) resolve live data in render_page() just like inventory_grid/car_builder,
    # and the interactive ones post to the /public/verify + /public/retail routes DR-1..4
    # built. Boolean-ish fields are plain text ("true"/"false") since the builder's field
    # editor only distinguishes text vs textarea today.
    "ask_dealeros": {
        "key": "ask_dealeros",
        "name": "Ask NXTDeal (AI Shopping Assistant)",
        "description": (
            "An AI shopping assistant grounded in this dealer's live inventory -- vehicle "
            "recommendations, comparisons, feature explanations, inventory search and trade "
            "questions. Resolves a live inventory sample at render time; the live chat itself "
            "runs through the site's existing public chat (core/website_chat.py)."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Ask NXTDeal", "ai_writable": True},
            {"key": "intro_text", "label": "Intro Text", "type": "textarea", "required": False, "ai_writable": True},
            {"key": "placeholder", "label": "Input Placeholder", "type": "text", "required": False, "default": "Ask about any vehicle, payment, or your trade..."},
        ],
    },
    "payment_builder": {
        "key": "payment_builder",
        "name": "Payment Builder",
        "description": (
            "A real-time payment estimator -- the customer picks a vehicle from what's live "
            "on the lot, adjusts down payment and term, and sees the monthly update instantly "
            "(client-side amortization against a dealer-set assumed APR). Resolves the same "
            "live Make/Model/Trim options as Build Your Car."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Estimate Your Payment", "ai_writable": True},
            {"key": "default_down", "label": "Default Down Payment", "type": "text", "required": False, "default": "3000"},
            {"key": "default_term_months", "label": "Default Term (months)", "type": "text", "required": False, "default": "60"},
            {"key": "assumed_apr", "label": "Assumed APR %", "type": "text", "required": False, "default": "6.9"},
            {"key": "disclaimer", "label": "Disclaimer", "type": "textarea", "required": False, "default": "Estimate only. Actual terms depend on credit approval."},
        ],
    },
    "trade_evaluation": {
        "key": "trade_evaluation",
        "name": "Trade Evaluation",
        "description": (
            "A trade-in intake -- the customer submits VIN, mileage, condition and photos and "
            "gets a trade estimate + equity/upgrade position. Posts to the Digital Retail trade "
            "flow (a trade estimate requires Verified Human via NXTDeal Verify)."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Value Your Trade", "ai_writable": True},
            {"key": "intro_text", "label": "Intro Text", "type": "textarea", "required": False, "ai_writable": True},
            {"key": "disclaimer", "label": "Disclaimer", "type": "textarea", "required": False, "default": "Estimate only, subject to a physical inspection."},
        ],
    },
    "buy_online": {
        "key": "buy_online",
        "name": "Buy Online",
        "description": (
            "The self-service purchase entry point. The dealer sets how far a customer can go: "
            "browse (inventory only), build (build a deal), negotiate (AI negotiation), or "
            "purchase (full online checkout). The level gates what the widget enables."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Buy Online", "ai_writable": True},
            {"key": "level", "label": "Level (browse | build | negotiate | purchase)", "type": "text", "required": False, "default": "build"},
            {"key": "cta_text", "label": "Button Text", "type": "text", "required": False, "default": "Start Buying Online", "ai_writable": True},
            {"key": "disclaimer", "label": "Disclaimer", "type": "textarea", "required": False},
        ],
    },
    "delivery_scheduling": {
        "key": "delivery_scheduling",
        "name": "Delivery Scheduling",
        "description": (
            "Lets the customer pick how they take delivery -- store pickup, home delivery, or a "
            "try-before-you-buy test. Each option is dealer-toggleable ('true'/'false')."
        ),
        "fields": [
            {"key": "heading", "label": "Heading", "type": "text", "required": False, "default": "Schedule Your Delivery", "ai_writable": True},
            {"key": "offer_store_pickup", "label": "Offer Store Pickup (true/false)", "type": "text", "required": False, "default": "true"},
            {"key": "offer_home_delivery", "label": "Offer Home Delivery (true/false)", "type": "text", "required": False, "default": "true"},
            {"key": "offer_try_before_you_buy", "label": "Offer Try Before You Buy (true/false)", "type": "text", "required": False, "default": "false"},
            {"key": "delivery_radius_miles", "label": "Home Delivery Radius (miles)", "type": "text", "required": False, "default": "50"},
            {"key": "disclaimer", "label": "Disclaimer", "type": "textarea", "required": False},
        ],
    },
}


def list_section_templates():
    return list(SECTION_TEMPLATES.values())


def get_section_template(section_key):
    return SECTION_TEMPLATES.get(section_key)


def list_page_keys():
    return [{"key": key, "label": PAGE_LABELS[key]} for key in PAGE_KEYS]


def list_modes():
    return MODES


# Layout template catalog (session 85) -- Sam: "layout templates to choose from for
# independent dealers, OEM compliant templates for franchise." This is the non-AI
# quick-start path that sits alongside create_website_from_wizard()'s AI path: pick a
# template, get a real set of pre-populated sections instantly, then edit/AI-regenerate
# from there. "OEM compliant" here means the oem_* templates ship their manufacturer
# branding banner PRE-LOCKED (apply_site_template() calls set_section_locked() right
# after adding it) -- matching how a real franchise/co-op ad agreement typically
# requires the OEM banner can't just be deleted by a location-level user, the same
# "lock stuff we don't want them to mess with" instinct Sam already asked for at the
# per-section level in session 58.
SITE_TEMPLATES = {
    "independent_classic": {
        "key": "independent_classic",
        "name": "Independent Classic",
        "dealer_type": "independent",
        "description": "A straightforward traditional layout for an independently owned lot -- hero, inventory, about, financing, contact.",
        "pages": {
            "home": [
                {"section_key": "hero_banner", "fields": {"headline": "Welcome to {dealership_name}", "subheadline": "Quality used vehicles, honest prices.", "cta_text": "Browse Inventory"}, "locked": False},
                {"section_key": "google_rating_badge", "fields": {"rating_text": "Add your Google rating here"}, "locked": False},
            ],
            "inventory": [
                {"section_key": "inventory_grid", "fields": {"limit": 12}, "locked": False},
            ],
            "about": [
                {"section_key": "text_block", "fields": {"heading": "About Us", "body": "Tell your dealership's story here."}, "locked": False},
            ],
            "financing": [
                {"section_key": "financing_info", "fields": {"heading": "Get Pre-Approved", "body": "Describe your in-house or partner financing options."}, "locked": False},
            ],
            "contact": [
                {"section_key": "contact_form", "fields": {"heading": "Visit Us"}, "locked": False},
            ],
        },
    },
    "independent_modern": {
        "key": "independent_modern",
        "name": "Independent Modern",
        "dealer_type": "independent",
        "description": "A DealerGPT-forward layout -- build-your-car configurator up front, traditional pages still available.",
        "pages": {
            "home": [
                {"section_key": "car_builder", "fields": {"heading": "Build Your Car", "intro_text": "Step through Make, Model, and Trim to find what's on our lot."}, "locked": False},
                {"section_key": "social_links", "fields": {}, "locked": False},
            ],
            "inventory": [
                {"section_key": "inventory_grid", "fields": {"limit": 12}, "locked": False},
            ],
            "contact": [
                {"section_key": "contact_form", "fields": {"heading": "Get In Touch"}, "locked": False},
            ],
        },
    },
    "oem_certified": {
        "key": "oem_certified",
        "name": "OEM Certified Franchise",
        "dealer_type": "franchise",
        "description": "An OEM-compliant layout with a locked manufacturer branding banner up top, matching typical franchise co-op ad requirements.",
        "pages": {
            "home": [
                {"section_key": "oem_branding_banner", "fields": {"oem_name": "Manufacturer Name", "disclaimer": "Independently owned and operated"}, "locked": True},
                {"section_key": "hero_banner", "fields": {"headline": "Welcome to {dealership_name}", "cta_text": "Browse New Inventory"}, "locked": False},
                {"section_key": "google_rating_badge", "fields": {"rating_text": "Add your Google rating here"}, "locked": False},
            ],
            "inventory": [
                {"section_key": "inventory_grid", "fields": {"limit": 12}, "locked": False},
            ],
            "about": [
                {"section_key": "text_block", "fields": {"heading": "About Us", "body": "Tell your dealership's story here."}, "locked": False},
            ],
            "testimonials": [
                {"section_key": "testimonials_carousel", "fields": {"testimonials": "Jane D. | Great experience!"}, "locked": False},
            ],
            "financing": [
                {"section_key": "financing_info", "fields": {"heading": "OEM Financing Offers", "body": "Describe current manufacturer financing/lease offers."}, "locked": False},
            ],
            "contact": [
                {"section_key": "contact_form", "fields": {"heading": "Visit Us"}, "locked": False},
            ],
        },
    },
    "oem_minimal": {
        "key": "oem_minimal",
        "name": "OEM Minimal",
        "dealer_type": "franchise",
        "description": "A lighter-weight OEM-compliant layout -- locked branding banner plus inventory and contact only.",
        "pages": {
            "home": [
                {"section_key": "oem_branding_banner", "fields": {"oem_name": "Manufacturer Name", "disclaimer": "Independently owned and operated"}, "locked": True},
                {"section_key": "hero_banner", "fields": {"headline": "Welcome to {dealership_name}"}, "locked": False},
            ],
            "inventory": [
                {"section_key": "inventory_grid", "fields": {"limit": 12}, "locked": False},
            ],
            "contact": [
                {"section_key": "contact_form", "fields": {"heading": "Visit Us"}, "locked": False},
            ],
        },
    },
}


def list_site_templates(dealer_type=None):

    templates = list(SITE_TEMPLATES.values())

    if dealer_type:
        templates = [t for t in templates if t["dealer_type"] == dealer_type]

    return templates


def get_site_template(template_key):
    return SITE_TEMPLATES.get(template_key)


@studio_content_write
def apply_site_template(website_id, template_key, dealership_name=None, by=None):
    """Lays a template's starter sections onto an existing (typically freshly created,
    empty) site. See SITE_TEMPLATES' module comment above for the OEM pre-lock
    behavior."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    template = get_site_template(template_key)

    if not template:
        return {"error": f"Unknown template '{template_key}'"}

    name = dealership_name or website.attributes.get("name") or "Your Dealership"

    for page_key, sections in template["pages"].items():

        if page_key not in PAGE_KEYS:
            continue

        for section_def in sections:

            fields = {
                k: (v.replace("{dealership_name}", name) if isinstance(v, str) else v)
                for k, v in (section_def.get("fields") or {}).items()
            }

            result = add_section(website.id, page_key, section_def["section_key"], fields, by=by, _skip_save=True)

            if isinstance(result, dict) and "error" in result:
                continue

            if section_def.get("locked"):

                sections_list = website.attributes["pages"][page_key]["sections"]
                set_section_locked(website.id, page_key, len(sections_list) - 1, True, by=by, _skip_save=True)

    if template["dealer_type"] == "franchise":
        update_admin_settings(website.id, {"branding_mode": "oem"}, by=by, _skip_save=True)

    # Session 86 -- every template (all four ship only one home variant today, see
    # SITE_TEMPLATES above) still needs to end up with BOTH a traditional and a
    # DealerGPT home section, same "both built in, customer switches" rule as the AI
    # wizard now follows. Backfill whichever one the template didn't include, with a
    # plain (non-AI) placeholder -- the dealer can AI-regenerate or hand-edit it
    # afterward like any other section.
    home_sections = website.attributes["pages"]["home"]["sections"]
    has_car_builder = any(s["section_key"] == "car_builder" for s in home_sections)
    has_traditional_hero = any(s["section_key"] == "hero_banner" for s in home_sections)

    if not has_car_builder:
        add_section(website.id, "home", "car_builder", {
            "heading": "Build Your Car",
            "intro_text": "Step through Make, Model, and Trim to find what's on our lot.",
        }, by=by, _skip_save=True)

    if not has_traditional_hero:
        add_section(website.id, "home", "hero_banner", {
            "headline": f"Welcome to {name}",
            "subheadline": "Quality vehicles, honest service.",
            "cta_text": "Browse Inventory",
        }, by=by, _skip_save=True)

    _log_history(website, "template_applied", by, notes=f"{template_key}, both home variants ensured")
    website.attributes["updated_at"] = _now()

    # One real save covering every section/lock/admin-settings change above -- see
    # add_section()/set_section_locked()/update_admin_settings()'s own _skip_save
    # comments for why this function passes _skip_save=True to all of them.
    save_graph(GRAPH_PATH)

    return website


def _now():
    return datetime.now(timezone.utc).isoformat()


def _empty_pages():
    return {page_key: {"sections": []} for page_key in PAGE_KEYS}


def _default_admin_settings():
    return {
        "custom_domain": None,
        "meta_title": None,
        "meta_description": None,
        "sitemap_enabled": True,
        "block_ai_crawlers": False,
        "allow_search_engines": True,
        "google_analytics_id": None,
        "umami_site_id": None,
        "umami_script_url": None,
        "facebook_pixel_id": None,
        "custom_head_snippet": None,
        "custom_body_snippet": None,
        "branding_mode": "independent",  # "independent" | "oem"
        "oem_name": None,
        "oem_logo_url": None,
        # Live Chat's AI Receptionist toggle (Marketing Growth Platform's "Live Chat"
        # item, session 113 follow-up) -- when True, an unclaimed chat session with no
        # employee reply yet gets a real, auto-applied AI-drafted response the moment a
        # visitor messages, same auto-apply precedent core/reputation.py's
        # auto_respond_review() already established. Off by default -- a dealer opts in
        # per site rather than every new site silently talking to visitors on its own.
        "ai_receptionist_enabled": False,
        "conversion_goals": [],
        # Per-page SEO (session 85) -- Sam: "adjust the seo per page." Site-wide
        # meta_title/meta_description above stay as the fallback; this dict lets each
        # page override title/description/social-preview-image independently. Merged
        # via update_page_seo(), not the generic update_admin_settings() patch loop, so
        # setting one page's SEO can't accidentally wipe another's.
        "page_seo": {page_key: {"meta_title": None, "meta_description": None, "og_image_url": None} for page_key in PAGE_KEYS},
    }


def _all_websites():
    return [e for e in ledger.get_all().values() if e.entity_type == WEBSITE]


def _log_history(website, action, by, notes=None):
    """Append-only per-site change log -- same shape as
    core/workflow_tracking.py's WorkflowInstance.history, kept as an attribute on the
    entity itself rather than a new store, per this codebase's one-graph rule. Backs
    the "Access & ownership controls" admin-panel requirement (a real per-site edit
    history, not just who last touched it)."""

    website.attributes.setdefault("history", []).append({
        "action": action,
        "by": by,
        "at": _now(),
        "notes": notes,
    })


def create_website(name, created_by, mode="traditional", _skip_save=False):

    if mode not in MODES:
        mode = "traditional"

    website_id = id_generator.generate("SITE")

    entity = Entity(
        id=website_id,
        entity_type=WEBSITE,
        attributes={
            "name": name,
            "status": "draft",
            "mode": mode,
            "pages": _empty_pages(),
            "owners": [created_by] if created_by else [],
            "admin_settings": _default_admin_settings(),
            "history": [],
            "requested_by": created_by,
            "reviewed_by": None,
            "review_notes": None,
            "created_at": _now(),
            "updated_at": _now(),
            "published_at": None,
        },
    )

    _log_history(entity, "created", created_by, notes=f"mode={mode}")

    ledger.add_entity(entity)

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return entity


def create_website_from_wizard(dealership_info, created_by, mode="traditional"):
    """Sam: 'have dealerOS create the website through a setup wizard... let ai write
    the content and set it up.' Drafts real copy via core/website_wizard.py (falling
    back to plain placeholder copy if OpenAI can't be reached), then assembles a full
    Website entity with sections pre-populated.

    Session 86 (Sam, direct follow-up to the session-85 builder: "every website should
    have both a traditional and ChatGPT style built into the site so the customer can
    switch between the two. That doesn't need to be a choice on this side"): every
    wizard-built site now gets BOTH a traditional hero_banner home experience AND a
    DealerGPT car_builder home experience populated for real, regardless of which
    `mode` was picked at creation -- `mode` still controls the AI copy's tone/framing
    (generate_wizard_copy's `mode` param) and which one the site opens to by default,
    but it is no longer a choice about which content exists. render_page() below
    always filters the home page down to whichever variant matches the visitor's
    effective_mode (see get_website_rendered()'s docstring) -- a real, always-live
    customer-facing toggle, not something the builder has to pre-decide. Same
    treatment for About/Testimonials/Financing: always populated now (previously
    dealer_gpt sites left them empty), since a visitor who toggles to Traditional mid-
    visit should land on a real, filled-in site, not empty pages."""

    name = (dealership_info or {}).get("dealership_name") or "New Dealership Site"

    website = create_website(name, created_by, mode=mode)

    copy = generate_wizard_copy(dealership_info, mode=mode)

    if not copy or "error" in copy:
        copy = fallback_copy(dealership_info)

    branding_mode = (dealership_info or {}).get("branding_mode") or "independent"
    social = (dealership_info or {}).get("social_links") or {}

    admin_patch = {"branding_mode": branding_mode}

    if branding_mode == "oem":
        admin_patch["oem_name"] = (dealership_info or {}).get("oem_name")
        admin_patch["oem_logo_url"] = (dealership_info or {}).get("oem_logo_url")

    update_admin_settings(website.id, admin_patch, by=created_by, _skip_save=True)

    # Home page -- BOTH variants, always. car_builder first or hero_banner first
    # doesn't matter for rendering (render_page() filters by effective_mode), but
    # `mode`'s preferred variant is added first so it reads naturally in the raw
    # section list too.
    #
    # Every add_section()/update_admin_settings() call in this function passes
    # _skip_save=True -- a wizard-built site can call add_section() up to ~10 times in
    # one invocation, and a real save_graph() per call (several seconds each on this
    # graph's size) would make one wizard run take the better part of a minute. One
    # real save happens once, at the very end of this function, covering everything.
    def _add_car_builder():
        add_section(website.id, "home", "car_builder", {
            "heading": copy.get("hero_headline") or "Build Your Car",
            "intro_text": copy.get("hero_subheadline") or "",
        }, by=created_by, _skip_save=True)

    def _add_traditional_hero():
        add_section(website.id, "home", "hero_banner", {
            "headline": copy.get("hero_headline"),
            "subheadline": copy.get("hero_subheadline"),
            "image_url": (dealership_info or {}).get("hero_image_url"),
        }, by=created_by, _skip_save=True)

        if (dealership_info or {}).get("google_rating_text"):
            add_section(website.id, "home", "google_rating_badge", {
                "rating_text": dealership_info["google_rating_text"],
                "google_place_id": dealership_info.get("google_place_id"),
            }, by=created_by, _skip_save=True)

        if branding_mode == "oem" and (dealership_info or {}).get("oem_name"):
            add_section(website.id, "home", "oem_branding_banner", {
                "oem_name": dealership_info.get("oem_name"),
                "oem_logo_url": dealership_info.get("oem_logo_url"),
                "disclaimer": None,
            }, by=created_by, _skip_save=True)

    if mode == "dealer_gpt":
        _add_car_builder()
        _add_traditional_hero()
    else:
        _add_traditional_hero()
        _add_car_builder()

    if any(social.get(k) for k in ("facebook", "instagram", "tiktok", "x")):
        add_section(website.id, "home", "social_links", {
            "facebook_url": social.get("facebook"),
            "instagram_url": social.get("instagram"),
            "tiktok_url": social.get("tiktok"),
            "x_url": social.get("x"),
        }, by=created_by, _skip_save=True)

    # Inventory page -- always the live grid, both modes.
    add_section(website.id, "inventory", "inventory_grid", {"limit": 12}, by=created_by, _skip_save=True)

    # Contact page -- always filled in from the basics given, both modes.
    add_section(website.id, "contact", "contact_form", {
        "heading": copy.get("contact_heading") or "Get In Touch",
        "phone": (dealership_info or {}).get("phone"),
        "address": (dealership_info or {}).get("address"),
    }, by=created_by, _skip_save=True)

    # About/Testimonials/Financing -- always populated now (session 86), so toggling
    # to Traditional mid-visit is never a dead end.
    add_section(website.id, "about", "text_block", {
        "heading": copy.get("about_heading") or "About Us",
        "body": copy.get("about_body"),
    }, by=created_by, _skip_save=True)

    if copy.get("testimonials"):
        add_section(website.id, "testimonials", "testimonials_carousel", {
            "testimonials": copy.get("testimonials"),
        }, by=created_by, _skip_save=True)

    add_section(website.id, "financing", "financing_info", {
        "heading": copy.get("financing_heading") or "Get Pre-Approved",
        "body": copy.get("financing_body"),
    }, by=created_by, _skip_save=True)

    _log_history(website, "wizard_generated", created_by, notes=f"mode={mode}, both home variants built")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


def get_website(website_id):

    entity = ledger.get_entity(website_id)

    if entity and entity.entity_type == WEBSITE:
        # Backfill fields for any site created before session 58 so old drafts don't
        # crash the new admin/lock/ownership code paths.
        entity.attributes.setdefault("mode", "traditional")
        entity.attributes.setdefault("owners", [entity.attributes.get("requested_by")] if entity.attributes.get("requested_by") else [])
        entity.attributes.setdefault("admin_settings", _default_admin_settings())
        entity.attributes["admin_settings"].setdefault(
            "page_seo",
            {page_key: {"meta_title": None, "meta_description": None, "og_image_url": None} for page_key in PAGE_KEYS},
        )
        entity.attributes.setdefault("history", [])
        entity.attributes.setdefault("image_library", [])
        return entity

    return None


def is_owner(website, employee_id):
    return employee_id in (website.attributes.get("owners") or [])


def add_owner(website_id, employee_id, by):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    owners = website.attributes.setdefault("owners", [])

    if employee_id not in owners:
        owners.append(employee_id)
        _log_history(website, "owner_added", by, notes=employee_id)
        website.attributes["updated_at"] = _now()
        save_graph(GRAPH_PATH)

    return website


def remove_owner(website_id, employee_id, by):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    owners = website.attributes.setdefault("owners", [])

    if employee_id in owners:
        owners.remove(employee_id)
        _log_history(website, "owner_removed", by, notes=employee_id)
        website.attributes["updated_at"] = _now()
        save_graph(GRAPH_PATH)

    return website


@studio_content_write
def add_section(website_id, page_key, section_key, fields, by=None, _skip_save=False):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    template = get_section_template(section_key)

    if not template:
        return {"error": f"Unknown section template '{section_key}'"}

    missing = [
        f["key"]
        for f in template["fields"]
        if f.get("required") and not (fields or {}).get(f["key"])
    ]

    if missing:
        return {"error": f"Missing required field(s): {', '.join(missing)}"}

    website.attributes["pages"][page_key]["sections"].append({
        "section_key": section_key,
        "fields": fields or {},
        "locked": False,
    })

    _log_history(website, "section_added", by, notes=f"{page_key}/{section_key}")
    website.attributes["updated_at"] = _now()

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return website


@studio_content_write
def update_section_fields(website_id, page_key, section_index, fields, by=None):
    """Manual in-place field edit (session 85) -- the gap between add_section()
    (append-only, creates a NEW section) and regenerate_section() (AI-only, rewrites
    only ai_writable fields): a builder editing a section's plain values by hand (an
    image URL, a phone number, a heading they don't want AI-rewritten) needs to patch
    the EXISTING section in place, preserving its position and locked state, rather
    than remove-then-re-add. Merges only the keys present in `fields` onto the
    section's existing fields dict, same partial-patch shape as update_admin_settings()."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    section = sections[section_index]

    if section.get("locked"):
        return {"error": "This section is locked and cannot be edited."}

    section["fields"].update(fields or {})

    _log_history(website, "section_edited", by, notes=f"{page_key}[{section_index}]")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def remove_section(website_id, page_key, section_index, by=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    removed = sections.pop(section_index)

    _log_history(website, "section_removed", by, notes=f"{page_key}/{removed.get('section_key')}")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def set_section_locked(website_id, page_key, section_index, locked, by=None, _skip_save=False):
    """Sam: 'we can lock stuff if we feel they'll mess it up' -- a locked section can
    still be added freely (locking is a per-section flag, not a template restriction),
    but core/websites_api.py's remove_section_api refuses to let a non-reviewer remove
    a locked section, and the frontend hides its edit affordance for anyone but ADMIN/
    MARKETING or a site owner with review rights."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    sections[section_index]["locked"] = bool(locked)

    _log_history(
        website,
        "section_locked" if locked else "section_unlocked",
        by,
        notes=f"{page_key}[{section_index}]",
    )
    website.attributes["updated_at"] = _now()

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return website


@studio_content_write
def reorder_sections(website_id, page_key, new_order, by=None):
    """The drag-and-drop canvas's reorder action (session 85). `new_order` is a list of
    the page's CURRENT section indices in the desired new order (e.g. [2, 0, 1]) --
    validated as a real permutation of the existing indices before applying, so a
    stale/partial drag payload can't silently drop or duplicate a section."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if sorted(new_order) != list(range(len(sections))):
        return {"error": "new_order must be a permutation of the page's current section indices"}

    website.attributes["pages"][page_key]["sections"] = [sections[i] for i in new_order]

    _log_history(website, "sections_reordered", by, notes=page_key)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


# Website Personalization (2026-07-19, closing the second half of Sam's "AI Marketing
# Studio + Website Personalization" pillar item). A PersonalizationVariant is NOT a
# separate entity and NOT a second copy of a section -- it's a small, targeted overlay
# stored in a new `personalization_variants` list directly on the section dict itself
# (same additive-list-on-an-existing-attribute convention `Deal.trade_in`/
# `Vehicle.price_history`/`vendor_assignments` already established elsewhere in this
# codebase), matched against a real visitor signal (`utm_source`/the raw `Referer`
# header) at RENDER TIME by render_page()/get_website_rendered() -- the section's own
# stored `fields` are never mutated, only overlaid onto a rendered COPY for that one
# request. The "PVAR" id-generator prefix (already registered) backs each variant's own
# id within that list. A locked section can't be personalized either -- same rule
# update_section_fields()/regenerate_section_copy() already enforce for manual/AI edits,
# since a locked section is meant to stay exactly as MARKETING/ADMIN set it.
@studio_content_write
def add_personalization_variant(website_id, page_key, section_index, match, field_overrides, by=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    section = sections[section_index]

    if section.get("locked"):
        return {"error": "This section is locked and cannot be personalized."}

    match = match or {}
    utm_source = (match.get("utm_source") or "").strip() or None
    referrer_contains = (match.get("referrer_contains") or "").strip() or None

    if not utm_source and not referrer_contains:
        return {"error": "A variant needs at least one match rule: utm_source or referrer_contains."}

    real_overrides = {k: v for k, v in (field_overrides or {}).items() if v not in (None, "")}

    if not real_overrides:
        return {"error": "A variant needs at least one real field override value."}

    variant = {
        "id": id_generator.generate("PVAR"),
        "match": {"utm_source": utm_source, "referrer_contains": referrer_contains},
        "field_overrides": real_overrides,
        "created_by": by,
        "created_at": _now(),
    }

    section.setdefault("personalization_variants", []).append(variant)

    _log_history(
        website,
        "personalization_variant_added",
        by,
        notes=f"{page_key}[{section_index}] -> {variant['id']}",
    )
    website.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def remove_personalization_variant(website_id, page_key, section_index, variant_id, by=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    section = sections[section_index]
    variants = section.get("personalization_variants") or []
    match_idx = next((i for i, v in enumerate(variants) if v.get("id") == variant_id), None)

    if match_idx is None:
        return {"error": f"No personalization variant '{variant_id}' on that section"}

    variants.pop(match_idx)

    _log_history(
        website,
        "personalization_variant_removed",
        by,
        notes=f"{page_key}[{section_index}] -> {variant_id}",
    )
    website.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return website


def list_personalization_variants(website_id, page_key, section_index):
    """Read-only -- core/websites_api.py gates this the same as any other builder read
    (this site's own builder/owners, or MARKETING/ADMIN)."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    return {"variants": sections[section_index].get("personalization_variants") or []}


def _select_personalization_variant(section, utm_source, referrer):
    """Real, transparent matching -- NOT "most specific wins" (deliberately simpler and
    more predictable): the FIRST variant in the section's own list whose every set match
    rule is satisfied by the real visitor signal wins. A variant with both `utm_source`
    and `referrer_contains` set requires BOTH to match (an AND, not an OR) -- a variant
    with only one set only needs that one. Returns None (no personalization) when no
    variant matches, or when the caller supplied neither signal at all."""

    if not utm_source and not referrer:
        return None

    for variant in (section.get("personalization_variants") or []):

        match = variant.get("match") or {}
        criteria_checked = False
        satisfied = True

        if match.get("utm_source"):
            criteria_checked = True
            if not utm_source or match["utm_source"] != utm_source:
                satisfied = False

        if match.get("referrer_contains"):
            criteria_checked = True
            if not referrer or match["referrer_contains"].lower() not in referrer.lower():
                satisfied = False

        if criteria_checked and satisfied:
            return variant

    return None


# Freeform drag-and-drop canvas (2026-07-18, Cowork, interactive) -- Sam: "have a
# button that says edit website where you can open it up fully into a wix drag and
# drop, fully editable website builder." Session 90 shipped the near-term version (a
# maximized visual-preview + side-panel editor); this is the real, deferred, "much
# larger build" -- a true pixel-freeform canvas mode a page can be switched into,
# where every section gets a real, stored x/y/width/height instead of only ever being
# a strict top-to-bottom stack. Deliberately additive, not a replacement: a page
# defaults to (and can always switch back to) "structured" mode, which is byte-for-
# byte today's existing stacked-flow behavior with `layout` data on a section simply
# ignored. Layering/z-order is NOT a new field -- it reuses the section list's own
# existing order (later in the array paints on top, same as any HTML document flow),
# so "bring to front"/"send to back" is just a reorder_sections() call, already real.
CANVAS_WIDTH = 1200
_DEFAULT_SECTION_HEIGHT = 320
_DEFAULT_SECTION_GAP = 24


@studio_content_write
def set_page_layout_mode(website_id, page_key, mode, by=None):
    """Switches a page between "structured" (today's stacked flow) and "canvas"
    (freeform x/y/width/height positioning). Switching TO canvas for the first time
    auto-backfills a real, deterministic default layout (stacked top-to-bottom, full
    canvas width) for any section that doesn't have one yet, so a page never renders
    with sections piled on top of each other at (0, 0) the moment canvas mode turns
    on -- the dealer sees their existing page laid out exactly as it already looked,
    now with real handles to drag/resize from there."""

    if mode not in ("structured", "canvas"):
        return {"error": "mode must be 'structured' or 'canvas'"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    page = website.attributes["pages"][page_key]
    sections = page["sections"]

    if mode == "canvas":

        running_y = 0

        for section in sections:

            if not section.get("layout"):
                section["layout"] = {
                    "x": 0,
                    "y": running_y,
                    "width": CANVAS_WIDTH,
                    "height": _DEFAULT_SECTION_HEIGHT,
                }

            layout = section["layout"]
            running_y = layout["y"] + layout["height"] + _DEFAULT_SECTION_GAP

    page["layout_mode"] = mode

    _log_history(website, "layout_mode_changed", by, notes=f"{page_key} -> {mode}")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def set_section_layout(website_id, page_key, section_index, x, y, width, height, by=None):
    """Real drag/resize persistence -- called on mouse-up at the end of a drag or
    resize gesture (the frontend tracks the live position/size locally during the
    gesture itself and only calls this once it settles, so a drag doesn't spam a real
    save_graph() call, which costs several seconds on this graph's size, on every
    mousemove). Locked sections can't be moved or resized, same rule
    update_section_fields() already enforces for field edits."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    section = sections[section_index]

    if section.get("locked"):
        return {"error": "This section is locked and cannot be moved or resized."}

    try:
        x = float(x)
        y = float(y)
        width = float(width)
        height = float(height)
    except (TypeError, ValueError):
        return {"error": "x/y/width/height must be numbers"}

    if width < 40 or height < 40:
        return {"error": "width and height must be at least 40px"}

    if x < 0 or y < 0:
        return {"error": "x and y must be non-negative"}

    section["layout"] = {"x": x, "y": y, "width": width, "height": height}

    _log_history(website, "section_layout_changed", by, notes=f"{page_key}[{section_index}]")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def add_library_image(website_id, url, label=None, by=None):
    """A site-level image library (session 85) -- Sam: 'image selection.' A flat list
    attribute on the Website entity, same one-entity-many-attributes pattern as
    pages/admin_settings/history, rather than a new entity type: these are dealer-
    supplied photo URLs the builder can pick from when filling a section's image
    field(s), not a new kind of graph-wide asset."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not url:
        return {"error": "url is required"}

    image_id = id_generator.generate("LIBIMG")

    website.attributes.setdefault("image_library", []).append({
        "id": image_id,
        "url": url,
        "label": label,
        "added_by": by,
        "added_at": _now(),
    })

    _log_history(website, "library_image_added", by, notes=image_id)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def remove_library_image(website_id, image_id, by=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    library = website.attributes.setdefault("image_library", [])
    before = len(library)

    website.attributes["image_library"] = [img for img in library if img["id"] != image_id]

    if len(website.attributes["image_library"]) == before:
        return {"error": f"No library image with id '{image_id}'"}

    _log_history(website, "library_image_removed", by, notes=image_id)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


def list_library_images(website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    return website.attributes.get("image_library", [])


@studio_content_write
def regenerate_section(website_id, page_key, section_index, instructions=None, by=None):
    """The per-section 'AI writing abilities' action (session 85) -- rewrites only the
    section's ai_writable fields (SECTION_TEMPLATES[...]["fields"][*]["ai_writable"]),
    leaving image URLs/phone numbers/filters/legally-sensitive fields untouched. On an
    OpenAI failure, the section's existing fields are left exactly as they were (same
    fallback discipline as the whole-site wizard) and an 'error' key is returned
    alongside the unchanged website so the caller can surface it without losing data."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    sections = website.attributes["pages"][page_key]["sections"]

    if section_index < 0 or section_index >= len(sections):
        return {"error": f"No section at index {section_index} on page '{page_key}'"}

    section = sections[section_index]

    if section.get("locked"):
        return {"error": "This section is locked and cannot be AI-regenerated."}

    template = get_section_template(section["section_key"])

    if not template:
        return {"error": f"Unknown section template '{section['section_key']}'"}

    writable_fields = [f for f in template["fields"] if f.get("ai_writable")]

    if not writable_fields:
        return {"error": "This section has no AI-writable fields."}

    text_fields = [
        {"key": f["key"], "label": f["label"], "current_value": section["fields"].get(f["key"])}
        for f in writable_fields
    ]

    result = regenerate_section_copy(
        template["name"],
        text_fields,
        dealership_name=website.attributes.get("name"),
        instructions=instructions,
    )

    if not result or "error" in result:
        return {"error": (result or {}).get("error", "AI regeneration failed"), "website": website}

    for field in writable_fields:
        if field["key"] in result:
            section["fields"][field["key"]] = result[field["key"]]

    _log_history(website, "section_ai_regenerated", by, notes=f"{page_key}[{section_index}]")
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def update_page_seo(website_id, page_key, patch, by=None):
    """Per-page SEO (session 85) -- Sam: 'adjust the seo per page.' Merges only the
    named page's meta_title/meta_description/og_image_url, leaving every other page's
    SEO settings (and the rest of admin_settings) untouched -- deliberately its own
    function rather than routed through the generic update_admin_settings() patch loop,
    since that loop replaces a whole top-level key at once and page_seo is itself a
    dict keyed by every page."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    settings = website.attributes.setdefault("admin_settings", _default_admin_settings())
    page_seo = settings.setdefault(
        "page_seo",
        {pk: {"meta_title": None, "meta_description": None, "og_image_url": None} for pk in PAGE_KEYS},
    )
    page_entry = page_seo.setdefault(page_key, {"meta_title": None, "meta_description": None, "og_image_url": None})

    for key in ("meta_title", "meta_description", "og_image_url"):
        if key in (patch or {}):
            page_entry[key] = patch[key]

    _log_history(website, "page_seo_updated", by, notes=page_key)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


def get_page_seo(website_id, page_key):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    settings = website.attributes.get("admin_settings") or {}
    page_seo = settings.get("page_seo") or {}

    return page_seo.get(page_key, {"meta_title": None, "meta_description": None, "og_image_url": None})


@serialized_website_write
def submit_contact_form(website_id, page_key, section_index, name, email=None, phone=None, message=None, vehicle_id=None, intent=None, request_id=None):
    """Capture a canonical CRM lead with provenance in its first durable write.

    Optional visitor UUID scopes retries to this tenant's website. The same key
    cannot overwrite or reuse a different inquiry. No second lead store is used.
    """
    import hashlib
    import json
    from uuid import UUID
    from copy import deepcopy

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    if request_id is not None:
        try:
            request_id = str(UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            return {"error": "A valid inquiry request ID is required"}
    name = (name or "").strip()
    email = (email or "").strip()
    phone = (phone or "").strip()
    fingerprint = hashlib.sha256(json.dumps(
        [page_key, section_index, name, email, phone, message or "", vehicle_id, intent],
        ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if request_id:
        for existing in ledger.get_all().values():
            attrs = existing.attributes
            if existing.entity_type == "Lead" and attrs.get("WebsiteID") == website_id and attrs.get("WebsiteRequestID") == request_id:
                if attrs.get("WebsiteInquiryFingerprint") != fingerprint:
                    return {"error": "This inquiry was already sent with different details. Start a new request."}
                return {"lead_id": existing.id, "assigned_to": attrs.get("AssignedSalesperson")}
    if intent not in (None, "information", "test_drive", "purchase", "financing", "trade"):
        return {"error": "Choose a valid inquiry type"}
    vehicle = ledger.get_entity(vehicle_id) if vehicle_id else None
    if vehicle_id and (not vehicle or vehicle.entity_type != VEHICLE or vehicle.attributes.get("DateSold")):
        return {"error": "The selected vehicle is unavailable. Please choose another vehicle."}
    if website.attributes.get("studio_config"):
        rendered = get_website_rendered(website_id, published=True)
        sections = rendered["pages"][page_key]["sections"]
        if type(section_index) is not int or section_index < 0 or section_index >= len(sections) or sections[section_index]["section_key"] != "contact_form":
            return {"error": "This contact form is no longer available. Refresh the page."}
    if not name or not (email or phone):
        return {"error": "name and at least one of email/phone are required"}

    owners = website.attributes.get("owners") or []
    assignee = owners[0] if owners else website.attributes.get("requested_by")

    if not assignee:
        return {"error": "This site has no owner to route the lead to -- add an owner first."}

    parts = name.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    previous_history = deepcopy(website.attributes.get("history", []))
    previous_updated = website.attributes.get("updated_at")
    _log_history(website, "contact_form_submitted", None, notes=f"page={page_key}")
    website.attributes["updated_at"] = _now()
    try:
        lead = create_lead(
            created_by=assignee, first_name=first_name, last_name=last_name,
            source="Website", phone=phone, email=email,
            vin=vehicle.attributes.get("VIN") if vehicle else None,
            message=message or "", website_id=website_id, contact_page=page_key,
            contact_section_index=section_index, website_request_id=request_id,
            inquiry_fingerprint=fingerprint, inquiry_intent=intent,
            interested_vehicle_id=vehicle.id if vehicle else None,
        )
    except Exception:
        website.attributes["history"] = previous_history
        website.attributes["updated_at"] = previous_updated
        raise

    return {"lead_id": lead.id, "assigned_to": assignee}


@studio_content_write
def set_mode(website_id, mode, by=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if mode not in MODES:
        return {"error": f"Unknown mode '{mode}' -- must be one of {MODES}"}

    website.attributes["mode"] = mode
    _log_history(website, "mode_changed", by, notes=mode)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@studio_content_write
def update_admin_settings(website_id, patch, by=None, _skip_save=False):
    """Merges a partial admin_settings patch onto the site -- DNS/SEO/bot/analytics/
    branding fields all live in one flat dict (see _default_admin_settings()) rather
    than nested sub-objects, keeping the patch shape simple for the frontend's one
    settings form. Unknown keys in `patch` are ignored rather than raising, so an older
    frontend build sending a stale shape can't corrupt the site record.

    `_skip_save` lets a batch-calling function (e.g. create_website_from_wizard(),
    apply_site_template()) defer persistence to its own single trailing save_graph()
    call, same convention as add_section()/set_section_locked()."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if "custom_domain" in (patch or {}):
        domain = patch["custom_domain"]
        if domain is not None:
            if not isinstance(domain, str):
                return {"error": "Enter a valid website hostname, such as www.yourdealership.com"}
            domain = domain.strip().lower().rstrip('.')
            labels = domain.split('.')
            if domain and (len(domain) > 253 or len(labels) < 2 or not all(
                __import__('re').fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                for label in labels) or labels[-1].isdigit()):
                return {"error": "Enter only a valid hostname, without https://, ports, or a page path"}
            patch = {**patch, "custom_domain": domain or None}

    if "conversion_goals" in (patch or {}):
        goals = patch["conversion_goals"]
        if not isinstance(goals, list) or len(goals) > 7:
            return {"error": "Choose up to seven conversion goals"}
        seen = set()
        for goal in goals:
            if not isinstance(goal, dict) or set(goal) != {"metric", "target", "enabled"}:
                return {"error": "Invalid conversion goal"}
            if goal["metric"] not in ("all", "information", "test_drive", "purchase", "financing", "trade", "assistant") or goal["metric"] in seen:
                return {"error": "Invalid or duplicate conversion goal"}
            if type(goal["target"]) is not int or not 1 <= goal["target"] <= 100000 or type(goal["enabled"]) is not bool:
                return {"error": "Goal targets must be whole numbers between 1 and 100000"}
            seen.add(goal["metric"])
    if "ai_receptionist_enabled" in (patch or {}) and type(patch["ai_receptionist_enabled"]) is not bool:
        return {"error": "Assistant setting must be true or false"}

    if "google_analytics_id" in (patch or {}):
        value = patch["google_analytics_id"]
        if value and (not isinstance(value, str) or not __import__('re').fullmatch(r'G-[A-Z0-9]{4,20}', value)):
            return {"error": "Enter a valid GA4 measurement ID (G-...)"}

    settings = website.attributes.setdefault("admin_settings", _default_admin_settings())
    changed = []

    for key in _default_admin_settings().keys():
        if key in (patch or {}):
            settings[key] = patch[key]
            changed.append(key)

    if changed:
        _log_history(website, "admin_settings_updated", by, notes=", ".join(changed))
        website.attributes["updated_at"] = _now()

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return website


def get_dns_instructions(website_id):
    """The honest DNS non-integration -- see module docstring. Returns the exact CNAME
    record the dealer needs to create at their own registrar, not anything NXTDeal
    actually provisions."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    domain = (website.attributes.get("admin_settings") or {}).get("custom_domain")

    if not domain:
        return {
            "configured": False,
            "note": "No custom domain set yet -- add one in Admin Settings first.",
        }

    import os
    assigned = os.environ.get('NXT_WEBSITE_SITE_ID') == website_id and os.environ.get('NXT_WEBSITE_ALLOWED_DOMAIN') == domain
    target = os.environ.get('NXT_WEBSITE_DNS_TARGET') if assigned else None
    kind = os.environ.get('NXT_WEBSITE_DNS_TYPE', 'CNAME') if assigned else 'CNAME'
    if not assigned:
        try:
            from core.website_provisioning import settings as hosting_settings
            addresses = sorted(hosting_settings()['addresses'])
            ipv4 = [ip for ip in addresses if ':' not in ip]
            target = ipv4[0] if ipv4 else addresses[0]
            kind = 'A' if ipv4 else 'AAAA'
        except ValueError:
            pass
    return {
        "configured": bool(target), "custom_domain": domain,
        "record_type": kind, "record_host": domain, "record_target": target,
        "note": "Use the platform-assigned record. Keep email records unchanged." if target else "NXTDeal must assign a hosting target before DNS routing instructions are available.",
    }



def get_robots_txt(website_id, published=False):
    """Generates robots.txt content from the site's bot-control admin settings.
    `block_ai_crawlers` adds explicit Disallow entries for the well-known AI-crawler
    user-agents; `allow_search_engines` toggles a blanket Allow/Disallow for everyone
    else. Real, generated text -- not a static file."""

    website = get_website(website_id)
    if published:
        website = public_version(website)

    if not website:
        return {"error": "Website not found"}

    settings = website.attributes.get("admin_settings") or {}
    lines = []

    if settings.get("block_ai_crawlers"):
        for agent in ("GPTBot", "CCBot", "ClaudeBot", "Google-Extended", "anthropic-ai"):
            lines.append(f"User-agent: {agent}")
            lines.append("Disallow: /")
            lines.append("")

    lines.append("User-agent: *")
    lines.append("Disallow: /" if not settings.get("allow_search_engines", True) else "Allow: /")

    if settings.get("sitemap_enabled", True):
        domain = settings.get("custom_domain") or DNS_TARGET_HOSTNAME
        lines.append("")
        lines.append(f"Sitemap: https://{domain}/sitemap.xml")

    return {"robots_txt": "\n".join(lines)}


def _first_vehicle_image_url(vehicle_id):
    """Best-effort lookup of a dealer-supplied photo linked to a vehicle via the
    existing HAS_IMAGE relationship (core/relationship_types.py) -- no fixed schema on
    Image entities (core/imports/image_import.py loads whatever CSV columns exist), so
    this tries the handful of column names a real import would plausibly use rather than
    assuming one. Returns None (not an error) if nothing's linked."""

    for rel in ledger.get_relationships():

        if rel.source_id == vehicle_id and rel.relationship_type == "HAS_IMAGE":

            image = ledger.get_entity(rel.target_id)

            if image and image.entity_type == IMAGE:

                for key in ("URL", "ImageURL", "url", "PhotoURL"):

                    value = image.attributes.get(key)

                    if value:
                        return value

    return None


def _all_vehicle_image_urls(vehicle_id):
    """Every dealer-supplied photo linked to a vehicle via HAS_IMAGE, not just the
    first one (see _first_vehicle_image_url() above) -- a real Vehicle Detail Page
    (session 113 follow-up's VDP slice) needs a full gallery, not one cover shot."""

    urls = []

    for rel in ledger.get_relationships():

        if rel.source_id == vehicle_id and rel.relationship_type == "HAS_IMAGE":

            image = ledger.get_entity(rel.target_id)

            if image and image.entity_type == IMAGE:

                for key in ("URL", "ImageURL", "url", "PhotoURL"):

                    value = image.attributes.get(key)

                    if value:
                        urls.append(value)
                        break

    return urls


def _unsold_vehicles():
    return [
        v for v in ledger.get_all().values()
        if v.entity_type == VEHICLE and not v.attributes.get("DateSold")
    ]


def website_locations():
    """Public location directory, without initializing or mutating settings."""
    locations = []
    for location in ledger.get_all().values():
        if location.entity_type == "Location":
            attrs = location.attributes
            locations.append({"id": location.id, "name": str(attrs.get("name") or attrs.get("Name") or ""), "address": str(attrs.get("address") or attrs.get("Address") or "")})
    settings = ledger.get_entity("SYSCFG-00001")
    if settings and settings.entity_type == "SystemConfig":
        for loc in settings.attributes.get("locations", []):
            if loc.get("name"):
                locations.append({"id": "name:" + str(loc["name"]), "name": str(loc["name"]), "address": str(loc.get("address") or "")})
    return locations


def website_vehicle_location(vehicle):
    """Resolve only tenant-owned, canonical public location fields; never raw IDs."""
    reference = vehicle.attributes.get("location_id") or vehicle.attributes.get("LocationId")
    if reference:
        location = ledger.get_entity(str(reference))
        if location and location.entity_type == "Location":
            attrs = location.attributes
            return {"location_id": location.id, "location_name": str(attrs.get("name") or attrs.get("Name") or ""), "location_address": str(attrs.get("address") or attrs.get("Address") or "")}
        return {"location_id": None, "location_name": None, "location_address": None}
    # Older organization settings store named rooftops rather than Location entities.
    name = vehicle.attributes.get("Location") or vehicle.attributes.get("location")
    settings = ledger.get_entity("SYSCFG-00001")
    if name and settings and settings.entity_type == "SystemConfig":
        matches = [loc for loc in settings.attributes.get("locations", []) if loc.get("name") == name]
        if len(matches) == 1:
            return {"location_id": "name:" + str(name), "location_name": str(name), "location_address": str(matches[0].get("address") or "")}
    return {"location_id": None, "location_name": None, "location_address": None}


def get_live_inventory(make=None, model=None, trim=None, max_price=None, limit=12, location_id=None):
    """The DriveFinder-lite piece -- queries the Vehicle entities already in the graph
    at request time rather than storing a copy, so the inventory page (and the
    DealerGPT car builder below) is always current with whatever's actually in stock.
    Only lists vehicles that haven't sold yet (no DateSold)."""

    vehicles = _unsold_vehicles()

    make = (make or "").strip().lower()
    model = (model or "").strip().lower()
    trim = (trim or "").strip().lower()

    try:
        max_price = float(max_price) if max_price not in (None, "") else None
    except (TypeError, ValueError):
        max_price = None

    try:
        limit = int(limit) if limit not in (None, "") else 12
    except (TypeError, ValueError):
        limit = 12

    results = []

    for vehicle in vehicles:

        if make and str(vehicle.attributes.get("Make", "")).strip().lower() != make:
            continue

        if model and str(vehicle.attributes.get("Model", "")).strip().lower() != model:
            continue

        if trim and str(vehicle.attributes.get("Trim", "")).strip().lower() != trim:
            continue

        if max_price is not None:

            try:
                price = float(vehicle.attributes.get("Price") or 0)
            except (TypeError, ValueError):
                price = 0

            if price > max_price:
                continue

        location = website_vehicle_location(vehicle)
        if location_id and location["location_id"] != location_id:
            continue
        results.append({
            **location,
            "id": vehicle.id,
            "year": vehicle.attributes.get("Year"),
            "make": vehicle.attributes.get("Make"),
            "model": vehicle.attributes.get("Model"),
            "trim": vehicle.attributes.get("Trim"),
            "price": vehicle.attributes.get("Price"),
            "mileage": vehicle.attributes.get("Mileage"),
            "image_url": _first_vehicle_image_url(vehicle.id),
            "photos": _all_vehicle_image_urls(vehicle.id),
            "badge": str(vehicle.attributes.get("WebsiteBadge") or ("Featured" if vehicle.attributes.get("Featured") is True else ""))[:32],
            "body_type": vehicle.attributes.get("BodyStyle") or vehicle.attributes.get("BodyType") or "",
            "stock": vehicle.attributes.get("StockNumber") or "",
            "vin": vehicle.attributes.get("VIN") or "",
            "fuel": vehicle.attributes.get("FuelType") or "",
            "drive": vehicle.attributes.get("Drivetrain") or "",
            "transmission": vehicle.attributes.get("Transmission") or "",
            "exterior": vehicle.attributes.get("ExteriorColor") or "",
            "interior": vehicle.attributes.get("InteriorColor") or "",

        })

        if len(results) >= limit:
            break

    return results


def get_car_builder_options():
    """DealerGPT 'build your car' configurator -- Sam: 'a stripped down dealer branded
    version of DriveFinder.xyz that they can build their car into whats available on
    the lot.' Groups live (unsold) inventory into Make -> Model -> Trim, each level
    carrying a real count and price range computed from the graph at fetch time -- the
    same no-parallel-inventory-copy rule as get_live_inventory(). This is the data the
    frontend's step-through Make/Model/Trim picker renders."""

    vehicles = _unsold_vehicles()

    by_make = {}

    for vehicle in vehicles:

        make = (vehicle.attributes.get("Make") or "Unknown").strip()
        model = (vehicle.attributes.get("Model") or "Unknown").strip()
        trim = (vehicle.attributes.get("Trim") or "Base").strip()

        try:
            price = float(vehicle.attributes.get("Price") or 0)
        except (TypeError, ValueError):
            price = 0

        by_make.setdefault(make, {}).setdefault(model, {}).setdefault(trim, []).append(price)

    result = []

    for make in sorted(by_make.keys()):

        models_out = []

        for model in sorted(by_make[make].keys()):

            trims_out = []

            for trim in sorted(by_make[make][model].keys()):

                prices = [p for p in by_make[make][model][trim] if p > 0]

                trims_out.append({
                    "trim": trim,
                    "count": len(by_make[make][model][trim]),
                    "price_min": min(prices) if prices else None,
                    "price_max": max(prices) if prices else None,
                })

            models_out.append({"model": model, "trims": trims_out})

        result.append({"make": make, "models": models_out})

    return result


def get_vehicle_landing_page(website_id, vehicle_id):
    """Real Vehicle Detail Page data (session 113 follow-up -- the last of the
    "AI-generated location/vehicle pages" item flagged open on Website's remaining
    Wix-level asks list since session 90). Confirmed before writing this: nothing
    anywhere in this codebase ever gave a vehicle its own indexable public page --
    `render_page()`'s `inventory_grid` only ever resolved a flat grid list
    (get_live_inventory(), real but shallow: year/make/model/trim/price/mileage/one
    image). A real dealership website needs a real VDP per vehicle -- full attributes,
    every photo, and a description -- for both visitor usability and SEO (this is why
    core/website_seo.py's get_sitemap_xml() now lists one per real unsold vehicle
    alongside it).

    Only serves a PUBLISHED site's vehicles (an unpublished draft has nothing real to
    show a visitor yet, same gate get_website_rendered() already applies). Does NOT
    gate on the vehicle still being unsold -- a real visitor who bookmarked/shared a
    VDP for a vehicle that has since sold should see an honest "no longer available"
    state, not a dead 404, so `available` is returned as its own real, computed field
    rather than hiding the vehicle entirely."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not has_public_version(website):
        return {"error": "This website is not published"}

    vehicle = ledger.get_entity(vehicle_id)

    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": "Vehicle not found"}

    attrs = vehicle.attributes
    published_content = website.attributes.get("published_snapshot") or website.attributes
    cached = (published_content.get("vehicle_pages") or {}).get(vehicle_id)

    return {
        **website_vehicle_location(vehicle),
        "website_id": website_id,
        "website_name": published_content.get("name"),
        "theme_id": (published_content.get("studio_config") or {}).get("theme_id"),
        "social_links": deepcopy((published_content.get("studio_config") or {}).get("social_links", {})),
        "vehicle_id": vehicle_id,
        "available": not bool(attrs.get("DateSold")),
        "year": attrs.get("Year"),
        "make": attrs.get("Make"),
        "model": attrs.get("Model"),
        "trim": attrs.get("Trim"),
        "color": attrs.get("Color"),
        "condition": attrs.get("Condition"),
        "mileage": attrs.get("Mileage"),
        "price": attrs.get("Price"),
        "vin": attrs.get("VIN"),
        "stock_number": attrs.get("StockNumber"),
        "images": _all_vehicle_image_urls(vehicle_id),
        "description": (cached or {}).get("description"),
        "description_ai_generated": (cached or {}).get("ai_generated", False),
        "description_generated_at": (cached or {}).get("generated_at"),
    }


@studio_content_write
def generate_vehicle_page_description(website_id, vehicle_id, by=None):
    """The AI-drafting half of the VDP -- generates a real description grounded in
    the vehicle's own on-file attributes (core/website_wizard.py's
    generate_vehicle_description(), same isolated no-tool-calling OpenAI client every
    other wizard function in this codebase uses) and CACHES it on the Website entity
    itself (website.attributes["vehicle_pages"][vehicle_id]), same "generate once,
    store on the entity, regenerate via an explicit action" convention
    regenerate_section() already established for page-section copy -- never
    regenerated on every page view, which would be both slow and needlessly costly.

    Deliberately cached on the WEBSITE, not the Vehicle entity itself: this is
    marketing copy specific to how THIS site presents the vehicle, not a fact about
    the vehicle as a shared graph object every department (Sales/Service/Inventory/
    Operations) reads -- writing it onto Vehicle.attributes would pollute a core
    business entity with one website's copy."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    vehicle = ledger.get_entity(vehicle_id)

    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": "Vehicle not found"}

    from core.website_wizard import generate_vehicle_description, fallback_vehicle_description

    attrs = vehicle.attributes
    result = generate_vehicle_description(website.attributes.get("name"), attrs)

    if "error" in result:
        description = fallback_vehicle_description(attrs)
        ai_generated = False
    else:
        description = result.get("description") or fallback_vehicle_description(attrs)
        ai_generated = True

    website.attributes.setdefault("vehicle_pages", {})[vehicle_id] = {
        "description": description,
        "ai_generated": ai_generated,
        "generated_at": _now(),
        "generated_by": by,
    }

    _log_history(website, "vehicle_description_generated", by, notes=f"{vehicle_id}: ai_generated={ai_generated}")
    save_graph(GRAPH_PATH)

    return {
        "vehicle_id": vehicle_id,
        "description": description,
        "ai_generated": ai_generated,
    }


def _to_number(value, default):
    """Coerce a builder text field to a number, falling back to `default`. Digital Retail
    widgets store numeric config as text (the builder's field editor is text-only today)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value, default):
    """Coerce a builder text field to a bool. Empty -> default; otherwise anything but
    false/no/off/0 is True."""
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in ("false", "no", "off", "0")


def render_page(website, page_key, utm_source=None, referrer=None):
    """Returns a page's sections with any `inventory_grid` section resolved to a live
    vehicle list (`live_vehicles`) and any `car_builder` section resolved to live
    Make/Model/Trim options (`live_options`) -- both computed here, never stored on the
    entity, so the page is always current.

    `utm_source`/`referrer` (2026-07-19, Website Personalization) are the real visitor
    signals a public page request can carry -- when present, each section's own
    `personalization_variants` list (see add_personalization_variant() above) is
    checked via _select_personalization_variant(); a match overlays that variant's
    field_overrides onto a COPY of the section's fields for THIS render only (the
    stored section is never touched), and the rendered section carries a real, visible
    `personalization_applied` marker naming which variant fired -- never a silent,
    untraceable content swap. inventory_grid/car_builder resolution runs AFTER the
    overlay, so a variant can genuinely steer which live vehicles/options a visitor
    sees (e.g. override `make` for a truck-focused ad campaign)."""

    page = website.attributes["pages"].get(page_key, {"sections": []})

    rendered_sections = []

    for section in page["sections"]:

        rendered = dict(section)
        fields = dict(section.get("fields") or {})

        variant = _select_personalization_variant(section, utm_source, referrer)

        if variant:
            fields.update(variant.get("field_overrides") or {})
            rendered["fields"] = fields
            rendered["personalization_applied"] = {
                "variant_id": variant["id"],
                "match": variant.get("match"),
            }

        if section["section_key"] == "inventory_grid":

            rendered["live_vehicles"] = get_live_inventory(
                make=fields.get("make"),
                max_price=fields.get("max_price"),
                location_id=fields.get("location_id"),
                limit=fields.get("limit", 12),
            )

        elif section["section_key"] == "car_builder":

            rendered["live_options"] = get_car_builder_options()

        elif section["section_key"] == "ask_dealeros":

            # A live inventory sample the assistant can ground initial suggestions on
            # (same no-parallel-copy rule as inventory_grid).
            rendered["live_vehicles"] = get_live_inventory(limit=6)

        elif section["section_key"] == "payment_builder":

            # Same live Make/Model/Trim tree as Build Your Car, plus the dealer's parsed
            # payment assumptions for the client-side real-time calculator.
            rendered["live_options"] = get_car_builder_options()
            rendered["payment_config"] = {
                "default_down": _to_number(fields.get("default_down"), 3000),
                "default_term_months": int(_to_number(fields.get("default_term_months"), 60)),
                "assumed_apr": _to_number(fields.get("assumed_apr"), 6.9),
            }

        elif section["section_key"] == "buy_online":

            level = str(fields.get("level") or "build").strip().lower()
            if level not in ("browse", "build", "negotiate", "purchase"):
                level = "build"
            rendered["buy_online_level"] = level

        elif section["section_key"] == "delivery_scheduling":

            rendered["delivery_options"] = {
                "store_pickup": _truthy(fields.get("offer_store_pickup"), True),
                "home_delivery": _truthy(fields.get("offer_home_delivery"), True),
                "try_before_you_buy": _truthy(fields.get("offer_try_before_you_buy"), False),
                "radius_miles": int(_to_number(fields.get("delivery_radius_miles"), 50)),
            }

        rendered_sections.append(rendered)

    return {"sections": rendered_sections, "layout_mode": page.get("layout_mode", "structured")}


def get_website_rendered(website_id, mode_override=None, utm_source=None, referrer=None, published=False):
    """The customer-facing 'toggle between a traditional website and a DriveFinder.xyz
    AI-powered car builder' Sam asked for.

    Session 86 (Sam: "every website should have both a traditional and ChatGPT style
    built into the site so the customer can switch between the two. That doesn't need
    to be a choice on this side"): the `home` page is now ALWAYS filtered down to
    whichever variant matches `effective_mode` -- not only when `mode_override` differs
    from the site's stored default `mode`, as it was in session 85. This is a real,
    always-on filter over real, always-present content: create_website_from_wizard()
    (session 86) populates BOTH a hero_banner-family section and a car_builder section
    on every new site's home page, so both are genuinely there to filter between, not
    synthesized on the fly. The synthesis fallback below (a minimal generated hero, or
    a bare car_builder shell) only fires for sites that predate this change or were
    built without the wizard (a blank draft, a template that only adds one variant) and
    genuinely have just one real home section -- it's a safety net, not the normal path
    anymore. `mode` (the site's stored default) still controls which variant a visitor
    sees before making any explicit choice; it is no longer a hard gate on which
    content exists.

    `utm_source`/`referrer` (2026-07-19, Website Personalization) are threaded straight
    through to every render_page() call -- the real visitor signals a public page
    request carries, backing each section's own personalization_variants overlay."""

    website = get_website(website_id)

    if not website:
        return None

    if published and website.attributes.get("published_snapshot"):
        website = public_version(website)
        if website is None:
            return None

    pages_out = {
        page_key: render_page(website, page_key, utm_source=utm_source, referrer=referrer)
        for page_key in PAGE_KEYS
    }

    # Captured before the mode-filter branches below reconstruct pages_out["home"]
    # wholesale -- both branches need to carry the page's real layout_mode through
    # rather than silently reset a canvas-mode home page back to "structured" the
    # moment a visitor's effective_mode filter kicks in.
    home_layout_mode = pages_out["home"].get("layout_mode", "structured")

    stored_mode = website.attributes.get("mode", "traditional")
    effective_mode = mode_override if mode_override in MODES else stored_mode

    if effective_mode == "dealer_gpt":

        # Searches pages_out (already rendered -- personalization overlay + live
        # inventory/car-builder resolution applied) rather than the raw stored
        # website.attributes, so a car_builder section's own personalization variants
        # (2026-07-19) apply in dealer_gpt mode too, not just traditional mode.
        car_builder_section = None

        for pk in PAGE_KEYS:
            for s in pages_out[pk]["sections"]:
                if s["section_key"] == "car_builder":
                    car_builder_section = s
                    break
            if car_builder_section:
                break

        base = car_builder_section or {
            "section_key": "car_builder",
            "fields": {"heading": "Build Your Car", "intro_text": ""},
            "locked": False,
        }

        rendered = dict(base)
        rendered["live_options"] = get_car_builder_options()
        # Non-inventory-page extras (social links, OEM banner) still ride along on
        # the DealerGPT home view if the site has them, same as the traditional view.
        extras = [s for s in pages_out["home"]["sections"] if s["section_key"] in ("social_links", "oem_branding_banner")]
        pages_out["home"] = {"sections": [rendered] + extras, "layout_mode": home_layout_mode}

    else:  # effective_mode == "traditional"

        non_builder = [s for s in pages_out["home"]["sections"] if s["section_key"] != "car_builder"]

        if non_builder:
            pages_out["home"] = {"sections": non_builder, "layout_mode": home_layout_mode}
        else:
            pages_out["home"] = {"sections": [{
                "section_key": "hero_banner",
                "fields": {
                    "headline": f"Welcome to {website.attributes.get('name') or 'Our Dealership'}",
                    "subheadline": "",
                    "image_url": None,
                    "cta_text": "Browse Inventory",
                },
                "locked": False,
            }], "layout_mode": home_layout_mode}

    for page in pages_out.values():
        for section in page["sections"]:
            if section["section_key"] == "contact_form":
                section["social_links"] = deepcopy((website.attributes.get("studio_config") or {}).get("social_links", {}))
    from core.website_studio import render_studio_events
    return {
        "id": website.id,
        **{k: v for k, v in website.attributes.items() if k != "pages"},
        "studio_locations": website_locations() if website.attributes.get("studio_config") else [],
        "studio_events": render_studio_events(website) if website.attributes.get("studio_config") else [],
        "pages": pages_out,
        "effective_mode": effective_mode,
        "both_modes_available": True,
    }


# Known-bot User-Agent substrings (session 86) -- Sam: "we need a section for the
# website analytics and bot traffic." A real, honestly-scoped classifier: matches the
# well-known search/AI-crawler/SEO-tool user agents this codebase already names
# elsewhere (get_robots_txt()'s block_ai_crawlers list), plus the standard major search
# engine and SEO-tool crawlers. Anything not matched is counted as human -- this is a
# real substring check against a real header, not a guess or a fabricated split. A
# visitor with no User-Agent at all (e.g. an internal preview call, or a client that
# omits the header) is also treated as human/unknown rather than bot, since there's no
# positive signal either way.
KNOWN_BOT_USER_AGENTS = [
    "GPTBot", "CCBot", "ClaudeBot", "Google-Extended", "anthropic-ai",
    "Googlebot", "Bingbot", "Slurp", "DuckDuckBot", "Baiduspider", "YandexBot",
    "facebookexternalhit", "Twitterbot", "LinkedInBot", "AhrefsBot", "SemrushBot",
    "MJ12bot", "DotBot", "PetalBot", "bingbot", "Applebot",
]


def _classify_user_agent(user_agent):
    """Returns (is_bot, matched_bot_name) -- matched_bot_name is None for human/unknown
    traffic. Case-sensitive substring match against KNOWN_BOT_USER_AGENTS, matching the
    literal casing real crawlers actually send (same list source as get_robots_txt())."""

    if not user_agent:
        return False, None

    for bot_name in KNOWN_BOT_USER_AGENTS:
        if bot_name in user_agent:
            return True, bot_name

    return False, None


def record_page_view(website_id, page_key, viewer_ref=None, user_agent=None):
    """Real page-view analytics event (session 85) -- Sam: 'the admin side should have
    google analytics / umami style reporting.' Logged every time the real preview/
    render route is hit (see api/app.py's GET /public/websites/{id}). This sandbox has
    no live public domain actually serving customer traffic, so these are genuinely
    real events off whatever traffic this environment's own render/preview endpoint
    receives (internal previews, personal-site visits) -- not fabricated numbers, just
    honestly limited to the traffic that's actually real here, matching this
    codebase's established honesty convention (e.g. core/network_aggregator.py's
    'reachable vs. not' reporting).

    Session 86 -- `user_agent` (the real HTTP User-Agent header, threaded through from
    api/app.py's request object on the public render route) is classified via
    _classify_user_agent() and stored as `IsBot`/`BotName`, backing the new Bot Traffic
    breakdown in get_website_analytics()."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    event_id = id_generator.generate("PVIEW")

    is_bot, bot_name = _classify_user_agent(user_agent)

    event = Entity(
        id=event_id,
        entity_type=WEBSITE_ANALYTICS_EVENT,
        attributes={
            "WebsiteID": website_id,
            "PageKey": page_key,
            "ViewerRef": viewer_ref,
            "UserAgent": user_agent,
            "IsBot": is_bot,
            "BotName": bot_name,
            "Timestamp": _now(),
        },
    )

    ledger.add_entity(event)

    # Deliberate exception to this module's own save_graph() fix (see module
    # docstring): this is the one path hit on every single public page load, and this
    # codebase's established precedent for a high-frequency internal call
    # (core/trigger_alerts.py's run_scan()) is to avoid an unconditional save per event.
    # A page-view event's real value is aggregate analytics (get_website_analytics()
    # below), not any single row -- losing the last few unsaved views on a restart is an
    # acceptable, honestly-scoped tradeoff, unlike a lost Lead/message/RSVP/alert
    # elsewhere in this same fix. Not batched/conditionally saved either, since there's
    # no natural batch boundary the way run_scan()'s single pass has one.

    return event


def get_website_analytics(website_id):
    """Aggregates this site's real WebsiteAnalyticsEvent entities -- total views, views
    by page, a simple day-bucketed trend, and (session 86) a real bot-vs-human traffic
    breakdown. See record_page_view()'s docstring for the honesty note on traffic
    volume and bot classification."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    events = [
        e for e in ledger.get_all().values()
        if e.entity_type == WEBSITE_ANALYTICS_EVENT and e.attributes.get("WebsiteID") == website_id
    ]

    by_page = {}
    by_day = {}
    bot_views = 0
    human_views = 0
    by_bot_name = {}

    for event in events:

        page_key = event.attributes.get("PageKey") or "unknown"
        by_page[page_key] = by_page.get(page_key, 0) + 1

        day = (event.attributes.get("Timestamp") or "")[:10]
        by_day[day] = by_day.get(day, 0) + 1

        if event.attributes.get("IsBot"):
            bot_views += 1
            bot_name = event.attributes.get("BotName") or "Unknown bot"
            by_bot_name[bot_name] = by_bot_name.get(bot_name, 0) + 1
        else:
            human_views += 1

    return {
        "website_id": website_id,
        "total_views": len(events),
        "by_page": by_page,
        "by_day": dict(sorted(by_day.items())),
        "bot_traffic": {
            "bot_views": bot_views,
            "human_views": human_views,
            "by_bot_name": by_bot_name,
            "note": (
                "Classified via a real User-Agent substring match against known search/"
                "AI-crawler/SEO-tool bots (see KNOWN_BOT_USER_AGENTS) -- a visitor with "
                "no matching signal is counted as human, not a fabricated split. "
                "Internal/preview hits from the builder itself typically send no "
                "browser User-Agent at all and are also counted as human/unknown here."
            ),
        },
        "note": (
            "Real page-view events logged by this environment's own preview/render "
            "endpoint -- there is no live public domain serving customer traffic in "
            "this sandbox, so volume reflects internal/preview/personal-site traffic "
            "only, not real public site visitors."
        ),
    }


@serialized_website_write
@rollback_website_transition
def submit_for_approval(website_id, by=None):

    website = get_website(website_id)

    if not website:
        return None

    if website.attributes.get("studio_config"):
        if website.attributes.get("status") not in ("draft", "rejected"):
            return {"error": "Only an editable draft can be submitted for review"}
        freeze_review(website)
    website.attributes["status"] = "pending_approval"
    _log_history(website, "submitted", by)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@serialized_website_write
@rollback_website_transition
def approve_website(website_id, reviewer_id, notes=None):

    website = get_website(website_id)

    if not website:
        return None

    if website.attributes.get("studio_config"):
        if website.attributes.get("status") != "pending_approval" or not review_is_current(website):
            return {"error": "The submitted website changed. Reject it and request a fresh review before publishing."}
        website.attributes["published_snapshot"] = deepcopy(website.attributes["review_snapshot"])
        website.attributes["published_fingerprint"] = website.attributes["review_fingerprint"]
    website.attributes["status"] = "published"
    website.attributes["reviewed_by"] = reviewer_id
    website.attributes["review_notes"] = notes
    website.attributes["published_at"] = _now()
    _log_history(website, "published", reviewer_id, notes=notes)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


@serialized_website_write
@rollback_website_transition
def reject_website(website_id, reviewer_id, notes=None):

    website = get_website(website_id)

    if not website:
        return None

    website.attributes["status"] = "rejected"
    website.attributes["reviewed_by"] = reviewer_id
    website.attributes["review_notes"] = notes
    _log_history(website, "rejected", reviewer_id, notes=notes)
    website.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return website


def list_websites(status=None, created_by=None):

    websites = _all_websites()

    if status:
        websites = [w for w in websites if w.attributes.get("status") == status]

    if created_by:
        websites = [
            w for w in websites
            if w.attributes.get("requested_by") == created_by or created_by in (w.attributes.get("owners") or [])
        ]

    # Same (created_at, id) tiebreaker as core/assets.py's list_assets()/
    # core/campaigns.py's list_campaigns().
    websites.sort(key=lambda w: (w.attributes.get("created_at", ""), w.id), reverse=True)

    return websites


def list_pending_approvals():
    return list_websites(status="pending_approval")
