"""Durable event receipts and opt-in proposal-only background automations.

Runs inside the existing single dealership process, never a second graph writer.
Background execution prepares actions; it cannot approve or dispatch proposals.
"""
import asyncio
import logging
from copy import deepcopy
from hashlib import sha256

from core.dealeros import ledger
from core.entities import Entity
from core.department_agents import AUTOMATIONS, CAPABILITIES
from core import agent_fabric as fabric

_task = None
log = logging.getLogger(__name__)


def emit(event, record_id, source_key):
    if event not in CAPABILITIES or CAPABILITIES[event].kind != "EVENT":
        raise ValueError("Unknown event contract")
    if not ledger.get_entity(record_id):
        raise ValueError("Event record must exist")
    event_id = "AFE-" + sha256(f"{event}:{record_id}:{source_key}".encode()).hexdigest()
    if not ledger.get_entity(event_id):
        ledger.add_entity(Entity(event_id, "AgentEvent", {
            "event": event, "record_id": record_id, "timestamp": fabric.now(),
            "workspace_id": ledger.tenant.workspace_id,
        }))
    return event_id


def subscriptions(actor):
    return [{"id": e.id, **e.attributes} for e in ledger.get_all().values()
            if e.entity_type == "AgentSubscription" and e.attributes["employee_id"] == actor["employee_id"]]


def subscribe(actor, automation_id, enabled):
    definition = AUTOMATIONS.get(automation_id)
    if not definition or definition["trigger"] == "manual":
        raise ValueError("Automation has no event trigger")
    for capability in definition["steps"]:
        fabric.authorize(actor, definition["department"], capability)
    entity_id = "AFSUB-" + sha256(f"{actor['employee_id']}:{automation_id}".encode()).hexdigest()
    with fabric.LOCK:
        previous_entity = ledger.get_entity(entity_id)
        previous = deepcopy(previous_entity.attributes) if previous_entity else None
        entity = previous_entity or Entity(entity_id, "AgentSubscription", {})
        entity.attributes = {
            "employee_id": actor["employee_id"], "automation_id": automation_id,
            "enabled": enabled, "updated_at": fabric.now(),
        }
        ledger.add_entity(entity)
        audit_id = fabric.audit(actor, definition["department"], "nxtdeal", "automation.subscribe",
                     "enabled" if enabled else "disabled", automation_id=automation_id)
        fabric.commit_metadata(entity, previous, audit_id)
    return subscriptions(actor)


def receipts(actor):
    return [{"id": e.id, **e.attributes} for e in ledger.get_all().values()
            if e.entity_type == "AgentEventReceipt" and
            (e.attributes["employee_id"] == actor["employee_id"] or actor["role"] == "ADMIN")][-100:]


def tick():
    from core.auth import credential_store
    from core.ai_kill_switch import is_workflow_automation_enabled
    if not is_workflow_automation_enabled():
        return {"processed": 0, "status": "disabled"}
    count = 0
    with fabric.LOCK:
        active = [e for e in ledger.get_all().values() if e.entity_type == "AgentSubscription" and e.attributes["enabled"]]
        if not active:
            return {"processed": 0, "status": "idle"}
        for entity in list(ledger.get_all().values()):
            if entity.entity_type == "Lead":
                stale, _, timestamp = fabric.agent_context.stale_lead(entity)
                if stale:
                    emit("lead.no_activity", entity.id, timestamp)
            elif entity.entity_type == "Vehicle":
                days = fabric.agent_context.attributes(entity, ("days_in_stock",)).get("days_in_stock")
                try:
                    if float(days) >= 60:
                        emit("vehicle.aged", entity.id, "60-days")
                except (TypeError, ValueError):
                    pass
        events = [e for e in ledger.get_all().values() if e.entity_type == "AgentEvent"]
        for sub in active:
            config = sub.attributes
            definition = AUTOMATIONS[config["automation_id"]]
            record = credential_store.get_record(config["employee_id"])
            if not record or record.get("disabled"):
                continue
            actor = {"employee_id": config["employee_id"], "role": record["role"]}
            for event in events:
                if event.attributes["event"] != definition["trigger"]:
                    continue
                receipt_id = "AFREC-" + sha256(f"{sub.id}:{event.id}".encode()).hexdigest()
                if ledger.get_entity(receipt_id):
                    continue
                receipt = Entity(receipt_id, "AgentEventReceipt", {
                    "employee_id": actor["employee_id"], "automation_id": definition["id"],
                    "event_id": event.id, "status": "running", "timestamp": fabric.now(),
                })
                ledger.add_entity(receipt)
                fabric.persist()
                try:
                    result = fabric.run_automation(actor, definition["id"], event.attributes["record_id"], "nxtdeal", receipt_id)
                    receipt.attributes.update(status="completed", outcome=result.get("status", "read"), proposal_id=result.get("id"))
                except (ValueError, PermissionError):
                    receipt.attributes.update(status="blocked", reason="Permission, policy or input validation rejected this event")
                except Exception:
                    receipt.attributes.update(status="needs_review", reason="Worker outcome requires review")
                fabric.persist()
                count += 1
                if count >= 50:
                    return {"processed": count, "status": "batch_limit"}
    return {"processed": count, "status": "complete"}


async def loop():
    while True:
        await asyncio.sleep(60)
        try:
            # Same event loop/process as the existing in-memory ledger writers.
            tick()
        except Exception:
            log.error("Department automation tick failed; review persisted receipts")


def start():
    global _task
    if _task is None:
        _task = asyncio.get_running_loop().create_task(loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _task
    task = _task
    if task is not None:
        task.cancel()
        _task = None
    return task
