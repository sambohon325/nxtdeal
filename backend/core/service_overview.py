"""
core/service_overview.py -- Service's "Overview" item, the second slice of
Service's rebuild (following the RO Workflow Engine, session 111). Sam's own
spec: a Service Command Center (real clickable waiting-buckets), Today's
Risks (actionable, not just informational), and an Advisor Dashboard (each
advisor's own personal queue). The Service Manager Dashboard's Shop
Capacity/Technician Utilization half is deliberately NOT duplicated here --
that's Shop Control's own item (Sam's spec lists it there too), so this
module only covers what's genuinely Overview-scoped: the command-center
buckets, today's risks, and the advisor's personal view.

Every bucket below is computed live off core/repair_orders.py's real
ro_stage -- "clickable" in Sam's spec means the frontend can list the real
RO ids behind each count, not just a number, so every bucket function
returns both a count and a capped list of RO briefs.

"Comebacks" is a genuinely new real signal: a vehicle (by VIN) that has more
than one ServiceRecord where a later RO's ServiceDate falls within 30 days of
an earlier one -- an honest proxy for "came back for more work shortly after
a visit," not a claim about whether it was for the SAME concern (no
concern-similarity matching exists in this codebase).

"Jobs Behind Schedule" and "Techs Overloaded" are both real computations
over an ASSUMED constant (a 24-hour shop-visit SLA, an assumed 8-hour/day
per-technician capacity) -- HEURISTIC, not simulated market data, since
there's no real SLA-commitment or time-clock field to read the true number
from; labeled accordingly. "Promised Today Not Started" is an honest gap --
no promised-time/promise-date field exists on ServiceRecord.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD, EMPLOYEE
from core.repair_orders import RO_STAGES, _stage_of, _ro_brief, _hours_since_checkin
from core.appointments import list_todays, list_this_week
from core.bot_tasks import infer_tier, TIER_MANAGER, TIER_EXECUTIVE
from core.permissions import ADMIN, OPERATIONS
from core.shop_control import get_technician_utilization

TECH_DAILY_CAPACITY_HOURS = 8.0
BEHIND_SCHEDULE_HOURS = 24.0
COMEBACK_WINDOW_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


def _records():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]


def _bucket(ros, limit=25):
    return {"count": len(ros), "repair_orders": [_ro_brief(r) for r in ros[:limit]]}


def _returned_bucket(records):
    # Sort the full set before the 25-record summary cap so urgent work isn't hidden.
    ordered = sorted(records, key=lambda r: (
        (r.attributes.get("return_followup") or {}).get("status") == "completed",
        (r.attributes.get("return_followup") or {}).get("due_date") or "",
        r.id,
    ))
    return _bucket(ordered)


def get_command_center():
    """Sam's spec, verbatim: Open ROs / Waiting Approval / Waiting Parts /
    Waiting Technician / Waiting Delivery / Comebacks -- "All clickable.\""""

    records = _records()
    live = [r for r in records if _stage_of(r) != "Follow-Up"]
    returned = [r for r in live if r.attributes.get("return_handover")]
    all_open = live
    live = [r for r in live if not r.attributes.get("return_handover")]

    waiting_approval = [r for r in live if _stage_of(r) == "Customer Approval"]
    waiting_parts = [r for r in live if _stage_of(r) == "Parts"]
    waiting_delivery = [r for r in live if _stage_of(r) == "Delivery"]
    waiting_technician = [
        r for r in live
        if _stage_of(r) == "Repair" and not r.attributes.get("Technician")
    ]

    # Comebacks: same VIN, a later ServiceDate within COMEBACK_WINDOW_DAYS of
    # an earlier one -- an honest "returned soon after" proxy, not a claim
    # about matching concerns.
    by_vin = {}
    for r in records:
        vin = r.attributes.get("VIN")
        date = r.attributes.get("ServiceDate")
        if vin and date:
            by_vin.setdefault(vin, []).append((date, r))

    comebacks = []
    for vin, entries in by_vin.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e[0])
        for i in range(1, len(entries)):
            try:
                prev_date = datetime.fromisoformat(entries[i - 1][0])
                cur_date = datetime.fromisoformat(entries[i][0])
            except ValueError:
                continue
            if 0 <= (cur_date - prev_date).days <= COMEBACK_WINDOW_DAYS:
                comebacks.append(entries[i][1])
                break

    return {
        "open_ros": _bucket(all_open),
        "returned_unfinished": _returned_bucket(returned),
        "waiting_approval": _bucket(waiting_approval),
        "waiting_parts": _bucket(waiting_parts),
        "waiting_technician": _bucket(waiting_technician),
        "waiting_delivery": _bucket(waiting_delivery),
        "comebacks": _bucket(comebacks),
        "note": (
            "'Comebacks' is a HEURISTIC proxy -- same VIN returning for another "
            f"RO within {COMEBACK_WINDOW_DAYS} days of a prior visit, not a "
            "confirmed same-concern comeback (no concern-similarity matching "
            "exists in this codebase)."
        ),
    }


