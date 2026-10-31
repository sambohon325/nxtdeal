"""Historical backfill has its own cursor and never activates or rewinds sync."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as b, bridge_sync as sync, bridge_runtime as runtime
from core.bridge_contracts import SourceRecord, SyncPage
from core.dealeros import ledger
from api.routers.dealer_bridge import router, admin
from tests.test_bridge_sync import A, B, API, configured, state_of, isolated  # noqa: F401


class HistoricalConnector:
    capabilities = frozenset({"sync", "history"})
    def __init__(self):
        self.calls = []
    def sync(self, object_type, cursor):
        self.calls.append(("sync", cursor))
        return SyncPage((SourceRecord(object_type, "1", "2026-03-01T00:00:00Z", {"name": "Current", "email": "ada@example.com"}),), "live-1", True)
    def history(self, object_type, cursor):
        self.calls.append(("history", cursor))
        if cursor is None:
            return SyncPage((SourceRecord(object_type, "1", "2026-01-01T00:00:00Z", {"name": "Oldest", "email": "ada@example.com"}),), "history-1", False)
        return SyncPage((SourceRecord(object_type, "1", "2026-02-01T00:00:00Z", {"name": "Earlier", "email": "ada@example.com"}),), "history-end", True)


def history_configured():
    system, mapping, live, _ = configured(False)
    adapter = HistoricalConnector()
    runtime.bind(system, adapter, revision="history-v1", objects=["customers"])
    sync.configure(A, mapping, False, 60, reviewed_binding_revision="history-v1", reviewed_binding_environment="unspecified")
    history = sync.configure(A, mapping, True, 60, "history")["id"]
    return system, mapping, live, history, adapter


def activate_page(state):
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job); b.activate(B, job)
    assert sync.run_once(A, state)["status"] == "checkpointed"
    return job


def test_history_and_sync_are_independent_streams_with_shared_record_identity():
    _, _, live, history, adapter = history_configured()
    assert live != history
    activate_page(live)
    first = sync.run_once(A, history)
    assert first["status"] == "awaiting_review"
    assert state_of(history)["cursor"] is None
    job = first["job_id"]
    assert b.get(job, "BridgeJob")["collection_mode"] == "history"
    assert b.validate(A, job)[0]["status"] == "history"
    b.activate(B, job)
    sync.run_once(A, history)
    assert state_of(history)["cursor"] == "history-1"
    activate_page(history)
    assert state_of(history)["status"] == "complete" and not state_of(history)["enabled"]
    assert state_of(history)["cursor"] == "history-end"
    assert state_of(live)["cursor"] == "live-1"
    assert state_of(live)["status"] == "idle"
    customers = [entity for entity in ledger.get_all().values() if entity.entity_type == "Customer"]
    assert len(customers) == 1 and customers[0].attributes["first_name"] == "Current"
    assert len(b.chrono_observations(A)) == 3
    assert adapter.calls == [("sync", None), ("history", None), ("history", "history-1")]
    assert sync.run_once(A, history)["status"] == "complete"
    assert len(adapter.calls) == 3


def test_terminal_history_page_waits_for_human_review_before_completion():
    _, _, _, history, adapter = history_configured()
    adapter.history = lambda object_type, cursor: adapter.sync(object_type, cursor)
    job = sync.run_once(A, history)["job_id"]
    assert state_of(history)["enabled"] and state_of(history)["status"] == "awaiting_review"
    b.validate(A, job)
    with pytest.raises(PermissionError):
        b.activate(API, job)
    assert sync.run_once(A, history)["status"] == "awaiting_review"
    b.activate(B, job)
    sync.run_once(A, history)
    assert state_of(history)["status"] == "complete" and not state_of(history)["enabled"]


def test_empty_completed_history_stops_without_creating_imports():
    _, mapping, _, history, adapter = history_configured()
    adapter.history = lambda *_: SyncPage((), "end", True)
    assert sync.run_once(A, history)["status"] == "complete"
    assert not state_of(history)["enabled"]
    assert not any(entity.entity_type == "BridgeJob" for entity in ledger.get_all().values())
    with pytest.raises(ValueError, match="replay plan"):
        sync.configure(A, mapping, True, 60, "history")
    with pytest.raises(ValueError, match="replay plan"):
        sync.retry(B, history, "Try to restart already completed historical collection")


def test_cancelled_history_page_never_completes_or_advances():
    _, _, _, history, _ = history_configured()
    job = sync.run_once(A, history)["job_id"]
    b.cancel_import(B, job, "Incorrect source backfill page")
    assert sync.run_once(A, history)["status"] == "blocked"
    assert state_of(history)["cursor"] is None
    sync.retry(B, history, "Source corrected for reviewed historical retry")
    assert state_of(history)["mode"] == "history"


def test_history_requires_declared_implemented_capability():
    _, mapping, _, _ = configured(False)
    with pytest.raises(ValueError, match="not authorized"):
        sync.configure(A, mapping, True, 60, "history")
    state = sync.configure(A, mapping, False, 60, "history")["id"]
    with pytest.raises(ValueError, match="not implemented"):
        sync.run_once(A, state)


def test_history_only_adapter_can_be_bound_without_inventing_sync():
    system, mapping, _, _, adapter = history_configured()
    adapter.capabilities = frozenset({"history"})
    runtime.bind(system, adapter, revision="history-only-v2", objects=["customers"])
    state = sync.configure(A, mapping, True, 60, "history", reviewed_binding_revision="history-only-v2", reviewed_binding_environment="unspecified")["id"]
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    with pytest.raises(ValueError):
        sync.configure(A, mapping, True, 60)


def test_legacy_sync_state_without_mode_keeps_same_identity_and_behavior():
    _, mapping, live, _ = configured(False)
    state_of(live).pop("mode")
    assert sync.configure(A, mapping, False, 60)["id"] == live
    assert sync.states(A)[0]["mode"] == "sync"
    assert sync.run_once(A, live)["status"] == "awaiting_review"


def test_history_configuration_http_has_strict_read_only_modes():
    _, mapping, _, _, _ = history_configured()
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    app.dependency_overrides[admin] = lambda: B
    body = {"mapping_id": mapping, "mode": "history", "enabled": False}
    assert client.post("/dealer-bridge/sync", json=body).json()["mode"] == "history"
    assert client.post("/dealer-bridge/sync", json={**body, "mode": "write"}).status_code == 422
    app.dependency_overrides[admin] = lambda: API
    assert client.post("/dealer-bridge/sync", json=body).status_code == 403
