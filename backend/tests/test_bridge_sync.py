from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from core import dealer_bridge as b, bridge_sync as sync, bridge_runtime as runtime
from core.bridge_contracts import SourceRecord, SyncPage
from core.dealeros import ledger

A = {"employee_id": "admin-a", "role": "ADMIN", "bridge_principal": "session"}
B = {"employee_id": "admin-b", "role": "ADMIN", "bridge_principal": "session"}
API = {**A, "bridge_principal": "api"}


class FakeConnector:
    capabilities = frozenset({"sync"})
    def __init__(self):
        self.calls = []
        self.page = SyncPage((SourceRecord("customers", "1", "2026-01-01T00:00:00Z", {"name": "Ada", "email": "ada@example.com"}),), "cursor-1", False)
        self.failure = None
        self.during_read = None
    def sync(self, object_type, cursor):
        self.calls.append((object_type, cursor))
        if self.during_read:
            self.during_read()
        if self.failure:
            raise self.failure
        return self.page


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    previous = ledger.entities, ledger.relationships, dict(runtime._BINDINGS)
    ledger.entities, ledger.relationships = {}, []
    runtime._BINDINGS.clear()
    monkeypatch.setattr(b, "save_graph", lambda path: None)
    monkeypatch.setattr(sync.credential_store, "get_record", lambda employee: {"role": "ADMIN"})
    yield
    ledger.entities, ledger.relationships = previous[:2]
    runtime._BINDINGS.clear(); runtime._BINDINGS.update(previous[2])


def configured(enabled=True):
    system = b.connect(A, "Frazer", "Main store")["id"]
    mapping = b.propose_mapping(A, system, "Customer", "customers", {
        "first_name": {"source": "name", "transform": "text"}, "email": {"source": "email", "transform": "lower"}})["id"]
    b.approve_mapping(B, mapping)
    connector = FakeConnector()
    runtime.bind(system, connector, revision="test-1", objects=["customers"])
    state = sync.configure(A, mapping, enabled, 60)["id"]
    return system, mapping, state, connector


def state_of(state_id):
    return b.get(state_id, "BridgeSyncState")


def test_collection_stages_only_then_checkpoints_after_human_activation():
    _, _, state, connector = configured()
    result = sync.run_once(A, state)
    assert result["status"] == "awaiting_review" and state_of(state)["cursor"] is None
    assert not any(e.entity_type == "Customer" for e in ledger.get_all().values())
    assert sync.run_once(A, state)["status"] == "awaiting_review" and len(connector.calls) == 1
    job = result["job_id"]
    b.validate(A, job)
    with pytest.raises(PermissionError): b.activate(API, job)
    b.activate(B, job)
    assert sync.run_once(A, state)["status"] == "checkpointed"
    assert state_of(state)["cursor"] == "cursor-1"
    connector.page = SyncPage((), "cursor-2", True)
    assert sync.run_once(A, state)["status"] == "idle"
    assert connector.calls[-1][1] == "cursor-1"


def test_cancelled_job_never_advances_checkpoint():
    _, _, state, connector = configured()
    job = sync.run_once(A, state)["job_id"]
    b.cancel_import(B, job, "Source extract was incorrect")
    assert sync.run_once(A, state)["status"] == "blocked" and state_of(state)["cursor"] is None
    sync.retry(B, state, "Source corrected for retry")
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    assert connector.calls == [("customers", None), ("customers", None)]


def test_retryable_failures_back_off_without_exposing_vendor_response(monkeypatch):
    _, _, state, connector = configured()
    connector.failure = TimeoutError("secret-token and customer PII")
    assert sync.run_once(A, state)["status"] == "retrying"
    assert "secret" not in str(sync.states(A)) and state_of(state)["attempts"] == 1
    assert sync.run_once(A, state)["status"] == "not_due"
    future = sync.utcnow() + timedelta(hours=5)
    for number in range(2, 6):
        monkeypatch.setattr(sync, "utcnow", lambda: future)
        result = sync.run_once(A, state)
        assert state_of(state)["attempts"] == number
        future += timedelta(hours=5)
    assert result["status"] == "blocked"


