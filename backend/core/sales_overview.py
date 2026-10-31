"""
Sales' "Overview" item -- the command center Sam's Sales sub-menu spec asks for:
"My Tasks Widget (Leads requiring contact today, Appointments arriving within 2
hours, Missing follow-ups, Unsold showroom visits, Deals awaiting manager approval),
Action Center (Call/Text/Email/Schedule Appointment/Create Deal/Transfer Lead per
item), Daily Sales Dashboard (salesperson: Today's Leads/Appointments/Shows/Demo
Drives/Write-Ups/Deliveries), Sales Manager Dashboard (Unworked Leads/Overdue Follow
Ups/Deals Stuck in F&I/Trades Awaiting Appraisal/Manager TO Needed)."

Session 94 follow-up, added ABOVE (not replacing) the existing generic Overview
KPI board per Sam's own scoping answer -- this is a second, personalized real-data
section, not a redesign of core/sales_menu.py's overview().

Reuses everything that already exists on the graph rather than inventing a parallel
model: core/lead_assignment.py's real ASSIGNED_TO relationship (with an honest
attribute-mirror fallback for the drift risk flagged in session 93) for "my leads",
core/field_notes.py's Communication Hub log for contact recency, core/lead_tasks.py's
real overdue-task detection, core/deals.py's real trade_in/financing_status/
funded_at fields, and core/bot_tasks.py's already-built infer_tier() to decide
whether the Sales Manager Dashboard section applies to this caller (a tier inferred
from Employee.Title, since this codebase has no separate "sales manager" role --
SALES covers both individual contributors and managers).

Manager Turn-Over (TO) is now real too (session 101 follow-up, core/manager_to.py)
-- the Sales Manager Dashboard's open_to_requests section reuses that engine
directly rather than a second computation, closing the last of the gaps this
module's own not_yet_tracked notes used to flag. Appointments (session 96) closed
the other one earlier. Both were part of the explicitly deferred "missing
workflows" list from Sam's original spec, worked through incrementally rather than
all at once.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD, DEAL

from core.lead_assignment import get_employee_leads
from core.lead_tasks import list_overdue_tasks
from core.field_notes import list_field_notes
from core.lead_record import COMMUNICATION_CATEGORIES
from core.workflow_tab_data import sales_fi_turnover_queue
from core.bot_tasks import infer_tier, TIER_MANAGER, TIER_EXECUTIVE
from core.manager_to_api import list_open_tos_api, get_to_stats_api
from core.permissions import ADMIN, OPERATIONS
from core.appointments import list_upcoming_within, list_todays, list_appointments as _list_appointments

AVAILABLE_ACTIONS = ["call", "text", "email", "create_deal", "transfer_lead", "schedule_appointment"]


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().date().isoformat()


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _days_since(ts):
    dt = _parse(ts)
    return (_now() - dt).days if dt else None


def _my_lead_ids(employee_id):
    """Union of the graph-native ASSIGNED_TO relationship (authoritative) and the
    Lead.AssignedSalesperson attribute (kept as a fallback so a lead assigned only
    through the older attribute-only path, e.g. at seed-import time, still shows up
    here -- see core/lead_assignment_api.py's module docstring for the same drift
    note)."""

    via_relationship = set(get_employee_leads(employee_id))
    via_attribute = {
        l.id for l in ledger.get_all().values()
        if l.entity_type == LEAD and l.attributes.get("AssignedSalesperson") == employee_id
    }
    return via_relationship | via_attribute


def _lead_brief(lead, last_contact=None, overdue_count=0):
    return {
        "id": lead.id,
        "name": f"{lead.attributes.get('FirstName', '')} {lead.attributes.get('LastName', '')}".strip(),
        "phone": lead.attributes.get("Phone"),
        "email": lead.attributes.get("Email"),
        "source": lead.attributes.get("Source"),
        "pipeline_state": lead.attributes.get("PipelineState"),
        "last_contact": last_contact,
        "overdue_task_count": overdue_count,
        "available_actions": AVAILABLE_ACTIONS,
    }


def get_my_tasks(role, employee_id):
    """The My Tasks Widget + Action Center, scoped to this employee's own leads."""

    lead_ids = _my_lead_ids(employee_id)
    leads = [ledger.get_entity(lid) for lid in lead_ids]
    leads = [l for l in leads if l and l.attributes.get("PipelineState") not in ("SOLD", "LOST")]

    upcoming_appts = list_upcoming_within(2, department="Sales", assigned_to=employee_id)

    needing_contact = []
    missing_follow_up = []
    unsold_showroom = []
    seen_action_items = {}

    for lead in leads:

        comms = [
            n for n in list_field_notes(linked_entity_id=lead.id, limit=200)
            if n.attributes.get("category") in COMMUNICATION_CATEGORIES
        ]
        last_contact = max((n.attributes.get("created_at") for n in comms), default=None)
        days_since_contact = _days_since(last_contact) if last_contact else None

        overdue = list_overdue_tasks(lead_id=lead.id)

        if not comms or (days_since_contact is not None and days_since_contact >= 1):
            brief = _lead_brief(lead, last_contact, len(overdue))
            needing_contact.append(brief)
            seen_action_items[lead.id] = brief

        if overdue:
            brief = seen_action_items.get(lead.id) or _lead_brief(lead, last_contact, len(overdue))
            missing_follow_up.append(brief)
            seen_action_items[lead.id] = brief

        if lead.attributes.get("PipelineState") == "VISITED":
            brief = seen_action_items.get(lead.id) or _lead_brief(lead, last_contact, len(overdue))
            unsold_showroom.append(brief)
            seen_action_items[lead.id] = brief

    return {
        "leads_requiring_contact_today": {"count": len(needing_contact), "items": needing_contact[:50]},
        "missing_follow_ups": {"count": len(missing_follow_up), "items": missing_follow_up[:50]},
        "unsold_showroom_visits": {"count": len(unsold_showroom), "items": unsold_showroom[:50]},
        "appointments_arriving_within_2_hours": {
            "count": len(upcoming_appts),
            "appointments": [
                {
                    "id": a.id, "appointment_type": a.attributes.get("appointment_type"),
                    "customer_id": a.attributes.get("customer_id"), "lead_id": a.attributes.get("lead_id"),
                    "scheduled_start": a.attributes.get("scheduled_start"), "status": a.attributes.get("status"),
                }
                for a in upcoming_appts
            ],
        },
        "action_center": {
            "count": len(seen_action_items),
            "items": list(seen_action_items.values())[:50],
        },
        "not_yet_tracked": {
            "deals_awaiting_manager_approval": "No manager-approval stage field exists on Deal yet.",
        },
    }


