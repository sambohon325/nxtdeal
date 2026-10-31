"""
core/sales_menu.py -- real data behind Sales' 8-item Top Menu (core/menu_catalog.py),
session 60 continuation. Sam: "lets move to sales" once Operations' Top Menu was fully
wired and confirmed working. Same discipline as core/operations_menu.py: reuse an
already-built function wherever it's a genuine match, compute a small new real
aggregate where the graph has the underlying data but nobody had queried it this way
yet, and use an honest `not_yet_tracked` note (never a fabricated number) wherever
sales.pdf asks for something this data model doesn't back at all. Appointments (session
96) and Communications' unified inbox (session 98, real Communication Hub log
aggregation) closed the two biggest original gaps here -- core/messaging.py's internal
employee messaging remains a genuinely different thing from customer-facing comms and
is still never conflated with it. Inventory (session 99, core/vehicle_holds.py's real
Reservation/Hold mechanism + a real side-by-side comparison tool) closed the last of
the original 8-submenu gaps -- all 8 of Sales' Top Menu items are now real, not a
generic JSON dump.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE, FINANCE_CONTRACT, SERVICE_RECORD
from core.relationship_types import AUTHORIZED, FINANCED_BY, OWNS

from core.workflow_tab_data import (
    sales_desking_pipeline,
    sales_fi_turnover_queue,
    sales_delivery_queue,
    marketing_database_mining,
    inventory_auction_acquisition,
)
from core.workflow_dashboard import get_lead_pipeline_dashboard
from core.follow_up_dashboard import get_follow_up_dashboard
from core.leaderboard_api import get_dashboard as get_leaderboard
from core.compliance_api import list_alerts_api
from core.data_connections_api import readiness_predictions_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.lead_record import get_lead_record
from core.trigger_alerts_api import get_alert_feed_api
from core.appointments import list_todays, list_this_week, list_appointments as _list_appointments
from core.manager_dashboard import get_manager_dashboard as _get_manager_lead_metrics
from core.sales_overview import get_manager_dashboard as _get_manager_operational_gaps
from core.field_notes import list_field_notes
from core.lead_record import COMMUNICATION_CATEGORIES
from core.vehicle_holds import get_active_hold

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Sales maps
# cleanly onto Department Intelligence's real "sales" KPI key.
from core.department_intelligence_api import get_department_api

# Newly-built Sales modules (2026-07-23 integration pass) -- thin role-gated
# pass-throughs, mirroring operations_menu.customer_journey.
from core.accessories_api import get_accessories_overview_api
from core.equity_center_api import get_equity_overview_api


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _funded_deal_gross(deals):
    """Front-end gross for a list of funded Deals -- real sum(Vehicle.Price -
    Vehicle.Cost) for each deal's vehicle, the same computation
    core/employee_value.py's sales attribution already relies on elsewhere."""

    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    total = 0.0
    for deal in deals:
        vehicle = vehicles_by_id.get(deal.attributes.get("vehicle_id"))
        if vehicle:
            total += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))
    return total


LEAD_SOURCE_BUCKETS = {
    "Internet Leads": {"Website", "Autotrader", "Cars.com", "CarGurus", "Facebook Marketplace"},
    "Phone Leads": {"Phone Inquiry"},
    "Walk-In Traffic": {"Walk-In"},
    "Referral": {"Referral"},
    "Trade Show": {"Trade Show"},
    "Service Drive": {"Service Drive"},
}


