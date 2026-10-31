from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import admin, router
from core import bridge_event_profiles as profiles, dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated, setup  # noqa: F401
from tests.test_bridge_adf_discovery import ADF

FIELDS = {"first_name": {"source": "name_full", "transform": "text"}, "email": {"source": "email", "transform": "lower"}}


def proposed():
    system, _ = setup()
    return system, profiles.propose(API, system, "Provider", FIELDS)["id"]


def snapshot():
    return {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}


def test_agent_can_propose_simulate_but_not_approve_and_no_records_are_imported():
    system, profile = proposed()
    before = snapshot()
    result = profiles.simulate(API, profile, ADF)
    assert snapshot() == before
    assert result["rows"][0]["time_semantics"] == "created"
    assert result["rows"][0]["occurred_at"] == "2026-10-04T15:00:00+00:00"
    assert result["rows"][0]["values"]["first_name"] == "Private Name"
    assert result["stored"] is result["activation_available"] is False
    with pytest.raises(PermissionError): profiles.approve(API, profile)
    with pytest.raises(PermissionError): profiles.approve(A, profile)
    profiles.approve(B, profile)
    assert profiles.approve(B, profile)["idempotent"]
    assert profiles.list_profiles(A, system)[0]["status"] == "approved"
    assert not any(e.entity_type in {"Lead", "SourceObservation", "BridgeJob"} for e in ledger.entities.values())


@pytest.mark.parametrize("field,value", [("id_source", "Other"), ("time_semantics", "modified"), ("projection", "update"), ("transform_version", 1)])
def test_approved_profile_cannot_change_semantics(field, value):
    _, profile = proposed()
    profiles.approve(B, profile)
    bridge.get(profile, "BridgeEventProfile")[field] = value
    with pytest.raises(ValueError, match="changed"):
        profiles.simulate(A, profile, ADF)


def test_revocation_and_workspace_boundaries():
    system, profile = proposed()
    with pytest.raises(PermissionError): profiles.list_profiles({**A, "workspace_id": "other"}, system)
    with pytest.raises(PermissionError): profiles.revoke(API, profile, "Stop this event profile")
    profiles.revoke(B, profile, "Stop this event profile")
    with pytest.raises(ValueError, match="revoked"): profiles.approve(B, profile)
    with pytest.raises(ValueError, match="revoked"): profiles.simulate(A, profile, ADF)


def test_profile_approval_save_failure_rolls_back(monkeypatch):
    _, profile = proposed()
    before = snapshot()
    def fail(_): raise OSError("synthetic failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError): profiles.approve(B, profile)
    assert snapshot() == before


def test_conflicting_event_values_are_quarantined_and_never_saved():
    _, profile = proposed()
    content = ADF.replace('</adf>', '') + ADF.replace('<adf>', '').replace('Private Name', 'Changed Name')
    before = snapshot()
    result = profiles.simulate(API, profile, content)
    assert [row["status"] for row in result["rows"]] == ["ready", "quarantined"]
    assert snapshot() == before


def test_api_profile_approval_and_strict_payloads():
    system, _ = setup()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    body = {"system_id": system, "id_source": "Provider", "fields": FIELDS}
    profile = client.post('/dealer-bridge/event-profiles', json=body).json()["id"]
    assert client.post(f'/dealer-bridge/event-profiles/{profile}/approve').status_code == 403
    assert client.post(f'/dealer-bridge/event-profiles/{profile}/test', json={"content": ADF}).status_code == 200
    assert client.post('/dealer-bridge/event-profiles', json={**body, "time_semantics": "modified"}).status_code == 422
    app.dependency_overrides[admin] = lambda: B
    assert client.post(f'/dealer-bridge/event-profiles/{profile}/approve').status_code == 200
