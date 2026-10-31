"""
core/service_menu.py -- real data behind Service & Parts' 8-item Top Menu
(core/menu_catalog.py), session 61 continuation of the Top Menu rollout (Operations,
session 60; Sales, session 60; Service & Parts, this pass -- the third department, and
the first real test that the "no engine/frontend redesign needed, just a new
core/<dept>_menu.py + two dict entries" claim holds for a department whose data lives
in an entirely different corner of the graph than the sales pipeline).

Same discipline as core/operations_menu.py and core/sales_menu.py: reuse an already-
built, already-role-filtered function wherever it's a genuine match (service.pdf's
Repair Orders map cleanly onto the existing ServiceRecord entity, Warranty onto
core/workflow_tab_data.py's service_warranty_claims), compute a small new real aggregate
where the graph has the underlying data but nobody had queried it this way yet (parts
inventory value/turns off Part/PartSale, technician labor-hour distribution off
ServiceRecord.Technician), and use an honest `not_yet_tracked` note (never a fabricated
number) wherever service.pdf asks for something this data model doesn't back at all --
most notably Appointments (no Appointment/calendar entity exists anywhere in this
codebase, same gap already documented in core/sales_menu.py) and bay/shop-loading
scheduling (no bay or technician-calendar data model exists yet).

Every function takes `role` first (mirrors the operations/sales convention) and returns
a plain JSON-able dict -- core/menu_data.py's generic engine calls whichever one matches
the requested item_key, and the frontend's generic renderers display whatever comes
back, so nothing here needs to think about presentation.
"""

from core.dealeros import ledger
from core.entity_types import (
    SERVICE_RECORD,
    PART,
    PART_SALE,
    RECALL,
    CUSTOMER,
    VEHICLE,
    EMPLOYEE,
)

