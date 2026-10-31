"""
core/provider_catalog.py -- a real, tenant-side named-provider catalog (Freemium Platform roadmap,
Phase 3, 2026-08-03).

Phase 3's finding was that the Hub's Integrations Center and Migration Tracking are honest manual
data entry -- there is no real provider catalog for Google, Microsoft, Meta, CDK, DealerTrack,
RouteOne, Xtime, and no automatic connector or record-count comparison for the DMS/CRM migration
sources (CDK, Reynolds, Tekion, DealerSocket, VinSolutions, HubSpot). Building the actual OAuth/API
connectors needs credentials the dealer supplies later; building the CATALOG those screens read does
not. This is that catalog: a real, structured list of the providers NXTDeal integrates with or
migrates from, each with the metadata the Integrations Center / Migration Tracking need (category,
capabilities, auth type, whether it is a DMS/CRM migration source, and whether it needs credentials
before it can go live).

It composes with the two existing structured provider sources rather than duplicating them:
  * core/integrations_registry.py CAPABILITIES -- capability -> recommended provider + live/simulated
    status via is_live()/provider_status(). This catalog cross-references that so an entry can report
    whether its capability is actually live yet.
  * core/provider_credentials.py PROVIDER_OPTIONS -- the credential builder slots.

Static data (a price/partners sheet, not per-dealer state), so no persistence -- the per-dealer
"which provider did the dealer pick / connect" facts already live in INTEGRATION_SETTINGS /
PROVIDER_CREDENTIAL.
"""

# Auth styles the Integrations Center needs to know to render the right connect flow.
AUTH_API_KEY = "api_key"
AUTH_OAUTH = "oauth"
AUTH_FEED = "feed"          # a URL/file inventory or data feed
AUTH_WEBHOOK = "webhook"
AUTH_NONE = "none"          # keyless (e.g. NHTSA vPIC)

# Categories the Hub groups providers by.
CATEGORIES = ("dms", "crm", "inventory", "productivity", "advertising", "payments",
              "identity", "credit", "banking", "telephony", "esignature", "vehicle_data")


def _p(key, name, category, capabilities, auth_type, migration_source=False,
       requires_credentials=True, status="planned", notes=""):
    return {
        "key": key,
        "name": name,
        "category": category,
        "capabilities": capabilities,
        "auth_type": auth_type,
        "migration_source": migration_source,   # a DMS/CRM a dealer would migrate OFF of
        "requires_credentials": requires_credentials,
        "status": status,                        # "live" | "beta" | "planned"
        "notes": notes,
    }


