"""
core/operations_menu.py -- real data behind Operations' 8-item Top Menu
(core/menu_catalog.py), session 60. Sam: "Operations first, fully realized" when asked
how deep this first pass should go across the 9-department menu-bar batch.

Same discipline as core/workflow_tab_data.py's REAL_SOURCES build (session 57/59): reuse
an already-built, already-role-filtered function wherever one is a genuine match,
compute a small new real aggregate where the graph has the underlying data but nobody
had queried it this way yet, and use an honest `"note"` field (never a fabricated
precise-looking number) wherever operations.pdf asks for something the data model
doesn't track (e.g. no recon-stage timestamp exists, so "Average Recon Days" can't be
computed -- said so, not guessed at).

Every function here takes `role` first (mirrors REAL_SOURCES's "self_gated" convention)
and returns a plain JSON-able dict -- core/menu_data.py's generic engine calls whichever
one matches the requested item_key, and the frontend's generic ObjectTable/ListTable
renderers (same ones components/DepartmentWorkflowButtons.tsx already uses) display
whatever comes back, so nothing here needs to think about presentation.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE, DEAL, DOCUMENT, EMPLOYEE

from core.workflow_tab_data import (
    operations_recon_queue,
    operations_inventory_reconciliation,
    inventory_aging_pricing_bands,
    inventory_wholesale_disposition,
    inventory_auction_acquisition,
    inventory_lot_audit,
)
from core.compliance_api import list_alerts_api
from core.workload_dashboard_api import get_dashboard as get_workload_dashboard
from core.escalation_dashboard_api import get_dashboard as get_escalation_dashboard
from core.campaigns_api import list_pending_campaigns_api
from core.websites_api import list_pending_websites_api
from core.deals_api import list_pending_financing_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.unified_communications_api import get_unified_communications_overview_api
from core.communications_hub_api import get_communications_hub_overview_api
from core.customer_journey_api import get_journey_overview_api
from core.workforce_api import get_workforce_overview_api
from core.queries import get_service_dashboard
from core.employee_value_api import list_employee_values_api
from core.vehicle_lifecycle_api import get_vehicle_lifecycle_api
from core.vehicle_lifecycle import RECON_ITEMS
from core.operations_scheduling import get_delivery_risk_board
from core.operations_tasks import list_tasks as list_operations_tasks
from core.operations_alerts import get_alert_stats

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Department
# Intelligence's real KPI engine (core/department_intelligence.py) only has 5 keys --
# sales/service/parts/fi/executive -- not one per menu department, so this is an honest
# gap for Operations rather than a stretch mapping onto an unrelated key.
_DI_GAP_NOTE = {
    "available": False,
    "note": (
        "No 1:1 Department Intelligence key exists for Operations -- the 5 real keys "
        "are sales/service/parts/fi/executive (see core/department_intelligence.py)."
    ),
}


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _pending_count(result):
    """list_pending_*_api functions return either a plain list or a role-forbidden
    {"error": ...} dict -- normalize both into one shape so overview/tasks don't each
    reimplement this."""
    if isinstance(result, dict) and "error" in result:
        return {"count": None, "error": result["error"]}
    return {"count": len(result), "items": result}


def overview(role):
    """operations.pdf's "Overview" item: Operations home screen KPIs. Several of the
    PDF's requested KPIs (Average Recon Days, Vehicles Awaiting Inspection) have no
    backing field in the current data model -- said so explicitly rather than guessed."""

    recon = operations_recon_queue(role)
    aging = inventory_aging_pricing_bands(role)
    alerts = list_alerts_api(role, status="open")
    workload = get_workload_dashboard()
    lot_audit = inventory_lot_audit(role)

    deals_today_delivered = [
        d for d in _entities(DEAL)
        if d.attributes.get("status") == "funded"
        and str(d.attributes.get("funded_at") or "").startswith(_today())
    ]

    return {
        "units_in_recon": recon.get("used_unsold_count"),
        "aging_inventory_unsold_count": aging.get("unsold_count"),
        "compliance_exceptions_open": (
            len(alerts["alerts"]) if isinstance(alerts, dict) and "alerts" in alerts else None
        ),
        "compliance_access_error": alerts.get("error") if isinstance(alerts, dict) and "error" in alerts else None,
        "inventory_ownership_mismatches": lot_audit.get("sold_without_purchase_relationship"),
        "todays_deliveries": len(deals_today_delivered),
        "cross_department_bottlenecks": sorted(
            workload, key=lambda w: w["active_workload"], reverse=True
        )[:5],
        "not_yet_tracked": {
            "average_recon_days": "No recon-stage timestamp exists on Vehicle yet -- can't compute a real duration.",
            "vehicles_awaiting_inspection": "No inspection-status field exists on Vehicle yet.",
        },
    }


def tasks(role):
    """operations.pdf's "Tasks" item: a universal task queue. Rather than fabricate
    example tasks, this derives real, actionable items from real graph gaps -- the
    same "real computation over a real proxy" discipline as core/bot_tasks.py's
    _gap_* functions, applied to Operations-relevant data (wholesale candidates need
    transferring, lot-audit discrepancies need confirming, open compliance exceptions
    need reviewing) plus real cross-department pending-approval queues Operations, as
    the command-center department, needs visibility into."""

    wholesale = inventory_wholesale_disposition(role)
    lot_audit = inventory_lot_audit(role)
    alerts = list_alerts_api(role, status="open")
    escalations = get_escalation_dashboard()

    derived_tasks = []

    for candidate in wholesale.get("candidates", [])[:15]:
        derived_tasks.append({
            "type": "Transfer Unit to Wholesale",
            "entity_id": candidate["vehicle_id"],
            "detail": f"{candidate.get('year')} {candidate.get('make')} {candidate.get('model')} -- "
                      f"{candidate.get('margin_pct')} margin",
        })

    for discrepancy in lot_audit.get("discrepancies", [])[:15]:
        derived_tasks.append({
            "type": "Confirm Lot Audit",
            "entity_id": discrepancy["vehicle_id"],
            "detail": f"Marked sold with no PURCHASED relationship -- VIN {discrepancy.get('vin')}",
        })

    if isinstance(alerts, dict) and "alerts" in alerts:
        for alert in alerts["alerts"][:15]:
            derived_tasks.append({
                "type": "Review Compliance Exception",
                "entity_id": alert.get("id"),
                "detail": f"{alert.get('law', alert.get('category', 'Compliance'))} -- severity {alert.get('severity')}",
            })

    return {
        "tasks": derived_tasks,
        "task_count": len(derived_tasks),
        "escalations": escalations,
        "pending_approvals": {
            "campaigns": _pending_count(list_pending_campaigns_api(role)),
            "websites": _pending_count(list_pending_websites_api(role)),
            "financing": _pending_count(list_pending_financing_api(role)),
        },
    }


def vehicles(role, query=None):
    """operations.pdf's "Vehicles" item: vehicle-centric search by VIN/stock number,
    returning the full record plus everything one hop away on the graph. Session 106
    follow-up: the dedicated Vehicle Lifecycle Management Dash
    (components/VehicleLifecycleBoard.tsx) talks directly to
    /vehicle-lifecycle/* rather than this generic JSON view -- same "bespoke board
    bypasses /menu/data" precedent as every other department's real Dash build. This
    function still gets a lightweight real enrichment (lifecycle_status on a VIN-
    lookup) so the plain Top Menu / chat-tool path stays consistent with what the
    dedicated board shows, rather than silently diverging."""

    if not query:
        # Default view before a search: the real recon population, same as the
        # Scheduling item's Recon Board -- a reasonable "here's what's active" default.
        recon = operations_recon_queue(role)
        return {"default_view": "recon_queue", "vehicles": recon.get("vehicles", [])}

    if query.upper().startswith(("VEH-",)):
        entity = get_entity_by_id(role, query.upper())
        if "error" in entity:
            return entity
        related = get_related_entities(role, query.upper())
        lifecycle = get_vehicle_lifecycle_api(role, query.upper())
        return {"vehicle": entity, "related_entities": related, "lifecycle": lifecycle}

    results = [r for r in search_entities(role, query) if r["entity_type"] == VEHICLE]
    return {"query": query, "count": len(results), "results": results}


def inventory(role):
    """operations.pdf's "Inventory" item: the command center -- active/aging/incoming
    inventory, wholesale candidates, and the pricing queue."""

    unsold = [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold")]
    aging = inventory_aging_pricing_bands(role)
    wholesale = inventory_wholesale_disposition(role)
    auctions = inventory_auction_acquisition(role)

    pricing_queue = [
        {"vehicle_id": v.id, "vin": v.attributes.get("VIN"), "stock_number": v.attributes.get("StockNumber")}
        for v in unsold
        if not v.attributes.get("Price") or float(v.attributes.get("Price") or 0) <= 0
    ]

    incoming = [
        t for t in auctions.get("transactions", [])
        if t.get("transport_status") != "delivered"
    ]

    return {
        "active_inventory_count": len(unsold),
        "aging": aging,
        "wholesale_candidates": wholesale,
        "incoming_inventory": {"count": len(incoming), "transactions": incoming},
        "pricing_queue": {"count": len(pricing_queue), "vehicles": pricing_queue},
    }


def scheduling(role):
    """operations.pdf's "Scheduling" item: operational coordination across
    departments. Internal Install Queue has no backing data model yet -- honest
    placeholder, not fabricated."""

    recon = operations_recon_queue(role)
    auctions = inventory_auction_acquisition(role)
    service = get_service_dashboard()

    service_employees = [e for e in _entities(EMPLOYEE) if e.attributes.get("Department") == "Service"]

    deals_delivery_ready = [
        {"id": d.id, "customer_id": d.attributes.get("customer_id"), "vehicle_id": d.attributes.get("vehicle_id"),
         "status": d.attributes.get("status")}
        for d in _entities(DEAL)
        if d.attributes.get("status") in ("contract", "funded")
    ]

    return {
        "recon_board": recon.get("by_lot"),
        "transport_schedule": auctions.get("by_transport_status"),
        "delivery_calendar": {"count": len(deals_delivery_ready), "deals": deals_delivery_ready},
        "service_capacity": service,
        "technician_availability": {
            "service_department_headcount": len(service_employees),
        },
        "not_yet_tracked": {
            "internal_install_queue": "No accessory/install-request data model exists yet.",
        },
    }


def documents(role, query=None):
    """operations.pdf's "Documents" item: the categorized document vault seeded by
    imports/seed_demo_extras.py's seed_documents() -- Deal Jackets, Titles, Recon
    Forms, Inspection Reports, Buyer Orders, Compliance Files, searchable by the VIN/
    stock number/customer/employee the underlying entity resolves to."""

    docs = _entities(DOCUMENT)

    if query:
        q = query.lower()
        matched = []
        for d in docs:
            haystack = " ".join(str(v) for v in d.attributes.values()).lower()
            if q in haystack:
                matched.append(d)
        docs = matched

    by_type = {}
    for d in docs:
        doc_type = d.attributes.get("DocumentType", "Other")
        by_type.setdefault(doc_type, []).append({
            "id": d.id,
            "file_name": d.attributes.get("FileName"),
            "entity_type": d.attributes.get("EntityType"),
            "entity_id": d.attributes.get("EntityID"),
            "uploaded_by": d.attributes.get("UploadedBy"),
            "created_at": d.attributes.get("CreatedAt"),
        })

    return {
        "total": len(docs),
        "by_type": {k: {"count": len(v), "documents": v[:25]} for k, v in by_type.items()},
    }


def alerts(role):
    """operations.pdf's "Alerts" item: exception management, red/yellow/green per the
    PDF's severity framing -- open compliance alerts (severity-ranked), lot-audit
    ownership mismatches, and unfunded deals. Missing Documents is now a real check
    (funded Deals with no Deal Jacket on file) now that Documents exist on the graph;
    Missing Keys / Lost Vehicle Flags have no backing field yet."""

    open_alerts = list_alerts_api(role, status="open")
    lot_audit = inventory_lot_audit(role)

    unfunded_deals = [
        {"id": d.id, "status": d.attributes.get("status"), "customer_id": d.attributes.get("customer_id")}
        for d in _entities(DEAL)
        if d.attributes.get("status") in ("financing", "contract")
    ]

    funded_deal_ids = {d.id for d in _entities(DEAL) if d.attributes.get("status") == "funded"}
    documented_deal_ids = {
        doc.attributes.get("EntityID") for doc in _entities(DOCUMENT)
        if doc.attributes.get("EntityType") == DEAL and doc.attributes.get("DocumentType") == "Deal Jacket"
    }
    missing_deal_jackets = sorted(funded_deal_ids - documented_deal_ids)

    return {
        "compliance_alerts": open_alerts,
        "inventory_ownership_mismatches": lot_audit.get("discrepancies"),
        "unfunded_deals": {"count": len(unfunded_deals), "deals": unfunded_deals},
        "missing_deal_jackets": {"count": len(missing_deal_jackets), "deal_ids": missing_deal_jackets},
        "not_yet_tracked": {
            "missing_keys": "No key-tracking data model exists yet.",
            "lost_vehicle_flags": "No lot-location/geofence tracking data model exists yet.",
        },
    }


def _recon_reporting():
    """Session 106 follow-up #8 (Reporting): real process-performance metrics
    over Vehicle Lifecycle's recon checklist (session 106 follow-up #1) --
    distinct from operational_performance below, which is the pre-existing
    exception-style "how many need recon" count. This is "how is the recon
    process actually performing" -- completion rates and, where any real
    lifecycle_status_history exists, real stage-transition activity. Honest
    about a real limitation: this codebase has no per-item recon start
    timestamp, so a true cycle-time-per-item metric can't be computed --
    completion rate and transition counts are the real signals available."""

    used_unsold = [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold") and v.attributes.get("Condition") == "Used"]

    total = len(used_unsold)
    fully_complete = 0
    zero_progress = 0
    item_complete_counts = {item: 0 for item in RECON_ITEMS}
    total_complete_items = 0
    vehicles_with_history = 0

    for v in used_unsold:
        checklist = v.attributes.get("recon_checklist") or {}
        complete_count = 0
        for item in RECON_ITEMS:
            if (checklist.get(item) or {}).get("complete"):
                item_complete_counts[item] += 1
                complete_count += 1
        total_complete_items += complete_count
        if complete_count == len(RECON_ITEMS):
            fully_complete += 1
        if complete_count == 0:
            zero_progress += 1
        if v.attributes.get("lifecycle_status_history"):
            vehicles_with_history += 1

    avg_completion_pct = round(100 * total_complete_items / (total * len(RECON_ITEMS)), 1) if total else None

    return {
        "used_unsold_count": total,
        "avg_checklist_completion_pct": avg_completion_pct,
        "vehicles_fully_recon_complete": fully_complete,
        "vehicles_with_zero_recon_progress": zero_progress,
        "completion_by_item": item_complete_counts,
        "vehicles_with_recorded_stage_transitions": vehicles_with_history,
        "note": (
            "No per-item recon start timestamp exists in this data model, so a true "
            "cycle-time-per-item metric can't be computed -- checklist completion rate "
            "is the real process signal available today."
        ),
    }


def _delivery_reporting(role):
    """Real process-performance metric off Scheduling's own real Deal-vs-
    Appointment cross-reference (session 106 follow-up #5) -- an on-time
    delivery rate, not just a current risk snapshot."""

    board = get_delivery_risk_board(role)
    if not isinstance(board, dict) or "error" in board:
        return board

    on_track = board.get("on_track", {}).get("count", 0)
    no_delivery = board.get("no_delivery_scheduled", {}).get("count", 0)
    overdue = board.get("overdue", {}).get("count", 0)
    total = on_track + no_delivery + overdue

    return {
        "total_pending_delivery": total,
        "on_track": on_track,
        "no_delivery_scheduled": no_delivery,
        "overdue": overdue,
        "on_time_rate_pct": round(100 * on_track / total, 1) if total else None,
    }


def _inventory_actions_reporting():
    """Real process-performance metric off Inventory Aging's own real
    workflow actions (session 106 follow-up #4) -- how many aging-management
    actions have actually been taken, not just how many vehicles are aging."""

    tasks = list_operations_tasks()
    aging_task_types = {"transfer_to_wholesale", "manager_review", "marketing_campaign_tie_in", "auction_assignment"}
    by_type = {t: {"open": 0, "closed": 0} for t in aging_task_types}
    for task in tasks:
        t_type = task.attributes.get("task_type")
        if t_type in aging_task_types:
            bucket = "closed" if task.attributes.get("status") == "closed" else "open"
            by_type[t_type][bucket] += 1

    unsold = [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold")]
    total_price_reductions = sum(len(v.attributes.get("price_history") or []) for v in unsold)
    vehicles_with_price_reductions = sum(1 for v in unsold if v.attributes.get("price_history"))

    return {
        "actions_by_type": by_type,
        "total_price_reductions": total_price_reductions,
        "vehicles_with_price_reductions": vehicles_with_price_reductions,
    }


def reporting(role):
    """operations.pdf's "Reporting" item: department-specific performance rollups,
    composed entirely from the real functions above plus core/employee_value_api.py's
    already-built (ADMIN/OPERATIONS-gated) $ effectiveness data for Personnel
    Performance. Executive Reports overlaps with the Network/Department Intelligence
    dashboards already built elsewhere in NXTDeal -- not duplicated here.

    Session 106 follow-up #8 added four real process-performance sections (recon_
    reporting, delivery_reporting, inventory_actions_reporting, and an enriched
    compliance_reporting) on top of the original exception-style rollups below --
    Sam's own framing for this item was "Recon/Inventory/Delivery/Compliance
    Reporting, process-performance focused, distinct from existing exception
    reporting." No new routes needed: core/report_modules.py's catalog engine
    already turns any top-level key this function returns into a real draggable
    module on the existing ReportDashboardBuilder, same precedent session 97's
    Sales Reporting slice already established."""

    recon = operations_recon_queue(role)
    wholesale = inventory_wholesale_disposition(role)
    aging = inventory_aging_pricing_bands(role)
    open_alerts = list_alerts_api(role, status="open")
    resolved_alerts = list_alerts_api(role, status="resolved")
    workload = get_workload_dashboard()
    # Fixed session 64 (Finance rollout): list_employee_values() compares against
    # Employee.Department lowercased (core/employee_value.py's _department_of()) --
    # "Operations" never matched, so personnel_performance silently returned an empty
    # employees list from session 60 onward. Confirmed while wiring the same call
    # pattern into core/finance_menu.py's commissions().
    personnel = list_employee_values_api(role, department="operations")

    wholesale_loss_total = round(
        sum(c["margin"] for c in wholesale.get("candidates", []) if c["margin"] < 0), 2
    )

    open_alerts_list = open_alerts["alerts"] if isinstance(open_alerts, dict) and "alerts" in open_alerts else []
    by_law = {}
    for a in open_alerts_list:
        key = a.get("law", a.get("category", "Uncategorized"))
        by_law[key] = by_law.get(key, 0) + 1

    open_count = len(open_alerts_list)
    resolved_count = len(resolved_alerts["alerts"]) if isinstance(resolved_alerts, dict) and "alerts" in resolved_alerts else None
    total_seen = open_count + (resolved_count or 0)

    nervous_system = get_alert_stats(role)

    return {
        "operational_performance": {
            "used_unsold_needing_recon": recon.get("used_unsold_count"),
            "recon_by_lot": recon.get("by_lot"),
        },
        "inventory_performance": {
            "aging_by_price_band": aging.get("by_price_band"),
            "wholesale_candidate_count": wholesale.get("count"),
            "wholesale_loss_total": wholesale_loss_total,
        },
        "compliance_performance": {
            "open_count": open_count,
            "resolved_count": resolved_count,
            "open_by_law_or_category": by_law,
            "resolution_rate_pct": round(100 * (resolved_count or 0) / total_seen, 1) if total_seen else None,
            "nervous_system_snapshot": nervous_system,
        },
        "sla_performance": {
            "employees_with_active_workload": len(workload),
            "highest_workload": workload[-3:] if workload else [],
        },
        "personnel_performance": personnel,
        "recon_reporting": _recon_reporting(),
        "delivery_reporting": _delivery_reporting(role),
        "inventory_actions_reporting": _inventory_actions_reporting(),
        "department_intelligence": _DI_GAP_NOTE,
        "not_yet_tracked": {
            "executive_reports": (
                "See the Network and Department Intelligence dashboards for "
                "cross-department executive rollups -- not duplicated here."
            ),
        },
    }


def communications(role):
    """Operations' "Communications" Top Menu item (added 2026-07-19, Sam's own
    six-pillar spec naming "Communications/Unified Communications Hub" as one of
    Operations' genuinely missing sub-features; extended 2026-07-22 as the
    dedicated Communications Hub build -- Sam's own follow-up gap-analysis
    naming Communications Hub, with Recording/Transcription/Sentiment/
    Follow-Up Tasks/AI Summaries, as the highest-priority remaining module).

    Composes TWO real, distinct sources rather than one -- neither replaces the
    other:

    - `legacy_unified` reuses core/unified_communications_api.py's real,
      read-only, cross-department feed composed from Sales'/Service's/
      Finance's own already-real, but previously siloed, FieldNote-backed
      contact logs. See core/unified_communications.py's own module docstring
      for the full reuse-not-duplicate reasoning.
    - `communications_hub` is core/communications_hub_api.py's own first-class
      Communication log -- real logging across Phone/Text/Email/Chat/Social,
      honestly-simulated call recording/transcript/sentiment (session-110's
      disclosed-simulation convention, no real telephony vendor is connected
      anywhere in this codebase), real embedded follow-up tasks, and a real,
      isolated-OpenAI-backed AI summary with an honest deterministic fallback.
      See core/communications_hub.py's own module docstring for why this is a
      new, first-class entity rather than a FieldNote."""

    return {
        "legacy_unified": get_unified_communications_overview_api(role),
        "communications_hub": get_communications_hub_overview_api(role),
        "note": (
            "legacy_unified is the pre-existing Sales/Service/Finance "
            "FieldNote-backed aggregation (session 2026-07-19). "
            "communications_hub is the newer, first-class Communication log "
            "with real logging, simulated phone recording/transcript/"
            "sentiment, real follow-up tasks, and real AI summaries "
            "(session 2026-07-22) -- composed alongside, not replacing, the "
            "legacy feed."
        ),
    }


def customer_journey(role):
    """Operations' "Customer Journey" view (added 2026-07-22, slice 1) -- a
    thin, role-gated pass-through to core/customer_journey_api.py's real,
    graph-native lifecycle stage overview (per-stage counts + total across
    every Customer currently tracked through Awareness -> Lead -> Appointment
    -> Sale -> Service -> Loyalty -> Repeat).

    Journey state is stored directly as attributes on the existing Customer
    entity (core/customer_journey.py), the same graph-native "state on the
    entity itself" convention core/pipeline_state.py already established for
    Lead pipeline state -- not a separate store. Slice 1 is backend-only and
    AI-free; later slices add journey intelligence on top of this same
    backbone. See core/customer_journey.py's own module docstring."""

    return {
        "customer_journey": get_journey_overview_api(role),
        "note": (
            "Graph-native customer lifecycle stage tracking (Awareness -> "
            "Lead -> Appointment -> Sale -> Service -> Loyalty -> Repeat), "
            "stored as attributes on the Customer entity (slice 1, "
            "session 2026-07-22, backend backbone only -- no AI yet)."
        ),
    }


def workforce(role):
    """A new "Workforce" Top Menu item (added 2026-07-19, continuing Sam's
    six-pillar spec) -- a thin pass-through to core/workforce_api.py's real
    Directory/Shift Scheduling/Time-Off Requests/Coverage/Performance
    composition. See core/workforce.py's own module docstring for the full
    reasoning behind the two genuinely new entities (EmployeeShift,
    TimeOffRequest) this closes a real, confirmed-absent gap with."""

    return get_workforce_overview_api(role)
