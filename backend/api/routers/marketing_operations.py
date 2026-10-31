"""Supervised marketing planning and channel execution, in the existing dealer graph.

Every external action requires the configured human approver. Provider acceptance is
not delivery. Unknown outcomes are never automatically retried. One dealer/process,
matching the current graph authority; no donor database or credentials are imported.
"""
import hashlib
import hmac
import json
import math
import logging
import os
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.routers.marketing_journeys import _lock, authorized
from core.dealeros import ledger
from core.entities import Entity
from core import marketing_inventory
from core import marketing_delivery
from core import marketing_email_footer as email_footer
from api.routers.marketing_email_preferences import router as preferences_router
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

router = APIRouter(prefix="/marketing/operations", tags=["marketing operations"])
router.include_router(preferences_router)
AGENTS = [
    ("orchestrator", "Campaign Orchestrator", "Coordinate goals, channels, timelines and approvals"),
    ("inventory", "Inventory Scout", "Review recorded inventory and recommend merchandising"),
    ("creative", "Creative Director", "Draft copy and channel variants"),
    ("media", "Paid Media Agent", "Propose paid campaigns within an approved budget"),
    ("journey", "Customer Journey Agent", "Plan consent-aware follow-up and handoffs"),
    ("website", "Website Agent", "Draft merchandising and website improvements"),
    ("reputation", "Reputation Agent", "Draft review responses and recovery plans"),
    ("analytics", "Measurement Agent", "Explain recorded outcomes and missing evidence"),
]
CHANNELS = Literal["email", "sms", "social", "paid_media", "website", "voice", "whatsapp"]
RUN, ACTION, CONTROL, EVENT = "MarketingAgentRun", "MarketingChannelAction", "MarketingAgentControl", "MarketingProviderEvent"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActionSpec(Model):
    channel: CHANNELS
    subject: str = Field(default="", max_length=160)
    body: str = Field(min_length=1, max_length=8000)
    recipient_id: str | None = Field(default=None, max_length=100)
    budget: float = Field(default=0, ge=0, le=100000, allow_inf_nan=False)
    scheduled_at: datetime | None = None

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("A timezone is required")
        return value


class Goal(Model):
    agent_id: str = Field(default="orchestrator", max_length=40)
    goal: str = Field(min_length=3, max_length=2000)
    campaign_id: str | None = Field(default=None, max_length=100)


class GeneratedPlan(Model):
    summary: str = Field(min_length=1, max_length=6000)
    actions: list[ActionSpec] = Field(default_factory=list, max_length=20)


class EditAction(ActionSpec):
    revision: int = Field(ge=1, strict=True)


class BulkDraft(ActionSpec):
    recipient_ids: list[str] = Field(min_length=1, max_length=200)


class Decision(Model):
    revision: int = Field(ge=1, strict=True)
    decision: Literal["approve", "reject", "cancel"]
    note: str = Field(default="", max_length=1000)


class Control(Model):
    paused: bool


class Reconciliation(Model):
    provider_reference: str = Field(min_length=1, max_length=200)
    status: Literal["accepted", "delivered", "failed"]
    evidence: str = Field(min_length=10, max_length=1000)


def now():
    return datetime.now(timezone.utc).isoformat()


def serial(e):
    return {"id": e.id, **deepcopy(e.attributes)}


def all_of(kind):
    return [e for e in ledger.get_all().values() if e.entity_type == kind]


def get(entity_id, kind):
    e = ledger.get_entity(entity_id)
    if not e or e.entity_type != kind:
        raise HTTPException(404, "Record not found")
    return e


def new(kind, attrs, entity_id=None):
    e = Entity(entity_id or "MKT-" + uuid4().hex, kind, {**attrs, "created_at": now(), "updated_at": now(), "revision": 1})
    ledger.add_entity(e)
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        ledger.entities.pop(e.id, None)
        raise
    return e


