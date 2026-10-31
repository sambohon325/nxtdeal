"""Data-minimal export structure diagnostics; never mapping approval or staging."""
from hashlib import sha256
from core import dealer_bridge as bridge
from core.bridge_connectors import inspect_file, source_columns_profile
from core.dealeros import ledger
from core.bridge_receipts import snapshot_integrity


def inspect(actor, mapping_id, content, file_format="csv"):
    bridge.authorize(actor)
    with bridge.LOCK:
        mapping = bridge.get(mapping_id, "BridgeMapping")
        bridge.get(mapping["system_id"], "BridgeSystem")
        if mapping["status"] == "revoked" or bridge.mapping_digest(mapping) != mapping["hash"]:
            raise ValueError("An unchanged, non-revoked mapping is required")
        headers, rows = inspect_file(content, file_format)
        required = {spec["source"] for spec in mapping["fields"].values()} | set(source_columns_profile(mapping.get("source_columns")).values())
        missing = sorted(required - set(headers))
        prior = [entity for entity in ledger.get_all().values() if entity.entity_type == "BridgeJob" and
                 entity.attributes.get("workspace_id") == ledger.tenant.workspace_id and
                 entity.attributes.get("mapping_id") == mapping_id and entity.attributes.get("status") == "activated"]
        prior.sort(key=lambda entity: (entity.attributes.get("activated_at", ""), entity.id), reverse=True)
        previous = prior[0] if prior else None
        previous_headers = previous.attributes.get("headers") if previous else None
        # A missing legacy schema is unknown, never evidence of an empty schema.
        comparable = (isinstance(previous_headers, list) and all(isinstance(value, str) for value in previous_headers) and
                      snapshot_integrity(previous.attributes, previous.id) == "consistent" and
                      bridge.digest(sorted(previous_headers)) == previous.attributes.get("source_evidence", {}).get("schema_hash"))
        fields = [{"field": field, "source": spec["source"], "present": spec["source"] in headers,
                   "blank_rows": sum(not str(row.get(spec["source"], "")).strip() for row in rows) if spec["source"] in headers else None}
                  for field, spec in mapping["fields"].items()]
        return {"mapping_id": mapping_id, "mapping_hash": mapping["hash"], "stored": False,
                "status": "missing_columns" if missing else "empty_export" if not rows else "columns_present",
                "row_count": len(rows), "headers": headers, "missing_columns": missing,
                "unmapped_columns": sorted(set(headers) - required), "mapped_fields": fields,
                "content_hash": sha256(content.encode("utf-8")).hexdigest(), "schema_hash": bridge.digest(sorted(headers)),
                "baseline_job_id": previous.id if previous else None, "schema_comparison_available": comparable,
                "added_columns": sorted(set(headers) - set(previous_headers)) if comparable else [],
                "removed_columns": sorted(set(previous_headers) - set(headers)) if comparable else [],
                "notice": "Structure and blank-value counts only. Values, IDs, timestamps, identities and totals still require mapping simulation and validation. Added or removed columns never change the approved mapping. No row values or source IDs are returned, and no data is stored."}
