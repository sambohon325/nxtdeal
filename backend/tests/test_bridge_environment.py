import pytest
from core import dealer_bridge as b, bridge_runtime as runtime, bridge_sync as sync
from tests.test_bridge_sync import configured, state_of, FakeConnector, A, B, isolated  # noqa: F401


def test_environment_change_requires_revision_and_collection_review():
    system, mapping, state, connector = configured()
    with pytest.raises(ValueError, match="revision"):
        runtime.bind(system, connector, revision="test-1", objects=["customers"], environment="sandbox")
    runtime.bind(system, connector, revision="test-2", objects=["customers"], environment="sandbox")
    assert runtime.describe(system)["environment"] == "sandbox"
    assert sync.public(state, state_of(state))["availability"]["binding_review_required"]
    with pytest.raises(ValueError, match="reviewed"):
        sync.run_once(A, state)
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    report = b.import_report(A, job)
    assert report["activation_receipt"]["collection_environment"] == "sandbox"
    assert report["receipt_integrity"] == "consistent"


def test_restart_cannot_reuse_reviewed_revision_for_changed_environment():
    system, mapping, state, connector = configured()
    runtime.unbind(system)
    runtime.bind(system, FakeConnector(), revision="test-1", objects=["customers"], environment="production")
    with pytest.raises(ValueError, match="reviewed"):
        sync.run_once(A, state)
    assert sync.public(state, state_of(state))["availability"]["binding_review_required"]
    assert state_of(state)["cursor"] is None


@pytest.mark.parametrize("environment", [None, True, "live", "https://secret.example", {}])
def test_invalid_environment_does_not_replace_binding(environment):
    system, _, _, connector = configured()
    before = runtime.binding(system)
    with pytest.raises(ValueError, match="environment"):
        runtime.bind(system, connector, revision="test-2", objects=["customers"], environment=environment)
    assert runtime.binding(system) is before


def test_unspecified_legacy_configuration_retains_current_behavior():
    system, _, state, _ = configured()
    state_of(state).pop("authorized_environment")
    assert runtime.describe(system)["environment"] == "unspecified"
    assert sync.run_once(A, state)["status"] == "awaiting_review"



def test_prior_health_environment_and_transition_preview_are_explicit():
    from core import bridge_health as health
    from tests.test_bridge_sync_transition import replacement
    system, _, state, connector = configured()
    previous = {"connector_health": {"status": "ready", "binding_revision": "test-1", "binding_environment": "synthetic"}}
    assert not health.public(previous, runtime.describe(system))["current_binding"]
    new_mapping = replacement(system)
    plan = sync.transition_preview(A, state, new_mapping)
    assert plan["binding_environment"] == "unspecified"
    runtime.unbind(system)
    runtime.bind(system, connector, revision="test-1", objects=["customers"], environment="production")
    with pytest.raises(ValueError, match="changed"):
        sync.transition_mapping(B, state, new_mapping, plan["review_token"], "Old environment review must not transfer")



@pytest.mark.parametrize("activate_first", [False, True])
def test_retained_classified_pages_cannot_mix_source_environments(activate_first):
    system, mapping, state, connector = configured()
    runtime.bind(system, connector, revision="synthetic-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    job = sync.run_once(A, state)["job_id"]
    if activate_first:
        b.validate(A, job)
        b.activate(B, job)
    runtime.unbind(system)
    runtime.bind(system, FakeConnector(), revision="production-1", objects=["customers"], environment="production")
    with pytest.raises(ValueError, match="separate system"):
        sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    with pytest.raises(ValueError, match="separate system"):
        sync.run_once(A, state)
    assert state_of(state)["cursor"] is None
    assert b.get(job, "BridgeJob")["collection_environment"] == "synthetic"


def test_cancelled_unactivated_page_allows_reviewed_environment_retry():
    system, mapping, state, connector = configured()
    runtime.bind(system, connector, revision="sandbox-1", objects=["customers"], environment="sandbox")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    job = sync.run_once(A, state)["job_id"]
    b.cancel_import(B, job, "Cancel synthetic sandbox capture")
    replacement = FakeConnector()
    runtime.bind(system, replacement, revision="production-1", objects=["customers"], environment="production")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    assert sync.run_once(A, state)["status"] == "blocked"
    sync.retry(B, state, "Reviewed source environment retry after cancellation")
    new_job = sync.run_once(B, state)["job_id"]
    assert b.get(new_job, "BridgeJob")["collection_environment"] == "production"
    assert b.get(job, "BridgeJob")["status"] == "cancelled"


def test_mapping_transition_cannot_reauthorize_mixed_environment():
    from tests.test_bridge_sync_transition import replacement
    system, mapping, state, connector = configured()
    runtime.bind(system, connector, revision="sandbox-1", objects=["customers"], environment="sandbox")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job)
    b.activate(B, job)
    new_mapping = replacement(system)
    plan = sync.transition_preview(A, state, new_mapping)
    runtime.bind(system, FakeConnector(), revision="production-1", objects=["customers"], environment="production")
    with pytest.raises(ValueError, match="separate system"):
        sync.transition_preview(A, state, new_mapping)
    with pytest.raises(ValueError, match="separate system"):
        sync.transition_mapping(B, state, new_mapping, plan["review_token"], "Previously reviewed sandbox mapping")
    assert state_of(state)["mapping_id"] == mapping
    assert state_of(state)["cursor"] is None
    assert state_of(state)["pending_job_id"] == job


@pytest.mark.parametrize("legacy_marker", [False, True])
def test_empty_page_checkpoint_cannot_transfer_to_production(legacy_marker):
    from core.bridge_contracts import SyncPage
    system, mapping, state, connector = configured()
    runtime.bind(system, connector, revision="sandbox-1", objects=["customers"], environment="sandbox")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    connector.page = SyncPage((), "sandbox-position", True)
    assert sync.run_once(A, state)["status"] == "idle"
    assert state_of(state)["checkpoint_environment"] == "sandbox"
    if legacy_marker:
        state_of(state).pop("checkpoint_environment")
    runtime.bind(system, FakeConnector(), revision="production-1", objects=["customers"], environment="production")
    with pytest.raises(ValueError, match="checkpoint.*separate system"):
        sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)
    assert state_of(state)["cursor"] == "sandbox-position"
    assert state_of(state)["authorized_environment"] == "sandbox"
    sync.configure(A, mapping, False, 60)
    assert state_of(state)["checkpoint_environment"] == "sandbox"
    with pytest.raises(ValueError, match="checkpoint.*separate system"):
        sync.configure(A, mapping, True, 60, reviewed_binding_revision=runtime.binding(system).revision, reviewed_binding_environment=runtime.binding(system).environment)

