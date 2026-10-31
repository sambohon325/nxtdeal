"""
core/workflow_tab_data.py -- "wire it all up" (session 57).

Sam, on the session-56 multi-window rebuild: "k, lets wire it all up." That request
covers ~150 placeholder tabs / 72 "Core Functionality" widgets across
core/workflow_catalog.py's 36 workflows -- ranging from a trivial reuse of an existing
dashboard to genuinely new products (OFAC watchlist checks, biometric ID verification,
co-op ad-text scanning AI, IoT lot geofencing) that have no backend logic anywhere in
this codebase. Scoped by Sam's direct answer to a clarifying question: wire real data
wherever the graph already has it; leave anything needing a new integration/data model
as an honest placeholder rather than fake it.

One generic engine (matching this codebase's established one-catalog/one-engine
pattern -- core/bot_tasks.py's TASK_CATALOG, core/compliance_rules.py's RULES,
core/workflow_catalog.py itself), not 36 bespoke modules. Two kinds of real data:

  1. Linked-entity block -- if the caller passes a linked_entity_id (usually a live
     WorkflowInstance's own linked_entity_id), this reuses core/ai_tools.py's
     get_entity_by_id()/get_related_entities() verbatim -- the same already-built,
     already-role-filtered (core/security.py's can_access_entity()) functions backing
     the AI assistant's graph tools. No new entity-access logic; genuinely just reuse.
  2. REAL_SOURCES -- a workflow_key -> [source] map. Each source wraps one already-
     existing, already-built function (a dashboard, compliance alerts, network
     benchmark/audit, connections list, readiness predictions, audit log, a pending-
     approval queue) that is a genuine substantive match for what that workflow's tabs
     describe -- not a stretch mapping.

Session 59 (Sam: "lets go ahead and populate that data with demo data") closed the
remaining gap: 13 workflow keys had nothing real to fall back on (no REAL_SOURCES entry
and no useful linked-entity data), because either nothing in the graph modeled the
underlying concept at all (reviews, auction/transport tracking, OEM recalls -- fixed by
seeding 3 new entity types via imports/seed_demo_extras.py) or the real data existed but
needed a genuine aggregate query nobody had written yet (Deal-status filters for the
desking/F&I/delivery stages, Vehicle/FinanceContract/ServiceRecord aggregates). Every
one of those new sources is computed directly from real (if in a few cases seeded-
synthetic, like the auction/review/recall data) entities already in the graph --
several are explicitly labeled as heuristics in their own `note` field where the
computation is a real but simplified proxy (e.g. "equity mining" candidates estimated
from contract term progress, since there's no live amortization engine here). This same
pass also fixed three workflow keys (operations.recon, operations.inventory_
reconciliation, inventory.aging_pricing) that session 57 had wired to
get_velocity_dashboard() -- that function is LEAD pipeline state velocity, not vehicle
inventory data, a real mismap now replaced with genuine Vehicle-based aggregates.

Only marketing.reputation's underlying Customer entity_type, service.intake/mpi/
warranty_claims' ServiceRecord entity_type, sales.desking/fi_turnover/delivery's Deal
entity_type, inventory.*'s Vehicle entity_type, and finance.floorplan_payoff's Vehicle
entity_type get the linked-entity block; the REAL_SOURCES entries added this session are
additive department/workflow-level aggregates on top of that, not a replacement for it.

Every source function here is either already self-gating (takes `role`, returns its own
{"error": ...} exactly like the existing route that already calls it) or is gated in
this module the exact same way its existing route gates it (ADMIN/OPERATIONS-only for
the two raw audit_api functions and administration.onboarding's roster/credential
summary, both of which take no role param; can_access_dashboard() for the no-role-param
dashboard functions). The session-59 aggregate queries over Vehicle/Deal/FinanceContract/
ServiceRecord/Review/AuctionTransaction/Recall data are left open to any authenticated
role, matching readiness_predictions_api()'s precedent -- none of it is
compensation-adjacent or PII-sensitive in the way core/employee_value.py's data is.
Nothing here creates a new store, bypasses a role check, or invents data the graph
doesn't have.
"""

from core.workflow_catalog import get_workflow_def
from core.ai_tools import get_entity_by_id, get_related_entities
from core.permissions import ADMIN, OPERATIONS
from core.security import can_access_dashboard

from core.audit_api import list_audit_events, get_audit_dashboard
from core.data_connections_api import list_connections_api, readiness_predictions_api
from core.network_api import get_network_benchmarks_api, get_network_audit_api
from core.compliance_api import list_alerts_api
from core.campaigns_api import list_pending_campaigns_api
from core.websites_api import list_pending_websites_api
from core.deals_api import list_pending_financing_api
from core.up_system_api import get_rotation_api
from core.bdc_api import get_bdc_dashboard_api
from core.demo_drive_api import get_demo_drive_dashboard_api
from core.credit_app_api import get_credit_app_dashboard_api
from core.esignature_api import get_esignature_dashboard_api
from core.fi_products_api import get_fi_products_dashboard_api
from core.lost_sale_recovery_api import get_lost_sale_recovery_dashboard_api
from core.orphan_owner_mining_api import get_orphan_owner_dashboard_api

