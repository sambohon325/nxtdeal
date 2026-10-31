"""Marketing journey plans over the canonical dealer graph; never dispatches messages."""
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import _authenticate
from core.dealeros import ledger
from core.entities import Entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

router = APIRouter(prefix="/marketing/journeys", tags=["marketing journeys"])
ENTITY_TYPE = "MarketingJourneyPlan"
_lock = RLock()
Objective = Literal["lead_nurture", "lost_lead_recovery", "service_retention", "equity_upgrade", "ownership_onboarding", "review_and_referral"]
Trigger = Literal["lead_created", "lead_status_changed", "vehicle_purchased", "service_due", "equity_threshold", "manual_audience"]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: Literal["wait", "email", "sms", "condition", "sales_handoff"]
    label: str = Field(min_length=1, max_length=100)
    delay_minutes: int = Field(default=0, ge=0, le=525600, strict=True)
    content_asset_id: str | None = Field(default=None, max_length=200)
    email_template_id: str | None = Field(default=None, max_length=200)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    objective: Objective
    trigger_type: Trigger
    audience_rule: str = Field(default="", max_length=240)
    audience_list_id: str | None = Field(default=None, max_length=200)
    steps: list[Step] = Field(min_length=1, max_length=20)


class Update(Plan):
    revision: int = Field(ge=1, strict=True)


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    status: Literal["draft", "ready", "paused", "archived"]


def authorized(authorization, write=False):
    payload, error = _authenticate(authorization)
    if error:
        raise HTTPException(401, "Sign in to access marketing journeys")
    roles = {"ADMIN", "MARKETING"} if write else {"ADMIN", "MARKETING", "OPERATIONS", "SALES", "BDC", "SERVICE", "FINANCE"}
    if payload["role"] not in roles:
        raise HTTPException(403, "Marketing/Admin role required" if write else "Marketing access required")
    return payload["employee_id"]


def serialize(entity):
    return {"id": entity.id, **deepcopy(entity.attributes), "execution_enabled": False}


def find(plan_id):
    entity = ledger.get_entity(plan_id)
    if not entity or entity.entity_type != ENTITY_TYPE:
        raise HTTPException(404, "Journey plan not found")
    return entity


def validate_assets(plan):
    if plan.audience_list_id:
        audience = ledger.get_entity(plan.audience_list_id)
        if not audience or audience.entity_type != "MarketingList" or audience.attributes.get("archived"):
            raise HTTPException(422, "Choose an active audience list in this dealership")
    for step in plan.steps:
        if step.email_template_id:
            template = ledger.get_entity(step.email_template_id)
            if step.type != "email" or not template or template.entity_type != "EmailTemplate" or template.attributes.get("channel") != "email":
                raise HTTPException(422, "Choose an existing email template in this dealership")
        if step.content_asset_id:
            asset = ledger.get_entity(step.content_asset_id)
            if not asset or asset.entity_type != "FileAsset" or asset.attributes.get("deleted"):
                raise HTTPException(422, "Content asset must reference an existing asset in this dealership")


def unique_name(name, except_id=None):
    if any(e.id != except_id and e.entity_type == ENTITY_TYPE and e.attributes.get("status") != "archived" and e.attributes.get("name", "").casefold() == name.casefold() for e in ledger.get_all().values()):
        raise HTTPException(409, "A journey plan with that name already exists")


def persist(entity, attributes):
    previous = deepcopy(entity.attributes)
    entity.attributes = attributes
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        entity.attributes = previous
        raise


def change(entity, revision, actor, patch, action):
    if entity.attributes["revision"] != revision:
        raise HTTPException(409, "This journey changed. Reload it before saving.")
    now = datetime.now(timezone.utc).isoformat()
    attrs = {**deepcopy(entity.attributes), **patch, "revision": revision + 1, "updated_at": now}
    attrs["history"].append({"action": action, "actor": actor, "recorded_at": now, "revision": revision + 1})
    persist(entity, attrs)
    return serialize(entity)


@router.get("")
def list_plans(authorization: str = Header(None)):
    authorized(authorization)
    with _lock:
        plans = [serialize(e) for e in ledger.get_all().values() if e.entity_type == ENTITY_TYPE]
    return {"journeys": sorted(plans, key=lambda p: p["updated_at"], reverse=True), "execution_enabled": False}


@router.post("")
def create_plan(request: Plan, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        unique_name(request.name)
        validate_assets(request)
        now = datetime.now(timezone.utc).isoformat()
        entity = Entity("MJRN-" + uuid4().hex, ENTITY_TYPE, {**request.model_dump(), "status": "draft", "revision": 1, "created_at": now, "updated_at": now, "created_by": actor, "history": [{"action": "created", "actor": actor, "recorded_at": now, "revision": 1}]})
        ledger.add_entity(entity)
        try:
            save_graph(GRAPH_PATH)
        except Exception:
            ledger.entities.pop(entity.id, None)
            raise
        return serialize(entity)


@router.put("/{plan_id}")
def update_plan(plan_id: str, request: Update, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        entity = find(plan_id)
        if entity.attributes["status"] == "archived":
            raise HTTPException(409, "Restore this plan to draft before editing")
        unique_name(request.name, plan_id)
        validate_assets(request)
        return change(entity, request.revision, actor, {**request.model_dump(exclude={"revision"}), "status": "draft"}, "edited")


@router.post("/{plan_id}/status")
def transition_plan(plan_id: str, request: Transition, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        entity = find(plan_id)
        if entity.attributes["status"] == "archived" and request.status != "draft":
            raise HTTPException(409, "Archived plans can only be restored to draft")
        if request.status != "archived":
            unique_name(entity.attributes["name"], plan_id)
        if request.status == "ready" and not any(s["type"] in {"email", "sms"} for s in entity.attributes["steps"]):
            raise HTTPException(422, "A ready plan requires an email or SMS step")
        if request.status == "ready":
            validate_assets(Plan(**{key: entity.attributes.get(key) for key in Plan.model_fields if key in entity.attributes}))
        return change(entity, request.revision, actor, {"status": request.status}, "status:" + request.status)
