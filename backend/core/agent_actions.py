"""Typed native action adapters. Business mutations reuse existing domain modules."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.dealeros import ledger
from core.entities import Entity
from core.security import can_access_entity


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskInput(Input):
    lead_id: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=500)
    due_at: str | None = None


class CampaignInput(Input):
    name: str = Field(min_length=1, max_length=160)
    channel: Literal["email", "sms"] = "email"
    make: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)


class AppointmentInput(Input):
    lead_id: str = Field(min_length=1)
    scheduled_start: str
    scheduled_end: str | None = None
    appointment_type: Literal["showroom_visit", "test_drive", "delivery", "paperwork", "trade_appraisal", "other"] = "showroom_visit"


class LeadInput(Input):
    lead_id: str = Field(min_length=1)
    next_state: Literal["CONTACTED", "APPOINTMENT_SET", "VISITED", "PROPOSAL", "NEGOTIATION", "SOLD", "LOST"]


class ReviewInput(Input):
    record_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class MessageInput(Input):
    record_id: str = Field(min_length=1)
    topic: str = Field(min_length=1, max_length=200)


class SendInput(Input):
    customer_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)
    subject: str = Field(default="", max_length=200)


MODELS = {"task.create": TaskInput, "campaign.create": CampaignInput,
          "appointment.create": AppointmentInput, "lead.update": LeadInput,
          "manager.request_approval": ReviewInput, "deal.request_review": ReviewInput,
          "message.generate": MessageInput, "sms.send": SendInput, "email.send": SendInput}
from core import department_work
MODELS.update(department_work.MODELS)
CONNECTORS = {}


def register_connector(capability, *, model, connection_id, credential_ref, validate_access, dispatch):
    """Trusted provider startup registration; never called from client input.

    dispatch(actor, validated_input, secret, idempotency_key) must return a small
    JSON-safe outcome. It must honor idempotency and raise on ambiguous outcomes.
    validate_access must validate record scope and provider-specific policy/consent.
    Credentials resolve centrally at execution, never from department manifests.
    """
    from core.department_agents import CAPABILITIES
    if capability not in CAPABILITIES or CAPABILITIES[capability].kind != "ACTION" or capability in MODELS:
        raise ValueError("Unknown or already bound action")
    if not isinstance(model, type) or not issubclass(model, Input) or not callable(validate_access) or not callable(dispatch):
        raise ValueError("Typed schema, authorization validator and dispatcher required")
    if not connection_id or not credential_ref:
        raise ValueError("Connection and centralized credential reference required")
    MODELS[capability] = model
    CONNECTORS[capability] = {"connection_id": connection_id, "credential_ref": credential_ref,
                             "validate": validate_access, "dispatch": dispatch}


def connected(capability):
    if capability in CONNECTORS:
        from core.secrets import get_secret
        binding = CONNECTORS[capability]
        connection = ledger.get_entity(binding["connection_id"])
        return bool(connection and connection.entity_type == "Connection" and
                    connection.attributes.get("status") == "connected" and get_secret(binding["credential_ref"]))
    if capability in {"sms.send", "email.send"}:
        from core.integrations_registry import is_live
        return is_live("notifications")
    return capability in MODELS


def require_record(actor, record_id, types):
    entity = ledger.get_entity(record_id)
    if not entity or entity.entity_type not in types or not can_access_entity(actor["role"], entity.entity_type):
        raise PermissionError("Record is unavailable to this employee")
    return entity


def channel_consent(customer, channel):
    """Latest consent wins; imported evidence cannot grant outbound permission.

    Imported opt-outs and unresolved source permissions suppress legacy flags.
    A later native consent decision can supersede them after separate review.
    """
    if customer.attributes.get("do_not_contact"):
        return False
    records = [e for e in ledger.get_all().values() if e.entity_type in {"Consent", "ImportedConsent"} and
               e.attributes.get("workspace_id", ledger.tenant.workspace_id) == ledger.tenant.workspace_id and
               e.attributes.get("customer_id") == customer.id and
               isinstance(e.attributes.get("channel"), str) and e.attributes["channel"].strip().casefold() == channel.casefold()]
    if records:
        dated = []
        for record in records:
            try:
                timestamp = datetime.fromisoformat(record.attributes["occurred_at"])
                if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
                    return False
                dated.append((timestamp, record.attributes.get("status"), record.entity_type == "Consent"))
            except (ValueError, TypeError, KeyError):
                return False
        latest = max(t for t, _, _ in dated)
        return all(native and status in {"granted", "opted_in", "subscribed"}
                   for t, status, native in dated if t == latest)
    flags = customer.attributes.get("consent", {})
    return isinstance(flags, dict) and flags.get(channel) is True


def validate(actor, capability, data):
    if capability in department_work.MODELS:
        try:
            return department_work.validate(actor, capability, data)
        except ValidationError:
            raise ValueError("Input does not match the capability schema") from None
    try:
        value = MODELS[capability].model_validate(data).model_dump()
    except ValidationError:
        raise ValueError("Input does not match the capability schema") from None
    if any(isinstance(value.get(field), str) and not value[field].strip() for field in ("description", "name", "body", "reason", "topic")):
        raise ValueError("Action text must not be blank")
    if capability in CONNECTORS:
        if not connected(capability):
            raise ValueError("Connected provider and credentials required")
        CONNECTORS[capability]["validate"](actor, value)
        return value
    if "lead_id" in value:
        lead = require_record(actor, value["lead_id"], {"Lead"})
    if "record_id" in value:
        require_record(actor, value["record_id"], {"Deal"} if capability == "deal.request_review" else {"Lead", "Customer", "Vehicle", "Deal", "Campaign", "ServiceRecord"})
    if capability in {"sms.send", "email.send"}:
        customer = require_record(actor, value["customer_id"], {"Customer"})
        channel = capability.split(".")[0]
        if not channel_consent(customer, channel):
            raise PermissionError("Current explicit channel consent is required")
        keys = ("phone", "Phone") if channel == "sms" else ("email", "Email")
        if not any(isinstance(customer.attributes.get(k), str) and customer.attributes[k].strip() for k in keys):
            raise ValueError("Customer has no destination for this channel")
        if not connected(capability):
            raise ValueError("Live notification adapter required")
    for field in ("due_at", "scheduled_start", "scheduled_end"):
        if value.get(field) is not None:
            parsed = datetime.fromisoformat(value[field])
            if parsed.tzinfo is None:
                raise ValueError("Action timestamps must include a timezone")
    if capability == "appointment.create":
        from core.appointments import _time_range_error
        if _time_range_error(value["scheduled_start"], value["scheduled_end"]):
            raise ValueError("Appointment end must follow its start")
    if capability == "lead.update":
        from core.workflows import can_transition
        if not can_transition(lead.attributes.get("PipelineState"), value["next_state"]):
            raise ValueError("Invalid lead workflow transition")
    return value


def source_records(data):
    return [data[k] for k in ("lead_id", "record_id", "campaign_id", "customer_id") if data.get(k)]


def execute(actor, capability, data, proposal_id):
    value = validate(actor, capability, data)
    if capability in department_work.MODELS:
        return department_work.execute(actor, capability, value, proposal_id)
    if capability in CONNECTORS:
        from core.secrets import get_secret
        binding = CONNECTORS[capability]
        result = binding["dispatch"](actor, value, get_secret(binding["credential_ref"]), proposal_id)
        if not isinstance(result, dict) or result.get("status") not in {"accepted", "executed", "queued"}:
            raise ValueError("Connector outcome was not confirmed")
        # Only the agreed outcome contract reaches the journal; provider payloads may contain tokens/PII.
        return {"status": result["status"], "connection_id": binding["connection_id"]}
    if capability in {"sms.send", "email.send"}:
        from core.integrations_registry import send_notification
        customer = ledger.get_entity(value["customer_id"])
        channel = capability.split(".")[0]
        keys = ("phone", "Phone") if channel == "sms" else ("email", "Email")
        destination = next(customer.attributes[k] for k in keys if customer.attributes.get(k))
        result = send_notification(destination, {"type": "agent_message", "body": value["body"],
                                   "subject": value["subject"], "idempotency_key": proposal_id}, (channel,))
        if not isinstance(result, dict) or result.get("simulated") is not False or result.get("status") not in {"sent", "queued", "accepted"}:
            raise ValueError("Provider did not confirm a live dispatch outcome")
        return {"customer_id": customer.id, "status": result["status"], "channel": channel}
    if capability == "task.create":
        from core.lead_tasks import create_task
        entity = create_task(value["lead_id"], "custom", value["description"], value["due_at"], actor["employee_id"])
        return {"task_id": entity.id}
    if capability == "campaign.create":
        from core.campaigns import create_campaign
        entity = create_campaign("inventory_ads", value["name"], value["channel"], actor["employee_id"],
                                 {"make": value["make"], "model": value["model"]})
        return {"campaign_id": entity.id, "status": "draft", "sent": False}
    if capability == "appointment.create":
        from core.appointments import create_appointment
        entity = create_appointment("Sales", value["appointment_type"], value["scheduled_start"],
                                    actor["employee_id"], assigned_to=actor["employee_id"],
                                    lead_id=value["lead_id"], scheduled_end=value["scheduled_end"])
        if isinstance(entity, dict):
            raise ValueError("Appointment could not be created")
        return {"appointment_id": entity.id}
    if capability == "lead.update":
        from core.lead_workflows import advance_lead_workflow
        advance_lead_workflow(value["lead_id"], value["next_state"])
        return {"lead_id": value["lead_id"], "state": value["next_state"]}
    if capability == "message.generate":
        # Deterministic preparation; no claims of a generated/predicted LLM result.
        return {"draft": f"Hello, following up about {value['topic']}. Would you like us to help with next steps?",
                "evidence_kind": "derived", "method": "template", "sent": False}
    entity_id = "AFREVIEW-" + uuid4().hex
    ledger.add_entity(Entity(entity_id, "AgentReviewRequest", {
        **value, "requested_by": actor["employee_id"], "status": "open",
        "proposal_id": proposal_id, "kind": capability, "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    return {"review_id": entity_id, "status": "open"}