from core.queries import (
    get_sales_dashboard,
    get_service_dashboard,
    get_finance_dashboard,
)
from core.velocity_dashboard import get_velocity_dashboard
from core.workflow_dashboard import get_lead_pipeline_dashboard
from core.follow_up_dashboard import get_follow_up_dashboard
from core.workload_dashboard_api import get_dashboard as get_workload_dashboard_api
from core.escalation_dashboard_api import get_dashboard as get_escalation_dashboard_api

# Session 59 additions -- direct graph access for the new aggregate queries below.
from datetime import datetime, timezone
from core.dealeros import ledger
from core.entity_types import (
    VEHICLE,
    DEAL,
    FINANCE_CONTRACT,
    SERVICE_RECORD,
    EMPLOYEE,
    REVIEW,
    AUCTION_TRANSACTION,
    RECALL,
    CUSTOMER,
)
from core.relationship_types import PURCHASED
from core.auth import credential_store


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _vehicles():
    return _entities(VEHICLE)


def _unsold_vehicles():
    return [v for v in _vehicles() if not v.attributes.get("DateSold")]


def _deals_by_status(*statuses):
    return [d for d in _entities(DEAL) if d.attributes.get("status") in statuses]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sales_desking_pipeline(role):
    """sales.desking's real source: Deals currently in the 'desking' stage -- scenario
    comparison not yet resolved to a selected financing path."""

    deals = _deals_by_status("desking")

    return {
        "count": len(deals),
        "deals": [
            {
                "id": d.id,
                "customer_id": d.attributes.get("customer_id"),
                "vehicle_id": d.attributes.get("vehicle_id"),
                "scenario_count": len(d.attributes.get("scenarios") or []),
                "selected_scenario_id": d.attributes.get("selected_scenario_id"),
                "created_by": d.attributes.get("created_by"),
                "created_at": d.attributes.get("created_at"),
            }
            for d in deals
        ],
    }


def sales_fi_turnover_queue(role):
    """sales.fi_turnover's real source: Deals that have moved past desking into
    financing but haven't reached a contract yet -- the actual F&I turnover queue."""

    deals = _deals_by_status("financing")

    return {
        "count": len(deals),
        "deals": [
            {
                "id": d.id,
                "customer_id": d.attributes.get("customer_id"),
                "vehicle_id": d.attributes.get("vehicle_id"),
                "financing_type": d.attributes.get("financing_type"),
                "lender_id": d.attributes.get("lender_id"),
                "financing_status": d.attributes.get("financing_status"),
            }
            for d in deals
        ],
    }


def sales_delivery_queue(role):
    """sales.delivery's real source: Deals with a signed contract or already funded --
    the delivery-ready queue (vehicle prep + paperwork handoff to the customer)."""

    deals = _deals_by_status("contract", "funded")

    return {
        "count": len(deals),
        "deals": [
            {
                "id": d.id,
                "customer_id": d.attributes.get("customer_id"),
                "vehicle_id": d.attributes.get("vehicle_id"),
                "status": d.attributes.get("status"),
                "finance_contract_id": d.attributes.get("finance_contract_id"),
                "funded_at": d.attributes.get("funded_at"),
            }
            for d in deals
        ],
    }


def _customer_id_by_raw_key():
    """FinanceContract.CustomerID (see marketing_database_mining() below) is the raw
    CSV import business key (e.g. "C4077"), not the resolved graph CUST- id -- the
    same "raw import key never resolved" bug class sessions 39/94 already found and
    fixed for ServiceRecord.Technician/Lead.AssignedSalesperson. Confirmed live
    2026-07-19: this was silently making core/trigger_alerts.py's
    _scan_equity_mining() (built directly on marketing_database_mining()'s candidate
    list) return zero real alerts -- every one of its ledger.get_entity(customer_id)
    lookups failed since customer_id was never a real entity id to begin with.
    core/smart_audiences.py's _customer_id_lookup_by_raw_key() already worked around
    this locally for its own Positive Equity smart-audience preset (session 113) via
    the one place the mapping IS available: every real Customer entity still has its
    own original CustomerID stored as a plain attribute. Fixed here at the actual
    source instead, so every consumer (this function's own candidates, and anything
    built on top of them) gets a real, resolved CUST- id without needing its own
    workaround."""

    return {c.attributes.get("CustomerID"): c.id for c in _entities(CUSTOMER) if c.attributes.get("CustomerID")}


