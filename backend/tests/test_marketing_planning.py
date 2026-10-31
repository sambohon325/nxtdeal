from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import marketing_planning as planning
from core.dealeros import ledger
from core.entities import Entity
from staff_auth_fixture import staff_token

@pytest.fixture
def client():
    ledger.reset()
    app = FastAPI()
    app.include_router(planning.router)
    with TestClient(app) as client:
        yield client
    ledger.reset()

def headers(role="MARKETING"):
    return {"Authorization": "Bearer " + staff_token("TEST-MARKETER", role)}

def brief(**patch):
    return {"name":"Service week", "objective":"Fill available appointments", "department":"Service", "starts_on":"2026-11-01", "ends_on":"2026-11-07", "budget":500, "currency":"USD", "target_appointments":12, "next_step":"Confirm the requested time with Service", **patch}

def test_save_reload_without_creating_customer_or_task(client):
    result = client.post("/marketing/planning", headers=headers(), json=brief())
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["capacity_review"] == "unknown"
    assert saved["execution_enabled"] is False
    ledger.reset()
    assert ledger.load(planning.ops.GRAPH_PATH)
    assert client.get("/marketing/planning",headers=headers()).json()["briefs"] == [saved]
    assert {e.entity_type for e in ledger.get_all().values()} == {planning.KIND}

@pytest.mark.parametrize("patch", [{"ends_on":"2026-10-01"},{"budget":-1},{"target_appointments":-1},{"confirmed_capacity":5},{"response_minutes":0},{"objective":" "}])
def test_invalid_brief_does_not_persist(client,patch):
    assert client.post("/marketing/planning",headers=headers(),json=brief(**patch)).status_code == 422
    assert planning.ops.all_of(planning.KIND) == []

def test_capacity_and_optimistic_edit(client):
    saved=client.post("/marketing/planning",headers=headers(),json=brief(confirmed_capacity=4,capacity_evidence="Service manager checked November 1 schedule")).json()
    assert saved["capacity_review"] == "shortfall"
    url="/marketing/planning/"+saved["id"]
    payload=brief(revision=1,confirmed_capacity=12,capacity_evidence="Manager rechecked available slots")
    changed=client.put(url,headers=headers(),json=payload).json()
    assert changed["revision"] == 2
    assert changed["capacity_review"] == "recorded_capacity_covers_target"
    assert len(changed["history"]) == 2
    assert client.put(url,headers=headers(),json=payload).status_code == 409

def test_permissions_and_shared_references(client):
    assert client.get("/marketing/planning").status_code == 401
    assert client.post("/marketing/planning",headers=headers("SALES"),json=brief()).status_code == 403
    assert client.get("/marketing/planning",headers=headers("SERVICE")).status_code == 200
    ledger.add_entity(Entity("SEG-PRIVATE","SalesCrmSegment",{"name":"Private", "shared":False}))
    choices=client.get("/marketing/planning",headers=headers()).json()["choices"]
    assert choices["audiences"] == []
    assert client.post("/marketing/planning",headers=headers(),json=brief(audience_id="SEG-PRIVATE")).status_code == 422
    assert client.post("/marketing/planning",headers=headers(),json=brief(campaign_id="MISSING")).status_code == 422

def test_failed_edit_restores_previous_record(client,monkeypatch):
    saved=client.post("/marketing/planning",headers=headers(),json=brief()).json()
    before=deepcopy(ledger.get_entity(saved["id"]).attributes)
    def fail(*args): raise OSError("disk unavailable")
    monkeypatch.setattr(planning.ops,"save_graph",fail)
    with pytest.raises(OSError):
        client.put("/marketing/planning/"+saved["id"],headers=headers(),json=brief(revision=1,name="Changed"))
    assert ledger.get_entity(saved["id"]).attributes == before
