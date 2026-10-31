"""
core/orphan_owner_mining.py -- Orphan Owner Mining (session 105 follow-up), the
ninth of Sam's ~10 "completely missing" dealership workflows (Up System, BDC,
Manager TO, Demo Drive, Credit App, eSignature, F&I Workflow, Delivery Checklist,
Lost Sale Recovery, Orphan Owner Mining -- session 92's original spec).

Real dealership definition: an "orphan owner" is a customer who owns a vehicle but
has no salesperson currently working that relationship -- classically because the
original selling rep left the dealership. This codebase has no Employee
termination/departure field anywhere (confirmed absent by grep -- the same finding
sessions 65 and 94 already made independently), so "the rep who sold this left the
company" can't be computed honestly here.

What IS real and buildable, confirmed by querying the live seed graph before writing
any code: this graph has 630 real OWNS relationships across 315 distinct Customers,
but only 5 funded Deals exist connecting any of that ownership back to a salesperson
(via Deal.customer_id + Deal.created_by) -- meaning 310 of those 315 owning
customers have ZERO traceable salesperson attribution on file at all (their
ownership predates this dealership's live Deal Desk usage -- e.g. a historical
vehicle-import). That gap -- real, current ownership with no rep ever attributed to
it -- is this module's actual "orphan" definition: nobody is presently working this
relationship, regardless of the reason why. Once a real Employee-departure field
exists in this codebase, that would be a second, narrower source of orphans worth
adding here; flagged, not guessed at.

claim_orphan_owner() is the literal "mine this owner" action, and the real "tightly
integrate into the CRM" mechanism: it creates a real new Lead (Source="Orphan Owner
Mining") auto-assigned to the claiming salesperson via core/lead_intake.py's
create_lead() (the same ASSIGNED_TO mechanism every other lead gets), tied back to
the originating Customer via a real GENERATED_LEAD relationship -- the identical
precedent session 84's promote_alert()/promote_rsvp_to_lead() and session 85's
promote_session_to_lead() already established, reused rather than reinvented. Once
claimed, that customer drops out of the unclaimed queue automatically -- detected by
an existing outgoing GENERATED_LEAD relationship whose target Lead has
Source=="Orphan Owner Mining", no new entity type or relationship needed.
"""

from core.dealeros import ledger
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, DEAL, SERVICE_RECORD, LEAD
from core.relationship_types import OWNS, AUTHORIZED, GENERATED_LEAD
from core.lead_intake import create_lead
from core.field_notes import create_field_note
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _relationships_from(entity_id, relationship_type):
    return [
        r for r in ledger.get_relationships()
        if r.source_id == entity_id and r.relationship_type == relationship_type
    ]


def _vehicles_owned(customer_id):
    return [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, OWNS)
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == VEHICLE
    ]


def _funded_deals_by_customer():
    by_customer = {}
    for d in _entities(DEAL):
        if d.attributes.get("status") == "funded":
            by_customer.setdefault(d.attributes.get("customer_id"), []).append(d)
    return by_customer


def _has_salesperson_attribution(customer_id, funded_by_customer):
    deals = funded_by_customer.get(customer_id) or []
    return any(d.attributes.get("created_by") for d in deals)


def _already_claimed(customer_id):
    """Returns the real Lead this customer was already mined into, or None."""

    for r in _relationships_from(customer_id, GENERATED_LEAD):
        lead = ledger.get_entity(r.target_id)
        if lead and lead.entity_type == LEAD and lead.attributes.get("Source") == "Orphan Owner Mining":
            return lead

    return None


def _service_recency(customer_id):

    records = [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, AUTHORIZED)
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == SERVICE_RECORD
    ]
    dates = [r.attributes.get("ServiceDate") for r in records if r.attributes.get("ServiceDate")]

    return {
        "visit_count": len(records),
        "most_recent_service_date": max(dates) if dates else None,
    }


def _customer_brief(customer):
    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
        "email": customer.attributes.get("Email"),
        "phone": customer.attributes.get("Phone"),
    }


def _vehicle_brief(v):
    return {
        "id": v.id,
        "vin": v.attributes.get("VIN"),
        "description": f"{v.attributes.get('Year', '')} {v.attributes.get('Make', '')} {v.attributes.get('Model', '')}".strip() or v.id,
    }


