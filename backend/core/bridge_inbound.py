"""Opt-in signed ADF staging. Receipts and jobs persist atomically; no activation."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import re

from core import dealer_bridge as bridge, bridge_event_profiles as profiles, bridge_event_imports as imports
from core.bridge_adapters.adf_gateway import ADFGatewayVerifier, InvalidDelivery
from core.auth import credential_store
from core.dealeros import ledger
from core.entities import Entity

_BINDINGS = {}


class InboundBackpressure(ValueError):
    def __init__(self): super().__init__("Inbound review queue is full; resolve pending batches before retrying")


@dataclass(frozen=True)
class Binding:
    endpoint_id: str
    workspace_id: str
    system_id: str
    profile_id: str
    revision: str
    environment: str
    verifier: ADFGatewayVerifier
    max_pending_batches: int


def bind(endpoint_id, *, profile_id, revision, environment, verifier, max_pending_batches=100):
    """Trusted startup only; configuration does not enable incoming delivery."""
    if (not isinstance(endpoint_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{24,96}", endpoint_id) or
            not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", revision) or
            environment not in {"synthetic", "sandbox", "production"} or type(verifier) is not ADFGatewayVerifier or
            type(max_pending_batches) is not int or not 1 <= max_pending_batches <= 1000):
        raise ValueError("Explicit bounded gateway binding and verifier required")
    with bridge.LOCK:
        profile = profiles.checked(profile_id)
        bridge.get(profile["system_id"], "BridgeSystem")
        if verifier._system_id != profile["system_id"] or verifier._scope["environment"] != environment:
            raise ValueError("Verifier scope must match the bound source and environment")
        previous = _BINDINGS.get(endpoint_id)
        if previous and (previous.workspace_id != ledger.tenant.workspace_id or previous.revision == revision):
            raise ValueError("Replacing an inbound binding requires its workspace and a new revision")
        _BINDINGS[endpoint_id] = Binding(endpoint_id, ledger.tenant.workspace_id, profile["system_id"], profile_id, revision, environment, verifier, max_pending_batches)


def unbind(endpoint_id):
    with bridge.LOCK: _BINDINGS.pop(endpoint_id, None)


def policy_id(endpoint_id):
    return "BRIN-" + bridge.digest([ledger.tenant.workspace_id, endpoint_id])


def _binding(endpoint_id):
    value = _BINDINGS.get(endpoint_id)
    if not value or value.workspace_id != ledger.tenant.workspace_id: raise InvalidDelivery()
    return value


def _check_environment(bound):
    from core.bridge_sync import _check_environment_namespace
    _check_environment_namespace(bound.system_id, bound.environment)


def _review_token(bound):
    profile = profiles.checked(bound.profile_id)
    source = bridge.get(bound.system_id, "BridgeSystem")
    identifier = policy_id(bound.endpoint_id)
    policy = bridge.get(identifier, "BridgeInboundPolicy") if ledger.get_entity(identifier) else None
    return bridge.digest([bound.workspace_id, bound.endpoint_id, bound.system_id,
        bound.profile_id, profile["hash"], profile["status"], bound.revision,
        bound.environment, bound.max_pending_batches,
        source["name"], source["vendor"], bool(source.get("paused")), policy])


def configure(actor, endpoint_id, enabled, revision=None, review_token=None):
    if type(enabled) is not bool: raise ValueError("Boolean enabled required")
    with bridge.mutation(actor, True):
        record_id = policy_id(endpoint_id)
        if enabled:
            bridge.require_durable_state()
            bound = _binding(endpoint_id)
            profile = profiles.checked(bound.profile_id)
            if revision != bound.revision or profile["status"] != "approved" or bridge.get(bound.system_id, "BridgeSystem").get("paused"):
                raise ValueError("Review the current gateway binding and approved profile before enabling")
            _check_environment(bound)
            if review_token is not None and review_token != _review_token(bound):
                raise ValueError("Gateway configuration or policy changed; inspect and review it again")
            value = {"system_id": bound.system_id, "profile_id": bound.profile_id, "profile_hash": profile["hash"],
                "endpoint_id": endpoint_id, "revision": bound.revision, "environment": bound.environment}
        else:
            value = deepcopy(bridge.get(record_id, "BridgeInboundPolicy"))
        bridge.put(Entity(record_id, "BridgeInboundPolicy", {**value, "workspace_id": ledger.tenant.workspace_id,
            "enabled": enabled, "authorized_by": actor["employee_id"], "updated_at": bridge.now()}))
        bridge.audit(actor, "inbound.enable" if enabled else "inbound.disable", record_id)
    return {"enabled": enabled, "endpoint_id": endpoint_id}


def _authorized(endpoint_id):
    bridge.require_durable_state()
    bound = _binding(endpoint_id)
    policy = bridge.get(policy_id(endpoint_id), "BridgeInboundPolicy")
    profile = profiles.checked(bound.profile_id)
    record = credential_store.get_record(policy["authorized_by"])
    if (not policy.get("enabled") or not record or record.get("disabled") or record.get("role") != "ADMIN" or
            policy.get("revision") != bound.revision or policy.get("profile_id") != bound.profile_id or
            policy.get("profile_hash") != profile["hash"] or policy.get("environment") != bound.environment or
            policy.get("system_id") != bound.system_id or profile["status"] != "approved" or
            bridge.get(bound.system_id, "BridgeSystem").get("paused")):
        raise InvalidDelivery()
    _check_environment(bound)
    actor = {"employee_id": policy["authorized_by"], "role": "ADMIN", "bridge_principal": "inbound_gateway", "workspace_id": ledger.tenant.workspace_id}
    return bound, actor, bridge.digest([policy, profile])


def receive(endpoint_id, delivery_id, signed_at, signature, body):
    # Verification and secret-provider IO occur outside the graph lock.
    with bridge.LOCK:
        bound, actor, fence = _authorized(endpoint_id)
    bound.verifier.verify(endpoint_id, delivery_id, signed_at, signature, body)
    try: content = body.decode("utf-8")
    except UnicodeError: raise InvalidDelivery() from None
    fingerprint = hashlib.sha256(body).hexdigest()
    receipt_id = "BRIND-" + bridge.digest([ledger.tenant.workspace_id, bound.system_id, delivery_id])
    with bridge.mutation(actor):
        current, fresh_actor, current_fence = _authorized(endpoint_id)
        if current is not bound or current_fence != fence: raise InvalidDelivery()
        prior = ledger.get_entity(receipt_id)
        if prior:
            receipt = bridge.get(receipt_id, "BridgeInboundDelivery")
            job = bridge.get(receipt["job_id"], "BridgeEventJob")
            if (receipt.get("body_hash") != fingerprint or receipt.get("profile_id") != bound.profile_id or
                    receipt.get("system_id") != bound.system_id or job.get("system_id") != bound.system_id or
                    job.get("profile_id") != bound.profile_id or job.get("source_evidence", {}).get("export_sha256") != fingerprint):
                raise InvalidDelivery()
            from core.bridge_inbound_evidence import checked
            evidence = checked(receipt["job_id"], job)
            if not evidence or evidence["receipt_id"] != receipt_id: raise InvalidDelivery()
            return {"status": "already_received", "receipt_id": receipt_id}
        pending = sum(entity.entity_type == "BridgeEventJob" and entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and
                      entity.attributes.get("system_id") == bound.system_id and entity.attributes.get("status") not in {"activated", "cancelled"}
                      for entity in ledger.get_all().values())
        if pending >= bound.max_pending_batches:
            raise InboundBackpressure()
        result = imports.stage(fresh_actor, bound.profile_id, content)
        job = bridge.get(result["id"], "BridgeEventJob")
        job.update(transport="nxtdeal_adf_gateway_v1", inbound_receipt_id=receipt_id)
        receipt = {"workspace_id": ledger.tenant.workspace_id,
            "system_id": bound.system_id, "profile_id": bound.profile_id, "profile_hash": profiles.checked(bound.profile_id)["hash"],
            "job_id": result["id"], "body_hash": fingerprint, "delivery_id_hash": bridge.digest(delivery_id),
            "environment": bound.environment, "binding_revision": bound.revision,
            "received_at": bridge.now(), "authorized_by": actor["employee_id"], "transport": "nxtdeal_adf_gateway_v1"}
        receipt["checksum"] = bridge.digest(receipt)
        bridge.put(Entity(receipt_id, "BridgeInboundDelivery", receipt))
        bridge.audit(fresh_actor, "inbound.received", receipt_id)
    return {"status": "received_for_review", "receipt_id": receipt_id}


def accepting(endpoint_id):
    with bridge.LOCK: _authorized(endpoint_id)


def _review_details(bound, policy):
    """Administrator diagnostics only; neither secret lookup nor an authorization."""
    reasons = []
    if not bound:
        return ["binding_unavailable"], False
    try: bridge.require_durable_state()
    except (ValueError, PermissionError): reasons.append("durable_storage_required")
    try:
        profile = profiles.checked(bound.profile_id)
        if profile.get("status") != "approved": reasons.append("profile_approval_required")
    except (ValueError, KeyError):
        profile = None
        reasons.append("profile_unavailable_or_changed")
    if bridge.get(bound.system_id, "BridgeSystem").get("paused"):
        reasons.append("source_paused")
    try: _check_environment(bound)
    except (ValueError, PermissionError, KeyError): reasons.append("environment_conflict")
    can_review = not reasons
    if policy.get("enabled"):
        record = credential_store.get_record(policy.get("authorized_by"))
        if not record or record.get("disabled") or record.get("role") != "ADMIN":
            reasons.append("authorizing_administrator_unavailable")
        if (policy.get("revision") != bound.revision or policy.get("profile_id") != bound.profile_id or
                policy.get("system_id") != bound.system_id or policy.get("environment") != bound.environment or
                profile and policy.get("profile_hash") != profile.get("hash")):
            reasons.append("binding_review_required")
    return reasons, can_review


def status(actor, system_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
        bindings = {key:value for key,value in _BINDINGS.items() if value.workspace_id == ledger.tenant.workspace_id and value.system_id == system_id}
        policies = {entity.attributes["endpoint_id"]:entity.attributes for entity in ledger.get_all().values()
                    if entity.entity_type == "BridgeInboundPolicy" and entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and entity.attributes.get("system_id") == system_id}
        pending = sum(entity.entity_type == "BridgeEventJob" and entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and
                      entity.attributes.get("system_id") == system_id and entity.attributes.get("status") not in {"activated", "cancelled"}
                      for entity in ledger.get_all().values())
        received, inconsistent = [], 0
        from core.bridge_inbound_evidence import checked
        from core.bridge_contracts import timestamp
        for entity in ledger.get_all().values():
            if entity.entity_type != "BridgeInboundDelivery" or entity.attributes.get("workspace_id") != ledger.tenant.workspace_id or entity.attributes.get("system_id") != system_id:
                continue
            try:
                job_id = entity.attributes["job_id"]
                evidence = checked(job_id, bridge.get(job_id, "BridgeEventJob"))
                if not evidence or evidence["receipt_id"] != entity.id: raise ValueError("Receipt ownership changed")
                timestamp(evidence["received_at"])
                received.append(evidence["received_at"])
            except (ValueError, KeyError, TypeError): inconsistent += 1
        results = []
        for endpoint in sorted(set(bindings) | set(policies)):
            bound, policy = bindings.get(endpoint), policies.get(endpoint, {})
            reasons, can_review = _review_details(bound, policy)
            effective = "disabled"
            if policy.get("enabled"):
                try: _authorized(endpoint); effective = "queue_full" if bound and pending >= bound.max_pending_batches else "ready"
                except (ValueError, PermissionError, KeyError): effective = "review_required"
            results.append({"endpoint_id":endpoint, "enabled":policy.get("enabled",False), "effective_status":effective,
                "profile_id":bound.profile_id if bound else policy.get("profile_id"), "binding_available":bound is not None,
                "binding_revision":bound.revision if bound else None, "environment":bound.environment if bound else policy.get("environment"),
                "authorized_revision":policy.get("revision"), "pending_batches":pending,
                "review_reasons":reasons, "can_review_policy":can_review,
                "review_token":_review_token(bound) if bound and can_review else None,
                "max_pending_batches":bound.max_pending_batches if bound else None})
    return {"system_id":system_id, "gateways":results, "policy_only":True,
            "received_delivery_count":len(received), "last_received_at":max(received) if received else None,
            "delivery_evidence_issues":inconsistent,
            "notice":"Gateway policy status only; signing credentials and sender connectivity are not probed. Counts describe consistent retained receipts for this source. Deliveries stage for human review and do not approve profiles, activate records or enable Chrono delivery."}
