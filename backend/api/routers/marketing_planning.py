"""Campaign briefs share canonical references; planning never enrolls or dispatches."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Header, HTTPException
from pydantic import Field, model_validator
from api.routers import marketing_operations as ops
from api.routers.marketing_journeys import authorized, _lock

router = APIRouter(prefix="/marketing/planning", tags=["marketing planning"])
KIND = "MarketingCampaignBrief"

class Brief(ops.Model):
    name: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=3, max_length=1000)
    department: Literal["Sales", "Service"]
    starts_on: date
    ends_on: date
    budget: float = Field(ge=0, le=10000000, allow_inf_nan=False)
    currency: Literal["USD", "CAD"]
    target_appointments: int = Field(ge=0, le=100000, strict=True)
    confirmed_capacity: int | None = Field(default=None, ge=0, le=100000, strict=True)
    capacity_evidence: str = Field(default="", max_length=1000)
    audience_id: str | None = None
    campaign_id: str | None = None
    offer: str = Field(default="", max_length=2000)
    routing_owner_id: str | None = None
    response_minutes: int = Field(default=30, ge=1, le=10080, strict=True)
    next_step: str = Field(min_length=3, max_length=500)
    exclusions: str = Field(default="Exclude opted-out contacts, existing bookings and recently contacted customers.", max_length=1500)

    @model_validator(mode="after")
    def valid_window(self):
        if self.ends_on < self.starts_on:
            raise ValueError("Campaign end must be on or after its start")
        if self.confirmed_capacity is not None and not self.capacity_evidence.strip():
            raise ValueError("Record the source and date of the capacity check")
        return self

class Edit(Brief):
    revision: int = Field(ge=1, strict=True)

def references(body):
    for key, kinds in {"audience_id": {"MarketingList", "SalesCrmSegment"}, "campaign_id": {"Campaign", "SalesCrmSequence"}, "routing_owner_id": {"Employee"}}.items():
        value = getattr(body, key)
        if value:
            entity = ops.ledger.get_entity(value)
            if not entity or entity.entity_type not in kinds or entity.attributes.get("archived"):
                raise HTTPException(422, f"Choose an active existing {key.replace('_id', '').replace('_', ' ')}")
            if entity.entity_type == "SalesCrmSegment" and not entity.attributes.get("shared"):
                raise HTTPException(422, "Choose a shared segment for a cross-department brief")

def serial(entity):
    result = ops.serial(entity)
    capacity = result.get("confirmed_capacity")
    result["capacity_review"] = "unknown" if capacity is None else "shortfall" if capacity < result["target_appointments"] else "recorded_capacity_covers_target"
    result["execution_enabled"] = False
    return result

@router.get("")
def listing(authorization: str = Header(None)):
    authorized(authorization)
    with _lock:
        choices = {}
        for key, kinds in {"audiences": {"MarketingList", "SalesCrmSegment"}, "campaigns": {"Campaign", "SalesCrmSequence"}, "owners": {"Employee"}}.items():
            choices[key] = [{"id": e.id, "name": e.attributes.get("name") or e.attributes.get("Name") or " ".join(filter(None, [e.attributes.get("FirstName"), e.attributes.get("LastName")])) or e.id} for e in ops.ledger.get_all().values() if e.entity_type in kinds and not e.attributes.get("archived") and (e.entity_type != "SalesCrmSegment" or e.attributes.get("shared"))]
        return {"briefs": [serial(e) for e in ops.all_of(KIND)], "choices": choices}

@router.post("")
def create(body: Brief, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        references(body)
        entity = ops.new(KIND, {**body.model_dump(mode="json"), "created_by": actor, "status": "draft", "history": [{"actor": actor, "action": "created", "at": ops.now()}]})
        return serial(entity)

@router.put("/{brief_id}")
def edit(brief_id: str, body: Edit, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        entity = ops.get(brief_id, KIND)
        if entity.attributes["revision"] != body.revision:
            raise HTTPException(409, "This brief changed. Reload before saving.")
        references(body)
        ops.update(entity, {**body.model_dump(mode="json", exclude={"revision"}), "status": "draft", "history": [*entity.attributes["history"], {"actor": actor, "action": "edited", "at": ops.now()}]})
        return serial(entity)
