"""
Marketing CRM: Customer 360 (Marketing Growth Platform kickoff, 2026-07-17).

Sam's reframe of Marketing into a "NXTDeal Growth Platform": the existing CRM
(session 79-82) is a real lead pipeline, which is Sales CRM -- "Marketing CRM needs
to be an audience and customer intelligence platform," a Customer 360 covering Lead
History / Vehicle Ownership / Trade Equity / Service History / Finance History /
Website Activity / Email Activity / SMS Activity / Chat Activity / Event Attendance
/ Campaign Activity / Purchase History. "One record. One timeline."

Built entirely by composing already-real engines rather than a parallel data model
-- same "reuse, don't duplicate" discipline as every prior department kickoff in
this codebase:

  - Purchase History / Service History / Finance Contracts / Vehicles Owned: calls
    core/sales_menu.py's `_customer_360()` verbatim (session 95) rather than a
    second grouped-relationship query.
  - Lead History: BECAME (Lead -> Customer, the historical lead(s) that became this
    customer, core/lead_conversion.py, session 93) plus GENERATED_LEAD
    (Customer -> Lead, leads generated FROM this customer later by orphan-owner
    mining / trigger-alert promotion / service-to-sales handoff -- sessions
    84/85/93/105/106) -- a customer can have both an origin lead and later
    re-engagement leads, and this is the one place both directions are shown
    together.
  - Trade Equity: reuses core/trigger_alerts.py's real, already-computed
    equity-mining scan filtered to this customer -- the exact same HEURISTIC
    signal core/sales_menu.py's `customers()` Equity Mining tab already surfaces,
    not a second equity computation.
  - Email/SMS/Call/Video ("Communication") Activity: reuses
    core/field_notes.py's Communication Hub categories (session 92/93), keyed to
    every Lead ever linked to this customer -- a FieldNote's `linked_entity_id` is
    always a Lead id in this codebase's Sales-communication logging, never a
    Customer id directly, so this module resolves through the customer's known
    leads first.
  - Chat Activity: reuses core/website_chat.py's real sessions, matched the same
    way -- a chat session only ever gains a `lead_id` once promoted
    (`promote_session_to_lead()`); pre-promotion anonymous browsing has no
    visitor-to-identity link anywhere in this codebase, an honest, explicitly
    flagged gap.
  - Event Attendance: reuses core/dealership_events.py's real `EventRSVP.customer_id`
    (session 84).
  - Campaign Activity: reuses core/campaigns.py's real `Campaign.audience_ids`,
    matched against this customer's id AND every id of a lead ever linked to them
    (a campaign audience is built pre-conversion as often as post-).
  - Website Activity (anonymous on-site browsing, distinct from Chat): an honest,
    stated gap -- core/websites.py's `record_page_view()` is genuinely anonymous
    (`viewer_ref` is a raw, unresolved string), so no per-customer page-view history
    can be honestly computed. Not simulated -- this is an internal telemetry gap
    this codebase could close for real in a future slice (same class of decision
    Lot Control/Merchandising made: build it real or say so), not a market-data gap
    covered by the standing simulate-when-blocked policy.
  - Credit Applications: reuses core/credit_app.py's real `list_credit_applications
    (customer_id=...)` directly (session 104) -- status/decision/score-band/
    estimated-APR/requested-amount, the same records Finance's own Credit App
    workflow already manages, not a second application model.
  - Trade-Ins: a real scan of every Deal this customer has ever desked with a
    non-empty `trade_in` dict on file (core/deals.py's Trade Appraisal, session 92)
    -- vehicle/ACV/market-value-estimate/appraisal-and-approval status, surfaced
    here for the first time outside the Deal Desk itself.

Added 2026-07-19 (Sam's "Customer Intelligence Layer" ask, his own framing: "the
single biggest feature... every department sees the same timeline" -- Credit
Applications and Trade-Ins were the two fields on his own explicit list
(Contact/History/Calls/Texts/Emails/Trades/Credit Apps/Vehicles/Service Visits/
Marketing Activity) this module didn't already carry; every other item on that
list was already real here since session 113). This is also the session that gave
Sales (`CustomersBoard.tsx`) and Service (`CustomersServiceBoard.tsx`) their own
"Full Customer 360" entry points into this exact same engine/timeline (previously
Marketing's CRM tab was the only frontend consumer) and gave Finance
(`PortfolioBoard.tsx`) its first Customer 360 entry point at all -- see
`frontend/components/shared/Customer360Panel.tsx`.

One real, chronologically-merged Timeline is composed from all of the above,
matching Prospects' own `get_lead_record()` Timeline precedent (session 92/93).
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER, LEAD, CAMPAIGN, EVENT_RSVP, WEBSITE_CHAT_SESSION, DEAL
from core.ai_tools import get_entity_by_id, get_related_entities
from core.field_notes import list_field_notes
from core.relationship_types import BECAME, GENERATED_LEAD
from core.sales_menu import _customer_360 as _sales_customer_360
from core.trigger_alerts import list_alerts
from core.purls import get_purl_activity_for_customer
from core.credit_app import list_credit_applications

COMMUNICATION_CATEGORIES = {"call", "text", "email", "video"}


def _now():
    return datetime.now(timezone.utc)


def _relationships_from(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.source_id == entity_id and r.relationship_type == relationship_type]


def _relationships_to(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.target_id == entity_id and r.relationship_type == relationship_type]


def _linked_lead_ids(customer_id):
    """Every Lead ever connected to this customer, either direction: BECAME
    (the historical lead(s) that converted into this customer) and GENERATED_LEAD
    (re-engagement leads generated from this customer later)."""

    origin_leads = [r.source_id for r in _relationships_to(customer_id, BECAME)]
    generated_leads = [r.target_id for r in _relationships_from(customer_id, GENERATED_LEAD)]

    seen = []
    for lid in origin_leads + generated_leads:
        if lid not in seen:
            seen.append(lid)

    return seen


def _lead_brief(lead_id):
    entity = ledger.get_entity(lead_id)
    if not entity or entity.entity_type != LEAD:
        return None
    return {
        "id": entity.id,
        "source": entity.attributes.get("Source"),
        "pipeline_state": entity.attributes.get("PipelineState"),
        "created_at": entity.attributes.get("CreatedAt") or entity.attributes.get("CreatedDate"),
    }


def _get_lead_history(customer_id):

    origin_rels = _relationships_to(customer_id, BECAME)
    generated_rels = _relationships_from(customer_id, GENERATED_LEAD)

    origin = [b for b in (_lead_brief(r.source_id) for r in origin_rels) if b]
    generated = [b for b in (_lead_brief(r.target_id) for r in generated_rels) if b]

    return {
        "origin_leads": {"count": len(origin), "leads": origin},
        "re_engagement_leads": {"count": len(generated), "leads": generated},
    }


def _get_trade_equity(customer_id):

    equity_alerts = [
        a for a in list_alerts(alert_type="equity_mining", status=None)
        if a.attributes.get("target_entity_id") == customer_id
    ]

    return {
        "count": len(equity_alerts),
        "basis": "heuristic_equity_mining",
        "signals": [
            {
                "id": a.id,
                "status": a.attributes.get("status"),
                "headline": a.attributes.get("headline"),
                "vehicle_id": a.attributes.get("vehicle_id"),
                "created_at": a.attributes.get("created_at"),
            }
            for a in equity_alerts
        ],
    }


def _get_communication_activity(lead_ids):

    all_notes = []
    for lid in lead_ids:
        all_notes.extend(list_field_notes(linked_entity_id=lid, limit=200))

    comms = [n for n in all_notes if n.attributes.get("category") in COMMUNICATION_CATEGORIES]

    by_channel = {}
    for n in comms:
        cat = n.attributes.get("category")
        by_channel[cat] = by_channel.get(cat, 0) + 1

    comms.sort(key=lambda n: n.attributes.get("created_at") or "", reverse=True)

    return {
        "count": len(comms),
        "by_channel": by_channel,
        "recent": [
            {
                "id": n.id,
                "category": n.attributes.get("category"),
                "body": n.attributes.get("body"),
                "created_by": n.attributes.get("created_by"),
                "created_at": n.attributes.get("created_at"),
            }
            for n in comms[:20]
        ],
    }


def _get_chat_activity(lead_ids):

    sessions = [
        e for e in ledger.get_all().values()
        if e.entity_type == WEBSITE_CHAT_SESSION and e.attributes.get("lead_id") in lead_ids
    ]

    sessions.sort(key=lambda s: s.attributes.get("created_at") or "", reverse=True)

    return {
        "count": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "website_id": s.attributes.get("website_id"),
                "status": s.attributes.get("status"),
                "created_at": s.attributes.get("created_at"),
            }
            for s in sessions
        ],
        "not_yet_tracked": "Pre-promotion anonymous chat/browsing has no visitor-to-customer identity link anywhere in this codebase -- only sessions already promoted to one of this customer's known leads are shown.",
    }


def _get_event_attendance(customer_id):

    rsvps = [
        e for e in ledger.get_all().values()
        if e.entity_type == EVENT_RSVP and e.attributes.get("customer_id") == customer_id
    ]

    rsvps.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)

    return {
        "count": len(rsvps),
        "rsvps": [
            {
                "id": r.id,
                "event_id": r.attributes.get("event_id"),
                "status": r.attributes.get("status"),
                "attended": r.attributes.get("attended"),
                "created_at": r.attributes.get("created_at"),
            }
            for r in rsvps
        ],
    }


def _get_campaign_activity(customer_id, lead_ids):

    target_ids = {customer_id, *lead_ids}

    campaigns = [
        e for e in ledger.get_all().values()
        if e.entity_type == CAMPAIGN and target_ids.intersection(e.attributes.get("audience_ids") or [])
    ]

    campaigns.sort(key=lambda c: c.attributes.get("created_at") or "", reverse=True)

    return {
        "count": len(campaigns),
        "campaigns": [
            {
                "id": c.id,
                "name": c.attributes.get("name"),
                "campaign_type": c.attributes.get("campaign_type"),
                "channel": c.attributes.get("channel"),
                "status": c.attributes.get("status"),
                "activated_at": c.attributes.get("activated_at"),
            }
            for c in campaigns
        ],
        "not_yet_tracked": "No per-recipient send/open/click event log exists -- membership in a campaign's audience_ids at creation time is the real signal available, not delivery/engagement status.",
    }


def _get_credit_applications(customer_id):

    apps = list_credit_applications(customer_id=customer_id)

    return {
        "count": len(apps),
        "applications": [
            {
                "id": a.id,
                "status": a.attributes.get("status"),
                "linked_deal_id": a.attributes.get("linked_deal_id"),
                "requested_amount": a.attributes.get("requested_amount"),
                "decision": (a.attributes.get("decision") or {}).get("decision") if a.attributes.get("decision") else None,
                "score_band": (a.attributes.get("decision") or {}).get("score_band") if a.attributes.get("decision") else None,
                "estimated_apr": (a.attributes.get("decision") or {}).get("estimated_apr") if a.attributes.get("decision") else None,
                "created_at": a.attributes.get("created_at"),
            }
            for a in apps
        ],
    }


def _get_trade_ins(customer_id):

    deals = [
        e for e in ledger.get_all().values()
        if e.entity_type == DEAL and e.attributes.get("customer_id") == customer_id and e.attributes.get("trade_in")
    ]

    deals.sort(key=lambda d: (d.attributes.get("trade_in") or {}).get("appraised_at") or "", reverse=True)

    trades = []
    for d in deals:
        t = d.attributes.get("trade_in") or {}
        trades.append({
            "deal_id": d.id,
            "deal_status": d.attributes.get("status"),
            "vin": t.get("vin"),
            "year": t.get("year"),
            "make": t.get("make"),
            "model": t.get("model"),
            "acv": t.get("acv"),
            "market_value_estimate": t.get("market_value_estimate"),
            "approved": t.get("approved"),
            "appraised_by": t.get("appraised_by"),
            "appraised_at": t.get("appraised_at"),
        })

    return {"count": len(trades), "trades": trades}


def get_customer_360(role, customer_id, employee_id=None):

    result = get_entity_by_id(role, customer_id)

    if "error" in result:
        return result

    # Field-level security (Administration's Roles & Permissions slice,
    # core/permissions_registry.py) -- Sam's own literal example, "Can View Deal,
    # Cannot See Credit Score." Masks Customer.CreditScore for any role/employee
    # not permitted to see it (ADMIN/FINANCE by default, or a real per-employee
    # override), real enforcement on the actual attributes returned here rather
    # than just a config screen.
    from core.permissions_registry import filter_sensitive_fields
    result = dict(result)
    result["attributes"] = filter_sensitive_fields(role, employee_id, "Customer", result.get("attributes"))

    entity = ledger.get_entity(customer_id)

    if not entity or entity.entity_type != CUSTOMER:
        return {"error": "Customer not found"}

    lead_ids = _linked_lead_ids(customer_id)

    sales_360 = _sales_customer_360(customer_id)
    lead_history = _get_lead_history(customer_id)
    trade_equity = _get_trade_equity(customer_id)
    communications = _get_communication_activity(lead_ids)
    chat = _get_chat_activity(lead_ids)
    events = _get_event_attendance(customer_id)
    campaigns = _get_campaign_activity(customer_id, lead_ids)
    credit_applications = _get_credit_applications(customer_id)
    trade_ins = _get_trade_ins(customer_id)

    # One real, chronologically-merged Timeline -- "one record, one timeline."
    timeline = []

    for d in sales_360["purchase_history"]["deals"]:
        timeline.append({"type": "purchase", "summary": f"Deal {d['id']} ({d['status']})", "timestamp": d.get("funded_at"), "details": d})

    for s in sales_360["service_history"]["records"]:
        timeline.append({"type": "service", "summary": f"Service: {s.get('description') or s['id']}", "timestamp": s.get("service_date"), "details": s})

    for n in communications["recent"]:
        timeline.append({"type": "communication", "summary": f"{n['category']}: {(n.get('body') or '')[:140]}", "timestamp": n.get("created_at"), "actor": n.get("created_by"), "details": n})

    for s in chat["sessions"]:
        timeline.append({"type": "chat", "summary": f"Website chat session {s['id']} ({s.get('status')})", "timestamp": s.get("created_at"), "details": s})

    for r in events["rsvps"]:
        timeline.append({"type": "event", "summary": f"RSVP to event {r.get('event_id')} ({r.get('status')})", "timestamp": r.get("created_at"), "details": r})

    for c in campaigns["campaigns"]:
        timeline.append({"type": "campaign", "summary": f"In audience for campaign: {c.get('name')}", "timestamp": c.get("activated_at"), "details": c})

    for eq in trade_equity["signals"]:
        timeline.append({"type": "trade_equity", "summary": eq.get("headline"), "timestamp": eq.get("created_at"), "details": eq})

    for a in credit_applications["applications"]:
        label = a.get("decision") or a.get("status")
        timeline.append({"type": "credit_application", "summary": f"Credit application {a['id']} ({label})", "timestamp": a.get("created_at"), "details": a})

    for t in trade_ins["trades"]:
        vehicle_label = " ".join(str(x) for x in (t.get("year"), t.get("make"), t.get("model")) if x) or t["deal_id"]
        approved_label = "approved" if t.get("approved") else "pending approval"
        timeline.append({"type": "trade_in", "summary": f"Trade-in appraised: {vehicle_label} ({approved_label})", "timestamp": t.get("appraised_at"), "actor": t.get("appraised_by"), "details": t})

    website_activity = get_purl_activity_for_customer(customer_id)

    for v in website_activity["visits"]:
        timeline.append({"type": "website_activity", "summary": f"Visited personalized page {v.get('purl_id')} ({v.get('offer_type')})", "timestamp": v.get("visited_at"), "details": v})

    timeline = [t for t in timeline if t.get("timestamp")]
    timeline.sort(key=lambda t: t["timestamp"], reverse=True)

    return {
        "customer": result,
        "related_entities": get_related_entities(role, customer_id),
        "lead_history": lead_history,
        "purchase_history": sales_360["purchase_history"],
        "vehicles_owned": sales_360["vehicles_owned"],
        "service_history": sales_360["service_history"],
        "finance_contracts": sales_360["finance_contracts"],
        "trade_equity": trade_equity,
        "communication_activity": communications,
        "chat_activity": chat,
        "event_attendance": events,
        "campaign_activity": campaigns,
        "credit_applications": credit_applications,
        "trade_ins": trade_ins,
        "website_activity": website_activity,
        "timeline": timeline,
        "not_yet_tracked": {
            "anonymous_website_browsing": "General anonymous on-site page-view/browsing history still has no visitor-to-customer identity link anywhere in this codebase (core/websites.py's record_page_view() is genuinely anonymous) -- an internal tracking gap for that channel specifically, not a market-data gap. The PURL Platform (core/purls.py, added this same slice) closes this for real on ITS one channel, since a PURL visitor's identity IS the token -- see website_activity above.",
            "email_sms_delivery_status": "No per-recipient send/open/click event log exists for Email/SMS campaigns -- audience membership is the real signal available today.",
        },
    }
