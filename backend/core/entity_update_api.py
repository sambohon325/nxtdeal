"""
Generic entity-attribute update (Sam: "we need to be able to edit the information in
the menu dashes where it makes sense"). Lets an authorized role edit a real entity's
attributes inline from wherever it's shown -- a Top Menu dash's linked_entity block, a
workflow window's LiveDataPanel -- rather than adding a bespoke edit form per entity
type. Reuses core/security.py's can_access_entity(), the exact same role-gate
GET /entity/{id} and every AI-tool graph read (core/ai_tools.py) already enforce, so
editing never opens up more than viewing already does -- if a role can't see an entity
type, it can't edit one either.

Security-owned API keys, permission overrides and approval requests cannot be
edited here, even by ADMIN: their dedicated handlers enforce credential freshness,
expiry, revocation, approval transitions and audit history.

`id` and `entity_type` are permanently protected (identity fields, never patchable
through this endpoint). Everything else in `attributes` can be patched; unknown keys
are simply added, matching how every importer/seed script already treats `attributes`
as an open dict rather than a fixed schema. Every update is audit-logged with a real
before/after diff (core/audit.py), same as every other mutating action in this
codebase, and persisted immediately via the same save_graph()/GRAPH_PATH convention
core/field_notes.py and friends already use.
"""

from core.repository import repository
from core.security import can_access_entity
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, AUDIT_PATH
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.entity_types import API_KEY, PERMISSION_OVERRIDE, APPROVAL_REQUEST


_PROTECTED_KEYS = {"id", "entity_type"}
_CONTROL_RECORDS = {API_KEY, PERMISSION_OVERRIDE, APPROVAL_REQUEST, "MarketplaceInstall", "SystemConfig", "SsoConfig", "Entitlement", "Connection", "BotCapabilityGrant", "ProviderCredential", "TeamAgent", "ExecutionPolicy"}


def update_entity_api(role, actor_employee_id, entity_id, patch):

    entity = repository.get_entity(entity_id)

    if not entity:
        return {"error": "Entity not found"}

    if not can_access_entity(role, entity.entity_type):
        return {"error": "Forbidden: your role cannot edit this entity type"}

    if entity.entity_type in _CONTROL_RECORDS:
        return {"error": "Use the dedicated security or approval workflow to modify this record."}

    if not isinstance(patch, dict) or not patch:
        return {"error": "patch must be a non-empty object of attribute -> new value"}

    clean_patch = {
        key: value for key, value in patch.items()
        if key not in _PROTECTED_KEYS
    }

    if not clean_patch:
        return {"error": "No editable fields in patch -- 'id' and 'entity_type' cannot be changed."}

    before = {key: entity.attributes.get(key) for key in clean_patch}

    entity.attributes.update(clean_patch)

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="entity_updated",
        summary=f"{entity.entity_type} {entity_id} updated by {actor_employee_id}",
        entity_id=entity_id,
        actor=actor_employee_id,
        details={"before": before, "after": clean_patch},
    )
    save_audit_log(AUDIT_PATH)

    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes,
    }