def overview(role):
    """sales.pdf's "Overview" item: the Sales command center. Today's Appointments is
    real as of session 96 (core/appointments.py) -- CSI Risk Alerts still has no
    backing data model in this codebase (no customer-satisfaction survey entity
    exists), said so explicitly rather than guessed."""

    pipeline = get_lead_pipeline_dashboard()
    followup = get_follow_up_dashboard()
    delivery = sales_delivery_queue(role)
    fi_turnover = sales_fi_turnover_queue(role)
    leaderboard = get_leaderboard()

    funded_deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]
    gross_profit = _funded_deal_gross(funded_deals)

    active_opportunities = sum(count for state, count in pipeline.items() if state != "LOST")
    avg_conversion = round(sum(e["conversion_rate"] for e in leaderboard) / len(leaderboard), 3) if leaderboard else None

    todays_appointments = list_todays(department="Sales")

    return {
        "active_opportunities": active_opportunities,
        "leads_awaiting_response": len(followup),
        "deliveries_scheduled": delivery.get("count"),
        "fi_pending": fi_turnover.get("count"),
        "gross_profit_funded_deals": round(gross_profit, 2),
        "closing_ratio_avg": avg_conversion,
        "pipeline_by_stage": pipeline,
        "todays_appointments": {"count": len(todays_appointments)},
        "not_yet_tracked": {
            "csi_risk_alerts": "No customer-satisfaction survey data model exists yet.",
        },
    }


def prospects(role, query=None):
    """sales.pdf's "Prospects" item: a CRM-style lead center, bucketed by real Lead
    Source values, plus the real equity-mining candidates (reused from
    marketing.database_mining) as the "Equity Customers" bucket. A query of an exact
    LEAD- id returns the full Lead Record (session 92 follow-up, core/lead_record.py)
    -- Customer Profile, Activity Timeline, Communication Hub log, Task Management,
    Notes, Next Best Action -- same "CUST- id opens the full record" pattern
    customers() below already established. Free-text queries still do a plain search."""

    leads = _entities(LEAD)

    if query and query.upper().startswith("LEAD-"):
        return get_lead_record(role, query.upper())

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] == LEAD]
        return {"query": query, "count": len(results), "results": results}

    by_source_bucket = {
        bucket: len([l for l in leads if l.attributes.get("Source") in sources])
        for bucket, sources in LEAD_SOURCE_BUCKETS.items()
    }

    lost = [l for l in leads if l.attributes.get("PipelineState") == "LOST"]
    unsold_showroom_traffic = [l for l in leads if l.attributes.get("PipelineState") == "VISITED"]
    unassigned = [l for l in leads if not l.attributes.get("AssignedSalesperson")]

    return {
        "total_leads": len(leads),
        "by_source_bucket": by_source_bucket,
        "lost_opportunities": {"count": len(lost)},
        "unsold_showroom_traffic": {"count": len(unsold_showroom_traffic)},
        "needing_assignment": {"count": len(unassigned)},
        "equity_customers": marketing_database_mining(role),
        "not_yet_tracked": {
            "lead_scoring": "No lead-scoring model exists yet.",
            "ai_generated_recommendations": "No recommendation engine exists yet.",
        },
    }


def _relationships_from(entity_id, relationship_type):
    return [
        r for r in ledger.get_relationships()
        if r.source_id == entity_id and r.relationship_type == relationship_type
    ]


def _customer_360(customer_id):
    """Session 95 follow-up (Sales sub-menu spec, Customers item): a real grouped
    Customer 360 -- Purchase History (Deal.customer_id is an attribute, not a
    relationship, same lookup deals() above already uses), Service History
    (AUTHORIZED), Finance Contracts (FINANCED_BY), Vehicles Owned (OWNS) -- rather
    than the old flat, ungrouped one-hop related_entities dump."""

    deals = [d for d in _entities(DEAL) if d.attributes.get("customer_id") == customer_id]
    service_records = [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, AUTHORIZED)
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == SERVICE_RECORD
    ]
    finance_contracts = [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, FINANCED_BY)
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == FINANCE_CONTRACT
    ]
    vehicles_owned = [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, OWNS)
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == VEHICLE
    ]

    return {
        "purchase_history": {
            "count": len(deals),
            "deals": [
                {"id": d.id, "status": d.attributes.get("status"), "vehicle_id": d.attributes.get("vehicle_id"), "funded_at": d.attributes.get("funded_at")}
                for d in deals
            ],
        },
        "service_history": {
            "count": len(service_records),
            "records": [
                {"id": s.id, "service_date": s.attributes.get("ServiceDate"), "description": s.attributes.get("Description"), "technician": s.attributes.get("Technician")}
                for s in service_records
            ],
        },
        "finance_contracts": {
            "count": len(finance_contracts),
            "contracts": [
                {"id": f.id, "contract_date": f.attributes.get("ContractDate"), "term_months": f.attributes.get("TermMonths"), "lender_id": f.attributes.get("lender_id")}
                for f in finance_contracts
            ],
        },
        "vehicles_owned": {
            "count": len(vehicles_owned),
            "vehicles": [
                {"id": v.id, "vin": v.attributes.get("VIN"), "year": v.attributes.get("Year"), "make": v.attributes.get("Make"), "model": v.attributes.get("Model")}
                for v in vehicles_owned
            ],
        },
    }


