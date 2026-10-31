from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import sales_crm as crm
from staff_auth_fixture import staff_token
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship


def headers(role="SALES", employee="EMP-1"):
    return {"Authorization": "Bearer " + staff_token(employee, role)}


@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    app = FastAPI()
    app.include_router(crm.router)
    with TestClient(app) as client:
        yield client
    ledger.reset()


def seed():
    for entity in [Entity("EMP-1", "Employee", {"FirstName": "Test", "LastName": "Rep"}),
                   Entity("EMP-2", "Employee", {"Name": "Other Rep"}),
                   Entity("LEAD-1", "Lead", {"FirstName": "Alex", "LastName": "Example", "Source": "Website", "PipelineState": "NEW", "AssignedSalesperson": "EMP-2", "CreatedDate": "2026-01-01", "SSN": "NEVER-RETURN"}),
                   Entity("LEAD-2", "Lead", {"Name": "Blair Example", "Source": "Walk-In", "PipelineState": "VISITED", "CreatedDate": "2026-02-01"}),
                   Entity("CUST-1", "Customer", {"Name": "Customer Example", "CreditScore": 799}),
                   Entity("VEH-1", "Vehicle", {"Year": 2026, "Make": "Example", "Model": "Touring", "VIN": "TESTVIN123"}),
                   Entity("LTASK-1", "LeadTask", {"lead_id": "LEAD-1", "completed": False, "due_at": "2000-01-01T12:00:00-06:00"}),
                   Entity("LTASK-2", "LeadTask", {"lead_id": "LEAD-1", "completed": True, "due_at": "2000-01-01"}),
                   Entity("LTASK-3", "LeadTask", {"lead_id": "LEAD-1", "completed": False, "due_at": "invalid"})]:
        ledger.add_entity(entity)
    ledger.add_relationship(Relationship("EMP-2", "LEAD-1", "ASSIGNED_TO"))
    ledger.add_relationship(Relationship("EMP-1", "LEAD-1", "ASSIGNED_TO"))
    ledger.add_relationship(Relationship("LEAD-1", "VEH-1", "INTERESTED_IN"))


def test_access_and_allowlisted_projection(client):
    seed()
    assert client.get("/sales/crm/records").status_code == 401
    for role in ["CUSTOMER", "SERVICE", "FINANCE"]:
        assert client.get("/sales/crm/records", headers=headers(role)).status_code == 403
    response = client.get("/sales/crm/records", headers=headers())
    assert response.status_code == 200
    assert "NEVER-RETURN" not in response.text
    rows = response.json()["records"]
    alex = next(r for r in rows if r["id"] == "LEAD-1")
    assert alex["owner_id"] == "EMP-1"  # latest canonical relationship beats stale attribute
    assert alex["owner_name"] == "Test Rep"
    assert alex["vehicles"][0]["label"] == "2026 Example Touring"
    assert alex["open_tasks"] == 2 and alex["overdue_tasks"] == 1
    customers = client.get("/sales/crm/records?kind=Customer", headers=headers()).json()
    assert customers["total"] == 1 and "CreditScore" not in str(customers)


def test_filters_pagination_and_read_does_not_mutate(client):
    seed()
    before = deepcopy(ledger.entities)
    def query(params):
        return client.get("/sales/crm/records", params=params, headers=headers()).json()
    assert query({"owner": "mine"})["records"][0]["id"] == "LEAD-1"
    assert query({"owner": "unassigned"})["records"][0]["id"] == "LEAD-2"
    assert query({"q": "testvin123"})["total"] == 1
    assert query({"overdue": True})["total"] == 1
    assert query({"stage": "VISITED", "source": "Website"})["total"] == 0
    page = query({"limit": 1})
    assert page["total"] == 2 and page["records"][0]["id"] == "LEAD-2"
    assert query({"limit": 1, "offset": 1})["records"][0]["id"] == "LEAD-1"
    assert query({"offset": 10})["records"] == []
    assert ledger.entities == before


