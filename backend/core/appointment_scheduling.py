"""
core/appointment_scheduling.py -- Appointments' "smart-scheduling upgrades",
the last item flagged open from Sam's original Service spec (session 96
built the real Appointment entity/calendar itself; this module adds the four
named upgrades on top of it: capacity planning, technician/rep matching,
automated customer communication, and pre-visit check-in). Shared across
Sales and Service, same "one generic entity, not per-department" convention
core/appointments.py itself already established.

Capacity Planning and Technician/Rep Matching are real, not simulated --
both are computed off real Appointment counts per employee per day against
a stated ASSUMED daily-capacity constant (HEURISTIC, no real shift/time-
clock data exists anywhere in this codebase to read a true capacity from,
same limitation class as core/shop_control.py's TECH_DAILY_CAPACITY_HOURS --
deliberately a DIFFERENT number/concept though: that module counts real
ServiceRecord.LaborHours already booked on live repair orders, this one
counts real Appointment slots, a different real-world thing). Matching is a
simple, honest least-loaded-first suggestion, the same class of algorithm
core/lead_routing.py already uses for lead assignment, not a fabricated
"AI-matched" scheme.

Automated Customer Communication is an honestly-labeled SIMULATED action --
no real SMS/email dispatch integration exists anywhere in this sandbox
(same precedent as core/campaigns.py's activate_campaign()/
core/social_posts.py's publish_post()) -- `send_appointment_reminder()`
stamps a real, stored reminder record on the Appointment itself
(`reminders_sent`, `basis="simulated_communication"`) rather than a fake
"delivered" status. Deliberately an on-demand action, not a background
scheduler -- this codebase has exactly two scheduler precedents
(bot_scheduler.py/compliance_scheduler.py), both narrow; a third recurring
job to auto-fire reminders X hours before an appointment is a real future
increment, not assumed here.

Pre-Visit Check-In is REAL and mirrors core/approval_center.py's public-link
mechanism exactly: a real unguessable token
(`secrets.token_urlsafe(24)`), a genuinely unauthenticated public read/write
pair, and an honest sentinel (`CUSTOMER_SENTINEL`) marking a decision as
customer-initiated rather than staff-recorded on their behalf. Submitting
check-in moves the appointment to "confirmed" via core/appointments.py's own
`update_status()` -- no second status mechanism.
"""

import secrets
from copy import deepcopy
from datetime import datetime, timezone, timedelta

from core.dealeros import ledger
from core.entity_types import EMPLOYEE, CUSTOMER, LEAD, VEHICLE
from core.appointments import (
    get_appointment, list_appointments, update_status,
    _TERMINAL_STATUSES, _now_iso,
)
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CUSTOMER_SENTINEL = "customer_via_checkin_link"

REMINDER_CHANNELS = ("sms", "email", "call")

ASSUMED_DAILY_CAPACITY = {
    "Sales": 8,
    "Service": 6,
}

DROP_OFF_OPTIONS = ("drop_off", "wait")
CHECKIN_LINK_LIFETIME = timedelta(days=7)
MAX_CHECKIN_CONTACT_LENGTH = 200
MAX_CHECKIN_NOTES_LENGTH = 2000


def _now():
    return datetime.now(timezone.utc)


def _employee_name(emp):
    if not emp:
        return None
    return f"{emp.attributes.get('FirstName', '')} {emp.attributes.get('LastName', '')}".strip()


def _employees_for_department(department):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == EMPLOYEE
        and (e.attributes.get("Department") or "").strip().lower() == department.strip().lower()
    ]


def _find_appointment_by_token(token):
    from core.entity_types import APPOINTMENT
    for e in ledger.get_all().values():
        if e.entity_type == APPOINTMENT:
            link = e.attributes.get("checkin_link")
            if link and link.get("token") == token:
                return e
    return None


def _checkin_link_expired(link):
    """Bound legacy links by issuance too; malformed dates never grant access."""
    try:
        issued = datetime.fromisoformat(link["created_at"])
        if issued.tzinfo is None:
            return True
        deadline = issued + CHECKIN_LINK_LIFETIME
        if "expires_at" in link:
            explicit = datetime.fromisoformat(link["expires_at"])
            if explicit.tzinfo is None:
                return True
            deadline = min(deadline, explicit)
        now = _now()
        return now < issued or now >= deadline
    except (KeyError, TypeError, ValueError, OverflowError):
        return True


def _linked_brief(appt):
    customer = ledger.get_entity(appt.attributes.get("customer_id")) if appt.attributes.get("customer_id") else None
    lead = ledger.get_entity(appt.attributes.get("lead_id")) if appt.attributes.get("lead_id") else None
    vehicle = ledger.get_entity(appt.attributes.get("vehicle_id")) if appt.attributes.get("vehicle_id") else None

    person = None
    if customer and customer.entity_type == CUSTOMER:
        person = f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip()
    elif lead and lead.entity_type == LEAD:
        person = f"{lead.attributes.get('FirstName', '')} {lead.attributes.get('LastName', '')}".strip()

    vehicle_desc = None
    if vehicle and vehicle.entity_type == VEHICLE:
        vehicle_desc = f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip()

    return {"person_name": person or None, "vehicle": vehicle_desc or None}


