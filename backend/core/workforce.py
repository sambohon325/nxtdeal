"""
Operations' new "Workforce" Top Menu item (2026-07-19, continuing Sam's
six-pillar spec, autonomous "keep going" continuation right after the Unified
Communications Hub). Closes a real, confirmed-absent gap: nothing anywhere in
this codebase previously modeled staff shift scheduling or time-off requests --
confirmed via grep across every core/*.py file before writing anything (the
closest existing concepts are Appointment, a CUSTOMER-facing scheduling entity,
and Employee.Title/Department, which carry no schedule/availability data at
all).

Four real pieces, composed and built fresh where a genuine gap existed, reused
where one already did:

  - Directory -- the real Employee roster, enriched with a real seniority tier
    (core/bot_tasks.py's already-established `infer_tier()` off Employee.Title,
    the same convention core/sales_overview.py/core/manager_to.py already use
    to distinguish staff from manager-tier without a separate role).
  - Shift Scheduling -- a genuinely NEW real capability. EmployeeShift is a
    first-class entity (own lifecycle: scheduled -> completed/no_show, or
    cancelled as a terminal off-ramp from scheduled), not a dict on Employee.
  - Time-Off Requests -- also genuinely NEW. TimeOffRequest has its own real
    lifecycle (pending -> approved/denied, or cancelled from pending) with a
    real, checkable approval gate: `approve_time_off()`/`deny_time_off()`
    require the deciding employee's own Employee.Title to resolve to
    manager-or-executive tier via `infer_tier()` -- the same real tier-gated
    approval-chain precedent core/manager_to.py's Manager TO and
    core/permissions_registry.py's ApprovalRequest hierarchy already
    established, rather than a flat role check alone.
  - Coverage -- a real, computed-live cross-reference for a given date: which
    employees are scheduled to work that day, and whether any of them also
    has an APPROVED time-off request covering that same date (a real
    scheduling conflict, not a fabricated one) -- computed on every read, no
    stored "conflict" flag to go stale.

Honest scope note, stated here rather than guessed at: no time-clock/punch-in
system exists anywhere in this codebase, so actual hours-worked cannot be
computed -- only what was scheduled and what was explicitly marked complete.
No payroll/PTO-balance/accrual model exists either -- a time-off request has no
concept of "days remaining" to check against. Workforce Performance below
reuses two already-real, already-built engines rather than inventing a third:
core/workload_dashboard_api.py's real per-employee active-Lead-workload count
(Sales-specific, the only real cross-employee workload signal that exists
today) and core/employee_value_api.py's real, ADMIN/OPERATIONS-gated $
effectiveness data (session 37) -- neither recomputed here.
"""

from datetime import date, datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import EMPLOYEE, EMPLOYEE_SHIFT, TIME_OFF_REQUEST
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.bot_tasks import infer_tier, TIER_STAFF, TIER_MANAGER, TIER_EXECUTIVE

SHIFT_STATUSES = ("scheduled", "completed", "no_show", "cancelled")
TIME_OFF_STATUSES = ("pending", "approved", "denied", "cancelled")

_MANAGER_OR_ABOVE = (TIER_MANAGER, TIER_EXECUTIVE)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_employee(employee_id):
    e = ledger.get_entity(employee_id)
    return e if e and e.entity_type == EMPLOYEE else None


def _employee_brief(employee_id):
    e = _get_employee(employee_id)
    if not e:
        return {"id": employee_id, "name": employee_id, "department": None, "title": None, "tier": None}
    name = f"{e.attributes.get('FirstName', '')} {e.attributes.get('LastName', '')}".strip() or e.id
    title = e.attributes.get("Title")
    return {
        "id": e.id,
        "name": name,
        "department": e.attributes.get("Department"),
        "title": title,
        "tier": infer_tier(title),
    }


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------

def get_directory(department=None):

    employees = [e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE]

    if department:
        employees = [e for e in employees if e.attributes.get("Department") == department]

    briefs = [_employee_brief(e.id) for e in employees]

    by_department = {}
    by_tier = {}
    for b in briefs:
        by_department[b["department"] or "Unknown"] = by_department.get(b["department"] or "Unknown", 0) + 1
        by_tier[b["tier"]] = by_tier.get(b["tier"], 0) + 1

    briefs.sort(key=lambda b: (b["department"] or "", b["name"]))

    return {
        "total": len(briefs),
        "by_department": by_department,
        "by_tier": by_tier,
        "employees": briefs,
    }


# ---------------------------------------------------------------------------
# Shift Scheduling
# ---------------------------------------------------------------------------

