from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import admin, router
from core import bridge_sync_recovery as recovery, dealer_bridge as b, bridge_sync as sync
from core.dealeros import ledger
from tests.test_bridge_sync import configured, state_of, A, B, API, isolated  # noqa: F401


def pending():
    system, mapping, state, connector = configured()
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    return system, mapping, state, job, connector


def test_legacy_page_recovery_preserves_records_and_rereads_for_review():
    _, mapping, state, job, connector = pending()
    prior = b.get(job, "BridgeJob")
    prior.pop("collection_page")
    prior["activation_receipt"].pop("collection_page")
    prior["activation_receipt"]["checksum"] = b.digest({k: v for k, v in prior["activation_receipt"].items() if k != "checksum"})
    availability = sync.public(state, state_of(state))["availability"]
    assert availability["status"] == "review_required"
    assert not availability["binding_review_required"]
    preserved = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    plan = recovery.preview(API, state)
    result = recovery.replay(B, state, plan["review_token"], "Replay legacy page from accepted position")
    assert not result["state"]["enabled"] and result["state"]["pending_job_id"] is None
    assert state_of(state)["cursor"] is None and state_of(state)["pages_accepted"] == 0
    for key, attrs in preserved.items():
        if key != state:
            assert ledger.entities[key].attributes == attrs
    sync.configure(B, mapping, True, 60)
    replay_job = sync.run_once(B, state)["job_id"]
    assert replay_job != job and connector.calls == [("customers", None), ("customers", None)]
    assert b.validate(B, replay_job)[0]["status"] == "duplicate"
    b.activate(B, replay_job)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 1


def test_recovery_requires_human_and_fresh_plan():
    _, _, state, job, _ = pending()
    plan = recovery.preview(A, state)
    with pytest.raises(PermissionError):
        recovery.replay(API, state, plan["review_token"], "Agent must not recover cursor")
    b.get(job, "BridgeJob")["activation_receipt"]["checksum"] = "changed"
    with pytest.raises(ValueError, match="changed"):
        recovery.replay(B, state, plan["review_token"], "Stale recovery must be reviewed")
    assert state_of(state)["pending_job_id"] == job


def test_recovery_save_failure_rolls_back(monkeypatch):
    _, _, state, _, _ = pending()
    plan = recovery.preview(A, state)
    before = deepcopy(state_of(state))
    count = len(ledger.entities)
    def fail(path):
        raise OSError("Synthetic save failure")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(OSError):
        recovery.replay(B, state, plan["review_token"], "Reviewed synthetic recovery")
    assert state_of(state) == before and len(ledger.entities) == count


@pytest.mark.parametrize("condition", ["no_pending", "staged", "foreign_job", "lease"])
def test_unresolved_or_unrelated_pages_cannot_be_detached(condition):
    _, _, state, job, _ = pending()
    if condition == "no_pending":
        state_of(state)["pending_job_id"] = None
    elif condition == "staged":
        b.get(job, "BridgeJob")["status"] = "staged"
    elif condition == "foreign_job":
        b.get(job, "BridgeJob")["sync_state_id"] = "different"
    else:
        state_of(state)["lease_until"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        recovery.preview(A, state)


def test_recovery_api_workspace_and_actor_boundary():
    _, _, state, _, _ = pending()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    plan = client.get(f"/dealer-bridge/sync/{state}/replay-preview").json()
    body = {"review_token": plan["review_token"], "reason": "Reviewed synthetic replay"}
    assert client.post(f"/dealer-bridge/sync/{state}/replay", json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "foreign"}
    assert client.get(f"/dealer-bridge/sync/{state}/replay-preview").status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post(f"/dealer-bridge/sync/{state}/replay", json=body).status_code == 200