def test_bad_contract_blocks_and_keeps_cursor():
    _, _, state, connector = configured()
    connector.page = SyncPage((), None, False)
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["cursor"] is None


def test_pause_or_revocation_during_read_drops_result():
    system, _, state, connector = configured()
    connector.during_read = lambda: b.set_system_paused(B, system, True, "Stop source while reviewing")
    assert sync.run_once(A, state)["status"] == "blocked"
    assert not any(e.entity_type == "BridgeJob" for e in ledger.get_all().values())


def test_runtime_rebinding_during_read_drops_old_result():
    system, _, state, connector = configured()
    connector.during_read = lambda: runtime.bind(system, FakeConnector(), revision="test-2", objects=["customers"])
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["pending_job_id"] is None


def test_disabled_or_revoked_operator_never_collects(monkeypatch):
    _, _, state, connector = configured(False)
    assert sync.tick() == [] and connector.calls == []
    state_of(state)["enabled"] = True
    monkeypatch.setattr(sync.credential_store, "get_record", lambda employee: {"role": "SALES"})
    assert sync.tick() == [] and connector.calls == []


def test_lease_prevents_duplicate_concurrent_read():
    _, _, state, connector = configured()
    attempts = []
    connector.during_read = lambda: attempts.append(sync.run_once(B, state))
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    assert attempts == [{"status": "busy"}] and len(connector.calls) == 1


def test_expired_lease_recovery_and_stale_reader_fencing():
    _, _, state, connector = configured()
    state_of(state).update(status="reading", lease_token="crashed-process", lease_until="2020-01-01T00:00:00Z")
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    assert state_of(state)["lease_token"] is None


def test_save_failure_does_not_leave_orphan_staged_job(monkeypatch):
    _, _, state, connector = configured()
    calls = []
    def save(path):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk failure during final commit")
    monkeypatch.setattr(b, "save_graph", save)
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["cursor"] is None and state_of(state)["pending_job_id"] is None
    assert not any(e.entity_type == "BridgeJob" for e in ledger.get_all().values())


def test_binding_scopes_and_actor_controls():
    system, mapping, state, connector = configured()
    with pytest.raises(PermissionError): sync.configure(API, mapping, True, 60)
    with pytest.raises(PermissionError): sync.run_once(API, state)
    another = b.connect(A, "Frazer", "Second store source")["id"]
    with pytest.raises(ValueError): runtime.bind(another, connector, revision="test-1", objects=["customers"])
    runtime.unbind(system)
    with pytest.raises(ValueError): sync.run_once(A, state)
    assert runtime.describe(system)["status"] == "unavailable"


def test_source_page_contract_does_not_accept_nested_vendor_values():
    _, mapping, _, connector = configured()
    connector.page = SyncPage((SourceRecord("customers", "1", "2026-01-01T00:00:00Z", {"name": {"raw": "nested"}}),), "next", True)
    with pytest.raises(ValueError): sync.page_csv(connector.page, b.get(mapping, "BridgeMapping"))


def test_public_state_excludes_opaque_source_cursors():
    _, _, state, _ = configured()
    sync.run_once(A, state)
    public = sync.states(A)[0]
    assert "pending_cursor" not in public and "cursor" not in public and "lease_token" not in public


def test_new_adapter_revision_requires_human_configuration_review():
    system, mapping, state, original = configured()
    replacement = FakeConnector()
    runtime.bind(system, replacement, revision="test-2", objects=["customers"])
    with pytest.raises(ValueError, match="revision changed"):
        sync.run_once(A, state)
    assert not original.calls and not replacement.calls
    sync.configure(B, mapping, True, 60, reviewed_binding_revision="test-2", reviewed_binding_environment="unspecified")
    assert sync.run_once(B, state)["status"] == "awaiting_review"


def test_missing_initial_binding_requires_review_after_installation():
    system, mapping, state, original = configured(False)
    state_of(state).pop("authorized_binding_revision")
    with pytest.raises(ValueError, match="not reviewed"): sync.run_once(A, state)
    sync.configure(A, mapping, False, 60, reviewed_binding_revision="test-1", reviewed_binding_environment="unspecified")
    assert sync.run_once(A, state)["status"] == "awaiting_review"


