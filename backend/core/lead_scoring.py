"""
Marketing CRM: Lead Scoring (Marketing Growth Platform kickoff, 2026-07-17).

Sam's example point catalog: "Viewed Inventory = +10, Opened Email = +5, Clicked Ad
= +10, Used Payment Calculator = +15, Started Credit App = +40 -- automatically
prioritize."

Three of those five example signals have no backing tracking data anywhere in this
codebase, confirmed before writing anything (same "state the gap, don't fabricate
the signal" discipline core/lead_record.py's `next_best_action()` already applied
to Sam's own illustrative "customer opened pricing email" example, session 92):
  - "Opened Email": no per-recipient email open-tracking model exists anywhere.
  - "Clicked Ad": core/advertising.py's ad launches are honestly SIMULATED with no
    real click-tracking pixel/redirect (impressions/clicks/CPC are explicitly
    `not_yet_tracked` there too, session 83).
  - "Used Payment Calculator": no payment-calculator-usage-event model exists
    anywhere (core/websites.py's `record_page_view()` tracks anonymous page
    visits, not which on-page tool a visitor interacted with).
  - "Viewed Inventory": same gap as the above -- page views are anonymous
    (`viewer_ref` unresolved), so they can't be attributed to a specific Lead.

Rather than leave the scoring engine thin, this substitutes REAL, honestly
observable signals already tracked elsewhere in this codebase for genuine buying-
intent behavior -- same "real analog for an illustrative example" precedent
`next_best_action()` set:
  - Started Credit Application: +40 (kept exactly as Sam specified -- this one IS
    real, core/credit_app.py, session 104).
  - Deal Desked: +30 (a real desking record exists, core/deals.py, session 33 --
    about as strong an intent signal as exists in this codebase).
  - Test Drive Completed: +25 (core/demo_drive.py, session 102).
  - Appointment Attended (arrived/completed): +20 (core/appointments.py, session 96).
  - Event RSVP: +15 (core/dealership_events.py, session 84).
  - Appointment Scheduled (not yet attended): +15.
  - Website Chat Initiated: +10 (core/website_chat.py, session 85 -- only once a
    session carries a lead_id, i.e. post-promotion; anonymous pre-promotion chat
    has no identity link, same gap as page views).
  - Trigger Alert Match (an open equity-mining/conquest/lease-maturity/service
    win-back signal already exists for them): +10 (core/trigger_alerts.py,
    session 84).
  - Communication Logged (a staff-logged call/text/email/video touch,
    core/field_notes.py, session 92): +5 each, capped at 3 counted (+15 max) so a
    single busy salesperson's own notes don't dominate the score over real
    customer-initiated engagement.

A score resolves across every identity linked to the target (a Lead's own id, plus
the Customer it became via BECAME if it converted, or a Customer's id plus every
Lead ever linked to them via BECAME/GENERATED_LEAD) -- the same identity-resolution
core/customer_360.py already established, reused here rather than reimplemented.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import (
    LEAD, CUSTOMER, DEAL, CREDIT_APPLICATION, DEMO_DRIVE, EVENT_RSVP,
    APPOINTMENT, WEBSITE_CHAT_SESSION, TRIGGER_ALERT,
)
from core.field_notes import list_field_notes
from core.relationship_types import BECAME, GENERATED_LEAD

COMMUNICATION_CATEGORIES = {"call", "text", "email", "video"}

POINTS = {
    "credit_application_started": 40,
    "deal_desked": 30,
    "test_drive_completed": 25,
    "appointment_attended": 20,
    "event_rsvp": 15,
    "appointment_scheduled": 15,
    "website_chat_initiated": 10,
    "trigger_alert_match": 10,
    "communication_logged": 5,
}

COMMUNICATION_LOGGED_CAP = 3

TIER_HOT = "hot"
TIER_WARM = "warm"
TIER_COOL = "cool"


def _now():
    return datetime.now(timezone.utc)


def _relationships_from(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.source_id == entity_id and r.relationship_type == relationship_type]


def _relationships_to(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.target_id == entity_id and r.relationship_type == relationship_type]


def _resolve_identity(entity_id):
    """Every real id this prospect has ever been known by: the id itself, plus
    (Lead -> Customer via BECAME if converted) or (Customer -> every linked Lead
    via BECAME/GENERATED_LEAD if this is a Customer)."""

    entity = ledger.get_entity(entity_id)
    if not entity:
        return {"lead_ids": set(), "customer_ids": set()}

    lead_ids = set()
    customer_ids = set()

    if entity.entity_type == LEAD:
        lead_ids.add(entity_id)
        became = _relationships_from(entity_id, BECAME)
        for r in became:
            customer_ids.add(r.target_id)

    elif entity.entity_type == CUSTOMER:
        customer_ids.add(entity_id)
        for r in _relationships_to(entity_id, BECAME):
            lead_ids.add(r.source_id)
        for r in _relationships_from(entity_id, GENERATED_LEAD):
            lead_ids.add(r.target_id)

    return {"lead_ids": lead_ids, "customer_ids": customer_ids}


def _all_of_type(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def compute_score(entity_id):

    identity = _resolve_identity(entity_id)
    lead_ids = identity["lead_ids"]
    customer_ids = identity["customer_ids"]
    all_ids = lead_ids | customer_ids

    if not all_ids:
        return {"error": "Entity not found or not a Lead/Customer"}

    breakdown = []
    total = 0

    def _add(reason, count, points_each):
        nonlocal total
        if count <= 0:
            return
        pts = count * points_each
        total += pts
        breakdown.append({"reason": reason, "count": count, "points_each": points_each, "points": pts})

    credit_apps = [c for c in _all_of_type(CREDIT_APPLICATION) if c.attributes.get("customer_id") in customer_ids]
    _add("Started Credit Application", len(credit_apps), POINTS["credit_application_started"])

    deals = [d for d in _all_of_type(DEAL) if d.attributes.get("customer_id") in customer_ids]
    _add("Deal Desked", len(deals), POINTS["deal_desked"])

    demo_drives = [d for d in _all_of_type(DEMO_DRIVE) if d.attributes.get("linked_entity_id") in all_ids]
    completed_drives = [d for d in demo_drives if d.attributes.get("status") == "returned"]
    _add("Test Drive Completed", len(completed_drives), POINTS["test_drive_completed"])

    appointments = [
        a for a in _all_of_type(APPOINTMENT)
        if a.attributes.get("customer_id") in customer_ids or a.attributes.get("lead_id") in lead_ids
    ]
    attended = [a for a in appointments if a.attributes.get("status") in ("arrived", "completed")]
    scheduled_only = [a for a in appointments if a.attributes.get("status") not in ("arrived", "completed", "no_show", "cancelled")]
    _add("Appointment Attended", len(attended), POINTS["appointment_attended"])
    _add("Appointment Scheduled", len(scheduled_only), POINTS["appointment_scheduled"])

    rsvps = [
        r for r in _all_of_type(EVENT_RSVP)
        if r.attributes.get("customer_id") in customer_ids or r.attributes.get("lead_id") in lead_ids
    ]
    _add("Event RSVP", len(rsvps), POINTS["event_rsvp"])

    chat_sessions = [s for s in _all_of_type(WEBSITE_CHAT_SESSION) if s.attributes.get("lead_id") in lead_ids]
    _add("Website Chat Initiated", len(chat_sessions), POINTS["website_chat_initiated"])

    trigger_alerts = [
        a for a in _all_of_type(TRIGGER_ALERT)
        if a.attributes.get("target_entity_id") in all_ids and a.attributes.get("status") == "new"
    ]
    _add("Trigger Alert Match", len(trigger_alerts), POINTS["trigger_alert_match"])

    communications = []
    for lid in lead_ids:
        communications.extend([n for n in list_field_notes(linked_entity_id=lid, limit=200) if n.attributes.get("category") in COMMUNICATION_CATEGORIES])
    comm_count = min(len(communications), COMMUNICATION_LOGGED_CAP)
    _add("Communication Logged", comm_count, POINTS["communication_logged"])

    if total >= 100:
        tier = TIER_HOT
    elif total >= 50:
        tier = TIER_WARM
    else:
        tier = TIER_COOL

    return {
        "entity_id": entity_id,
        "score": total,
        "tier": tier,
        "breakdown": breakdown,
        "not_yet_tracked": [
            "Viewed Inventory (anonymous page views have no visitor-to-lead identity link)",
            "Opened Email (no per-recipient email open-tracking model exists)",
            "Clicked Ad (core/advertising.py's ad launches have no real click-tracking)",
            "Used Payment Calculator (no payment-calculator-usage-event model exists)",
        ],
    }


def leaderboard(limit=50):
    """Every open (not SOLD/LOST) Lead, ranked by real score descending --
    Sam's "automatically prioritize.\""""

    leads = [l for l in _all_of_type(LEAD) if l.attributes.get("PipelineState") not in ("SOLD", "LOST")]

    scored = []
    for lead in leads:
        result = compute_score(lead.id)
        if "error" in result:
            continue
        scored.append({
            "lead_id": lead.id,
            "pipeline_state": lead.attributes.get("PipelineState"),
            "source": lead.attributes.get("Source"),
            "score": result["score"],
            "tier": result["tier"],
        })

    scored.sort(key=lambda s: s["score"], reverse=True)

    by_tier = {TIER_HOT: 0, TIER_WARM: 0, TIER_COOL: 0}
    for s in scored:
        by_tier[s["tier"]] += 1

    return {"count": len(scored), "by_tier": by_tier, "leads": scored[:limit]}
