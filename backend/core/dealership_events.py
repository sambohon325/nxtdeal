"""
Dealership Events -- the NXTDeal Bumper half of the Events dash (session 84). Sam:
"build out the event dash. we want to style it after nxtdeal bumper,
automotivemastermind.com, and auto alert... has to tightly integrate into the CRM."

A DealershipEvent is a real, scheduled event (test-drive day, VIP sale, service
clinic) -- not a calendar bolted onto the side. Its invite audience is optionally a
real core/marketing_lists.py MarketingList: publish_event() snapshots that list's
current membership into real EventRSVP records (status="invited") at publish time,
same "snapshot at save time, not a live query that silently changes underneath you"
rule core/marketing_lists.py's build_list_from_pool() already established. Walk-ins
and self-registrations who aren't on any list get their own EventRSVP too, tied to a
real Customer/Lead id when they're already in the graph or a freeform name/phone/email
snapshot when they're a genuinely new prospect.

The CRM tie-in that actually matters: promote_rsvp_to_lead() turns a post-event
attendee into a real new Lead (core/lead_intake.py's create_lead(), source="Event" --
already a valid source before this session, never actually used until now), tied back
to the originating Customer via a real GENERATED_LEAD relationship when one exists --
the exact same promote mechanism core/trigger_alerts.py uses for the Timeline side of
this dash, so both halves hand off to Sales identically.

Real data-loss bug found and fixed (2026-07-18, Marketing Growth Platform data-gap-fill
follow-up) -- same bug class as core/compliance.py/core/trigger_alerts.py/
core/lead_conversion.py: this module had ZERO save_graph() calls anywhere since it
shipped (session 84). Every real Event created/published/started/completed/cancelled
and every real RSVP created/updated/promoted had been silently discarded on server
restart -- the whole NXTDeal-Bumper half of the Events dash Sam explicitly called out
as needing to "tightly integrate into the CRM" had never actually persisted a single
real event or RSVP. Fixed by adding save_graph(GRAPH_PATH) to every mutating function
below.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import EVENT, EVENT_RSVP, CUSTOMER, LEAD
from core.relationship_types import GENERATED_LEAD
from core.marketing_lists import get_list
from core.lead_intake import create_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

EVENT_TYPES = [
    {"key": "test_drive", "name": "Test Drive Day"},
    {"key": "vip_sale", "name": "VIP Sale"},
    {"key": "service_clinic", "name": "Service Clinic"},
    {"key": "community", "name": "Community Event"},
    {"key": "product_launch", "name": "Product Launch"},
    {"key": "other", "name": "Other"},
]

RSVP_STATUSES = ["invited", "confirmed", "attended", "no_show", "cancelled"]

_EVENT_EDITABLE_FIELDS = {"name", "description", "event_type", "start_time", "end_time", "location", "capacity", "linked_list_id"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_event_types():
    return list(EVENT_TYPES)


def create_event(created_by, name, event_type, start_time, end_time=None, location="", capacity=None, description="", linked_list_id=None):

    if event_type not in [t["key"] for t in EVENT_TYPES]:
        return {"error": f"Unknown event_type '{event_type}'"}

    if linked_list_id and not get_list(linked_list_id):
        return {"error": f"List '{linked_list_id}' not found"}

    event_id = id_generator.generate("EVT")

    entity = Entity(
        id=event_id,
        entity_type=EVENT,
        attributes={
            "name": name or "New Event",
            "description": description or "",
            "event_type": event_type,
            "start_time": start_time,
            "end_time": end_time,
            "location": location or "",
            "capacity": capacity,
            "linked_list_id": linked_list_id,
            "status": "draft",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "published_at": None,
            "completed_at": None,
            "cancelled_at": None,
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_event(event_id):

    entity = ledger.get_entity(event_id)

    if entity and entity.entity_type == EVENT:
        return entity

    return None


def update_event(event_id, patch):

    entity = get_event(event_id)

    if not entity:
        return None

    if entity.attributes.get("status") not in ("draft", "scheduled"):
        return {"error": f"Can't edit an event that's already '{entity.attributes.get('status')}'"}

    for key, value in (patch or {}).items():
        if key in _EVENT_EDITABLE_FIELDS:
            entity.attributes[key] = value

    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def _serialize_member_for_rsvp(entity):

    if entity.entity_type == CUSTOMER:
        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()
        return {"customer_id": entity.id, "lead_id": None, "name": name or entity.id, "phone": entity.attributes.get("Phone"), "email": entity.attributes.get("Email")}

    if entity.entity_type == LEAD:
        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()
        return {"customer_id": None, "lead_id": entity.id, "name": name or entity.attributes.get("LeadID", entity.id), "phone": entity.attributes.get("Phone"), "email": entity.attributes.get("Email")}

    return None


def publish_event(event_id):
    """draft -> scheduled. Snapshots the linked List's current membership into real
    EventRSVP(status="invited") records -- the actual invite send is out of scope
    (this sandbox has no email/SMS provider, same gap core/campaigns.py's
    activate_campaign() already documents), so this stamps a real, honest invite
    roster on the graph rather than pretending an invite was sent."""

    entity = get_event(event_id)

    if not entity:
        return {"error": "Event not found"}

    if entity.attributes.get("status") != "draft":
        return {"error": f"Event is '{entity.attributes.get('status')}', not draft"}

    invited_count = 0

    linked_list_id = entity.attributes.get("linked_list_id")

    if linked_list_id:

        mlist = get_list(linked_list_id)

        if mlist:

            for member_id in mlist.attributes.get("member_ids") or []:

                member = ledger.get_entity(member_id)

                if not member:
                    continue

                serialized = _serialize_member_for_rsvp(member)

                if not serialized:
                    continue

                create_rsvp(event_id, serialized["name"], serialized["phone"], serialized["email"], customer_id=serialized["customer_id"], lead_id=serialized["lead_id"], source="invited", _skip_save=True)
                invited_count += 1

    entity.attributes["status"] = "scheduled"
    entity.attributes["published_at"] = _now()
    entity.attributes["updated_at"] = _now()

    # One real save covering the whole invite roster + the event's own status change --
    # not one save_graph() call per invitee (create_rsvp()'s own default), which would
    # be a real performance problem for a large linked List (same bulk-save discipline
    # imports/seed_payment_history.py already established).
    save_graph(GRAPH_PATH)

    return {"event": entity, "invited_count": invited_count}


def start_event(event_id):

    entity = get_event(event_id)

    if not entity:
        return {"error": "Event not found"}

    if entity.attributes.get("status") != "scheduled":
        return {"error": f"Event is '{entity.attributes.get('status')}', not scheduled"}

    entity.attributes["status"] = "live"
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def complete_event(event_id):

    entity = get_event(event_id)

    if not entity:
        return {"error": "Event not found"}

    if entity.attributes.get("status") not in ("scheduled", "live"):
        return {"error": f"Event is '{entity.attributes.get('status')}', not scheduled/live"}

    entity.attributes["status"] = "completed"
    entity.attributes["completed_at"] = _now()
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def cancel_event(event_id):

    entity = get_event(event_id)

    if not entity:
        return {"error": "Event not found"}

    if entity.attributes.get("status") not in ("draft", "scheduled"):
        return {"error": f"Event is '{entity.attributes.get('status')}', can only cancel a draft/scheduled event"}

    entity.attributes["status"] = "cancelled"
    entity.attributes["cancelled_at"] = _now()
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def list_events(status=None, event_type=None, created_by=None):

    events = [e for e in ledger.get_all().values() if e.entity_type == EVENT]

    if status:
        events = [e for e in events if e.attributes.get("status") == status]

    if event_type:
        events = [e for e in events if e.attributes.get("event_type") == event_type]

    if created_by:
        events = [e for e in events if e.attributes.get("created_by") == created_by]

    events.sort(key=lambda e: e.attributes.get("start_time") or e.attributes.get("created_at") or "", reverse=True)

    return events


# --- RSVPs ---

def create_rsvp(event_id, name, phone=None, email=None, customer_id=None, lead_id=None, source="walk_in", _skip_save=False):

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if customer_id and not (ledger.get_entity(customer_id) and ledger.get_entity(customer_id).entity_type == CUSTOMER):
        customer_id = None

    if lead_id and not (ledger.get_entity(lead_id) and ledger.get_entity(lead_id).entity_type == LEAD):
        lead_id = None

    rsvp_id = id_generator.generate("RSVP")

    entity = Entity(
        id=rsvp_id,
        entity_type=EVENT_RSVP,
        attributes={
            "event_id": event_id,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "name": name or "Guest",
            "phone": phone or "",
            "email": email or "",
            "status": "invited" if source == "invited" else "confirmed",
            "source": source,
            "created_at": _now(),
            "updated_at": _now(),
            "promoted_to_lead_id": None,
        },
    )

    ledger.add_entity(entity)

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return entity


def get_rsvp(rsvp_id):

    entity = ledger.get_entity(rsvp_id)

    if entity and entity.entity_type == EVENT_RSVP:
        return entity

    return None


def update_rsvp_status(rsvp_id, status):

    if status not in RSVP_STATUSES:
        return {"error": f"status must be one of {', '.join(RSVP_STATUSES)}"}

    entity = get_rsvp(rsvp_id)

    if not entity:
        return {"error": "RSVP not found"}

    entity.attributes["status"] = status
    entity.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return entity


def list_event_rsvps(event_id, status=None):

    rsvps = [e for e in ledger.get_all().values() if e.entity_type == EVENT_RSVP and e.attributes.get("event_id") == event_id]

    if status:
        rsvps = [r for r in rsvps if r.attributes.get("status") == status]

    rsvps.sort(key=lambda r: r.attributes.get("created_at", ""))

    return rsvps


def get_event_detail(event_id):

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    rsvps = list_event_rsvps(event_id)

    by_status = {}
    for r in rsvps:
        s = r.attributes.get("status", "invited")
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "event": {"id": event.id, **event.attributes},
        "rsvp_summary": by_status,
        "rsvps": [{"id": r.id, **r.attributes} for r in rsvps],
    }


def promote_rsvp_to_lead(rsvp_id, promoted_by, assign_to_employee_id=None):
    """The post-event CRM tie-in: turns an attendee into a real new Lead
    (source="Event"), same promote mechanism as core/trigger_alerts.py's
    promote_alert() -- GENERATED_LEAD back to the originating Customer when the RSVP
    was tied to one, optional one-click assignment to a salesperson."""

    rsvp = get_rsvp(rsvp_id)

    if not rsvp:
        return {"error": "RSVP not found"}

    if rsvp.attributes.get("promoted_to_lead_id"):
        return {"error": "This RSVP has already been promoted to a Lead"}

    name_parts = (rsvp.attributes.get("name") or "Guest").split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    customer_id = rsvp.attributes.get("customer_id")
    customer = ledger.get_entity(customer_id) if customer_id else None

    if customer and customer.entity_type == CUSTOMER:
        first_name = customer.attributes.get("FirstName", first_name)
        last_name = customer.attributes.get("LastName", last_name)

    lead = create_lead(
        promoted_by,
        first_name,
        last_name,
        "Event",
        phone=rsvp.attributes.get("phone"),
        email=rsvp.attributes.get("email"),
    )

    if customer and customer.entity_type == CUSTOMER:
        ledger.add_relationship(
            Relationship(source_id=customer.id, target_id=lead.id, relationship_type=GENERATED_LEAD)
        )

    if assign_to_employee_id:
        from core.lead_assignment import assign_lead
        assign_lead(lead.id, assign_to_employee_id)

    rsvp.attributes["promoted_to_lead_id"] = lead.id
    rsvp.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return {"rsvp": rsvp, "lead": lead}
