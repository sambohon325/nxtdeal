"""Exercise real JSON persistence, not just in-memory worker state."""
from datetime import timedelta
import pytest
from core import dealer_bridge as b, bridge_runtime as runtime, bridge_sync as sync, bridge_chrono as outbox
from core.dealeros import ledger
from core.storage import save_graph, load_graph
from tests.test_bridge_sync import configured, state_of, FakeConnector, A, B, isolated  # noqa: F401
from tests.test_bridge_chrono import enabled, FakeSink
from tests.test_bridge_history_collection import history_configured, activate_page
from core import bridge_health as health
from tests.test_bridge_health import source as health_source


@pytest.fixture(autouse=True)
def disk_graph(tmp_path, monkeypatch, isolated):
    path = str(tmp_path / "bridge-restart.json")
    monkeypatch.setattr(b, "GRAPH_PATH", path)
    monkeypatch.setattr(b, "save_graph", save_graph)
    previous_sink = outbox._BINDING
    yield path
    outbox._BINDING = previous_sink


def restart(path):
    ledger.reset()
    load_graph(path)


def test_failed_snapshot_flush_rolls_back_bridge_change_and_survives_restart(disk_graph, monkeypatch):
    from core import json_graph_repository as storage
    system = b.connect(A, "CSV", "Flush recovery source")["id"]
    before = dict(b.get(system, "BridgeSystem"))
    real_fsync = storage.os.fsync

    def fail_flush(descriptor):
        raise OSError("Synthetic storage flush failure")

    monkeypatch.setattr(storage.os, "fsync", fail_flush)
    with pytest.raises(OSError, match="flush failure"):
        b.set_system_paused(B, system, True, "Review interrupted persistence")
    assert b.get(system, "BridgeSystem") == before
    restart(disk_graph)
    assert b.get(system, "BridgeSystem") == before
    monkeypatch.setattr(storage.os, "fsync", real_fsync)
    b.set_system_paused(B, system, True, "Retry after storage recovery")
    restart(disk_graph)
    assert b.get(system, "BridgeSystem")["paused"] is True


def test_pending_page_and_review_checkpoint_survive_graph_reload(disk_graph):
    system, mapping, state, first = configured()
    job = sync.run_once(A, state)["job_id"]
    runtime.unbind(system)
    restart(disk_graph)
    assert state_of(state)["pending_job_id"] == job and state_of(state)["cursor"] is None
    with pytest.raises(ValueError, match="No authorized"): sync.run_once(A, state)
    replacement = FakeConnector()
    runtime.bind(system, replacement, revision="test-1", objects=["customers"])
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    assert replacement.calls == []
    b.validate(A, job); b.activate(B, job)
    restart(disk_graph)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    restart(disk_graph)
    assert state_of(state)["cursor"] == "cursor-1" and state_of(state)["pages_accepted"] == 1
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 1


def test_acknowledgments_survive_reload_without_redelivery(disk_graph):
    events, sink = enabled()
    assert outbox.deliver_once(A)["delivered"] == len(events)
    outbox.unbind_sink()
    restart(disk_graph)
    assert outbox.status(A)["effective_status"] == "review_required"
    replacement = FakeSink()
    outbox.bind_sink("test-sink", "v1", replacement)
    assert outbox.deliver_once(A)["status"] == "idle" and replacement.calls == []
    assert outbox.status(A)["counts"] == {"delivered": len(events)}


def test_unacknowledged_durable_claim_recovers_same_ids_after_restart(disk_graph, monkeypatch):
    events, sink = enabled()
    saves = []
    def fail_ack(path):
        saves.append(path)
        if len(saves) == 2:
            raise OSError("Synthetic crash after remote acceptance")
        save_graph(path)
    monkeypatch.setattr(b, "save_graph", fail_ack)
    with pytest.raises(OSError): outbox.deliver_once(A)
    assert sink.accepted == set(events)
    restart(disk_graph)
    assert {record["status"] for record in outbox.receipts(A)} == {"in_flight"}
    later = outbox.utcnow() + timedelta(minutes=10)
    monkeypatch.setattr(outbox, "utcnow", lambda: later)
    assert outbox.deliver_once(A)["delivered"] == len(events)
    assert sink.accepted == set(events)
    restart(disk_graph)
    assert outbox.status(A)["counts"] == {"delivered": len(events)}


def test_completed_history_remains_complete_after_disk_reload(disk_graph):
    system, _, live, history, adapter = history_configured()
    activate_page(live)
    activate_page(history)
    activate_page(history)
    assert state_of(history)["status"] == "complete"
    original_calls = list(adapter.calls)
    restart(disk_graph)
    assert state_of(history)["mode"] == "history" and not state_of(history)["enabled"]
    assert state_of(history)["cursor"] == "history-end"
    assert state_of(live)["cursor"] == "live-1"
    assert sync.run_once(A, history)["status"] == "complete"
    assert adapter.calls == original_calls


def test_health_check_recovers_after_result_save_failure_and_reload(disk_graph, monkeypatch):
    system, adapter = health_source()
    saves = []
    def fail_result(path):
        saves.append(path)
        if len(saves) == 2:
            raise OSError("Synthetic health result save failure")
        save_graph(path)
    monkeypatch.setattr(b, "save_graph", fail_result)
    with pytest.raises(OSError): health.check(A, system)
    restart(disk_graph)
    assert "connector_health" not in ledger.get_entity(system).attributes
    assert health.check(A, system)["status"] == "checking"
    later = health.utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(health, "utcnow", lambda: later)
    assert health.check(A, system)["status"] == "ready"
    restart(disk_graph)
    saved = b.system_map(A)["systems"][0]["connector_health"]
    assert saved["status"] == "ready" and saved["current_binding"]