def update(e, patch):
    previous = deepcopy(e.attributes)
    e.attributes = {**previous, **patch, "updated_at": now(), "revision": previous["revision"] + 1}
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        e.attributes = previous
        raise


def approver(authorization):
    actor = authorized(authorization, True)
    configured = os.getenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID", "").strip()
    if not configured or not hmac.compare_digest(actor, configured):
        raise HTTPException(403, "The configured marketing approver must approve this action")
    return actor


def provider_ready():
    url = urlparse(os.getenv("NXTDEAL_CHANNEL_GATEWAY_URL", ""))
    return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password and bool(os.getenv("NXTDEAL_CHANNEL_GATEWAY_TOKEN"))


def channel_ready(channel):
    return os.getenv("NXTDEAL_MARKETING_DELIVERY_ENABLED", "false").lower() == "true" and (marketing_delivery.configured(channel) or provider_ready())


def paused(agent_id):
    return any(e.attributes.get("agent_id") == agent_id and e.attributes.get("paused") for e in all_of(CONTROL))


def plan_goal(goal, context):
    # Reuse the installed OpenAI client and the existing Marketing kill switch.
    # No fallback content is labelled as a model-generated plan.
    from core.ai_management import is_feature_enabled, record_call_attempt
    if not is_feature_enabled("email_sms_wizard"):
        raise RuntimeError("Marketing AI is paused")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Marketing AI provider is not configured")
    from openai import OpenAI
    model = os.getenv("NXTDEAL_MARKETING_MODEL", "gpt-4o-mini")
    response = OpenAI(timeout=45, max_retries=0).chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": "You are the dealership marketing specialist specified by agent_id. Return a JSON plan matching this schema: " + json.dumps(GeneratedPlan.model_json_schema()) + ". Use only supplied facts. Do not invent results, inventory, rates, prices, delivery or integrations. No customer identifiers or recipients may be invented. Leave recipient_id null; a human will choose recipients. Actions are proposals requiring human approval. Do not claim to have performed them."}, {"role": "user", "content": json.dumps({**goal.model_dump(), "recorded_context": context})}],
    )
    plan = GeneratedPlan.model_validate_json(response.choices[0].message.content)
    record_call_attempt("email_sms_wizard", "succeeded")
    return plan, {"provider": "openai", "model": response.model, "response_id": response.id, "generated_at": now()}


def check_recipient(spec):
    if spec["channel"] not in {"email", "sms", "voice", "whatsapp"}:
        return None
    rid = spec.get("recipient_id")
    e = ledger.get_entity(rid) if rid else None
    if not e or e.entity_type not in {"Customer", "Lead"}:
        raise HTTPException(422, "Choose an existing customer or lead recipient")
    attrs = e.attributes
    if any(attrs.get(k) in (True, "true", "True", "1", 1) for k in ("DoNotContact", "do_not_contact", "unsubscribed")):
        raise HTTPException(409, "Recipient is opted out")
    permission = attrs.get("bdc_email_permissions", {}).get(spec.get("sequence_id"), {})
    scoped_email = (spec["channel"] == "email" and bool(permission) and permission.get("revision") == spec.get("sequence_revision"))
    if attrs.get("marketing_" + spec["channel"] + "_consent") is not True and not scoped_email:
        raise HTTPException(409, "Explicit channel marketing consent is not recorded")
    keys = ("email", "Email", "email_address") if spec["channel"] == "email" else ("phone", "Phone", "phone_number", "mobile", "cell")
    contact = next((attrs[k] for k in keys if isinstance(attrs.get(k), str) and attrs[k].strip()), None)
    if not contact:
        raise HTTPException(422, "Recipient has no contact address for this channel")
    if spec["channel"] == "email" and email_footer.is_suppressed(contact):
        raise HTTPException(409, "Recipient has unsubscribed from marketing email")
    return contact


