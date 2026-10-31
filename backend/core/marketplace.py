"""
core/marketplace.py -- the NXTDeal Marketplace (2026-07-24, Sam's spec).

The Marketplace is how NXTDeal grows beyond what NXTDeal can build internally: a curated,
certified catalog of the integrations, connectors, and (later) AI skills / workflow packs /
themes a dealer installs with a single click, while all data still flows through NXTDeal as
the system of record. It is deliberately a CLOSED, reviewed catalog on Day 1 -- no public
developer uploads, no community plugins -- every listing is NXTDeal-reviewed.

Honesty, same bar as the rest of NXTDeal: installing a listing records a real, per-dealer
install (a MarketplaceInstall entity) but does NOT fabricate a live external connection. A
listing that maps to an integration capability (core/integrations_registry.py) is only reported
"connected" when a REAL adapter is registered in code; installing it without an adapter is an
honest "installed (simulated)" -- the intended provider is recorded via the same
integrations_registry.configure_provider seam so wiring the adapter later flips it live with no
catalog change.

State machine per listing (resolved live, never stored):
  coming_soon  -> Phase 2 listing (AI skills, packs, themes, partners) -- not installable yet
  connected    -> capability-backed AND integrations_registry.is_live(capability)
  installed    -> a live MarketplaceInstall exists (simulated connection)
  available    -> everything else, one click from installed

The graph is append-only (no ledger.remove_entity), so uninstall is a soft status flip.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import MARKETPLACE_INSTALL
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import integrations_registry


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------------------------
# CATEGORIES -- the Day 1 shelf. `capability` (optional) ties every listing in the category to a
# core/integrations_registry.py capability so install-state can reflect a real adapter going live.
# `section`: "day1" (integrations), "oem" (OEM programs area), "phase2" (coming soon).
# ---------------------------------------------------------------------------------------------

CATEGORIES = [
    {"id": "communications", "name": "Communications", "section": "day1", "capability": "notifications",
     "icon": "📞", "blurb": "Voice, SMS, MMS, video, and phone migration -- powering NXTDeal Connect.",
     "purpose": ["Voice", "SMS", "MMS", "Video", "Phone migration"]},
    {"id": "identity", "name": "Identity & Fraud", "section": "day1", "capability": "identity",
     "icon": "🪪", "blurb": "Identity verification, license scanning, and fraud prevention for Digital Retail.",
     "purpose": ["Identity verification", "License scanning", "Fraud prevention", "Selfie matching"]},
    {"id": "finance_credit", "name": "Finance & Credit", "section": "day1", "capability": "credit_bureau",
     "icon": "💳", "blurb": "Credit aggregation and bureau pulls -- mandatory for financing.",
     "purpose": ["Credit applications", "Bureau pulls", "Lender routing", "Decisioning"]},
    {"id": "esign", "name": "Electronic Signatures", "section": "day1", "capability": None,
     "icon": "✍️", "blurb": "Legally-binding e-signature for contracts and paperwork.",
     "purpose": ["Contract signing", "Remote signing", "Audit trail"]},
    {"id": "dms", "name": "DMS Integrations", "section": "day1", "capability": None,
     "icon": "🗄️", "blurb": "Dealer management system connectors for migration and hybrid dealers.",
     "purpose": ["Migration", "Hybrid operation", "Accounting sync"]},
    {"id": "crm", "name": "CRM Integrations", "section": "day1", "capability": None,
     "icon": "📇", "blurb": "Bring existing CRM data in -- key for Dealer Network adoption.",
     "purpose": ["Lead sync", "Customer history", "Migration"]},
    {"id": "service", "name": "Service Integrations", "section": "day1", "capability": None,
     "icon": "🔧", "blurb": "Service scheduling and communication platforms.",
     "purpose": ["Online scheduling", "Service comms", "Multi-point inspection"]},
    {"id": "inventory_valuation", "name": "Inventory & Valuation", "section": "day1", "capability": None,
     "icon": "🚗", "blurb": "Live market pricing, appraisal, and book values.",
     "purpose": ["Market pricing", "Appraisal", "Book values", "Trade valuation"]},
    {"id": "gps_bhph", "name": "GPS & Starter Interrupt", "section": "day1", "capability": None,
     "icon": "📡", "blurb": "GPS tracking and starter-interrupt devices -- critical for BHPH.",
     "purpose": ["GPS tracking", "Starter interrupt", "Recovery", "Payment reminders"]},
    {"id": "payments", "name": "Payments", "section": "day1", "capability": "payments",
     "icon": "💵", "blurb": "Card and ACH processing for deposits, down payments, and service.",
     "purpose": ["Deposits", "Down payments", "Service payment", "Recurring BHPH"]},
    {"id": "advertising", "name": "Advertising", "section": "day1", "capability": None,
     "icon": "📣", "blurb": "Paid media platforms for marketing campaigns.",
     "purpose": ["Paid social", "Search", "Video", "Retargeting"]},
    {"id": "reputation", "name": "Reputation", "section": "day1", "capability": None,
     "icon": "⭐", "blurb": "Review platforms and reputation management.",
     "purpose": ["Review collection", "Response", "Monitoring"]},
    {"id": "accounting", "name": "Accounting", "section": "day1", "capability": None,
     "icon": "📊", "blurb": "General-ledger and accounting platform sync.",
     "purpose": ["GL sync", "Reconciliation", "Financial reporting"]},
]

# OEM Programs get a dedicated area -- each brand is a "listing" that unlocks compliance, OEM
# programs, co-op advertising, and data feeds for that manufacturer.
OEM_CATEGORY = {
    "id": "oem", "name": "OEM Programs", "section": "oem", "capability": None,
    "icon": "🏁", "blurb": "Manufacturer compliance, programs, co-op advertising, and certified data feeds.",
    "purpose": ["Compliance", "OEM programs", "Co-op advertising", "Data feeds"],
}

# Phase 2 shelves -- installable AI modules, workflow/marketing packs, themes, and the dealer
# partner network. Listed now as "coming soon" so the shape of the Marketplace is visible.
PHASE2_CATEGORIES = [
    {"id": "ai_skills", "name": "AI Skills", "section": "phase2", "capability": None,
     "icon": "🧠", "blurb": "Installable AI modules that plug into the AI Workforce.",
     "purpose": ["Coaching", "Automation", "Specialized agents"]},
    {"id": "workflow_packs", "name": "Workflow Packs", "section": "phase2", "capability": None,
     "icon": "🧩", "blurb": "Ready-to-install process packs for a store type or OEM.",
     "purpose": ["Store-type workflows", "OEM workflows", "BHPH"]},
    {"id": "marketing_packs", "name": "Marketing Packs", "section": "phase2", "capability": None,
     "icon": "🎯", "blurb": "Seasonal campaign packs ready to launch.",
     "purpose": ["Seasonal events", "Templates", "Calendars"]},
    {"id": "themes", "name": "Website Themes", "section": "phase2", "capability": None,
     "icon": "🎨", "blurb": "Installable themes for the NXTDeal website builder.",
     "purpose": ["Store branding", "OEM styling", "Fast launch"]},
    {"id": "partners", "name": "NXTDeal Network Partners", "section": "phase2", "capability": None,
     "icon": "🤝", "blurb": "Powered By Dealers -- top stores publish playbooks, campaigns, and workflows (anonymously). Ties into the AI 20 Group.",
     "purpose": ["Playbooks", "Campaigns", "Workflows", "Processes"]},
]

ALL_CATEGORIES = CATEGORIES + [OEM_CATEGORY] + PHASE2_CATEGORIES


def _cat(cid):
    for c in ALL_CATEGORIES:
        if c["id"] == cid:
            return c
    return None


# ---------------------------------------------------------------------------------------------
# LISTINGS. `badge` surfaces "Migration" / "OEM" / "NXTDeal" (first-party) hints. `phase`:
# "day1" installable now, "phase2" coming soon. `capability` overrides the category default
# (usually inherited). Kept as plain data so adding a listing is a one-line edit.
# ---------------------------------------------------------------------------------------------

def _L(id, name, category, blurb="", badge=None, phase="day1", capability="__inherit__", provider=None):
    cat = _cat(category)
    cap = cat["capability"] if capability == "__inherit__" else capability
    return {
        "id": id, "name": name, "category": category, "blurb": blurb,
        "badge": badge, "phase": phase, "capability": cap,
        "provider": provider or name,
    }


LISTINGS = [
    # Communications
    _L("twilio", "Twilio", "communications", "Programmable voice, SMS, MMS, and video."),
    _L("bandwidth", "Bandwidth", "communications", "Carrier-grade voice and messaging."),
    _L("sinch", "Sinch", "communications", "Global messaging and voice APIs."),
    _L("ringcentral", "RingCentral", "communications", "Migrate an existing RingCentral phone system.", badge="Migration"),
    _L("dialpad", "Dialpad", "communications", "Migrate an existing Dialpad phone system.", badge="Migration"),
    _L("zoom_phone", "Zoom Phone", "communications", "Migrate an existing Zoom Phone system.", badge="Migration"),

    # Identity & Fraud
    _L("persona", "Persona", "identity", "Identity verification and KYC."),
    _L("veriff", "Veriff", "identity", "Document + biometric identity verification."),
    _L("jumio", "Jumio", "identity", "ID scanning and selfie matching."),

    # Finance & Credit
    _L("routeone", "RouteOne", "finance_credit", "Credit application aggregation and lender routing.", capability=None),
    _L("dealertrack_credit", "Dealertrack Credit", "finance_credit", "Credit aggregation and eContracting.", capability=None),
    _L("credit700", "700Credit", "finance_credit", "Credit reports, compliance, and prescreen."),
    _L("equifax", "Equifax", "finance_credit", "Consumer credit bureau."),
    _L("experian", "Experian", "finance_credit", "Consumer credit bureau."),
    _L("transunion", "TransUnion", "finance_credit", "Consumer credit bureau."),

    # E-Signatures
    _L("docusign", "DocuSign", "esign", "Electronic signature and agreement workflow."),
    _L("adobe_sign", "Adobe Sign", "esign", "Adobe Acrobat Sign e-signature."),
    _L("dealeros_sign", "NXTDeal Sign", "esign", "First-party e-signature, built into NXTDeal.", badge="NXTDeal", phase="phase2"),

    # DMS
    _L("cdk", "CDK Global", "dms", "CDK DMS integration and migration."),
    _L("reynolds", "Reynolds & Reynolds", "dms", "Reynolds DMS integration."),
    _L("tekion", "Tekion", "dms", "Tekion cloud DMS integration."),
    _L("autosoft", "AutoSoft", "dms", "AutoSoft DMS integration."),
    _L("dealertrack_dms", "Dealertrack DMS", "dms", "Dealertrack DMS integration."),

    # CRM
    _L("vinsolutions", "VinSolutions", "crm", "VinSolutions CRM sync and migration."),
    _L("elead", "Elead", "crm", "Elead CRM sync and migration."),
    _L("dealersocket", "DealerSocket", "crm", "DealerSocket CRM sync and migration."),
    _L("hubspot", "HubSpot", "crm", "HubSpot CRM and marketing sync."),
    _L("salesforce", "Salesforce", "crm", "Salesforce CRM sync."),

    # Service
    _L("xtime", "Xtime", "service", "Service scheduling and customer experience."),
    _L("dealerfx", "DealerFX", "service", "Service lane and communication platform."),
    _L("mykaarma", "myKaarma", "service", "Service communication and scheduling."),

    # Inventory & Valuation
    _L("vauto", "vAuto", "inventory_valuation", "Market-based inventory pricing."),
    _L("cbb", "Canadian Black Book", "inventory_valuation", "Canadian vehicle valuations."),
    _L("jdpower", "J.D. Power", "inventory_valuation", "Valuation and market data."),
    _L("kbb", "Kelley Blue Book", "inventory_valuation", "KBB valuations and trade-in."),
    _L("blackbook", "Black Book", "inventory_valuation", "Wholesale and retail valuations."),

    # GPS & Starter Interrupt
    _L("passtime", "PassTime", "gps_bhph", "GPS and starter-interrupt for BHPH."),
    _L("spireon", "Spireon", "gps_bhph", "GPS fleet and BHPH device management."),
    _L("goldstar", "GoldStar", "gps_bhph", "GPS tracking and recovery."),
    _L("calamp", "CalAmp", "gps_bhph", "Telematics and GPS devices."),

    # Payments
    _L("stripe", "Stripe", "payments", "Card and ACH payment processing."),
    _L("authorizenet", "Authorize.net", "payments", "Payment gateway."),
    _L("worldpay", "Worldpay", "payments", "Card processing."),
    _L("global_payments", "Global Payments", "payments", "Card processing."),
    _L("elavon", "Elavon", "payments", "Merchant payment processing."),
    _L("fiserv", "Fiserv", "payments", "Payment and merchant services."),
    _L("dealeros_payments", "NXTDeal Payments", "payments", "First-party payments, built into NXTDeal.", badge="NXTDeal", phase="phase2"),

    # Advertising
    _L("meta_ads", "Meta", "advertising", "Facebook and Instagram advertising."),
    _L("google_ads", "Google Ads", "advertising", "Search, display, and PMax."),
    _L("youtube_ads", "YouTube", "advertising", "Video advertising."),
    _L("microsoft_ads", "Microsoft Advertising", "advertising", "Bing search advertising."),

    # Reputation
    _L("google_reviews", "Google Reviews", "reputation", "Collect and respond to Google reviews."),
    _L("facebook_reviews", "Facebook Reviews", "reputation", "Facebook recommendations."),
    _L("dealerrater", "DealerRater", "reputation", "Automotive-specific reviews."),
    _L("yelp", "Yelp", "reputation", "Yelp reviews and listing."),

    # Accounting
    _L("quickbooks", "QuickBooks", "accounting", "QuickBooks GL sync."),
    _L("sage", "Sage", "accounting", "Sage accounting sync."),
    _L("dynamics", "Microsoft Dynamics", "accounting", "Dynamics 365 finance sync."),
    _L("netsuite", "NetSuite", "accounting", "NetSuite ERP sync."),

    # Phase 2 -- AI Skills
    _L("ai_sales_coach", "Sales Coach", "ai_skills", "AI coaching for the sales floor.", phase="phase2"),
    _L("ai_service_coach", "Service Coach", "ai_skills", "AI coaching for service advisors.", phase="phase2"),
    _L("ai_fi_coach", "F&I Coach", "ai_skills", "AI coaching for the F&I office.", phase="phase2"),
    _L("ai_marketing_planner", "Marketing Planner", "ai_skills", "AI marketing planning module.", phase="phase2"),
    _L("ai_bdc_coach", "BDC Coach", "ai_skills", "AI coaching for the BDC.", phase="phase2"),
    _L("ai_collections", "Collection Specialist", "ai_skills", "AI collections agent.", phase="phase2"),

    # Phase 2 -- Workflow Packs
    _L("wf_ford_service", "Ford Service Workflow", "workflow_packs", "Ford-specific service process pack.", phase="phase2"),
    _L("wf_toyota_delivery", "Toyota Delivery Workflow", "workflow_packs", "Toyota delivery process pack.", phase="phase2"),
    _L("wf_luxury", "Luxury Store Workflow", "workflow_packs", "Luxury retail process pack.", phase="phase2"),
    _L("wf_bhph", "BHPH Workflow Pack", "workflow_packs", "Buy-here-pay-here process pack.", phase="phase2"),

    # Phase 2 -- Marketing Packs
    _L("mk_truck_month", "Truck Month", "marketing_packs", "Truck Month campaign pack.", phase="phase2"),
    _L("mk_tax_season", "Tax Season", "marketing_packs", "Tax-season campaign pack.", phase="phase2"),
    _L("mk_lease_pull", "Lease Pull Ahead", "marketing_packs", "Lease pull-ahead campaign pack.", phase="phase2"),
    _L("mk_private_sale", "Private Sale Event", "marketing_packs", "Private-sale event pack.", phase="phase2"),

    # Phase 2 -- Website Themes
    _L("theme_ford", "Ford Theme", "themes", "Ford-styled website theme.", phase="phase2"),
    _L("theme_toyota", "Toyota Theme", "themes", "Toyota-styled website theme.", phase="phase2"),
    _L("theme_luxury", "Luxury Theme", "themes", "Luxury website theme.", phase="phase2"),
    _L("theme_truck", "Truck Theme", "themes", "Truck-focused website theme.", phase="phase2"),
    _L("theme_independent", "Independent Theme", "themes", "Independent dealer theme.", phase="phase2"),
    _L("theme_bhph", "BHPH Theme", "themes", "BHPH website theme.", phase="phase2"),

    # Phase 2 -- NXTDeal Network Partners (Powered By Dealers)
    _L("partner_playbooks", "Partner Playbooks", "partners", "Install top-store playbooks (anonymized).", phase="phase2"),
    _L("partner_campaigns", "Partner Campaigns", "partners", "Install proven campaigns from the network.", phase="phase2"),
    _L("partner_workflows", "Partner Workflows", "partners", "Install winning workflows from the network.", phase="phase2"),
    _L("partner_processes", "Partner Processes", "partners", "Install high-performing processes.", phase="phase2"),
]

# OEM brands -> synthesized as listings in the OEM area (each unlocks the four OEM purposes).
OEM_BRANDS = [
    "Ford", "GM", "Toyota", "Honda", "Stellantis",
    "Hyundai", "Kia", "Nissan", "BMW", "Mercedes-Benz",
]
for _brand in OEM_BRANDS:
    LISTINGS.append(_L(
        f"oem_{_brand.lower().replace(' ', '_').replace('-', '_')}",
        _brand, "oem",
        f"{_brand} compliance, programs, co-op advertising, and certified data feeds.",
        badge="OEM",
    ))


def _listing(listing_id):
    for l in LISTINGS:
        if l["id"] == listing_id:
            return l
    return None


# ---------------------------------------------------------------------------------------------
# Install state (per-dealer MarketplaceInstall entities; append-only -> soft status).
# ---------------------------------------------------------------------------------------------

def _installs():
    """listing_id -> the most recent MarketplaceInstall entity for it."""
    out = {}
    for e in ledger.get_all().values():
        if e.entity_type == MARKETPLACE_INSTALL:
            lid = e.attributes.get("listing_id")
            if lid:
                out[lid] = e  # dict insertion keeps last; installs are re-used/flipped, see install
    return out


def _install_for(listing_id):
    return _installs().get(listing_id)


def _resolve_state(listing, install):
    """The live state for a listing. Never stored -- computed from Phase, adapter presence, and
    whether an active install exists."""
    if listing["phase"] == "phase2":
        return "coming_soon"
    cap = listing.get("capability")
    if cap and integrations_registry.is_live(cap):
        return "connected"
    if install and install.attributes.get("status") == "installed":
        return "installed"
    return "available"


def _listing_view(listing, install):
    state = _resolve_state(listing, install)
    cap = listing.get("capability")
    return {
        "id": listing["id"],
        "name": listing["name"],
        "category": listing["category"],
        "blurb": listing["blurb"],
        "badge": listing["badge"],
        "phase": listing["phase"],
        "capability": cap,
        "state": state,
        "capability_live": bool(cap and integrations_registry.is_live(cap)),
        "installed_at": install.attributes.get("installed_at") if install and state == "installed" else None,
        "installed_by": install.attributes.get("installed_by") if install and state == "installed" else None,
    }


def _category_view(cat, installs):
    listings = [_listing_view(l, installs.get(l["id"])) for l in LISTINGS if l["category"] == cat["id"]]
    return {
        "id": cat["id"],
        "name": cat["name"],
        "section": cat["section"],
        "icon": cat["icon"],
        "blurb": cat["blurb"],
        "purpose": cat["purpose"],
        "capability": cat["capability"],
        "listing_count": len(listings),
        "listings": listings,
    }


def get_marketplace(role=None):
    """The full Marketplace: every category with its listings + live install state, plus a
    summary rollup. Read-only; open to any authenticated role."""
    installs = _installs()
    categories = [_category_view(c, installs) for c in ALL_CATEGORIES]

    all_listings = [l for c in categories for l in c["listings"]]
    def _count(state):
        return sum(1 for l in all_listings if l["state"] == state)

    summary = {
        "total_listings": len(all_listings),
        "categories": len(categories),
        "available": _count("available"),
        "installed": _count("installed"),
        "connected": _count("connected"),
        "coming_soon": _count("coming_soon"),
        "day1_categories": sum(1 for c in categories if c["section"] == "day1"),
        "oem_brands": sum(1 for l in LISTINGS if l["category"] == "oem"),
    }
    return {
        "summary": summary,
        "categories": categories,
        "sections": {
            "day1": [c["id"] for c in categories if c["section"] == "day1"],
            "oem": [c["id"] for c in categories if c["section"] == "oem"],
            "phase2": [c["id"] for c in categories if c["section"] == "phase2"],
        },
        "note": (
            "Every listing is NXTDeal-reviewed and certified. Installing records a real per-dealer "
            "install and (for integration listings) the intended provider; a listing shows "
            "'connected' only when a real adapter is registered in code -- otherwise it is an "
            "honest 'installed (simulated)' until that adapter is wired."
        ),
    }


def get_listing(listing_id):
    listing = _listing(listing_id)
    if not listing:
        return {"error": f"Unknown listing '{listing_id}'."}
    view = _listing_view(listing, _install_for(listing_id))
    cat = _cat(listing["category"])
    view["category_name"] = cat["name"] if cat else listing["category"]
    view["purpose"] = cat["purpose"] if cat else []
    return view


def install_listing(listing_id, admin_id="system"):
    """Install a listing for this dealer. Records a real MarketplaceInstall and, for a
    capability-backed listing, the intended provider via integrations_registry (informational --
    does NOT fabricate a live connection). Phase 2 listings are not installable yet."""
    listing = _listing(listing_id)
    if not listing:
        return {"error": f"Unknown listing '{listing_id}'."}
    if listing["phase"] == "phase2":
        return {"error": f"'{listing['name']}' is coming soon and can't be installed yet."}

    existing = _install_for(listing_id)
    if existing:
        existing.attributes["status"] = "installed"
        existing.attributes["installed_by"] = admin_id
        existing.attributes["installed_at"] = _now()
        existing.attributes["updated_at"] = _now()
        entity = existing
    else:
        entity = Entity(
            id=id_generator.generate("MKTI"),
            entity_type=MARKETPLACE_INSTALL,
            attributes={
                "listing_id": listing_id,
                "listing_name": listing["name"],
                "category": listing["category"],
                "status": "installed",
                "installed_by": admin_id,
                "installed_at": _now(),
                "updated_at": _now(),
            },
        )
        ledger.add_entity(entity)

    # Record the intended provider for a capability-backed listing (informational seam).
    cap = listing.get("capability")
    if cap:
        integrations_registry.configure_provider(cap, listing["name"], admin_id,
                                                  note="Configured via NXTDeal Marketplace install.")

    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="marketplace_listing_installed",
        summary=f"{admin_id} installed {listing['name']} from the Marketplace",
        entity_id=entity.id, actor=admin_id,
        details={"listing_id": listing_id, "category": listing["category"], "capability": cap},
    )
    return get_listing(listing_id)


def uninstall_listing(listing_id, admin_id="system"):
    """Soft-uninstall (append-only graph): flip the install to 'removed'. The capability's
    recorded provider is left as-is (informational; clearing it is a separate admin action)."""
    listing = _listing(listing_id)
    if not listing:
        return {"error": f"Unknown listing '{listing_id}'."}
    existing = _install_for(listing_id)
    if not existing or existing.attributes.get("status") != "installed":
        return {"error": f"'{listing['name']}' isn't installed."}
    existing.attributes["status"] = "removed"
    existing.attributes["updated_at"] = _now()
    existing.attributes["removed_by"] = admin_id
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="marketplace_listing_uninstalled",
        summary=f"{admin_id} removed {listing['name']} from the Marketplace",
        entity_id=existing.id, actor=admin_id,
        details={"listing_id": listing_id},
    )
    return get_listing(listing_id)
