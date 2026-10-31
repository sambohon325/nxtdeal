"""Sales CRM projections over existing dealership records. No parallel customer store."""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.deps import _authenticate
from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.workflows import LEAD_WORKFLOW
from core.lead_intake import VALID_SOURCES
from core.lead_tasks import list_tasks
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

router = APIRouter(prefix="/sales/crm", tags=["sales CRM"])
from api.routers.marketing_journeys import _lock


def authorized(authorization):
    payload, error = _authenticate(authorization)
    if error:
        raise HTTPException(401, "Sign in to open Sales CRM")
    if payload["role"] not in {"ADMIN", "SALES", "OPERATIONS", "MARKETING", "BDC"}:
        raise HTTPException(403, "Sales CRM access required")
    return payload["employee_id"]


def name(entity):
    a = entity.attributes
    return str(a.get("Name") or a.get("FullName") or " ".join(str(a.get(k) or "") for k in ("FirstName", "LastName")).strip() or entity.id)


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def records():
    entities = dict(ledger.get_all())
    owners, vehicles, task_counts, contact_dates = {}, {}, {}, {}
    for r in ledger.get_relationships():
        if r.relationship_type == "ASSIGNED_TO":
            owners[r.target_id] = r.source_id
        if r.relationship_type == "INTERESTED_IN" and r.target_id in entities:
            vehicle = entities[r.target_id]
            if vehicle.entity_type == "Vehicle":
                a = vehicle.attributes
                vehicles.setdefault(r.source_id, []).append({"id": vehicle.id, "label": " ".join(str(a.get(k) or "") for k in ("Year", "Make", "Model")).strip() or vehicle.id, "vin": a.get("VIN") or ""})
    now = datetime.now(timezone.utc)
    for entity in entities.values():
        a = entity.attributes
        if entity.entity_type == "FieldNote" and a.get("category") in {"call", "text", "email", "video"}:
            linked = a.get("linked_entity_id")
            at = timestamp(a.get("created_at"))
            previous = timestamp(contact_dates.get(linked))
            if at and (previous is None or at > previous):
                contact_dates[linked] = a["created_at"]
        if entity.entity_type == "LeadTask" and not a.get("completed"):
            counts = task_counts.setdefault(a.get("lead_id"), [0, 0])
            counts[0] += 1
            due = timestamp(a.get("due_at"))
            counts[1] += int(due is not None and due < now)
    result = []
    for entity in entities.values():
        if entity.entity_type not in {"Lead", "Customer"}:
            continue
        a = entity.attributes
        owner = owners.get(entity.id) or a.get("AssignedSalesperson") or ""
        counts = task_counts.get(entity.id, [0, 0])
        # Explicit allowlist: finance/identity/credential attributes never enter the list.
        result.append({"id": entity.id, "kind": entity.entity_type, "name": name(entity),
                       "email": a.get("Email") or "", "phone": a.get("Phone") or "",
                       "owner_id": owner, "owner_name": name(entities[owner]) if owner in entities else owner,
                       "stage": a.get("PipelineState") or ("UNTRACKED" if entity.entity_type == "Lead" else "CUSTOMER"),
                       "source": a.get("Source") or "", "created_at": a.get("PipelineCreatedAt") or a.get("CreatedDate"),
                       "stage_since": a.get("PipelineStateSince"), "last_contact": contact_dates.get(entity.id) or a.get("LastContactDate"),
                       "vehicles": vehicles.get(entity.id, []), "vin": a.get("VIN") or "",
                       "open_tasks": counts[0], "overdue_tasks": counts[1]})
    return result


@router.get("/records")
def list_records(kind: Literal["Lead", "Customer"] = "Lead", q: str = Query("", max_length=200),
                 owner: str = Query("", max_length=100), stage: str = Query("", max_length=40),
                 source: str = Query("", max_length=100), overdue: bool = False,
                 sort: Literal["name", "newest", "oldest", "overdue"] = "newest",
                 offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), authorization: str = Header(None)):
    employee = authorized(authorization)
    rows = [r for r in records() if r["kind"] == kind]
    owners = sorted({(r["owner_id"], r["owner_name"]) for r in rows if r["owner_id"]})
    sources = sorted({r["source"] for r in rows if r["source"]})
    if owner:
        rows = [r for r in rows if r["owner_id"] == (employee if owner == "mine" else "" if owner == "unassigned" else owner)]
    if stage:
        rows = [r for r in rows if r["stage"] == stage]
    if source:
        rows = [r for r in rows if r["source"] == source]
    if overdue:
        rows = [r for r in rows if r["overdue_tasks"] > 0]
    if q.strip():
        term = q.strip().casefold()
        rows = [r for r in rows if term in " ".join(str(r[k] or "") for k in ("id", "name", "email", "phone", "vin", "owner_name")).casefold() or any(term in (v["label"] + " " + str(v["vin"])).casefold() for v in r["vehicles"])]
    stage_counts = {s: sum(r["stage"] == s for r in rows) for s in [*LEAD_WORKFLOW, "UNTRACKED", "CUSTOMER"]}
    if sort == "name":
        rows.sort(key=lambda r: (r["name"].casefold(), r["id"]))
    elif sort == "overdue":
        rows.sort(key=lambda r: (-r["overdue_tasks"], r["name"].casefold(), r["id"]))
    else:
        rows.sort(key=lambda r: (timestamp(r["created_at"]) or datetime.min.replace(tzinfo=timezone.utc), r["id"]), reverse=sort == "newest")
    return {"records": rows[offset:offset + limit], "total": len(rows), "offset": offset,
            "stage_counts": stage_counts, "states": list(LEAD_WORKFLOW), "transitions": LEAD_WORKFLOW,
            "owners": [{"id": k, "name": n} for k, n in owners], "sources": sources, "intake_sources": VALID_SOURCES,
            "observed_at": datetime.now(timezone.utc).isoformat()}


class ViewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["Lead", "Customer"] = "Lead"
    q: str = Field(default="", max_length=200)
    owner: str = Field(default="", max_length=100)
    stage: str = Field(default="", max_length=40)
    source: str = Field(default="", max_length=100)
    overdue: bool = False
    sort: Literal["name", "newest", "oldest", "overdue"] = "newest"
    layout: Literal["table", "board"] = "table"


@router.get("/tasks")
def crm_tasks(scope: Literal["mine", "all", "overdue", "completed"] = "mine", authorization: str = Header(None)):
    employee = authorized(authorization)
    now = datetime.now(timezone.utc)
    result = []
    for task in list_tasks(assigned_to=employee if scope == "mine" else None, include_completed=scope == "completed"):
        a = task.attributes
        if scope == "completed" and not a.get("completed"):
            continue
        due = timestamp(a.get("due_at"))
        if scope == "overdue" and (due is None or due >= now):
            continue
        lead = ledger.get_entity(a.get("lead_id"))
        owner = ledger.get_entity(a.get("assigned_to"))
        result.append({"id": task.id, **{key: a.get(key) for key in ("lead_id", "task_type", "description", "due_at", "completed", "completed_at", "assigned_to")},
                       "lead_name": name(lead) if lead else a.get("lead_id"), "owner_name": name(owner) if owner else a.get("assigned_to")})
    return result


@router.get("/views")
def list_views(authorization: str = Header(None)):
    employee = authorized(authorization)
    return [{"id": e.id, **deepcopy(e.attributes["view"])} for e in list(ledger.get_all().values())
            if e.entity_type == "SalesCrmView" and e.attributes.get("employee_id") == employee]


@router.post("/views")
def save_view(body: ViewInput, authorization: str = Header(None)):
    employee = authorized(authorization)
    with _lock:
        existing = [e for e in list(ledger.get_all().values()) if e.entity_type == "SalesCrmView" and e.attributes.get("employee_id") == employee]
        if any(e.attributes["view"]["name"].casefold() == body.name.casefold() for e in existing):
            raise HTTPException(409, "A saved view already has this name")
        if len(existing) >= 30:
            raise HTTPException(409, "Limit of 30 personal saved views reached")
        entity = Entity(id_generator.generate("CRMVIEW"), "SalesCrmView", {"employee_id": employee, "view": body.model_dump()})
        ledger.add_entity(entity)
        save_graph(GRAPH_PATH)
    return {"id": entity.id, **body.model_dump()}


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    account_type: Literal["household", "business", "fleet"]
    member_ids: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=2000)


class AccountUpdate(AccountInput):
    revision: int = Field(ge=1, strict=True)


def serialize_account(entity):
    data = deepcopy(entity.attributes)
    data["members"] = []
    for member_id in data["member_ids"]:
        member = ledger.get_entity(member_id)
        if member and member.entity_type in {"Customer", "Lead"}:
            data["members"].append({"id": member.id, "name": name(member), "kind": member.entity_type})
    return {"id": entity.id, **data}


def validate_members(ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Each contact can appear only once")
    for member_id in ids:
        entity = ledger.get_entity(member_id)
        if not entity or entity.entity_type not in {"Customer", "Lead"}:
            raise HTTPException(422, "Account members must be existing customers or leads")


@router.get("/accounts")
def list_accounts(authorization: str = Header(None)):
    authorized(authorization)
    return [serialize_account(e) for e in list(ledger.get_all().values()) if e.entity_type == "SalesCrmAccount"]


@router.post("/accounts")
def create_account(body: AccountInput, authorization: str = Header(None)):
    employee = authorized(authorization)
    with _lock:
        validate_members(body.member_ids)
        entity = Entity(id_generator.generate("CRMACC"), "SalesCrmAccount", {
            **body.model_dump(), "revision": 1, "created_by": employee,
            "updated_by": employee, "updated_at": datetime.now(timezone.utc).isoformat()})
        ledger.add_entity(entity)
        save_graph(GRAPH_PATH)
    return serialize_account(entity)


@router.put("/accounts/{account_id}")
def update_account(account_id: str, body: AccountUpdate, authorization: str = Header(None)):
    employee = authorized(authorization)
    with _lock:
        entity = ledger.get_entity(account_id)
        if not entity or entity.entity_type != "SalesCrmAccount":
            raise HTTPException(404, "Account not found")
        if body.revision != entity.attributes["revision"]:
            raise HTTPException(409, "This account changed. Refresh before saving.")
        validate_members(body.member_ids)
        entity.attributes.update({**body.model_dump(), "revision": body.revision + 1,
                                  "updated_by": employee, "updated_at": datetime.now(timezone.utc).isoformat()})
        save_graph(GRAPH_PATH)
    return serialize_account(entity)