def marketing_database_mining(role):
    """marketing.database_mining's real source: FinanceContract-based equity/renewal
    mining candidates. HEURISTIC -- there's no live amortization engine in this
    codebase, so 'likely equity position' is estimated from elapsed contract term as a
    percentage of the total term (a real, if simplified, proxy for principal paid
    down), not a real payoff-quote calculation."""

    contracts = _entities(FINANCE_CONTRACT)
    customer_lookup = _customer_id_by_raw_key()
    candidates = []

    for c in contracts:

        term = _safe_float(c.attributes.get("TermMonths"), 0)
        contract_date = c.attributes.get("ContractDate")

        if term <= 0 or not contract_date:
            continue

        try:
            start = datetime.fromisoformat(str(contract_date).replace("Z", "+00:00"))
        except ValueError:
            continue

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        months_elapsed = max(0.0, (datetime.now(timezone.utc) - start).days / 30.4)
        pct_elapsed = min(1.0, months_elapsed / term) if term else 0

        if pct_elapsed >= 0.5:
            raw_customer_id = c.attributes.get("CustomerID")
            candidates.append({
                "finance_contract_id": c.id,
                "customer_id": customer_lookup.get(raw_customer_id, raw_customer_id),
                "vin": c.attributes.get("VIN"),
                "lender_name": c.attributes.get("LenderName"),
                "term_months": term,
                "pct_term_elapsed": round(pct_elapsed, 2),
                "amount_financed": c.attributes.get("AmountFinanced"),
            })

    candidates.sort(key=lambda x: x["pct_term_elapsed"], reverse=True)

    return {
        "count": len(candidates),
        "candidates": candidates[:50],
        "note": (
            "HEURISTIC: 'likely equity/renewal candidate' is estimated from elapsed "
            "contract term as a % of total term, not a real amortization payoff quote. "
            "No live amortization engine exists in this codebase yet. 'customer_id' is "
            "resolved to the real graph CUST- id (fixed 2026-07-19 -- previously the raw "
            "CSV import key, which silently broke downstream consumers like "
            "core/trigger_alerts.py's equity-mining alerts)."
        ),
    }


def marketing_reputation_summary(role):
    """marketing.reputation's real source: seeded Review entities (see
    imports/seed_demo_extras.py) -- average rating per platform and the unresponded
    negative-review queue this workflow exists to clear."""

    reviews = _entities(REVIEW)

    by_platform = {}
    for r in reviews:
        platform = r.attributes.get("platform", "Unknown")
        by_platform.setdefault(platform, []).append(r.attributes.get("rating", 0))

    platform_summary = {
        platform: {
            "count": len(ratings),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        }
        for platform, ratings in by_platform.items()
    }

    unresponded_negative = [
        {
            "id": r.id,
            "platform": r.attributes.get("platform"),
            "rating": r.attributes.get("rating"),
            "author_name": r.attributes.get("author_name"),
            "text": r.attributes.get("text"),
            "review_date": r.attributes.get("review_date"),
        }
        for r in reviews
        if r.attributes.get("rating", 5) <= 3 and not r.attributes.get("responded")
    ]

    return {
        "total_reviews": len(reviews),
        "by_platform": platform_summary,
        "unresponded_negative_count": len(unresponded_negative),
        "unresponded_negative": unresponded_negative,
    }


def inventory_auction_acquisition(role):
    """inventory.auction_acquisition's real source: seeded AuctionTransaction entities
    -- in-transit/at-yard/delivered acquisition pipeline."""

    auctions = _entities(AUCTION_TRANSACTION)

    by_status = {}
    for a in auctions:
        status = a.attributes.get("transport_status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "count": len(auctions),
        "by_transport_status": by_status,
        "transactions": [
            {
                "id": a.id,
                "vehicle_id": a.attributes.get("vehicle_id"),
                "vin": a.attributes.get("vin"),
                "auction_house": a.attributes.get("auction_house"),
                "bid_amount": a.attributes.get("bid_amount"),
                "purchase_date": a.attributes.get("purchase_date"),
                "transport_status": a.attributes.get("transport_status"),
                "carrier": a.attributes.get("carrier"),
                "expected_arrival": a.attributes.get("expected_arrival"),
            }
            for a in sorted(auctions, key=lambda x: x.attributes.get("purchase_date") or "", reverse=True)
        ],
    }


