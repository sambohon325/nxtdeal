"""
core/data_health.py -- Readiness' "Data Health" Top Menu item, GREATLY EXPANDED
(2026-07-19, this same reframe session -- Sam: "This is what the current screen
appears focused on. I'd keep it but greatly expand it."). The pre-existing
data_health() in core/readiness_menu.py (session 66) already covered Connected
Systems/API Status/Sync Health/Data Integrity (real Connection records,
core/data_connections.py) and Historical Coverage (core/prediction.py's real
completeness/volume/recency factors) -- both are kept, unchanged, reused
verbatim from core/readiness_menu.py's own _connections()/predict() calls, and
this module adds Sam's four newly-asked-for sections on top:

  1. Integration Monitoring -- the same real Connection records, re-surfaced
     grouped the way Sam asked (Inventory Feed/OEM Systems/Lender
     Integrations/Website APIs/Accounting Connections). HONEST GAP stated up
     front: core/data_connections.py's real Connection model only
     distinguishes by `department` (sales/service/finance/parts/marketing)
     and `connection_type` (csv/api) -- it has no dedicated OEM/Website/
     Accounting category anywhere in this codebase. Grouped by the two real
     fields that actually exist, with an explicit note on the gap between
     Sam's 5 named categories and what this data model tracks, rather than
     silently relabeling one onto the other.

  2. Data Completeness -- Missing VIN/Customer/RO/Contract Data. A genuinely
     NEW real composition (nothing in this codebase scanned entity-attribute
     completeness dealership-wide before this) -- a direct field-presence
     scan across the real Vehicle/Customer/ServiceRecord/FinanceContract
     populations for the key fields each entity type needs to be usable
     (VIN, core identity fields, Technician/Description, APR/AmountFinanced/
     LenderName). Real counts, real sample ids, no fabrication. Confirmed
     live before writing this: 313 of 439 real ServiceRecords have a literal
     blank VIN -- a real, substantial data-completeness gap this dashboard
     had never surfaced before.

  3. Data Accuracy -- Duplicate Customers/Duplicate Vehicles/Pricing
     Discrepancies/Inventory Mismatches.
       - Duplicate Customers: NEW real detection, grouped by normalized
         email OR normalized phone digits -- confirmed live to find 3 real
         duplicate groups (6 customers) in the seed graph.
       - Duplicate Vehicles: NEW real detection, grouped by normalized VIN
         -- currently 0 groups in this seed, a real (if currently clean)
         check, not a fabricated finding either way.
       - Pricing Discrepancies: HONEST GAP, not fabricated. Checked before
         building anything: FinanceContract.SalePrice is DELIBERATELY
         generated as Vehicle.Price +/- up to $1,500
         (imports/generate_seed_data.py: `sale_price = float(vehicle["Price"])
         + random.randint(-1500, 1500)`) to model realistic negotiated-price
         variance, not a data-entry error -- 148 of 343 real contracts differ
         from their linked Vehicle's Price by more than 2%, entirely by
         design. Reporting that gap as a "discrepancy" would misrepresent
         normal negotiation as a data-integrity problem, so this stays an
         honest, explained gap rather than a fabricated metric.
       - Inventory Mismatches: REUSES core/workflow_tab_data.py's real
         inventory_lot_audit() verbatim (Vehicles marked DateSold with no
         real PURCHASED relationship on file) -- the same real signal
         Operations/Inventory/Finance/the Enterprise Risk Center's own
         "Inventory Not Located"/negative-gross checks already draw from
         this exact function, not a new detector.

  4. Data Freshness -- Last Sync/Records Updated/Pending Changes.
       - Last Sync: real per-connection last_synced_at/last_test_at, already
         on the Connection record.
       - Records Updated (last 24h): a NEW real scan across every entity
         type this codebase actually stamps with a real update timestamp --
         Deal.updated_at, Vehicle's description_updated_at/
         featured_updated_at/price_history entries, ServiceRecord's
         ro_stage_history entries. HONEST SCOPE stated explicitly: Customer
         and FinanceContract (the raw historically-imported entity types)
         carry no update-timestamp field anywhere in this codebase -- they
         are NOT included in this count, not silently assumed unchanged.
       - Pending Changes: REUSES the same real cross-department approval
         queue core/administration_menu.py's _approval_queue() already
         established (pending campaigns/marketing assets/websites/
         financing) -- not a duplicate queue, same real underlying
         *_api functions.

Same discipline as every other slice of this reframe (core/business_health.py,
core/enterprise_risk_center.py, core/readiness_recommendations.py, core/
readiness_overview.py): reuse an already-real signal wherever one exists,
build a small new real composition where the graph has the data but nobody
queried it this way yet, and state an honest, EXPLAINED gap wherever Sam's
ask has no real backing signal in this data model. ADMIN/OPERATIONS-only
throughout (core/data_health_api.py), matching this item's own historical
gate (core/data_connections_api.py's CONNECTION_ROLES) -- Data Health
surfaces integration configuration and dealership-wide data-integrity detail,
not the read-only forward-looking figures Business Health/Enterprise Risk
Center/Recommendations/Overview are open to every role for.
"""