def get_daily_dashboard(role, employee_id):
    """Daily Sales Dashboard -- today's activity for this one salesperson."""

    today = _today()
    my_lead_ids = _my_lead_ids(employee_id)

    todays_leads = [
        l for l in ledger.get_all().values()
        if l.entity_type == LEAD and l.id in my_lead_ids
        and str(l.attributes.get("PipelineCreatedAt") or "").startswith(today)
    ]
    todays_shows = [
        l for l in ledger.get_all().values()
        if l.entity_type == LEAD and l.id in my_lead_ids
        and l.attributes.get("PipelineState") == "VISITED"
        and str(l.attributes.get("PipelineStateSince") or "").startswith(today)
    ]

    my_deals = [d for d in ledger.get_all().values() if d.entity_type == DEAL and d.attributes.get("created_by") == employee_id]
    write_ups_today = [d for d in my_deals if str(d.attributes.get("created_at") or "").startswith(today)]
    deliveries_today = [d for d in my_deals if str(d.attributes.get("funded_at") or "").startswith(today)]

    todays_appts = list_todays(department="Sales", assigned_to=employee_id)
    todays_demo_drives = [a for a in todays_appts if a.attributes.get("appointment_type") == "test_drive"]

    return {
        "todays_leads": {"count": len(todays_leads)},
        "todays_shows": {"count": len(todays_shows)},
        "todays_appointments": {"count": len(todays_appts)},
        "write_ups_today": {"count": len(write_ups_today)},
        "deliveries_today": {"count": len(deliveries_today)},
        "demo_drives": {"count": len(todays_demo_drives)},
        "not_yet_tracked": {},
    }


def get_manager_dashboard(role):
    """Sales Manager Dashboard -- team-wide, not scoped to one employee. Real data
    across the whole department, not a fabricated aggregate."""

    all_leads = [l for l in ledger.get_all().values() if l.entity_type == LEAD]
    unworked = [
        l for l in all_leads
        if l.attributes.get("PipelineState") == "NEW"
        and not list_field_notes(linked_entity_id=l.id, limit=1)
    ]

    overdue = list_overdue_tasks()

    all_deals = [d for d in ledger.get_all().values() if d.entity_type == DEAL]
    trades_awaiting_appraisal = [
        d for d in all_deals
        if d.attributes.get("trade_in") and not d.attributes["trade_in"].get("approved")
    ]

    open_tos = list_open_tos_api(role)
    to_stats = get_to_stats_api(role)

    return {
        "unworked_leads": {"count": len(unworked)},
        "overdue_follow_ups": {"count": len(overdue)},
        "deals_stuck_in_fi": sales_fi_turnover_queue(role),
        "trades_awaiting_appraisal": {
            "count": len(trades_awaiting_appraisal),
            "deals": [
                {"id": d.id, "customer_id": d.attributes.get("customer_id"), "vehicle_id": d.attributes.get("vehicle_id")}
                for d in trades_awaiting_appraisal
            ],
        },
        "open_to_requests": {
            "count": len(open_tos) if isinstance(open_tos, list) else 0,
            "requests": open_tos if isinstance(open_tos, list) else [],
            "stats": to_stats,
        },
        "not_yet_tracked": {},
    }


def get_my_day(role, employee_id):
    """Assembles the full Overview payload: My Tasks + Action Center (always),
    Daily Sales Dashboard (always, personal), and Sales Manager Dashboard (only if
    this employee's real Title infers to a manager/executive tier, or the caller is
    ADMIN/OPERATIONS)."""

    employee = ledger.get_entity(employee_id)
    tier = infer_tier(employee.attributes.get("Title") if employee else None)
    is_manager_view = role in (ADMIN, OPERATIONS) or tier in (TIER_MANAGER, TIER_EXECUTIVE)

    result = {
        "my_tasks": get_my_tasks(role, employee_id),
        "daily_dashboard": get_daily_dashboard(role, employee_id),
        "is_manager_view": is_manager_view,
    }

    if is_manager_view:
        result["manager_dashboard"] = get_manager_dashboard(role)

    return result
