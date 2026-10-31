"""Activation evidence is captured at commit, not reconstructed from today's mapping."""
from copy import deepcopy
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import dealer_bridge as b
from core.dealeros import ledger
from core.storage import load_graph, save_graph
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, API, CSV, setup, imported, isolated  # noqa: F401


def test_receipt_captures_exact_review_and_survives_later_mapping_revocation():
    system, mapping = setup()
    job = imported(mapping=mapping)
    report = b.import_report(API, job)
    receipt = report["activation_receipt"]
    assert report["receipt_integrity"] == "consistent"
    assert receipt["job_id"] == job and receipt["system_id"] == system
    assert receipt["mapping_proposed_by"] == A["employee_id"]
    assert receipt["mapping_proposed_principal"] == "api"
    assert receipt["mapping_approved_by"] == B["employee_id"]
    assert receipt["staged_by"] == A["employee_id"] and receipt["activated_by"] == B["employee_id"]
    assert receipt["validated_by"] == A["employee_id"] and receipt["validated_principal"] == "session"
    assert receipt["transport"] == "manual_upload" and receipt["binding_revision"] is None
    assert receipt["mapping_hash_version"] == 3 and receipt["transform_version"] == 3
    assert receipt["preview_hash"] == b.digest(b.get(job, "BridgeJob")["preview"])
    assert receipt["content_hash"] == b.digest(b.get(job, "BridgeJob")["rows"])
    b.revoke_mapping(B, mapping, "Replacing this source mapping")
    assert b.activate(B, job)["idempotent"]
    assert b.import_report(A, job)["activation_receipt"] == receipt
    assert "ada@example.com" not in json.dumps(receipt)
    assert "activation_receipt" not in next(value for value in b.system_map(A)["jobs"] if value["id"] == job)


def test_receipt_is_detached_and_checksum_failure_is_explicit():
    _, mapping = setup(); job = imported(mapping=mapping)
    receipt = b.import_report(A, job)["activation_receipt"]
    receipt["reconciliation"]["counts"]["ready"] = 99
    assert b.import_report(A, job)["receipt_integrity"] == "consistent"
    b.get(job, "BridgeJob")["activation_receipt"]["activated_by"] = "changed"
    assert b.import_report(A, job)["receipt_integrity"] == "mismatch"


def test_old_activated_jobs_are_not_given_invented_receipts():
    _, mapping = setup(); job = imported(mapping=mapping)
    b.get(job, "BridgeJob").pop("activation_receipt")
    assert b.activate(B, job)["idempotent"]
    report = b.import_report(A, job)
    assert report["activation_receipt"] is None and report["receipt_integrity"] == "not_recorded"


def test_failed_activation_rolls_back_receipt_with_canonical_records(monkeypatch):
    _, mapping = setup(); job = b.stage(A, mapping, CSV)["id"]; b.validate(A, job)
    before = deepcopy(b.get(job, "BridgeJob"))
    def fail(path):
        raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(OSError): b.activate(B, job)
    assert b.get(job, "BridgeJob") == before
    assert not any(entity.entity_type == "Customer" for entity in ledger.get_all().values())


def test_receipt_survives_real_repository_reload(tmp_path, monkeypatch):
    path = str(tmp_path / "receipt.json")
    monkeypatch.setattr(b, "GRAPH_PATH", path)
    monkeypatch.setattr(b, "save_graph", save_graph)
    _, mapping = setup(); job = imported(mapping=mapping)
    before = b.import_report(A, job)
    ledger.reset(); load_graph(path)
    assert b.import_report(A, job) == before


def test_report_api_is_read_only_and_respects_workspace(monkeypatch):
    _, mapping = setup(); job = imported(mapping=mapping)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    def unexpected_save(path):
        raise AssertionError("Read-only report attempted persistence")
    monkeypatch.setattr(b, "save_graph", unexpected_save)
    assert client.get(f"/dealer-bridge/imports/{job}/report").json()["receipt_integrity"] == "consistent"
    app.dependency_overrides[admin] = lambda: {**API, "workspace_id": "foreign"}
    assert client.get(f"/dealer-bridge/imports/{job}/report").status_code == 403
    app.dependency_overrides[admin] = lambda: API
    b.get(job, "BridgeJob")["workspace_id"] = "foreign"
    assert client.get(f"/dealer-bridge/imports/{job}/report").status_code == 400


def test_staged_cancelled_and_duplicate_import_receipts():
    _, mapping = setup(); job = b.stage(A, mapping, CSV)["id"]
    assert b.import_report(A, job)["receipt_integrity"] == "not_recorded"
    b.cancel_import(B, job, "Source export will be replaced")
    assert b.import_report(A, job)["activation_receipt"] is None
    imported(mapping=mapping); duplicate = imported(mapping=mapping)
    receipt = b.import_report(A, duplicate)["activation_receipt"]
    assert receipt["reconciliation"]["counts"] == {"duplicate": 1}
