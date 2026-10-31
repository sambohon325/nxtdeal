from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import bridge_event_imports as imports, bridge_event_retention as retention, dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401
from tests.test_bridge_event_imports import staged
from tests.test_bridge_event_lineage import activated


def test_cleanup_preserves_history_receipt_and_original_batch_count():
    system, _, job_id = activated()
    before = imports.lineage(A, system, "Provider", "private-id")
    retained = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()
                if value.entity_type in {"Lead", "SourceObservation", "BridgeEventExternalID"}}
    review = retention.preview(API, job_id)
    assert review["eligible"] and review["retained_rows"] == 1
    assert "private@example.com" not in str(review)
    assert retention.cleanup(B, job_id, review["review_token"], "Reviewed synthetic retention decision")["status"] == "removed"
    report = imports.report(A, job_id)
    assert report["rows"] == report["preview"] == []
    assert report["receipt_integrity"] == "consistent"
    assert imports.lineage(A, system, "Provider", "private-id") == before
    assert retained == {key: value.attributes for key, value in ledger.entities.items()
                        if value.entity_type in {"Lead", "SourceObservation", "BridgeEventExternalID"}}
    assert imports.list_jobs(A, system)["jobs"][0]["row_count"] == 1
    assert imports.list_jobs(A, system)["jobs"][0]["payload_removed"]
    assert imports.activate(B, job_id)["idempotent"]
    assert retention.cleanup(B, job_id, review["review_token"], "Repeat reviewed retention decision")["status"] == "already_removed"
    assert not retention.preview(A, job_id)["eligible"]


def test_unfinished_and_agent_cleanup_are_blocked_and_cancelled_batch_stays_final():
    _, _, job = staged()
    review = retention.preview(A, job)
    assert not review["eligible"]
    with pytest.raises(ValueError, match="Only activated"):
        retention.cleanup(B, job, review["review_token"], "Do not remove unfinished batch")
    imports.cancel(B, job, "Cancel synthetic event batch")
    with pytest.raises(ValueError, match="changed"):
        retention.cleanup(B, job, review["review_token"], "Stale review must not succeed")
    review = retention.preview(A, job)
    with pytest.raises(PermissionError):
        retention.cleanup(API, job, review["review_token"], "Agent cannot remove event data")
    retention.cleanup(B, job, review["review_token"], "Remove cancelled staging copy")
    with pytest.raises(ValueError): imports.validate(A, job)
    with pytest.raises((ValueError, PermissionError)): imports.activate(B, job)


@pytest.mark.parametrize("field", ["rows", "preview", "source_evidence", "validated_by", "created_by", "activation_receipt"])
def test_changed_event_evidence_is_not_eligible(field):
    _, _, job_id = activated()
    job = bridge.get(job_id, "BridgeEventJob")
    if field in {"rows", "preview"}: job[field][0]["values"]["first_name"] = "Changed"
    elif field == "source_evidence": job[field]["byte_count"] += 1
    elif field == "activation_receipt": job.pop(field)
    else: job[field] = "another-actor"
    assert not retention.preview(A, job_id)["eligible"]
    with pytest.raises(ValueError, match="receipt"):
        retention.cleanup(B, job_id, retention.preview(A, job_id)["review_token"], "Invalid receipt must retain payload")
    assert job["rows"]


def test_failed_cleanup_save_restores_payload_and_audit(monkeypatch):
    _, _, job = activated()
    before = deepcopy(bridge.get(job, "BridgeEventJob"))
    keys = set(ledger.entities)
    def fail(_): raise OSError("synthetic save failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError):
        retention.cleanup(B, job, retention.preview(A, job)["review_token"], "Reviewed retention test decision")
    assert bridge.get(job, "BridgeEventJob") == before
    assert set(ledger.entities) == keys


def test_event_cleanup_api_is_strict_human_only_and_workspace_scoped():
    _, _, job = activated()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/event-imports/{job}/payload-cleanup"
    review = client.get(path).json()
    body = {"review_token": review["review_token"], "reason": "Reviewed synthetic retention"}
    assert client.post(path, json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "other"}
    assert client.get(path).status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post(path, json={**body, "delete_history": True}).status_code == 422
    assert client.post(path, json=body).json()["status"] == "removed"


@pytest.mark.parametrize("field", ["rows", "preview"])
def test_cleanup_marker_does_not_hide_reintroduced_staging_data(field):
    _, _, job_id = activated()
    job = bridge.get(job_id, "BridgeEventJob")
    original = deepcopy(job[field])
    retention.cleanup(B, job_id, retention.preview(A, job_id)["review_token"], "Reviewed synthetic retention decision")
    job[field] = original
    assert imports.report(A, job_id)["receipt_integrity"] == "changed"



def test_retained_observation_lookup_survives_cleanup_and_enforces_identity():
    system, _, job = activated()
    before = imports.lineage(A, system, "Provider", "private-id")
    event_id = before["observation"]["event_id"]
    retention.cleanup(B, job, retention.preview(A, job)["review_token"], "Reviewed synthetic retention decision")
    assert imports.observation_lineage(API, event_id) == before
    with pytest.raises(PermissionError):
        imports.observation_lineage({**A, "workspace_id": "other"}, event_id)
    event = bridge.get(event_id, "SourceObservation")
    event["source_time_semantics"] = "modified"
    with pytest.raises(ValueError, match="creation event"):
        imports.observation_lineage(A, event_id)


def test_retained_observation_api_rejects_copied_or_foreign_identity():
    from core.entities import Entity
    _, _, job = activated()
    event_id = imports.report(A, job)["activation_receipt"]["created"][0]["event_id"]
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: A
    client = TestClient(app)
    assert client.get(f"/dealer-bridge/event-observations/{event_id}").json()["receipt_integrity"] == "consistent"
    copied = deepcopy(bridge.get(event_id, "SourceObservation"))
    ledger.add_entity(Entity("copied-event", "SourceObservation", copied))
    assert client.get("/dealer-bridge/event-observations/copied-event").status_code == 400
    copied["workspace_id"] = "other"
    ledger.add_entity(Entity("foreign-event", "SourceObservation", copied))
    response = client.get("/dealer-bridge/event-observations/foreign-event")
    assert response.status_code == 400
    assert "private@example.com" not in response.text