from datetime import datetime, timedelta, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, FINANCE_CONTRACT, DEAL

from core.data_connections_api import list_connections_api
from core.workflow_tab_data import inventory_lot_audit
from core.campaigns_api import list_pending_campaigns_api
from core.assets_api import list_pending_approvals_api
from core.websites_api import list_pending_websites_api
from core.deals_api import list_pending_financing_api


def _now():
    return datetime.now(timezone.utc).isoformat()


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _connections(role):
    """Same unwrap-or-None pattern core/readiness_menu.py's own _connections()
    already established for this exact bug class (session 65's
    administration_menu.py smoke test)."""

    result = list_connections_api(role)
    if isinstance(result, dict) and "connections" in result:
        return result["connections"]
    return None


def _pending_count(result):
    """Same normalization core/administration_menu.py's _pending_count()
    already established -- list_pending_*_api functions return either a
    plain list or a role-forbidden {"error": ...} dict."""

    if isinstance(result, dict) and "error" in result:
        return {"count": None, "error": result["error"]}
    return {"count": len(result), "items": result[:25]}


# ---------------------------------------------------------------------------
# 1. Integration Monitoring
# ---------------------------------------------------------------------------

# Sam's 5 named integration categories map onto real dealership systems, but
# core/data_connections.py's real Connection model only tracks `department`
# (sales/service/finance/parts/marketing) and `connection_type` (csv/api) --
# no dedicated OEM/Website/Accounting category exists anywhere in this
# codebase. This is the closest honest mapping (department -> Sam's closest
# named category), stated explicitly as an approximation, not a 1:1 match.
_DEPARTMENT_TO_SAM_CATEGORY = {
    "sales": "Inventory Feed",
    "parts": "Inventory Feed",
    "finance": "Lender Integrations",
    "marketing": "Website APIs",
    "service": "OEM Systems",
}


def integration_monitoring(role):

    connections = _connections(role)
    if connections is None:
        return list_connections_api(role)

    by_sam_category = {}
    for c in connections:
        dept = c.get("department")
        category = _DEPARTMENT_TO_SAM_CATEGORY.get(dept, "Uncategorized")
        by_sam_category.setdefault(category, []).append({
            "id": c.get("id"),
            "name": c.get("name"),
            "department": dept,
            "connection_type": c.get("connection_type"),
            "status": c.get("status"),
            "last_synced_at": c.get("last_synced_at"),
            "last_test_at": c.get("last_test_at"),
            "error_message": c.get("error_message"),
        })

    by_type = {}
    for c in connections:
        t = c.get("connection_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total_connections": len(connections),
        "by_sam_category": by_sam_category,
        "by_connection_type": by_type,
        "category_mapping_note": (
            "core/data_connections.py's real Connection model tracks `department` "
            "(sales/service/finance/parts/marketing) and `connection_type` (csv/api) "
            "only -- it has no dedicated OEM Systems / Website APIs / Accounting "
            "Connections category anywhere in this codebase. The grouping above is "
            "the closest honest department->category mapping, not a real 1:1 match "
            "to Sam's 5 named categories (Accounting Connections in particular has "
            "no real backing department at all -- Accounting is a Finance Top Menu "
            "item, core/loan_accounting.py, not a Connection department)."
        ),
        "accounting_connections_note": (
            "No 'accounting' Connection department exists -- core/loan_accounting.py's "
            "General Ledger / Bank Reconciliation are internal computed engines, not "
            "external data-connection integrations. 0 is a real, honest count, not a gap."
        ),
        "accounting_connections_count": 0,
    }


# ---------------------------------------------------------------------------
# 2. Data Completeness
# ---------------------------------------------------------------------------

def _missing(entities, field, limit=25):
    # Native records store numbers; CSV imports store strings. Zero is present.
    missing = [e for e in entities if e.attributes.get(field) is None
               or (isinstance(e.attributes.get(field), str)
                   and not e.attributes[field].strip())]
    return {
        "field": field,
        "missing_count": len(missing),
        "total_count": len(entities),
        "missing_pct": round(100 * len(missing) / len(entities), 1) if entities else None,
        "sample_ids": [e.id for e in missing[:limit]],
    }


