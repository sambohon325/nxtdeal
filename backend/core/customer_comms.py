"""
core/customer_comms.py -- the CUSTOMER side of Communications (2026-07-24, Sam's spec).

NXTDeal Communications is being split into two halves, mirroring the Knowledge panel above it:
  * Company -- internal, Slack-style channels/DMs between NXTDeal users (unchanged; the existing
    messaging system).
  * Customer -- outbound/inbound phone + text with actual customers: search the CRM, dial a
    number, place a call or send a text, and carry out the conversation in a workspace that shows
    the AI recording, analyzing, and coaching the interaction.

This module is the customer side's composition layer. It does NOT reimplement telephony -- it
wires together the real modules NXTDeal already has:
  * call_center.py       -- the Call entity (place/connect/end, simulated voice)
  * communications_hub.py -- the Communication entity (a text, or a call's recorded transcript)
  * conversation_intelligence.py -- rules-based sentiment/score/coaching on any transcript/body
  * connect.py           -- the per-customer unified timeline
  * integrations_registry.py -- the swappable provider seam (notifications capability)

HONESTY: no real telephony provider is registered in this codebase, so dialing a number and
sending a text are simulated (a real Call/Communication record is created and the AI analysis is
real, but nothing leaves the building). The day a Twilio-type adapter is registered for the
`notifications` capability, the same call sites go live. `provider_status()` tells the UI whether
a provider is connected so it can surface a "Connect a phone provider" prompt into the Marketplace.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import CUSTOMER, LEAD
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.audit import audit_log
from core.queries import search_graph
from core import (
    call_center,
    communications_hub,
    conversation_intelligence,
    connect,
    integrations_registry,
)

# Calls are department-scoped in call_center (lowercase: sales/service/finance/general); default
# to sales when the caller doesn't specify.
DEFAULT_DEPARTMENT = "sales"


def _dept(department):
    """Normalize a department to call_center's lowercase set, falling back to the default."""
    d = (department or DEFAULT_DEPARTMENT).strip().lower()
    return d if d in ("sales", "service", "finance", "general") else DEFAULT_DEPARTMENT


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------------------------
# Provider status -- drives the "Connect a phone provider" prompt.
# ---------------------------------------------------------------------------------------------

def provider_status():
    live = integrations_registry.is_live("notifications")
    return {
        "capability": "notifications",
        "live": live,
        "recommended_provider": "Twilio",
        "marketplace_category": "communications",
        "note": (
            "A real phone/SMS provider is connected -- calls and texts are live."
            if live
            else "No phone/SMS provider is connected yet, so calls and texts are simulated "
                 "(a real record is created and the AI analysis runs, but nothing is actually "
                 "dialed or sent). Install a Communications provider (e.g. Twilio) from the "
                 "Marketplace to go live."
        ),
    }


# ---------------------------------------------------------------------------------------------
# Customer search + contact save.
# ---------------------------------------------------------------------------------------------

def _brief(entity):
    a = entity.attributes
    name = a.get("name") or " ".join(
        p for p in [a.get("first_name"), a.get("last_name")] if p
    ) or entity.id
    return {
        "id": entity.id,
        "type": entity.entity_type,
        "name": name,
        "phone": a.get("phone"),
        "email": a.get("email"),
        "pipeline_state": a.get("pipeline_state"),
    }


def search_customers(query, limit=25):
    """Find customers/leads by name, phone, or email (reuses the graph search). Only the
    contactable people (Customer/Lead) are returned -- never vehicles/deals/etc."""
    if not query or not query.strip():
        return {"query": "", "count": 0, "results": []}
    hits = [e for e in search_graph(query) if e.entity_type in (CUSTOMER, LEAD)]
    briefs = [_brief(e) for e in hits][:limit]
    return {"query": query, "count": len(briefs), "results": briefs}


