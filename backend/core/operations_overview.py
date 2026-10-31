"""
core/operations_overview.py -- Overview + Action Center, the second slice of
Operations' rebuild (session 106 follow-up #2, right after Vehicle Lifecycle
Management). Sam's spec asked for three real pieces on top of the existing KPI
widgets (`core/operations_menu.py`'s `overview()`, untouched): an "Operations
Action Center" (clickable Daily Priorities, not bare counts), a color-coded
"Department Health Dashboard," and "Workload Distribution."

Reuses `core/workflow_tab_data.py`'s `operations_recon_queue`/
`inventory_wholesale_disposition`/`inventory_lot_audit`, `core/compliance_api.py`'s
`list_alerts_api`, and -- new this session -- `core/vehicle_lifecycle.py`'s real
lifecycle-stage/recon-checklist data for a genuinely new "Vehicles Awaiting
Inspection" signal that had no backing data model before this session.

Honest scoping decisions, stated up front rather than guessed silently:

- "Units Over 90 Days" from Sam's spec can't be computed -- Vehicle has no
  acquisition/stock-date field anywhere in this codebase (confirmed absent, same
  finding sessions 63/85/106 already independently made). Substituted with the
  real, correctly-labeled analog "Wholesale Candidates (Thin Margin)" -- vehicles
  that genuinely need a pricing/disposition decision today. Same honest-substitute
  precedent as `core/department_intelligence.py`'s F&I "Deals Financed" swapped in
  for an unbuildable "Product Penetration" (before session 105 made the real thing
  possible for Sales' own F&I workflow).

- Sam's "Recon Team / Title Team / Lot Team" utilization example is illustrative,
  not literal -- this codebase has exactly one real Operations-department Title &
  Registration Clerk and no dedicated Recon/Lot team rosters (recon work is
  physically performed by Service technicians, per `ServiceRecord.Technician`).
  Workload Distribution here is a real task-volume-to-headcount RATIO across three
  genuine functional areas (Title Processing, Recon/Vehicle Prep, Lot/Inventory
  Operations), explicitly labeled HEURISTIC -- no time-tracking/shift/clock-in data
  exists anywhere in this codebase to compute a real literal utilization percentage.

- "Allow Manager Reassignment" is deliberately NOT built here -- real per-task
  ownership assignment belongs to the Universal Operations Work Queue (Sam's
  separate "Tasks" spec item), not invented ad hoc inside Overview.
"""

from datetime import datetime, timezone, timedelta

from core.dealeros import ledger
from core.entity_types import VEHICLE, DEAL, DOCUMENT, EMPLOYEE

from core.workflow_tab_data import (
    operations_recon_queue,
    inventory_wholesale_disposition,
    inventory_lot_audit,
)
from core.compliance_api import list_alerts_api
from core.vehicle_lifecycle import list_by_stage as lifecycle_by_stage

_DELIVERY_SECTIONS = ("vehicle_prep", "quality_control", "tech_setup", "documentation")


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _section_complete(section_data):
    if not section_data:
        return False
    bool_items = {k: v for k, v in section_data.items() if isinstance(v, bool)}
    if not bool_items:
        return False
    return all(bool_items.values())


def _deal_delivery_ready(deal):
    checklist = deal.attributes.get("delivery_checklist") or {}
    return all(_section_complete(checklist.get(s)) for s in _DELIVERY_SECTIONS)


