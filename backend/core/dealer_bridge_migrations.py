"""Explicit, additive graph migration; never reinterpret legacy imports as trusted."""
from core import dealer_bridge as bridge
from core.dealeros import ledger
from core.entities import Entity

VERSION_ID = "DEALER-BRIDGE-SCHEMA"

def migrate(actor):
    with bridge.mutation(actor, True):
        existing = ledger.get_entity(VERSION_ID)
        if existing:
            if existing.entity_type != "BridgeSchemaVersion" or existing.attributes.get("workspace_id") != ledger.tenant.workspace_id:
                raise ValueError("Schema marker is not valid for this workspace")
            if type(existing.attributes.get("version")) is not int or existing.attributes["version"] != 1:
                raise ValueError("Unsupported bridge schema version")
            return {"version": 1, "changed": False}
        bridge.put(Entity(VERSION_ID, "BridgeSchemaVersion", {
            "version": 1, "workspace_id": ledger.tenant.workspace_id,
            "applied_at": bridge.now(), "applied_by": actor["employee_id"],
        }))
        bridge.audit(actor, "schema.migrate.v1", VERSION_ID)
    return {"version": 1, "changed": True}