def save_contact(number, name, actor_id, email=None):
    """Turn a dialed/free-typed number into a real CRM Customer so the conversation is anchored
    to a record (Sam: "dial a number directly ... and then save it to the crm")."""
    if not number or not str(number).strip():
        return {"error": "A phone number is required to save a contact."}
    entity = Entity(
        id=id_generator.generate("CUST"),
        entity_type=CUSTOMER,
        attributes={
            "name": name or number,
            "phone": number,
            "email": email,
            "source": "communications_dialpad",
            "created_by": actor_id,
            "created_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="customer_saved_from_comms",
        summary=f"{actor_id} saved {name or number} to the CRM from Communications",
        entity_id=entity.id, actor=actor_id,
        details={"phone": number},
    )
    return _brief(entity)


def _resolve_number(customer_id=None, number=None):
    """Return (number, linked_entity_id, error)."""
    if customer_id:
        entity = ledger.get_entity(customer_id)
        if not entity:
            return None, None, f"Customer '{customer_id}' not found."
        num = number or entity.attributes.get("phone")
        if not num:
            return None, customer_id, f"{_brief(entity)['name']} has no phone number on file."
        return num, customer_id, None
    if number:
        return number, None, None
    return None, None, "A customer or a phone number is required."


# ---------------------------------------------------------------------------------------------
# Voice -- place / end a call, with the AI analysis of the (simulated) recording.
# ---------------------------------------------------------------------------------------------

def place_call(actor_id, customer_id=None, number=None, department=DEFAULT_DEPARTMENT):
    """Place an outbound call and connect it (ringing -> connected) so the workspace shows a live
    call. Simulated until a telephony provider is registered."""
    num, linked, error = _resolve_number(customer_id, number)
    if error:
        return {"error": error}

    call, call_error = call_center.place_outbound_call(
        department=_dept(department), to_number=num, created_by=actor_id, linked_entity_id=linked,
    )
    if call_error:
        return {"error": call_error}

    # Move ringing -> connected so it reads as a live conversation in the workspace.
    connected, connect_error = call_center.connect_call(call["id"])
    result_call = connected if connected and not connect_error else call

    return {
        "call": result_call,
        "customer": _brief(ledger.get_entity(linked)) if linked else {"name": num, "phone": num},
        "provider": provider_status(),
    }


def end_call(call_id, actor_id, notes=None, duration_seconds=None):
    """End a connected call. call_center.end_call synthesizes a phone Communication with the
    simulated recording/transcript; we then run the AI analysis (sentiment/score/coaching) over
    it and return everything the workspace needs."""
    call, error = call_center.end_call(call_id, ended_by=actor_id, notes=notes,
                                        duration_seconds=duration_seconds)
    if error:
        return {"error": error}

    comm_id = call.get("communication_id")
    communication = communications_hub.get_communication(comm_id) if comm_id else None
    intelligence = conversation_intelligence.analyze_communication(comm_id) if comm_id else None
    return {"call": call, "communication": communication, "intelligence": intelligence}


def get_call_intelligence(comm_id):
    """The AI recording/analysis/coaching for one communication (a call's recorded transcript or a
    text) -- what the workspace shows under 'AI'."""
    return conversation_intelligence.analyze_communication(comm_id)


# ---------------------------------------------------------------------------------------------
# Text -- send an SMS-style message (real Communication + simulated dispatch via the seam).
# ---------------------------------------------------------------------------------------------

def send_text(actor_id, body, customer_id=None, number=None, department=DEFAULT_DEPARTMENT):
    if not body or not body.strip():
        return {"error": "A message body is required."}
    num, linked, error = _resolve_number(customer_id, number)
    if error:
        return {"error": error}

    from core.contact_suppression import contact_suppression
    blocked = contact_suppression(num, linked, channels=("sms",))
    if blocked:
        return blocked

    comm, comm_error = communications_hub.log_communication(
        department=_dept(department), channel="text", direction="outbound", body=body,
        created_by=actor_id, linked_entity_id=linked,
    )
    if comm_error:
        return {"error": comm_error}

    # Dispatch through the provider seam (simulated unless a real adapter is registered).
    dispatch = integrations_registry.send_notification(
        to=num, event={"type": "customer_text", "body": body}, channels=("sms",),
    )
    if dispatch.get("error"):
        return {"error": dispatch["error"], "code": dispatch.get("code"), "dispatch": dispatch}
    intelligence = conversation_intelligence.analyze_communication(comm["id"])
    return {
        "communication": comm,
        "dispatch": dispatch,
        "intelligence": intelligence,
        "provider": provider_status(),
    }


# ---------------------------------------------------------------------------------------------
# Conversation timeline + recent activity for the panel.
# ---------------------------------------------------------------------------------------------

def get_conversation(customer_id):
    """The full unified timeline (calls + texts + appointments) with one customer -- reuses
    NXTDeal Connect's per-entity timeline."""
    entity = ledger.get_entity(customer_id)
    if not entity:
        return {"error": f"Customer '{customer_id}' not found."}
    timeline = connect.get_customer_timeline(customer_id)
    return {"customer": _brief(entity), "timeline": timeline}


def recent_activity(department=None, limit=25):
    """Recent customer calls + texts across the store, newest first -- the 'recent conversations'
    list on the Customer side of the panel."""
    calls = call_center.list_calls(department=department)
    comms = communications_hub.list_communications(department=department)

    items = []
    for c in (calls or []):
        items.append({
            "kind": "call",
            "id": c.get("id"),
            "at": c.get("created_at"),
            "direction": c.get("direction"),
            "status": c.get("status"),
            "number": c.get("to_number") or c.get("from_number"),
            "linked_entity_id": c.get("linked_entity_id"),
            "communication_id": c.get("communication_id"),
        })
    for m in (comms or []):
        if m.get("channel") in ("text", "phone"):
            items.append({
                "kind": m.get("channel"),
                "id": m.get("id"),
                "at": m.get("created_at"),
                "direction": m.get("direction"),
                "summary": m.get("ai_summary") or m.get("body"),
                "linked_entity_id": m.get("linked_entity_id"),
                "communication_id": m.get("id"),
            })
    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"count": len(items[:limit]), "items": items[:limit]}
