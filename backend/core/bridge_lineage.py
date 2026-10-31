"""Read-only source lineage: current projection and immutable source observations."""
from copy import deepcopy

from core import dealer_bridge as bridge
from core.bridge_contracts import FIELDS, storage_kind, timestamp
from core.dealeros import ledger
from core.bridge_projection import snapshot


def lookup(actor, system_id, object_type, external_id, limit=25, before_event_id=None):
    bridge.authorize(actor)
    if (not isinstance(object_type, str) or not object_type.strip() or object_type != object_type.strip() or len(object_type) > 120 or
            not isinstance(external_id, str) or not external_id.strip() or external_id != external_id.strip() or len(external_id) > 500):
        raise ValueError("Bounded source object and exact external ID required")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("History page size must be between 1 and 100")
    if before_event_id is not None and (not isinstance(before_event_id, str) or len(before_event_id) != 68 or not before_event_id.startswith("BRE-")):
        raise ValueError("Use a history cursor from this source lookup")
    with bridge.LOCK:
        system = bridge.get(system_id, "BridgeSystem")
        key = bridge.digest([ledger.tenant.workspace_id, system_id, object_type, external_id])
        link = bridge.get("BRX-" + key, "BridgeExternalID")
        kind = link["kind"]
        target = ledger.get_entity(link["target_id"])
        if (kind not in FIELDS or link.get("system_id") != system_id or link.get("object_type") != object_type or
                link.get("external_id") != external_id or not target or target.entity_type != storage_kind(kind) or
                target.attributes.get("workspace_id", ledger.tenant.workspace_id) != ledger.tenant.workspace_id):
            raise ValueError("Source identity target is unavailable in this workspace")
        current, conflicts = snapshot(kind, target.attributes)
        events = [entity for entity in list(ledger.get_all().values())
                  if entity.entity_type == "SourceObservation" and entity.attributes.get("origin") == "dealer_bridge" and
                  entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and
                  entity.attributes.get("external_key") == key and entity.attributes.get("entity_id") == target.id]
        events.sort(key=lambda event: (timestamp(event.attributes["source_timestamp"]),
                                      timestamp(event.attributes["import_timestamp"]), event.id), reverse=True)
        start = 0
        if before_event_id is not None:
            positions = [number for number, event in enumerate(events) if event.id == before_event_id]
            if not positions:
                raise ValueError("History cursor does not belong to this source lookup")
            start = positions[0] + 1
        page = events[start:start + limit]
        observations = [{"event_id": event.id,
            "source_timestamp": event.attributes["source_timestamp"], "import_timestamp": event.attributes["import_timestamp"],
            "mapping_id": event.attributes["mapping_id"], "import_job_id": event.attributes["raw_reference"],
            "confidence": event.attributes.get("confidence"), "identity_resolution": event.attributes.get("identity_resolution"),
            "values": deepcopy(event.attributes["values"])} for event in page]
        more = start + len(page) < len(events)
        return {"canonical_id": target.id, "kind": kind, "current_values": current, "legacy_conflicts": conflicts,
            "source": {"system_id": system_id, "system_name": system["name"], "vendor": system["vendor"],
                       "object_type": object_type, "external_id": external_id,
                       "latest_source_timestamp": link["modified_at"], "projection": link.get("projection", "update")},
            "observations": observations, "total_observations": len(events),
            "next_before_event_id": page[-1].id if more else None,
            "notice": "Current values may include later dealership edits. Source observations preserve what was imported; they are not an as-of reconstruction of the whole record."}
