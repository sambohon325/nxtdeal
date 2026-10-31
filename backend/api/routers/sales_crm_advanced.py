"""Advanced Sales CRM operations on the canonical graph.

Sequences schedule tasks and approval drafts, never provider sends. Single-process
scheduling matches the current graph authority; no independent customer database.
"""
import hashlib
import json
import re
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.deps import _authenticate
from api.routers import sales_crm as crm
from api.routers import marketing_operations as delivery
from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

router = APIRouter(prefix="/sales/crm", tags=["Sales CRM automation"])
# Share the delivery lock so stopping a sequence cannot race approval/dispatch.
_lock = delivery._lock
SEGMENT, SEQUENCE, ENROLLMENT, MERGE = "SalesCrmSegment", "SalesCrmSequence", "SalesCrmEnrollment", "SalesCrmMergeAudit"
FIELDS = {"kind": "text", "name": "text", "email": "text", "phone": "text", "owner_id": "text", "stage": "text", "source": "text", "vehicle": "text", "open_tasks": "number", "overdue_tasks": "number", "created_at": "date", "last_contact": "date"}
CONTACT_FIELDS = ("Name", "FirstName", "LastName", "Email", "Phone")


def now():
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def admin(authorization):
    actor = crm.authorized(authorization)
    payload, _ = _authenticate(authorization)
    if payload["role"] not in {"ADMIN", "OPERATIONS"}:
        raise HTTPException(403, "Admin or Operations role required to merge records")
    return actor


def find(entity_id, kind):
    e = ledger.get_entity(entity_id)
    if not e or e.entity_type != kind:
        raise HTTPException(404, "Record not found")
    return e


def serial(e):
    return {"id": e.id, **deepcopy(e.attributes)}


def all_of(kind):
    return [e for e in list(ledger.get_all().values()) if e.entity_type == kind]


@contextmanager
def transaction():
    # All mutations here are synchronous and protected by the shared sequence/
    # delivery lock. Restore in-memory state too if atomic graph persistence fails.
    entities, relationships = deepcopy(ledger.entities), deepcopy(ledger.relationships)
    try:
        yield
        save_graph(GRAPH_PATH)
    except Exception:
        ledger.entities, ledger.relationships = entities, relationships
        raise


def create(prefix, kind, attrs, actor):
    e = Entity(id_generator.generate(prefix), kind, {**attrs, "created_by": actor, "created_at": now().isoformat(), "updated_at": now().isoformat(), "revision": 1})
    ledger.add_entity(e)
    return e


def revise(e, revision, patch, actor):
    if e.attributes["revision"] != revision:
        raise HTTPException(409, "Record changed. Reload before saving.")
    e.attributes.update({**patch, "revision": revision + 1, "updated_at": now().isoformat(), "updated_by": actor})


class Condition(Model):
    field: str
    op: Literal["eq", "ne", "contains", "empty", "not_empty", "gt", "gte", "lt", "lte", "before", "after"]
    value: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def valid(self):
        kind = FIELDS.get(self.field)
        allowed = {"empty", "not_empty", "eq", "ne"}
        allowed |= {"contains"} if kind == "text" else {"gt", "gte", "lt", "lte"} if kind == "number" else {"before", "after"}
        if kind is None or self.op not in allowed:
            raise ValueError("Unsupported field/operator")
        if self.op not in {"empty", "not_empty"}:
            if not self.value:
                raise ValueError("A value is required")
            if kind == "number" and not re.fullmatch(r"\d{1,9}", self.value):
                raise ValueError("Use a non-negative whole number")
            if kind == "date" and crm.timestamp(self.value) is None:
                raise ValueError("Use an ISO date")
        return self


class Group(Model):
    conditions: list[Condition] = Field(min_length=1, max_length=12)


class Rules(Model):
    # OR across groups, AND within each group: explicit bounded boolean rules.
    groups: list[Group] = Field(min_length=1, max_length=8)


class Segment(Rules):
    name: str = Field(min_length=1, max_length=100)
    shared: bool = False
    archived: bool = False


class SegmentEdit(Segment):
    revision: int = Field(ge=1, strict=True)


