import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import dealer_bridge as bridge, bridge_runtime as runtime, bridge_sync as sync
from core.bridge_contracts import SourceRecord, SyncPage
from core.bridge_connectors import parse_csv
from tests.test_bridge_sync import FakeConnector, state_of, A, B, API, isolated  # noqa: F401
from tests.test_bridge_accounting import configured as journal_mapping, CSV


def source(required=True, content=CSV):
    mapping = journal_mapping()
    system = bridge.get(mapping, "BridgeMapping")["system_id"]
    adapter = FakeConnector()
    adapter.page = SyncPage(tuple(SourceRecord("journal_lines", row["external_id"], row["modified_at"], row) for row in parse_csv(content)[1]), "journal-page", True)
    runtime.bind(system, adapter, revision="balance-test-1", objects=["journal_lines"], environment="synthetic")
    state = sync.configure(A, mapping, True, 60, require_balanced_journals=required)["id"]
    return mapping, state, adapter


def test_collected_journal_page_preserves_required_check_in_job_and_receipt():
    mapping, state, _ = source()
    job = sync.run_once(A, state)["job_id"]
    assert bridge.get(job, "BridgeJob")["expectations"]["balanced_journals"]
    bridge.validate(A, job); bridge.activate(B, job)
    report = bridge.import_report(A, job)
    assert report["reconciliation"]["status"] == "matched"
    assert report["activation_receipt"]["expectations"]["balanced_journals"]
    assert sync.run_once(B, state)["status"] == "checkpointed"
    sync.configure(B, mapping, False, 60)
    assert state_of(state)["require_balanced_journals"] is True


def test_unbalanced_collected_page_cannot_activate_or_advance():
    _, state, _ = source(content=CSV.replace("credit,0.20", "credit,0.21"))
    job = sync.run_once(A, state)["job_id"]
    bridge.validate(A, job)
    assert bridge.get(job, "BridgeJob")["status"] == "blocked"
    with pytest.raises(ValueError): bridge.activate(B, job)
    assert sync.run_once(A, state)["status"] == "awaiting_review"
    assert state_of(state)["cursor"] is None


@pytest.mark.parametrize("activated", [False, True])
def test_balance_policy_cannot_change_while_a_retained_page_is_pending(activated):
    mapping, state, _ = source()
    job = sync.run_once(A, state)["job_id"]
    if activated:
        bridge.validate(A, job); bridge.activate(B, job)
    with pytest.raises(ValueError, match="checkpoint"):
        sync.configure(B, mapping, True, 60, require_balanced_journals=False)
    assert state_of(state)["require_balanced_journals"] is True


def test_policy_change_during_read_discards_the_page():
    mapping, state, adapter = source(required=False)
    adapter.during_read = lambda: sync.configure(B, mapping, True, 60, require_balanced_journals=True)
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["pending_job_id"] is None and state_of(state)["cursor"] is None


def test_pending_activation_cannot_checkpoint_against_tampered_policy():
    _, state, _ = source()
    job = sync.run_once(A, state)["job_id"]
    bridge.validate(A, job); bridge.activate(B, job)
    state_of(state)["require_balanced_journals"] = False
    with pytest.raises(ValueError, match="balance policy"):
        sync.run_once(B, state)
    assert state_of(state)["cursor"] is None


def test_policy_api_is_strict_human_only_and_kind_specific():
    mapping, state, _ = source(required=False)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    body = {"mapping_id": mapping, "enabled": False, "require_balanced_journals": True}
    assert client.post("/dealer-bridge/sync", json=body).status_code == 403
    app.dependency_overrides[admin] = lambda: B
    assert client.post("/dealer-bridge/sync", json={**body, "require_balanced_journals": "true"}).status_code == 422
    assert client.post("/dealer-bridge/sync", json=body).json()["require_balanced_journals"] is True
    from tests.test_bridge_sync import configured
    _, customer_mapping, _, _ = configured()
    assert client.post("/dealer-bridge/sync", json={**body, "mapping_id": customer_mapping}).status_code == 400
