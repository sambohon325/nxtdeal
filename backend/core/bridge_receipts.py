"""Snapshot receipt consistency, including the owning job and retained evidence.

Checksums detect inconsistency; they are not signatures against a graph writer.
"""

def snapshot_integrity(job, job_id):
    from core import dealer_bridge as bridge
    receipt = job.get("activation_receipt")
    if receipt is None:
        return "not_recorded"
    if not isinstance(receipt, dict):
        return "mismatch"
    try:
        fields = ("system_id", "mapping_id", "mapping_hash", "content_hash", "source_evidence",
                  "validation_hash", "validated_at", "validated_by", "validated_principal",
                  "transport", "binding_revision", "collection_mode", "sync_state_id", "collection_page", "collection_environment",
                  "expectations", "reconciliation", "activated_by", "activated_at")
        consistent = (job.get("status") == "activated" and receipt.get("job_id") == job_id and
                      receipt.get("checksum") == bridge.digest({key: value for key, value in receipt.items() if key != "checksum"}) and
                      all(receipt.get(field) == job.get(field) for field in fields) and
                      receipt.get("staged_by") == job.get("created_by") and
                      receipt.get("staged_at") == job.get("created_at") and
                      receipt.get("staged_principal") == job.get("created_principal"))
        if job.get("payload_cleanup"):
            consistent = consistent and job.get("rows") == [] and job.get("preview") == []
        else:
            consistent = (consistent and bridge.digest(job.get("rows")) == job.get("content_hash") and
                          bridge.digest(job.get("preview")) == receipt.get("preview_hash"))
    except (TypeError, ValueError):
        consistent = False
    return "consistent" if consistent else "mismatch"
