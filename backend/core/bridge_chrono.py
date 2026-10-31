"""Opt-in temporal outbox with durable receipts, fenced leases and bounded retries.

No sink is installed by default. Only a trusted startup binding and an explicit
administrator policy can enable egress. Analysis-engine availability is separate.
"""
import asyncio
from core.worker_io import run_worker_io
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from chrono.contracts import Observation
from chrono.delivery import TemporalEnvelope, DeliveryReceipt, ObservationSink
from core import dealer_bridge as bridge
from core.auth import credential_store
from core.dealeros import ledger
from core.entities import Entity
from core.bridge_contracts import timestamp

POLICY_ID = "BRIDGE-CHRONO-POLICY"
LEASE_SECONDS = 300
MAX_ATTEMPTS = 5
_TASK = None
_BINDING = None
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SinkBinding:
    workspace_id: str
    name: str
    revision: str
    sink: ObservationSink


def bind_sink(name, revision, sink):
    """Trusted startup hook, never exposed through HTTP or model-generated code."""
    global _BINDING
    if any(not isinstance(v, str) or not v.strip() or len(v) > 120 for v in (name, revision)):
        raise ValueError("Bounded sink name and revision required")
    if getattr(sink, "supports_idempotency", False) is not True or not callable(getattr(sink, "deliver", None)):
        raise ValueError("Sink must explicitly support durable event-ID deduplication")
    with bridge.LOCK:
        if (_BINDING and _BINDING.workspace_id == ledger.tenant.workspace_id and
                _BINDING.name == name and _BINDING.revision == revision):
            if _BINDING.sink is sink:
                return
            raise ValueError("Replacing an active Chrono destination requires a new revision")
        _BINDING = SinkBinding(ledger.tenant.workspace_id, name, revision, sink)


def unbind_sink():
    global _BINDING
    with bridge.LOCK:
        _BINDING = None


def utcnow():
    return datetime.now(timezone.utc)


def policy():
    entity = ledger.get_entity(POLICY_ID)
    if entity is None:
        return {"enabled": False, "sink_name": None, "sink_revision": None, "authorized_by": None}
    return bridge.get(POLICY_ID, "BridgeChronoPolicy")


def _events():
    return [e for e in ledger.get_all().values() if e.entity_type == "SourceObservation" and
            e.attributes.get("origin") == "dealer_bridge" and e.attributes.get("workspace_id") == ledger.tenant.workspace_id]


def receipt_id(event_id, sink_name, sink_revision):
    return "BRCDEL-" + bridge.digest([ledger.tenant.workspace_id, sink_name, sink_revision, event_id])


def status_for(event_id):
    config = policy()
    receipt = ledger.get_entity(receipt_id(event_id, config["sink_name"], config["sink_revision"]))
    return receipt.attributes["status"] if receipt else "pending"


def status(actor):
    bridge.authorize(actor)
    with bridge.LOCK:
        config = deepcopy(policy())
        bound = _BINDING if _BINDING and _BINDING.workspace_id == ledger.tenant.workspace_id else None
        counts = {}
        for event in _events():
            value = status_for(event.id)
            counts[value] = counts.get(value, 0) + 1
        effective_status, reason = "disabled", None
        if config["enabled"]:
            try:
                _authorized_binding()
                effective_status = "ready"
            except (PermissionError, ValueError) as exc:
                effective_status, reason = "review_required", str(exc)
        return {"enabled": config["enabled"], "authorized_sink": {"name": config["sink_name"], "revision": config["sink_revision"]},
                "runtime_sink": {"name": bound.name, "revision": bound.revision} if bound else None,
                "delivery": "bound" if bound else "not_connected", "effective_status": effective_status, "reason": reason,
                "counts": counts, "analysis_engine": "not_configured_by_bridge"}


def configure(actor, enabled, sink_name=None, sink_revision=None):
    if type(enabled) is not bool:
        raise ValueError("Enabled must be a boolean")
    with bridge.mutation(actor, True):
        if enabled:
            bridge.require_durable_state()
        if enabled and (not _BINDING or _BINDING.workspace_id != ledger.tenant.workspace_id or
                        (_BINDING.name, _BINDING.revision) != (sink_name, sink_revision)):
            raise ValueError("Review and select the current trusted sink binding before enabling delivery")
        previous = policy()
        bridge.put(Entity(POLICY_ID, "BridgeChronoPolicy", {
            "workspace_id": ledger.tenant.workspace_id, "enabled": enabled,
            "sink_name": sink_name if enabled else previous["sink_name"],
            "sink_revision": sink_revision if enabled else previous["sink_revision"],
            "authorized_by": actor["employee_id"], "updated_at": bridge.now(),
        }))
        bridge.audit(actor, "chrono.enable" if enabled else "chrono.disable", POLICY_ID)
    return status(actor)


