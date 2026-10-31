"""Explicit read-only connector probes with sanitized, revision-bound results.

Health is diagnostic evidence, never authorization to collect or write. Adapter
implementations own their bounded network timeouts; a lease fences late replies.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from core import dealer_bridge as bridge, bridge_runtime as runtime
from core.bridge_contracts import timestamp
from core.bridge_sync import ConnectorFailure
from core.bridge_credentials import CredentialUnavailable

STATUSES = frozenset({"ready", "degraded", "unavailable", "authentication_required", "permission_denied", "rate_limited", "source_changed"})
LEASE_SECONDS = 60


def utcnow():
    return datetime.now(timezone.utc)


def check(actor, system_id):
    with bridge.mutation(actor):
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        bound = runtime.binding(system_id)
        if system.get("paused"):
            raise ValueError("System is paused")
        if "health" not in bound.capabilities:
            raise ValueError("Connector health checks are not available")
        current = utcnow()
        pending = system.get("health_probe")
        if pending and timestamp(pending["lease_until"]) > current:
            return {"status": "checking", "stored": False}
        token = uuid4().hex
        system["health_probe"] = {"token": token, "lease_until": (current + timedelta(seconds=LEASE_SECONDS)).isoformat()}
    try:
        result = bound.adapter.health()
        status = result.get("status") if isinstance(result, dict) else None
        if not isinstance(status, str) or status not in STATUSES:
            status, code = "unavailable", "invalid_health_response"
        else:
            code = "reported_by_connector"
        # Never return/store adapter diagnostics, URLs, credentials or samples.
    except ConnectorFailure as exc:
        status, code = exc.code, "connector_failure"
    except CredentialUnavailable:
        status, code = "authentication_required", "credential_unavailable"
    except Exception:
        status, code = "unavailable", "health_check_failed"
    with bridge.mutation(actor):
        bridge.require_durable_state()
        system = bridge.get(system_id, "BridgeSystem")
        pending = system.get("health_probe") or {}
        if pending.get("token") != token or timestamp(pending["lease_until"]) <= utcnow():
            return {"status": "discarded", "stored": False}
        try:
            unchanged = runtime.binding(system_id) is bound
        except ValueError:
            unchanged = False
        system.pop("health_probe", None)
        if system.get("paused") or not unchanged:
            return {"status": "discarded", "stored": False}
        system["connector_health"] = {"status": status, "code": code,
                                      "checked_at": utcnow().isoformat(), "binding_revision": bound.revision, "binding_environment": bound.environment}
        bridge.audit(actor, "system.health_check", system_id)
        return {**deepcopy(system["connector_health"]), "stored": True}


def public(system, runtime_description):
    result = deepcopy(system.get("connector_health"))
    if result is None:
        return None
    result["current_binding"] = (runtime_description.get("status") == "bound" and
                                 runtime_description.get("revision") == result.get("binding_revision") and
                                 runtime_description.get("environment", "unspecified") == result.get("binding_environment", "unspecified"))
    return result