def get_todays_risks():
    """Sam's spec: 'These are actionable' -- every bucket below is a real RO
    list, not just a count, so a manager can click straight into the ones
    that need attention."""

    records = _records()
    live = [r for r in records if _stage_of(r) != "Follow-Up"]
    returned = [r for r in live if r.attributes.get("return_handover")]
    all_open = live
    live = [r for r in live if not r.attributes.get("return_handover")]

    customers_waiting = [r for r in live if _stage_of(r) == "Check-In"]

    behind_schedule = []
    for r in live:
        hours = _hours_since_checkin(r)
        if hours is not None and hours >= BEHIND_SCHEDULE_HOURS:
            behind_schedule.append(r)

    parts_delayed = [
        r for r in live
        if _stage_of(r) == "Parts" and (r.attributes.get("parts_status") or {}).get("status") == "backordered"
    ]

    # Techs Overloaded -- reuses core/shop_control.py's real technician
    # utilization engine (the same one Shop Control's own dashboard uses)
    # rather than a second, independent computation of the same thing.
    utilization = get_technician_utilization()
    overloaded_techs = [
        {
            "technician_id": t["technician_id"],
            "hours_booked_today": t["hours_booked"],
            "assumed_capacity_hours": t["assumed_capacity_hours"],
        }
        for t in utilization["technicians"]
        if t["overloaded"]
    ]

    return {
        "customers_waiting": _bucket(customers_waiting),
        "jobs_behind_schedule": {
            **_bucket(behind_schedule),
            "note": f"HEURISTIC -- checked in {BEHIND_SCHEDULE_HOURS}+ hours ago with no real promised-time field to compare against.",
        },
        "techs_overloaded": {
            "count": len(overloaded_techs),
            "technicians": overloaded_techs,
            "note": f"HEURISTIC -- today's real LaborHours booked per technician vs. an ASSUMED {TECH_DAILY_CAPACITY_HOURS}-hour/day capacity (no real time-clock/shift data exists to read a true capacity from).",
        },
        "parts_delayed": _bucket(parts_delayed),
        "promised_today_not_started": {
            "count": None,
            "not_yet_tracked": "No promised-time/promise-date field exists on ServiceRecord yet.",
        },
    }


def _employee_name(emp):
    if not emp:
        return None
    return f"{emp.attributes.get('FirstName', '')} {emp.attributes.get('LastName', '')}".strip()


def get_advisor_dashboard(employee_id):
    """Sam's spec: 'My Appointments / My Waiting Customers / My Pending
    Approvals / My Vehicles Ready.' An RO's 'advisor' is whoever checked the
    customer in (ro_stage_history's first entry's `by`, i.e. the same value
    as create_repair_order()'s created_by) -- ServiceRecord has no separate
    Advisor field distinct from Technician, so this is the honest real
    analog rather than a fabricated field."""

    records = _records()

    def _advisor_of(r):
        history = r.attributes.get("ro_stage_history") or []
        return history[0].get("by") if history else None

    my_ros = [r for r in records if _advisor_of(r) == employee_id and _stage_of(r) != "Follow-Up"]

    my_returned = [r for r in records if r.attributes.get("return_handover") and _stage_of(r) != "Follow-Up" and ((r.attributes.get("return_followup") or {}).get("owner_id") or _advisor_of(r)) == employee_id]
    my_ros = [r for r in my_ros if not r.attributes.get("return_handover")]

    my_waiting_customers = [r for r in my_ros if _stage_of(r) in ("Check-In", "RO Written", "Inspection")]
    my_pending_approvals = [r for r in my_ros if _stage_of(r) == "Customer Approval"]
    my_vehicles_ready = [r for r in my_ros if _stage_of(r) in ("Quality Control", "Delivery")]

    todays_appts = list_todays(department="Service", assigned_to=employee_id)
    weeks_appts = list_this_week(department="Service", assigned_to=employee_id)

    emp = ledger.get_entity(employee_id)

    return {
        "advisor": {"id": employee_id, "name": _employee_name(emp)},
        "my_appointments": {
            "today_count": len(todays_appts),
            "this_week_count": len(weeks_appts),
        },
        "my_returned_unfinished": _returned_bucket(my_returned),
        "my_waiting_customers": _bucket(my_waiting_customers),
        "my_pending_approvals": _bucket(my_pending_approvals),
        "my_vehicles_ready": _bucket(my_vehicles_ready),
    }


def get_service_my_day(role, employee_id):
    """Assembles the full Overview payload: Advisor Dashboard (always,
    personal) plus the Service Command Center + Today's Risks (only for
    ADMIN/OPERATIONS or an employee whose real Title infers to a manager/
    executive tier -- same is_manager_view mechanic core/sales_overview.py's
    get_my_day() already established, since this codebase has no separate
    'Service Manager' role)."""

    employee = ledger.get_entity(employee_id)
    tier = infer_tier(employee.attributes.get("Title") if employee else None)
    is_manager_view = role in (ADMIN, OPERATIONS) or tier in (TIER_MANAGER, TIER_EXECUTIVE)

    result = {
        "advisor_dashboard": get_advisor_dashboard(employee_id),
        "is_manager_view": is_manager_view,
    }

    if is_manager_view:
        result["command_center"] = get_command_center()
        result["todays_risks"] = get_todays_risks()

    return result
