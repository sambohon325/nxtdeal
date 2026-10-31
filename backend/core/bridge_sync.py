"""Durable, opt-in, read-only collection. Every nonempty page becomes a reviewed job.

Cursors advance only after activation; no worker approves mappings or imports.
Adapters must enforce their own network timeout. Runtime bindings are trusted code.
"""
import asyncio
from core.worker_io import run_worker_io
import csv
import io
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from core import dealer_bridge as bridge, bridge_runtime as runtime
from core.bridge_contracts import SourceRecord, SyncPage, timestamp, source_timestamp, DECIMAL_FIELDS
from core.bridge_connectors import source_columns_profile
from core.dealeros import ledger
from core.auth import credential_store
from core.bridge_credentials import CredentialUnavailable

_TASK = None
log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
LEASE_SECONDS = 300


class ConnectorFailure(Exception):
    """Safe adapter failure metadata; never attach vendor response text or secrets.

    Retry-After is an adapter-parsed bounded duration, not an untrusted header.
    Access/permission/schema changes always require operator review.
    """
    def __init__(self, retryable=True, *, code="unavailable", retry_after_seconds=None):
        if type(retryable) is not bool or not isinstance(code, str) or code not in {"unavailable", "rate_limited", "authentication_required", "permission_denied", "source_changed"}:
            raise ValueError("Known connector failure code and boolean retry policy required")
        if retry_after_seconds is not None and (type(retry_after_seconds) is not int or not 1 <= retry_after_seconds <= 86400):
            raise ValueError("Retry delay must be between 1 and 86400 seconds")
        if code in {"authentication_required", "permission_denied", "source_changed"}:
            retryable = False
        self.retryable = retryable
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Connector read failed")


def utcnow():
    return datetime.now(timezone.utc)


def public(state_id, state):
    try:
        current_binding = runtime.binding(state["system_id"])
        binding_review_required = (state.get("authorized_binding_revision") != current_binding.revision or state.get("authorized_environment", "unspecified") != current_binding.environment)
    except ValueError:
        binding_review_required = False
    try:
        _check(state)
        if state.get("enabled"):
            _actor(state)
        if state.get("pending_job_id"):
            pending = bridge.get(state["pending_job_id"], "BridgeJob")
            if pending.get("status") == "activated":
                _accepted_page(state_id, state, pending)
        availability = {"status": "ready", "reason": None}
    except (PermissionError, ValueError) as exc:
        availability = {"status": "review_required", "reason": str(exc)}
    from core.bridge_snapshot_restart import available as snapshot_restart_available
    return {"id": state_id, "snapshot_restart_available": snapshot_restart_available(state_id), **deepcopy({key: value for key, value in state.items()
                                      if key not in {"cursor", "pending_cursor", "lease_token", "lease_until", "workspace_id"}}),
            "mode": state.get("mode", "sync"), "availability": {**availability, "binding_review_required": binding_review_required}}


def states(actor):
    bridge.authorize(actor)
    with bridge.LOCK:
        return [public(e.id, e.attributes) for e in ledger.get_all().values()
                if e.entity_type == "BridgeSyncState" and e.attributes.get("workspace_id") == ledger.tenant.workspace_id]


def _mapping(mapping_id):
    mapping = bridge.get(mapping_id, "BridgeMapping")
    if mapping["status"] != "approved" or bridge.mapping_digest(mapping) != mapping["hash"]:
        raise ValueError("An approved unchanged mapping is required")
    return mapping