from core.workflow_tab_data import (
    service_intake_queue,
    service_mpi_summary,
    service_warranty_claims,
)
from core.compliance_api import list_alerts_api
from core.data_connections_api import readiness_predictions_api
from core.employee_value_api import list_employee_values_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.appointments import list_todays, list_this_week, list_appointments as _list_appointments
from core.repair_orders_api import get_ro_workspace_api, get_stage_counts_api
from core.shop_control_api import (
    get_dispatch_board_api, get_technician_utilization_api,
    get_stalled_ros_api, get_bottlenecks_api,
)
from core.service_customers_api import (
    get_customer_360_api as get_service_customer_360_api,
    get_lost_customer_recovery_api,
    get_declined_services_api,
)
from core.parts_desk_api import (
    get_parts_request_queue_api,
    get_special_orders_api,
    get_inventory_recommendations_api,
)
from core.warranty_desk_api import (
    get_claims_queue_api,
    get_rejected_claims_queue_api,
    get_recall_management_queue_api,
)
from core.service_reporting import (
    get_advisor_performance,
    get_technician_scorecard,
    get_shop_capacity,
    get_customer_retention_reporting,
)

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Service &
# Parts is the one department that maps to TWO Department Intelligence keys at once
# (its own combined scope) -- "service" and "parts" -- rather than the usual 1:1.
from core.department_intelligence_api import get_department_api


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _repair_orders_by_status(records):
    by_status = {}
    for r in records:
        status = r.attributes.get("Status", "Unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return by_status


def _repair_orders_by_pay_type(records):
    by_pay = {}
    for r in records:
        pay = r.attributes.get("PayType", "Unknown")
        by_pay[pay] = by_pay.get(pay, 0) + 1
    return by_pay


def _open_recalls():
    return [r for r in _entities(RECALL) if r.attributes.get("open")]


def _parts_inventory_value(parts):
    """Real total on-hand cost/retail exposure across the Part catalog --
    sum(QuantityOnHand * UnitCost) and sum(QuantityOnHand * ListPrice)."""
    total_cost = 0.0
    total_retail = 0.0
    for p in parts:
        qty = _safe_int(p.attributes.get("QuantityOnHand"))
        total_cost += qty * _safe_float(p.attributes.get("UnitCost"))
        total_retail += qty * _safe_float(p.attributes.get("ListPrice"))
    return round(total_cost, 2), round(total_retail, 2)


def overview(role):
    """service.pdf's "Overview" item: the Service & Parts home screen. Real KPIs off
    ServiceRecord/Part/PartSale/Recall; today's Appointments is real as of session 96
    (core/appointments.py) -- bay utilization and CSI score still have no backing
    data model in this codebase (no bay/shop-loading or survey entity exists), said
    so explicitly rather than guessed."""

    records = _entities(SERVICE_RECORD)
    parts = _entities(PART)
    part_sales = _entities(PART_SALE)

    by_status = _repair_orders_by_status(records)
    open_ros = sum(count for status, count in by_status.items() if status != "Completed")

    warranty = service_warranty_claims(role)
    open_recalls = _open_recalls()
    parts_cost, parts_retail = _parts_inventory_value(parts)

    service_revenue = round(sum(_safe_float(r.attributes.get("Cost")) for r in records), 2)
    parts_gross = round(sum(_safe_float(s.attributes.get("GrossProfit")) for s in part_sales), 2)

    technicians = [e for e in _entities(EMPLOYEE) if e.attributes.get("Department") == "Service"]

    todays_appointments = list_todays(department="Service")

    return {
        "repair_orders_total": len(records),
        "repair_orders_open": open_ros,
        "repair_orders_by_status": by_status,
        "warranty_claims_open": warranty.get("count"),
        "open_recall_count": len(open_recalls),
        "parts_inventory_cost_value": parts_cost,
        "parts_inventory_retail_value": parts_retail,
        "service_revenue_total": service_revenue,
        "parts_gross_profit_total": parts_gross,
        "service_technician_headcount": len(technicians),
        "todays_appointments": {"count": len(todays_appointments)},
        "not_yet_tracked": {
            "bay_utilization": "No service-bay/shop-loading data model exists yet.",
            "csi_score": "No customer-satisfaction survey data model exists yet.",
        },
    }


def _appointment_brief(a):
    return {
        "id": a.id,
        "appointment_type": a.attributes.get("appointment_type"),
        "customer_id": a.attributes.get("customer_id"),
        "assigned_to": a.attributes.get("assigned_to"),
        "scheduled_start": a.attributes.get("scheduled_start"),
        "status": a.attributes.get("status"),
    }


def appointments(role):
    """service.pdf's "Appointments" item: the service scheduling center. Today's/This
    week's bookings, waiter-vs-dropoff, and no-show tracking are real as of session 96
    (core/appointments.py) -- the recent-intake queue and open-recalls-needing-
    scheduling signals (unchanged) are still the real complement for what hasn't been
    booked yet. Bay assignments still have no backing data model (no service-bay
    entity exists)."""

    intake = service_intake_queue(role)

    todays_appts = list_todays(department="Service")
    weeks_appts = list_this_week(department="Service")
    waiters = _list_appointments(department="Service", appointment_type="waiter")
    dropoffs = _list_appointments(department="Service", appointment_type="drop_off")
    no_shows = _list_appointments(department="Service", status="no_show")

    return {
        "recent_intake": intake.get("recent_service_records"),
        "open_recalls_needing_scheduling": {
            "count": intake.get("open_recall_count"),
            "recalls": intake.get("open_recalls"),
        },
        "todays_appointments": {"count": len(todays_appts), "appointments": [_appointment_brief(a) for a in todays_appts]},
        "this_weeks_schedule": {"count": len(weeks_appts), "appointments": [_appointment_brief(a) for a in weeks_appts]},
        "waiter_vs_dropoff": {"waiters": len(waiters), "drop_offs": len(dropoffs)},
        "no_show_tracking": {"count": len(no_shows), "appointments": [_appointment_brief(a) for a in no_shows]},
        "not_yet_tracked": {
            "bay_assignments": "No service-bay data model exists yet.",
        },
    }


def repair_orders(role, query=None):
    """service.pdf's "Repair Orders" item -- the centerpiece of the Service rebuild
    (Sam: "This should be the centerpiece of Service... a full operating
    environment"). ServiceRecords ARE the repair orders, and as of the RO Workflow
    Engine (core/repair_orders.py) they now carry a real 10-stage lifecycle, concern
    tracking, estimate/approval, parts requests, a QC checklist, and a composed
    timeline -- not just a flat history list. Searching by an SRV- id now returns
    the real RO Workspace (get_ro_workspace_api) instead of a raw entity dump; the
    default view adds a real stage_board summary on top of the pre-existing status/
    pay-type breakdown, so the plain Top Menu path stays consistent with what the
    dedicated RepairOrderWorkspaceBoard.tsx shows."""

    records = _entities(SERVICE_RECORD)

    if query and query.strip():
        q = query.strip()

        if q.upper().startswith("SRV-"):
            workspace = get_ro_workspace_api(role, q.upper())
            if "error" in workspace:
                return workspace
            return {"repair_order": workspace}

        results = [r for r in search_entities(role, q) if r["entity_type"] == SERVICE_RECORD]
        return {"query": q, "count": len(results), "results": results}

    recent = sorted(
        records, key=lambda r: r.attributes.get("ServiceDate") or "", reverse=True
    )[:25]

    stage_counts = get_stage_counts_api(role)
    if not isinstance(stage_counts, dict) or "error" in stage_counts:
        stage_counts = {}

    return {
        "total": len(records),
        "by_status": _repair_orders_by_status(records),
        "by_pay_type": _repair_orders_by_pay_type(records),
        "stage_counts": stage_counts,
        "recent": [
            {
                "id": r.id,
                "vin": r.attributes.get("VIN"),
                "description": r.attributes.get("Description"),
                "service_date": r.attributes.get("ServiceDate"),
                "pay_type": r.attributes.get("PayType"),
                "status": r.attributes.get("Status"),
                "cost": r.attributes.get("Cost"),
                "technician": r.attributes.get("Technician"),
            }
            for r in recent
        ],
    }


def customers(role, query=None):
    """service.pdf's "Customers" item: "Service should be relationship-driven."
    A CUST- id lookup now returns the real grouped Customer 360
    (core/service_customers.py -- Vehicles Owned/Service History/Warranty/
    Recall/Declined Services/Retention) instead of a flat one-hop dump. The
    default view surfaces the real Lost Customer Recovery and Declined
    Services feeds (session 111 follow-up) alongside the existing recent-
    customers list."""

    if query and query.strip():
        q = query.strip()

        if q.upper().startswith("CUST-"):
            return get_service_customer_360_api(role, q.upper())

        results = [r for r in search_entities(role, q) if r["entity_type"] == CUSTOMER]
        return {"query": q, "count": len(results), "results": results}

    # Default: customers who actually have service records, most recent first by the
    # CustomerID that appears on the most recent ServiceRecords.
    records = sorted(
        _entities(SERVICE_RECORD), key=lambda r: r.attributes.get("ServiceDate") or "", reverse=True
    )
    customers_by_id = {c.attributes.get("CustomerID"): c for c in _entities(CUSTOMER)}

    seen = []
    seen_ids = set()
    for r in records:
        cust_key = r.attributes.get("CustomerID")
        if cust_key and cust_key not in seen_ids:
            seen_ids.add(cust_key)
            c = customers_by_id.get(cust_key)
            if c:
                seen.append({
                    "id": c.id,
                    "name": f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')}".strip(),
                    "email": c.attributes.get("Email"),
                    "phone": c.attributes.get("Phone"),
                    "last_service_date": r.attributes.get("ServiceDate"),
                })
        if len(seen) >= 20:
            break

    return {
        "default_view": "recent_service_customers",
        "customers": seen,
        "lost_customer_recovery": get_lost_customer_recovery_api(role),
        "declined_services": get_declined_services_api(role),
    }


def shop_control(role):
    """service.pdf's "Shop Control" item: "the operational heart of the shop." Real
    labor-hour and revenue distribution across technicians (off ServiceRecord.Technician
    and .LaborHours/.Cost) plus the pay-type revenue mix, unchanged from before -- plus,
    as of core/shop_control.py (Service rebuild, third slice), a real Technician
    Dispatch Board, real (HEURISTIC-over-an-assumed-capacity) Technician Utilization,
    real Stalled RO Detection, and a real composed Bottlenecks feed. Bay scheduling and
    live RO-in-bay status still have no backing data model (no service-bay entity
    exists anywhere in this codebase); the technician time-clock gap is now partially
    closed by the real utilization computation, though it's still built over an
    ASSUMED capacity, not a true clocked-hours figure."""

    records = _entities(SERVICE_RECORD)
    employees_by_id = {e.id: e for e in _entities(EMPLOYEE)}

    by_tech = {}
    for r in records:
        tech_id = r.attributes.get("Technician")
        if not tech_id:
            continue
        tech = by_tech.setdefault(tech_id, {"ro_count": 0, "labor_hours": 0.0, "revenue": 0.0})
        tech["ro_count"] += 1
        tech["labor_hours"] += _safe_float(r.attributes.get("LaborHours"))
        tech["revenue"] += _safe_float(r.attributes.get("Cost"))

    technician_productivity = []
    for tech_id, stats in by_tech.items():
        emp = employees_by_id.get(tech_id)
        technician_productivity.append({
            "technician_id": tech_id,
            "name": (
                f"{emp.attributes.get('FirstName', '')} {emp.attributes.get('LastName', '')}".strip()
                if emp else tech_id
            ),
            "ro_count": stats["ro_count"],
            "labor_hours": round(stats["labor_hours"], 2),
            "revenue": round(stats["revenue"], 2),
        })
    technician_productivity.sort(key=lambda t: t["labor_hours"], reverse=True)

    pay_type_revenue = {}
    for r in records:
        pay = r.attributes.get("PayType", "Unknown")
        pay_type_revenue[pay] = round(pay_type_revenue.get(pay, 0.0) + _safe_float(r.attributes.get("Cost")), 2)

    total_labor_hours = round(sum(t["labor_hours"] for t in technician_productivity), 2)

    return {
        "active_technicians": len(technician_productivity),
        "total_labor_hours": total_labor_hours,
        "technician_productivity": technician_productivity,
        "pay_type_revenue_mix": pay_type_revenue,
        "mpi_summary": service_mpi_summary(role),
        "dispatch_board": get_dispatch_board_api(role),
        "technician_utilization": get_technician_utilization_api(role),
        "stalled_ros": get_stalled_ros_api(role),
        "bottlenecks": get_bottlenecks_api(role),
        "not_yet_tracked": {
            "bay_scheduling": "No service-bay/shop-loading data model exists yet.",
            "live_shop_load": "Real-time RO status now exists (ro_stage/dispatch_board above) -- there's still no service-bay/physical-location field, so 'which bay is this vehicle in' remains untracked.",
            "technician_clock": "technician_utilization above is real, but built over an ASSUMED daily capacity -- no real time-clock/flat-rate-hours-turned data model exists yet to read a true capacity from.",
        },
    }


def parts(role, query=None):
    """service.pdf's "Parts" item: the parts department. Real inventory value/on-hand
    off the Part catalog, low-stock flagging (QuantityOnHand == 0), a category
    breakdown, and part-sale revenue/gross off PartSale. Searching filters the Part
    catalog by part number or description."""

    all_parts = _entities(PART)
    part_sales = _entities(PART_SALE)

    if query and query.strip():
        q = query.strip().lower()
        matched = [
            {
                "id": p.id,
                "part_number": p.attributes.get("PartNumber"),
                "description": p.attributes.get("Description"),
                "category": p.attributes.get("Category"),
                "quantity_on_hand": p.attributes.get("QuantityOnHand"),
                "unit_cost": p.attributes.get("UnitCost"),
                "list_price": p.attributes.get("ListPrice"),
            }
            for p in all_parts
            if q in str(p.attributes.get("PartNumber", "")).lower()
            or q in str(p.attributes.get("Description", "")).lower()
            or q in str(p.attributes.get("Category", "")).lower()
        ]
        return {"query": query.strip(), "count": len(matched), "results": matched[:100]}

    total_cost, total_retail = _parts_inventory_value(all_parts)

    by_category = {}
    for p in all_parts:
        cat = p.attributes.get("Category", "Uncategorized")
        group = by_category.setdefault(cat, {"sku_count": 0, "units_on_hand": 0})
        group["sku_count"] += 1
        group["units_on_hand"] += _safe_int(p.attributes.get("QuantityOnHand"))

    out_of_stock = [
        {"id": p.id, "part_number": p.attributes.get("PartNumber"), "description": p.attributes.get("Description")}
        for p in all_parts
        if _safe_int(p.attributes.get("QuantityOnHand")) == 0
    ]

    sales_revenue = round(sum(_safe_float(s.attributes.get("SalePrice")) * _safe_int(s.attributes.get("QuantitySold")) for s in part_sales), 2)
    sales_gross = round(sum(_safe_float(s.attributes.get("GrossProfit")) for s in part_sales), 2)

    by_customer_type = {}
    for s in part_sales:
        ct = s.attributes.get("CustomerType", "Unknown")
        by_customer_type[ct] = by_customer_type.get(ct, 0) + 1

    return {
        "sku_count": len(all_parts),
        "inventory_cost_value": total_cost,
        "inventory_retail_value": total_retail,
        "by_category": by_category,
        "out_of_stock": {"count": len(out_of_stock), "parts": out_of_stock[:50]},
        "part_sales": {
            "count": len(part_sales),
            "revenue_total": sales_revenue,
            "gross_profit_total": sales_gross,
            "by_customer_type": by_customer_type,
        },
        "parts_request_queue": get_parts_request_queue_api(role),
        "special_orders": get_special_orders_api(role),
        "inventory_recommendations": get_inventory_recommendations_api(role),
    }


def warranty(role):
    """service.pdf's "Warranty" item: warranty claims + OEM recalls. Reuses
    core/workflow_tab_data.py's service_warranty_claims (a real ServiceRecord.PayType ==
    'Warranty' filter) and the open-recall population. Claim submission/reimbursement
    aging has no backing status field on the warranty record yet."""

    claims = service_warranty_claims(role)
    open_recalls = _open_recalls()
    all_recalls = _entities(RECALL)

    return {
        "warranty_claims": claims,
        "recalls": {
            "total": len(all_recalls),
            "open": len(open_recalls),
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
        },
        "claims_workflow": get_claims_queue_api(role),
        "rejected_claims": get_rejected_claims_queue_api(role),
        "recall_management": get_recall_management_queue_api(role),
    }


def reporting(role):
    """service.pdf's "Reporting" item: department performance rollups, composed from the
    real functions above plus core/employee_value_api.py's already-built (ADMIN/
    OPERATIONS-gated) $ effectiveness data for Service personnel and core/prediction.py's
    real ledger-based repair_orders forecast (readiness_predictions_api) for Forecasting,
    rather than a fabricated projection."""

    records = _entities(SERVICE_RECORD)
    part_sales = _entities(PART_SALE)

    service_revenue = round(sum(_safe_float(r.attributes.get("Cost")) for r in records), 2)
    service_labor_hours = round(sum(_safe_float(r.attributes.get("LaborHours")) for r in records), 2)
    parts_revenue = round(sum(_safe_float(s.attributes.get("SalePrice")) * _safe_int(s.attributes.get("QuantitySold")) for s in part_sales), 2)
    parts_gross = round(sum(_safe_float(s.attributes.get("GrossProfit")) for s in part_sales), 2)

    warranty_claims = service_warranty_claims(role)
    personnel = list_employee_values_api(role, department="Service")

    readiness = readiness_predictions_api()
    service_forecast = next(
        (d for d in readiness.get("departments", []) if d["department"] == "service"), None
    )
    parts_forecast = next(
        (d for d in readiness.get("departments", []) if d["department"] == "parts"), None
    )

    return {
        "service_performance": {
            "repair_order_count": len(records),
            "service_revenue_total": service_revenue,
            "total_labor_hours": service_labor_hours,
            "avg_revenue_per_ro": round(service_revenue / len(records), 2) if records else None,
            "by_pay_type": _repair_orders_by_pay_type(records),
        },
        "parts_performance": {
            "part_sale_count": len(part_sales),
            "parts_revenue_total": parts_revenue,
            "parts_gross_profit_total": parts_gross,
        },
        "warranty_performance": {
            "claim_count": warranty_claims.get("count"),
            "claim_cost_total": warranty_claims.get("total_cost"),
        },
        "personnel_performance": personnel,
        "advisor_performance": get_advisor_performance(),
        "technician_scorecard": get_technician_scorecard(),
        "shop_capacity": get_shop_capacity(),
        "customer_retention": get_customer_retention_reporting(),
        "forecasting": {
            "service": service_forecast,
            "parts": parts_forecast,
        },
        "department_intelligence": {
            "service": get_department_api(role, "service"),
            "parts": get_department_api(role, "parts"),
        },
        "not_yet_tracked": {
            "effective_labor_rate": "No posted-vs-actual labor-rate field exists yet to compute a real ELR.",
            "csi_reporting": "No customer-satisfaction survey data model exists yet.",
        },
    }
