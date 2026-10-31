"""Scoped, data-minimal activity feed from retained Bridge audit records."""
from core import dealer_bridge as bridge
from core.dealeros import ledger

DIRECT = frozenset({"BridgeMapping", "BridgeJob", "BridgeEventProfile", "BridgeEventJob", "BridgeSyncState", "BridgeWriteProposal", "BridgeInboundPolicy", "BridgeInboundDelivery"})
PARENTS = {"BridgeIdentityReview": ("job_id", "BridgeJob"),
           "BridgeEventIdentityReview": ("job_id", "BridgeEventJob"),
           "BridgeSyncMappingTransition": ("state_id", "BridgeSyncState"),
           "BridgeSyncRecovery": ("state_id", "BridgeSyncState"),
           "BridgeChronoDelivery": ("event_id", "SourceObservation")}


def _source(entity, entities):
    if not entity or entity.attributes.get("workspace_id") != ledger.tenant.workspace_id:
        return None
    attrs = entity.attributes
    if entity.entity_type == "BridgeSystem":
        return entity.id
    if entity.entity_type in DIRECT:
        return attrs.get("system_id")
    if entity.entity_type == "SourceObservation" and attrs.get("origin") == "dealer_bridge":
        return attrs.get("system_id")
    parent_spec = PARENTS.get(entity.entity_type)
    if parent_spec:
        key, kind = parent_spec
        parent = entities.get(attrs.get(key))
        if parent and parent.entity_type == kind:
            return _source(parent, entities)
    return None


def read(actor, system_id, limit=25, before_id=None):
    bridge.authorize(actor)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Activity page size must be between 1 and 100")
    if before_id is not None and (not isinstance(before_id, str) or not before_id or len(before_id) > 120):
        raise ValueError("Use an activity cursor from this system")
    with bridge.LOCK:
        bridge.get(system_id, "BridgeSystem")
        entities = dict(ledger.get_all())
        records = [entity for entity in entities.values() if entity.entity_type == "BridgeAudit" and
                   entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and
                   _source(entities.get(entity.attributes.get("record_id")), entities) == system_id]
        records.sort(key=lambda entity: (entity.attributes["at"], entity.id), reverse=True)
        start = 0
        if before_id is not None:
            positions = [index for index, entity in enumerate(records) if entity.id == before_id]
            if not positions:
                raise ValueError("Activity cursor does not belong to this system")
            start = positions[0] + 1
        page = records[start:start + limit]
        return {"system_id": system_id, "activities": [{"id": entity.id,
                    **{key: entity.attributes[key] for key in ("action", "actor", "record_id", "at")},
                    "principal": entity.attributes.get("principal")} for entity in page],
                "next_before_id": page[-1].id if start + len(page) < len(records) else None,
                "total_activities": len(records),
                "notice": "Retained source-scoped Bridge actions only. Customer values, decision reasons and cursor tokens are omitted. Older actions may have no recorded credential type. Missing or unrelated targets and global Chrono policy actions are excluded; this is not a tamper-proof audit log."}