def _check_environment_namespace(system_id, environment):
    classified = {"synthetic", "sandbox", "production"}
    if environment not in classified:
        return
    for entity in ledger.get_all().values():
        value = entity.attributes
        if (entity.entity_type == "BridgeSyncState" and value.get("workspace_id") == ledger.tenant.workspace_id and
                value.get("system_id") == system_id and value.get("cursor") is not None and
                value.get("checkpoint_environment", value.get("authorized_environment")) in classified - {environment}):
            raise ValueError("This system retains a checkpoint from another source environment; configure a separate system to preserve source identity")
        if (entity.entity_type == "BridgeInboundDelivery" and value.get("workspace_id") == ledger.tenant.workspace_id and
                value.get("system_id") == system_id and value.get("environment") in classified - {environment}):
            raise ValueError("This system retains inbound deliveries from another source environment; configure a separate system to preserve source identity")
        if (entity.entity_type == "BridgeJob" and value.get("workspace_id") == ledger.tenant.workspace_id and
                value.get("system_id") == system_id and value.get("status") != "cancelled" and
                value.get("collection_environment") in classified - {environment}):
            raise ValueError("This system retains pages from another source environment; configure a separate system to preserve source identity")


def configure(actor, mapping_id, enabled=False, interval_seconds=300, mode="sync", require_balanced_journals=None, *, reviewed_binding_revision=None, reviewed_binding_environment=None):
    if require_balanced_journals is not None and type(require_balanced_journals) is not bool:
        raise ValueError("Boolean journal balance policy required")
    if type(enabled) is not bool or type(interval_seconds) is not int or not 60 <= interval_seconds <= 86400:
        raise ValueError("Boolean enabled and interval between 60 and 86400 seconds required")
    if not isinstance(mode, str) or mode not in {"sync", "history"}:
        raise ValueError("Collection mode must be sync or history")
    with bridge.mutation(actor, True):
        mapping = _mapping(mapping_id) if enabled else bridge.get(mapping_id, "BridgeMapping")
        system = bridge.get(mapping["system_id"], "BridgeSystem")
        try:
            configured_binding = runtime.binding(mapping["system_id"])
        except ValueError:
            configured_binding = None
        binding_reviewed = reviewed_binding_revision is not None or reviewed_binding_environment is not None
        if binding_reviewed and (not configured_binding or
                reviewed_binding_revision != configured_binding.revision or reviewed_binding_environment != configured_binding.environment):
            raise ValueError("Connector configuration changed; reload and explicitly review its revision and environment")
        if enabled:
            bridge.require_durable_state()
            connector = runtime.binding(mapping["system_id"])
            _check_environment_namespace(mapping["system_id"], connector.environment)
            if mapping["object_type"] not in connector.objects or mode not in connector.capabilities or system.get("paused"):
                raise ValueError("System paused or source object not authorized for collection")
        # Preserve existing sync identities. Backfill cursors are a separate stream,
        # while both streams retain the same source-record identity namespace.
        stream_key = [ledger.tenant.workspace_id, mapping["system_id"], mapping["object_type"]]
        state_id = "BRSYNC-" + bridge.digest(stream_key + (["history"] if mode == "history" else []))
        entity = ledger.get_entity(state_id)
        if entity:
            state = bridge.get(state_id, "BridgeSyncState")
            if state["mapping_id"] != mapping_id:
                raise ValueError("Existing source stream uses another mapping; migration requires an explicit checkpoint plan")
            if enabled and state.get("status") == "complete":
                raise ValueError("Completed history requires a separate reviewed replay plan")
        else:
            from core.entities import Entity
            state = {"system_id": mapping["system_id"], "mapping_id": mapping_id, "object_type": mapping["object_type"], "mode": mode,
                     "workspace_id": ledger.tenant.workspace_id, "cursor": None, "pending_job_id": None,
                     "status": "idle", "attempts": 0, "next_attempt_at": utcnow().isoformat(), "pages_accepted": 0}
            bridge.put(Entity(state_id, "BridgeSyncState", state))
        binding_changed = bool(configured_binding and (
            state.get("authorized_binding_revision") != configured_binding.revision or
            state.get("authorized_environment", "unspecified") != configured_binding.environment))
        if entity and enabled and binding_changed and not binding_reviewed:
            raise ValueError("Explicit review of the changed connector revision and environment is required")
        prior_policy = state.get("require_balanced_journals", False)
        policy = prior_policy if require_balanced_journals is None else require_balanced_journals
        if type(policy) is not bool or policy and mapping["kind"] != "JournalEntry":
            raise ValueError("Journal balance checks require a JournalEntry mapping")
        if policy != prior_policy and state.get("pending_job_id"):
            pending = bridge.get(state["pending_job_id"], "BridgeJob")
            if pending.get("status") != "cancelled":
                raise ValueError("Resolve and checkpoint the pending page before changing its balance policy")
        state["require_balanced_journals"] = policy
        if require_balanced_journals is not None:
            state.update(balance_policy_reviewed_by=actor["employee_id"], balance_policy_reviewed_at=bridge.now())
        if state.get("cursor") is not None and "checkpoint_environment" not in state:
            state["checkpoint_environment"] = state.get("authorized_environment", "unspecified")
        state.update(enabled=enabled, interval_seconds=interval_seconds, authorized_by=actor["employee_id"], updated_at=bridge.now())
        if configured_binding and (not entity or not binding_changed or binding_reviewed):
            state["authorized_binding_revision"] = configured_binding.revision
            state["authorized_environment"] = configured_binding.environment
        bridge.audit(actor, "sync.configure", state_id)
    return public(state_id, state)


