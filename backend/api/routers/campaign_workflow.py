"""Evidence-backed campaign response work over canonical dealership records.

No provider send, financial posting, invented conversion or causal revenue claim.
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as store
from core.appointments import create_appointment, update_status, appointment_lock, APPOINTMENT_TYPES
from core.entities import Entity

router = APIRouter(prefix="/marketing/workflow", tags=["campaign outcomes"])
CASE, SIGNAL = "CampaignResponseWork", "CampaignResponseSignal"
QUALIFYING = {"reply", "call", "booking_request"}


def auth(header):
    payload, error = _authenticate(header)
    if error:
        raise HTTPException(401, "Sign in to access campaign responses")
    if payload["role"] not in {"ADMIN", "OPERATIONS", "MARKETING", "BDC", "SALES", "SERVICE"}:
        raise HTTPException(403, "Campaign response access required")
    return payload


def allowed(payload, department):
    if payload["role"] == "SERVICE" and department != "Service" or payload["role"] == "SALES" and department != "Sales":
        raise HTTPException(403, "This response belongs to another department")


def new(kind, attrs, actor):
    e = Entity("CWF-" + uuid4().hex, kind, {**attrs, "created_by": actor, "created_at": store.now().isoformat(), "revision": 1})
    store.ledger.add_entity(e)
    return e


def identities(person_id):
    e = store.ledger.get_entity(person_id)
    if not e or e.entity_type not in {"Lead", "Customer"}:
        raise HTTPException(422, "Choose an existing customer or lead")
    ids = {e.id}
    for r in store.ledger.get_relationships():
        if r.relationship_type == "BECAME" and e.id in {r.source_id, r.target_id}:
            ids.update((r.source_id, r.target_id))
    for key in ("ConvertedCustomerID", "ConvertedFromLeadID"):
        if e.attributes.get(key):
            ids.add(e.attributes[key])
    return {i for i in ids if store.ledger.get_entity(i)}


def find_case(case_id, payload):
    e = store.find(case_id, CASE)
    allowed(payload, e.attributes["department"])
    return e


def audit(e, actor, event, detail):
    e.attributes.setdefault("history", []).append({"at": store.now().isoformat(), "actor": actor, "event": event, "detail": detail})
    e.attributes["revision"] += 1
    new("FieldNote", {"department": e.attributes["department"], "category": "general", "linked_entity_id": e.attributes["person_id"], "body": f"Campaign response {e.id}: {event}. {detail}"}, actor)


def money(value):
    try:
        amount = Decimal(str(value))
        return float(amount.quantize(Decimal("0.01"))) if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def outcome_person(e):
    if e.entity_type == "Deal":
        return e.attributes.get("customer_id")
    linked = {r.source_id for r in store.ledger.get_entity_relationships(e.id) if r.target_id == e.id and r.relationship_type == "AUTHORIZED"}
    if linked:
        return next(iter(linked)) if len(linked) == 1 else None
    key = e.attributes.get("CustomerID")
    matches = [c.id for c in store.all_of("Customer") if key and (c.id == key or c.attributes.get("CustomerID") == key)]
    return matches[0] if len(matches) == 1 else None


def projection(e):
    a = store.serial(e)
    person = store.ledger.get_entity(a["person_id"])
    a["person_name"] = store.crm.name(person) if person else a["person_id"]
    appt = store.ledger.get_entity(a.get("appointment_id"))
    outcome = store.ledger.get_entity(a.get("outcome_id"))
    a["appointment_status"] = appt.attributes.get("status") if appt else None
    a["stage"] = "closed" if a.get("closed") else "response_due"
    a["recorded_value"] = None
    a["currency"] = None
    a["outcome_status"] = None
    if not a.get("closed") and appt:
        status = appt.attributes.get("status")
        a["stage"] = "recover_appointment" if status in {"no_show", "cancelled"} else "awaiting_outcome" if status == "completed" else "visit_in_progress" if status == "arrived" else "appointment_booked"
    if outcome:
        status = outcome.attributes.get("status") if outcome.entity_type == "Deal" else outcome.attributes.get("Status")
        a["outcome_status"] = status
        complete = status == ("funded" if outcome.entity_type == "Deal" else "Completed")
        if complete:
            a["stage"] = "sale_completed" if outcome.entity_type == "Deal" else "service_completed"
            value = outcome.attributes.get("contract", {}).get("sale_price") if outcome.entity_type == "Deal" else outcome.attributes.get("Cost")
            a["recorded_value"] = money(value)
            a["currency"] = outcome.attributes.get("currency") or outcome.attributes.get("Currency") or "Unspecified"
    a["overdue"] = a["stage"] in {"response_due", "recover_appointment", "awaiting_outcome"} and store.crm.timestamp(a["due_at"]) < store.now()
    a["attribution"] = "Staff-recorded campaign response and explicit record links; association, not proven incremental revenue."
    campaign = store.ledger.get_entity(a["campaign_id"])
    a["campaign_name"] = (campaign.attributes.get("name") or store.crm.name(campaign)) if campaign else a["campaign_id"]
    a["link_issues"] = []
    for kind, record in (("appointment", appt), ("outcome", outcome)):
        if a.get(kind + "_id") and (not record or not candidate(e, record, kind)):
            a["link_issues"].append("The linked " + kind + " no longer matches this customer or department")
        elif record and chronology_issue(e, record, kind):
            a["link_issues"].append(chronology_issue(e, record, kind))
    if a["link_issues"]:
        a.update(stage="attribution_review", recorded_value=None, currency=None)
    a["contact_restricted"] = bool(person and any(person.attributes.get(k) in (True, "true", "True", "1", 1) for k in ("DoNotContact", "do_not_contact", "unsubscribed")))
    return a


class Signal(store.Model):
    brief_id: str = Field(max_length=100)
    person_id: str = Field(max_length=100)
    kind: Literal["open", "click", "reply", "call", "booking_request"]
    event_key: str = Field(min_length=5, max_length=150)
    evidence: str = Field(min_length=10, max_length=1500)


def record_signal_locked(body: Signal, payload):
    actor = payload["employee_id"]
    with store._lock, store.transaction():
        brief = store.find(body.brief_id, "MarketingCampaignBrief")
        b = brief.attributes
        allowed(payload, b["department"])
        if not b.get("campaign_id"):
            raise HTTPException(422, "Link an existing campaign to the brief first")
        campaign = store.ledger.get_entity(b["campaign_id"])
        if not campaign or campaign.entity_type not in {"Campaign", store.SEQUENCE}:
            raise HTTPException(422, "The linked campaign is unavailable")
        ids = identities(body.person_id)
        previous = next((s for s in store.all_of(SIGNAL) if s.attributes["campaign_id"] == campaign.id and s.attributes["event_key"] == body.event_key), None)
        if previous:
            if any(previous.attributes[k] != getattr(body, k) for k in ("brief_id", "person_id", "kind", "evidence")):
                raise HTTPException(409, "This event reference already belongs to a different response")
            return {"signal": store.serial(previous), "replayed": True}
        case = None
        if body.kind in QUALIFYING:
            owner = store.ledger.get_entity(b.get("routing_owner_id"))
            if not owner or owner.entity_type != "Employee" or owner.attributes.get("archived"):
                raise HTTPException(422, "Set an active BDC response owner on the campaign brief first")
            case = next((c for c in store.all_of(CASE) if c.attributes["campaign_id"] == campaign.id and c.attributes["department"] == b["department"] and identities(c.attributes["person_id"]) & ids and not c.attributes.get("closed")), None)
            if case is None:
                case = new(CASE, {"brief_id": brief.id, "campaign_id": campaign.id, "person_id": body.person_id, "department": b["department"], "owner_id": owner.id, "due_at": (store.now() + timedelta(minutes=b["response_minutes"])).isoformat(), "next_step": b["next_step"], "reason": body.kind, "closed": False, "history": [], "appointment_ids": []}, actor)
            audit(case, actor, "response_recorded", body.evidence)
            # Shared customer history also stops pending canonical nurture sequences.
            new("FieldNote", {"department": b["department"], "category": "call" if body.kind == "call" else "email", "direction": "inbound", "linked_entity_id": body.person_id, "body": body.evidence, "campaign_id": campaign.id, "response_id": case.id}, actor)
            for enrollment in store.all_of(store.ENROLLMENT):
                if enrollment.attributes.get("recipient_id") in ids and enrollment.attributes.get("status") in {"active", "paused"}:
                    store.cancel_output(enrollment)
                    enrollment.attributes.update(status="stopped", reason="Qualifying campaign response recorded", revision=enrollment.attributes.get("revision", 1)+1)
                    enrollment.attributes.setdefault("history", []).append({"event": "stopped", "at": store.now().isoformat(), "actor": actor, "reason": "Qualifying campaign response recorded"})
        signal = new(SIGNAL, {**body.model_dump(), "campaign_id": campaign.id, "department": b["department"], "case_id": case.id if case else None}, actor)
        return {"signal": store.serial(signal), "replayed": False}


@router.post("/signals")
def record_signal(body: Signal, authorization: str = Header(None)):
    return record_signal_locked(body, auth(authorization))


def sync_recorded_responses(payload=None):
    """Only persisted, authenticated delivery response events; safe to replay.

    Provider ingestion may call this after its event commit. Unconfigured or
    ambiguous routing remains visible for staff review instead of guessing.
    """
    payload = payload or {"role": "ADMIN", "employee_id": "provider-response"}
    routed, pending = 0, []
    for event in store.all_of(store.delivery.EVENT):
        if event.attributes.get("status") != "response":
            continue
        action = store.ledger.get_entity(event.attributes.get("action_id"))
        if not action or not action.attributes.get("sequence_id"):
            continue
        briefs = [b for b in store.all_of("MarketingCampaignBrief") if b.attributes.get("campaign_id") == action.attributes["sequence_id"]]
        if payload["role"] in {"SALES", "SERVICE"}:
            briefs = [b for b in briefs if b.attributes["department"].upper() == payload["role"]]
            if not briefs:
                continue
        if len(briefs) != 1:
            pending.append({"event_id": event.id, "reason": "Choose exactly one campaign brief for response routing"})
            continue
        try:
            result = record_signal_locked(Signal(brief_id=briefs[0].id, person_id=action.attributes["recipient_id"], kind="reply", event_key="provider:"+event.id, evidence="Verified provider response event " + event.id + " for message " + action.id), payload)
            routed += not result["replayed"]
        except HTTPException as exc:
            pending.append({"event_id": event.id, "reason": str(exc.detail)})
    return {"routed": routed, "pending": pending}


@router.post("/sync")
def sync(authorization: str = Header(None)):
    return sync_recorded_responses(auth(authorization))


@router.get("")
def listing(authorization: str = Header(None)):
    p = auth(authorization)
    departments = {"Service"} if p["role"] == "SERVICE" else {"Sales"} if p["role"] == "SALES" else {"Sales", "Service"}
    cases = [projection(e) for e in store.all_of(CASE) if e.attributes["department"] in departments]
    cases.sort(key=lambda c: (not c["overdue"], c["due_at"]))
    briefs = [{"id": b.id, "name": b.attributes["name"]} for b in store.all_of("MarketingCampaignBrief") if b.attributes["department"] in departments and b.attributes.get("campaign_id")]
    return {"cases": cases, "briefs": briefs, "owners": [{"id": e.id, "name": store.crm.name(e)} for e in store.all_of("Employee") if not e.attributes.get("archived")], "signal_count": sum(s.attributes["department"] in departments for s in store.all_of(SIGNAL)), "automation": "Qualifying responses create assigned work. Appointment and outcome stages update from the linked records; opens and clicks create no agent work."}


@router.get("/people")
def people(q: str = Query(min_length=2, max_length=100), authorization: str = Header(None)):
    auth(authorization)
    return [{"id": e.id, "name": store.crm.name(e)} for e in store.ledger.get_all().values() if e.entity_type in {"Lead", "Customer"} and q.casefold() in (e.id + " " + store.crm.name(e)).casefold()][:30]


class WorkEdit(store.Model):
    revision: int = Field(ge=1)
    owner_id: str = Field(max_length=100)
    due_at: datetime
    next_step: str = Field(min_length=3, max_length=500)
    closed: bool = False
    evidence: str = Field(min_length=10, max_length=1000)


@router.put("/{case_id}")
def edit(case_id: str, body: WorkEdit, authorization: str = Header(None)):
    p = auth(authorization)
    if body.due_at.tzinfo is None:
        raise HTTPException(422, "Due time must include its timezone")
    with store._lock, store.transaction():
        e = find_case(case_id, p)
        owner = store.find(body.owner_id, "Employee")
        if owner.attributes.get("archived"):
            raise HTTPException(422, "Choose an active employee")
        store.revise(e, body.revision, body.model_dump(mode="json", exclude={"revision", "evidence"}), p["employee_id"])
        audit(e, p["employee_id"], "work_updated", body.evidence)
        return projection(e)


def check_revision(e, revision):
    if e.attributes["revision"] != revision or e.attributes.get("closed"):
        raise HTTPException(409, "Response changed or is closed. Refresh before continuing")


class Booking(store.Model):
    revision: int = Field(ge=1)
    scheduled_start: datetime
    scheduled_end: datetime
    appointment_type: str = Field(max_length=40)
    assigned_to: str = Field(max_length=100)


@router.post("/{case_id}/book")
def book(case_id: str, body: Booking, authorization: str = Header(None)):
    p = auth(authorization)
    if body.scheduled_start.tzinfo is None or body.scheduled_end.tzinfo is None or body.scheduled_start < store.now() or body.scheduled_end <= body.scheduled_start:
        raise HTTPException(422, "Choose a future start and later end with timezone information")
    with store._lock, store.transaction():
        e = find_case(case_id, p)
        check_revision(e, body.revision)
        a = e.attributes
        if a.get("outcome_id"):
            raise HTTPException(409, "This response already has an outcome; review its links before booking again")
        ids = identities(a["person_id"])
        employee = store.find(body.assigned_to, "Employee")
        if employee.attributes.get("archived"):
            raise HTTPException(422, "Choose an active appointment owner")
        if body.appointment_type not in APPOINTMENT_TYPES[a["department"]]:
            raise HTTPException(422, "Choose a valid appointment type for this department")
        for appt in store.all_of("Appointment"):
            x = appt.attributes
            if x.get("status") not in {"scheduled", "confirmed", "arrived"}:
                continue
            if x.get("department") == a["department"] and ids & {x.get("customer_id"), x.get("lead_id")}:
                raise HTTPException(409, "This person already has an open appointment. Link that appointment instead")
            start = store.crm.timestamp(x.get("scheduled_start"))
            end = store.crm.timestamp(x.get("scheduled_end")) or (start + timedelta(minutes=30) if start else None)
            if start and end and x.get("assigned_to") == body.assigned_to and body.scheduled_start < end and body.scheduled_end > start:
                raise HTTPException(409, "This employee already has an overlapping appointment")
        customer = next((i for i in ids if store.ledger.get_entity(i).entity_type == "Customer"), None)
        lead = next((i for i in ids if store.ledger.get_entity(i).entity_type == "Lead"), None)
        appt = create_appointment(a["department"], body.appointment_type, body.scheduled_start.isoformat(), p["employee_id"], assigned_to=body.assigned_to, customer_id=customer, lead_id=lead, scheduled_end=body.scheduled_end.isoformat(), notes=f"Campaign response {e.id}", _persist=False)
        if isinstance(appt, dict):
            raise HTTPException(422, appt["error"])
        appt.attributes.update(campaign_response_id=e.id, campaign_id=a["campaign_id"])
        a["appointment_id"] = appt.id
        a["appointment_ids"].append(appt.id)
        audit(e, p["employee_id"], "appointment_booked", appt.id)
        return projection(e)


class Link(store.Model):
    revision: int = Field(ge=1)
    record_id: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=10, max_length=1000)


class AppointmentStatus(store.Model):
    revision: int = Field(ge=1)
    expected_status: str
    status: Literal["confirmed", "arrived", "completed", "no_show", "cancelled"]


@router.post("/{case_id}/appointment-status")
def appointment_status(case_id: str, body: AppointmentStatus, authorization: str = Header(None)):
    p = auth(authorization)
    with store._lock:
        e = find_case(case_id, p)
        check_revision(e, body.revision)
        if e.attributes.get("closed"):
            raise HTTPException(409, "Reopen this response before changing its appointment")
        appt = store.find(e.attributes.get("appointment_id"), "Appointment")
        with appointment_lock(appt.id):
            current = appt.attributes.get("status")
            transitions = {"scheduled": {"confirmed", "arrived", "no_show", "cancelled"}, "confirmed": {"arrived", "no_show", "cancelled"}, "arrived": {"completed", "cancelled"}}
            if current != body.expected_status or body.status not in transitions.get(current, set()):
                raise HTTPException(409, "Appointment changed or this transition is unavailable. Refresh first")
            result = update_status(appt.id, body.status, p["employee_id"])
            if isinstance(result, dict):
                raise HTTPException(422, result["error"])
        return projection(e)


def candidate(e, record, kind):
    ids = identities(e.attributes["person_id"])
    a = record.attributes
    if kind == "appointment":
        return record.entity_type == "Appointment" and a.get("department") == e.attributes["department"] and bool(ids & {a.get("customer_id"), a.get("lead_id")})
    expected = "Deal" if e.attributes["department"] == "Sales" else "ServiceRecord"
    return record.entity_type == expected and outcome_person(record) in ids


def chronology_issue(e, record, kind):
    occurred = store.crm.timestamp(record.attributes.get("scheduled_start") if kind == "appointment" else record.attributes.get("funded_at") or record.attributes.get("ServiceDate") or record.attributes.get("created_at"))
    if occurred and occurred.date() < store.crm.timestamp(e.attributes["created_at"]).date():
        return "This record predates the campaign response"
    if kind == "outcome" and occurred:
        appointment = store.ledger.get_entity(e.attributes.get("appointment_id"))
        visit = store.crm.timestamp(appointment.attributes.get("scheduled_start")) if appointment else None
        if visit and occurred.date() < visit.date():
            return "This outcome predates the linked appointment"
    return ""


@router.get("/{case_id}/links")
def links(case_id: str, authorization: str = Header(None)):
    p = auth(authorization)
    e = find_case(case_id, p)
    return {kind: [{"id": r.id, "label": r.id + " · " + str(r.attributes.get("scheduled_start") or r.attributes.get("ServiceDate") or r.attributes.get("status") or "")} for r in store.ledger.get_all().values() if candidate(e, r, kind)] for kind in ("appointment", "outcome")}


@router.post("/{case_id}/link/{kind}")
def link(case_id: str, kind: Literal["appointment", "outcome"], body: Link, authorization: str = Header(None)):
    p = auth(authorization)
    with store._lock, store.transaction():
        e = find_case(case_id, p)
        check_revision(e, body.revision)
        record = store.ledger.get_entity(body.record_id)
        if not record or not candidate(e, record, kind):
            raise HTTPException(422, "Choose a matching record for the same customer and department")
        if kind == "outcome" and not e.attributes.get("appointment_id"):
            raise HTTPException(422, "Link the appointment before its sale or service outcome")
        issue = chronology_issue(e, record, kind)
        if issue:
            raise HTTPException(422, issue)
        key = kind + "_id"
        if any(c.id != e.id and c.attributes.get(key) == record.id for c in store.all_of(CASE)):
            raise HTTPException(409, "This record is already attributed to another response; resolve that link first")
        if e.attributes.get(key) and e.attributes[key] != record.id:
            raise HTTPException(409, "Remove the existing attribution link before replacing it")
        e.attributes[key] = record.id
        if kind == "appointment" and record.id not in e.attributes["appointment_ids"]:
            e.attributes["appointment_ids"].append(record.id)
        audit(e, p["employee_id"], kind + "_linked", record.id + ": " + body.evidence)
        return projection(e)


@router.post("/{case_id}/unlink/{kind}")
def unlink(case_id: str, kind: Literal["appointment", "outcome"], body: Link, authorization: str = Header(None)):
    p = auth(authorization)
    with store._lock, store.transaction():
        e = find_case(case_id, p)
        check_revision(e, body.revision)
        if e.attributes.get(kind + "_id") != body.record_id:
            raise HTTPException(409, "The link changed. Refresh first")
        if kind == "appointment" and e.attributes.get("outcome_id"):
            raise HTTPException(409, "Remove the outcome link first")
        e.attributes.pop(kind + "_id", None)
        audit(e, p["employee_id"], kind + "_unlinked", body.record_id + ": " + body.evidence)
        return projection(e)