# --- Capacity Planning ---

def get_capacity_planning(department, date=None):
    if department not in ASSUMED_DAILY_CAPACITY:
        return {"error": f"department must be one of {list(ASSUMED_DAILY_CAPACITY.keys())}"}

    target_date = date or _now().date().isoformat()
    capacity = ASSUMED_DAILY_CAPACITY[department]

    appts = [
        a for a in list_appointments(department=department, date=target_date)
        if a.attributes.get("status") not in ("cancelled", "no_show")
    ]

    by_employee = {}
    for a in appts:
        emp_id = a.attributes.get("assigned_to")
        if not emp_id:
            continue
        by_employee.setdefault(emp_id, []).append(a)

    employees = _employees_for_department(department)
    employees_by_id = {e.id: e for e in employees}

    rows = []
    seen = set()
    for emp_id, emp in employees_by_id.items():
        booked = len(by_employee.get(emp_id, []))
        rows.append({
            "employee_id": emp_id,
            "name": _employee_name(emp),
            "title": emp.attributes.get("Title"),
            "booked_count": booked,
            "capacity": capacity,
            "available_slots": max(0, capacity - booked),
            "at_capacity": booked >= capacity,
        })
        seen.add(emp_id)

    # An employee assigned who isn't on the current department roster (e.g. a
    # resolved historical id) -- still real, still shown, not silently dropped.
    for emp_id, appt_list in by_employee.items():
        if emp_id in seen:
            continue
        rows.append({
            "employee_id": emp_id,
            "name": emp_id,
            "title": None,
            "booked_count": len(appt_list),
            "capacity": capacity,
            "available_slots": max(0, capacity - len(appt_list)),
            "at_capacity": len(appt_list) >= capacity,
        })

    rows.sort(key=lambda r: r["available_slots"], reverse=True)

    total_booked = sum(r["booked_count"] for r in rows)
    total_capacity = sum(r["capacity"] for r in rows) or capacity

    return {
        "department": department,
        "date": target_date,
        "assumed_daily_capacity_per_employee": capacity,
        "employees": rows,
        "total_booked": total_booked,
        "total_capacity": total_capacity,
        "pct_booked": round(100 * total_booked / total_capacity, 1) if total_capacity else 0.0,
        "note": (
            f"HEURISTIC -- real Appointment counts per employee on {target_date} vs. an "
            f"ASSUMED {capacity}/day capacity (no real shift/time-clock data exists "
            "anywhere in this codebase to read a true capacity from)."
        ),
    }


# --- Technician / Rep Matching ---

def suggest_assignee(department, date=None):
    plan = get_capacity_planning(department, date=date)
    if "error" in plan:
        return plan

    if not plan["employees"]:
        return {"error": f"No {department} employees on file to match against"}

    best = plan["employees"][0]

    return {
        "department": department,
        "date": plan["date"],
        "recommended_employee_id": best["employee_id"],
        "name": best["name"],
        "booked_count": best["booked_count"],
        "capacity": best["capacity"],
        "available_slots": best["available_slots"],
        "at_capacity": best["at_capacity"],
        "note": (
            "Least-loaded-first suggestion off real Appointment counts for this date -- "
            "not an AI match, a simple honest heuristic, same class of algorithm "
            "core/lead_routing.py already uses for lead assignment."
            if not best["at_capacity"] else
            "Every employee is at or over the assumed daily capacity for this date -- "
            "this is still the least-loaded option."
        ),
    }


# --- Automated Customer Communication (SIMULATED) ---

def send_appointment_reminder(appointment_id, channel, sent_by):
    appt = get_appointment(appointment_id)
    if not appt:
        return {"error": "Appointment not found"}
    if channel not in REMINDER_CHANNELS:
        return {"error": f"channel must be one of {REMINDER_CHANNELS}"}
    if appt.attributes.get("status") in _TERMINAL_STATUSES:
        return {"error": f"Appointment is already '{appt.attributes.get('status')}' -- no reminder needed"}

    reminder = {
        "channel": channel,
        "sent_by": sent_by,
        "sent_at": _now_iso(),
        "basis": "simulated_communication",
    }
    previous = deepcopy(appt.attributes)
    appt.attributes.setdefault("reminders_sent", []).append(reminder)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return {
        "appointment_id": appointment_id,
        "reminders_sent": appt.attributes["reminders_sent"],
        "disclaimer": "SIMULATED -- no real SMS/email/phone dispatch is connected in this environment; this records that a reminder was triggered, it does not actually deliver one.",
    }


def get_reminder_history(appointment_id):
    appt = get_appointment(appointment_id)
    if not appt:
        return {"error": "Appointment not found"}
    return {"appointment_id": appointment_id, "reminders_sent": appt.attributes.get("reminders_sent", [])}


# --- Pre-Visit Check-In ---

