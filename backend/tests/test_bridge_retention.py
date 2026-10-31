from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import admin, router
from core import dealer_bridge as bridge, bridge_retention as retention
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, CSV, imported, isolated, setup  # noqa: F401


def test_cleanup_preserves_canonical_history_and_receipt():
    job_id = imported()
    before = deepcopy(bridge.get(job_id, "BridgeJob"))
    history = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()
               if value.entity_type in {"Customer", "SourceObservation", "BridgeExternalID"}}
    review = retention.preview(API, job_id)
    assert review["eligible"] and review["retained_rows"] == 1
    result = retention.cleanup(B, job_id, review["review_token"], "Reviewed synthetic retention decision")
    after = bridge.get(job_id, "BridgeJob")
    assert result["status"] == "removed" and after["rows"] == after["preview"] == []
    for field in ("status", "activation_receipt", "source_evidence", "content_hash", "reconciliation"):
        assert after[field] == before[field]
    assert history == {key: value.attributes for key, value in ledger.entities.items()
                       if value.entity_type in {"Customer", "SourceObservation", "BridgeExternalID"}}
    assert bridge.import_report(A, job_id)["receipt_integrity"] == "consistent"
    assert bridge.activate(B, job_id)["idempotent"]
    assert retention.cleanup(B, job_id, review["review_token"], "Repeated reviewed decision")["status"] == "already_removed"
    assert not retention.preview(A, job_id)["eligible"]


def test_cancelled_job_can_be_cleaned_but_not_reactivated():
    _, mapping = setup()
    job = bridge.stage(A, mapping, CSV)["id"]
    bridge.cancel_import(A, job, "Cancel synthetic source import")
    retention.cleanup(A, job, retention.preview(A, job)["review_token"], "Remove cancelled staging copy")
    assert bridge.get(job, "BridgeJob")["status"] == "cancelled"
    with pytest.raises(ValueError):
        bridge.activate(A, job)


def test_active_jobs_agent_calls_and_stale_reviews_cannot_remove_payload():
    _, mapping = setup()
    job = bridge.stage(A, mapping, CSV)["id"]
    review = retention.preview(A, job)
    assert not review["eligible"]
    with pytest.raises(ValueError, match="Only activated"):
        retention.cleanup(A, job, review["review_token"], "Premature cleanup should fail")
    bridge.cancel_import(A, job, "Cancel synthetic import")
    with pytest.raises(ValueError, match="changed"):
        retention.cleanup(A, job, review["review_token"], "Old review should fail")
    with pytest.raises(PermissionError):
        retention.cleanup(API, job, retention.preview(A, job)["review_token"], "Agent cannot remove payload")
    assert bridge.get(job, "BridgeJob")["rows"]


def test_cleanup_save_failure_restores_payload_and_audit(monkeypatch):
    job = imported()
    before = deepcopy(bridge.get(job, "BridgeJob"))
    count = len(ledger.entities)
    def fail(_):
        raise OSError("synthetic save failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError):
        retention.cleanup(A, job, retention.preview(A, job)["review_token"], "Reviewed cleanup attempt")
    assert bridge.get(job, "BridgeJob") == before
    assert len(ledger.entities) == count


def test_cleanup_api_restricts_actor_and_workspace():
    job = imported()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/imports/{job}/payload-cleanup"
    review = client.get(path).json()
    body = {"review_token": review["review_token"], "reason": "Synthetic approved cleanup"}
    assert client.post(path, json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "other"}
    assert client.get(path).status_code == 403
    app.dependency_overrides[admin] = lambda: A
    assert client.post(path, json=body).json()["status"] == "removed"


@pytest.mark.parametrize("corrupt", ["missing", "checksum", "content_hash"])
def test_legacy_or_inconsistent_receipts_keep_payload_for_review(corrupt):
    job_id = imported()
    job = bridge.get(job_id, "BridgeJob")
    if corrupt == "missing":
        job.pop("activation_receipt")
    elif corrupt == "checksum":
        job["activation_receipt"]["checksum"] = "changed"
    else:
        job["content_hash"] = "changed"
    review = retention.preview(A, job_id)
    assert not review["eligible"]
    with pytest.raises(ValueError, match="receipt"):
        retention.cleanup(A, job_id, review["review_token"], "Unsafe cleanup must fail")
    assert job["rows"]


@pytest.mark.parametrize("field", ["job_id", "system_id", "activated_by", "validation_hash", "source_evidence"])
def test_self_consistent_receipt_must_belong_to_reviewed_job(field):
    job_id = imported()
    job = bridge.get(job_id, "BridgeJob")
    receipt = job["activation_receipt"]
    receipt[field] = "different"
    receipt["checksum"] = bridge.digest({key: value for key, value in receipt.items() if key != "checksum"})
    assert bridge.import_report(A, job_id)["receipt_integrity"] == "mismatch"
    review = retention.preview(A, job_id)
    assert not review["eligible"]
    with pytest.raises(ValueError, match="receipt"):
        retention.cleanup(A, job_id, review["review_token"], "Mismatched receipt must block cleanup")
    assert job["rows"]


@pytest.mark.parametrize("field", ["rows", "preview"])
def test_changed_retained_payload_is_not_consistent(field):
    job_id = imported()
    job = bridge.get(job_id, "BridgeJob")
    job[field][0]["unexpected"] = "changed"
    assert bridge.import_report(A, job_id)["receipt_integrity"] == "mismatch"
    assert not retention.preview(A, job_id)["eligible"]


@pytest.mark.parametrize("field", ["source_evidence", "mapping_hash"])
def test_cancelled_payload_cleanup_requires_review_of_current_evidence(field):
    _, mapping = setup()
    job_id = bridge.stage(A, mapping, CSV)["id"]
    bridge.cancel_import(B, job_id, "Cancelled synthetic source import")
    original = retention.preview(B, job_id)
    job = bridge.get(job_id, "BridgeJob")
    job[field] = {"changed": "Synthetic operator correction"} if field == "source_evidence" else "changed"
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError, match="changed"):
        retention.cleanup(B, job_id, original["review_token"], "Review retained payload cleanup")
    assert ledger.entities == before and job["rows"]
    current = retention.preview(B, job_id)
    assert current["eligible"] and current["review_token"] != original["review_token"]


def test_consistent_receipt_repair_invalidates_earlier_cleanup_review():
    job_id = imported()
    original = retention.preview(B, job_id)
    job = bridge.get(job_id, "BridgeJob")
    # Simulate an operator correction; checksums are not privileged-writer guards.
    job["source_evidence"]["operator_annotation"] = "Synthetic reviewed correction"
    receipt = job["activation_receipt"]
    receipt["source_evidence"] = deepcopy(job["source_evidence"])
    receipt["checksum"] = bridge.digest({key: value for key, value in receipt.items() if key != "checksum"})
    assert bridge.import_report(B, job_id)["receipt_integrity"] == "consistent"
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError, match="changed"):
        retention.cleanup(B, job_id, original["review_token"], "Previous cleanup review is stale")
    assert ledger.entities == before and job["rows"]
    assert retention.preview(B, job_id)["review_token"] != original["review_token"]