# The catalog. `status` is the *build* status of NXTDeal's connector for that provider, not whether
# a given dealer has connected it. "live" means a real connector exists in this codebase today.
PROVIDERS = [
    # --- DMS / CRM migration sources (Phase 3 "Readiness / migration-path" work) ---
    _p("cdk", "CDK Global", "dms", ["inventory", "crm", "service"], AUTH_API_KEY,
       migration_source=True, notes="Franchise DMS. Migration source; connector planned."),
    _p("reynolds", "Reynolds & Reynolds", "dms", ["inventory", "crm", "service"], AUTH_API_KEY,
       migration_source=True, notes="Franchise DMS. Migration source; connector planned."),
    _p("tekion", "Tekion", "dms", ["inventory", "crm", "service"], AUTH_API_KEY,
       migration_source=True, notes="Cloud DMS. Migration source; connector planned."),
    _p("dealersocket", "DealerSocket", "crm", ["crm"], AUTH_API_KEY,
       migration_source=True, notes="Dealer CRM. Migration source; connector planned."),
    _p("vinsolutions", "VinSolutions", "crm", ["crm"], AUTH_API_KEY,
       migration_source=True, notes="Dealer CRM. Migration source; connector planned."),
    _p("hubspot", "HubSpot", "crm", ["crm"], AUTH_OAUTH,
       migration_source=True, notes="General CRM. Migration source; connector planned."),
    _p("dealertrack", "Dealertrack", "dms", ["finance", "inventory"], AUTH_API_KEY,
       migration_source=True, notes="F&I / registration. Migration + finance source; planned."),
    _p("routeone", "RouteOne", "dms", ["finance"], AUTH_API_KEY,
       migration_source=True, notes="F&I credit aggregation; connector planned."),
    _p("xtime", "Xtime", "dms", ["service"], AUTH_API_KEY,
       migration_source=True, notes="Service scheduling; connector planned."),

    # --- Productivity (Phase 3 self-serve email/calendar logging) ---
    _p("google", "Google Workspace", "productivity", ["email_logging", "calendar"], AUTH_OAUTH,
       notes="Gmail/Calendar logging for the free tier; OAuth connector planned."),
    _p("microsoft", "Microsoft 365", "productivity", ["email_logging", "calendar"], AUTH_OAUTH,
       notes="Outlook/Calendar logging for the free tier; OAuth connector planned."),

    # --- Advertising ---
    _p("meta_ads", "Meta Ads", "advertising", ["ads"], AUTH_OAUTH,
       notes="Marketing Module advertising; maps to integrations_registry 'ads'."),
    _p("google_ads", "Google Ads", "advertising", ["ads"], AUTH_OAUTH,
       notes="Marketing Module advertising; maps to integrations_registry 'ads'."),

    # --- Capability providers already modeled in integrations_registry ---
    _p("stripe", "Stripe", "payments", ["payments", "identity"], AUTH_API_KEY,
       notes="Payments + Stripe Identity; integrations_registry 'payments'/'identity'."),
    _p("plaid", "Plaid", "banking", ["banking"], AUTH_API_KEY,
       notes="Personal-tools bank link (MySales); integrations_registry 'banking' (personal layer)."),
    _p("twilio", "Twilio", "telephony", ["notifications", "telephony"], AUTH_API_KEY,
       notes="Connect Module phone/SMS; integrations_registry 'telephony'/'notifications'."),
    _p("ringcentral", "RingCentral", "telephony", ["telephony"], AUTH_API_KEY,
       notes="Connect Module telephony alternative."),
    _p("docusign", "DocuSign", "esignature", ["esignature"], AUTH_API_KEY,
       notes="Contracting e-signature; integrations_registry 'esignature'."),
    _p("experian", "Experian", "credit", ["credit_bureau", "enrichment"], AUTH_API_KEY,
       notes="Finance Module credit pull + data enrichment."),
    _p("equifax", "Equifax", "credit", ["credit_bureau"], AUTH_API_KEY,
       notes="Finance Module credit pull."),
    _p("transunion", "TransUnion", "credit", ["credit_bureau"], AUTH_API_KEY,
       notes="Finance Module credit pull."),

    # --- Vehicle data (already real + keyless) ---
    _p("nhtsa_vpic", "NHTSA vPIC", "vehicle_data", ["vin_decode"], AUTH_NONE,
       migration_source=False, requires_credentials=False, status="live",
       notes="Keyless VIN decode -- already wired (core/vin_decoder.py). No credentials needed."),
]

_BY_KEY = {p["key"]: p for p in PROVIDERS}


def _capability_live_map():
    """capability -> is_live(), from integrations_registry, so the catalog can tell the Hub which of
    a provider's capabilities are actually connected on this dealer today. Best-effort."""
    try:
        from core import integrations_registry as ir
        return {cap: ir.is_live(cap) for cap in ir.CAPABILITIES}
    except Exception:
        return {}


def get_provider_catalog():
    """The full provider catalog, each entry annotated with which of its capabilities are live on
    this dealer right now (via integrations_registry)."""
    live = _capability_live_map()
    out = []
    for p in PROVIDERS:
        entry = dict(p)
        entry["live_capabilities"] = [c for c in p["capabilities"] if live.get(c)]
        entry["any_capability_live"] = bool(entry["live_capabilities"])
        out.append(entry)
    return {
        "providers": out,
        "categories": list(CATEGORIES),
        "count": len(out),
        "migration_source_count": sum(1 for p in PROVIDERS if p["migration_source"]),
    }


def list_migration_sources():
    """Just the DMS/CRM sources a dealer would migrate OFF of -- what the Hub's Migration Tracking
    screen should offer instead of a free-text box."""
    return [dict(p) for p in PROVIDERS if p["migration_source"]]


def get_provider(key):
    p = _BY_KEY.get(key)
    return dict(p) if p else None