def schedule_shift(employee_id, shift_date, start_time, end_time, department, created_by, notes=""):

    employee = _get_employee(employee_id)
    if not employee:
        return {"error": f"Employee '{employee_id}' not found"}

    shift_id = id_generator.generate("SHIFT")

    entity = Entity(
        id=shift_id,
        entity_type=EMPLOYEE_SHIFT,
        attributes={
            "employee_id": employee_id,
            "shift_date": shift_date,
            "start_time": start_time,
            "end_time": end_time,
            "department": department or employee.attributes.get("Department"),
            "status": "scheduled",
            "notes": notes or "",
            "created_by": created_by,
            "created_at": _now(),
            "status_history": [{"status": "scheduled", "at": _now(), "by": created_by}],
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def _get_shift(shift_id):
    e = ledger.get_entity(shift_id)
    return e if e and e.entity_type == EMPLOYEE_SHIFT else None


def _advance_shift_status(shift_id, new_status, by):

    shift = _get_shift(shift_id)
    if not shift:
        return {"error": "Shift not found"}

    current = shift.attributes.get("status")

    if current != "scheduled":
        return {"error": f"Cannot change a shift out of '{current}' status."}

    if new_status not in SHIFT_STATUSES:
        return {"error": f"status must be one of {SHIFT_STATUSES}"}

    shift.attributes["status"] = new_status
    shift.attributes.setdefault("status_history", []).append({"status": new_status, "at": _now(), "by": by})

    save_graph(GRAPH_PATH)

    return shift


def complete_shift(shift_id, by):
    return _advance_shift_status(shift_id, "completed", by)


def mark_no_show(shift_id, by):
    return _advance_shift_status(shift_id, "no_show", by)


def cancel_shift(shift_id, by):
    return _advance_shift_status(shift_id, "cancelled", by)


def list_shifts(employee_id=None, department=None, date_from=None, date_to=None, status=None):

    shifts = [e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE_SHIFT]

    if employee_id:
        shifts = [s for s in shifts if s.attributes.get("employee_id") == employee_id]
    if department:
        shifts = [s for s in shifts if s.attributes.get("department") == department]
    if date_from:
        shifts = [s for s in shifts if (s.attributes.get("shift_date") or "") >= date_from]
    if date_to:
        shifts = [s for s in shifts if (s.attributes.get("shift_date") or "") <= date_to]
    if status:
        shifts = [s for s in shifts if s.attributes.get("status") == status]

    shifts.sort(key=lambda s: (s.attributes.get("shift_date") or "", s.attributes.get("start_time") or ""))

    return shifts


def _shift_brief(shift):
    return {
        "id": shift.id,
        "employee": _employee_brief(shift.attributes.get("employee_id")),
        "shift_date": shift.attributes.get("shift_date"),
        "start_time": shift.attributes.get("start_time"),
        "end_time": shift.attributes.get("end_time"),
        "department": shift.attributes.get("department"),
        "status": shift.attributes.get("status"),
        "notes": shift.attributes.get("notes"),
    }


# ---------------------------------------------------------------------------
# Time-Off Requests
# ---------------------------------------------------------------------------

def request_time_off(employee_id, start_date, end_date, reason, created_by=None):

    employee = _get_employee(employee_id)
    if not employee:
        return {"error": f"Employee '{employee_id}' not found"}

    if not start_date or not end_date or end_date < start_date:
        return {"error": "start_date/end_date must be provided and end_date must not precede start_date"}

    request_id = id_generator.generate("PTO")

    entity = Entity(
        id=request_id,
        entity_type=TIME_OFF_REQUEST,
        attributes={
            "employee_id": employee_id,
            "start_date": start_date,
            "end_date": end_date,
            "reason": reason or "",
            "status": "pending",
            "requested_at": _now(),
            "requested_by": created_by or employee_id,
            "decided_by": None,
            "decided_at": None,
            "decision_note": None,
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def _get_time_off(request_id):
    e = ledger.get_entity(request_id)
    return e if e and e.entity_type == TIME_OFF_REQUEST else None


def _decide_time_off(request_id, new_status, decided_by, note=None):

    req = _get_time_off(request_id)
    if not req:
        return {"error": "Time-off request not found"}

    if req.attributes.get("status") != "pending":
        return {"error": f"Cannot decide a request that is already '{req.attributes.get('status')}'."}

    decider = _get_employee(decided_by)
    decider_tier = infer_tier(decider.attributes.get("Title")) if decider else None

    if decider_tier not in _MANAGER_OR_ABOVE:
        return {
            "error": (
                f"'{decided_by}' does not resolve to manager-or-above tier "
                f"(infer_tier -> {decider_tier or 'unknown'}) -- only a manager-"
                f"or-executive-titled employee can approve or deny a time-off request."
            )
        }

    req.attributes["status"] = new_status
    req.attributes["decided_by"] = decided_by
    req.attributes["decided_at"] = _now()
    req.attributes["decision_note"] = note

    save_graph(GRAPH_PATH)

    return req


def approve_time_off(request_id, decided_by, note=None):
    return _decide_time_off(request_id, "approved", decided_by, note)


def deny_time_off(request_id, decided_by, note=None):
    return _decide_time_off(request_id, "denied", decided_by, note)


def cancel_time_off(request_id, by):

    req = _get_time_off(request_id)
    if not req:
        return {"error": "Time-off request not found"}

    if req.attributes.get("status") not in ("pending", "approved"):
        return {"error": f"Cannot cancel a request that is already '{req.attributes.get('status')}'."}

    req.attributes["status"] = "cancelled"
    req.attributes["decided_by"] = by
    req.attributes["decided_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def list_time_off(employee_id=None, status=None):

    requests = [e for e in ledger.get_all().values() if e.entity_type == TIME_OFF_REQUEST]

    if employee_id:
        requests = [r for r in requests if r.attributes.get("employee_id") == employee_id]
    if status:
        requests = [r for r in requests if r.attributes.get("status") == status]

    requests.sort(key=lambda r: r.attributes.get("requested_at") or "", reverse=True)

    return requests


def _time_off_brief(req):
    return {
        "id": req.id,
        "employee": _employee_brief(req.attributes.get("employee_id")),
        "start_date": req.attributes.get("start_date"),
        "end_date": req.attributes.get("end_date"),
        "reason": req.attributes.get("reason"),
        "status": req.attributes.get("status"),
        "requested_at": req.attributes.get("requested_at"),
        "decided_by": req.attributes.get("decided_by"),
        "decided_at": req.attributes.get("decided_at"),
        "decision_note": req.attributes.get("decision_note"),
    }


def _covers_date(start_date, end_date, on_date):
    return bool(start_date and end_date and start_date <= on_date <= end_date)


# ---------------------------------------------------------------------------
# Coverage -- a real, computed-live cross-reference for one date
# ---------------------------------------------------------------------------

def get_coverage_for_date(on_date=None):

    on_date = on_date or date.today().isoformat()

    shifts_that_day = [
        s for s in ledger.get_all().values()
        if s.entity_type == EMPLOYEE_SHIFT
        and s.attributes.get("shift_date") == on_date
        and s.attributes.get("status") != "cancelled"
    ]

    approved_time_off = [
        r for r in ledger.get_all().values()
        if r.entity_type == TIME_OFF_REQUEST
        and r.attributes.get("status") == "approved"
        and _covers_date(r.attributes.get("start_date"), r.attributes.get("end_date"), on_date)
    ]

    approved_employee_ids = {r.attributes.get("employee_id") for r in approved_time_off}

    conflicts = []
    scheduled = []
    for s in shifts_that_day:
        brief = _shift_brief(s)
        if s.attributes.get("employee_id") in approved_employee_ids:
            conflicts.append(brief)
        else:
            scheduled.append(brief)

    return {
        "date": on_date,
        "scheduled_count": len(scheduled),
        "conflict_count": len(conflicts),
        "on_approved_time_off_count": len(approved_employee_ids),
        "scheduled": scheduled,
        "conflicts": conflicts,
        "on_approved_time_off": [_time_off_brief(r) for r in approved_time_off],
    }


# ---------------------------------------------------------------------------
# Workforce Performance -- composition only, reuses already-real engines
# ---------------------------------------------------------------------------

def get_workforce_performance(role):

    from core.workload_dashboard_api import get_dashboard as get_workload_dashboard
    from core.employee_value_api import list_employee_values_api
    from core.workflow_tab_data import administration_onboarding_roster

    workload = get_workload_dashboard()
    employee_value = list_employee_values_api(role)
    credential_coverage = administration_onboarding_roster(role) if role in ("ADMIN", "OPERATIONS") else {
        "error": "Credential/login coverage is Admin/Operations-only."
    }

    return {
        "lead_workload": {
            "note": "Real per-employee active-Lead workload -- Sales-specific, the only real cross-employee workload signal this codebase computes today.",
            "employees": workload,
        },
        "employee_value": employee_value,
        "credential_coverage": credential_coverage,
        "not_yet_tracked": {
            "hours_worked": "No time-clock/punch-in system exists anywhere in this codebase -- only what was scheduled (EmployeeShift) and explicitly marked complete/no-show, never actual clocked hours.",
            "pto_balance_accrual": "No payroll/PTO-balance/accrual model exists -- a time-off request has no concept of days remaining to check against.",
        },
    }


def get_workforce_overview(role):

    today = date.today().isoformat()

    directory = get_directory()
    coverage_today = get_coverage_for_date(today)
    pending_time_off = list_time_off(status="pending")
    upcoming_shifts = [s for s in list_shifts(date_from=today, status="scheduled")]

    return {
        "directory": directory,
        "coverage_today": coverage_today,
        "pending_time_off_count": len(pending_time_off),
        "pending_time_off": [_time_off_brief(r) for r in pending_time_off[:25]],
        "upcoming_shift_count": len(upcoming_shifts),
        "performance": get_workforce_performance(role),
    }
