"""
Marketing asset design/approval workflow (2026-07-13, session 30) -- phase 1 of folding
NXTDeal's product suite into NXTDeal, per Sam: "the full suite of products that
NXTDeal provides currently, but split across the team structure we have set up in
NXTDeal, with the singular graph database... all routed through the same graph
knowledge." Mirrors the previous sales design reference (sales/marketing requests an OEM/dealer
branded asset) and admin.nxtdeal.design (marketing/compliance approves it) -- but
graph-native like everything else in this codebase, and template-fill rather than a
freeform design canvas (Sam's explicit scoping answer, session 30).

An Asset is an ordinary Entity in the same core.dealeros.ledger every other entity type
lives in (no new parallel content-management store) -- optionally tied to a Vehicle
(the car it's advertising) and/or a Campaign (the push it belongs to), and always tied
to the Employee who requested it. Approval is role-based (MARKETING/ADMIN), same
ADMIN-always-passes shape as can_access_channel/can_access_dashboard.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import ASSET
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 30) --
# every real marketing asset ever created, submitted, approved, or rejected had been
# silently discarded on server restart. Fixed below: every mutating function now saves
# directly.


# Fixed starter catalog, one template per department that touches customer-facing
# creative today (mirrors the department split NXTDeal's roles already use). `fields`
# is the schema the frontend renders as a form -- no freeform canvas, matching Sam's
# "template-fill" scoping answer. Add new templates here rather than inventing an
# admin UI to manage them, same "fixed catalog, not a management screen" shape
# core/messaging.py's CHANNEL_DEFS already uses.
ASSET_TEMPLATES = {
    "inventory_flyer": {
        "key": "inventory_flyer",
        "name": "Inventory Flyer",
        "category": "sales",
        "description": "A single-vehicle promotional flyer -- link a vehicle to pull in its details.",
        "fields": [
            {"key": "headline", "label": "Headline", "type": "text", "required": True},
            {"key": "price_override", "label": "Price (override)", "type": "text", "required": False},
            {"key": "highlight_1", "label": "Highlight 1", "type": "text", "required": False},
            {"key": "highlight_2", "label": "Highlight 2", "type": "text", "required": False},
            {"key": "cta_text", "label": "Call to Action", "type": "text", "required": False},
            {"key": "photo_url", "label": "Photo URL", "type": "text", "required": False},
        ],
    },
    "social_post": {
        "key": "social_post",
        "name": "Social Media Post",
        "category": "marketing",
        "description": "A single social post -- caption, hashtags, one image.",
        "fields": [
            {"key": "headline", "label": "Headline", "type": "text", "required": True},
            {"key": "body", "label": "Caption", "type": "textarea", "required": True},
            {"key": "hashtags", "label": "Hashtags", "type": "text", "required": False},
            {"key": "photo_url", "label": "Photo URL", "type": "text", "required": False},
        ],
    },
    "sold_announcement": {
        "key": "sold_announcement",
        "name": "Sold Announcement",
        "category": "sales",
        "description": "Congratulate a customer on their new vehicle.",
        "fields": [
            {"key": "customer_name", "label": "Customer Name", "type": "text", "required": True},
            {"key": "vehicle_description", "label": "Vehicle Description", "type": "text", "required": False},
            {"key": "message", "label": "Message", "type": "textarea", "required": False},
            {"key": "photo_url", "label": "Photo URL", "type": "text", "required": False},
        ],
    },
    "service_special": {
        "key": "service_special",
        "name": "Service Special",
        "category": "service",
        "description": "A limited-time service department offer.",
        "fields": [
            {"key": "offer_title", "label": "Offer Title", "type": "text", "required": True},
            {"key": "offer_details", "label": "Offer Details", "type": "textarea", "required": True},
            {"key": "expiration_date", "label": "Expires", "type": "text", "required": False},
        ],
    },
    "finance_offer": {
        "key": "finance_offer",
        "name": "Finance Offer",
        "category": "finance",
        "description": "An F&I promotional offer (APR/term specials, protection products).",
        "fields": [
            {"key": "offer_title", "label": "Offer Title", "type": "text", "required": True},
            {"key": "apr_rate", "label": "APR", "type": "text", "required": False},
            {"key": "term_months", "label": "Term (months)", "type": "text", "required": False},
            {"key": "disclaimer", "label": "Disclaimer", "type": "textarea", "required": False},
        ],
    },
}


def list_templates():

    return list(ASSET_TEMPLATES.values())


def get_template(template_key):

    return ASSET_TEMPLATES.get(template_key)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_assets():
    return [
        entity
        for entity in ledger.get_all().values()
        if entity.entity_type == ASSET
    ]


def create_asset(template_key, requested_by, fields, vehicle_id=None, campaign_id=None):
    """Always created as a `draft` -- see submit_for_approval() for the separate step
    that actually routes it to MARKETING/ADMIN. Matches the reset-password precedent
    (core/ai_api.py's `_match_reset_password_request`) of "recognize/create, but don't
    silently escalate" -- a draft is private to its requester until submitted."""

    asset_id = id_generator.generate("ASSET")

    entity = Entity(
        id=asset_id,
        entity_type=ASSET,
        attributes={
            "template_key": template_key,
            "status": "draft",
            "fields": fields,
            "vehicle_id": vehicle_id,
            "campaign_id": campaign_id,
            "requested_by": requested_by,
            "reviewed_by": None,
            "review_notes": None,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_asset(asset_id):
    entity = ledger.get_entity(asset_id)

    if entity and entity.entity_type == ASSET:
        return entity

    return None


def submit_for_approval(asset_id):

    asset = get_asset(asset_id)

    if not asset:
        return None

    asset.attributes["status"] = "pending_approval"
    asset.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return asset


def approve_asset(asset_id, reviewer_id, notes=None):

    asset = get_asset(asset_id)

    if not asset:
        return None

    asset.attributes["status"] = "approved"
    asset.attributes["reviewed_by"] = reviewer_id
    asset.attributes["review_notes"] = notes
    asset.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return asset


def reject_asset(asset_id, reviewer_id, notes=None):

    asset = get_asset(asset_id)

    if not asset:
        return None

    asset.attributes["status"] = "rejected"
    asset.attributes["reviewed_by"] = reviewer_id
    asset.attributes["review_notes"] = notes
    asset.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return asset


def list_assets(status=None, requested_by=None):

    assets = _all_assets()

    if status:
        assets = [a for a in assets if a.attributes.get("status") == status]

    if requested_by:
        assets = [a for a in assets if a.attributes.get("requested_by") == requested_by]

    # Sort by (created_at, id) rather than created_at alone -- two assets created in
    # the same test/request can land on the same ISO timestamp, and id is a strictly
    # increasing counter (core/id_generator.py), so it's a reliable tiebreaker for
    # "most recent first" even when timestamps collide.
    assets.sort(key=lambda a: (a.attributes.get("created_at", ""), a.id), reverse=True)

    return assets


def list_pending_approvals():

    return list_assets(status="pending_approval")