def customers(role, query=None):
    """sales.pdf's "Customers" item: customer-centric search by name/email/phone/VIN/
    stock number, returning the full record plus a real grouped 360 view (Purchase
    History, Service History, Finance Contracts, Vehicles Owned), plus -- session 95
    follow-up -- Equity Mining and a Retention Center on the default view, both real
    data reused directly from core/trigger_alerts.py's Timeline engine (session 84)
    rather than a second parallel signal-detection pass: Equity Mining is that
    Timeline's equity_mining alert type, Retention Center is every open
    customer-typed alert (lease/loan maturity, service win-back, open recalls)."""

    if not query:
        recent = sorted(_entities(CUSTOMER), key=lambda c: c.id, reverse=True)[:20]
        retention_alerts = get_alert_feed_api(role, status="new", target_entity_type=CUSTOMER)
        equity_alerts = [a for a in retention_alerts if a.get("alert_type") == "equity_mining"]
        retention_alerts = [a for a in retention_alerts if a.get("alert_type") != "equity_mining"]
        return {
            "default_view": "recent_customers",
            "customers": [
                {
                    "id": c.id,
                    "name": f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')}".strip(),
                    "email": c.attributes.get("Email"),
                    "phone": c.attributes.get("Phone"),
                }
                for c in recent
            ],
            "equity_mining": {"count": len(equity_alerts), "alerts": equity_alerts},
            "retention_center": {"count": len(retention_alerts), "alerts": retention_alerts},
        }

    if query.upper().startswith("CUST-"):
        entity = get_entity_by_id(role, query.upper())
        if "error" in entity:
            return entity
        related = get_related_entities(role, query.upper())
        return {"customer": entity, "related_entities": related, "customer_360": _customer_360(query.upper())}

    results = [r for r in search_entities(role, query) if r["entity_type"] == CUSTOMER]
    return {"query": query, "count": len(results), "results": results}


def deals(role):
    """sales.pdf's "Deals" item: the deal desk shortcut. Pending Trade Evaluation and
    Pending Manager Approval have no backing status field in this data model yet (no
    seeded trade-in data, no manager-approval stage) -- said so rather than guessed."""

    all_deals = _entities(DEAL)

    working = sales_desking_pipeline(role)
    pending_delivery = [d for d in all_deals if d.attributes.get("status") == "contract"]
    awaiting_credit_approval = [d for d in all_deals if d.attributes.get("financing_status") == "submitted"]
    pending_trade_eval = [d for d in all_deals if d.attributes.get("trade_in")]
    delivered = [d for d in all_deals if d.attributes.get("status") == "funded"]

    def _brief(d):
        return {
            "id": d.id,
            "customer_id": d.attributes.get("customer_id"),
            "vehicle_id": d.attributes.get("vehicle_id"),
            "status": d.attributes.get("status"),
            "financing_status": d.attributes.get("financing_status"),
        }

    return {
        "working_deals": working,
        "pending_delivery": {"count": len(pending_delivery), "deals": [_brief(d) for d in pending_delivery]},
        "awaiting_credit_approval": {"count": len(awaiting_credit_approval), "deals": [_brief(d) for d in awaiting_credit_approval]},
        "pending_trade_evaluation": {"count": len(pending_trade_eval), "deals": [_brief(d) for d in pending_trade_eval]},
        "delivered_deals": {"count": len(delivered), "deals": [_brief(d) for d in delivered]},
        "not_yet_tracked": {
            "pending_manager_approval": "No manager-approval stage field exists on Deal yet.",
        },
    }


