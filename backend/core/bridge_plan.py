"""Read-only dependency guidance from approved mappings, never an execution plan."""
from collections import Counter, defaultdict

from core import dealer_bridge as bridge
from core.bridge_contracts import REFERENCE_TYPES
from core.dealeros import ledger


def import_order(actor, system_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        system = bridge.get(system_id, "BridgeSystem")
        records = list(ledger.get_all().values())
        mappings, excluded = defaultdict(list), Counter()
        for entity in records:
            value = entity.attributes
            if (entity.entity_type != "BridgeMapping" or value.get("workspace_id") != ledger.tenant.workspace_id or
                    value.get("system_id") != system_id):
                continue
            if value.get("status") != "approved":
                excluded[value.get("status", "unknown")] += 1
                continue
            if bridge.mapping_digest(value) != value.get("hash"):
                excluded["changed_definition"] += 1
                continue
            mappings[value["object_type"]].append((entity.id, value))
        linked = Counter((entity.attributes.get("object_type"), entity.attributes.get("kind")) for entity in records
                         if entity.entity_type == "BridgeExternalID" and entity.attributes.get("workspace_id") == ledger.tenant.workspace_id
                         and entity.attributes.get("system_id") == system_id)
        nodes, dependencies = {}, {}
        for object_type, options in sorted(mappings.items()):
            refs, direct, warnings = {}, set(), []
            kinds = sorted({value["kind"] for _, value in options})
            if len(options) > 1:
                warnings.append("Choose the intended approved mapping version before importing this object.")
            if len(kinds) > 1:
                warnings.append("This source object has conflicting canonical types; review its mappings.")
            for mapping_id, value in options:
                for field, spec in value["fields"].items():
                    if field not in REFERENCE_TYPES:
                        continue
                    if spec["transform"] != "external_id":
                        direct.add(field)
                        continue
                    source, kind = spec["object_type"], REFERENCE_TYPES[field]
                    ref = refs.setdefault((source, kind), {"object_type": source, "kind": kind, "fields": set(),
                                                         "existing_links": linked[(source, kind)]})
                    ref["fields"].add(field)
            dependencies[object_type] = {source for source, _ in refs if source != object_type and source in mappings}
            for (source, kind), ref in refs.items():
                ref["fields"] = sorted(ref["fields"])
                if source == object_type:
                    ref["status"] = "prior_records_required"
                    warnings.append("References within this source object require previously imported records; split dependent rows into ordered jobs.")
                elif source not in mappings:
                    ref["status"] = "existing_records_only" if ref["existing_links"] else "mapping_required"
                    warnings.append(f"No approved mapping for referenced source object: {source}.")
                elif not any(value["kind"] == kind for _, value in mappings[source]):
                    ref["status"] = "type_mismatch"
                    warnings.append(f"Referenced source object does not map to {kind}: {source}.")
                else:
                    ref["status"] = "mapped"
            nodes[object_type] = {"object_type": object_type, "kinds": kinds,
                "mapping_ids": sorted(mapping_id for mapping_id, _ in options),
                "existing_links": sum(linked[(object_type, kind)] for kind in kinds),
                "references": [refs[key] for key in sorted(refs)], "direct_reference_fields": sorted(direct),
                "warnings": sorted(set(warnings)), "step": None}
        pending, completed, steps = set(nodes), set(), []
        while pending:
            ready = sorted(name for name in pending if dependencies[name] <= completed)
            if not ready:
                break
            steps.append(ready)
            for name in ready:
                nodes[name]["step"] = len(steps)
            pending.difference_update(ready)
            completed.update(ready)
        for name in pending:
            nodes[name]["warnings"].append("Dependency cycle or dependency on a cycle requires mapping review.")
        return {"system_id": system_id, "system_name": system["name"], "paused": bool(system.get("paused")),
                "steps": steps, "objects": list(nodes.values()), "excluded_mappings": dict(sorted(excluded.items())),
                "stored": False, "status": "guidance_only",
                "notice": "Order is derived from approved mapping references. It does not approve, stage or activate imports. Existing link counts do not prove that every referenced row exists; validate each export."}
