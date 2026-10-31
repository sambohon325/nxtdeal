"""
Third-party data enrichment -- Phase 1 (2026-07-25). CDK's Built-In CDP layers third-party
household/vehicle-ownership data on top of a dealer's own records; automotiveMastermind
enriches to sharpen its propensity model. This module is NXTDeal's enrichment hook: it
routes a customer record through the provider seam (integrations_registry.enrich_record)
and stores whatever a real provider appends back onto the customer.

Honest by construction: with no enrichment provider connected the seam appends nothing, so
enrich_customer records an "enrichment ran, no provider" result rather than inventing data.
The day an enrichment/CDP provider is registered (Administration -> Connections), the same
call appends real third-party attributes, which then feed buy-propensity scoring.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import integrations_registry


def _now():
    return datetime.now(timezone.utc).isoformat()


def _record_from_customer(customer):
    a = customer.attributes
    return {
        "customer_id": customer.id,
        "first_name": a.get("FirstName"),
        "last_name": a.get("LastName"),
        "email": a.get("Email") or a.get("email"),
        "phone": a.get("Phone") or a.get("phone"),
        "city": a.get("City"),
        "state": a.get("State"),
    }


def enrich_customer(customer_id):
    """Run one customer record through the enrichment seam and persist the result. Returns
    the dispatch result (simulated + empty when no provider is connected)."""
    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        return {"error": "Customer not found"}

    result = integrations_registry.enrich_record(_record_from_customer(customer))
    appended = result.get("appended") or {}

    customer.attributes["enrichment"] = {
        "provider": result.get("provider"),
        "simulated": bool(result.get("simulated")),
        "appended": appended,
        "appended_count": len(appended),
        "enriched_at": _now(),
    }
    # Only merge appended fields the provider actually returned -- never fabricated.
    for k, v in appended.items():
        customer.attributes.setdefault(f"enriched_{k}", v)

    save_graph(GRAPH_PATH)
    return {
        "customer_id": customer_id,
        "provider": result.get("provider"),
        "mode": "live" if not result.get("simulated") else "simulated",
        "appended_count": len(appended),
        "appended": appended,
        "note": result.get("note"),
    }


def enrich_batch(customer_ids):
    return [enrich_customer(cid) for cid in (customer_ids or [])]


def get_enrichment(customer_id):
    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        return {"error": "Customer not found"}
    return customer.attributes.get("enrichment") or {
        "provider": None, "simulated": True, "appended": {}, "appended_count": 0, "enriched_at": None,
    }
