"""
core/service_reporting.py -- Service's "Reporting" item, the seventh and
final slice of Service's original 8-item spec (following RO Workflow
Engine, Overview, Shop Control, Customers, Parts, and Warranty, session
111). Sam's spec: Advisor Performance, Technician Scorecard, Shop Capacity,
and Customer Retention -- department PROCESS-performance rollups, distinct
from `core/service_menu.py`'s existing `reporting()` (service/parts revenue
totals, warranty cost, personnel $ value, forecasting).

Every section here reuses an already-built engine rather than a new one:
Advisor Performance reuses `core/service_overview.py`'s own real advisor
derivation (an RO's "advisor" is whoever checked the customer in --
`ro_stage_history[0]["by"]` -- since ServiceRecord has no separate Advisor
field), scoped honestly to live RO Workflow Engine records only (the 434
historical ServiceRecords predate stage-history tracking entirely and are
correctly excluded, not guessed at). Technician Scorecard combines
`core/shop_control.py`'s real technician roster/utilization with a real
historical RO-count/revenue rollup per technician off
`ServiceRecord.Technician` (the same real attribution
`core/employee_value.py`'s `_real_service_value()` already established,
recomputed here without that function's trailing-window limit since a
scorecard wants the full picture, not just a recent window). Shop Capacity
reuses `core/shop_control.py`'s dispatch board + utilization for a real
department-wide rollup. Customer Retention reuses
`core/service_customers.py`'s real per-customer retention/lost-customer/
declined-services engines, aggregated across every customer with service
history rather than a second retention computation.
"""

from datetime import date

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD, EMPLOYEE, CUSTOMER
from core.repair_orders import _stage_of
from core.shop_control import _service_technicians, _employee_name, get_dispatch_board, get_technician_utilization
from core.service_customers import get_lost_customer_recovery, get_declined_services, get_retention_metrics


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _all_records():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]


def _advisor_of(r):
    """Same real derivation as core/service_overview.py's get_advisor_dashboard()
    -- an RO's 'advisor' is whoever checked the customer in
    (ro_stage_history's first entry's `by`)."""
    history = r.attributes.get("ro_stage_history") or []
    return history[0].get("by") if history else None


def get_advisor_performance():
    """Real per-advisor rollup, scoped to live RO Workflow Engine records
    only (the only ones with a real ro_stage_history to derive an advisor
    from) -- an honest scope limit, not a fabricated advisor field on the
    434 historical ServiceRecords that predate this workflow entirely."""

    live_records = [r for r in _all_records() if r.attributes.get("ro_stage_history")]

    by_advisor = {}
    for r in live_records:
        advisor_id = _advisor_of(r)
        if not advisor_id:
            continue
        entry = by_advisor.setdefault(advisor_id, {"advisor_id": advisor_id, "ro_count": 0, "open_count": 0, "completed_count": 0, "estimates_sent": 0, "estimates_approved": 0})
        entry["ro_count"] += 1
        if _stage_of(r) == "Follow-Up":
            entry["completed_count"] += 1
        else:
            entry["open_count"] += 1
        estimate = r.attributes.get("estimate")
        if estimate:
            entry["estimates_sent"] += 1
            if estimate.get("approved") is True:
                entry["estimates_approved"] += 1

    employees_by_id = {e.id: e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE}

    scorecards = []
    for advisor_id, entry in by_advisor.items():
        emp = employees_by_id.get(advisor_id)
        approval_rate = round(100.0 * entry["estimates_approved"] / entry["estimates_sent"], 1) if entry["estimates_sent"] else None
        scorecards.append({
            **entry,
            "name": _employee_name(emp) or advisor_id,
            "estimate_approval_rate_pct": approval_rate,
        })

    scorecards.sort(key=lambda s: s["ro_count"], reverse=True)

    return {
        "count": len(scorecards),
        "advisors": scorecards,
        "note": "Scoped to live RO Workflow Engine records only -- historical ServiceRecords predate stage-history tracking and have no real advisor to derive.",
    }


