"""
core/onboarding_signals.py -- tenant-side onboarding auto-detection (Freemium Platform roadmap,
Phase 2, 2026-08-03).

The roadmap's Phase 2 replaces the Hub's manual 7-step Setup Wizard (Dealer Created, Users Invited,
Inventory Imported, CRM Imported, Website Connected, Network Connected, Go Live) with an automated
flow: each step needs "a genuine tenant-side signal, an authenticated event the product itself
fires, rather than staff manually marking a checkbox." Dealer Created and Network Connected already
have real signals; the middle steps -- especially Inventory Imported and CRM Imported, the two most
central to the free tier -- were honest manual staff entry.

This module computes those signals from the dealer's OWN data, with zero credentials and zero Hub
dependency: it just reads the ledger the running product already maintains. The Hub reads the result
through a network-key-gated snapshot (mirroring GET /network/*-snapshot) and stops guessing; the
product can also read it in-app to drive its own onboarding checklist.

Every step reports `basis: "auto"` (a real, recomputed signal) -- never a staff checkbox. "Go Live"
is a composite: the dealer is live once the real setup steps are satisfied.
"""

from core.dealeros import ledger
from core.entity_types import EMPLOYEE, VEHICLE, CUSTOMER, LEAD


def _count(entity_type):
    return sum(1 for e in ledger.get_all().values() if e.entity_type == entity_type)


def _dealer_created():
    """A configured dealer identity = the SystemConfig singleton has a dealership name."""
    from core import system_config
    cfg = system_config.get_system_config()
    name = (cfg.get("dealership_name") or "").strip()
    return bool(name), {"dealership_name": name or None}


def _published_website_count():
    from core import websites
    try:
        published = websites.list_websites(status="published")
    except Exception:
        published = []
    return len(published) if isinstance(published, list) else 0


def compute_onboarding_signals():
    """The 7 setup steps, each auto-detected from real tenant data. Returns an ordered list plus a
    progress percentage and a go_live flag."""
    created, created_detail = _dealer_created()

    employee_count = _count(EMPLOYEE)
    vehicle_count = _count(VEHICLE)
    customer_count = _count(CUSTOMER)
    lead_count = _count(LEAD)
    crm_records = customer_count + lead_count
    website_count = _published_website_count()

    steps = [
        {
            "key": "dealer_created",
            "name": "Dealer Created",
            "complete": created,
            "basis": "auto",
            "signal": "SystemConfig has a dealership name",
            "detail": created_detail,
        },
        {
            "key": "users_invited",
            "name": "Users Invited",
            # More than the single owner account = a real invite happened.
            "complete": employee_count >= 2,
            "basis": "auto",
            "signal": "employee count >= 2",
            "detail": {"employee_count": employee_count},
        },
        {
            "key": "inventory_imported",
            "name": "Inventory Imported",
            "complete": vehicle_count > 0,
            "basis": "auto",
            "signal": "vehicle count > 0",
            "detail": {"vehicle_count": vehicle_count},
        },
        {
            "key": "crm_imported",
            "name": "CRM Imported",
            "complete": crm_records > 0,
            "basis": "auto",
            "signal": "customer + lead count > 0",
            "detail": {"customer_count": customer_count, "lead_count": lead_count},
        },
        {
            "key": "website_connected",
            "name": "Website Connected",
            "complete": website_count > 0,
            "basis": "auto",
            "signal": "at least one published website",
            "detail": {"published_website_count": website_count},
        },
        {
            "key": "network_connected",
            "name": "Network Connected",
            # The tenant exposes the network snapshot endpoints the Hub calls; whether the Hub has
            # actually reached them is a Hub-side fact. Tenant-side this is "network-ready".
            "complete": True,
            "basis": "auto",
            "signal": "network snapshot endpoints are served",
            "detail": {"network_ready": True},
        },
    ]

    # Go Live = every real setup step above is satisfied (network_connected is always ready, so the
    # binding steps are the five real-data ones).
    go_live = all(s["complete"] for s in steps)
    steps.append({
        "key": "go_live",
        "name": "Go Live",
        "complete": go_live,
        "basis": "auto",
        "signal": "all setup steps complete",
        "detail": None,
    })

    completed = sum(1 for s in steps if s["complete"])
    return {
        "steps": steps,
        "completed_steps": completed,
        "total_steps": len(steps),
        "progress_pct": round(100 * completed / len(steps)),
        "go_live": go_live,
    }


def build_onboarding_signals_snapshot():
    """Dealer-identified snapshot for the Hub's onboarding view -- the real, auto-detected state
    that replaces manual staff checkboxes. Same shape the in-product checklist reads."""
    return compute_onboarding_signals()