def test_personal_saved_views_persist_and_do_not_cross_employees(client):
    body = {"name": "My internet leads", "owner": "mine", "source": "Website", "layout": "board"}
    response = client.post("/sales/crm/views", headers=headers(), json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert client.get("/sales/crm/views", headers=headers(employee="EMP-2")).json() == []
    assert client.post("/sales/crm/views", headers=headers(), json=body).status_code == 409
    ledger.reset()
    assert ledger.load(crm.GRAPH_PATH)
    assert client.get("/sales/crm/views", headers=headers()).json() == [saved]
    assert client.post("/sales/crm/views", headers=headers("CUSTOMER"), json=body).status_code == 403


@pytest.mark.parametrize("params", [{"limit": 101}, {"offset": -1}, {"kind": "FinanceContract"}, {"sort": "secret"}])
def test_invalid_query_is_rejected(client, params):
    assert client.get("/sales/crm/records", headers=headers(), params=params).status_code == 422


@pytest.mark.parametrize("body", [{"name": " "}, {"name": "x", "employee_id": "EMP-2"}, {"name": "x", "layout": "invalid"}])
def test_invalid_view_is_rejected(client, body):
    assert client.post("/sales/crm/views", headers=headers(), json=body).status_code == 422


def test_accounts_use_existing_contacts_and_guard_stale_edits(client):
    seed()
    body = {"name": "Example family", "account_type": "household", "member_ids": ["LEAD-1", "CUST-1"]}
    assert client.post("/sales/crm/accounts", headers=headers("CUSTOMER"), json=body).status_code == 403
    for ids in [["VEH-1"], ["missing"], ["LEAD-1", "LEAD-1"]]:
        assert client.post("/sales/crm/accounts", headers=headers(), json={**body, "member_ids": ids}).status_code == 422
    saved = client.post("/sales/crm/accounts", headers=headers(), json=body).json()
    assert len(saved["members"]) == 2
    updated = client.put("/sales/crm/accounts/" + saved["id"], headers=headers(), json={**body, "revision": 1, "name": "Updated family"})
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert client.put("/sales/crm/accounts/" + saved["id"], headers=headers(), json={**body, "revision": 1}).status_code == 409
    ledger.reset()
    assert ledger.load(crm.GRAPH_PATH)
    loaded = client.get("/sales/crm/accounts", headers=headers()).json()[0]
    assert loaded["name"] == "Updated family" and loaded["revision"] == 2
    assert ledger.get_entity("LEAD-1").attributes["FirstName"] == "Alex"


def test_contact_date_uses_actual_logged_communication(client):
    seed()
    ledger.add_entity(Entity("NOTE-1", "FieldNote", {"linked_entity_id": "LEAD-1", "category": "call", "created_at": "2026-04-01T12:00:00Z", "body": "Private call notes"}))
    ledger.add_entity(Entity("NOTE-2", "FieldNote", {"linked_entity_id": "LEAD-1", "category": "general", "created_at": "2026-05-01T12:00:00Z"}))
    response = client.get("/sales/crm/records?q=Alex", headers=headers())
    assert response.json()["records"][0]["last_contact"] == "2026-04-01T12:00:00Z"
    assert "Private call notes" not in response.text


def test_task_queue_names_scopes_and_invalid_dates(client):
    seed()
    ledger.get_entity("LTASK-1").attributes["assigned_to"] = "EMP-1"
    mine = client.get("/sales/crm/tasks", headers=headers()).json()
    assert len(mine) == 1
    assert mine[0]["lead_name"] == "Alex Example" and mine[0]["owner_name"] == "Test Rep"
    assert len(client.get("/sales/crm/tasks?scope=all", headers=headers()).json()) == 2
    assert len(client.get("/sales/crm/tasks?scope=overdue", headers=headers()).json()) == 1
    assert len(client.get("/sales/crm/tasks?scope=completed", headers=headers()).json()) == 1
    assert client.get("/sales/crm/tasks", headers=headers("CUSTOMER")).status_code == 403
