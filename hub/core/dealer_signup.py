"""
hub/core/dealer_signup.py -- HubSpot-style self-serve dealer signup (NXTDeal Freemium / Free Forever
funnel, 2026-08-03).

A prospect on the marketing site (dealeros.xyz) clicks "Start Free", fills in name / work email /
dealership / "what kind of business are you", and this creates a real NXTDeal dealer account
automatically -- no sales conversation, no staff step -- and kicks off provisioning of their own
instance. Same growth motion HubSpot used: create free, put your data in, upgrade later.

What signup does (and deliberately doesn't):
  * Creates a Dealer on the FREE Foundation tier with the 20-seat Free Forever cap.
  * SUGGESTS the industry's package modules (from the Step-1 business type) but does NOT auto-buy
    them -- the roadmap is explicit that Step 3 pre-suggests without forcing a purchase.
  * Stamps created_via="self_serve" and last_activity_at=now so the inactivity lifecycle
    (dealer_lifecycle.py) has a clock from minute one.
  * Triggers provisioning through an injectable provisioner (the Hub's real Coolify path,
    hub_core/infra_provisioning.py); if none is bound it records status="provisioning" for the Hub's
    existing async provisioner/NOC to pick up -- signup never blocks on a deploy.

Persistence + provisioning are injected (see _signup_store.py) so the logic is unit-tested here and
drop-in for the real Hub.
"""

import re

from hub.core._signup_store import InMemoryDealerStore, utcnow


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FOUNDATION_TIER = "foundation"
FREE_SEAT_CAP = 20  # the Free Forever Foundation seat cap (marketing "20-free-seat" model)

