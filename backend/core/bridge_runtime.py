"""Trusted runtime bindings. No HTTP endpoint accepts adapters, credentials or URLs.

Each configured system gets a distinct, operator-authenticated connector instance.
Registry existence alone never enables scheduled fetching or external writes.
"""
from dataclasses import dataclass
from threading import RLock

from core.dealeros import ledger
from core.bridge_contracts import Connector, validated_capabilities


@dataclass(frozen=True)
class Binding:
    system_id: str
    workspace_id: str
    vendor: str
    revision: str
    objects: frozenset[str]
    adapter: Connector
    capabilities: frozenset[str]
    environment: str = "unspecified"


_BINDINGS = {}
_LOCK = RLock()


def bind(system_id, adapter, *, revision, objects, environment="unspecified"):
    """Trusted application-startup hook after operator credential authorization."""
    if not isinstance(environment, str) or environment not in {"unspecified", "synthetic", "local_file", "sandbox", "production"}:
        raise ValueError("Known operator-declared connector environment required")
    system = ledger.get_entity(system_id)
    if not system or system.entity_type != "BridgeSystem" or system.attributes.get("workspace_id") != ledger.tenant.workspace_id:
        raise ValueError("Existing system in this workspace required")
    if not isinstance(revision, str) or not revision.strip() or len(revision) > 120:
        raise ValueError("A bounded adapter revision is required")
    if not isinstance(objects, (list, tuple, set, frozenset)) or len(objects) > 100:
        raise ValueError("Explicit bounded source object allowlist required")
    objects = frozenset(objects)
    if not objects or any(not isinstance(obj, str) or not obj.strip() or obj != obj.strip() or len(obj) > 120 for obj in objects):
        raise ValueError("Explicit source object allowlist required")
    capabilities = validated_capabilities(adapter)
    if not capabilities & {"sync", "history"}:
        raise ValueError("Adapter must implement read-only sync or history")
    with _LOCK:
        if any(value.adapter is adapter and key != system_id for key, value in _BINDINGS.items()):
            raise ValueError("Use a distinct authenticated adapter instance per system")
        previous = _BINDINGS.get(system_id)
        if previous and previous.workspace_id == ledger.tenant.workspace_id and previous.revision == revision:
            if previous.adapter is adapter and previous.objects == objects and previous.capabilities == capabilities and previous.vendor == system.attributes["vendor"] and previous.environment == environment:
                return
            raise ValueError("Replacing an active connector or its scope requires a new revision")
        _BINDINGS[system_id] = Binding(system_id, ledger.tenant.workspace_id, system.attributes["vendor"], revision, objects, adapter, capabilities, environment)


def unbind(system_id):
    with _LOCK:
        _BINDINGS.pop(system_id, None)


def binding(system_id):
    with _LOCK:
        value = _BINDINGS.get(system_id)
        if not value or value.workspace_id != ledger.tenant.workspace_id:
            raise ValueError("No authorized runtime connector is bound to this system")
        system = ledger.get_entity(system_id)
        if (not system or system.entity_type != "BridgeSystem" or
                system.attributes.get("workspace_id") != value.workspace_id or
                system.attributes.get("vendor") != value.vendor):
            raise ValueError("Source identity changed; review the runtime connector binding")
        return value


def describe(system_id):
    try:
        value = binding(system_id)
    except ValueError:
        return {"status": "unavailable", "capabilities": []}
    return {"status": "bound", "revision": value.revision, "environment": value.environment, "objects": sorted(value.objects),
            "capabilities": sorted(value.capabilities & {"sync", "history", "discover", "schema", "health", "reconcile"})}
