import pytest

from core import dealer_bridge as bridge
from core.bridge_readiness import summarize
from tests.test_dealer_bridge import A, API, isolated, setup  # noqa: F401


@pytest.mark.parametrize("paused,mapping,job,bound,expected", [
    (True, "approved", "blocked", True, "paused"),
    (False, "approved", "blocked", True, "resolve_import"),
    (False, "approved", "validated", False, "review_activation"),
    (False, "approved", "staged", False, "validate_import"),
    (False, "proposed", None, False, "review_mapping"),
    (False, "revoked", None, True, "discover_mapping"),
    (False, "approved", None, True, "review_collection"),
    (False, "approved", "activated", False, "review_export"),
])
def test_next_step_uses_facts_not_catalog_or_evidence_claims(paused, mapping, job, bound, expected):
    system = {"id": "s1", "paused": paused, "onboarding": {"everything": "available"}}
    mappings = [{"system_id": "s1", "status": mapping}]
    jobs = [{"system_id": "s1", "status": job}] if job else []
    result = summarize(system, {"status": "bound" if bound else "unavailable"}, mappings, jobs)
    assert result["next_step"] == expected
    assert result["live_access"] is bound


def test_guidance_never_counts_another_systems_imports():
    result = summarize({"id": "s1"}, {}, [{"system_id": "s2", "status": "approved"}], [{"system_id": "s2", "status": "blocked"}])
    assert result["mapping_counts"] == result["import_counts"] == {}
    assert result["next_step"] == "discover_mapping"


def test_system_map_guidance_changes_after_proposal_without_granting_live_access():
    system, mapping = setup(False)
    item = next(item for item in bridge.system_map(API)["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "review_mapping"
    assert not item["readiness"]["live_access"]
    assert bridge.get(mapping, "BridgeMapping")["status"] == "proposed"


@pytest.mark.parametrize("profile,job,expected", [
    ("proposed", None, "review_event_profile"), ("approved", None, "review_event_export"),
    ("approved", "staged", "validate_event_import"), ("approved", "validated", "review_event_activation"),
    ("approved", "blocked", "resolve_event_import"), ("revoked", "cancelled", "discover_mapping"),
])
def test_event_workflow_contributes_scoped_next_steps(profile, job, expected):
    profiles = [{"system_id": "s1", "status": profile}, {"system_id": "other", "status": "proposed"}]
    jobs = [{"system_id": "s1", "status": job}] if job else []
    result = summarize({"id": "s1"}, {}, [], [], profiles, jobs)
    assert result["next_step"] == expected
    assert result["event_profile_counts"] == {profile: 1}
    assert not result["live_access"]


def test_system_map_exposes_event_guidance_without_staged_values():
    from core import bridge_event_profiles as profiles, bridge_event_imports as imports
    from tests.test_bridge_adf_discovery import ADF
    system = bridge.connect(A, "CSV", "Event source")["id"]
    profile = profiles.propose(API, system, "Provider", {"email": {"source": "email", "transform": "lower"}})["id"]
    imports.stage(API, profile, ADF)
    result = bridge.system_map(A)
    item = next(item for item in result["systems"] if item["id"] == system)
    assert item["readiness"]["next_step"] == "validate_event_import"
    assert "private@example.com" not in str(result)


@pytest.mark.parametrize("state,expected", [
    ({"status": "blocked", "last_error_code": "authentication_required"}, "renew_connector_access"),
    ({"status": "blocked", "last_error_code": "source_changed"}, "review_blocked_collection"),
    ({"status": "idle", "availability": {"status": "review_required"}}, "review_collection_configuration"),
    ({"status": "idle", "availability": {"status": "ready"}}, "review_collection"),
])
def test_collection_guidance_uses_scoped_public_state_without_exposing_error_payload(state, expected):
    state.update(system_id="s1", last_error="sensitive-adapter-message")
    other = {"system_id": "other", "status": "blocked", "last_error_code": "authentication_required"}
    result = summarize({"id": "s1"}, {"status": "bound"}, [{"system_id": "s1", "status": "approved"}], [], sync_states=[state, other])
    assert result["next_step"] == expected
    assert result["collection_counts"] == {state["status"]: 1}
    assert "sensitive-adapter-message" not in str(result)


def test_import_review_precedes_access_renewal_because_retained_data_remains_reviewable():
    state = {"system_id": "s1", "status": "blocked", "last_error_code": "authentication_required"}
    result = summarize({"id": "s1"}, {}, [], [{"system_id": "s1", "status": "blocked"}], sync_states=[state])
    assert result["next_step"] == "resolve_import"



@pytest.mark.parametrize("status,expected", [("staged", "validate_import"), ("validated", "review_activation"), ("blocked", "resolve_import")])
def test_retained_import_review_precedes_health_failure(status, expected):
    result = summarize({"id": "s1"}, {"status": "bound"}, [{"system_id": "s1", "status": "approved"}],
                       [{"system_id": "s1", "status": status}],
                       connector_health={"status": "authentication_required", "current_binding": True})
    assert result["next_step"] == expected
