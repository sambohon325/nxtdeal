"""All interfaces enter the same authenticated department gateway."""
from typing import Literal
from hashlib import sha256

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.deps import _authenticate, _bearer_token
from core import agent_fabric as fabric
from core.department_agents import CAPABILITIES

router = APIRouter(prefix="/agent-fabric", tags=["Department agents"])


def employee(authorization: str | None = Header(None)):
    payload, error = _authenticate(authorization)
    if error or not payload.get("employee_id"):
        raise HTTPException(401, "Authenticated employee required")
    from core.auth import credential_store, verify_token, is_mfa_challenge_token
    record = credential_store.get_record(payload["employee_id"])
    if not record or record.get("disabled"):
        raise HTTPException(401, "Employee access is no longer active")
    session = verify_token(_bearer_token(authorization))
    return {**payload, "role": record["role"], "session_id": sha256(_bearer_token(authorization).encode()).hexdigest()[:24],
            "principal": "session" if session and not is_mfa_challenge_token(session) else "api"}


def call(fn, *args):
    try:
        return fn(*args)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Invocation(StrictModel):
    department: str
    capability: str
    input: dict = Field(default_factory=dict)
    provider: Literal["nxtdeal", "api", "chatgpt", "claude", "copilot", "hermes", "openclaw"] = "nxtdeal"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class AutomationRequest(StrictModel):
    record_id: str | None = None
    provider: Literal["nxtdeal", "api", "chatgpt", "claude", "copilot", "hermes", "openclaw"] = "nxtdeal"
    idempotency_key: str | None = Field(default=None, max_length=128)


class DealerPolicy(StrictModel):
    disabled: list[str] = Field(default_factory=list)
    require_approval: list[str] = Field(default_factory=list)
    employee_limits: dict[str, list[str]] = Field(default_factory=dict)
    lead_response_sla_minutes: int = Field(default=5, ge=1, le=1440)
    discount_limit: float = Field(default=1500, ge=0, allow_inf_nan=False)
    trade_appraisal_limit: float = Field(default=35000, ge=0, allow_inf_nan=False)
    max_autonomous_risk: int = Field(default=2, ge=0, le=3)

    @field_validator("disabled", "require_approval")
    @classmethod
    def known_capabilities(cls, values):
        if any(v not in CAPABILITIES for v in values):
            raise ValueError("Unknown capability")
        return values

    @field_validator("employee_limits")
    @classmethod
    def known_limits(cls, values):
        for capabilities in values.values():
            cls.known_capabilities(capabilities)
        return values


@router.get("/catalog")
def catalog(actor=Depends(employee)):
    return call(fabric.catalog, actor)


@router.get("/readiness")
def readiness(actor=Depends(employee)):
    return call(fabric.readiness, actor)


@router.get("/manifest/{department}/{provider}")
def manifest(department: str, provider: str, actor=Depends(employee)):
    return call(fabric.manifest, actor, department, provider)


@router.put("/policy")
def policy(request: DealerPolicy, actor=Depends(employee)):
    return call(fabric.set_policy, actor, request.model_dump())


@router.post("/invoke")
def invoke(request: Invocation, actor=Depends(employee)):
    return call(fabric.invoke, actor, request.department, request.capability,
                request.input, request.provider, request.idempotency_key)


@router.get("/proposals")
def proposals(actor=Depends(employee)):
    return {"proposals": call(fabric.proposals, actor)}


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, actor=Depends(employee)):
    return call(fabric.approve, actor, proposal_id)


@router.post("/proposals/{proposal_id}/execute")
def execute(proposal_id: str, actor=Depends(employee)):
    return call(fabric.execute, actor, proposal_id)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, actor=Depends(employee)):
    return call(fabric.reject, actor, proposal_id)


class ReconciliationRequest(StrictModel):
    outcome: Literal["confirmed_executed", "confirmed_not_executed"]
    evidence: str = Field(min_length=1, max_length=500)


@router.post("/proposals/{proposal_id}/reconcile")
def reconcile(proposal_id: str, request: ReconciliationRequest, actor=Depends(employee)):
    return call(fabric.reconcile, actor, proposal_id, request.outcome, request.evidence)


@router.get("/audit")
def audit(actor=Depends(employee)):
    return {"events": call(fabric.events, actor)}


@router.post("/automations/{automation_id}/run")
def run(automation_id: str, request: AutomationRequest, actor=Depends(employee)):
    return call(fabric.run_automation, actor, automation_id, request.record_id,
                request.provider, request.idempotency_key)


class SubscriptionRequest(StrictModel):
    enabled: bool


@router.get("/subscriptions")
def subscriptions(actor=Depends(employee)):
    from core.agent_events import subscriptions
    return {"subscriptions": subscriptions(actor)}


@router.put("/subscriptions/{automation_id}")
def subscribe(automation_id: str, request: SubscriptionRequest, actor=Depends(employee)):
    from core.agent_events import subscribe
    return {"subscriptions": call(subscribe, actor, automation_id, request.enabled)}


@router.get("/receipts")
def receipts(actor=Depends(employee)):
    from core.agent_events import receipts
    return {"receipts": receipts(actor)}


@router.post("/events/process")
def process(actor=Depends(employee)):
    if actor["role"] != "ADMIN":
        raise HTTPException(403, "Administrator role required")
    from core.agent_events import tick
    return call(tick)
