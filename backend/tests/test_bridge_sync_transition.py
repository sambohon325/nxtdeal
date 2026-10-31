import pytest
from core import dealer_bridge as b, bridge_sync as sync
from core.dealeros import ledger
from tests.test_bridge_sync import configured, state_of, A, B, API, isolated  # noqa: F401


def replacement(system, kind="Customer", object_type="customers"):
    mapping = b.propose_mapping(A, system, kind, object_type, {"first_name": {"source": "name", "transform": "text"}})["id"]
    b.approve_mapping(B, mapping)
    return mapping


def test_transition_preserves_checkpoint_disables_schedule_and_retains_evidence():
    system, old, state, connector = configured()
    state_of(state)["cursor"] = "opaque-saved-position"
    new = replacement(system)
    plan = sync.transition_preview(A, state, new)
    assert "opaque-saved-position" not in str(plan)
    with pytest.raises(PermissionError): sync.transition_mapping(API, state, new, plan["review_token"], "New source export layout reviewed")
    result = sync.transition_mapping(B, state, new, plan["review_token"], "New source export layout reviewed")
    assert result["mapping_id"] == new and not result["enabled"]
    assert state_of(state)["cursor"] == "opaque-saved-position"
    assert not connector.calls
    assert any(e.entity_type == "BridgeSyncMappingTransition" for e in ledger.get_all().values())


def test_transition_handles_activated_page_even_after_mapping_revocation():
    system, old, state, _ = configured()
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job); b.activate(B, job)
    b.revoke_mapping(B, old, "Source layout needs replacement")
    new = replacement(system)
    plan = sync.transition_preview(A, state, new)
    assert plan["checkpoint_action"] == "accept_activated_page"
    sync.transition_mapping(B, state, new, plan["review_token"], "Reviewed and accepted prior activated page")
    assert state_of(state)["cursor"] == "cursor-1" and state_of(state)["pages_accepted"] == 1
    assert state_of(state)["pending_job_id"] is None


def test_pending_job_requires_resolution_and_cancel_never_advances():
    system, _, state, _ = configured()
    job = sync.run_once(A, state)["job_id"]
    new = replacement(system)
    with pytest.raises(ValueError, match="Activate or cancel"): sync.transition_preview(A, state, new)
    b.cancel_import(B, job, "Use reviewed replacement layout")
    plan = sync.transition_preview(A, state, new)
    sync.transition_mapping(B, state, new, plan["review_token"], "Use reviewed replacement layout")
    assert state_of(state)["cursor"] is None


def test_changed_stream_invalidates_review_token():
    system, _, state, _ = configured()
    new = replacement(system)
    plan = sync.transition_preview(A, state, new)
    state_of(state)["cursor"] = "changed"
    with pytest.raises(ValueError, match="changed"): sync.transition_mapping(B, state, new, plan["review_token"], "Reviewed replacement source")


def test_no_cross_source_or_kind_switch_and_no_live_lease_transition():
    system, _, state, _ = configured()
    for new in (replacement(system, object_type="different"), replacement(system, kind="Lead")):
        with pytest.raises(ValueError, match="same system"): sync.transition_preview(A, state, new)
    new = replacement(system)
    state_of(state)["lease_until"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="in-progress"): sync.transition_preview(A, state, new)


def test_transition_save_failure_keeps_old_mapping_and_position(monkeypatch):
    system, old, state, _ = configured()
    new = replacement(system)
    plan = sync.transition_preview(A, state, new)
    monkeypatch.setattr(b, "save_graph", lambda path: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError): sync.transition_mapping(B, state, new, plan["review_token"], "Reviewed replacement source")
    assert state_of(state)["mapping_id"] == old and state_of(state)["cursor"] is None
    assert not any(e.entity_type == "BridgeSyncMappingTransition" for e in ledger.get_all().values())


@pytest.mark.parametrize("checkpoint_first", [False, True])
@pytest.mark.parametrize("end_cursor", [None, "end"])
def test_history_mapping_replacement_preserves_completion_without_restarting(checkpoint_first, end_cursor):
    from core.bridge_contracts import SyncPage
    from tests.test_bridge_history_collection import history_configured
    system, old, _, history, adapter = history_configured()
    original_read = adapter.history
    def final_page(*args):
        page = original_read(*args)
        return SyncPage(page.records, end_cursor, True)
    adapter.history = final_page
    job = sync.run_once(A, history)["job_id"]
    b.validate(A, job); b.activate(B, job)
    if checkpoint_first:
        sync.run_once(A, history)
    prior_completed_at = state_of(history).get("completed_at")
    b.revoke_mapping(B, old, "Replace the completed history mapping")
    new = replacement(system)
    calls = list(adapter.calls)
    plan = sync.transition_preview(A, history, new)
    assert plan["status_after_transition"] == "complete"
    result = sync.transition_mapping(B, history, new, plan["review_token"], "Retain the finished historical checkpoint")
    assert result["status"] == "complete" and not result["enabled"]
    assert state_of(history)["cursor"] == end_cursor and state_of(history)["pages_accepted"] == 1
    assert state_of(history)["completed_at"]
    if prior_completed_at:
        assert state_of(history)["completed_at"] == prior_completed_at
    assert sync.run_once(B, history)["status"] == "complete" and adapter.calls == calls
    with pytest.raises(ValueError, match="replay plan"):
        sync.configure(B, new, True, 60, "history")


@pytest.mark.parametrize("change", ["receipt", "pending_cursor"])
def test_mapping_transition_cannot_accept_unverified_checkpoint(change):
    system, _, state, _ = configured()
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    new = replacement(system)
    plan = sync.transition_preview(A, state, new)
    if change == "receipt":
        b.get(job, "BridgeJob")["activation_receipt"]["checksum"] = "changed"
    else:
        state_of(state)["pending_cursor"] = "changed"
    with pytest.raises(ValueError, match="evidence"):
        sync.transition_mapping(B, state, new, plan["review_token"], "Previously reviewed mapping transition")
    assert state_of(state)["cursor"] is None