def inventory_lot_audit(role):
    """inventory.lot_audit's real source: a genuine data-integrity check, not a fixture
    -- Vehicles marked sold (DateSold set) should carry a real PURCHASED relationship
    from a Customer; any that don't are flagged as a lot-audit discrepancy (either a
    data-entry gap or a vehicle that needs re-verification against the physical lot)."""

    vehicles = _vehicles()
    purchased_targets = {
        rel.target_id for rel in ledger.get_relationships()
        if rel.relationship_type == PURCHASED
    }

    discrepancies = [
        {
            "vehicle_id": v.id,
            "vin": v.attributes.get("VIN"),
            "stock_number": v.attributes.get("StockNumber"),
            "lot": v.attributes.get("Lot"),
            "date_sold": v.attributes.get("DateSold"),
        }
        for v in vehicles
        if v.attributes.get("DateSold") and v.id not in purchased_targets
    ]

    by_lot = {}
    for v in _unsold_vehicles():
        lot = v.attributes.get("Lot", "Unknown")
        by_lot[lot] = by_lot.get(lot, 0) + 1

    return {
        "total_vehicles": len(vehicles),
        "unsold_by_lot": by_lot,
        "sold_without_purchase_relationship": len(discrepancies),
        "discrepancies": discrepancies,
        "note": (
            "Discrepancy check: a Vehicle marked DateSold should always have a real "
            "PURCHASED relationship from the buying Customer -- any listed here is a "
            "genuine data-integrity gap, not a simulated finding."
        ),
    }


def inventory_wholesale_disposition(role):
    """inventory.wholesale_disposition's real source: unsold vehicles whose margin
    (Price - Cost) is thin or negative -- real candidates to wholesale out rather than
    continue retailing, ranked worst-margin-first."""

    candidates = []

    for v in _unsold_vehicles():

        price = _safe_float(v.attributes.get("Price"))
        cost = _safe_float(v.attributes.get("Cost"))
        margin = price - cost

        if price and margin / price < 0.08:
            candidates.append({
                "vehicle_id": v.id,
                "vin": v.attributes.get("VIN"),
                "stock_number": v.attributes.get("StockNumber"),
                "year": v.attributes.get("Year"),
                "make": v.attributes.get("Make"),
                "model": v.attributes.get("Model"),
                "lot": v.attributes.get("Lot"),
                "price": price,
                "cost": cost,
                "margin": round(margin, 2),
                "margin_pct": round(margin / price, 3) if price else None,
            })

    candidates.sort(key=lambda x: x["margin"])

    return {
        "count": len(candidates),
        "candidates": candidates[:50],
        "note": "Candidates: unsold vehicles with under 8% price-to-cost margin.",
    }


def service_intake_queue(role):
    """service.intake's real source: the most recently opened ServiceRecords plus any
    open OEM Recall campaigns matching Make/Model combinations currently in inventory
    -- both real signals a service intake desk needs on hand."""

    records = sorted(
        _entities(SERVICE_RECORD),
        key=lambda r: r.attributes.get("ServiceDate") or "",
        reverse=True,
    )[:20]

    open_recalls = [r for r in _entities(RECALL) if r.attributes.get("open")]

    return {
        "recent_service_records": [
            {
                "id": r.id,
                "vin": r.attributes.get("VIN"),
                "description": r.attributes.get("Description"),
                "service_date": r.attributes.get("ServiceDate"),
                "pay_type": r.attributes.get("PayType"),
                "status": r.attributes.get("Status"),
            }
            for r in records
        ],
        "open_recall_count": len(open_recalls),
        "open_recalls": [
            {
                "id": r.id,
                "recall_number": r.attributes.get("recall_number"),
                "make": r.attributes.get("make"),
                "model": r.attributes.get("model"),
                "description": r.attributes.get("description"),
                "campaign_type": r.attributes.get("campaign_type"),
            }
            for r in open_recalls
        ],
    }


def service_mpi_summary(role):
    """service.mpi's real source: same open-recall data as service.intake (a
    multi-point inspection should surface open recalls for the VIN being inspected)
    plus a real Cost/LaborHours summary across all completed service records, as a
    stand-in for 'typical MPI findings volume' since there's no dedicated MPI-findings
    field in the data model yet."""

    records = _entities(SERVICE_RECORD)
    open_recalls = [r for r in _entities(RECALL) if r.attributes.get("open")]

    total_cost = sum(_safe_float(r.attributes.get("Cost")) for r in records)
    total_labor_hours = sum(_safe_float(r.attributes.get("LaborHours")) for r in records)

    return {
        "service_record_count": len(records),
        "avg_cost_per_visit": round(total_cost / len(records), 2) if records else None,
        "avg_labor_hours_per_visit": round(total_labor_hours / len(records), 2) if records else None,
        "open_recall_count": len(open_recalls),
        "note": (
            "No dedicated MPI-findings field exists in this data model yet -- cost/"
            "labor-hour aggregates and open recalls stand in as the real signals "
            "available today."
        ),
    }


def service_warranty_claims(role):
    """service.warranty_claims's real source: ServiceRecords with PayType ==
    'Warranty' -- a genuine filter on real data, not a heuristic."""

    records = [r for r in _entities(SERVICE_RECORD) if r.attributes.get("PayType") == "Warranty"]
    total_cost = sum(_safe_float(r.attributes.get("Cost")) for r in records)
    total_parts_cost = sum(_safe_float(r.attributes.get("PartsCost")) for r in records)

    return {
        "count": len(records),
        "total_cost": round(total_cost, 2),
        "total_parts_cost": round(total_parts_cost, 2),
        "claims": [
            {
                "id": r.id,
                "vin": r.attributes.get("VIN"),
                "description": r.attributes.get("Description"),
                "service_date": r.attributes.get("ServiceDate"),
                "cost": r.attributes.get("Cost"),
                "parts_cost": r.attributes.get("PartsCost"),
                "technician": r.attributes.get("Technician"),
            }
            for r in records
        ],
    }


