from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import marketing_journeys as journeys
from staff_auth_fixture import staff_token
from core.dealeros import ledger
from core.entities import Entity


@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    app = FastAPI()
    app.include_router(journeys.router)
    with TestClient(app) as client:
        yield client
    ledger.reset()


def headers(role="MARKETING"):
    return {"Authorization": "Bearer " + staff_token("TEST-MARKETER", role)}


def plan():
    return {"name": "Service reminder", "objective": "service_retention", "trigger_type": "service_due", "steps": [{"type": "email", "label": "Reminder", "delay_minutes": 0}, {"type": "wait", "label": "Wait", "delay_minutes": 1440}]}


def create(client):
    response = client.post("/marketing/journeys", headers=headers(), json=plan())
    assert response.status_code == 200, response.text
    return response.json()


def test_roles_and_unauthenticated_access(client):
    assert client.get("/marketing/journeys").status_code == 401
    assert client.post("/marketing/journeys", headers=headers("SALES"), json=plan()).status_code == 403
    assert client.get("/marketing/journeys", headers=headers("SALES")).status_code == 200
    assert client.get("/marketing/journeys", headers=headers("CUSTOMER")).status_code == 403
    saved = create(client)
    for path, method, body in [(saved["id"], "put", {**plan(), "revision": 1}), (saved["id"] + "/status", "post", {"revision": 1, "status": "ready"})]:
        assert getattr(client, method)("/marketing/journeys/" + path, headers=headers("SALES"), json=body).status_code == 403


def test_persist_reload_and_read_has_no_side_effects(client):
    saved = create(client)
    assert saved["status"] == "draft" and saved["execution_enabled"] is False
    before = deepcopy(ledger.entities)
    client.get("/marketing/journeys", headers=headers())
    assert ledger.entities == before
    ledger.reset()
    assert ledger.load(journeys.GRAPH_PATH)
    loaded = client.get("/marketing/journeys", headers=headers()).json()["journeys"][0]
    assert loaded == saved
    assert {e.entity_type for e in ledger.get_all().values()} == {journeys.ENTITY_TYPE}


def test_reordering_revision_conflict_and_edit_resets_ready(client):
    saved = create(client)
    url = "/marketing/journeys/" + saved["id"]
    assert client.post(url + "/status", headers=headers(), json={"revision": 1, "status": "ready"}).json()["status"] == "ready"
    edit = {**plan(), "revision": 1}
    edit["steps"].reverse()
    assert client.put(url, headers=headers(), json=edit).status_code == 409
    edit["revision"] = 2
    response = client.put(url, headers=headers(), json=edit).json()
    assert response["status"] == "draft" and response["revision"] == 3
    assert response["steps"][0]["type"] == "wait"
    assert [h["revision"] for h in response["history"]] == [1, 2, 3]


def test_archive_restore_and_name_collision(client):
    saved = create(client)
    url = "/marketing/journeys/" + saved["id"]
    assert client.post("/marketing/journeys", headers=headers(), json=plan()).status_code == 409
    assert client.post(url + "/status", headers=headers(), json={"revision": 1, "status": "archived"}).status_code == 200
    assert client.put(url, headers=headers(), json={**plan(), "revision": 2}).status_code == 409
    assert client.post(url + "/status", headers=headers(), json={"revision": 2, "status": "ready"}).status_code == 409
    assert client.post(url + "/status", headers=headers(), json={"revision": 2, "status": "draft"}).json()["revision"] == 3


@pytest.mark.parametrize("patch", [{"name": "   "}, {"steps": []}, {"trigger_type": "invented"}, {"steps": [{"type": "wait", "label": "Wait", "delay_minutes": -1}]}, {"steps": [{"type": "wait", "label": "Wait", "delay_minutes": 0.5}]}, {"steps": [{"type": "email", "label": "Email", "content_asset_id": "CUST-1"}]}])
def test_invalid_plans_do_not_mutate(client, patch):
    ledger.add_entity(Entity("CUST-1", "Customer", {}))
    before = deepcopy(ledger.entities)
    assert client.post("/marketing/journeys", headers=headers(), json={**plan(), **patch}).status_code == 422
    assert ledger.entities == before


def test_ready_requires_message_and_never_creates_delivery(client):
    data = plan()
    data["steps"] = [{"type": "wait", "label": "Wait", "delay_minutes": 5}]
    saved = client.post("/marketing/journeys", headers=headers(), json=data).json()
    assert client.post(f'/marketing/journeys/{saved["id"]}/status', headers=headers(), json={"revision": 1, "status": "ready"}).status_code == 422
    assert len(ledger.get_all()) == 1


def test_saved_email_and_audience_links_persist_without_copying_contacts(client):
    ledger.add_entity(Entity("EMAIL-QA", "EmailTemplate", {"channel": "email", "subject": "Synthetic"}))
    ledger.add_entity(Entity("LIST-QA", "MarketingList", {"name": "Synthetic", "member_ids": []}))
    data = plan()
    data["audience_list_id"] = "LIST-QA"
    data["steps"][0]["email_template_id"] = "EMAIL-QA"
    saved = client.post("/marketing/journeys", headers=headers(), json=data)
    assert saved.status_code == 200
    assert saved.json()["steps"][0]["email_template_id"] == "EMAIL-QA"
    ledger.reset()
    assert ledger.load(journeys.GRAPH_PATH)
    result = client.get("/marketing/journeys", headers=headers()).json()["journeys"][0]
    assert result["audience_list_id"] == "LIST-QA"
    assert len(ledger.get_all()) == 3


@pytest.mark.parametrize("kind", ["missing_email", "sms_template", "archived_list", "wrong_entity"])
def test_invalid_linked_records_reject_without_saving(client, kind):
    data = plan()
    if kind == "archived_list":
        ledger.add_entity(Entity("LIST-QA", "MarketingList", {"archived": True}))
        data["audience_list_id"] = "LIST-QA"
    else:
        if kind != "missing_email":
            ledger.add_entity(Entity("EMAIL-QA", "Customer" if kind == "wrong_entity" else "EmailTemplate", {"channel": "sms"}))
        data["steps"][0]["email_template_id"] = "EMAIL-QA"
    before = deepcopy(ledger.entities)
    assert client.post("/marketing/journeys", headers=headers(), json=data).status_code == 422
    assert ledger.entities == before


def test_failed_persistence_rolls_back(client, monkeypatch):
    saved = create(client)
    before = deepcopy(ledger.entities)
    def fail(_):
        raise OSError("Test disk full")
    monkeypatch.setattr(journeys, "save_graph", fail)
    with pytest.raises(OSError):
        client.put(f'/marketing/journeys/{saved["id"]}', headers=headers(), json={**plan(), "name": "Changed", "revision": 1})
    assert ledger.entities == before
    with pytest.raises(OSError):
        client.post("/marketing/journeys", headers=headers(), json={**plan(), "name": "New"})
    assert ledger.entities == before
