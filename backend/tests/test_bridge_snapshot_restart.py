from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import bridge_snapshot_restart as recovery, bridge_sync as sync, bridge_runtime as runtime, dealer_bridge as b
from core.dealeros import ledger
from tests.test_bridge_sync import configured, state_of, A, B, API, isolated  # noqa: F401
from tests.test_bridge_export_file_paged import reader, content


def partial(tmp_path):
    system, mapping, state, _ = configured()
    path, adapter = reader(tmp_path)
    runtime.bind(system, adapter, revision="paged-restart-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="paged-restart-1", reviewed_binding_environment="synthetic")
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job); b.activate(B, job)
    assert sync.run_once(A, state)["status"] == "checkpointed"
    return system, mapping, state, job, path, adapter


def test_changed_partial_snapshot_restarts_with_review_and_preserves_prior_evidence(tmp_path):
    _, _, state, prior_job, path, _ = partial(tmp_path)
    old_cursor = state_of(state)["cursor"]
    path.write_text(content(4), encoding="utf-8", newline="")
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["last_error_code"] == "source_changed"
    retained = {key: deepcopy(value.attributes) for key, value in ledger.entities.items() if key != state}
    plan = recovery.preview(API, state)
    assert plan["pages_previously_accepted"] == 1
    result = recovery.restart(B, state, plan["review_token"], "Replace incomplete synthetic source export")
    assert result["state"]["enabled"] is False
    assert state_of(state)["cursor"].startswith("csvrestart:v1:")
    for key, attributes in retained.items():
        assert ledger.entities[key].attributes == attributes
    audit = b.get(result["recovery_id"], "BridgeSyncRecovery")
    assert audit["checkpoint_hash"] == b.digest(old_cursor)
    replay_job = sync.run_once(B, state)["job_id"]
    assert replay_job != prior_job
    assert {row["status"] for row in b.validate(B, replay_job)} == {"duplicate"}
    b.activate(B, replay_job)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    final_job = sync.run_once(B, state)["job_id"]
    b.validate(B, final_job); b.activate(B, final_job)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    assert state_of(state)["cursor"].endswith(":4:done")
    assert state_of(state)["pages_accepted"] == 3
    assert b.import_report(A, prior_job)["receipt_integrity"] == "consistent"
    assert len([e for e in ledger.get_all().values() if e.entity_type == "Customer"]) == 4


@pytest.mark.parametrize("change", ["file", "state", "binding", "pause"], ids=["file", "state", "binding", "pause"])
def test_stale_restart_review_cannot_reset_checkpoint(tmp_path, change):
    system, mapping, state, _, path, _ = partial(tmp_path)
    plan = recovery.preview(A, state)
    cursor = state_of(state)["cursor"]
    if change == "file": path.write_text(content(4), encoding="utf-8", newline="")
    elif change == "state": sync.configure(B, mapping, False, 120)
    elif change == "binding": runtime.unbind(system)
    else: b.get(system, "BridgeSystem")["paused"] = True
    with pytest.raises(ValueError): recovery.restart(B, state, plan["review_token"], "Stale review must not change position")
    assert state_of(state)["cursor"] == cursor


def test_replacement_changed_after_confirmation_blocks_until_reviewed_again(tmp_path):
    _, _, state, _, path, _ = partial(tmp_path)
    plan = recovery.preview(A, state)
    recovery.restart(B, state, plan["review_token"], "Reviewed synthetic replacement")
    path.write_text(content(4), encoding="utf-8", newline="")
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["pending_job_id"] is None
    next_plan = recovery.preview(A, state)
    recovery.restart(B, state, next_plan["review_token"], "Review changed replacement bytes again")
    assert sync.run_once(A, state)["status"] == "awaiting_review"


@pytest.mark.parametrize("condition", ["pending", "activated", "lease", "history", "completed", "unstarted"])
def test_restart_requires_idle_partial_snapshot_and_resolved_pages(tmp_path, condition):
    _, _, state, _, _, _ = partial(tmp_path)
    if condition in {"pending", "activated"}:
        job = sync.run_once(A, state)["job_id"]
        if condition == "activated": b.validate(A, job); b.activate(B, job)
    elif condition == "lease": state_of(state)["lease_until"] = "2099-01-01T00:00:00Z"
    elif condition == "history": state_of(state)["mode"] = "history"
    elif condition == "completed": state_of(state)["cursor"] = state_of(state)["cursor"].replace(":more", ":done")
    else: state_of(state)["cursor"] = None
    with pytest.raises(ValueError): recovery.preview(A, state)


def test_cancelled_pending_page_is_retained_and_detached_on_reviewed_restart(tmp_path):
    _, _, state, _, _, _ = partial(tmp_path)
    job = sync.run_once(A, state)["job_id"]
    b.cancel_import(B, job, "Replace incomplete source snapshot")
    plan = recovery.preview(A, state)
    result = recovery.restart(B, state, plan["review_token"], "Reviewed restart after cancelling page")
    assert state_of(state)["pending_job_id"] is None
    assert b.get(job, "BridgeJob")["status"] == "cancelled"
    assert b.get(result["recovery_id"], "BridgeSyncRecovery")["cancelled_job_id"] == job


def test_restart_rechecks_configuration_after_inspection_and_redacts_read_error(tmp_path, monkeypatch):
    system, _, state, _, _, adapter = partial(tmp_path)
    original = adapter.reviewed_restart_cursor
    def changed(obj):
        result = original(obj)
        b.get(system, "BridgeSystem")["paused"] = True
        return result
    monkeypatch.setattr(adapter, "reviewed_restart_cursor", changed)
    with pytest.raises(ValueError): recovery.preview(A, state)
    b.get(system, "BridgeSystem")["paused"] = False
    def failed(obj): raise OSError("PRIVATE SOURCE PATH")
    monkeypatch.setattr(adapter, "reviewed_restart_cursor", failed)
    with pytest.raises(ValueError) as error: recovery.preview(A, state)
    assert "PRIVATE" not in str(error.value)


def test_restart_save_failure_rolls_back(tmp_path, monkeypatch):
    _, _, state, _, _, _ = partial(tmp_path)
    plan = recovery.preview(A, state)
    before, count = deepcopy(state_of(state)), len(ledger.entities)
    def failed(path): raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(b, "save_graph", failed)
    with pytest.raises(OSError): recovery.restart(B, state, plan["review_token"], "Reviewed replacement before failed save")
    assert state_of(state) == before and len(ledger.entities) == count


def test_restart_api_requires_interactive_human_and_workspace(tmp_path):
    _, _, state, _, _, _ = partial(tmp_path)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    plan = client.get(f"/dealer-bridge/sync/{state}/snapshot-restart-preview").json()
    body = {"review_token": plan["review_token"], "reason": "Reviewed replacement export"}
    assert client.post(f"/dealer-bridge/sync/{state}/snapshot-restart", json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: {**B, "workspace_id": "foreign"}
    assert client.get(f"/dealer-bridge/sync/{state}/snapshot-restart-preview").status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post(f"/dealer-bridge/sync/{state}/snapshot-restart", json=body).status_code == 200