def _orphan_entry(customer, vehicles, claimed_lead=None):

    entry = {
        "customer": _customer_brief(customer),
        "vehicles_owned": {"count": len(vehicles), "vehicles": [_vehicle_brief(v) for v in vehicles]},
        "service_history": _service_recency(customer.id),
        "claimed": False,
        "claimed_lead_id": None,
        "claimed_by": None,
    }

    if claimed_lead:
        entry["claimed"] = True
        entry["claimed_lead_id"] = claimed_lead.id
        entry["claimed_by"] = claimed_lead.attributes.get("AssignedSalesperson")

    return entry


def get_orphan_owners(limit=50, include_claimed=False):
    """Every real Customer who owns >=1 Vehicle with zero traceable salesperson
    attribution on file -- see module docstring. `include_claimed=True` also returns
    already-claimed owners (with `claimed`/`claimed_lead_id`/`claimed_by`
    populated), for a full-history view rather than just the actionable queue.
    Sorted by vehicles owned (most first), then most recent service visit -- a real,
    if simple, prioritization: an owner with multiple vehicles or a recent service
    visit is a warmer reconquest candidate than one with neither."""

    funded_by_customer = _funded_deals_by_customer()

    owns_rels = [r for r in ledger.get_relationships() if r.relationship_type == OWNS]
    owner_ids = []
    seen = set()
    for r in owns_rels:
        if r.source_id not in seen:
            seen.add(r.source_id)
            owner_ids.append(r.source_id)

    results = []
    for cid in owner_ids:

        customer = ledger.get_entity(cid)
        if not customer or customer.entity_type != CUSTOMER:
            continue

        if _has_salesperson_attribution(cid, funded_by_customer):
            continue

        claimed_lead = _already_claimed(cid)
        if claimed_lead and not include_claimed:
            continue

        vehicles = _vehicles_owned(cid)
        results.append(_orphan_entry(customer, vehicles, claimed_lead=claimed_lead))

    results.sort(
        key=lambda e: (e["vehicles_owned"]["count"], e["service_history"]["most_recent_service_date"] or ""),
        reverse=True,
    )

    return results[:limit]


def get_orphan_owner_detail(customer_id):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return {"error": "Customer not found"}

    vehicles = _vehicles_owned(customer_id)

    if not vehicles:
        return {"error": "This customer has no vehicle ownership on file -- not an orphan-owner candidate"}

    claimed_lead = _already_claimed(customer_id)
    funded_by_customer = _funded_deals_by_customer()

    entry = _orphan_entry(customer, vehicles, claimed_lead=claimed_lead)
    entry["has_salesperson_attribution"] = _has_salesperson_attribution(customer_id, funded_by_customer)

    return entry


def claim_orphan_owner(customer_id, claimed_by, note=None):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return {"error": "Customer not found"}

    vehicles = _vehicles_owned(customer_id)

    if not vehicles:
        return {"error": "This customer has no vehicle ownership on file -- not an orphan-owner candidate"}

    funded_by_customer = _funded_deals_by_customer()

    if _has_salesperson_attribution(customer_id, funded_by_customer):
        return {"error": "This customer already has a real funded deal on file with a salesperson attributed -- not an orphan owner"}

    existing = _already_claimed(customer_id)

    if existing:
        return {"error": f"Already claimed -- Lead {existing.id} (assigned to {existing.attributes.get('AssignedSalesperson')})"}

    vehicle = vehicles[0]

    lead = create_lead(
        claimed_by,
        customer.attributes.get("FirstName", ""),
        customer.attributes.get("LastName", ""),
        "Orphan Owner Mining",
        phone=customer.attributes.get("Phone"),
        email=customer.attributes.get("Email"),
        city=customer.attributes.get("City"),
        state=customer.attributes.get("State"),
        vin=vehicle.attributes.get("VIN"),
    )

    ledger.add_relationship(
        Relationship(source_id=customer.id, target_id=lead.id, relationship_type=GENERATED_LEAD)
    )
    save_graph(GRAPH_PATH)

    if note:
        create_field_note(
            department="Sales",
            category="recovery_attempt",
            body=note,
            created_by=claimed_by,
            linked_entity_id=customer.id,
        )

    return {
        "lead_id": lead.id,
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "assigned_to": claimed_by,
    }


def get_orphan_owner_stats():

    all_orphans = get_orphan_owners(limit=100000, include_claimed=True)
    unclaimed = [o for o in all_orphans if not o["claimed"]]
    claimed = [o for o in all_orphans if o["claimed"]]
    total_vehicles = sum(o["vehicles_owned"]["count"] for o in all_orphans)

    return {
        "total_orphan_owners": len(all_orphans),
        "unclaimed": len(unclaimed),
        "claimed": len(claimed),
        "total_vehicles_represented": total_vehicles,
    }