def _authorized_binding():
    config = policy()
    if not config["enabled"]:
        return None
    bridge.require_durable_state()
    record = credential_store.get_record(config["authorized_by"])
    if not record or record.get("disabled") or record.get("role") != "ADMIN":
        raise PermissionError("Chrono delivery authorization is no longer valid")
    if not _BINDING or _BINDING.workspace_id != ledger.tenant.workspace_id or (_BINDING.name, _BINDING.revision) != (config["sink_name"], config["sink_revision"]):
        raise ValueError("Chrono binding changed or is unavailable; administrator review required")
    return _BINDING


def envelope(event):
    attrs = event.attributes
    observation = Observation(**{field.name: deepcopy(attrs.get(field.name)) for field in fields(Observation)})
    lineage = {"connector_instance_id": attrs.get("system_id"), "source_object": attrs.get("object_type"),
               "mapping_revision_id": attrs.get("mapping_id"), "external_identity_key": attrs.get("external_key"),
               "canonical_kind": attrs.get("canonical_kind"), "origin": attrs.get("origin"),
               "source_time_semantics": attrs.get("source_time_semantics"), "source_namespace": attrs.get("source_namespace"),
               "source_transport": attrs.get("source_transport"), "ingestion_receipt_id": attrs.get("ingestion_receipt_id")}
    return TemporalEnvelope(event.id, observation, deepcopy(attrs.get("values", {})),
                            {key: value for key, value in lineage.items() if isinstance(value, str)})


def deliver_once(actor, limit=50, *, scheduled=False):
    bridge.authorize(actor, human=not scheduled)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Delivery batch must contain 1 to 100 events")
    current, token, claimed = utcnow(), uuid4().hex, []
    with bridge.mutation(actor, human=not scheduled):
        bound = _authorized_binding()
        if bound is None:
            return {"status": "disabled", "delivered": 0}
        if scheduled and policy()["authorized_by"] != actor["employee_id"]:
            raise PermissionError("Worker actor does not match delivery authorization")
        for event in sorted(_events(), key=lambda e: (e.attributes["import_timestamp"], e.id)):
            entity_id = receipt_id(event.id, bound.name, bound.revision)
            existing = ledger.get_entity(entity_id)
            prior = existing.attributes if existing else {}
            if prior.get("status") in {"delivered", "blocked"}:
                continue
            if prior.get("lease_until") and timestamp(prior["lease_until"]) > current:
                continue
            if prior.get("next_attempt_at") and timestamp(prior["next_attempt_at"]) > current:
                continue
            attempts = prior.get("attempts", 0)
            if attempts >= MAX_ATTEMPTS:
                bridge.put(Entity(entity_id, "BridgeChronoDelivery", {**prior, "status": "blocked", "lease_token": None, "lease_until": None}))
                continue
            payload = envelope(event)
            bridge.put(Entity(entity_id, "BridgeChronoDelivery", {
                **deepcopy(prior), "workspace_id": ledger.tenant.workspace_id, "event_id": event.id,
                "sink_name": bound.name, "sink_revision": bound.revision, "status": "in_flight",
                "attempts": attempts + 1, "lease_token": token, "lease_until": (current + timedelta(seconds=LEASE_SECONDS)).isoformat(),
                "last_attempt_at": current.isoformat(), "next_attempt_at": None,
            }))
            claimed.append((entity_id, payload))
            if len(claimed) >= limit:
                break
    if not claimed:
        return {"status": "idle", "delivered": 0}
    requested = {payload.event_id for _, payload in claimed}
    accepted, retryable, error = set(), True, None
    try:
        # The sink must enforce a bounded network timeout and durable event-ID
        # deduplication; no lock is held during network IO.
        receipt = bound.sink.deliver(workspace_id=bound.workspace_id, events=tuple(payload for _, payload in claimed))
        if (not isinstance(receipt, DeliveryReceipt) or type(receipt.retryable) is not bool or
                not isinstance(receipt.accepted_event_ids, tuple) or len(receipt.accepted_event_ids) > len(requested) or
                any(not isinstance(v, str) or len(v) > 120 for v in receipt.accepted_event_ids) or
                len(set(receipt.accepted_event_ids)) != len(receipt.accepted_event_ids) or not set(receipt.accepted_event_ids) <= requested):
            raise ValueError("Invalid sink receipt")
        accepted, retryable = set(receipt.accepted_event_ids), receipt.retryable
        if accepted != requested:
            error = "Sink did not acknowledge every event"
    except (TimeoutError, ConnectionError):
        error = "Sink temporarily unavailable; outcome may require idempotent retry"
    except Exception:
        retryable, error = False, "Sink contract or delivery requires operator review"
    # Acknowledgments are factual evidence, even if egress policy was disabled
    # while the call was in flight. This block never triggers another delivery.
    delivered = 0
    with bridge.mutation(actor):
        for entity_id, payload in claimed:
            record = bridge.get(entity_id, "BridgeChronoDelivery")
            if record.get("lease_token") != token:
                continue
            success = payload.event_id in accepted
            blocked = not retryable or record["attempts"] >= MAX_ATTEMPTS
            record.update(status="delivered" if success else "blocked" if blocked else "retrying",
                          lease_token=None, lease_until=None, last_error=None if success else error,
                          next_attempt_at=None if success or blocked else (utcnow() + timedelta(seconds=min(3600, 60 * 2 ** (record["attempts"] - 1)))).isoformat())
            if success:
                record["acknowledged_at"] = bridge.now()
                delivered += 1
            bridge.audit(actor, "chrono.acknowledge" if success else "chrono.delivery_failed", entity_id)
    return {"status": "complete" if delivered == len(claimed) else "partial_or_failed", "delivered": delivered, "attempted": len(claimed)}


