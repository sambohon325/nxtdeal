"""Human-reviewed replacement of an unfinished local paginated snapshot."""
from copy import deepcopy
import re

from core import dealer_bridge as bridge, bridge_sync as sync
from core.bridge_adapters.export_file_paged import PagedExportFileConnector
from core.bridge_contracts import timestamp


def _plan(state_id):
    state = bridge.get(state_id, "BridgeSyncState")
    mapping, bound = sync._check(state)
    if state.get("mode", "sync") != "sync" or type(bound.adapter) is not PagedExportFileConnector:
        raise ValueError("Snapshot restart requires the built-in paginated local export reader")
    cursor = state.get("cursor")
    if not isinstance(cursor, str) or not re.fullmatch(r"csvpage:v1:[0-9a-f]{64}:[0-9]{1,6}:more|csvrestart:v1:[0-9a-f]{64}", cursor):
        raise ValueError("An unfinished paginated snapshot is required")
    if state.get("lease_until") and timestamp(state["lease_until"]) > sync.utcnow():
        raise ValueError("Wait for the in-progress read before restart")
    pending = None
    if state.get("pending_job_id"):
        pending = bridge.get(state["pending_job_id"], "BridgeJob")
        if (pending.get("status") != "cancelled" or pending.get("sync_state_id") != state_id or
                pending.get("system_id") != state["system_id"] or pending.get("mapping_id") != state["mapping_id"]):
            raise ValueError("Resolve and checkpoint or cancel the pending import before restart")
    return deepcopy(state), bound, bridge.digest([state_id, state, mapping, pending])


def available(state_id):
    """Eligibility only; no filesystem read and no review authorization."""
    try:
        _plan(state_id)
    except (ValueError, PermissionError):
        return False
    return True


def _inspect(actor, state_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        state, bound, token = _plan(state_id)
    try:
        restart_cursor = bound.adapter.reviewed_restart_cursor(state["object_type"])
    except Exception:
        raise ValueError("Replacement snapshot inspection failed; check the authorized local export") from None
    with bridge.LOCK:
        bridge.authorize(actor)
        _, current, current_token = _plan(state_id)
        if current is not bound or current_token != token:
            raise ValueError("Collection configuration changed; review restart again")
    return state, bound, token, restart_cursor


def preview(actor, state_id):
    state, bound, token, restart_cursor = _inspect(actor, state_id)
    return {"state_id": state_id, "review_token": bridge.digest([token, restart_cursor]),
            "replacement_fingerprint": restart_cursor.split(":")[2], "binding_revision": bound.revision,
            "pages_previously_accepted": state.get("pages_accepted", 0), "schedule_after_restart": "disabled",
            "notice": "Starts the reviewed file again at its first row. Retains imported records, observations and prior receipts; duplicate rows remain subject to normal identity review. Missing rows never delete records. This does not certify complete source history. Every new page still requires activation."}


def restart(actor, state_id, review_token, reason):
    bridge.authorize(actor, human=True)
    reason = bridge.review_reason(reason)
    state, bound, token, restart_cursor = _inspect(actor, state_id)
    if not isinstance(review_token, str) or review_token != bridge.digest([token, restart_cursor]):
        raise ValueError("Snapshot or collection state changed; review restart again")
    with bridge.mutation(actor, True):
        _, current, current_token = _plan(state_id)
        if current is not bound or current_token != token:
            raise ValueError("Collection configuration changed; review restart again")
        recovery_id = bridge.add("BridgeSyncRecovery", {"state_id": state_id,
            "action": "restart_reviewed_snapshot", "checkpoint_hash": bridge.digest(state["cursor"]),
            "replacement_fingerprint": restart_cursor.split(":")[2], "binding_revision": bound.revision,
            "cancelled_job_id": state.get("pending_job_id"), "pages_previously_accepted": state.get("pages_accepted", 0),
            "review_token": review_token, "reviewed_by": actor["employee_id"], "reviewed_at": bridge.now(), "reason": reason})
        current_state = bridge.get(state_id, "BridgeSyncState")
        current_state.update(cursor=restart_cursor, enabled=False, status="idle", pending_job_id=None,
            pending_cursor=None, pending_complete=None, lease_token=None, lease_until=None,
            attempts=0, last_error=None, last_error_code=None, retry_after_seconds=None,
            next_attempt_at=sync.utcnow().isoformat(), updated_at=bridge.now(), last_recovery_id=recovery_id)
        bridge.audit(actor, "sync.snapshot_restart_reviewed", recovery_id)
    return {"recovery_id": recovery_id, "state": sync.public(state_id, current_state)}