def finance_floorplan_payoff(role):
    """finance.floorplan_payoff's real source: total floorplan cost-basis exposure --
    sum(Cost) across unsold vehicles, grouped by Lot/Condition. HEURISTIC -- there's no
    real floorplan-lender or per-unit floorplan-line data model in this codebase, so
    this uses each vehicle's own Cost attribute as a stand-in for its floorplan
    principal, which is a real and directionally correct number but not an actual
    floorplan lender statement."""

    vehicles = _unsold_vehicles()
    by_group = {}

    for v in vehicles:
        key = f"{v.attributes.get('Lot', 'Unknown')} / {v.attributes.get('Condition', 'Unknown')}"
        cost = _safe_float(v.attributes.get("Cost"))
        group = by_group.setdefault(key, {"count": 0, "total_cost": 0.0})
        group["count"] += 1
        group["total_cost"] += cost

    for group in by_group.values():
        group["total_cost"] = round(group["total_cost"], 2)

    total_exposure = round(sum(_safe_float(v.attributes.get("Cost")) for v in vehicles), 2)

    return {
        "total_units": len(vehicles),
        "total_exposure": total_exposure,
        "by_lot_and_condition": by_group,
        "note": (
            "HEURISTIC: exposure is estimated from each Vehicle's own Cost attribute, "
            "used as a stand-in for its floorplan principal balance. No real "
            "floorplan-lender or per-unit floorplan-line data exists in this "
            "codebase yet."
        ),
    }


def administration_onboarding_roster(role):
    """administration.onboarding's real source: the Employee roster cross-referenced
    with real NXTDeal login credential coverage (core/auth.py's credential_store) --
    who has a login, who's still on a temp password, grouped by department. Gated
    ADMIN/OPERATIONS-only in REAL_SOURCES below since it surfaces every employee's
    account-security state."""

    employees = _entities(EMPLOYEE)
    credentialed_ids = {rec["employee_id"] for rec in credential_store.list_records()}
    must_change = {
        rec["employee_id"] for rec in credential_store.list_records()
        if rec.get("must_change_password")
    }

    by_department = {}
    for e in employees:
        dept = e.attributes.get("Department", "Unknown")
        entry = by_department.setdefault(dept, {"total": 0, "with_login": 0, "must_change_password": 0})
        entry["total"] += 1
        if e.id in credentialed_ids:
            entry["with_login"] += 1
        if e.id in must_change:
            entry["must_change_password"] += 1

    no_login = [
        {"id": e.id, "name": f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip(),
         "department": e.attributes.get("Department")}
        for e in employees
        if e.id not in credentialed_ids
    ]

    return {
        "total_employees": len(employees),
        "by_department": by_department,
        "employees_without_login": no_login,
    }


def operations_recon_queue(role):
    """operations.recon's real source (fixed session 59 -- previously mismapped to
    get_velocity_dashboard, which is LEAD pipeline velocity, not vehicle data): Used-
    condition unsold vehicles needing reconditioning review, grouped by Lot. HEURISTIC
    -- there's no recon-stage/recon-complete field in the Vehicle data model yet, so
    this surfaces the real population that recon work applies to (unsold Used units)
    rather than a fabricated 'in progress' vs 'complete' status."""

    used_unsold = [v for v in _unsold_vehicles() if v.attributes.get("Condition") == "Used"]

    by_lot = {}
    for v in used_unsold:
        lot = v.attributes.get("Lot", "Unknown")
        by_lot[lot] = by_lot.get(lot, 0) + 1

    return {
        "used_unsold_count": len(used_unsold),
        "by_lot": by_lot,
        "vehicles": [
            {
                "vehicle_id": v.id,
                "vin": v.attributes.get("VIN"),
                "stock_number": v.attributes.get("StockNumber"),
                "lot": v.attributes.get("Lot"),
                "year": v.attributes.get("Year"),
                "make": v.attributes.get("Make"),
                "model": v.attributes.get("Model"),
            }
            for v in used_unsold[:50]
        ],
        "note": (
            "HEURISTIC: no recon-stage field exists in the Vehicle data model yet -- "
            "this surfaces the real population (unsold Used-condition units) recon "
            "work applies to, not a fabricated in-progress/complete status."
        ),
    }


def operations_inventory_reconciliation(role):
    """operations.inventory_reconciliation's real source (fixed session 59 -- same
    mismap as operations.recon): reuses inventory_lot_audit's real PURCHASED-
    relationship discrepancy check -- the genuine reconciliation signal this workflow
    is about (does the sold-vehicle count on the graph match real ownership
    relationships)."""

    return inventory_lot_audit(role)


