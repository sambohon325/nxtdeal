"""Discoverable provider-neutral tools describe existing proposal/test APIs only."""
from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import router, admin, Mapping, MappingTest, EventProfile
from core import dealer_bridge as b
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated, setup  # noqa: F401
from tests.test_bridge_adf_discovery import ADF


def client(actor=API):
    app = FastAPI()
    app.include_router(router)
    if actor is not None: app.dependency_overrides[admin] = lambda: actor
    return TestClient(app)


def test_contract_is_authenticated_scoped_read_only_and_uses_real_request_schemas():
    setup()
    before = deepcopy(ledger.entities)
    assert client(None).get("/dealer-bridge/agent-contract").status_code == 401
    assert client({**API,"workspace_id":"foreign"}).get("/dealer-bridge/agent-contract").status_code == 403
    response = client().get("/dealer-bridge/agent-contract")
    assert response.status_code == 200
    contract = response.json()
    assert contract["provider_neutral"] and contract["version"] == 1
    assert ledger.entities == before
    operations = {entry["name"]:entry for entry in contract["operations"]}
    assert operations["propose_snapshot_mapping"]["body_schema"] == Mapping.model_json_schema()
    assert operations["test_snapshot_mapping"]["body_schema"] == MappingTest.model_json_schema()
    assert operations["propose_event_profile"]["body_schema"] == EventProfile.model_json_schema()
    paths = {(route.path,method) for route in router.routes for method in getattr(route,"methods",[])}
    for operation in operations.values():
        assert (operation["path"],operation["method"]) in paths
        assert not operation["external_io"]
        assert operation["effect"] in {"read_only","simulation_only","proposal_only"}
        assert not any(part in operation["path"] for part in ["/approve","/activate","/policy","/write","/sync","/identity"])
        if operation["body_schema"]:
            assert operation["body_schema"]["additionalProperties"] is False
    assert contract["boundaries"]["external_write_execution"] == "unavailable"
    assert contract["boundaries"]["automatic_tool_registration"] is False


def test_agent_uses_discovered_snapshot_proposal_and_test_without_approval_or_import():
    system, _ = setup()
    api = client()
    operations = {entry["name"]:entry for entry in api.get("/dealer-bridge/agent-contract").json()["operations"]}
    proposed = api.post(operations["propose_snapshot_mapping"]["path"],json={
        "system_id":system, "kind":"Customer", "object_type":"agent_contacts",
        "fields":{"first_name":{"source":"name","transform":"text"}}})
    assert proposed.status_code == 200
    mapping_id = proposed.json()["id"]
    before = deepcopy(ledger.entities)
    tested = api.post(operations["test_snapshot_mapping"]["path"].format(mapping_id=mapping_id),json={
        "file_format":"json", "content":'[{"external_id":"agent-c1","modified_at":"2026-10-04T12:00:00Z","name":"Synthetic agent test"}]'})
    assert tested.status_code == 200 and tested.json()["stored"] is False
    assert tested.json()["rows"][0]["status"] == "ready"
    assert ledger.entities == before
    assert b.get(mapping_id,"BridgeMapping")["status"] == "proposed"
    assert api.post(f"/dealer-bridge/mappings/{mapping_id}/approve",json={}).status_code == 403


def test_event_profile_tool_preserves_creation_semantics_and_human_gate():
    system, _ = setup()
    api = client()
    operations = {entry["name"]:entry for entry in api.get("/dealer-bridge/agent-contract").json()["operations"]}
    proposed = api.post(operations["propose_event_profile"]["path"],json={"system_id":system,"id_source":"Provider",
        "fields":{"first_name":{"source":"name_full","transform":"text"}}})
    assert proposed.status_code == 200
    profile_id = proposed.json()["id"]
    before = deepcopy(ledger.entities)
    tested = api.post(operations["test_event_profile"]["path"].format(profile_id=profile_id),json={"content":ADF})
    assert tested.status_code == 200 and tested.json()["stored"] is False
    assert tested.json()["rows"][0]["time_semantics"] == "created"
    assert ledger.entities == before
    assert api.post(f"/dealer-bridge/event-profiles/{profile_id}/approve",json={}).status_code == 403
