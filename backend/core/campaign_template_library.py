"""
Campaign-Template Library (Bumper parity, 2026-07-25). Bumper ships a Library of ~79
prebuilt campaigns a user browses and launches with one click. NXTDeal had campaign
*types* (7 archetypes) but no browsable catalog of ready-to-run templates. This module is
that catalog: each template is a CampaignTemplate entity carrying a campaign_type + channel
+ default params + suggested copy, and "instantiate" turns it into a real draft Campaign
via campaigns.create_campaign (so a launched template is an ordinary campaign from then on).

Starter templates ship seeded (ensure_seeded / seed_starter_templates, idempotent by slug);
users can also save their own. Templates are ordinary graph entities -- one graph, no side
store, same posture as the rest of the campaign engine.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CAMPAIGN_TEMPLATE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import campaigns


def _now():
    return datetime.now(timezone.utc).isoformat()


# The seeded starter Library. Each entry's default_params satisfies its campaign_type's
# required audience_fields, so a starter template instantiates into a valid draft with no
# extra input. (event_promo/individual need a runtime event/target id, so they're offered
# as user templates, not seeds.)
STARTER_TEMPLATES = [
    {"slug": "lapsed-service-winback", "name": "Lapsed Service Win-Back", "category": "Retention",
     "campaign_type": "retention", "channel": "email", "default_params": {"months_since_service": 6},
     "suggested_subject": "We miss you — let's get your vehicle road-ready",
     "suggested_body": "It's been a while since your last service. Book now and save on your next visit.",
     "description": "Win back customers who haven't been in for service in 6+ months."},
    {"slug": "never-serviced-outreach", "name": "Never-Serviced Outreach", "category": "Retention",
     "campaign_type": "retention", "channel": "email", "default_params": {"months_since_service": 12},
     "suggested_subject": "Your first service is on us to schedule",
     "suggested_body": "Thanks for buying with us — let's keep your vehicle in top shape.",
     "description": "Reach buyers who have never returned for service (12+ months)."},
    {"slug": "new-inventory-alert", "name": "New Inventory Alert", "category": "Sales",
     "campaign_type": "inventory_ads", "channel": "sms", "default_params": {},
     "suggested_subject": "Fresh arrivals just hit our lot",
     "suggested_body": "New inventory just landed that matches what you were looking for. Reply to take a look.",
     "description": "Alert interested leads the moment matching inventory arrives."},
    {"slug": "model-conquest", "name": "Model-Specific Conquest", "category": "Sales",
     "campaign_type": "inventory_ads", "channel": "sms", "default_params": {},
     "suggested_subject": "The {model} you wanted is here",
     "suggested_body": "We just got the exact model you were eyeing. Want first dibs?",
     "description": "Target leads by make/model with a fresh conquest push (fill make/model on launch)."},
    {"slug": "lease-maturity-3mo", "name": "Lease Maturity — 3 Months Out", "category": "Finance",
     "campaign_type": "finance_renewal", "channel": "email", "default_params": {"months_to_maturity": 3},
     "suggested_subject": "Your lease is almost up — here are your options",
     "suggested_body": "You're 3 months from lease-end. Let's talk upgrade, buyout, or return.",
     "description": "Reach customers 3 months from lease/loan maturity."},
    {"slug": "loan-payoff-upgrade", "name": "Loan Payoff / Upgrade Offer", "category": "Finance",
     "campaign_type": "finance_renewal", "channel": "email", "default_params": {"months_to_maturity": 6},
     "suggested_subject": "You may be closer to a new vehicle than you think",
     "suggested_body": "Your loan is winding down — you could upgrade with little to no change in payment.",
     "description": "Equity/upgrade nudge for customers 6 months from payoff."},
    {"slug": "new-buyer-accessories", "name": "New Buyer Accessory Upsell", "category": "Accessories",
     "campaign_type": "accessory_accelerator", "channel": "sms", "default_params": {"days_since_sale": 30},
     "suggested_subject": "Make it yours — accessories for your new ride",
     "suggested_body": "Congrats on your purchase! Here are the top accessories owners add in the first month.",
     "description": "Upsell accessories to buyers within 30 days of purchase."},
    {"slug": "protection-followup", "name": "Protection Product Follow-Up", "category": "Accessories",
     "campaign_type": "accessory_accelerator", "channel": "email", "default_params": {"days_since_sale": 14},
     "suggested_subject": "Protect your investment",
     "suggested_body": "Extended coverage and protection plans are still available on your recent purchase.",
     "description": "Follow up on protection products two weeks post-sale."},
    {"slug": "holiday-hours", "name": "Holiday Hours Announcement", "category": "Announcements",
     "campaign_type": "general", "channel": "email", "default_params": {},
     "suggested_subject": "Our holiday hours",
     "suggested_body": "Here are our adjusted hours for the holiday. We look forward to seeing you.",
     "description": "Broadcast adjusted holiday hours to every customer."},
    {"slug": "service-special", "name": "Service Special Broadcast", "category": "Announcements",
     "campaign_type": "general", "channel": "email", "default_params": {},
     "suggested_subject": "This month's service special",
     "suggested_body": "Save on service this month — limited-time offer for our customers.",
     "description": "Store-wide service special announcement."},
    {"slug": "recall-notice", "name": "Recall Notice", "category": "Announcements",
     "campaign_type": "general", "channel": "email", "default_params": {},
     "suggested_subject": "Important recall information for your vehicle",
     "suggested_body": "A recall may affect your vehicle. Please contact us to schedule the free repair.",
     "description": "Broadcast an important recall notice."},
]


def get_template(template_id):
    e = ledger.get_entity(template_id)
    return e if e and e.entity_type == CAMPAIGN_TEMPLATE else None


def _all_templates():
    return [e for e in ledger.get_all().values() if e.entity_type == CAMPAIGN_TEMPLATE and not e.attributes.get("deleted")]


def _existing_slugs():
    return {e.attributes.get("slug") for e in _all_templates() if e.attributes.get("slug")}


def seed_starter_templates():
    """Create any starter template not already present (idempotent by slug). Returns the
    count created this call."""
    existing = _existing_slugs()
    created = 0
    for spec in STARTER_TEMPLATES:
        if spec["slug"] in existing:
            continue
        entity = Entity(
            id=id_generator.generate("CTMPL"),
            entity_type=CAMPAIGN_TEMPLATE,
            attributes={
                "slug": spec["slug"],
                "name": spec["name"],
                "description": spec.get("description", ""),
                "category": spec.get("category", "General"),
                "campaign_type": spec["campaign_type"],
                "channel": spec["channel"],
                "default_params": dict(spec.get("default_params") or {}),
                "suggested_subject": spec.get("suggested_subject", ""),
                "suggested_body": spec.get("suggested_body", ""),
                "tags": list(spec.get("tags") or []),
                "is_starter": True,
                "created_by": "system",
                "created_at": _now(),
                "updated_at": _now(),
                "times_used": 0,
            },
        )
        ledger.add_entity(entity)
        created += 1
    if created:
        save_graph(GRAPH_PATH)
    return created


def ensure_seeded():
    """Seed the starter Library on first read if the starters aren't present, so the catalog
    is never missing its prebuilt templates -- independent of any user-authored templates
    that may already exist (checking 'is the library empty' would miss the starters whenever
    a user saved a template first)."""
    have_starters = any(t.attributes.get("is_starter") for t in _all_templates())
    if not have_starters:
        seed_starter_templates()


def list_templates(category=None, campaign_type=None, query=None):
    ensure_seeded()
    out = _all_templates()
    if category:
        out = [t for t in out if (t.attributes.get("category") or "").lower() == category.lower()]
    if campaign_type:
        out = [t for t in out if t.attributes.get("campaign_type") == campaign_type]
    if query:
        q = query.lower()
        out = [t for t in out if q in (t.attributes.get("name", "") + " " + t.attributes.get("description", "")).lower()]
    return sorted(out, key=lambda t: (t.attributes.get("category", ""), t.attributes.get("name", "")))


def list_categories():
    ensure_seeded()
    counts = {}
    for t in _all_templates():
        cat = t.attributes.get("category") or "General"
        counts[cat] = counts.get(cat, 0) + 1
    return [{"category": c, "count": n} for c, n in sorted(counts.items())]


def create_template(name, campaign_type, channel, created_by, default_params=None, category="General",
                    description="", suggested_subject="", suggested_body="", tags=None):
    """Save a user-authored template into the Library."""
    if not (name or "").strip():
        return {"error": "name is required"}
    if not campaigns.get_campaign_type(campaign_type):
        return {"error": f"Unknown campaign_type '{campaign_type}'"}
    if channel not in campaigns.list_channels():
        return {"error": f"Unknown channel '{channel}'"}
    entity = Entity(
        id=id_generator.generate("CTMPL"),
        entity_type=CAMPAIGN_TEMPLATE,
        attributes={
            "slug": None,
            "name": name.strip(),
            "description": description or "",
            "category": category or "General",
            "campaign_type": campaign_type,
            "channel": channel,
            "default_params": dict(default_params or {}),
            "suggested_subject": suggested_subject or "",
            "suggested_body": suggested_body or "",
            "tags": list(tags or []),
            "is_starter": False,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "times_used": 0,
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


def delete_template(template_id):
    t = get_template(template_id)
    if not t:
        return {"error": "Template not found"}
    if t.attributes.get("is_starter"):
        return {"error": "Starter templates can't be deleted (deactivate the campaign instead)"}
    t.attributes["deleted"] = True
    t.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"ok": True, "template_id": template_id}


def instantiate_template(template_id, created_by, name_override=None, params_override=None, channel_override=None):
    """Turn a template into a real draft Campaign. Params are the template defaults merged
    with any overrides; name defaults to the template name. Returns the created campaign."""
    t = get_template(template_id)
    if not t:
        return {"error": "Template not found"}
    a = t.attributes
    params = dict(a.get("default_params") or {})
    params.update(params_override or {})
    name = (name_override or "").strip() or a.get("name", "Campaign")
    channel = channel_override or a.get("channel")

    campaign = campaigns.create_campaign(a.get("campaign_type"), name, channel, created_by, params)
    # Carry the template's suggested copy into the campaign notes so the launcher sees it.
    if a.get("suggested_subject") or a.get("suggested_body"):
        campaign.attributes["notes"] = (
            f"Suggested subject: {a.get('suggested_subject', '')}\n{a.get('suggested_body', '')}".strip()
        )
    campaign.attributes["from_template_id"] = template_id
    a["times_used"] = a.get("times_used", 0) + 1
    a["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return campaign