def test_event_profile_review_activation_and_replay_survive_disk_reload(disk_graph):
    from core import bridge_event_imports as imports, bridge_event_profiles as profiles
    from tests.test_bridge_event_identity import candidate, decide
    from tests.test_bridge_adf_discovery import ADF
    job, row = candidate()
    decision = decide(job, row)
    profile_id = b.get(job, "BridgeEventJob")["profile_id"]
    system_id = b.get(job, "BridgeEventJob")["system_id"]
    restart(disk_graph)
    assert profiles.list_profiles(A, system_id)[0]["status"] == "approved"
    assert imports.validate(A, job)["rows"][0]["identity_review_id"] == decision["id"]
    result = imports.activate(B, job)
    assert result["created"] == 0 and result["observations"] == 1
    restart(disk_graph)
    assert imports.report(A, job)["receipt_integrity"] == "consistent"
    history = imports.lineage(A, system_id, "Provider", "private-id")
    assert history["observation"]["identity_resolution"] == "human_link"
    assert history["current_values"]["first_name"] == "Dealership name"
    replay = imports.stage(A, profile_id, ADF)["id"]
    assert imports.validate(A, replay)["rows"][0]["status"] == "duplicate"
    assert imports.activate(B, replay)["observations"] == 0
    restart(disk_graph)
    assert len(b.chrono_observations(A)) == 1


def test_revoked_event_profile_and_cancelled_batch_stay_closed_after_reload(disk_graph):
    from core import bridge_event_imports as imports, bridge_event_profiles as profiles
    from tests.test_bridge_event_imports import staged
    _, profile, job = staged()
    imports.cancel(B, job, "Cancelled before import review")
    profiles.revoke(B, profile, "Source evidence needs correction")
    restart(disk_graph)
    assert imports.report(A, job)["status"] == "cancelled"
    with pytest.raises(ValueError): imports.validate(A, job)
    with pytest.raises(ValueError): imports.activate(B, job)



def test_export_file_checkpoint_survives_new_adapter_and_payload_cleanup(disk_graph, tmp_path, monkeypatch):
    from core.bridge_adapters.export_file import ExportFileConnector
    from core import bridge_retention as retention
    system, mapping, state, _ = configured()
    path = tmp_path / "snapshot.csv"
    path.write_bytes(b"external_id,modified_at,name,email\n1,2026-01-01T00:00:00Z,Ada,ada@example.com\n")
    runtime.bind(system, ExportFileConnector(path, object_type="customers"), revision="file-1", objects=["customers"])
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="file-1", reviewed_binding_environment="unspecified")
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    review = retention.preview(A, job)
    retention.cleanup(B, job, review["review_token"], "Synthetic terminal payload retention review")
    runtime.unbind(system)
    restart(disk_graph)
    runtime.bind(system, ExportFileConnector(path, object_type="customers"), revision="file-1", objects=["customers"])
    assert sync.run_once(A, state)["status"] == "checkpointed"
    restart(disk_graph)
    later = sync.utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(sync, "utcnow", lambda: later)
    assert sync.run_once(A, state)["status"] == "idle"
    assert state_of(state)["pages_accepted"] == 1
    assert b.import_report(A, job)["receipt_integrity"] == "consistent"
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 1


def test_grouped_journal_collection_policy_and_checkpoint_survive_restarts(disk_graph, tmp_path):
    from core.bridge_adapters.export_file_paged import PagedExportFileConnector
    from tests.test_bridge_accounting import CSV, configured as journal_mapping
    from core.entity_types import GL_ENTRY, BANK_TRANSACTION
    mapping = journal_mapping()
    system = b.get(mapping, "BridgeMapping")["system_id"]
    second = CSV.split("\n", 1)[1].replace("line-", "other-").replace("journal-1", "journal-2")
    path = tmp_path / "grouped-journals.csv"
    path.write_text(CSV + second, encoding="utf-8", newline="")
    def bind_reader():
        runtime.bind(system, PagedExportFileConnector(path, object_type="journal_lines", page_size=4,
            group_by_source_column="journal_id"), revision="grouped-journals-1", objects=["journal_lines"], environment="synthetic")
    bind_reader()
    state = sync.configure(A, mapping, True, 60, require_balanced_journals=True)["id"]
    prior_cursor, jobs = None, []
    for expected_pages in (1, 2):
        job = sync.run_once(A, state)["job_id"]
        jobs.append(job)
        runtime.unbind(system)
        restart(disk_graph)
        assert state_of(state)["require_balanced_journals"] is True
        assert state_of(state)["cursor"] == prior_cursor
        bind_reader()
        assert sync.run_once(A, state)["status"] == "awaiting_review"
        b.validate(A, job)
        report = b.import_report(A, job)
        assert report["reconciliation"]["status"] == "matched"
        b.activate(B, job)
        restart(disk_graph)
        assert sync.run_once(B, state)["status"] == "checkpointed"
        prior_cursor = state_of(state)["cursor"]
        restart(disk_graph)
        assert state_of(state)["pages_accepted"] == expected_pages
        receipt = b.import_report(A, job)
        assert receipt["receipt_integrity"] == "consistent"
        assert receipt["activation_receipt"]["expectations"]["balanced_journals"] is True
    assert len(set(jobs)) == 2
    assert prior_cursor.endswith(":6:done")
    assert len([e for e in ledger.get_all().values() if e.entity_type == "JournalEntry"]) == 6
    assert not any(e.entity_type in {GL_ENTRY, BANK_TRANSACTION} for e in ledger.get_all().values())
