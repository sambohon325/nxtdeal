"""Mappings can be tested by agents without creating an activatable import job."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as b
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, API, CSV, setup, isolated  # noqa: F401


def snapshot():
    return deepcopy({key: (entity.entity_type, entity.attributes) for key, entity in ledger.get_all().items()})


def test_agent_simulation_does_not_save_or_create_approvals_jobs_or_canonical_records(monkeypatch):
    _, mapping = setup(False)
    before = snapshot()
    def forbidden_save(*args):
        raise AssertionError("Simulation must not persist")
    monkeypatch.setattr(b, "save_graph", forbidden_save)
    result = b.simulate_mapping(API, mapping, CSV, {"row_count": 1})
    assert result["status"] == "simulated" and result["stored"] is False
    assert result["mapping_status"] == "proposed"
    assert result["rows"][0]["values"]["first_name"] == "Ada"
    assert result["reconciliation"]["status"] == "matched"
    assert snapshot() == before
    with pytest.raises(PermissionError):
        b.approve_mapping(API, mapping)


def test_simulation_uses_same_validation_and_reconciliation_as_staging():
    _, mapping = setup(False)
    content = CSV.replace("ada@example.com", "invalid-email")
    simulated = b.simulate_mapping(API, mapping, content, {"row_count": 2})
    job = b.stage(A, mapping, content, {"row_count": 2})["id"]
    assert b.validate(A, job) == simulated["rows"]
    assert b.get(job, "BridgeJob")["reconciliation"] == simulated["reconciliation"]
    assert simulated["reconciliation"]["status"] == "incomplete"


def test_test_results_never_authorize_activation_or_freeze_identity_candidates():
    _, mapping = setup()
    assert b.simulate_mapping(API, mapping, CSV)["rows"][0]["status"] == "ready"
    ledger.add_entity(Entity("new-candidate", "Customer", {"Email": "ada@example.com"}))
    job = b.stage(A, mapping, CSV)["id"]
    with pytest.raises(ValueError, match="Validate"):
        b.activate(B, job)
    assert b.validate(A, job)[0]["status"] == "quarantined"


def test_simulation_can_diagnose_paused_source_but_staging_stays_blocked():
    system, mapping = setup(False)
    b.set_system_paused(B, system, True, "Pause while correcting the proposed mapping")
    assert b.simulate_mapping(API, mapping, CSV)["status"] == "simulated"
    with pytest.raises(ValueError, match="paused"):
        b.stage(A, mapping, CSV)


def test_revoked_or_tampered_mapping_is_not_simulated():
    _, mapping = setup(False)
    b.revoke_mapping(B, mapping, "Discard proposed mapping after source review")
    with pytest.raises(ValueError, match="revoked"):
        b.simulate_mapping(A, mapping, CSV)
    _, mapping = setup(False)
    b.get(mapping, "BridgeMapping")["fields"]["first_name"]["source"] = "email"
    with pytest.raises(ValueError, match="definition changed"):
        b.simulate_mapping(A, mapping, CSV)


def test_unmapped_private_column_values_are_not_returned_or_retained():
    _, mapping = setup(False)
    content = CSV.replace("name,email", "name,email,private_note").replace("ada@example.com\n", "ada@example.com,unmapped-private-value\n")
    result = b.simulate_mapping(API, mapping, content)
    assert "unmapped-private-value" not in str(result)
    assert result["source_evidence"]["omitted_columns"] == ["private_note"]
    assert not any(entity.entity_type == "BridgeJob" for entity in ledger.get_all().values())


def test_simulation_api_rejects_unknown_controls_and_foreign_workspace():
    _, mapping = setup(False)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/mappings/{mapping}/test"
    assert client.post(path, json={"content": CSV}).json()["stored"] is False
    assert client.post(path, json={"content": CSV, "activate": True}).status_code == 422
    app.dependency_overrides[admin] = lambda: {**API, "workspace_id": "elsewhere"}
    assert client.post(path, json={"content": CSV}).status_code == 403