# The six business types the marketing "What kind of business are you?" selector offers, each mapped
# to (a) the Hub's canonical industry_type (only four exist in hubApi.ts -- dealer_group/service_only
# collapse to their closest match, with the finer business_type kept verbatim), and (b) the paid
# Modules to SUGGEST (not purchase) -- the industry launch paths from the Freemium roadmap.
BUSINESS_TYPES = {
    "franchise": {
        "label": "Franchise Dealership",
        "industry_type": "franchise",
        "suggested_modules": ["sales", "service", "marketing"],
    },
    "independent": {
        "label": "Independent Dealership",
        "industry_type": "independent",
        "suggested_modules": ["sales", "marketing"],
    },
    "bhph": {
        "label": "Buy-Here-Pay-Here",
        "industry_type": "bhph",
        "suggested_modules": ["finance", "operations"],
    },
    "finance_company": {
        "label": "Finance Company",
        "industry_type": "finance_company",
        "suggested_modules": ["finance", "service"],
    },
    "dealer_group": {
        "label": "Dealer Group",
        "industry_type": "franchise",  # closest Hub industry_type; business_type kept as dealer_group
        "suggested_modules": ["network_premium", "sales", "service"],
    },
    "service_only": {
        "label": "Service-Only Operation",
        "industry_type": "independent",
        "suggested_modules": ["service"],
    },
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Free-mail domains a dealership signup usually shouldn't use for "work email" -- soft-flagged, not
# blocked (a small independent may legitimately use gmail), so we warn rather than reject.
_FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com"}


# ---------------------------------------------------------------------------
# Injected dependencies (bound once by the Hub; defaulted for tests/dev)
# ---------------------------------------------------------------------------

_store = InMemoryDealerStore()
_provisioner = None  # callable(record) -> dict | None ; None = leave for the Hub's async provisioner


def set_store(store):
    global _store
    _store = store


def set_provisioner(provisioner):
    """provisioner(record) is called after the dealer is created; it should start the real instance
    deploy (Coolify) and may return {api_url, frontend_url, ...}. If it raises, signup still succeeds
    and the dealer is left status='provisioning' for retry."""
    global _provisioner
    _provisioner = provisioner


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "dealer"


def _unique_slug(base):
    existing = {d.get("slug") for d in _store.all()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

def _email_taken(email):
    e = (email or "").strip().lower()
    return any((d.get("contact_email") or "").strip().lower() == e for d in _store.all())


def self_serve_signup(name, work_email, dealership_name, business_type,
                      contact_phone=None, network_opt_in=True, base_domain="dealeros.xyz"):
    """Create a free NXTDeal account and start provisioning. Returns a result dict with the new
    dealer + the instance URL to land the user in, or an {"error": ...} dict on bad input."""
    name = (name or "").strip()
    work_email = (work_email or "").strip()
    dealership_name = (dealership_name or "").strip()
    business_type = (business_type or "").strip().lower()

    if not dealership_name:
        return {"error": "A dealership name is required.", "field": "dealership_name"}
    if not _EMAIL_RE.match(work_email):
        return {"error": "A valid work email is required.", "field": "work_email"}
    if business_type not in BUSINESS_TYPES:
        return {"error": f"Pick a business type: {list(BUSINESS_TYPES)}.", "field": "business_type"}
    if _email_taken(work_email):
        return {"error": "An account already exists for that email. Try signing in.", "reason": "email_taken"}

    bt = BUSINESS_TYPES[business_type]
    slug = _unique_slug(_slugify(dealership_name))
    now = utcnow().isoformat()
    warnings = []
    domain = (work_email.split("@", 1)[1] or "").lower()
    if domain in _FREE_EMAIL_DOMAINS:
        warnings.append("Using a personal email — fine to start, but a work email is recommended.")

    record = {
        # Dealer shape (mirrors frontend/lib/hubApi.ts Dealer) --------------------------------
        "slug": slug,
        "name": dealership_name,
        "contact_name": name or None,
        "contact_email": work_email,
        "contact_phone": contact_phone or None,
        "address": None, "city": None, "state": None,
        "plan_tier": FOUNDATION_TIER,
        "status": "active",                     # self-serve accounts start active on Foundation
        "storage_dir": f"dealers/{slug}",
        "network_opt_in": bool(network_opt_in),
        "api_base_url": None,
        "created_by": "self_serve",
        "created_at": now,
        "group": None, "oem": None, "location_count": 1,
        "industry_type": bt["industry_type"],
        "active_modules": [FOUNDATION_TIER],    # free tier only; suggestions are NOT auto-bought
        "renewal_date": None,
        "seat_count": FREE_SEAT_CAP,
        "current_release": None,
        "beta_programs": [],
        # Freemium / lifecycle additions ----------------------------------------------------
        "created_via": "self_serve",
        "business_type": business_type,         # finer than industry_type (keeps dealer_group/service_only)
        "suggested_modules": list(bt["suggested_modules"]),  # shown as add-ons, not purchased
        "last_activity_at": now,                # inactivity clock starts now
        "suspended_reason": None,
        "deactivated_at": None,
        "scheduled_deletion_at": None,
    }

    record = _store.create(record)

    # Kick off provisioning. Never let a deploy failure fail the signup -- the Hub's async
    # provisioner / NOC retries a dealer left in "provisioning".
    provision = None
    if _provisioner is not None:
        try:
            provision = _provisioner(record)
            if isinstance(provision, dict):
                if provision.get("api_url"):
                    record["api_base_url"] = provision["api_url"]
                if provision.get("frontend_url"):
                    record["instance_url"] = provision["frontend_url"]
                _store.save(record)
        except Exception as exc:  # noqa: BLE001 -- signup must be resilient
            record["status"] = "provisioning"
            _store.save(record)
            warnings.append(f"Instance is still provisioning ({exc}).")

    instance_url = record.get("instance_url") or f"https://{slug}.{base_domain}"

    return {
        "ok": True,
        "dealer_id": record["dealer_id"],
        "slug": slug,
        "instance_url": instance_url,
        "plan_tier": FOUNDATION_TIER,
        "seat_count": FREE_SEAT_CAP,
        "suggested_modules": record["suggested_modules"],
        "industry_type": bt["industry_type"],
        "business_type": business_type,
        "status": record["status"],
        "warnings": warnings,
        "provision": provision,
    }


def suggest_modules(business_type):
    """The industry-package Modules to pre-suggest for a business type (Step 3 of the wizard)."""
    bt = BUSINESS_TYPES.get((business_type or "").strip().lower())
    return list(bt["suggested_modules"]) if bt else []


def list_business_types():
    """For the marketing 'What kind of business are you?' selector."""
    return [{"key": k, "label": v["label"], "suggested_modules": v["suggested_modules"]}
            for k, v in BUSINESS_TYPES.items()]
