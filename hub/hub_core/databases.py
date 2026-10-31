"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 2 of 4:
Databases.

Sam's spec: "DATABASES -- critical. Track: Primary/Replica/Analytics/
Warehouse/AI Data Stores. Show: Load/Replication/Storage/Health."

Real vs. honest-gap, checked before writing anything: this codebase's real
"database" is a single JSON file per tenant (graph.json), loaded fully into
memory at process start and persisted back on save (see CLAUDE.md's "Data
Architecture" section) -- there is no separate Replica, Analytics Warehouse,
or AI Data/Vector Store anywhere in this codebase. Rather than fabricate a
five-tier picture that doesn't exist, this module reports:

  - Primary -- REAL. The tenant's one real graph.json: size, real entity/
    relationship counts, last-modified time (backend/core/storage_snapshot.py,
    fetched live via hub/hub_core/tenant_storage_metrics.py). "Load" is real in
    the loosest honest sense (entity/relationship COUNT, a real proxy for
    how much data this store holds) -- there is no query-throughput/QPS
    metric anywhere in this codebase to report a literal "load" figure, so
    that's stated as a gap rather than guessed at.
  - Replica -- HONEST GAP. No replication of any kind exists -- one file,
    one process, no read replica.
  - Analytics -- HONEST GAP. hub_core/kpi_snapshots.py/hub_core/department_
    intelligence.py compute real KPI aggregates, but they read the SAME
    graph.json in-process -- there is no separate analytics data store.
  - Warehouse -- HONEST GAP. No ETL pipeline or separate warehouse exists.
  - AI Data Stores -- HONEST GAP. No vector database or embeddings store
    exists anywhere in this codebase (confirmed via grep) -- every AI
    feature (hub_core/ai_management.py's 13-feature catalog) calls OpenAI
    directly with data assembled fresh from the graph, never a persisted
    embedding index.

"Health" for the one real store that exists is derived from the same real
reachability the rest of this Infrastructure section already uses --
reachable + a successful read = healthy, unreachable = down, never checked
= unknown.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.tenant_storage_metrics import registry as storage_registry, get_dealer_storage, recheck_dealer_storage


_STORE_TIERS = ["primary", "replica", "analytics", "warehouse", "ai_data_stores"]

_HONEST_GAP_NOTES = {
    "replica": "No replication of any kind exists -- one graph.json file, one in-memory ledger, one process per tenant.",
    "analytics": "No separate analytics data store exists -- real KPI aggregates (hub_core/department_intelligence.py, hub_core/kpi_snapshots.py) read the SAME graph.json in-process, not a second store.",
    "warehouse": "No ETL pipeline or separate data warehouse exists anywhere in this codebase.",
    "ai_data_stores": "No vector database or embeddings store exists anywhere in this codebase -- every AI feature calls OpenAI directly with data assembled fresh from the graph, never a persisted embedding index.",
}


def _primary_store_entry(dealer):

    snapshot = storage_registry.get(dealer.dealer_id)

    if snapshot is None:
        return {
            "tier": "primary",
            "label": "Primary Data Store (graph.json)",
            "health": "not_checked",
            "basis": None,
            "load": None,
            "storage": None,
            "note": "Never checked -- click Recheck to fetch this tenant's real storage figures.",
        }

    if not snapshot.reachable or not snapshot.data.get("graph_json"):
        return {
            "tier": "primary",
            "label": "Primary Data Store (graph.json)",
            "health": "down",
            "basis": snapshot.basis,
            "load": None,
            "storage": None,
            "note": snapshot.error or "Last check was unable to read this tenant's real storage figures.",
        }

    graph = snapshot.data.get("graph_json", {})

    return {
        "tier": "primary",
        "label": "Primary Data Store (graph.json)",
        "health": "healthy",
        "basis": snapshot.basis,
        "load": {
            "entity_count": graph.get("entity_count"),
            "relationship_count": graph.get("relationship_count"),
            "note": (
                "'Load' here is a real proxy (how much data this store "
                "holds), not a query-throughput/QPS figure -- no such "
                "metric exists anywhere in this codebase."
            ),
        },
        "storage": {
            "size_bytes": graph.get("size_bytes"),
            "last_modified_at": graph.get("last_modified_at"),
        },
        "fetched_at": snapshot.fetched_at,
        "dev_note": snapshot.data.get("_dev_note"),
        "note": None,
    }


def get_databases_overview():

    dealers = dealer_registry.list_all()

    per_dealer = []
    for dealer in dealers:
        primary = _primary_store_entry(dealer)
        per_dealer.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "tiers": [primary] + [
                {
                    "tier": tier,
                    "label": tier.replace("_", " ").title(),
                    "health": "not_applicable",
                    "note": _HONEST_GAP_NOTES[tier],
                }
                for tier in _STORE_TIERS if tier != "primary"
            ],
        })

    checked_count = len([d for d in dealers if storage_registry.get(d.dealer_id) is not None])
    healthy_count = len([
        d for d in dealers
        if storage_registry.get(d.dealer_id) and storage_registry.get(d.dealer_id).reachable
    ])

    return {
        "dealers": per_dealer,
        "summary": {
            "total_dealers": len(dealers),
            "checked": checked_count,
            "healthy_primary_stores": healthy_count,
        },
        "tier_catalog": [
            {"tier": t, "label": t.replace("_", " ").title()} for t in _STORE_TIERS
        ],
        "note": (
            "This tenant's real 'database' is one JSON file per tenant "
            "(graph.json), loaded fully into memory at process start and "
            "persisted back on save -- there is no separate Replica, "
            "Analytics, Warehouse, or AI Data Store anywhere in this "
            "codebase. Every tier below the real Primary entry is an "
            "honest, stated gap, not a fabricated multi-tier database "
            "picture. Each dealer's Primary figures are LAST-KNOWN, not "
            "live -- use GET /hub/infra/databases/{dealer_id}/recheck for "
            "a fresh live pull."
        ),
    }


def get_dealer_databases(dealer_id):
    result, error = get_dealer_storage(dealer_id)
    if error:
        return None, error
    dealer = dealer_registry.get(dealer_id)
    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name if dealer else dealer_id,
        "primary": _primary_store_entry(dealer) if dealer else None,
        "raw_snapshot": result["snapshot"],
    }, None


def recheck_dealer_databases(dealer_id):
    snapshot, error = recheck_dealer_storage(dealer_id)
    if error:
        return None, error
    return get_dealer_databases(dealer_id)