def matches(row, rule):
    for group in rule["groups"]:
        matched = True
        for c in group["conditions"]:
            actual = " ".join(v["label"] + " " + str(v["vin"]) for v in row["vehicles"]) if c["field"] == "vehicle" else row.get(c["field"])
            op, expected = c["op"], c["value"]
            if op in {"empty", "not_empty"}:
                result = (actual is None or actual == "") == (op == "empty")
            elif actual is None or actual == "":
                result = False
            else:
                kind = FIELDS[c["field"]]
                a, b = (int(actual), int(expected)) if kind == "number" else (crm.timestamp(actual), crm.timestamp(expected)) if kind == "date" else (str(actual).casefold(), expected.casefold())
                if a is None or b is None:
                    result = False
                elif op == "contains":
                    result = b in a
                else:
                    result = {"eq": lambda: a == b, "ne": lambda: a != b, "gt": lambda: a > b, "gte": lambda: a >= b, "lt": lambda: a < b, "lte": lambda: a <= b, "before": lambda: a < b, "after": lambda: a > b}[op]()
            matched &= result
        if matched:
            return True
    return False


def segment_access(e, actor, write=False):
    if e.attributes["created_by"] != actor and (write or not e.attributes["shared"]):
        raise HTTPException(403, "Only the creator can change this segment; private segments are personal")