def generate_checkin_link(appointment_id, created_by):
    appt = get_appointment(appointment_id)
    if not appt:
        return {"error": "Appointment not found"}
    if appt.attributes.get("status") in _TERMINAL_STATUSES:
        return {"error": f"Appointment is already '{appt.attributes.get('status')}' -- can't generate a check-in link"}

    token = secrets.token_urlsafe(24)
    previous = deepcopy(appt.attributes)
    appt.attributes["checkin_link"] = {
        "token": token,
        "created_by": created_by,
        "created_at": _now_iso(),
        "expires_at": (_now() + CHECKIN_LINK_LIFETIME).isoformat(),
        "revoked": False,
    }
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return {"appointment_id": appointment_id, "token": token, "path": f"/checkin/{token}"}


def get_checkin_link_status(appointment_id):
    appt = get_appointment(appointment_id)
    if not appt:
        return {"error": "Appointment not found"}

    link = appt.attributes.get("checkin_link")
    if not link:
        return {"appointment_id": appointment_id, "exists": False}

    return {"appointment_id": appointment_id, "exists": True, **link, "path": f"/checkin/{link['token']}"}


def revoke_checkin_link(appointment_id, revoked_by):
    appt = get_appointment(appointment_id)
    if not appt:
        return {"error": "Appointment not found"}

    link = appt.attributes.get("checkin_link")
    if not link:
        return {"error": "No check-in link exists for this appointment"}
    if link.get("revoked"):
        return {"error": "This check-in link is already revoked"}

    previous = deepcopy(appt.attributes)
    link["revoked"] = True
    link["revoked_by"] = revoked_by
    link["revoked_at"] = _now_iso()
    appt.attributes["checkin_link"] = link
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return {"appointment_id": appointment_id, "revoked": True}


def get_public_checkin_view(token):
    """PUBLIC, unauthenticated -- same /public/* convention as
    core/approval_center.py's get_public_approval_view()."""

    appt = _find_appointment_by_token(token)
    if not appt:
        return {"error": "This check-in link is invalid or has expired."}

    link = appt.attributes["checkin_link"]
    if link.get("revoked"):
        return {"error": "This check-in link has been revoked. Please contact the dealership."}
    if _checkin_link_expired(link):
        return {"error": "This check-in link has expired. Please contact the dealership."}
    brief = _linked_brief(appt)

    return {
        "revoked": link.get("revoked", False),
        "department": appt.attributes.get("department"),
        "appointment_type": appt.attributes.get("appointment_type"),
        "scheduled_start": appt.attributes.get("scheduled_start"),
        "status": appt.attributes.get("status"),
        "person_name": brief["person_name"],
        "vehicle": brief["vehicle"],
        "checkin": appt.attributes.get("checkin"),
    }


def record_public_checkin(token, drop_off_or_wait, contact_preference="", notes=""):
    """PUBLIC, unauthenticated -- the real customer-initiated pre-visit
    check-in. Confirms the appointment via core/appointments.py's own
    update_status(), recorded with CUSTOMER_SENTINEL, an honest, distinct
    marker from any real employee id -- same precedent
    core/approval_center.py's CUSTOMER_SENTINEL established."""

    appt = _find_appointment_by_token(token)
    if not appt:
        return {"error": "This check-in link is invalid or has expired."}

    link = appt.attributes["checkin_link"]
    if link.get("revoked"):
        return {"error": "This check-in link has been revoked. Please contact the dealership."}

    if _checkin_link_expired(link):
        return {"error": "This check-in link has expired. Please contact the dealership."}

    if appt.attributes.get("checkin"):
        return {"error": "You've already checked in for this appointment."}

    if appt.attributes.get("status") in _TERMINAL_STATUSES:
        return {"error": f"This appointment is already '{appt.attributes.get('status')}' -- check-in is no longer available."}

    if drop_off_or_wait not in DROP_OFF_OPTIONS:
        return {"error": f"drop_off_or_wait must be one of {DROP_OFF_OPTIONS}"}

    for value, limit, label in (
        (contact_preference, MAX_CHECKIN_CONTACT_LENGTH, "Contact preference"),
        (notes, MAX_CHECKIN_NOTES_LENGTH, "Visit notes"),
    ):
        if not isinstance(value, str) or len(value) > limit:
            return {"error": f"{label} must be text of at most {limit} characters."}

    previous = deepcopy(appt.attributes)
    appt.attributes["checkin"] = {
        "drop_off_or_wait": drop_off_or_wait,
        "contact_preference": contact_preference or "",
        "notes": notes or "",
        "submitted_at": _now_iso(),
        "submitted_by": CUSTOMER_SENTINEL,
    }
    try:
        if appt.attributes.get("status") == "scheduled":
            # The canonical transition persists the check-in and confirmation
            # together, rather than leaving a durable half-completed check-in.
            result = update_status(appt.id, "confirmed", CUSTOMER_SENTINEL)
            if isinstance(result, dict) and "error" in result:
                appt.attributes = previous
                return result
        else:
            save_graph(GRAPH_PATH)
    except Exception:
        appt.attributes = previous
        raise

    return get_public_checkin_view(token)