def inventory_aging_pricing_bands(role):
    """inventory.aging_pricing's real source (fixed session 59 -- same mismap as
    operations.recon/inventory_reconciliation): a real price-band distribution of
    unsold inventory. HEURISTIC on the 'aging' half specifically -- Vehicle entities
    have no acquisition/stock-date field in this data model, so true days-on-lot aging
    can't be computed; price banding is the real signal available today."""

    bands = [
        ("under_15k", 0, 15000),
        ("15k_25k", 15000, 25000),
        ("25k_40k", 25000, 40000),
        ("40k_plus", 40000, float("inf")),
    ]

    by_band = {label: {"count": 0, "total_value": 0.0} for label, _, _ in bands}

    for v in _unsold_vehicles():
        price = _safe_float(v.attributes.get("Price"))
        for label, low, high in bands:
            if low <= price < high:
                by_band[label]["count"] += 1
                by_band[label]["total_value"] += price
                break

    for entry in by_band.values():
        entry["total_value"] = round(entry["total_value"], 2)

    return {
        "unsold_count": len(_unsold_vehicles()),
        "by_price_band": by_band,
        "note": (
            "HEURISTIC: Vehicle entities have no acquisition/stock-date field in this "
            "data model, so true days-on-lot aging can't be computed yet -- price "
            "banding is the real signal available today."
        ),
    }


def _readiness_gaps(role):
    """readiness.exception_escalation's source -- departments whose 'tomorrow' horizon
    confidence is below core/prediction.py's GO_LIVE_CONFIDENCE_THRESHOLD, derived from
    the same readiness_predictions_api() the Readiness page's main panel already calls,
    not a new prediction path."""

    data = readiness_predictions_api()

    below_threshold = [
        entry for entry in data["departments"]
        if entry["readiness"] and not entry["readiness"]["ready"]
    ]

    return {
        "departments_below_threshold": below_threshold,
        "note": "Gate: 'tomorrow' horizon confidence >= the go-live threshold (default 90%).",
    }


