"""Explicit terminal-job payload cleanup; not source-history deletion or undo."""
from copy import deepcopy

from core import dealer_bridge as bridge


def _receipt_consistent(job, job_id):
    from core.bridge_receipts import snapshot_integrity
    return snapshot_integrity(job, job_id) == "consistent"


def _preview(job_id, job):
    eligible = (job["status"] == "cancelled" or job["status"] == "activated" and _receipt_consistent(job, job_id)) and not job.get("payload_cleanup")
    token = bridge.digest({"job_id": job_id, "status": job["status"], "rows": job.get("rows", []),
                           "preview": job.get("preview", []), "content_hash": job.get("content_hash"),
                           "receipt": job.get("activation_receipt"), "source_evidence": job.get("source_evidence"),
                           "mapping_hash": job.get("mapping_hash"),
                           "cleanup": job.get("payload_cleanup")})
    return {"job_id": job_id, "status": job["status"], "eligible": eligible,
            "retained_rows": len(job.get("rows", [])), "retained_preview_rows": len(job.get("preview", [])),
            "receipt_required": job["status"] == "activated", "receipt_consistent": _receipt_consistent(job, job_id),
            "review_token": token, "cleanup": deepcopy(job.get("payload_cleanup")),
            "notice": "Permanently removes this terminal import's staging rows and cached preview only. Imported records, source observations, audit records, fingerprints and approval receipts remain. This does not undo an import, erase all personal data or delete backups. Follow your dealership's retention requirements before proceeding."}


def preview(actor, job_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        return _preview(job_id, bridge.get(job_id, "BridgeJob"))


def cleanup(actor, job_id, review_token, reason):
    bridge.authorize(actor, human=True)
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, human=True):
        job = bridge.get(job_id, "BridgeJob")
        if job["status"] not in {"activated", "cancelled"}:
            raise ValueError("Only activated or cancelled import payloads can be removed")
        if job.get("payload_cleanup"):
            return {"job_id": job_id, "status": "already_removed", "cleanup": deepcopy(job["payload_cleanup"])}
        if job["status"] == "activated" and not _receipt_consistent(job, job_id):
            raise ValueError("Activated import requires a consistent recorded receipt before payload cleanup")
        if not isinstance(review_token, str) or review_token != _preview(job_id, job)["review_token"]:
            raise ValueError("Import payload changed; review cleanup again")
        job["payload_cleanup"] = {"removed_at": bridge.now(), "removed_by": actor["employee_id"],
                                  "reason": reason, "row_count": len(job.get("rows", [])),
                                  "preview_row_count": len(job.get("preview", []))}
        job["rows"] = []
        job["preview"] = []
        bridge.audit(actor, "import.payload.cleanup", job_id)
        return {"job_id": job_id, "status": "removed", "cleanup": deepcopy(job["payload_cleanup"])}