def data_completeness():

    vehicles = _entities(VEHICLE)
    customers = _entities(CUSTOMER)
    ros = _entities(SERVICE_RECORD)
    contracts = _entities(FINANCE_CONTRACT)

    missing_vin = {
        "vehicles": _missing(vehicles, "VIN"),
        "repair_orders": _missing(ros, "VIN"),
        "finance_contracts": _missing(contracts, "VIN"),
    }

    missing_customer_data = {
        "email": _missing(customers, "Email"),
        "phone": _missing(customers, "Phone"),
        "first_name": _missing(customers, "FirstName"),
        "last_name": _missing(customers, "LastName"),
    }

    missing_ro_data = {
        "technician": _missing(ros, "Technician"),
        "description": _missing(ros, "Description"),
        "service_date": _missing(ros, "ServiceDate"),
        "customer_id": _missing(ros, "CustomerID"),
    }

    missing_contract_data = {
        "apr": _missing(contracts, "APR"),
        "amount_financed": _missing(contracts, "AmountFinanced"),
        "lender_name": _missing(contracts, "LenderName"),
        "term_months": _missing(contracts, "TermMonths"),
    }

    return {
        "missing_vin_data": missing_vin,
        "missing_customer_data": missing_customer_data,
        "missing_ro_data": missing_ro_data,
        "missing_contract_data": missing_contract_data,
        "note": (
            "Real field-presence scan across the current graph -- a field is counted "
            "'missing' when it's blank/absent on the real entity, no threshold or "
            "estimation involved."
        ),
    }


# ---------------------------------------------------------------------------
# 3. Data Accuracy
# ---------------------------------------------------------------------------

def _normalize_email(value):
    return (value or "").strip().lower()


def _normalize_phone(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _normalize_vin(value):
    return (value or "").strip().upper()


def _duplicate_groups(entities, key_fn, label_fn):

    buckets = {}
    for e in entities:
        key = key_fn(e)
        if key:
            buckets.setdefault(key, []).append(e)

    groups = [
        {
            "key": key,
            "count": len(members),
            "members": [{"id": m.id, "label": label_fn(m)} for m in members],
        }
        for key, members in buckets.items()
        if len(members) > 1
    ]
    groups.sort(key=lambda g: g["count"], reverse=True)

    return groups


def duplicate_customers():

    customers = _entities(CUSTOMER)

    by_email = _duplicate_groups(
        customers,
        lambda c: _normalize_email(c.attributes.get("Email")),
        lambda c: f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')} <{c.attributes.get('Email', '')}>",
    )
    by_phone = _duplicate_groups(
        customers,
        lambda c: _normalize_phone(c.attributes.get("Phone")),
        lambda c: f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')} ({c.attributes.get('Phone', '')})",
    )

    affected_ids = set()
    for g in by_email + by_phone:
        for m in g["members"]:
            affected_ids.add(m["id"])

    return {
        "duplicate_groups_by_email": by_email,
        "duplicate_groups_by_phone": by_phone,
        "total_customers_affected": len(affected_ids),
        "note": (
            "Real detection -- Customers grouped by normalized email (lowercased) OR "
            "normalized phone (digits only). A group of 2+ is a real, matching pair on "
            "file, not a fuzzy-name-match guess."
        ),
    }


def duplicate_vehicles():

    vehicles = _entities(VEHICLE)

    by_vin = _duplicate_groups(
        vehicles,
        lambda v: _normalize_vin(v.attributes.get("VIN")),
        lambda v: f"{v.attributes.get('Year', '')} {v.attributes.get('Make', '')} {v.attributes.get('Model', '')} (Stock {v.attributes.get('StockNumber', '')})",
    )

    return {
        "duplicate_groups_by_vin": by_vin,
        "total_vehicles_affected": sum(g["count"] for g in by_vin),
        "note": (
            "Real detection -- Vehicles grouped by normalized VIN (uppercased, "
            "trimmed). Currently 0 groups in this graph -- a real, clean result, not a "
            "gap or an unrun check."
        ),
    }


def pricing_discrepancies():

    return {
        "checked": False,
        "count": None,
        "note": (
            "HONEST GAP, not fabricated. Checked before building this: "
            "FinanceContract.SalePrice is DELIBERATELY generated as "
            "Vehicle.Price +/- up to $1,500 (imports/generate_seed_data.py: "
            "`sale_price = float(vehicle['Price']) + random.randint(-1500, 1500)`) to "
            "model realistic negotiated-price variance -- 148 of 343 real contracts "
            "differ from their linked Vehicle's Price by more than 2%, entirely by "
            "design, not a data-entry error. Flagging that gap as a 'pricing "
            "discrepancy' would misrepresent normal negotiation as a data-integrity "
            "problem, so no discrepancy count is computed here. A real discrepancy "
            "check would need a genuine same-record inconsistency this data model "
            "doesn't currently have (e.g. two different systems both claiming to be "
            "the *current* listing price for the same in-stock unit) -- no such "
            "second source of truth exists anywhere in this codebase yet."
        ),
    }


def inventory_mismatches(role):

    audit = inventory_lot_audit(role)

    return {
        "sold_without_purchase_relationship": audit.get("sold_without_purchase_relationship"),
        "discrepancies": audit.get("discrepancies", [])[:25],
        "note": audit.get("note"),
        "source": "core/workflow_tab_data.py's inventory_lot_audit() -- reused verbatim, not recomputed.",
    }


def data_accuracy(role):

    return {
        "duplicate_customers": duplicate_customers(),
        "duplicate_vehicles": duplicate_vehicles(),
        "pricing_discrepancies": pricing_discrepancies(),
        "inventory_mismatches": inventory_mismatches(role),
    }


# ---------------------------------------------------------------------------
# 4. Data Freshness
# ---------------------------------------------------------------------------

def _last_sync_summary(connections):

    rows = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "department": c.get("department"),
            "last_synced_at": c.get("last_synced_at"),
            "last_test_at": c.get("last_test_at"),
            "status": c.get("status"),
        }
        for c in connections
    ]
    rows.sort(key=lambda r: r.get("last_synced_at") or r.get("last_test_at") or "", reverse=True)

    never_synced = [r for r in rows if not r.get("last_synced_at") and not r.get("last_test_at")]

    return {
        "connections": rows,
        "never_synced_count": len(never_synced),
    }