@router.get("")
def overview(authorization: str = Header(None)):
    actor = authorized(authorization)
    with _lock:
        return {"can_approve": bool(os.getenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID")) and actor == os.getenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID"), "agents": [{"id": key, "name": name, "role": role, "paused": paused(key)} for key, name, role in AGENTS], "runs": [serial(e) for e in sorted(all_of(RUN), key=lambda e: e.attributes["created_at"], reverse=True)[:50]], "actions": [serial(e) for e in sorted(all_of(ACTION), key=lambda e: e.attributes["created_at"], reverse=True)[:200]], "events": [serial(e) for e in sorted(all_of(EVENT), key=lambda e: e.attributes["created_at"], reverse=True)[:100]], "provider_configured": any(channel_ready(c) for c in ("email", "sms", "social", "paid_media", "website", "voice", "whatsapp")), "channels": {c: bool(channel_ready(c)) for c in ("email", "sms", "social", "paid_media", "website", "voice", "whatsapp")}, "approver_configured": bool(os.getenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID")), "ai_configured": bool(os.getenv("OPENAI_API_KEY")), "execution_mode": "human_approved", "delivery_verified": False}


@router.post("/agents/{agent_id}")
def set_control(agent_id: str, request: Control, authorization: str = Header(None)):
    actor = approver(authorization)
    if agent_id not in {a[0] for a in AGENTS}:
        raise HTTPException(404, "Unknown specialist")
    with _lock:
        e = next((e for e in all_of(CONTROL) if e.attributes["agent_id"] == agent_id), None)
        if e:
            update(e, {"paused": request.paused, "updated_by": actor})
        else:
            e = new(CONTROL, {"agent_id": agent_id, "paused": request.paused, "updated_by": actor})
        return serial(e)


@router.post("/runs")
def run_goal(request: Goal, authorization: str = Header(None), idempotency_key: str = Header(..., min_length=16, max_length=128)):
    actor = authorized(authorization, True)
    if request.agent_id not in {a[0] for a in AGENTS}:
        raise HTTPException(422, "Unknown specialist")
    run_id = "MRUN-" + hashlib.sha256((actor + ":" + idempotency_key).encode()).hexdigest()
    with _lock:
        previous = ledger.get_entity(run_id)
        if previous:
            if previous.attributes["request"] != request.model_dump():
                raise HTTPException(409, "Idempotency key belongs to a different request")
            return serial(previous)
        if paused(request.agent_id):
            raise HTTPException(423, "This specialist is paused")
        if request.campaign_id:
            get(request.campaign_id, "Campaign")
        context = {"entity_counts": dict(Counter(e.entity_type for e in ledger.get_all().values())), "observed_at": now(), "inventory": [{"id": e.id, **{k: v for k, v in e.attributes.items() if k in {"year", "make", "model", "trim", "status", "price", "Year", "Make", "Model", "Trim", "Status", "Price"} and isinstance(v, (str, int, float, bool))}} for e in all_of("Vehicle")[:50]], "campaigns": [{"id": e.id, **{k: v for k, v in e.attributes.items() if k in {"name", "channel", "status", "objective"} and isinstance(v, str)}} for e in all_of("Campaign")[:25]], "limitations": "Bounded current records, not a historical snapshot. No customer personal details included. No provider spend, delivery or attribution is implied."}
        run = new(RUN, {"request": request.model_dump(), "actor": actor, "status": "planning", "context": context, "actions": []}, run_id)
    try:
        plan, provenance = plan_goal(request, context)
        # Generated recipient identifiers are never accepted as authority to contact people.
        for action in plan.actions:
            action.recipient_id = None
        with _lock:
            actions = []
            for i, action in enumerate(plan.actions):
                action_id = run_id + "-" + str(i)
                if not ledger.get_entity(action_id):
                    new(ACTION, {**action.model_dump(mode="json"), "run_id": run.id, "campaign_id": request.campaign_id, "status": "draft", "created_by": actor, "attempt_count": 0, "provider_reference": None}, action_id)
                actions.append(action_id)
            update(run, {"status": "awaiting_review", "summary": plan.summary, "provenance": provenance, "actions": actions})
    except Exception:
        with _lock:
            update(run, {"status": "failed", "error": "Planning could not complete. Check provider configuration and AI controls; no actions were dispatched."})
    return serial(run)


@router.post("/actions")
def create_action(request: ActionSpec, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        return serial(new(ACTION, {**request.model_dump(mode="json"), "run_id": None, "campaign_id": None, "status": "draft", "created_by": actor, "attempt_count": 0, "provider_reference": None}))


@router.put("/actions/{action_id}")
def edit_action(action_id: str, request: EditAction, authorization: str = Header(None)):
    actor = authorized(authorization, True)
    with _lock:
        e = get(action_id, ACTION)
        if e.attributes.get("html_body") or e.attributes.get("sequence_id"):
            raise HTTPException(409, "Branded emails retain their reviewed design. Cancel this draft and create a new campaign to change the message")
        if e.attributes["revision"] != request.revision or e.attributes["status"] not in {"draft", "rejected", "approved"}:
            raise HTTPException(409, "Action changed or has already been dispatched")
        update(e, {**request.model_dump(mode="json", exclude={"revision"}), "status": "draft", "approved_by": None, "approved_at": None, "edited_by": actor})
        return serial(e)


@router.post("/bulk-actions")
def bulk_drafts(request: BulkDraft, authorization: str = Header(None), idempotency_key: str = Header(..., min_length=16, max_length=128)):
    actor = authorized(authorization, True)
    if request.channel not in {"email", "sms", "voice", "whatsapp"}:
        raise HTTPException(422, "Bulk drafts require a recipient channel")
    payload = request.model_dump(mode="json")
    batch_id = "MBATCH-" + hashlib.sha256((actor + ":" + idempotency_key).encode()).hexdigest()
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with _lock:
        previous = ledger.get_entity(batch_id)
        if previous:
            if previous.attributes["request_digest"] != digest:
                raise HTTPException(409, "Idempotency key belongs to another batch")
            return serial(previous)
        recipients = list(dict.fromkeys(request.recipient_ids))
        base = request.model_dump(mode="json", exclude={"recipient_ids"})
        for recipient in recipients:
            check_recipient({**base, "recipient_id": recipient})
        staged = []
        timestamp = now()
        try:
            for i, recipient in enumerate(recipients):
                e = Entity(batch_id + "-" + str(i), ACTION, {**base, "recipient_id": recipient, "batch_id": batch_id, "run_id": None, "campaign_id": None, "status": "draft", "created_by": actor, "attempt_count": 0, "provider_reference": None, "created_at": timestamp, "updated_at": timestamp, "revision": 1})
                ledger.add_entity(e)
                staged.append(e.id)
            batch = new("MarketingCommunicationBatch", {"created_by": actor, "request_digest": digest, "actions": staged[:], "status": "draft", "recipient_count": len(recipients)}, batch_id)
        except Exception:
            for entity_id in staged:
                ledger.entities.pop(entity_id, None)
            raise
        return serial(batch)


@router.post("/actions/{action_id}/decision")
def decide(action_id: str, request: Decision, authorization: str = Header(None)):
    actor = approver(authorization)
    with _lock:
        e = get(action_id, ACTION)
        a = e.attributes
        if a["revision"] != request.revision or a["status"] not in {"draft", "approved", "rejected"}:
            raise HTTPException(409, "Action changed or can no longer be decided")
        if request.decision == "reject" and not request.note.strip():
            raise HTTPException(422, "Explain the changes needed before returning this draft")
        footer_patch = {}
        if request.decision == "approve":
            if a.get("run_id") and get(a["run_id"], RUN).attributes["status"] != "awaiting_review":
                raise HTTPException(409, "The originating plan did not finish successfully")
            contact = check_recipient(a)
            if a["channel"] == "email":
                footer_patch = {**email_footer.prepare(a), "approved_to": contact}
            if a["channel"] == "paid_media":
                try:
                    limit = float(os.getenv("NXTDEAL_MARKETING_MEDIA_LIMIT", "0"))
                except ValueError:
                    limit = 0
                allocated = sum(x.attributes.get("budget", 0) for x in all_of(ACTION) if x.id != e.id and x.attributes.get("status") in {"approved", "dispatching", "unknown", "accepted", "delivered"} and x.attributes.get("approved_at", "").startswith(now()[:10]))
                if not math.isfinite(limit) or limit <= 0 or a["budget"] <= 0 or allocated + a["budget"] > limit:
                    raise HTTPException(409, "Action exceeds the configured media approval limit")
        update(e, {**footer_patch, "status": {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}[request.decision], "approved_by": actor if request.decision == "approve" else None, "approved_at": now() if request.decision == "approve" else None, "decision_by": actor, "decision_at": now(), "review_note": request.note.strip() if request.decision == "reject" else None})
        return serial(e)


def send_gateway(action):
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        with client.stream("POST", os.environ["NXTDEAL_CHANNEL_GATEWAY_URL"], headers={"Authorization": "Bearer " + os.environ["NXTDEAL_CHANNEL_GATEWAY_TOKEN"], "Idempotency-Key": action["id"]}, json={"version": "1", "action": action}) as response:
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > 16384:
                    raise RuntimeError("Oversized gateway response")
            response.raise_for_status()
        data = json.loads(body)
        ref = data.get("provider_reference")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 200:
            raise RuntimeError("Missing provider acceptance reference")
        return ref


@router.post("/actions/{action_id}/dispatch")
def dispatch(action_id: str, authorization: str = Header(None)):
    actor = approver(authorization)
    with _lock:
        e = get(action_id, ACTION)
        if e.attributes["status"] != "approved":
            raise HTTPException(409, "Action needs fresh approval; accepted or uncertain actions cannot be resent")
        if not channel_ready(e.attributes["channel"]):
            raise HTTPException(503, "Channel delivery is disabled or not configured")
        if e.attributes.get("scheduled_at") and datetime.fromisoformat(e.attributes["scheduled_at"]).timestamp() > time.time():
            raise HTTPException(409, "Action is not due yet")
        enrollment_id = e.attributes.get("sequence_enrollment_id")
        if enrollment_id:
            from api.routers.sales_crm_advanced import stop_reason
            enrollment = ledger.get_entity(enrollment_id)
            if not enrollment or enrollment.entity_type != "SalesCrmEnrollment" or enrollment.attributes.get("status") != "active" or enrollment.attributes.get("output_id") != e.id:
                raise HTTPException(409, "Sequence is not active for this action")
            if stop_reason(ledger.get_entity(e.attributes.get("recipient_id")), enrollment.attributes):
                raise HTTPException(409, "Sequence recipient reached an exit condition")
        contact = check_recipient(e.attributes)
        inventory = e.attributes.get("inventory_snapshot", [])
        if inventory and marketing_inventory.snapshot([v["id"] for v in inventory]) != inventory:
            raise HTTPException(409, "Suggested inventory changed; create a fresh campaign with current vehicle details")
        if e.attributes["channel"] == "email":
            if e.attributes.get("mailing_identity") != email_footer.identity() or contact != e.attributes.get("approved_to"):
                raise HTTPException(409, "Dealer address or recipient changed; approve this message again")
            if not e.attributes.get("unsubscribe_url", "").startswith(email_footer.public_base() + "/marketing/operations/unsubscribe/"):
                raise HTTPException(409, "Unsubscribe configuration changed; approve this message again")
        update(e, {"status": "dispatching", "attempt_count": e.attributes["attempt_count"] + 1, "dispatched_by": actor, "sent_to": contact})
        payload = {**serial(e), "to": contact}
        if payload["channel"] == "email":
            payload.update(body=payload["send_body"], html_body=payload["send_html_body"])
    try:
        result = marketing_delivery.send(payload) if marketing_delivery.configured(payload["channel"]) else {"provider": "gateway", "provider_reference": send_gateway(payload)}
    except Exception:
        with _lock:
            update(e, {"status": "unknown", "error": "Provider outcome could not be confirmed. Reconcile with the provider before any resend."})
        return serial(e)
    with _lock:
        update(e, {"status": "accepted", **result, "accepted_at": now()})
        return serial(e)


@router.post("/actions/{action_id}/reconcile")
def reconcile(action_id: str, request: Reconciliation, authorization: str = Header(None)):
    actor = approver(authorization)
    with _lock:
        e = get(action_id, ACTION)
        if e.attributes["status"] == "dispatching" and time.time() - datetime.fromisoformat(e.attributes["updated_at"]).timestamp() < 120:
            raise HTTPException(409, "Dispatch is still in progress; wait before reconciling")
        if e.attributes["status"] not in {"unknown", "dispatching", "accepted"}:
            raise HTTPException(409, "Only dispatched actions can be reconciled")
        if e.attributes["status"] == "accepted" and (request.provider_reference != e.attributes.get("provider_reference") or request.status not in {"delivered", "failed"}):
            raise HTTPException(409, "Confirm a final outcome using the existing provider reference")
        update(e, {**request.model_dump(), "reconciled_by": actor, "reconciled_at": now(), "status_source": "human_provider_reconciliation"})
        return serial(e)


def sync_responses():
    try:
        from api.routers.campaign_workflow import sync_recorded_responses
        sync_recorded_responses()
    except Exception:
        logging.getLogger(__name__).warning("Response saved; BDC routing needs retry", exc_info=True)


@router.post("/provider-events")
async def provider_event(request: Request, x_nxtdeal_timestamp: str = Header(""), x_nxtdeal_signature: str = Header("")):
    secret = os.getenv("NXTDEAL_CHANNEL_CALLBACK_SECRET", "")
    if not secret:
        raise HTTPException(503, "Provider callbacks are not configured")
    try:
        if abs(time.time() - int(x_nxtdeal_timestamp)) > 300:
            raise ValueError()
    except ValueError:
        raise HTTPException(401, "Invalid callback timestamp")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > 16384:
            raise HTTPException(413, "Callback too large")
    signature = hmac.new(secret.encode(), x_nxtdeal_timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, x_nxtdeal_signature):
        raise HTTPException(401, "Invalid callback signature")
    try:
        data = json.loads(body)
        action_id, ref, event_id = data["action_id"], data["provider_reference"], data["event_id"]
        status = data["status"]
        if status not in {"delivered", "failed", "response"} or not all(isinstance(x, str) and 0 < len(x) <= 200 for x in (action_id, ref, event_id)):
            raise ValueError()
        text = data.get("text", "")
        if not isinstance(text, str) or len(text) > 8000:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "Invalid provider event")
    with _lock:
        e = get(action_id, ACTION)
        event_key = "MEVT-" + hashlib.sha256((action_id + ":" + event_id).encode()).hexdigest()
        if ledger.get_entity(event_key):
            if status == "response":
                sync_responses()
            return {"ok": True, "replay": True}
        if e.attributes.get("provider_reference") != ref:
            raise HTTPException(409, "Provider reference does not match the accepted action")
        previous = deepcopy(e.attributes)
        if status == "delivered" or (status == "failed" and e.attributes["status"] != "delivered"):
            e.attributes = {**previous, "status": status, "provider_updated_at": now(), "revision": previous["revision"] + 1}
        try:
            new(EVENT, {"action_id": action_id, "provider_reference": ref, "event_id": event_id, "status": status, "text": text}, event_key)
        except Exception:
            e.attributes = previous
            raise
        if status == "response":
            sync_responses()
        return {"ok": True}