# Each source: {"id", "label", "type", "fetch"}.
#   type "dashboard"   -- fetch() takes no args; gated here via can_access_dashboard(role, dashboard_key).
#   type "admin_only"  -- fetch() takes no args; gated here to ADMIN/OPERATIONS (matches /dashboard/audit's _require_admin).
#   type "self_gated"  -- fetch(role); the underlying *_api function already checks role itself.
REAL_SOURCES = {

    "operations.recon": [
        {"id": "recon_queue", "label": "Recon Queue (Used Unsold Inventory)", "type": "self_gated",
         "fetch": operations_recon_queue},
    ],
    "operations.deal_jacket_audit": [
        {"id": "compliance_alerts", "label": "Compliance Alerts (Deal Jacket)", "type": "self_gated",
         "fetch": list_alerts_api},
    ],
    "operations.inventory_reconciliation": [
        {"id": "reconciliation", "label": "Inventory / Ownership Reconciliation", "type": "self_gated",
         "fetch": operations_inventory_reconciliation},
    ],
    "operations.interdept_sla": [
        {"id": "workload", "label": "Cross-Department Workload", "type": "dashboard",
         "dashboard_key": "workload", "fetch": get_workload_dashboard_api},
    ],

    "sales.lead_cadence": [
        {"id": "pipeline", "label": "Lead Pipeline", "type": "dashboard",
         "dashboard_key": "pipeline", "fetch": get_lead_pipeline_dashboard},
        {"id": "followup", "label": "Follow-Up Queue", "type": "dashboard",
         "dashboard_key": "followup", "fetch": get_follow_up_dashboard},
    ],
    "sales.desking": [
        {"id": "desking_pipeline", "label": "Active Desking Pipeline", "type": "self_gated",
         "fetch": sales_desking_pipeline},
    ],
    "sales.fi_turnover": [
        {"id": "fi_turnover", "label": "F&I Turnover Queue", "type": "self_gated",
         "fetch": sales_fi_turnover_queue},
    ],
    "sales.delivery": [
        {"id": "delivery_queue", "label": "Delivery-Ready Queue", "type": "self_gated",
         "fetch": sales_delivery_queue},
    ],
    # Session 100 follow-up: the first two of Sam's ~10 "completely missing"
    # dealership workflows, given their own catalog entries (extending Sales from 4
    # to 6 workflow buttons -- DepartmentWorkflowButtons.tsx is fully catalog-driven,
    # confirmed no hardcoded "4" assumption before adding these).
    "sales.up_system": [
        {"id": "rotation", "label": "Floor Rotation (Up Board)", "type": "self_gated",
         "fetch": get_rotation_api},
    ],
    "sales.bdc": [
        {"id": "bdc_dashboard", "label": "BDC Untouched Queue + Response Time", "type": "self_gated",
         "fetch": get_bdc_dashboard_api},
    ],
    # Session 102 follow-up: the fourth of Sam's ~10 "completely missing" dealership
    # workflows -- the Demo Drive keys-out board + stats (core/demo_drive.py).
    "sales.demo_drive": [
        {"id": "demo_dashboard", "label": "Keys-Out Board + Test-Drive Stats", "type": "self_gated",
         "fetch": get_demo_drive_dashboard_api},
    ],
    # Session 104 follow-up: the fifth of Sam's ~10 "completely missing" dealership
    # workflows -- recent Credit Applications + real approval stats (core/credit_app.py).
    "sales.credit_app": [
        {"id": "credit_app_dashboard", "label": "Recent Applications + Approval Stats", "type": "self_gated",
         "fetch": get_credit_app_dashboard_api},
    ],
    # Session 104 follow-up: the sixth of Sam's ~10 "completely missing" dealership
    # workflows -- recent signature envelopes + real completion stats (core/esignature.py).
    "sales.esignature": [
        {"id": "esignature_dashboard", "label": "Recent Envelopes + Completion Stats", "type": "self_gated",
         "fetch": get_esignature_dashboard_api},
    ],

    "sales.fi_products": [
        {"id": "fi_products_dashboard", "label": "F&I Catalog + Queue + Penetration", "type": "self_gated",
         "fetch": get_fi_products_dashboard_api},
    ],

    "sales.lost_sale_recovery": [
        {"id": "lost_sale_recovery_dashboard", "label": "Lost Leads + Cancelled Deals + Stats", "type": "self_gated",
         "fetch": get_lost_sale_recovery_dashboard_api},
    ],

    "sales.orphan_owner_mining": [
        {"id": "orphan_owner_dashboard", "label": "Orphan Owner Queue + Stats", "type": "self_gated",
         "fetch": get_orphan_owner_dashboard_api},
    ],

    "marketing.oem_incentive": [
        {"id": "pending_campaigns", "label": "Pending Campaign Activations", "type": "self_gated",
         "fetch": list_pending_campaigns_api},
    ],
    # Session 68: "Website & Reputation" is the merged workflow (old website_merchandising
    # + old reputation workflows collapsed into one per new modal layout.pdf) -- carries
    # both real sources now.
    "marketing.website_merchandising": [
        {"id": "pending_websites", "label": "Pending Website Approvals", "type": "self_gated",
         "fetch": list_pending_websites_api},
        {"id": "reputation", "label": "Review Platform Summary", "type": "self_gated",
         "fetch": marketing_reputation_summary},
    ],
    "marketing.database_mining": [
        {"id": "mining_candidates", "label": "Equity / Renewal Mining Candidates", "type": "self_gated",
         "fetch": marketing_database_mining},
    ],
    # Session 68: this key now carries "Events & Activations" (per new modal layout.pdf's
    # Marketing restructure) -- no Event entity exists anywhere in this codebase yet (same
    # gap already flagged in core/marketing_menu.py's events()), so honestly no real
    # sources here rather than a stretch mapping.
    "marketing.reputation": [],

    "inventory.aging_pricing": [
        {"id": "aging_bands", "label": "Unsold Inventory Price Bands", "type": "self_gated",
         "fetch": inventory_aging_pricing_bands},
    ],
    "inventory.auction_acquisition": [
        {"id": "auctions", "label": "Auction Acquisition / Transport Pipeline", "type": "self_gated",
         "fetch": inventory_auction_acquisition},
    ],
    "inventory.lot_audit": [
        {"id": "lot_audit", "label": "Lot Audit / Ownership Discrepancies", "type": "self_gated",
         "fetch": inventory_lot_audit},
    ],
    "inventory.wholesale_disposition": [
        {"id": "wholesale_candidates", "label": "Wholesale Disposition Candidates", "type": "self_gated",
         "fetch": inventory_wholesale_disposition},
    ],

    "service.quality_control": [
        {"id": "service_dashboard", "label": "Service Department Overview", "type": "dashboard",
         "dashboard_key": "service", "fetch": get_service_dashboard},
    ],
    "service.intake": [
        {"id": "intake_queue", "label": "Intake Queue & Open Recalls", "type": "self_gated",
         "fetch": service_intake_queue},
    ],
    "service.mpi": [
        {"id": "mpi_summary", "label": "MPI Summary & Open Recalls", "type": "self_gated",
         "fetch": service_mpi_summary},
    ],
    "service.warranty_claims": [
        {"id": "warranty_claims", "label": "Warranty Claims", "type": "self_gated",
         "fetch": service_warranty_claims},
    ],

    "finance.cit_funding": [
        {"id": "pending_financing", "label": "Pending Lender Financing Decisions", "type": "self_gated",
         "fetch": list_pending_financing_api},
    ],
    "finance.compliance": [
        {"id": "compliance_alerts", "label": "Compliance Alerts", "type": "self_gated",
         "fetch": list_alerts_api},
    ],
    "finance.deal_accounting": [
        {"id": "finance_dashboard", "label": "Finance Department Overview", "type": "dashboard",
         "dashboard_key": "finance", "fetch": get_finance_dashboard},
    ],
    "finance.floorplan_payoff": [
        {"id": "floorplan_exposure", "label": "Floorplan Cost-Basis Exposure", "type": "self_gated",
         "fetch": finance_floorplan_payoff},
    ],

    "administration.audit_monitoring": [
        {"id": "audit_dashboard", "label": "Global Activity Log", "type": "admin_only",
         "fetch": get_audit_dashboard},
        {"id": "audit_events", "label": "Recent Audit Events (most recent 50)", "type": "admin_only",
         "fetch": lambda: list_audit_events()[:50]},
    ],
    "administration.vendor_management": [
        {"id": "connections", "label": "Connected Vendors / Integrations", "type": "self_gated",
         "fetch": list_connections_api},
    ],
    "administration.executive_approval": [
        {"id": "escalations", "label": "Escalation Queue", "type": "dashboard",
         "dashboard_key": "escalations", "fetch": get_escalation_dashboard_api},
    ],
    "administration.onboarding": [
        {"id": "onboarding_roster", "label": "Employee Roster & Login Coverage", "type": "admin_only",
         "fetch": lambda: administration_onboarding_roster(ADMIN)},
    ],

    "readiness.data_connection": [
        {"id": "connections", "label": "Connected Data Sources", "type": "self_gated",
         "fetch": list_connections_api},
    ],
    "readiness.data_maturity": [
        {"id": "readiness", "label": "Department Data Maturity / Confidence", "type": "self_gated",
         "fetch": lambda role: readiness_predictions_api()},
    ],
    "readiness.forecasting": [
        {"id": "readiness", "label": "Time-Horizon Forecasts (Tomorrow/Week/Month/Quarter)",
         "type": "self_gated", "fetch": lambda role: readiness_predictions_api()},
    ],
    "readiness.exception_escalation": [
        {"id": "readiness_gaps", "label": "Departments Below Readiness Threshold", "type": "self_gated",
         "fetch": _readiness_gaps},
    ],

    "network.peer_filtering": [
        {"id": "benchmarks", "label": "Peer Network Benchmarks", "type": "self_gated",
         "fetch": get_network_benchmarks_api},
    ],
    "network.gap_analysis": [
        {"id": "audit", "label": "AI Dealership Audit / Gap Analysis", "type": "self_gated",
         "fetch": get_network_audit_api},
    ],
    "network.trend_forecasting": [
        {"id": "benchmarks", "label": "Peer Network Benchmarks", "type": "self_gated",
         "fetch": get_network_benchmarks_api},
    ],
    "network.playbook_syndication": [
        {"id": "audit", "label": "Cross-Store Recommendations Feed", "type": "self_gated",
         "fetch": get_network_audit_api},
    ],
}