def _appointment_brief(a):
    return {
        "id": a.id,
        "appointment_type": a.attributes.get("appointment_type"),
        "customer_id": a.attributes.get("customer_id"),
        "lead_id": a.attributes.get("lead_id"),
        "assigned_to": a.attributes.get("assigned_to"),
        "scheduled_start": a.attributes.get("scheduled_start"),
        "status": a.attributes.get("status"),
    }


def appointments(role):
    """sales.pdf's "Appointments" item: sales calendar / showroom traffic center.
    Deliveries and Showroom Traffic are real, derived from real Deal status and Lead
    pipeline state (unchanged). Today's/This Week's appointments, salesperson
    calendars, test drives, and no-show tracking are real as of session 96
    (core/appointments.py) -- the single most-repeated "not_yet_tracked" gap in this
    codebase, now closed here."""

    leads = _entities(LEAD)
    today = datetime.now(timezone.utc).date().isoformat()

    showroom_today = [
        l for l in leads
        if l.attributes.get("PipelineState") == "VISITED" and str(l.attributes.get("PipelineStateSince")) == today
    ]
    showroom_all = [l for l in leads if l.attributes.get("PipelineState") == "VISITED"]

    todays_appts = list_todays(department="Sales")
    weeks_appts = list_this_week(department="Sales")
    test_drives = _list_appointments(department="Sales", appointment_type="test_drive")
    no_shows = _list_appointments(department="Sales", status="no_show")

    calendars = {}
    for a in weeks_appts:
        assignee = a.attributes.get("assigned_to") or "unassigned"
        calendars.setdefault(assignee, []).append(_appointment_brief(a))

    return {
        "deliveries": sales_delivery_queue(role),
        "showroom_traffic_today": {"count": len(showroom_today)},
        "showroom_traffic_all_visited": {"count": len(showroom_all)},
        "todays_appointments": {"count": len(todays_appts), "appointments": [_appointment_brief(a) for a in todays_appts]},
        "this_weeks_schedule": {"count": len(weeks_appts), "appointments": [_appointment_brief(a) for a in weeks_appts]},
        "salesperson_calendars": calendars,
        "test_drives": {"count": len(test_drives), "appointments": [_appointment_brief(a) for a in test_drives]},
        "no_show_tracking": {"count": len(no_shows), "appointments": [_appointment_brief(a) for a in no_shows]},
    }


