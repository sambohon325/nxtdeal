"""
core/marketing_menu.py -- real data behind Marketing's Top Menu (core/menu_catalog.py),
session 62 (a new interactive session, picking up after the scheduled builder's
session 61 shipped Service & Parts). Sam: "ok, so lets replace the marketing pdf with
this updated one and start that next" -- marketing2.pdf REPLACES the original
marketing.pdf spec. Original Menu Bar (session 62): Overview | Campaigns | Audiences |
Events | Website | Opportunities | Reputation | Reporting.

**Reworked session 79** (Sam: "combine campaigns, audiences, and opportunities into
one Hubspot style workflow dash called CRM... add an Email/SMS dash with a fully
functional email builder"): Campaigns/Audiences/Opportunities were merged into one
crm() item, and a new email_sms() item was added. Current Menu Bar: Overview | CRM |
Email/SMS | Events | Website | Reputation | Reporting. See crm()/email_sms() below for
the full reasoning -- the original Campaigns/Audiences/Opportunities functions weren't
deleted, they were kept as private helpers (_campaigns/_audiences/_opportunities) that
crm() composes, so no existing data logic was rewritten to make the merge happen.

marketing2.pdf's own framing: with NXTDeal/Bumper (events, campaigns, database
activation, showroom traffic), Mastermind (predictive equity, ownership-cycle
intelligence, conquest, retention), the native Website Builder, OEM advertising, CRM
lifecycle marketing, and reputation management all folding into NXTDeal, Marketing
should evolve into a Revenue Operations department, not a narrow "marketing manager"
page. Content and Analytics (the original spec's items) are dropped as standalone menu
items and become embedded features instead; Events and Opportunities are new,
first-class items.

Same discipline as core/operations_menu.py/core/sales_menu.py/core/service_menu.py:
reuse an already-built function wherever it's a genuine match, compute a small new real
aggregate where the graph has the underlying data but nobody had queried it this way
yet, and use an honest `not_yet_tracked` note (never a fabricated number) wherever
marketing2.pdf asks for something this data model doesn't back at all. The biggest gap:
**no Event entity exists anywhere in this codebase.** marketing2.pdf is explicit that
Events should be modeled as "their own operational system," not folded into Campaigns
-- so events() below is an honest placeholder describing what a real Event entity would
need, not a reuse of Campaign data dressed up as events. Opportunities/Audiences reuse
core/campaigns.py's build_audience()/preview_audience() (retention/finance_renewal/
inventory_ads audience builders, session 31) and core/workflow_tab_data.py's
marketing_database_mining() (equity mining) and marketing_reputation_summary() (real
seeded Review entities, session 59) -- these are Mastermind-style scoring/segmentation
functions that already existed for the Workflow-button "database mining" tab and are
genuinely the right data for marketing2.pdf's Audiences/Opportunities/Reputation items,
not new code duplicating the same query.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE, CAMPAIGN, WEBSITE, REVIEW, EMAIL_TEMPLATE

from core.campaigns import (
    list_campaign_types,
    list_channels,
    list_campaigns,
    preview_audience,
    build_audience,
    audience_entity_type,
)
from core.websites import list_websites, SECTION_TEMPLATES, SITE_TEMPLATES
from core.personal_sites import list_personal_sites
from core.website_chat import list_sessions as list_chat_sessions
from core.workflow_tab_data import marketing_database_mining, marketing_reputation_summary
from core.workflow_dashboard import get_lead_pipeline_dashboard
from core.workflows import LEAD_WORKFLOW
from core.compliance_api import list_alerts_api
from core.data_connections_api import readiness_predictions_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.email_templates import list_templates as list_email_templates, list_block_types
from core.marketing_lists import list_lists
from core.smart_audiences import list_presets as list_smart_audience_presets, list_audiences as list_smart_audiences
from core.lead_scoring import leaderboard as lead_scoring_leaderboard
from core.social_posts import (
    list_platforms as list_social_platforms,
    list_posts as list_social_posts,
    get_calendar as get_social_calendar,
)
from core.reputation_api import (
    get_reputation_summary_api,
    list_bad_review_alerts_api,
    get_competitor_tracking_api,
)
from core.advertising import (
    list_platforms as list_ad_platforms,
    list_objectives as list_ad_objectives,
    list_ad_campaigns,
)
from core.trigger_alerts import (
    run_scan as run_trigger_scan,
    list_alerts,
    ALERT_TYPES as _ALERT_TYPES,
)
from core.dealership_events import (
    list_event_types,
    list_events as list_dealership_events,
)
from core.marketing_attribution_api import get_marketing_roi_dashboard_api

# Newly-built Marketing modules (2026-07-23 integration pass) -- thin role-gated
# pass-throughs, mirroring operations_menu.customer_journey.
from core.inventory_advertising_api import get_advertising_overview_api
from core.loyalty_api import get_loyalty_overview_api


def list_alert_types():
    return _ALERT_TYPES

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Department
# Intelligence's real KPI engine (core/department_intelligence.py) only has 5 keys --
# sales/service/parts/fi/executive -- not one per menu department, so this is an honest
# gap for Marketing rather than a stretch mapping onto an unrelated key.
_DI_GAP_NOTE = {
    "available": False,
    "note": (
        "No 1:1 Department Intelligence key exists for Marketing -- the 5 real keys "
        "are sales/service/parts/fi/executive (see core/department_intelligence.py)."
    ),
}


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _funded_deal_gross(deals):
    """Same real front-end-gross computation core/sales_menu.py/core/employee_value.py
    already rely on -- sum(Vehicle.Price - Vehicle.Cost) across a list of funded Deals."""

    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    total = 0.0
    for deal in deals:
        vehicle = vehicles_by_id.get(deal.attributes.get("vehicle_id"))
        if vehicle:
            total += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
    return total


def _avg_funded_deal_gross():
    funded = [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]
    if not funded:
        return 0.0
    return _funded_deal_gross(funded) / len(funded)


def overview(role):
    """marketing2.pdf's "Overview" item: the Revenue Operations command center.
    Website Traffic, Event Registrations, Appointments Set, and Cost Per Lead have no
    backing data model in this codebase yet (no analytics-event store, no Event entity,
    no Appointment entity, no ad-spend ledger) -- said so explicitly rather than
    guessed. Revenue Funnel/Opportunity Pipeline widgets are real graph counts."""

    leads = _entities(LEAD)
    pipeline = get_lead_pipeline_dashboard()
    showroom = [l for l in leads if l.attributes.get("PipelineState") == "VISITED"]
    funded_deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]
    gross_profit = _funded_deal_gross(funded_deals)

    campaigns = _entities(CAMPAIGN)
    audience_total = sum(c.attributes.get("audience_count", 0) for c in campaigns)

    equity = marketing_database_mining(role)
    lease = preview_audience("finance_renewal", {"months_to_maturity": 6})
    conquest = preview_audience("inventory_ads", {})

    return {
        "lead_volume": len(leads),
        "showroom_traffic": len(showroom),
        "revenue_generated_funded_deals": round(gross_profit, 2),
        "active_opportunities": equity.get("count", 0) + lease.get("count", 0),
        "revenue_funnel": {
            "audience": audience_total,
            "campaign": len(campaigns),
            "lead": len(leads),
            "appointment": None,
            "showroom": len(showroom),
            "sold": len(funded_deals),
        },
        "opportunity_pipeline": {
            "equity_customers": equity.get("count", 0),
            "lease_maturity": lease.get("count", 0),
            "service_defectors": preview_audience("retention", {"months_since_service": 6}).get("count", 0),
            "conquest_targets": conquest.get("count", 0),
        },
        "not_yet_tracked": {
            "website_traffic": "No web-analytics event store exists yet -- Website admin settings can hold a Google Analytics / Umami ID (core/websites.py), but no traffic numbers are ingested into the graph.",
            "event_registrations": "No Event entity exists yet -- see the 'events' menu item.",
            "appointments_set": "No Appointment/calendar data model exists in this codebase yet.",
            "cost_per_lead": "No ad-spend/budget ledger exists yet to divide against lead volume.",
            "event_performance": "No Event entity exists yet -- see the 'events' menu item.",
        },
    }


def _campaigns(role):
    """The campaign orchestration center -- real campaign data (core/campaigns.py,
    session 31) grouped by type/category/channel/status. Budget management and true
    multi-touch attribution tracking have no backing data model yet (Campaign has no
    budget field, and Leads/Deals aren't linked back to the Campaign that generated
    them) -- said so rather than fabricated. Compliance approval reuses the real
    CAN-SPAM/TCPA alert category, same as core/sales_menu.py's communications(). Folded
    into the "CRM" Top Menu item's Campaigns tab as of session 79 (previously its own
    standalone Top Menu item) -- see crm() below."""

    all_campaigns = list_campaigns()

    by_status = {}
    by_category = {}
    by_channel = {}

    types_by_key = {t["key"]: t for t in list_campaign_types()}

    for c in all_campaigns:
        status = c.attributes.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        campaign_type = c.attributes.get("campaign_type")
        category = (types_by_key.get(campaign_type) or {}).get("category", "unknown")
        by_category[category] = by_category.get(category, 0) + 1

        channel = c.attributes.get("channel", "unknown")
        by_channel[channel] = by_channel.get(channel, 0) + 1

    alerts = list_alerts_api(role, status=None)
    marketing_alerts = []
    if isinstance(alerts, dict) and "alerts" in alerts:
        marketing_alerts = [a for a in alerts["alerts"] if a.get("category") == "marketing"]

    return {
        "total_campaigns": len(all_campaigns),
        "by_status": by_status,
        "by_category": by_category,
        "by_channel": by_channel,
        "available_types": list_campaign_types(),
        "available_channels": list_channels(),
        "pending_drafts": {"count": by_status.get("draft", 0)},
        "compliance_approval": {"count": len(marketing_alerts), "alerts": marketing_alerts},
        "recent_campaigns": [
            {
                "id": c.id,
                "name": c.attributes.get("name"),
                "campaign_type": c.attributes.get("campaign_type"),
                "channel": c.attributes.get("channel"),
                "status": c.attributes.get("status"),
                "audience_count": c.attributes.get("audience_count"),
                "sent_count": c.attributes.get("sent_count"),
            }
            for c in all_campaigns[:20]
        ],
        "not_yet_tracked": {
            "budget_management": "Campaign has no budget/spend field in this data model yet.",
            "attribution_tracking": "Leads/Deals still aren't linked back to the specific Campaign that generated them -- no true multi-touch attribution is computed. As of session 113 follow-up, see the new 'Analytics' Top Menu item (core/marketing_attribution.py) for real, honest FIRST-touch attribution off each Lead's own Source field, plus a real ROI rollup of this module's own per-campaign revenue correlation.",
        },
    }


def campaigns(role, query=None):
    """Marketing's "Campaigns" Top Menu item (session 113 follow-up) -- split back
    out of the merged "CRM" item per Sam's later 12-item Growth Platform menu spec,
    which lists Campaigns as its own thing distinct from CRM. Session 79/81's merge
    decision is deliberately NOT undone here -- crm()'s own "campaigns" key (its
    Campaigns tab) is untouched and still works exactly as before for anyone working
    inside that broader HubSpot-style workspace. This is a genuinely separate, lean
    Top Menu item for a Marketing user who wants campaigns directly without loading
    Pipeline/Lists/Opportunities/Customer 360/Smart Audiences/Lead Scoring alongside
    it -- same real _campaigns(role) computation, zero duplicated logic, zero new
    routes needed for the CRUD/stats/A-B-test/revenue actions themselves (those
    already have their own dedicated /campaigns/* routes via core/campaigns_api.py)."""

    if query:

        q = query.strip().upper()

        if q.startswith("CAMP-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity
            return {"campaign": entity, "related_entities": get_related_entities(role, q)}

    return _campaigns(role)


AUDIENCE_VIEWS = {
    "equity_mining": {"builder": "database_mining"},
    "lease_maturity": {"campaign_type": "finance_renewal", "params": {"months_to_maturity": 6}},
    "service_defection": {"campaign_type": "retention", "params": {"months_since_service": 12}},
    "upgrade_opportunities": {"campaign_type": "accessory_accelerator", "params": {"days_since_sale": 30}},
}


def _audiences(role):
    """Mastermind-style segmentation -- reuses core/campaigns.py's real audience
    builders (session 31) for Equity Mining, Lease Maturity, Service Defection/
    Conquest, and Upgrade Opportunities. Warranty Expiration and the four predictive
    scores (Purchase Probability, Service Probability, Defection Risk, Upgrade
    Opportunity) have no backing data model yet -- Vehicle has no warranty-term field,
    and no scoring engine exists in this codebase. Folded into the "CRM" Top Menu
    item's Lists tab as of session 79 -- see crm() below."""

    equity = marketing_database_mining(role)
    lease = preview_audience("finance_renewal", {"months_to_maturity": 6})
    service_defection = preview_audience("retention", {"months_since_service": 12})
    service_conquest = preview_audience("retention", {"months_since_service": 0})
    upgrade = preview_audience("accessory_accelerator", {"days_since_sale": 30})

    previous_buyers = list({
        rel.source_id
        for rel in ledger.get_relationships()
        if rel.relationship_type == "OWNS"
    })

    unsold_leads = [l for l in _entities(LEAD) if l.attributes.get("PipelineState") == "LOST"]

    return {
        "equity_mining": {"count": equity.get("count", 0), "sample": equity.get("candidates", [])[:10]},
        "lease_maturity": lease,
        "service_conquest": service_conquest,
        "service_defection": service_defection,
        "upgrade_opportunities": upgrade,
        "previous_buyers": {"count": len(previous_buyers)},
        "unsold_leads": {"count": len(unsold_leads)},
        "not_yet_tracked": {
            "warranty_expiration": "Vehicle has no warranty-term/expiration field in this data model yet.",
            "purchase_probability_score": "No predictive scoring engine exists yet.",
            "service_probability_score": "No predictive scoring engine exists yet.",
            "defection_risk_score": "No predictive scoring engine exists yet.",
            "upgrade_opportunity_score": "No predictive scoring engine exists yet.",
        },
    }


def events(role, query=None):
    """**Reworked session 84** (Sam: "build out the event dash. we want to style it
    after nxtdeal bumper, automotivemastermind.com, and auto alert. this part we
    absolutely have to nail, and has to tightly integrate into the CRM" -- scoped via
    AskUserQuestion to "Both, unified" + "One-click promote"). marketing2.pdf's own
    framing was right that Events shouldn't be a Campaign subtype -- but rather than
    one operational system, this is genuinely TWO real ones behind one toggle,
    matching the three named references: a live, urgency-ranked Timeline of
    individually actionable trigger signals (core/trigger_alerts.py -- the
    AutoAlert/automotiveMastermind half) and real scheduled dealership events with a
    CRM-list-backed invite audience and RSVP tracking (core/dealership_events.py --
    the NXTDeal Bumper half). Both promote directly into a real new Lead
    (core/lead_intake.py's create_lead()) tied back to the originating Customer via a
    real GENERATED_LEAD relationship -- the literal "tightly integrate into the CRM"
    requirement, not just a description of how it should work."""

    if query:
        alerts = [
            a for a in list_alerts()
            if query.lower() in str(a.attributes.get("target_name", "")).lower()
            or query.lower() in str(a.attributes.get("headline", "")).lower()
        ]
        evts = [
            e for e in list_dealership_events()
            if query.lower() in str(e.attributes.get("name", "")).lower()
            or query.lower() in str(e.attributes.get("location", "")).lower()
        ]
        return {
            "query": query,
            "count": len(alerts) + len(evts),
            "results": {
                "alerts": [
                    {"id": a.id, "alert_type": a.attributes.get("alert_type"), "headline": a.attributes.get("headline"), "target_name": a.attributes.get("target_name"), "status": a.attributes.get("status")}
                    for a in alerts
                ],
                "events": [
                    {"id": e.id, "name": e.attributes.get("name"), "event_type": e.attributes.get("event_type"), "status": e.attributes.get("status"), "start_time": e.attributes.get("start_time")}
                    for e in evts
                ],
            },
        }

    run_trigger_scan()
    all_alerts = list_alerts(status="new")

    by_type = {}
    by_urgency = {}
    for a in all_alerts:
        t = a.attributes.get("alert_type", "unknown")
        u = a.attributes.get("urgency", "low")
        by_type[t] = by_type.get(t, 0) + 1
        by_urgency[u] = by_urgency.get(u, 0) + 1

    all_events = list_dealership_events()
    upcoming = [e for e in all_events if e.attributes.get("status") == "scheduled"]

    return {
        "timeline": {
            "alert_types": list_alert_types(),
            "open_count": len(all_alerts),
            "by_type": by_type,
            "by_urgency": by_urgency,
            "recent_alerts": [
                {
                    "id": a.id,
                    "alert_type": a.attributes.get("alert_type"),
                    "alert_type_label": a.attributes.get("alert_type_label"),
                    "target_entity_type": a.attributes.get("target_entity_type"),
                    "target_entity_id": a.attributes.get("target_entity_id"),
                    "target_name": a.attributes.get("target_name"),
                    "headline": a.attributes.get("headline"),
                    "urgency": a.attributes.get("urgency"),
                    "basis": a.attributes.get("basis"),
                    "created_at": a.attributes.get("created_at"),
                }
                for a in all_alerts[:30]
            ],
        },
        "events": {
            "event_types": list_event_types(),
            "total": len(all_events),
            "upcoming_count": len(upcoming),
            "recent_events": [
                {
                    "id": e.id,
                    "name": e.attributes.get("name"),
                    "event_type": e.attributes.get("event_type"),
                    "status": e.attributes.get("status"),
                    "start_time": e.attributes.get("start_time"),
                    "location": e.attributes.get("location"),
                    "linked_list_id": e.attributes.get("linked_list_id"),
                }
                for e in all_events[:15]
            ],
        },
        "not_yet_tracked": {
            "appointment_scheduling": "No standalone Appointment/calendar entity exists -- Events cover scheduled dealership events specifically, not general appointment booking (same gap core/sales_menu.py/core/service_menu.py already flag).",
            "check_in_dashboard": "RSVP status supports attended/no_show tracking, but there's no live check-in kiosk/scanner flow -- status updates are manual.",
            "revenue_attribution": "No Deal <-> Event linkage exists yet, so 'revenue generated by this event' can't be computed -- would need a new relationship or Deal field.",
        },
    }


def website(role, query=None):
    """marketing2.pdf's "Website" item -- since NXTDeal already has a real website
    builder (core/websites.py, sessions 32/58), this reuses it directly rather than
    reinventing a summary. Landing Pages, Pop-Ups, and Conversion Tools have no backing
    data model -- PAGE_KEYS is a fixed page set (home/inventory/about/testimonials/
    financing/contact), not freeform user-created pages, and there's no pop-up section
    template or conversion-event tracking yet. AI Content Generation is real (already
    shipped, session 58's website_wizard, extended session 85 with per-section
    regenerate) -- reported as available, not a gap.

    Extended session 85 (the Website Builder overhaul -- layout templates,
    drag-and-drop reorder, image library, per-page SEO, per-section AI regenerate,
    personal URL microsites, live chat wired into the CRM): adds real summaries of
    the two brand-new entity families (PersonalSite, WebsiteChatSession) alongside the
    existing Website summary, so this one menu item still reflects everything the
    Website Builder now covers rather than just its original scope."""

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] == WEBSITE]
        return {"query": query, "count": len(results), "results": results}

    all_sites = list_websites()

    by_status = {}
    by_mode = {}
    inventory_widget_count = 0
    form_count = 0
    seo_configured_count = 0
    custom_domain_count = 0

    for site in all_sites:
        status = site.attributes.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        mode = site.attributes.get("mode", "traditional")
        by_mode[mode] = by_mode.get(mode, 0) + 1

        settings = site.attributes.get("admin_settings") or {}
        if settings.get("meta_title") or settings.get("meta_description"):
            seo_configured_count += 1
        if settings.get("custom_domain"):
            custom_domain_count += 1

        for page in (site.attributes.get("pages") or {}).values():
            for section in page.get("sections", []):
                if section.get("section_key") == "inventory_grid":
                    inventory_widget_count += 1
                if section.get("section_key") == "contact_form":
                    form_count += 1

    all_personal_sites = list_personal_sites()

    personal_sites_by_status = {}
    for site in all_personal_sites:
        status = site.attributes.get("status", "unknown")
        personal_sites_by_status[status] = personal_sites_by_status.get(status, 0) + 1

    all_chat_sessions = list_chat_sessions()

    chat_by_status = {}
    promoted_chat_count = 0
    for session in all_chat_sessions:
        status = session.attributes.get("status", "unknown")
        chat_by_status[status] = chat_by_status.get(status, 0) + 1
        if session.attributes.get("lead_id"):
            promoted_chat_count += 1

    return {
        "total_websites": len(all_sites),
        "by_status": by_status,
        "by_mode": by_mode,
        "site_builder": {
            "sites": [
                {"id": s.id, "name": s.attributes.get("name"), "status": s.attributes.get("status"), "mode": s.attributes.get("mode")}
                for s in all_sites[:20]
            ],
            "available_section_templates": list(SECTION_TEMPLATES.keys()),
            "available_layout_templates": [
                {"key": t["key"], "name": t["name"], "dealer_type": t["dealer_type"]}
                for t in SITE_TEMPLATES.values()
            ],
        },
        "inventory_widgets": {"count": inventory_widget_count},
        "forms": {"count": form_count},
        "seo_pages": {"sites_with_seo_configured": seo_configured_count, "sites_with_custom_domain": custom_domain_count},
        "ai_content_generation": {
            "available": True,
            "note": "core/website_wizard.py drafts real hero/about/financing/testimonial copy via OpenAI at site-creation time (the 'Use AI Setup Wizard' flow, session 58), and per-section regenerate_section_copy() rewrites one section's AI-writable fields on demand (session 85) -- not a gap.",
        },
        "personal_sites": {
            "total": len(all_personal_sites),
            "by_status": personal_sites_by_status,
            "note": "Session 85 -- one personal landing page per employee ('deployed by the sales rep or marketing / events'), borrowing its parent Website's branding live rather than a full site mirror. A contact-form lead on a personal page assigns directly to that employee.",
        },
        "live_chat": {
            "total_sessions": len(all_chat_sessions),
            "by_status": chat_by_status,
            "promoted_to_lead": promoted_chat_count,
            "note": "Session 85 -- REST + polling (not a new public WebSocket), scoped deliberately since core/messaging.py's real-time system assumes authenticated employees only. One-click promote creates a real Lead, same precedent as the Events dash's trigger-alert/RSVP promote.",
        },
        "not_yet_tracked": {
            "landing_pages": "PAGE_KEYS is a fixed page set (home/inventory/about/testimonials/financing/contact) -- no freeform, user-created landing pages exist yet.",
            "pop_ups": "No pop-up section template exists in SECTION_TEMPLATES yet.",
            "conversion_tools": "No conversion-event tracking data model exists yet.",
            "event_landing_pages": "Depends on the Event entity gap noted in the 'events' menu item.",
            "real_time_chat_push": "Live chat is REST + polling, not push -- see core/website_chat.py's module docstring for the scoping reasoning.",
        },
    }


def _opportunities(role):
    """Mastermind-inspired, distinct from Campaigns and Audiences: "Actual revenue
    opportunities... Who should we contact today?" Reuses the same real audience
    builders as _audiences() but frames them as dollar-value opportunity pools rather
    than segments, with a clearly-labeled ESTIMATE for projected revenue (extrapolated
    from this dealership's real average funded-deal gross, not a customer-specific
    valuation -- no live payoff/appraisal engine exists to price an individual
    customer's equity). Folded into the "CRM" Top Menu item's Opportunities tab as of
    session 79 -- see crm() below."""

    avg_gross = _avg_funded_deal_gross()

    def _pool(campaign_type, params, label):
        result = preview_audience(campaign_type, params)
        count = result.get("count", 0)
        return {
            "label": label,
            "count": count,
            "projected_revenue_estimate": round(count * avg_gross, 2),
            "sample": result.get("sample", [])[:5],
            "note": "ESTIMATE: count x this dealership's average front-end gross per funded deal -- not a customer-specific valuation.",
        }

    equity = marketing_database_mining(role)
    lease_pool = _pool("finance_renewal", {"months_to_maturity": 6}, "Lease/Finance Maturity Opportunities")
    conquest_pool = _pool("inventory_ads", {}, "Conquest Opportunities")
    service_pool = _pool("retention", {"months_since_service": 6}, "Service Opportunities")
    retention_pool = _pool("retention", {"months_since_service": 12}, "Retention Opportunities")

    equity_pool = {
        "label": "Equity Opportunities",
        "count": equity.get("count", 0),
        "sample": equity.get("candidates", [])[:5],
        "note": "HEURISTIC pct-term-elapsed proxy (core/workflow_tab_data.py's marketing_database_mining) -- no live payoff-quote engine exists, so a dollar estimate isn't computed for this pool.",
    }

    # "Who should we contact today?" -- combine the highest-signal members from the
    # dollar-estimable pools into one real, ranked outreach list.
    contact_today = (lease_pool["sample"][:3] + service_pool["sample"][:2])

    return {
        "equity_opportunities": equity_pool,
        "trade_opportunities": equity_pool,
        "conquest_opportunities": conquest_pool,
        "lease_opportunities": lease_pool,
        "service_opportunities": service_pool,
        "retention_opportunities": retention_pool,
        "who_to_contact_today": contact_today,
    }


PIPELINE_STATES = list(LEAD_WORKFLOW.keys())


def _pipeline_board():
    """HubSpot-style Lead pipeline board (session 79) -- Sam: "combine campaigns,
    audiences, and opportunities into one Hubspot style workflow dash called CRM."
    Groups real Lead entities into columns by their real PipelineState
    (core/pipeline_state.py, session 17), one column per core/workflows.py's
    LEAD_WORKFLOW state -- the exact state machine core/lead_pipeline_api.py's
    advance_lead_pipeline_api() (new this session) validates transitions against when
    a card is dragged between columns. Not a new/parallel pipeline model -- this is the
    same Lead pipeline state every dashboard elsewhere in this codebase already reads,
    rendered as a draggable board for the first time."""

    leads = _entities(LEAD)

    columns = {state: [] for state in PIPELINE_STATES}

    for lead in leads:

        state = lead.attributes.get("PipelineState") or "NEW"

        columns.setdefault(state, []).append({
            "id": lead.id,
            "name": lead.attributes.get("LeadID") or lead.id,
            "source": lead.attributes.get("Source"),
            "since": lead.attributes.get("PipelineStateSince"),
        })

    return {
        "states": PIPELINE_STATES,
        "columns": columns,
        "total": len(leads),
    }


def _lists_summary():
    """Session 82 -- Sam: "under lists we need to be able to click on the list names
    and have them show as a list of names... its really there you'd be able to start
    to curate marketing lists for campaigns." A glance summary of real
    core/marketing_lists.py MarketingList entities (name/source/member count) for the
    CRM's Lists tab -- full paginated member browsing happens through the dedicated
    /lists/{id}/members route, not through this summary."""

    lists = list_lists()

    return {
        "total_lists": len(lists),
        "lists": [
            {
                "id": l.id,
                "name": l.attributes.get("name"),
                "description": l.attributes.get("description"),
                "source": l.attributes.get("source"),
                "member_count": len(l.attributes.get("member_ids") or []),
                "created_by": l.attributes.get("created_by"),
                "updated_at": l.attributes.get("updated_at"),
            }
            for l in lists[:50]
        ],
    }


def crm(role, query=None):
    """Marketing's "CRM" Top Menu item (session 79), replacing the three standalone
    Campaigns/Audiences/Opportunities items -- Sam: "combine campaigns, audiences, and
    opportunities into one Hubspot style workflow dash called CRM." One combined view:
    a real, draggable Lead pipeline board plus the pre-existing real Campaigns/
    Audiences/Opportunities data (sessions 31/62), all reusing the exact same
    functions those three items called before -- no data was invented or reshaped to
    make this merge happen, they're just presented as one workspace with tabs instead
    of three separate Top Menu items. Session 82 adds a real Lists tab summary (the
    full curated-list browser Sam asked for -- see core/marketing_lists.py).

    **Marketing Growth Platform kickoff (2026-07-17):** Sam's reframe -- "Marketing
    CRM needs to be an audience and customer intelligence platform," not just a lead
    pipeline. Three new real pieces layered on here without touching anything
    above: a `customer_360` reachable via a CUST- id query (core/customer_360.py --
    "One record. One timeline."), a `smart_audiences` summary (core/
    smart_audiences.py -- the no-code Visual Segment Builder + preset segments like
    Truck Owners/Positive Equity/Subprime), and a `lead_scoring` leaderboard summary
    (core/lead_scoring.py -- real point-based prioritization off actually-trackable
    signals). The interactive Segment Builder and full Customer 360/Lead Scoring
    detail views talk directly to their own dedicated `/smart-audiences/*`,
    `/customer-360/*`, and `/lead-scoring/*` routes, same "glance view here, full
    interactivity on the dedicated routes" split every other menu item follows."""

    if query:

        q = query.strip().upper()

        if q.startswith("CAMP-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity
            return {"campaign": entity, "related_entities": get_related_entities(role, q)}

        if q.startswith("LEAD-"):
            entity = get_entity_by_id(role, q)
            if "error" in entity:
                return entity
            return {"lead": entity, "related_entities": get_related_entities(role, q)}

        if q.startswith("CUST-"):
            from core.customer_360 import get_customer_360
            return get_customer_360(role, q)

        results = [
            r for r in search_entities(role, query)
            if r["entity_type"] in (LEAD, CAMPAIGN, CUSTOMER)
        ]
        return {"query": query, "count": len(results), "results": results}

    scoring = lead_scoring_leaderboard(limit=10)
    audiences = list_smart_audiences()

    return {
        "pipeline": _pipeline_board(),
        "lists": _lists_summary(),
        "campaigns": _campaigns(role),
        "audiences": _audiences(role),
        "opportunities": _opportunities(role),
        "smart_audiences": {
            "presets": list_smart_audience_presets(),
            "saved_count": len(audiences),
            "saved": [
                {"id": a.id, "name": a.attributes.get("name"), "preset_key": a.attributes.get("preset_key")}
                for a in audiences[:10]
            ],
        },
        "lead_scoring": {
            "total_scored": scoring["count"],
            "by_tier": scoring["by_tier"],
            "top_leads": scoring["leads"],
        },
    }


def purls(role, query=None):
    """Marketing's "PURLs" Top Menu item (Marketing Growth Platform, session 113
    follow-up) -- Sam's own "one of NXTDeal' strongest differentiators" example
    (dealer.com/john-smith). A thin pass-through to core/purls.py's real dashboard
    -- a PURL_-prefixed query returns that specific PURL's real analytics, matching
    core/finance_menu.py's own `portfolio()` FIN-/free-text query precedent;
    otherwise the real cross-PURL dashboard (KPIs + recent list). The interactive
    Generate/Revoke/Mail-Piece actions and the public landing page both talk
    directly to their own dedicated `/purls/*` and `/public/purl/*` routes, same
    "glance view here, full interactivity on the dedicated routes" split `crm()`
    already established for Smart Audiences/Lead Scoring."""

    from core.purls import get_purl_dashboard, get_purl_analytics, _get_purl

    if query:
        q = query.strip().upper()
        if q.startswith("PURL-"):
            purl = _get_purl(q)
            if not purl:
                return {"error": f"PURL '{q}' not found"}
            return {"purl_id": q, "analytics": get_purl_analytics(q)}

    return get_purl_dashboard(role)


def email_sms(role, query=None):
    """Marketing's new "Email / SMS" Top Menu item (session 79) -- Sam: "add an
    Email/SMS dash with a fully functional email builder (for mass and individual
    campaigns). It should have an Ai build an email wizard as well as a traditional
    drag and drop modual / mailchimp builder. it should have a toggle to switch to a
    texting/sms builder. Both pull from the CRM." Real EmailTemplate entities
    (core/email_templates.py, new this session) by channel, plus the block catalog and
    campaign-type list the frontend builder's recipient picker needs -- "pull from the
    CRM" is literal: mass sends reuse the exact same campaign-type/audience-preview
    data crm()'s Campaigns tab already surfaces, not a parallel targeting system. This
    glance view is read-only (no employee_id reaches menu items, see core/menu_data.py)
    -- the interactive builder itself (create/edit/save/AI-draft a template) talks
    directly to the dedicated /email-templates/* routes, which do have it."""

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] in (CUSTOMER, LEAD)]
        return {"query": query, "count": len(results), "results": results}

    templates = list_email_templates()

    by_channel = {}
    for t in templates:
        ch = t.attributes.get("channel", "email")
        by_channel[ch] = by_channel.get(ch, 0) + 1

    ai_generated_count = sum(1 for t in templates if t.attributes.get("ai_generated"))
    linked_count = sum(1 for t in templates if t.attributes.get("linked_campaign_id"))

    return {
        "total_templates": len(templates),
        "by_channel": by_channel,
        "ai_generated_count": ai_generated_count,
        "attached_to_campaign_count": linked_count,
        "recent_templates": [
            {
                "id": t.id,
                "name": t.attributes.get("name"),
                "channel": t.attributes.get("channel"),
                "subject": t.attributes.get("subject"),
                "ai_generated": t.attributes.get("ai_generated"),
                "created_by": t.attributes.get("created_by"),
                "updated_at": t.attributes.get("updated_at"),
            }
            for t in templates[:20]
        ],
        "block_catalog": list_block_types(),
        "available_campaign_types": list_campaign_types(),
    }


def social_reputation(role, query=None):
    """**Reworked session 83** (Sam: "we need a hootsuit-style social suite merged
    with reputation management -- multi platform post builder, social content
    calendar, competitor social tracking, and a reputation toggle... bot function to
    respond to reviews / alert for bad reviews"). Replaces the old standalone
    reputation() item -- this Menu Bar item is now Social + Reputation combined behind
    one "toggle" (the `section` field on the response), per Sam's own framing.

    Social half is genuinely new this session: core/social_posts.py's real (simulated-
    publish) SocialPost entities + content calendar. Reputation half reuses
    core/workflow_tab_data.py's marketing_reputation_summary() (real seeded Review
    entities, session 59) exactly as the old reputation() item did, now via
    core/reputation_api.py so the bad-review alert queue and simulated competitor
    tracking (both new this session) are included too. Review Requests, GM
    Escalations, and Customer Recovery Workflows still have no backing automation/
    workflow data model -- unchanged gap from the old reputation() item."""

    if query:
        reviews = [
            r for r in _entities(REVIEW)
            if query.lower() in str(r.attributes.get("author_name", "")).lower()
            or query.lower() in str(r.attributes.get("text", "")).lower()
        ]
        posts = [
            p for p in list_social_posts()
            if query.lower() in str(p.attributes.get("content", "")).lower()
        ]
        return {
            "query": query,
            "count": len(reviews) + len(posts),
            "results": {
                "reviews": [
                    {
                        "id": r.id,
                        "platform": r.attributes.get("platform"),
                        "rating": r.attributes.get("rating"),
                        "author_name": r.attributes.get("author_name"),
                        "text": r.attributes.get("text"),
                        "responded": r.attributes.get("responded"),
                    }
                    for r in reviews
                ],
                "posts": [
                    {"id": p.id, "platform": p.attributes.get("platform"), "content": p.attributes.get("content"), "status": p.attributes.get("status")}
                    for p in posts
                ],
            },
        }

    summary = marketing_reputation_summary(role)

    return {
        "social": {
            "platforms": list_social_platforms(),
            "recent_posts": [
                {"id": p.id, "platform": p.attributes.get("platform"), "content": (p.attributes.get("content") or "")[:120], "status": p.attributes.get("status"), "scheduled_time": p.attributes.get("scheduled_time")}
                for p in list_social_posts()[:10]
            ],
            "calendar": get_social_calendar(),
            "not_yet_tracked": {
                "real_platform_publishing": "This sandbox has no real Facebook/Instagram/X/LinkedIn/TikTok API access -- publishing is a real, simulated graph action (see core/social_posts.py).",
                "post_engagement": "No likes/comments/shares data exists -- no real platform connection to pull it from.",
            },
        },
        "reputation": {
            **summary,
            "response_management": {
                "queue": summary.get("unresponded_negative", []),
                "count": summary.get("unresponded_negative_count", 0),
            },
            "bad_review_alerts": list_bad_review_alerts_api(role),
            "competitor_tracking": get_competitor_tracking_api(role),
            "not_yet_tracked": {
                "review_requests": "No automated review-request send capability exists yet.",
                "csi": "No customer-satisfaction survey data model exists yet.",
                "open_cases": "No case/ticket data model exists yet -- unresponded_negative is the real proxy.",
                "gm_escalations": "No escalation-routing tie-in exists for reviews yet (core/escalation_routing.py handles leads, not reviews).",
                "customer_recovery_workflows": "No recovery-workflow automation exists yet.",
            },
        },
    }


def advertising(role, query=None):
    """New session 83 Menu Bar item (Sam: "advertising dash... start meta and google
    ad campaigns that include inventory and allow ai recommendations / building, or
    granular control"). Real core/advertising.py AdCampaign entities -- an AI-drafted
    or fully manual headline/copy/targeting, launched as an honestly-labeled SIMULATED
    action (no real Meta/Google Ads API access in this sandbox, matching
    core/campaigns.py's activate_campaign()/core/social_posts.py's publish_post()
    precedent). Inventory integration is the same live-query pattern as
    core/websites.py -- an ad's linked_vehicle_ids resolve against real unsold Vehicle
    entities, never a copied snapshot."""

    if query:
        campaigns = [
            c for c in list_ad_campaigns()
            if query.lower() in str(c.attributes.get("name", "")).lower()
            or query.lower() in str(c.attributes.get("headline", "")).lower()
        ]
        return {
            "query": query,
            "count": len(campaigns),
            "results": [
                {"id": c.id, "platform": c.attributes.get("platform"), "name": c.attributes.get("name"), "status": c.attributes.get("status")}
                for c in campaigns
            ],
        }

    campaigns = list_ad_campaigns()

    by_status = {}
    by_platform = {}

    for c in campaigns:
        status = c.attributes.get("status", "draft")
        platform = c.attributes.get("platform", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_platform[platform] = by_platform.get(platform, 0) + 1

    return {
        "platforms": list_ad_platforms(),
        "objectives": list_ad_objectives(),
        "total_campaigns": len(campaigns),
        "by_status": by_status,
        "by_platform": by_platform,
        "recent_campaigns": [
            {
                "id": c.id,
                "platform": c.attributes.get("platform"),
                "objective": c.attributes.get("objective"),
                "name": c.attributes.get("name"),
                "status": c.attributes.get("status"),
                "ai_generated": c.attributes.get("ai_generated"),
                "daily_budget": c.attributes.get("daily_budget"),
            }
            for c in campaigns[:15]
        ],
        "not_yet_tracked": {
            "performance_metrics": "impressions/clicks/CPC/spend/ROAS -- no real Meta/Google Ads API connection exists in this sandbox.",
            "audience_size_estimate": "No real platform audience-size API to query.",
        },
    }


def studio(role):
    """2026-07-19 -- the AI Marketing Studio Top Menu item, continuing Sam's
    six-pillar spec. A thin pass-through to core/marketing_studio_api.py's real
    studio overview (the 7-content-type catalog + real drafted/applied/discarded
    stats) -- deferred import, same circular-import-avoidance convention this
    module already uses elsewhere for sibling modules. The real generate/apply/
    discard actions live behind their own dedicated /marketing-studio/* routes,
    not this GET-only menu view."""

    from core.marketing_studio_api import get_studio_overview_api

    return get_studio_overview_api(role)


def analytics(role):
    """Session 113 follow-up -- the Attribution Engine + Marketing ROI Dashboard +
    Vehicle Attribution capstone. NOT a revival of the original marketing.pdf's
    "Analytics" item (dropped as a standalone item at session 62, folded into
    embedded features) -- this is a new, genuinely new capability: Sam's own
    Growth Platform reframe named Attribution as the capstone, "most valuable
    once other channels are feeding it real event data," which is now true
    after the CRM/PURLs/Email-SMS slices this same rebuild arc already shipped.
    See core/marketing_attribution.py for the full reasoning and honesty notes
    (real first-touch attribution off Lead.Source, not fabricated multi-touch)."""

    return get_marketing_roi_dashboard_api(role)


def reporting(role):
    """marketing2.pdf's "Reporting" item -- Advertising (CPL/CPC/ROAS) and Event
    reports have no backing data model (no ad-spend ledger, no Event entity).
    Campaign/Website/Opportunity reports are real rollups off the same data the other
    7 items already surface. Forecasting reuses core/prediction.py's real ledger-based
    leads_generated forecast (readiness_predictions_api's "marketing" department entry,
    same pattern core/sales_menu.py's reporting() uses for "sales")."""

    all_campaigns = list_campaigns()
    completed = [c for c in all_campaigns if c.attributes.get("status") in ("active", "completed")]
    total_sent = sum(c.attributes.get("sent_count", 0) for c in completed)

    all_sites = list_websites()
    published_sites = [s for s in all_sites if s.attributes.get("status") == "published"]

    equity = marketing_database_mining(role)
    lease = preview_audience("finance_renewal", {"months_to_maturity": 6})
    retention = preview_audience("retention", {"months_since_service": 12})

    readiness = readiness_predictions_api()
    marketing_forecast = next((d for d in readiness.get("departments", []) if d["department"] == "marketing"), None)

    return {
        "campaign_reports": {
            "total_campaigns": len(all_campaigns),
            "active_or_completed": len(completed),
            "total_audience_reached": total_sent,
        },
        "website_reports": {
            "total_websites": len(all_sites),
            "published": len(published_sites),
        },
        "opportunity_reports": {
            "equity_pool_size": equity.get("count", 0),
            "lease_pool_size": lease.get("count", 0),
            "retention_pool_size": retention.get("count", 0),
        },
        "forecasting": marketing_forecast,
        "department_intelligence": _DI_GAP_NOTE,
        "not_yet_tracked": {
            "advertising_reports": "No ad-spend/click-tracking ledger exists yet (CPL/CPC/ROAS).",
            "event_reports": "No Event entity exists yet (RSVP Rate/Attendance/Sales/Revenue).",
            "website_conversion_form_submissions_traffic_sources": "No web-analytics event store exists yet -- only which sites have an analytics ID configured is known (see the 'website' menu item).",
            "opportunity_conversions": "No Campaign/Lead/Deal linkage exists yet to compute real equity/lease/retention conversion rates.",
            "executive_revenue_attribution_and_marketing_roi": "No multi-touch attribution model exists yet.",
            "customer_acquisition_cost": "No ad-spend ledger exists yet to divide against acquisitions.",
            "lifetime_value": "No LTV computation exists yet in this codebase.",
        },
    }


def inventory_advertising(role):
    """Marketing's "Inventory Advertising" view (2026-07-23) -- a thin, role-gated
    pass-through to core/inventory_advertising_api.py's real advertising overview.
    Mirrors operations_menu.customer_journey."""

    return {
        "inventory_advertising": get_advertising_overview_api(role),
        "note": "Inventory advertising campaign overview (Marketing department).",
    }


def loyalty(role):
    """Marketing's "Loyalty" view (2026-07-23) -- a thin, role-gated pass-through
    to core/loyalty_api.py's real loyalty overview (no AI). Mirrors
    operations_menu.customer_journey."""

    return {
        "loyalty": get_loyalty_overview_api(role),
        "note": "Loyalty ledger and redemption overview (Marketing department).",
    }