def test_demo_without_durable_storage_never_reads_live_connector(monkeypatch):
    _, mapping, state, connector = configured()
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    with pytest.raises(ValueError, match="Durable storage"): sync.run_once(A, state)
    with pytest.raises(ValueError, match="Durable storage"): sync.configure(A, mapping, True, 60)
    assert sync.states(A)[0]["availability"]["status"] == "review_required"
    assert connector.calls == []
    assert sync.configure(A, mapping, False, 60)["enabled"] is False


@pytest.mark.parametrize("activated", [True, False])
def test_terminal_payload_cleanup_preserves_sync_checkpoint_decision(activated):
    from core import bridge_retention
    _, _, state, connector = configured()
    job = sync.run_once(A, state)["job_id"]
    if activated:
        b.validate(A, job)
        b.activate(B, job)
    else:
        b.cancel_import(B, job, "Reject synthetic source batch")
    review = bridge_retention.preview(A, job)
    bridge_retention.cleanup(B, job, review["review_token"], "Remove reviewed synthetic staging copy")
    assert b.get(job, "BridgeJob")["rows"] == []
    result = sync.run_once(A, state)
    assert result["status"] == ("checkpointed" if activated else "blocked")
    assert state_of(state)["cursor"] == ("cursor-1" if activated else None)
    assert len(connector.calls) == 1


def test_local_export_snapshot_obeys_human_checkpoint(tmp_path, monkeypatch):
    from core.bridge_adapters.export_file import ExportFileConnector
    system, mapping, state, _ = configured()
    path = tmp_path / "authorized.csv"
    path.write_bytes(b"external_id,modified_at,name,email\n1,2026-01-01T00:00:00Z,Ada,ada@example.com\n")
    reader = ExportFileConnector(path, object_type="customers")
    runtime.bind(system, reader, revision="export-profile-1", objects=["customers"])
    # Updating an operator binding requires explicit sync reconfiguration.
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="export-profile-1", reviewed_binding_environment="unspecified")
    result = sync.run_once(A, state)
    assert result["status"] == "awaiting_review"
    fingerprint = reader.sync("customers").cursor
    assert state_of(state)["cursor"] is None
    job = result["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    assert sync.run_once(A, state)["status"] == "checkpointed"
    assert state_of(state)["cursor"] == fingerprint
    future = sync.utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(sync, "utcnow", lambda: future)
    assert sync.run_once(A, state)["status"] == "idle"
    assert len([entity for entity in ledger.get_all().values() if entity.entity_type == "Customer"]) == 1


@pytest.mark.parametrize("change", ["pending_cursor", "cursor", "pending_complete", "receipt", "collection_page"])
def test_checkpoint_requires_exact_activated_page_evidence(change):
    _, _, state, _ = configured()
    job_id = sync.run_once(A, state)["job_id"]
    b.validate(A, job_id)
    b.activate(B, job_id)
    job = b.get(job_id, "BridgeJob")
    if change == "receipt":
        job["activation_receipt"]["checksum"] = "changed"
    elif change == "collection_page":
        job["collection_page"]["next_cursor_hash"] = "changed"
    elif change == "pending_complete":
        state_of(state)[change] = True
    else:
        state_of(state)[change] = "unexpected-position"
    before = deepcopy(state_of(state))
    with pytest.raises(ValueError, match="evidence"):
        sync.run_once(A, state)
    assert state_of(state) == before


def test_page_receipt_contains_hashes_not_raw_cursor_tokens():
    _, _, state, connector = configured()
    connector.page = SyncPage(connector.page.records, "secret-vendor-cursor-token", False)
    job_id = sync.run_once(A, state)["job_id"]
    b.validate(A, job_id)
    b.activate(B, job_id)
    report = b.import_report(A, job_id)
    assert "secret-vendor-cursor-token" not in str(report)
    assert report["collection_page"] == report["activation_receipt"]["collection_page"]
    assert report["collection_page"]["next_cursor_hash"] == b.digest("secret-vendor-cursor-token")
    assert sync.run_once(A, state)["status"] == "checkpointed"
