from copy import deepcopy
import pytest
from core import dealer_bridge as b, bridge_activity as activity
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, CSV, setup, imported, isolated  # noqa: F401


def test_scoped_activity_paginates_without_values_or_mutations(monkeypatch):
    system, mapping = setup()
    job = imported(mapping=mapping)
    other, other_mapping = setup()
    b.stage(A, other_mapping, CSV)
    before = deepcopy(ledger.entities)
    def fail(path):
        raise AssertionError("Read-only activity must not save")
    monkeypatch.setattr(b, "save_graph", fail)
    result = activity.read(API, system, 2)
    actions = list(result["activities"])
    while result["next_before_id"]:
        result = activity.read(API, system, 2, result["next_before_id"])
        actions.extend(result["activities"])
    assert len(actions) == len({row["id"] for row in actions}) == result["total_activities"]
    assert {row["action"] for row in actions} >= {"system.discover", "mapping.propose", "mapping.approve", "import.stage", "import.validate", "import.activate"}
    assert all(row["record_id"] in {system, mapping, job} for row in actions)
    assert next(row for row in actions if row["action"] == "import.activate")["principal"] == "session"
    assert "ada@example.com" not in str(actions) and ledger.entities == before
    with pytest.raises(ValueError):
        activity.read(A, other, before_id=actions[0]["id"])


def test_typed_parent_resolution_and_foreign_records_are_excluded():
    system, mapping = setup()
    job = imported(mapping=mapping)
    with b.mutation(A):
        review = b.add("BridgeIdentityReview", {"job_id": job, "reason": "private decision details"})
        b.audit(A, "identity.review.link", review)
        wrong = b.add("BridgeIdentityReview", {"job_id": mapping})
        b.audit(A, "identity.review.link", wrong)
        foreign = b.add("BridgeIdentityReview", {"job_id": job})
        b.get(foreign, "BridgeIdentityReview")["workspace_id"] = "other"
        b.audit(A, "identity.review.link", foreign)
        b.audit(A, "unknown.target", "missing")
        b.audit(A, "global.policy", "BRIDGE-CHRONO-POLICY")
    result = activity.read(A, system)
    targets = {row["record_id"] for row in result["activities"]}
    assert review in targets and wrong not in targets and foreign not in targets
    assert "private decision details" not in str(result)


def test_legacy_principal_is_not_inferred_and_auth_is_required():
    system, _ = setup()
    audit = next(e for e in ledger.get_all().values() if e.entity_type == "BridgeAudit")
    audit.attributes.pop("principal")
    assert next(row for row in activity.read(A, system)["activities"] if row["id"] == audit.id)["principal"] is None
    with pytest.raises(PermissionError):
        activity.read({**A, "role": "SALES"}, system)
    with pytest.raises(PermissionError):
        activity.read({**A, "workspace_id": "other"}, system)
    for limit in [True, 0, 101]:
        with pytest.raises(ValueError):
            activity.read(A, system, limit)


def test_recovery_and_event_profile_actions_resolve_to_source():
    from core import bridge_event_profiles as profiles, bridge_event_imports as events
    from tests.test_bridge_adf_discovery import ADF
    system, _ = setup()
    profile = profiles.propose(API, system, "Provider", {"email": {"source": "email", "transform": "lower"}})["id"]
    profiles.approve(B, profile)
    job = events.stage(A, profile, ADF)["id"]
    events.cancel(B, job, "Synthetic activity verification")
    with b.mutation(A):
        state = b.add("BridgeSyncState", {"system_id": system})
        recovery = b.add("BridgeSyncRecovery", {"state_id": state})
        b.audit(B, "sync.replay_reviewed", recovery)
    actions = {row["action"] for row in activity.read(A, system)["activities"]}
    assert {"event_profile.propose", "event_profile.approve", "event_import.stage", "event_import.cancel", "sync.replay_reviewed"} <= actions



def test_activity_route_preserves_admin_and_page_bounds():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers.dealer_bridge import admin, router
    system, _ = setup()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{system}/activity"
    assert client.get(path).status_code == 200
    assert client.get(path + "?limit=101").status_code == 400
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "foreign"}
    assert client.get(path).status_code == 403
