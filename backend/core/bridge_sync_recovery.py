"""Reviewed replay of an activated pending page without accepting its cursor."""
from core import dealer_bridge as bridge, bridge_sync as sync
from core.bridge_contracts import timestamp
from core.bridge_receipts import snapshot_integrity


def _plan(state_id):
    state = bridge.get(state_id, "BridgeSyncState")
    if state.get("lease_until") and timestamp(state["lease_until"]) > sync.utcnow():
        raise ValueError("Wait for the in-progress read before recovery")
    if not state.get("pending_job_id"):
        raise ValueError("An activated pending import is required for replay")
    job = bridge.get(state["pending_job_id"], "BridgeJob")
    if (job.get("status") != "activated" or job.get("sync_state_id") != state_id or
            job.get("mapping_id") != state["mapping_id"] or job.get("system_id") != state["system_id"]):
        raise ValueError("An activated pending import belonging to this stream is required")
    # Recovery never claims the questionable checkpoint was approved. It keeps
    # the last accepted cursor and the entire prior job for investigation.
    token = bridge.digest([state_id, state, job])
    return state, job, token


def preview(actor, state_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        state, job, token = _plan(state_id)
        return {"state_id": state_id, "pending_job_id": state["pending_job_id"],
                "review_token": token, "receipt_integrity": snapshot_integrity(job, state["pending_job_id"]),
                "checkpoint_action": "preserve_last_accepted", "schedule_after_recovery": "disabled",
                "notice": "Keeps imported records, observations and the prior job. Discards only the pending cursor, retaining the last accepted position for a reviewed reread. The source must still support replay from that position; no missing history is reconstructed."}


def replay(actor, state_id, review_token, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        state, job, token = _plan(state_id)
        if not isinstance(review_token, str) or token != review_token:
            raise ValueError("Source state or import changed; review recovery again")
        recovery_id = bridge.add("BridgeSyncRecovery", {"state_id": state_id, "job_id": state["pending_job_id"],
            "action": "replay_from_last_accepted", "checkpoint_hash": bridge.digest(state.get("cursor")),
            "discarded_pending_cursor_hash": bridge.digest(state.get("pending_cursor")),
            "receipt_integrity": snapshot_integrity(job, state["pending_job_id"]), "review_token": token,
            "reviewed_by": actor["employee_id"], "reviewed_at": bridge.now(), "reason": reason})
        state.update(enabled=False, status="idle", pending_job_id=None, pending_cursor=None, pending_complete=None,
                     lease_token=None, lease_until=None, attempts=0, last_error=None, last_error_code=None,
                     retry_after_seconds=None, next_attempt_at=sync.utcnow().isoformat(), updated_at=bridge.now(),
                     last_recovery_id=recovery_id)
        bridge.audit(actor, "sync.replay_reviewed", recovery_id)
    return {"recovery_id": recovery_id, "state": sync.public(state_id, state)}
