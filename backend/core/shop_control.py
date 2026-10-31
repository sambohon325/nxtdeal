"""
core/shop_control.py -- Service's "Shop Control" item, the third slice of
Service's rebuild (following the RO Workflow Engine and Overview slices,
session 111). Sam's own framing: "This should be the operational heart of
the shop." His spec lists a Technician Dispatch Board, a Shop Workflow
Board, Technician Utilization, Stalled RO Detection, and Shop Bottlenecks.

The Shop Workflow Board is deliberately NOT rebuilt here -- it's the exact
same real 10-stage board `core/repair_orders.py`'s `get_ro_board()` already
provides (Check-In -> ... -> Follow-Up), already rendered by
`RepairOrderWorkspaceBoard.tsx`. Duplicating it under Shop Control would be
a second board showing the same real data through the same lens; this
module covers the four genuinely NEW capabilities Shop Control needs on top
of that board: technician-centric dispatch (not stage-centric), real
utilization, stalled-RO detection, and a composed bottleneck feed.

Technician Dispatch reuses `core/repair_orders.py`'s new
`assign_technician()` (a real, new mutation -- nothing in this codebase
could previously assign/reassign a technician to a live RO) for the actual
"drag a card onto a technician" action; this module's `get_dispatch_board()`
is just the real read side, grouped by technician instead of by stage.

Technician Utilization is a real computation over an ASSUMED daily-capacity
constant (`TECH_DAILY_CAPACITY_HOURS`, matching `core/service_overview.py`'s
own constant) -- no real time-clock/shift data exists anywhere in this
codebase to read a true capacity from, same HEURISTIC labeling as that
module's `techs_overloaded`. In fact this module IS the shared engine now:
`service_overview.get_todays_risks()`'s techs_overloaded reuses this
module's `get_technician_utilization()` rather than recomputing the same
thing a second way (see that module's own updated docstring).

Stalled RO Detection is Sam's own example, almost verbatim: "RO Open 9
Hours, No Labor Posted." A real check -- a live (non-Follow-Up) RO past
`STALLED_HOURS_THRESHOLD` hours since check-in with `LaborHours` still at
0 -- distinct from Overview's own `jobs_behind_schedule` (a longer,
24-hour "still not out the door" signal) by using a shorter threshold and a
narrower, more specific condition (no labor posted at all, not just "still
open").

Shop Bottlenecks composes three real signals rather than inventing a
fourth: Parts Delays (Parts-stage ROs with a real backordered
`parts_status`), Approval Delays (Customer-Approval-stage ROs that have sat
past the same behind-schedule threshold Overview uses), and Technician
Delays (this module's own stalled-RO check).
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD, EMPLOYEE
from core.repair_orders import _stage_of, _ro_brief, _hours_since_checkin

TECH_DAILY_CAPACITY_HOURS = 8.0
STALLED_HOURS_THRESHOLD = 9.0
APPROVAL_DELAY_HOURS_THRESHOLD = 24.0


def _now():
    return datetime.now(timezone.utc)


def _records():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]


def _service_technicians():
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE and e.attributes.get("Department") == "Service"
        and "Technician" in (e.attributes.get("Title") or "")
    ]


def _employee_name(emp):
    if not emp:
        return None
    return f"{emp.attributes.get('FirstName', '')} {emp.attributes.get('LastName', '')}".strip()


def get_dispatch_board():
    """Technician Dispatch Board -- every real, live (non-Follow-Up)
    ServiceRecord grouped by Technician instead of by stage, plus a real
    Unassigned column. Includes every real Service technician on the roster
    even if they currently have zero ROs assigned, so the dispatcher sees
    the whole team, not just whoever already has work."""

    records = [r for r in _records() if _stage_of(r) != "Follow-Up"]

    board = {}
    for tech in _service_technicians():
        board[tech.id] = {"name": _employee_name(tech), "repair_orders": []}

    unassigned = []
    for r in records:
        tech_id = r.attributes.get("Technician")
        if tech_id and tech_id in board:
            board[tech_id]["repair_orders"].append(_ro_brief(r))
        elif tech_id:
            # A technician assigned who isn't on the current Service roster
            # (e.g. a historical record's resolved employee id) -- still
            # real, still shown, just under its own id rather than silently
            # dropped.
            board.setdefault(tech_id, {"name": tech_id, "repair_orders": []})
            board[tech_id]["repair_orders"].append(_ro_brief(r))
        else:
            unassigned.append(_ro_brief(r))

    return {"technicians": board, "unassigned": unassigned}


def get_technician_utilization(date=None):
    """Real today's-(or given date's)-LaborHours booked per technician on
    live ROs, compared against an ASSUMED daily capacity -- HEURISTIC, no
    real time-clock/shift data exists anywhere in this codebase to read a
    true capacity from."""

    target_date = date or _now().date().isoformat()

    by_tech = {}
    for r in _records():
        if r.attributes.get("ServiceDate") != target_date:
            continue
        tech_id = r.attributes.get("Technician")
        if not tech_id:
            continue
        try:
            hours = float(r.attributes.get("LaborHours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        entry = by_tech.setdefault(tech_id, {"technician_id": tech_id, "ro_count": 0, "hours_booked": 0.0})
        entry["ro_count"] += 1
        entry["hours_booked"] += hours

    employees_by_id = {e.id: e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE}

    utilization = []
    for tech_id, entry in by_tech.items():
        emp = employees_by_id.get(tech_id)
        hours_booked = round(entry["hours_booked"], 1)
        utilization.append({
            "technician_id": tech_id,
            "name": _employee_name(emp) if emp else tech_id,
            "ro_count": entry["ro_count"],
            "hours_booked": hours_booked,
            "assumed_capacity_hours": TECH_DAILY_CAPACITY_HOURS,
            "utilization_pct": round(100 * hours_booked / TECH_DAILY_CAPACITY_HOURS, 1),
            "overloaded": hours_booked > TECH_DAILY_CAPACITY_HOURS,
        })

    utilization.sort(key=lambda u: u["utilization_pct"], reverse=True)

    return {
        "date": target_date,
        "technicians": utilization,
        "note": (
            f"HEURISTIC -- real LaborHours booked per technician on {target_date} vs. "
            f"an ASSUMED {TECH_DAILY_CAPACITY_HOURS}-hour/day capacity (no real time-"
            "clock/shift data exists anywhere in this codebase to read a true capacity from)."
        ),
    }


def get_stalled_ros(hours_threshold=STALLED_HOURS_THRESHOLD):
    """Sam's own example, almost verbatim: 'RO Open 9 Hours, No Labor
    Posted.' A real check, distinct from Overview's longer 24-hour
    jobs_behind_schedule signal -- shorter threshold, narrower condition
    (zero labor posted at all, not just 'still open')."""

    stalled = []
    for r in _records():
        if _stage_of(r) in ("Follow-Up",):
            continue
        hours = _hours_since_checkin(r)
        if hours is None or hours < hours_threshold:
            continue
        try:
            labor_hours = float(r.attributes.get("LaborHours") or 0)
        except (TypeError, ValueError):
            labor_hours = 0.0
        if labor_hours == 0:
            brief = _ro_brief(r)
            brief["hours_open"] = hours
            stalled.append(brief)

    stalled.sort(key=lambda r: r["hours_open"], reverse=True)

    return {"count": len(stalled), "repair_orders": stalled, "hours_threshold": hours_threshold}


def get_bottlenecks():
    """Shop Bottlenecks -- composes three real signals rather than a fourth
    parallel computation: Parts Delays, Approval Delays, and Technician
    Delays (this module's own stalled-RO check)."""

    records = _records()

    parts_delays = [
        _ro_brief(r) for r in records
        if _stage_of(r) == "Parts" and (r.attributes.get("parts_status") or {}).get("status") == "backordered"
    ]

    approval_delays = []
    for r in records:
        if _stage_of(r) != "Customer Approval":
            continue
        hours = _hours_since_checkin(r)
        if hours is not None and hours >= APPROVAL_DELAY_HOURS_THRESHOLD:
            brief = _ro_brief(r)
            brief["hours_open"] = hours
            approval_delays.append(brief)

    technician_delays = get_stalled_ros()

    return {
        "parts_delays": {"count": len(parts_delays), "repair_orders": parts_delays},
        "approval_delays": {
            "count": len(approval_delays),
            "repair_orders": approval_delays,
            "note": f"Customer-Approval-stage ROs open {APPROVAL_DELAY_HOURS_THRESHOLD}+ hours.",
        },
        "technician_delays": technician_delays,
    }