def get_tab_data(role, workflow_key, linked_entity_id=None):
    """Returns the real data available for one workflow's window: the linked entity
    (+ everything one hop away on the graph) if linked_entity_id was passed, plus
    whatever REAL_SOURCES blocks exist for this workflow_key. Every block/source is
    independently role-filtered -- a role with no access to a given source gets that
    source's own {"error": ...}, not a blanket failure for the whole response, so the
    rest of the window's real data still renders."""

    workflow = get_workflow_def(workflow_key)

    if not workflow:
        return {"error": f"Unknown workflow '{workflow_key}'"}

    result = {
        "workflow_key": workflow_key,
        "linked_entity": None,
        "related_entities": None,
        "sources": [],
    }

    if linked_entity_id:

        entity = get_entity_by_id(role, linked_entity_id)
        result["linked_entity"] = entity

        if "error" not in entity:
            result["related_entities"] = get_related_entities(role, linked_entity_id)

    for source in REAL_SOURCES.get(workflow_key, []):

        entry = {"id": source["id"], "label": source["label"]}
        kind = source["type"]

        if kind == "dashboard":
            if not can_access_dashboard(role, source["dashboard_key"]):
                entry["data"] = {
                    "error": f"Forbidden: your role cannot access the '{source['dashboard_key']}' dashboard"
                }
            else:
                entry["data"] = source["fetch"]()

        elif kind == "admin_only":
            if role not in (ADMIN, OPERATIONS):
                entry["data"] = {
                    "error": "Forbidden: this data is restricted to ADMIN/OPERATIONS"
                }
            else:
                entry["data"] = source["fetch"]()

        elif kind == "self_gated":
            entry["data"] = source["fetch"](role)

        else:
            entry["data"] = {"error": f"Unknown source type '{kind}'"}

        result["sources"].append(entry)

    return result