def page_csv(page, mapping):
    if not isinstance(page, SyncPage) or not isinstance(page.records, tuple) or len(page.records) > 1000 or type(page.complete) is not bool:
        raise ValueError("Connector returned an invalid bounded SyncPage")
    if page.cursor is not None and (not isinstance(page.cursor, str) or not page.cursor or len(page.cursor) > 2048):
        raise ValueError("Invalid connector cursor")
    if not page.complete and page.cursor is None:
        raise ValueError("Incomplete pages require a next cursor")
    columns = source_columns_profile(mapping.get("source_columns"))
    monetary_sources = {spec["source"] for field, spec in mapping["fields"].items()
                        if field in DECIMAL_FIELDS or spec.get("transform") == "decimal"}
    rows, headers = [], set(columns.values())
    value_bytes = 0
    for record in page.records:
        if (not isinstance(record, SourceRecord) or record.object_type != mapping["object_type"] or
                not isinstance(record.external_id, str) or not record.external_id.strip() or record.external_id != record.external_id.strip() or
                len(record.external_id) > 500 or not isinstance(record.values, dict) or len(record.values) > 100):
            raise ValueError("Invalid connector source record")
        source_timestamp(record.modified_at)
        row = {}
        for key, value in record.values.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 120 or any(ord(char) < 32 for char in key) or not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError("Adapters must flatten values into bounded scalar columns")
            if key in monetary_sources and isinstance(value, (float, bool)):
                raise ValueError("Adapters must preserve monetary values as decimal strings or integers")
            row[key] = "" if value is None else str(value)
            if len(row[key]) > 100000:
                raise ValueError("Source value exceeds staging limit")
        for key, value in ((columns["external_id"], record.external_id), (columns["modified_at"], record.modified_at)):
            if key in row and row[key] != value:
                raise ValueError("Source envelope conflicts with its data columns")
            row[key] = value
        rows.append(row)
        headers.update(row)
        if len(headers) > 100:
            raise ValueError("Source schema exceeds 100 columns")
        # This lower bound stops expansion before buffering every row in a huge
        # vendor page. CSV quoting, delimiters and headers are counted below.
        try:
            value_bytes += sum(len(value.encode("utf-8")) for value in row.values())
        except UnicodeEncodeError:
            raise ValueError("Source values must be valid UTF-8 text") from None
        if value_bytes > 1_000_000:
            raise ValueError("Source page exceeds staging limit")
    if not rows:
        return None
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=sorted(headers))
    writer.writeheader()
    byte_count = 0
    chunks = []
    for row in [None, *rows]:
        if row is not None:
            writer.writerow(row)
        chunk = stream.getvalue()
        try:
            byte_count += len(chunk.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("Source columns and values must be valid UTF-8 text") from None
        if byte_count > 1_000_000:
            raise ValueError("Source page exceeds staging limit")
        chunks.append(chunk)
        stream.seek(0); stream.truncate(0)
    return "".join(chunks)


def _actor(state):
    record = credential_store.get_record(state["authorized_by"])
    if not record or record.get("disabled") or record.get("role") != "ADMIN":
        raise PermissionError("Scheduled collection authorization is no longer valid")
    return {"employee_id": state["authorized_by"], "role": "ADMIN", "bridge_principal": "worker"}


def _check(state):
    bridge.require_durable_state()
    mapping = _mapping(state["mapping_id"])
    if type(state.get("require_balanced_journals", False)) is not bool or state.get("require_balanced_journals") and mapping["kind"] != "JournalEntry":
        raise ValueError("Journal balance collection policy is inconsistent; review configuration")
    system = bridge.get(state["system_id"], "BridgeSystem")
    if system.get("paused"):
        raise ValueError("System is paused")
    connector = runtime.binding(state["system_id"])
    _check_environment_namespace(state["system_id"], connector.environment)
    if state.get("authorized_binding_revision") != connector.revision or state.get("authorized_environment", "unspecified") != connector.environment:
        raise ValueError("Connector revision changed or was not reviewed; explicitly review the current revision and environment")
    if mapping["object_type"] not in connector.objects:
        raise ValueError("Object not authorized for this connector")
    if state.get("mode", "sync") not in connector.capabilities or state.get("mode", "sync") not in {"sync", "history"}:
        raise ValueError("Collection mode is not implemented by this connector")
    return mapping, connector


def _accepted_page(state_id, state, job):
    """Verify durable activation evidence before moving a source checkpoint."""
    from core.bridge_receipts import snapshot_integrity
    if (job.get("sync_state_id") != state_id or job.get("mapping_id") != state["mapping_id"] or
            job.get("system_id") != state["system_id"] or
            snapshot_integrity(job, state["pending_job_id"]) != "consistent"):
        raise ValueError("Pending import requires consistent activation evidence for this source stream")
    if bool((job.get("expectations") or {}).get("balanced_journals")) != state.get("require_balanced_journals", False):
        raise ValueError("Pending page balance policy differs from reviewed collection configuration")
    expected = {"version": 1, "request_cursor_hash": bridge.digest(state.get("cursor")),
                "next_cursor_hash": bridge.digest(state.get("pending_cursor")),
                "complete": state.get("pending_complete")}
    if job.get("collection_page") != expected:
        raise ValueError("Pending checkpoint differs from reviewed page evidence; operator review required")


def run_once(actor, state_id, *, scheduled=False):
    bridge.authorize(actor, human=not scheduled)
    current = utcnow()
    # Claim is durable before any outbound read. No graph lock is held during IO.
    with bridge.mutation(actor, human=not scheduled):
        state = bridge.get(state_id, "BridgeSyncState")
        if scheduled:
            fresh = _actor(state)
            if fresh["employee_id"] != actor["employee_id"] or not state["enabled"]:
                return {"status": "disabled"}
        mapping, connector = _check(state)
        if state.get("pending_job_id"):
            job = bridge.get(state["pending_job_id"], "BridgeJob")
            if job["status"] == "activated":
                _accepted_page(state_id, state, job)
                complete = state.get("pending_complete", False)
                history_complete = state.get("mode", "sync") == "history" and complete
                state.update(cursor=state["pending_cursor"], checkpoint_environment=job.get("collection_environment", "unspecified"), pending_cursor=None, pending_job_id=None, pending_complete=None,
                             pages_accepted=state["pages_accepted"] + 1, last_checkpoint_at=bridge.now(), status="complete" if history_complete else "idle")
                if history_complete:
                    state.update(enabled=False, completed_at=bridge.now())
                state["next_attempt_at"] = (current + timedelta(seconds=state["interval_seconds"] if complete else 0)).isoformat()
                bridge.audit(actor, "sync.checkpoint", state_id)
                return {"status": "checkpointed"}
            if job["status"] == "cancelled":
                state.update(status="blocked", last_error="Pending import was cancelled; explicit retry required", last_error_code="import_cancelled")
                return {"status": "blocked"}
            state["status"] = "awaiting_review"
            return {"status": "awaiting_review", "job_id": state["pending_job_id"]}
        if state.get("lease_until") and timestamp(state["lease_until"]) > current:
            return {"status": "busy"}
        if state["status"] == "blocked":
            return {"status": "blocked"}
        if state["status"] == "complete":
            return {"status": "complete"}
        if timestamp(state["next_attempt_at"]) > current:
            return {"status": "not_due"}
        lease = uuid4().hex
        state.update(status="reading", lease_token=lease, lease_until=(current + timedelta(seconds=LEASE_SECONDS)).isoformat(),
                     binding_revision=connector.revision, last_attempt_at=current.isoformat())
        source_cursor, mapping_hash = state["cursor"], mapping["hash"]
        collection_mode = state.get("mode", "sync")
        mapping_snapshot = deepcopy(mapping)
        balance_policy = state.get("require_balanced_journals", False)
    try:
        read_page = connector.adapter.history if collection_mode == "history" else connector.adapter.sync
        page = read_page(mapping_snapshot["object_type"], source_cursor)
        content = page_csv(page, mapping_snapshot)
        if not page.complete and page.cursor == source_cursor:
            raise ValueError("Connector returned a non-advancing cursor")
        with bridge.mutation(actor):
            state = bridge.get(state_id, "BridgeSyncState")
            if state.get("lease_token") != lease or timestamp(state["lease_until"]) <= utcnow():
                return {"status": "lease_lost"}
            if scheduled:
                fresh = _actor(state)
                if fresh["employee_id"] != actor["employee_id"] or not state["enabled"]:
                    raise ValueError("Collection was disabled while a read was in progress")
            mapping, current_connector = _check(state)
            if (current_connector is not connector or mapping["hash"] != mapping_hash or
                    state.get("require_balanced_journals", False) != balance_policy):
                raise ValueError("Connector or mapping changed while collecting")
            if content is None:
                history_complete = collection_mode == "history" and page.complete
                state.update(cursor=page.cursor, checkpoint_environment=connector.environment, status="complete" if history_complete else "idle", last_success_at=bridge.now(),
                             next_attempt_at=(utcnow() + timedelta(seconds=state["interval_seconds"] if page.complete else 0)).isoformat())
                if history_complete:
                    state.update(enabled=False, completed_at=bridge.now())
                bridge.audit(actor, "sync.empty_page", state_id)
            else:
                job_id = bridge._stage_import(actor, state["mapping_id"], content, {"balanced_journals": True} if balance_policy else None)["id"]
                job = bridge.get(job_id, "BridgeJob")
                job.update(transport="connector_read", sync_state_id=state_id, binding_revision=connector.revision, collection_mode=collection_mode, collection_environment=connector.environment,
                           collection_page={"version": 1, "request_cursor_hash": bridge.digest(source_cursor),
                                            "next_cursor_hash": bridge.digest(page.cursor), "complete": page.complete})
                state.update(pending_job_id=job_id, pending_cursor=page.cursor, pending_complete=page.complete,
                             status="awaiting_review", last_success_at=bridge.now())
                bridge.audit(actor, "sync.stage", state_id)
            state.update(attempts=0, last_error=None, last_error_code=None, retry_after_seconds=None, lease_token=None, lease_until=None)
            return {"status": state["status"], "job_id": state.get("pending_job_id")}
    except Exception as exc:
        # A failed final save rolled graph changes back; the durable lease remains.
        # A subsequent persisted failure clears it for a safe read-only retry.
        with bridge.mutation(actor):
            state = bridge.get(state_id, "BridgeSyncState")
            if state.get("lease_token") != lease or timestamp(state["lease_until"]) <= utcnow():
                return {"status": "lease_lost"}
            attempts = state["attempts"] + 1
            retryable = isinstance(exc, (TimeoutError, ConnectionError)) or isinstance(exc, ConnectorFailure) and exc.retryable
            blocked = not retryable or attempts >= MAX_ATTEMPTS
            code = exc.code if isinstance(exc, ConnectorFailure) else "authentication_required" if isinstance(exc, CredentialUnavailable) else "timeout" if isinstance(exc, TimeoutError) else "connection_error" if isinstance(exc, ConnectionError) else "contract_review"
            messages = {"unavailable": "Connector temporarily unavailable", "rate_limited": "Source rate limit reached",
                        "authentication_required": "Source access needs renewal by the connector operator",
                        "permission_denied": "Source permissions require operator review", "source_changed": "Source schema or account scope changed; review the connector",
                        "timeout": "Source read timed out", "connection_error": "Source connection temporarily unavailable",
                        "contract_review": "Connector contract/authorization requires review"}
            requested_delay = exc.retry_after_seconds if isinstance(exc, ConnectorFailure) else None
            delay = max(min(3600, 60 * 2 ** min(attempts - 1, 6)), requested_delay or 0)
            state.update(attempts=attempts, status="blocked" if blocked else "retrying", lease_token=None, lease_until=None,
                         last_error=messages[code], last_error_code=code, retry_after_seconds=requested_delay,
                         next_attempt_at=(utcnow() + timedelta(seconds=delay)).isoformat())
            bridge.audit(actor, "sync.blocked" if blocked else "sync.retry", state_id)
        return {"status": state["status"]}


def retry(actor, state_id, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        state = bridge.get(state_id, "BridgeSyncState")
        _check(state)
        if state.get("status") == "complete":
            raise ValueError("Completed history requires a separate reviewed replay plan")
        if state.get("lease_until") and timestamp(state["lease_until"]) > utcnow():
            raise ValueError("A read is still in progress")
        if state.get("pending_job_id"):
            job = bridge.get(state["pending_job_id"], "BridgeJob")
            if job["status"] != "cancelled":
                raise ValueError("Review or cancel the pending job before retrying")
        state.update(status="idle", attempts=0, pending_job_id=None, pending_cursor=None, lease_token=None,
                     lease_until=None, next_attempt_at=utcnow().isoformat(), last_error=None, last_error_code=None,
                     retry_after_seconds=None, retry_reason=reason)
        bridge.audit(actor, "sync.retry_requested", state_id)
    return public(state_id, state)


def _transition_plan(state_id, mapping_id):
    state = bridge.get(state_id, "BridgeSyncState")
    old = bridge.get(state["mapping_id"], "BridgeMapping")
    replacement = _mapping(mapping_id)
    if mapping_id == state["mapping_id"] or any(old[key] != replacement[key] for key in ("system_id", "object_type", "kind")):
        raise ValueError("Replacement must be a different approved mapping for the same system, object and canonical type")
    connector = runtime.binding(state["system_id"])
    _check_environment_namespace(state["system_id"], connector.environment)
    if state["object_type"] not in connector.objects:
        raise ValueError("Source object is not authorized for this connector")
    if state.get("mode", "sync") not in connector.capabilities:
        raise ValueError("Collection mode is not implemented by this connector")
    if state.get("lease_until") and timestamp(state["lease_until"]) > utcnow():
        raise ValueError("Wait for the in-progress read before replacing its mapping")
    pending = bridge.get(state["pending_job_id"], "BridgeJob") if state.get("pending_job_id") else None
    if pending and (pending.get("sync_state_id") != state_id or pending["mapping_id"] != state["mapping_id"]):
        raise ValueError("Pending import does not belong to this source stream")
    if pending and pending["status"] not in {"activated", "cancelled"}:
        raise ValueError("Activate or cancel the pending import before replacing its mapping")
    if pending and pending["status"] == "activated":
        _accepted_page(state_id, state, pending)
    token = bridge.digest([state_id, state, mapping_id, replacement["hash"], connector.revision, connector.environment])
    return state, replacement, connector, pending, token


def transition_preview(actor, state_id, mapping_id):
    bridge.authorize(actor)
    with bridge.LOCK:
        state, replacement, connector, pending, token = _transition_plan(state_id, mapping_id)
        return {"state_id": state_id, "from_mapping_id": state["mapping_id"], "to_mapping_id": mapping_id,
            "kind": replacement["kind"], "object_type": replacement["object_type"],
            "binding_revision": connector.revision, "binding_environment": connector.environment, "review_token": token,
            "checkpoint_action": "accept_activated_page" if pending and pending["status"] == "activated" else "preserve_saved_position",
            "status_after_transition": "complete" if _history_complete(state, pending) else "idle",
            "pending_job_id": state.get("pending_job_id"), "schedule_after_transition": "disabled"}


def _history_complete(state, pending):
    return state.get("mode", "sync") == "history" and (state.get("status") == "complete" or
        bool(pending and pending["status"] == "activated" and state.get("pending_complete")))


def transition_mapping(actor, state_id, mapping_id, review_token, reason):
    reason = bridge.review_reason(reason)
    with bridge.mutation(actor, True):
        state, replacement, connector, pending, token = _transition_plan(state_id, mapping_id)
        if token != review_token:
            raise ValueError("Source stream or mapping changed; review the transition again")
        history_complete = _history_complete(state, pending)
        prior_mapping = state["mapping_id"]
        if pending and pending["status"] == "activated":
            state.update(cursor=state["pending_cursor"], checkpoint_environment=pending.get("collection_environment", "unspecified"), pages_accepted=state["pages_accepted"] + 1,
                         last_checkpoint_at=bridge.now())
        transition_id = bridge.add("BridgeSyncMappingTransition", {"state_id": state_id,
            "from_mapping_id": prior_mapping, "to_mapping_id": mapping_id, "mapping_hash": replacement["hash"],
            "pending_job_id": state.get("pending_job_id"), "checkpoint_hash": bridge.digest(state.get("cursor")),
            "review_token": review_token, "reason": reason, "reviewed_by": actor["employee_id"], "reviewed_at": bridge.now()})
        state.update(mapping_id=mapping_id, enabled=False, authorized_by=actor["employee_id"],
            authorized_binding_revision=connector.revision, authorized_environment=connector.environment, status="complete" if history_complete else "idle", attempts=0,
            pending_job_id=None, pending_cursor=None, pending_complete=None, lease_token=None, lease_until=None,
            last_error=None, last_error_code=None, retry_after_seconds=None,
            completed_at=(state.get("completed_at") or bridge.now()) if history_complete else None,
            next_attempt_at=utcnow().isoformat(), updated_at=bridge.now())
        bridge.audit(actor, "sync.mapping_transition", transition_id)
    return public(state_id, state)


def tick():
    with bridge.LOCK:
        candidates = [(e.id, deepcopy(e.attributes)) for e in ledger.get_all().values()
                      if e.entity_type == "BridgeSyncState" and e.attributes.get("workspace_id") == ledger.tenant.workspace_id and e.attributes.get("enabled")]
    results = []
    for state_id, state in sorted(candidates, key=lambda item: item[1].get("last_attempt_at", "")):
        if state["status"] == "blocked" or timestamp(state["next_attempt_at"]) > utcnow():
            continue
        if state.get("lease_until") and timestamp(state["lease_until"]) > utcnow():
            continue
        if state.get("pending_job_id"):
            pending = ledger.get_entity(state["pending_job_id"])
            if pending and pending.attributes.get("status") not in {"activated", "cancelled"}:
                continue
        if len(results) >= 10:
            break
        try:
            actor = _actor(state)
            _check(state)
            results.append(run_once(actor, state_id, scheduled=True))
        except (PermissionError, ValueError):
            # No stale actor fallback and no raw connector data in logs.
            continue
    return results


async def loop():
    while True:
        await asyncio.sleep(60)
        try:
            await run_worker_io(tick)
        except Exception:
            log.error("Bridge collector tick failed; review durable sync state")


def start():
    global _TASK
    if _TASK is None:
        _TASK = asyncio.get_running_loop().create_task(loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _TASK
    task = _TASK
    if task is not None:
        task.cancel()
        # Retain ownership during thread drain so a repeated start cannot overlap.
        def release(completed):
            global _TASK
            if _TASK is completed:
                _TASK = None
        if task.done():
            release(task)
        else:
            task.add_done_callback(release)
    return task