@router.get("/segments")
def segments(authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    return {"fields": FIELDS, "segments": [serial(e) for e in all_of(SEGMENT) if e.attributes["created_by"] == actor or e.attributes["shared"]]}


@router.post("/segments/preview")
def segment_preview(body: Rules, offset: int = Query(0, ge=0), authorization: str = Header(None)):
    crm.authorized(authorization)
    rows = [r for r in crm.records() if matches(r, body.model_dump())]
    return {"records": rows[offset:offset + 50], "total": len(rows), "offset": offset, "observed_at": now().isoformat()}


@router.post("/segments")
def create_segment(body: Segment, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        e = create("CRMSEG", SEGMENT, body.model_dump(), actor)
    return serial(e)


@router.put("/segments/{entity_id}")
def edit_segment(entity_id: str, body: SegmentEdit, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        e = find(entity_id, SEGMENT)
        segment_access(e, actor, True)
        revise(e, body.revision, body.model_dump(exclude={"revision"}), actor)
    return serial(e)


# Matching proposes candidates only; shared phone numbers never auto-merge people.
def identity(value, phone=False):
    value = str(value or "").strip().casefold()
    if phone:
        value = re.sub(r"\D", "", value)
        if len(value) == 11 and value.startswith("1"):
            value = value[1:]
        return value if len(value) >= 10 else ""
    return value if "@" in value else ""


@router.get("/duplicates")
def duplicates(authorization: str = Header(None)):
    crm.authorized(authorization)
    index = {}
    for row in crm.records():
        for field in ("email", "phone"):
            value = identity(row[field], field == "phone")
            if value:
                index.setdefault((row["kind"], field, value), []).append(row)
    groups = [{"reason": key[1], "records": rows} for key, rows in index.items() if len(rows) > 1]
    return {"groups": groups[:100], "total_groups": len(groups), "note": "Same-type exact email/normalized phone matches; review identity before merging."}


class MergePair(Model):
    survivor_id: str = Field(max_length=100)
    duplicate_id: str = Field(max_length=100)


class MergeRequest(MergePair):
    token: str = Field(min_length=64, max_length=64)
    take_duplicate: list[Literal["Name", "FirstName", "LastName", "Email", "Phone"]] = Field(default_factory=list, max_length=5)


def pair(body):
    a, b = ledger.get_entity(body.survivor_id), ledger.get_entity(body.duplicate_id)
    if not a or not b or a.id == b.id or a.entity_type not in {"Lead", "Customer"} or a.entity_type != b.entity_type:
        raise HTTPException(422, "Choose two different records of the same type")
    if not any(identity(a.attributes.get(k), k == "Phone") and identity(a.attributes.get(k), k == "Phone") == identity(b.attributes.get(k), k == "Phone") for k in ("Email", "Phone")):
        raise HTTPException(409, "Records no longer share an exact email or normalized phone")
    return a, b


def graph_token(a, b):
    snapshot = {"pair": [a.id, b.id], "entities": [(e.id, e.entity_type, e.attributes) for e in list(ledger.entities.values())], "relationships": [vars(r) for r in ledger.relationships]}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def reference_count(value, entity_id):
    if isinstance(value, dict):
        return sum(reference_count(v, entity_id) for v in value.values())
    if isinstance(value, list):
        return sum(reference_count(v, entity_id) for v in value)
    return int(isinstance(value, str) and value == entity_id)


def replace_reference(value, source, target):
    if isinstance(value, dict):
        return {k: replace_reference(v, source, target) for k, v in value.items()}
    if isinstance(value, list):
        rewritten = [replace_reference(v, source, target) for v in value]
        if source in value and target in value:
            seen_target = False
            unique = []
            for item in rewritten:
                if item == target:
                    if seen_target:
                        continue
                    seen_target = True
                unique.append(item)
            return unique
        return rewritten
    return target if isinstance(value, str) and value == source else value


@router.post("/duplicates/preview")
def merge_preview(body: MergePair, authorization: str = Header(None)):
    crm.authorized(authorization)
    with _lock:
        a, b = pair(body)
        # A merge must not silently retarget pending provider messages or live sequences.
        blocked = [e.id for e in all_of(ENROLLMENT) if e.attributes["recipient_id"] in {a.id, b.id} and e.attributes["status"] not in {"completed", "stopped"}]
        # Identity/account links are deliberately outside CRM merge authority.
        blocked += [e.id for e in list(ledger.entities.values())
                    if (e.entity_type == "CustomerAccount" or any(k in e.entity_type.lower() for k in ("credential", "identity", "session", "authentication")))
                    and (reference_count(e.attributes, a.id) or reference_count(e.attributes, b.id))]
        blocked += [e.id for e in all_of(delivery.ACTION) if e.attributes.get("recipient_id") in {a.id, b.id} and e.attributes.get("status") in {"draft", "approved", "dispatching", "unknown"}]
        return {"token": graph_token(a, b), "survivor_id": a.id, "duplicate_id": b.id,
                "fields": [{"field": k, "survivor": a.attributes.get(k, ""), "duplicate": b.attributes.get(k, "")} for k in CONTACT_FIELDS],
                "relationships": sum(r.source_id == b.id or r.target_id == b.id for r in ledger.relationships),
                "referencing_records": sum(reference_count(e.attributes, b.id) > 0 for e in list(ledger.entities.values()) if e.entity_type not in {MERGE, "SalesCrmMergedRecord"}),
                "blocked_by": blocked, "policy": "Survivor lifecycle and ownership retained. Duplicate archived with full audit; references consolidated. Channel consent resets to false and opt-outs are retained."}


@router.post("/duplicates/merge")
def merge_records(body: MergeRequest, authorization: str = Header(None)):
    actor = admin(authorization)
    with _lock, transaction():
        a, b = pair(body)
        preview = merge_preview(MergePair(survivor_id=a.id, duplicate_id=b.id), authorization)
        if preview["token"] != body.token:
            raise HTTPException(409, "Graph changed since preview. Review the merge again.")
        if preview["blocked_by"]:
            raise HTTPException(409, "Stop active enrollments and resolve pending message actions before merging")
        before_a, before_b = deepcopy(a.attributes), deepcopy(b.attributes)
        a.attributes = replace_reference(a.attributes, b.id, a.id)
        changed = []
        for e in list(ledger.entities.values()):
            if e.id in {a.id, b.id} or e.entity_type in {MERGE, "SalesCrmMergedRecord"}:
                continue
            if reference_count(e.attributes, b.id):
                changed.append({"id": e.id, "before": deepcopy(e.attributes)})
                e.attributes = replace_reference(e.attributes, b.id, a.id)
                if e.entity_type == "SalesCrmAccount":
                    e.attributes["member_ids"] = list(dict.fromkeys(e.attributes["member_ids"]))
                    e.attributes["revision"] += 1
        relations_before = [deepcopy(vars(r)) for r in ledger.relationships if r.source_id in {a.id, b.id} or r.target_id in {a.id, b.id}]
        # Survivor's assignment wins; historical duplicate assignment is in the audit.
        ledger.relationships = [r for r in ledger.relationships if not (r.relationship_type == "ASSIGNED_TO" and r.target_id == b.id)]
        for r in ledger.relationships:
            if r.source_id == b.id: r.source_id = a.id
            if r.target_id == b.id: r.target_id = a.id
        seen, unique = set(), []
        for r in ledger.relationships:
            key = (r.source_id, r.target_id, r.relationship_type)
            affected = a.id in {r.source_id, r.target_id}
            if affected and r.source_id == r.target_id:
                continue
            if not affected or key not in seen:
                unique.append(r)
                seen.add(key)
        ledger.relationships = unique
        for key in CONTACT_FIELDS:
            if key in body.take_duplicate or not a.attributes.get(key):
                a.attributes[key] = b.attributes.get(key) or a.attributes.get(key, "")
        for key in ("DoNotContact", "do_not_contact", "unsubscribed"):
            if b.attributes.get(key) in (True, "true", "True", "1", 1):
                a.attributes[key] = True
        for channel in ("email", "sms", "voice", "whatsapp"):
            a.attributes["marketing_" + channel + "_consent"] = False
        b.entity_type = "SalesCrmMergedRecord"
        b.attributes = {"merged_into": a.id, "merged_at": now().isoformat(), "merged_by": actor, "original_kind": a.entity_type}
        audit = create("CRMMRG", MERGE, {"survivor_id": a.id, "duplicate_id": b.id, "survivor_before": before_a, "duplicate_before": before_b, "references_before": changed, "relationships_before": relations_before, "choices": body.take_duplicate}, actor)
    return {"survivor_id": a.id, "archived_id": b.id, "audit_id": audit.id}


class SequenceStep(Model):
    channel: Literal["call", "email", "sms"]
    delay_minutes: int = Field(ge=0, le=525600, strict=True)
    subject: str = Field(default="", max_length=160)
    body: str = Field(min_length=1, max_length=4000)


class Sequence(Model):
    name: str = Field(min_length=1, max_length=100)
    steps: list[SequenceStep] = Field(min_length=1, max_length=20)
    archived: bool = False


class SequenceEdit(Sequence):
    revision: int = Field(ge=1, strict=True)


class Enroll(Model):
    recipient_ids: list[str] = Field(default_factory=list, max_length=100)
    segment_id: str | None = Field(default=None, max_length=100)
    start_at: datetime

    @model_validator(mode="after")
    def valid(self):
        if bool(self.recipient_ids) == bool(self.segment_id):
            raise ValueError("Choose either recipients or a segment")
        if self.start_at.tzinfo is None:
            raise ValueError("Start time requires a timezone")
        if len(self.recipient_ids) != len(set(self.recipient_ids)):
            raise ValueError("Recipients must be unique")
        return self


class EnrollmentControl(Model):
    revision: int = Field(ge=1, strict=True)
    status: Literal["paused", "active", "stopped"]
    reason: str = Field(default="", max_length=200)


def can_edit(e, actor, authorization):
    payload, _ = _authenticate(authorization)
    if e.attributes["created_by"] != actor and payload["role"] not in {"ADMIN", "OPERATIONS"}:
        raise HTTPException(403, "Only the creator or a manager can change this sequence")


@router.get("/sequences")
def sequences(authorization: str = Header(None)):
    crm.authorized(authorization)
    return {"sequences": [serial(e) for e in all_of(SEQUENCE)], "enrollments": [serial(e) for e in all_of(ENROLLMENT)], "delivery_mode": "approval_drafts_only", "automatic_sending": False}


@router.post("/sequences")
def create_sequence(body: Sequence, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        e = create("CRMSEQ", SEQUENCE, body.model_dump(), actor)
    return serial(e)


@router.put("/sequences/{entity_id}")
def edit_sequence(entity_id: str, body: SequenceEdit, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        e = find(entity_id, SEQUENCE)
        can_edit(e, actor, authorization)
        if e.attributes.get("bdc_config"):
            raise HTTPException(409, "Edit this campaign in BDC Campaigns & follow-ups")
        revise(e, body.revision, body.model_dump(exclude={"revision"}), actor)
    return serial(e)


@router.post("/sequences/{entity_id}/enroll")
def enroll(entity_id: str, body: Enroll, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        if find(entity_id, SEQUENCE).attributes.get("bdc_config"):
            raise HTTPException(409, "Review and schedule this campaign in BDC Campaigns & follow-ups")
        result = enroll_locked(entity_id, body, actor)
    return result


def enroll_locked(entity_id, body, actor):
    """Caller owns the shared lock and persistence transaction."""
    sequence = find(entity_id, SEQUENCE)
    if sequence.attributes["archived"]:
        raise HTTPException(409, "Archived sequences cannot accept enrollments")
    ids = body.recipient_ids
    if body.segment_id:
        segment = find(body.segment_id, SEGMENT)
        segment_access(segment, actor)
        if segment.attributes["archived"]:
            raise HTTPException(409, "Segment is archived")
        ids = [r["id"] for r in crm.records() if matches(r, segment.attributes)]
    if not ids or len(ids) > 100:
        raise HTTPException(422, "Enroll between 1 and 100 matching records")
    recipients = [ledger.get_entity(rid) for rid in ids]
    if any(not e or e.entity_type not in {"Lead", "Customer"} for e in recipients):
        raise HTTPException(422, "Choose existing leads or customers")
    if any(step["channel"] == "call" for step in sequence.attributes["steps"]) and any(e.entity_type != "Lead" for e in recipients):
        raise HTTPException(422, "Call-task sequences require leads; customer sequences support email/SMS drafts")
    existing = {(e.attributes["sequence_id"], e.attributes["recipient_id"]) for e in all_of(ENROLLMENT) if e.attributes["status"] not in {"completed", "stopped"}}
    if any((entity_id, rid) in existing for rid in ids):
        raise HTTPException(409, "One or more recipients are already enrolled; no enrollments added")
    result = []
    for rid in ids:
        steps = deepcopy(sequence.attributes["steps"])
        e = create("CRMENR", ENROLLMENT, {"sequence_id": entity_id, "sequence_name": sequence.attributes["name"], "sequence_revision": sequence.attributes["revision"], "recipient_id": rid, "recipient_kind": ledger.get_entity(rid).entity_type, "steps": steps, "step_index": 0, "status": "active", "due_at": (body.start_at + timedelta(minutes=steps[0]["delay_minutes"])).isoformat(), "output_id": None, "history": [], "reason": "", "started_at": now().isoformat()}, actor)
        result.append(serial(e))
    return result


def cancel_output(e):
    output = ledger.get_entity(e.attributes.get("output_id"))
    if output and output.entity_type == delivery.ACTION and output.attributes["status"] in {"draft", "approved"}:
        output.attributes.update({"status": "cancelled", "revision": output.attributes["revision"] + 1, "updated_at": now().isoformat()})


@router.post("/enrollments/{entity_id}/status")
def enrollment_status(entity_id: str, body: EnrollmentControl, authorization: str = Header(None)):
    actor = crm.authorized(authorization)
    with _lock, transaction():
        e = find(entity_id, ENROLLMENT)
        can_edit(e, actor, authorization)
        if e.attributes["status"] in {"completed", "stopped"}:
            raise HTTPException(409, "Terminal enrollments cannot restart; enroll again explicitly")
        if body.status == "active" and e.attributes["status"] != "paused":
            raise HTTPException(409, "Only paused enrollments can resume")
        if body.status in {"paused", "stopped"}:
            output = ledger.get_entity(e.attributes.get("output_id"))
            if output and output.entity_type == delivery.ACTION and output.attributes.get("status") in {"dispatching", "unknown"}:
                raise HTTPException(409, "Reconcile the in-flight or unknown provider outcome before changing this enrollment")
            cancel_output(e)
        patch = {"status": body.status, "reason": body.reason}
        if body.status == "paused":
            patch["remaining_seconds"] = max(0, (crm.timestamp(e.attributes["due_at"]) - now()).total_seconds())
        if body.status == "active":
            output = ledger.get_entity(e.attributes.get("output_id"))
            if output and output.entity_type == delivery.ACTION and output.attributes["status"] == "cancelled":
                patch["output_id"] = None
            patch["due_at"] = (now() + timedelta(seconds=e.attributes.get("remaining_seconds", 0))).isoformat()
        e.attributes["history"].append({"event": body.status, "at": now().isoformat(), "actor": actor, "reason": body.reason})
        revise(e, body.revision, patch, actor)
    return serial(e)


def stop_reason(recipient, enrollment):
    if not recipient or recipient.entity_type not in {"Lead", "Customer"}:
        return "Recipient unavailable or merged"
    a = recipient.attributes
    if any(a.get(k) in (True, "true", "True", "1", 1) for k in ("DoNotContact", "do_not_contact", "unsubscribed")):
        return "Recipient opted out"
    if a.get("PipelineState") in {"SOLD", "LOST", "CONVERTED"} or a.get("ConvertedCustomerID"):
        return "Lead exited the sales pipeline"
    started = crm.timestamp(enrollment["started_at"])
    for e in list(ledger.entities.values()):
        attrs = e.attributes
        if e.entity_type == "Appointment" and recipient.id in {attrs.get("lead_id"), attrs.get("customer_id")} and attrs.get("status") in {"scheduled", "confirmed", "checked_in", "completed"}:
            at = crm.timestamp(attrs.get("created_at"))
            if at and at >= started:
                return "Appointment booked"
        if e.entity_type in {"FieldNote", "Communication"} and attrs.get("linked_entity_id") == recipient.id and attrs.get("direction") == "inbound" and (attrs.get("category") or attrs.get("channel")) in {"email", "text", "call", "phone", "chat"}:
            at = crm.timestamp(attrs.get("created_at"))
            if at and at >= started:
                return "Inbound reply recorded"
    for event in all_of(delivery.EVENT):
        attrs = event.attributes
        if attrs.get("status") == "response":
            action = ledger.get_entity(attrs.get("action_id"))
            at = crm.timestamp(attrs.get("created_at"))
            if action and action.attributes.get("recipient_id") == recipient.id and at and at >= started:
                return "Provider reply recorded"
    return None


def run_due(at=None):
    """Persisted cursor/output IDs make repeated ticks and restart safe. No send calls."""
    at = at or now()
    changed = 0
    with _lock:
        candidates = [e for e in all_of(ENROLLMENT) if e.attributes["status"] == "active"]
        if not candidates:
            return 0
        with transaction():
            for e in candidates:
                a = e.attributes
                reason = stop_reason(ledger.get_entity(a["recipient_id"]), a)
                if reason:
                    cancel_output(e)
                    a.update(status="stopped", reason=reason)
                elif crm.timestamp(a["due_at"]) > at:
                    continue
                else:
                    output = ledger.get_entity(a.get("output_id"))
                    if output:
                        done = output.attributes.get("completed") is True if output.entity_type == "LeadTask" else output.attributes.get("status") == "delivered"
                        if not done:
                            reason = "Awaiting task completion" if output.entity_type == "LeadTask" else "Message status: " + str(output.attributes.get("status")) + "; awaiting verified delivery. Automatic sending disabled"
                            if a["reason"] == reason:
                                continue
                            a["reason"] = reason
                        else:
                            a["history"].append({"event": "step_completed", "step": a["step_index"], "output_id": output.id, "at": at.isoformat()})
                            a["step_index"] += 1
                            a["output_id"] = None
                            if a["step_index"] >= len(a["steps"]):
                                a.update(status="completed", reason="All steps completed")
                            else:
                                a["due_at"] = (at + timedelta(minutes=a["steps"][a["step_index"]]["delay_minutes"])).isoformat()
                                a["reason"] = "Next step scheduled"
                    else:
                        step = a["steps"][a["step_index"]]
                        if step["channel"] == "call":
                            output = create("LTASK", "LeadTask", {"lead_id": a["recipient_id"], "task_type": "call", "description": step["body"], "due_at": at.isoformat(), "completed": False, "completed_at": None, "completed_by": None, "assigned_to": a["created_by"], "sequence_enrollment_id": e.id, "sequence_id": a["sequence_id"], "sequence_revision": a["sequence_revision"]}, a["created_by"])
                        else:
                            try:
                                delivery.check_recipient({"channel": step["channel"], "recipient_id": a["recipient_id"], "sequence_id": a["sequence_id"], "sequence_revision": a["sequence_revision"]})
                            except HTTPException as exc:
                                reason = str(exc.detail)
                                if a["reason"] == reason:
                                    continue
                                a["reason"] = reason
                                output = None
                            else:
                                output = create("CRMMSG", delivery.ACTION, {"channel": step["channel"], "subject": step["subject"], "body": step["body"], **({"html_body": step["html_body"]} if step.get("html_body") else {}), "inventory_snapshot": step.get("inventory_snapshot", []), "recipient_id": a["recipient_id"], "budget": 0, "scheduled_at": at.isoformat(), "run_id": None, "campaign_id": None, "status": "draft", "attempt_count": 0, "provider_reference": None, "sequence_enrollment_id": e.id, "sequence_id": a["sequence_id"], "sequence_revision": a["sequence_revision"]}, a["created_by"])
                        if output:
                            a["output_id"] = output.id
                            a["reason"] = "Task created" if step["channel"] == "call" else "Approval draft created; awaiting review"
                            a["history"].append({"event": "step_prepared", "step": a["step_index"], "output_id": output.id, "at": at.isoformat()})
                a["revision"] += 1
                a["updated_at"] = at.isoformat()
                changed += 1
    return changed


@router.post("/sequences/process-due")
def process_due(authorization: str = Header(None)):
    crm.authorized(authorization)
    return {"updated": run_due(), "automatic_sending": False}