def _vehicle_brief(v):
    """A vehicle summary tagged with real Reservation/Hold status
    (core/vehicle_holds.py) -- used across Inventory's browse, payment-search, and
    text-search modes so a rep sees "this one's spoken for" wherever they encounter
    a vehicle, not just on a dedicated holds screen."""

    hold = get_active_hold(v.id)

    return {
        "id": v.id,
        "vin": v.attributes.get("VIN"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "trim": v.attributes.get("Trim"),
        "price": v.attributes.get("Price"),
        "on_hold": bool(hold),
        "held_by": hold.attributes.get("held_by") if hold else None,
        "hold_expires_at": hold.attributes.get("expires_at") if hold else None,
    }


def inventory(role, query=None):
    """sales.pdf's "Inventory" item: a sales-facing browser (not management). Payment-
    based search is a real amortization calculation (60mo/7.9% APR assumption,
    explicitly labeled as an estimate) over real unsold-vehicle prices, not a
    fabricated match -- type a plain number (a target monthly payment) to use it, or
    text (make/model) for a normal search. Every vehicle returned (browse, payment
    search, text search) carries real Reservation/Hold status -- see _vehicle_brief."""

    unsold = [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold")]
    sold_recent = sorted(
        [v for v in _entities(VEHICLE) if v.attributes.get("DateSold")],
        key=lambda v: v.attributes.get("DateSold") or "",
        reverse=True,
    )[:20]

    if query and query.strip():
        q = query.strip()

        if q.replace(".", "", 1).isdigit():
            monthly_payment = float(q)
            annual_rate = 0.079
            term_months = 60
            monthly_rate = annual_rate / 12
            max_price = monthly_payment * (1 - (1 + monthly_rate) ** -term_months) / monthly_rate

            matches = [v for v in unsold if _safe_float(v.attributes.get("Price")) <= max_price]

            return {
                "mode": "payment_based_search",
                "target_monthly_payment": monthly_payment,
                "assumptions": {"term_months": term_months, "apr": annual_rate},
                "estimated_max_price": round(max_price, 2),
                "count": len(matches),
                "vehicles": [_vehicle_brief(v) for v in matches[:50]],
                "note": "ESTIMATE: assumes a 60-month term at 7.9% APR -- not a real credit-approved quote.",
            }

        results = [r for r in search_entities(role, q) if r["entity_type"] == VEHICLE]

        for r in results:
            hold = get_active_hold(r["id"])
            r["on_hold"] = bool(hold)
            r["held_by"] = hold.attributes.get("held_by") if hold else None
            r["hold_expires_at"] = hold.attributes.get("expires_at") if hold else None

        return {"mode": "text_search", "query": q, "count": len(results), "results": results}

    return {
        "available_count": len(unsold),
        "vehicles": [_vehicle_brief(v) for v in unsold[:100]],
        "incoming": inventory_auction_acquisition(role),
        "recently_sold": [
            {"id": v.id, "vin": v.attributes.get("VIN"), "date_sold": v.attributes.get("DateSold")}
            for v in sold_recent
        ],
        "not_yet_tracked": {
            "customer_match_suggestions": "No customer-preference/match-scoring model exists yet.",
        },
    }


def compare_vehicles(role, vehicle_ids):
    """Real side-by-side comparison -- sales.pdf's "Comparison Tool." No new data
    model needed: full real attributes for each requested vehicle
    (core/ai_tools.py's get_entity_by_id, same role-filtered access as GET
    /entity/{id}), capped at 4 vehicles (a side-by-side comparison stops being
    readable past that), plus real Reservation/Hold status on each."""

    if not vehicle_ids:
        return {"error": "At least one vehicle id is required"}

    ids = [v.strip() for v in vehicle_ids if v and v.strip()][:4]
    vehicles = []
    errors = []

    for vid in ids:
        result = get_entity_by_id(role, vid)

        if isinstance(result, dict) and "error" in result:
            errors.append({"id": vid, "error": result["error"]})
            continue

        if result.get("entity_type") != VEHICLE:
            errors.append({"id": vid, "error": "Not a vehicle"})
            continue

        hold = get_active_hold(vid)
        vehicles.append({
            "id": result["id"],
            "attributes": result["attributes"],
            "on_hold": bool(hold),
            "held_by": hold.attributes.get("held_by") if hold else None,
        })

    return {"count": len(vehicles), "vehicles": vehicles, "errors": errors}


def _lead_or_customer_name(entity_id):
    entity = ledger.get_entity(entity_id) if entity_id else None
    if not entity or entity.entity_type not in (LEAD, CUSTOMER):
        return None
    return f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip() or entity_id


def _unified_inbox(limit=100):
    """Session 98 follow-up: the real Communication Hub log (call/text/email/video
    FieldNotes, built for Prospects in session 92) aggregated across every lead in
    the department -- a real unified inbox, not the fabricated placeholder the old
    docstring here used to claim didn't exist. Honest framing, not overclaimed: this
    is a real, staff-entered log of what happened on each touch (core/field_notes.py's
    established quick-log mechanism), not an automated call-recording/SMS/email-
    provider integration -- this codebase has no telephony/SMS/email-provider
    connection anywhere."""

    notes = list_field_notes(department="Sales", limit=1000)
    comms = [n for n in notes if n.attributes.get("category") in COMMUNICATION_CATEGORIES]

    by_channel = {}
    for n in comms:
        category = n.attributes.get("category")
        by_channel[category] = by_channel.get(category, 0) + 1

    items = []
    for n in comms[:limit]:
        linked_id = n.attributes.get("linked_entity_id")
        items.append({
            "id": n.id,
            "category": n.attributes.get("category"),
            "body": n.attributes.get("body"),
            "linked_entity_id": linked_id,
            "linked_entity_name": _lead_or_customer_name(linked_id),
            "created_by": n.attributes.get("created_by"),
            "created_at": n.attributes.get("created_at"),
        })

    return {"total": len(comms), "by_channel": by_channel, "items": items}


def communications(role):
    """sales.pdf's "Communications" item: a unified comms hub. The real Communication
    Hub log built for Prospects (session 92) now backs a real unified inbox here
    (session 98) -- see _unified_inbox()'s docstring for the honest "staff-logged,
    not automated" framing. The follow-up cadence queue (who's overdue for outreach)
    and marketing-compliance alerts (CAN-SPAM/TCPA, core/compliance_rules.py) remain
    the other two real signals. Only message read-tracking has no backing data model
    at all -- said so rather than guessed. Mass messaging/templates are Marketing's
    Email/SMS CRM (core/email_templates.py), reused rather than duplicated here."""

    followup = get_follow_up_dashboard()
    for item in followup:
        item["name"] = _lead_or_customer_name(item.get("lead_id"))

    alerts = list_alerts_api(role, status=None)

    marketing_alerts = []
    if isinstance(alerts, dict) and "alerts" in alerts:
        marketing_alerts = [a for a in alerts["alerts"] if a.get("category") == "marketing"]

    return {
        "unified_inbox": _unified_inbox(),
        "follow_up_cadence_queue": {"count": len(followup), "items": followup[:50]},
        "compliance_logs": {"count": len(marketing_alerts), "alerts": marketing_alerts},
        "not_yet_tracked": {
            "read_receipts": "No message-tracking data model exists yet.",
        },
    }


def _lead_source_conversion():
    """Real per-source conversion -- how many of each Lead.Source's leads actually
    reached SOLD -- the real signal behind sales.pdf's Lead Performance ask, beyond
    the existing flat volume-by-stage breakdown."""

    by_source = {}

    for l in _entities(LEAD):
        source = l.attributes.get("Source") or "Unknown"
        bucket = by_source.setdefault(source, {"total": 0, "sold": 0})
        bucket["total"] += 1
        if l.attributes.get("PipelineState") == "SOLD":
            bucket["sold"] += 1

    return {
        source: {**counts, "conversion_rate": round(counts["sold"] / counts["total"], 3) if counts["total"] else None}
        for source, counts in by_source.items()
    }


def _salesperson_scorecards():
    """Session 97 follow-up (Sales sub-menu spec, Reporting item): a real per-rep
    Salesperson Scorecard. Reuses core/manager_dashboard.py's already-built,
    already-routed (GET /dashboard/manager) per-employee lead metrics (assigned/
    active/closed/stalled leads, real conversion rate off core/employee_performance.py)
    rather than the old bare {employee_id, conversion_rate} leaderboard shape --
    enriched here with real name/title, funded units/gross (Deal.created_by, same
    Vehicle.Price-minus-Cost computation core/employee_value.py's sales attribution
    already relies on), and a real appointment show rate (arrived/completed vs.
    scheduled, session 96's Appointment entity)."""

    raw = _get_manager_lead_metrics()
    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    all_deals = _entities(DEAL)

    scorecards = []

    for entry in raw:

        employee_id = entry["employee_id"]
        employee = ledger.get_entity(employee_id)
        name = f"{employee.attributes.get('FirstName', '')} {employee.attributes.get('LastName', '')}".strip() if employee else employee_id
        title = employee.attributes.get("Title") if employee else None

        my_funded = [
            d for d in all_deals
            if d.attributes.get("created_by") == employee_id and d.attributes.get("status") == "funded"
        ]
        gross = 0.0
        for d in my_funded:
            vehicle = vehicles_by_id.get(d.attributes.get("vehicle_id"))
            if vehicle:
                gross += _safe_float(vehicle.attributes.get("Price")) - _safe_float(vehicle.attributes.get("Cost"))

        my_appointments = _list_appointments(department="Sales", assigned_to=employee_id)
        shown = [a for a in my_appointments if a.attributes.get("status") in ("arrived", "completed")]
        show_rate = round(len(shown) / len(my_appointments), 3) if my_appointments else None

        scorecards.append({
            "employee_id": employee_id,
            "name": name,
            "title": title,
            "assigned_leads": entry["assigned_leads"],
            "active_leads": entry["active_leads"],
            "closed_leads": entry["closed_leads"],
            "stalled_leads": entry["stalled_leads"],
            "conversion_rate": entry["conversion_rate"],
            "units_sold_funded": len(my_funded),
            "gross_profit": round(gross, 2),
            "appointments_scheduled": len(my_appointments),
            "appointments_shown": len(shown),
            "show_rate": show_rate,
        })

    scorecards.sort(key=lambda s: s["gross_profit"], reverse=True)

    return scorecards


def reporting(role):
    """sales.pdf's "Reporting" item: department performance rollups. BDC Performance
    has no call-tracking data model yet. Forecasting reuses core/prediction.py's real
    ledger-based units_sold predictions (readiness_predictions_api) rather than a
    fabricated projection. Salesperson Scorecards and Manager Reports, both real as
    of session 97, reuse core/manager_dashboard.py/core/manager_analytics.py (built
    and already routed at GET /dashboard/manager, just never surfaced here) and
    core/sales_overview.py's Sales Manager Dashboard (session 94) rather than a
    third parallel per-rep computation."""

    pipeline = get_lead_pipeline_dashboard()
    all_deals = _entities(DEAL)
    funded_deals = [d for d in all_deals if d.attributes.get("status") == "funded"]
    gross_total = _funded_deal_gross(funded_deals)

    trade_capture_rate = (
        round(len([d for d in all_deals if d.attributes.get("trade_in")]) / len(all_deals), 3)
        if all_deals else None
    )

    readiness = readiness_predictions_api()
    sales_forecast = next((d for d in readiness.get("departments", []) if d["department"] == "sales"), None)

    scorecards = _salesperson_scorecards()
    avg_conversion = round(sum(s["conversion_rate"] for s in scorecards) / len(scorecards), 3) if scorecards else None

    total_leads = len(_entities(LEAD))
    sales_appointments = _list_appointments(department="Sales")
    lead_linked_appointments = [a for a in sales_appointments if a.attributes.get("lead_id")]

    return {
        "lead_performance": {
            "lead_volume": sum(pipeline.values()),
            "by_pipeline_stage": pipeline,
            "by_source_conversion": _lead_source_conversion(),
            "lead_to_appointment_rate": round(len(lead_linked_appointments) / total_leads, 3) if total_leads else None,
        },
        "sales_performance": {
            "units_sold_funded": len(funded_deals),
            "front_end_gross_total": round(gross_total, 2),
            "avg_closing_ratio": avg_conversion,
        },
        "deal_performance": {
            "gross_profit_total": round(gross_total, 2),
            "trade_capture_rate": trade_capture_rate,
        },
        "salesperson_scorecards": {"reps": scorecards},
        "manager_reports": {
            "team_performance": scorecards,
            "operational_gaps": _get_manager_operational_gaps(role),
        },
        "forecasting": sales_forecast,
        "department_intelligence": get_department_api(role, "sales"),
        "not_yet_tracked": {
            "bdc_performance": "No call-tracking data model exists yet (Calls Made/Contacts/Appointments Set/Shown).",
        },
    }


def accessories(role):
    """Sales' "Accessories" view (2026-07-23) -- a thin, role-gated pass-through
    to core/accessories_api.py's real accessories upsell overview. Mirrors
    operations_menu.customer_journey."""

    return {
        "accessories": get_accessories_overview_api(role),
        "note": "Accessories upsell desk overview (Sales department).",
    }


def equity_center(role):
    """Sales' "Equity Center" view (2026-07-23) -- a thin, role-gated pass-through
    to core/equity_center_api.py's real equity/upgrade-offer overview. Mirrors
    operations_menu.customer_journey."""

    return {
        "equity_center": get_equity_overview_api(role),
        "note": "Equity position and upgrade-offer overview (Sales department).",
    }