def get_technician_scorecard():
    """Combines shop_control.py's real technician roster/today's utilization
    with a real all-time RO-count/revenue rollup per technician off
    ServiceRecord.Technician -- the full historical picture, not just
    today's booked hours."""

    records = _all_records()

    by_tech = {}
    for r in records:
        tech_id = r.attributes.get("Technician")
        if not tech_id:
            continue
        entry = by_tech.setdefault(tech_id, {"technician_id": tech_id, "ro_count": 0, "total_labor_hours": 0.0, "total_revenue": 0.0})
        entry["ro_count"] += 1
        entry["total_labor_hours"] += _safe_float(r.attributes.get("LaborHours"))
        entry["total_revenue"] += _safe_float(r.attributes.get("Cost")) - _safe_float(r.attributes.get("PartsCost"))

    today_utilization = {u["technician_id"]: u for u in get_technician_utilization()["technicians"]}

    employees_by_id = {e.id: e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE}

    scorecards = []
    for tech in _service_technicians():
        entry = by_tech.get(tech.id, {"technician_id": tech.id, "ro_count": 0, "total_labor_hours": 0.0, "total_revenue": 0.0})
        today = today_utilization.get(tech.id)
        scorecards.append({
            "technician_id": tech.id,
            "name": _employee_name(tech),
            "ro_count": entry["ro_count"],
            "total_labor_hours": round(entry["total_labor_hours"], 1),
            "total_revenue": round(entry["total_revenue"], 2),
            "avg_revenue_per_ro": round(entry["total_revenue"] / entry["ro_count"], 2) if entry["ro_count"] else None,
            "today_utilization_pct": today["utilization_pct"] if today else 0,
            "today_overloaded": today["overloaded"] if today else False,
        })

    scorecards.sort(key=lambda s: s["total_revenue"], reverse=True)

    return {"count": len(scorecards), "technicians": scorecards}


def get_shop_capacity():
    """Real department-wide capacity rollup off shop_control.py's dispatch
    board + utilization, rather than a third computation."""

    board = get_dispatch_board()
    utilization = get_technician_utilization()

    total_open_ros = sum(len(t["repair_orders"]) for t in board["technicians"].values()) + len(board["unassigned"])
    utilized_techs = [t for t in utilization["technicians"] if t["ro_count"] > 0]
    avg_utilization = round(sum(t["utilization_pct"] for t in utilized_techs) / len(utilized_techs), 1) if utilized_techs else 0

    return {
        "technician_count": len(board["technicians"]),
        "open_ro_count": total_open_ros,
        "unassigned_ro_count": len(board["unassigned"]),
        "avg_open_ros_per_technician": round(total_open_ros / len(board["technicians"]), 1) if board["technicians"] else None,
        "avg_utilization_pct_today": avg_utilization,
        "overloaded_technician_count": sum(1 for t in utilization["technicians"] if t["overloaded"]),
    }


def get_customer_retention_reporting():
    """Aggregates core/service_customers.py's real per-customer retention/
    lost-customer/declined-services engines across every customer with
    service history, rather than a second retention computation."""

    customers_with_history = set()
    for r in _all_records():
        cust_key = r.attributes.get("CustomerID")
        if cust_key:
            customers_with_history.add(cust_key)

    customers_by_key = {c.attributes.get("CustomerID"): c for c in ledger.get_all().values() if c.entity_type == CUSTOMER}

    visits_per_year = []
    for cust_key in customers_with_history:
        customer = customers_by_key.get(cust_key)
        if not customer:
            continue
        metrics = get_retention_metrics(customer.id)
        if metrics.get("visits_per_year") is not None:
            visits_per_year.append(metrics["visits_per_year"])

    avg_visits_per_year = round(sum(visits_per_year) / len(visits_per_year), 2) if visits_per_year else None

    lost = get_lost_customer_recovery()
    declined = get_declined_services()

    return {
        "customers_with_service_history": len(customers_with_history),
        "avg_visits_per_year": avg_visits_per_year,
        "lost_customers": {"count": lost["count"]},
        "declined_services": {"count": declined["count"], "total_value": declined["total_value"]},
    }