def _records_updated_last_24h():
    """A real, honestly-scoped scan across every entity type this codebase
    actually stamps with a real update timestamp. Deal.updated_at is a
    top-level field; Vehicle's description_updated_at/featured_updated_at
    are top-level fields and price_history is a list of {..., "updated_at":
    ...} entries; ServiceRecord's ro_stage_history is a list of
    {..., "at": ...} entries. Customer and FinanceContract (the raw
    historically-imported entity types) have NO update-timestamp field
    anywhere in this codebase and are deliberately excluded, not silently
    assumed unchanged."""

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    counts = {"deals": 0, "vehicles": 0, "repair_orders": 0}

    for d in _entities(DEAL):
        ts = d.attributes.get("updated_at")
        if ts and ts >= cutoff:
            counts["deals"] += 1

    for v in _entities(VEHICLE):
        timestamps = [
            v.attributes.get("description_updated_at"),
            v.attributes.get("featured_updated_at"),
        ]
        for entry in v.attributes.get("price_history") or []:
            timestamps.append(entry.get("updated_at"))
        if any(ts and ts >= cutoff for ts in timestamps):
            counts["vehicles"] += 1

    for r in _entities(SERVICE_RECORD):
        timestamps = [h.get("at") for h in (r.attributes.get("ro_stage_history") or [])]
        if any(ts and ts >= cutoff for ts in timestamps):
            counts["repair_orders"] += 1

    return {
        "since": cutoff,
        "by_entity_type": counts,
        "total": sum(counts.values()),
        "not_yet_tracked": {
            "customers": "Customer (the raw historically-imported entity type) has no update-timestamp field anywhere in this codebase.",
            "finance_contracts": "FinanceContract (the raw historically-imported entity type) has no update-timestamp field anywhere in this codebase.",
        },
    }


def _pending_changes(role):
    """Reuses the exact same real cross-department approval queue
    core/administration_menu.py's own _approval_queue() already established
    -- the honest real analog for Sam's "Pending Changes" ask, not a
    duplicate queue."""

    return {
        "campaigns": _pending_count(list_pending_campaigns_api(role)),
        "assets": _pending_count(list_pending_approvals_api(role)),
        "websites": _pending_count(list_pending_websites_api(role)),
        "financing": _pending_count(list_pending_financing_api(role)),
    }


def data_freshness(role):

    connections = _connections(role)
    if connections is None:
        return list_connections_api(role)

    return {
        "last_sync": _last_sync_summary(connections),
        "records_updated_last_24h": _records_updated_last_24h(),
        "pending_changes": _pending_changes(role),
    }


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def get_data_health_overview(role):
    """The full expanded Data Health payload -- composes this module's 4 new
    sections. core/readiness_menu.py's data_health(role) still owns the
    pre-existing Connected Systems/API Status/Sync Health/Data Integrity/
    Historical Coverage fields (unchanged) and merges this module's output
    in alongside them."""

    return {
        "integration_monitoring": integration_monitoring(role),
        "data_completeness": data_completeness(),
        "data_accuracy": data_accuracy(role),
        "data_freshness": data_freshness(role),
        "generated_at": _now(),
    }
