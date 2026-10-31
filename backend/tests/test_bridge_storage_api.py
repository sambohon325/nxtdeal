"""Storage faults are recoverable JSON responses, not authorization diagnostics."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, CSV, setup, isolated  # noqa: F401


def client(actor=B):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: actor
    return TestClient(app)


@pytest.mark.parametrize("fault", [OSError, PermissionError])
def test_save_fault_returns_redacted_503_after_rollback(monkeypatch, fault):
    before = deepcopy(ledger.entities)
    def fail(path):
        raise fault("private-storage-path private-volume-details")
    monkeypatch.setattr(bridge, "save_graph", fail)
    response = client().post("/dealer-bridge/systems", json={"vendor": "CSV", "name": "Synthetic source"})
    assert response.status_code == 503
    assert "reload the current state" in response.json()["detail"]
    assert "private" not in response.text
    assert ledger.entities == before


def test_activation_storage_failure_preserves_review_and_retry(monkeypatch):
    _, mapping = setup()
    job = bridge.stage(A, mapping, CSV)["id"]
    bridge.validate(A, job)
    before = deepcopy(ledger.entities)
    saved = bridge.save_graph
    def fail(path): raise PermissionError("private filesystem access failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    api = client()
    assert api.post(f"/dealer-bridge/imports/{job}/activate", json={}).status_code == 503
    assert ledger.entities == before
    monkeypatch.setattr(bridge, "save_graph", saved)
    assert api.post(f"/dealer-bridge/imports/{job}/activate", json={}).status_code == 200
    assert bridge.import_report(A, job)["receipt_integrity"] == "consistent"


def test_human_permission_failure_remains_403():
    _, mapping = setup()
    job = bridge.stage(A, mapping, CSV)["id"]
    bridge.validate(A, job)
    before = deepcopy(ledger.entities)
    response = client(API).post(f"/dealer-bridge/imports/{job}/activate", json={})
    assert response.status_code == 403
    assert ledger.entities == before


def test_concurrent_record_conflict_remains_409(monkeypatch):
    system = bridge.connect(A, "CSV", "Synthetic source")["id"]
    def fail(path):
        ledger.get_entity(system).attributes["pause_reason"] = "Concurrent operator review"
        raise OSError("private filesystem error")
    monkeypatch.setattr(bridge, "save_graph", fail)
    response = client().post(f"/dealer-bridge/systems/{system}/pause",
        json={"paused": True, "reason": "Original operator review"})
    assert response.status_code == 409 and "private" not in response.text
    assert ledger.get_entity(system).attributes["pause_reason"] == "Concurrent operator review"