def _missing_title_vehicles():
    title_docs = {
        d.attributes.get("EntityID")
        for d in _entities(DOCUMENT)
        if d.attributes.get("EntityType") == VEHICLE and d.attributes.get("DocumentType") == "Title"
    }
    unsold = [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold")]
    return [v for v in unsold if v.id not in title_docs]


def get_action_center(role):
    """Sam's "Daily Priorities" -- every item real, every item carries real entity
    ids meant to be individually clickable in the UI, not just a bare count."""

    deals = _entities(DEAL)
    at_risk_deals = [
        d for d in deals
        if d.attributes.get("status") in ("contract", "funded") and not _deal_delivery_ready(d)
    ]

    missing_titles = _missing_title_vehicles()

    inspection_stage = lifecycle_by_stage(stage="Inspection").get("Inspection", [])

    open_alerts = list_alerts_api(role, status="open")
    compliance_error = open_alerts.get("error") if isinstance(open_alerts, dict) and "error" in open_alerts else None
    compliance_count = len(open_alerts["alerts"]) if isinstance(open_alerts, dict) and "alerts" in open_alerts else None

    wholesale = inventory_wholesale_disposition(role)

    return {
        "deliveries_at_risk": {
            "count": len(at_risk_deals),
            "deals": [
                {
                    "deal_id": d.id,
                    "customer_id": d.attributes.get("customer_id"),
                    "vehicle_id": d.attributes.get("vehicle_id"),
                    "status": d.attributes.get("status"),
                }
                for d in at_risk_deals[:25]
            ],
            "note": "A deal in contract/funded status whose delivery_checklist (vehicle_prep/quality_control/tech_setup/documentation) isn't fully checked off yet.",
        },
        "vehicles_missing_titles": {
            "count": len(missing_titles),
            "vehicles": [
                {"vehicle_id": v.id, "vin": v.attributes.get("VIN"), "stock_number": v.attributes.get("StockNumber")}
                for v in missing_titles[:25]
            ],
        },
        "vehicles_awaiting_inspection": {
            "count": len(inspection_stage),
            "vehicles": inspection_stage[:25],
            "note": "Real as of this session's Vehicle Lifecycle Management build -- vehicles whose lifecycle_status is explicitly 'Inspection'.",
        },
        "compliance_violations": {
            "count": compliance_count,
            "error": compliance_error,
        },
        "wholesale_candidates_needing_decision": {
            "count": wholesale.get("count"),
            "vehicles": wholesale.get("candidates", [])[:10],
            "substituted_for": (
                "Sam's spec asked for 'Units Over 90 Days' -- no acquisition-date field "
                "exists on Vehicle anywhere in this codebase, so real day-based aging "
                "can't be computed. This is the honest substitute: vehicles that "
                "genuinely need a pricing/disposition decision today."
            ),
        },
    }


def get_department_health(role):
    """Sam's "Department Health Dashboard" -- 5 real color-coded statuses."""

    recon = operations_recon_queue(role)
    open_alerts = list_alerts_api(role, status="open")
    compliance_count = len(open_alerts["alerts"]) if isinstance(open_alerts, dict) and "alerts" in open_alerts else 0

    deals = _entities(DEAL)
    now = datetime.now(timezone.utc)
    stale_financing = 0

    for d in deals:
        if d.attributes.get("status") != "financing":
            continue
        updated = d.attributes.get("updated_at")
        if not updated:
            continue
        try:
            dt = datetime.fromisoformat(updated)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if (now - dt) > timedelta(days=3):
            stale_financing += 1

    lifecycle = lifecycle_by_stage()
    front_line_ready = len(lifecycle.get("Front Line Ready", []))
    total_active = sum(len(v) for k, v in lifecycle.items() if k not in ("Sold", "Delivered"))

    wholesale = inventory_wholesale_disposition(role)

    checks = [
        {
            "area": "Sales Ready Inventory",
            "status": "healthy" if total_active and front_line_ready / total_active >= 0.5 else "warning",
            "detail": f"{front_line_ready} of {total_active} active-pipeline units are Front Line Ready.",
        },
        {
            "area": "Recon Delays",
            "status": "warning" if recon.get("used_unsold_count", 0) > 20 else "healthy",
            "detail": f"{recon.get('used_unsold_count', 0)} used unsold units in the recon-applicable population.",
        },
        {
            "area": "Funding Delays",
            "status": "warning" if stale_financing > 0 else "healthy",
            "detail": (
                f"{stale_financing} deals in financing with no update in 3+ days "
                f"(HEURISTIC -- no submitted-to-lender timestamp exists, updated_at "
                f"is the real proxy, same convention as core/finance_menu.py's "
                f"funding-aging figure)."
            ),
        },
        {
            "area": "Compliance",
            "status": "warning" if compliance_count > 0 else "healthy",
            "detail": f"{compliance_count} open compliance alerts.",
        },
        {
            "area": "Aged Inventory",
            "status": "warning" if wholesale.get("count", 0) > 5 else "healthy",
            "detail": (
                f"{wholesale.get('count', 0)} wholesale-candidate units under 8% margin "
                f"(real substitute for day-based aging -- see acquisition-date gap note)."
            ),
        },
    ]

    return {"checks": checks}


def get_workload_distribution(role):
    """Sam's "Workload Distribution" -- see module docstring for why this is a real
    task-volume-to-headcount ratio across 3 genuine functional areas, not a
    fabricated literal utilization percentage or Sam's illustrative 3 team names."""

    employees = _entities(EMPLOYEE)
    ops_employees = [e for e in employees if (e.attributes.get("Department") or "").strip().lower() == "operations"]
    service_employees = [e for e in employees if (e.attributes.get("Department") or "").strip().lower() == "service"]

    title_clerks = [e for e in ops_employees if "title" in (e.attributes.get("Title") or "").lower()]
    title_clerk_ids = {e.id for e in title_clerks}
    lot_ops_staff = [e for e in ops_employees if e.id not in title_clerk_ids]

    missing_titles = _missing_title_vehicles()
    recon = operations_recon_queue(role)
    lot_audit = inventory_lot_audit(role)
    wholesale = inventory_wholesale_disposition(role)

    def _ratio_bucket(task_count, headcount):
        if headcount <= 0:
            return "unstaffed"
        ratio = task_count / headcount
        if ratio >= 15:
            return "high"
        if ratio >= 5:
            return "moderate"
        return "low"

    lot_task_count = lot_audit.get("sold_without_purchase_relationship", 0) + wholesale.get("count", 0)

    areas = [
        {
            "area": "Title Processing",
            "headcount": len(title_clerks),
            "employee_ids": [e.id for e in title_clerks],
            "open_task_count": len(missing_titles),
            "load": _ratio_bucket(len(missing_titles), len(title_clerks)),
        },
        {
            "area": "Recon / Vehicle Prep",
            "headcount": len(service_employees),
            "employee_ids": [e.id for e in service_employees],
            "open_task_count": recon.get("used_unsold_count", 0),
            "load": _ratio_bucket(recon.get("used_unsold_count", 0), len(service_employees)),
            "note": (
                "Recon work is physically performed by Service technicians in this "
                "codebase (ServiceRecord.Technician) -- no separate Recon Team "
                "roster exists in Operations."
            ),
        },
        {
            "area": "Lot / Inventory Operations",
            "headcount": len(lot_ops_staff),
            "employee_ids": [e.id for e in lot_ops_staff],
            "open_task_count": lot_task_count,
            "load": _ratio_bucket(lot_task_count, len(lot_ops_staff)),
        },
    ]

    return {
        "areas": areas,
        "methodology_note": (
            "HEURISTIC: a real open-task-count-to-real-headcount ratio, not a "
            "time-tracked utilization percentage -- no shift/clock-in/time-tracking "
            "data exists anywhere in this codebase. 'Recon Team'/'Title Team'/'Lot "
            "Team' from the original spec were illustrative examples; this codebase "
            "has exactly one real Title & Registration Clerk and no dedicated Recon/"
            "Lot rosters, so the 3 functional areas above are the honest real analog."
        ),
        "reassignment_note": (
            "Manager reassignment of specific open tasks is handled by the "
            "Universal Operations Work Queue (Tasks item), not duplicated here."
        ),
    }


def get_operations_overview(role):
    """Composes Action Center + Department Health + Workload Distribution into one
    call for the frontend Overview board, on top of operations_menu.py's own
    existing overview() KPIs (untouched, still real)."""

    return {
        "action_center": get_action_center(role),
        "department_health": get_department_health(role),
        "workload_distribution": get_workload_distribution(role),
    }