def retry(actor, event_id, reason, expected_receipt_id=None):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        bound = _authorized_binding()
        if bound is None:
            raise ValueError("Enable an authorized sink before retrying")
        selected_id = receipt_id(event_id, bound.name, bound.revision)
        if expected_receipt_id is not None and expected_receipt_id != selected_id:
            raise ValueError("Chrono destination changed; reload delivery evidence before retrying")
        record = bridge.get(selected_id, "BridgeChronoDelivery")
        if record["status"] == "delivered":
            raise ValueError("Acknowledged events do not need redelivery")
        if record.get("lease_until") and timestamp(record["lease_until"]) > utcnow():
            raise ValueError("Delivery is still in progress")
        record.update(status="retrying", attempts=0, lease_token=None, lease_until=None,
                      next_attempt_at=utcnow().isoformat(), retry_reason=reason, retried_by=actor["employee_id"])
        bridge.audit(actor, "chrono.retry_requested", event_id)
    return {"status": "retrying"}


def receipts(actor):
    with bridge.LOCK:
        return _receipts(actor)


def _receipts(actor):
    bridge.authorize(actor)
    config = policy()
    return [{"id": e.id, **deepcopy({key: value for key, value in e.attributes.items() if key not in {"lease_token", "workspace_id"}})}
            for e in list(ledger.get_all().values()) if e.entity_type == "BridgeChronoDelivery" and
            e.attributes.get("workspace_id") == ledger.tenant.workspace_id and
            (e.attributes["sink_name"], e.attributes["sink_revision"]) == (config["sink_name"], config["sink_revision"])][-200:]


def tick():
    config = deepcopy(policy())
    if not config["enabled"]:
        return {"status": "disabled", "delivered": 0}
    actor = {"employee_id": config["authorized_by"], "role": "ADMIN", "bridge_principal": "worker"}
    try:
        return deliver_once(actor, scheduled=True)
    except (PermissionError, ValueError):
        return {"status": "authorization_or_binding_unavailable", "delivered": 0}


async def loop():
    while True:
        await asyncio.sleep(60)
        try:
            await run_worker_io(tick)
        except Exception:
            log.error("Bridge temporal delivery failed; review durable receipts")


def start():
    global _TASK
    if _TASK is None:
        _TASK = asyncio.get_running_loop().create_task(loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _TASK
    task = _TASK
    if task is not None:
        task.cancel()
        # Retain ownership during thread drain so a repeated start cannot overlap.
        def release(completed):
            global _TASK
            if _TASK is completed:
                _TASK = None
        if task.done():
            release(task)
        else:
            task.add_done_callback(release)
    return task
