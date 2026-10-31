import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_agent_fabric import isolate, SALES, ADMIN, MARKETING, propose
from core import agent_fabric as f
from core import agent_events
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from api.routers.agent_fabric import router, employee
from api.routers.agent_mcp import router as mcp_router, mcp_employee


def approved(capability, data, department="sales", actor=SALES):
    item = f.invoke(actor, department, capability, data, "api", capability)
    f.approve(ADMIN, item["id"])
    return f.execute(actor, item["id"])


def test_native_campaign_is_a_draft_without_simulated_sends():
    result = approved("campaign.create", {"name": "Aged inventory", "make": "Honda"}, "marketing", MARKETING)
    campaign = ledger.get_entity(result["result"]["campaign_id"])
    assert campaign.attributes["status"] == "draft"
    assert campaign.attributes["sent_count"] == 0


def test_native_appointment_links_the_existing_lead():
    result = approved("appointment.create", {"lead_id": "lead-1", "scheduled_start": "2026-10-10T12:00:00-05:00"})
    appointment = ledger.get_entity(result["result"]["appointment_id"])
    assert appointment.attributes["lead_id"] == "lead-1"


def test_native_workflow_transition_uses_existing_state_machine():
    ledger.get_entity("lead-1").attributes["PipelineState"] = "NEW"
    result = approved("lead.update", {"lead_id": "lead-1", "next_state": "CONTACTED"})
    assert result["result"]["state"] == "CONTACTED"
    assert ledger.get_entity("lead-1").attributes["PipelineState"] == "CONTACTED"


def test_action_is_revalidated_if_lead_changes_after_approval():
    lead = ledger.get_entity("lead-1")
    lead.attributes["PipelineState"] = "NEW"
    item = f.invoke(SALES, "sales", "lead.update", {"lead_id": "lead-1", "next_state": "CONTACTED"}, "api", "change")
    f.approve(ADMIN, item["id"])
    lead.attributes["PipelineState"] = "SOLD"
    with pytest.raises(ValueError):
        f.execute(SALES, item["id"])


def test_sms_requires_live_adapter_and_current_consent(monkeypatch):
    from core import integrations_registry as integrations
    monkeypatch.setattr(integrations, "_ADAPTERS", {})
    ledger.add_entity(Entity("customer-1", "Customer", {"Phone": "+15555550100", "consent": {"sms": True}}))
    assert not f.available("sms.send")
    calls = []
    def send(to, event, channels):
        calls.append(event)
        return {"simulated": False, "status": "accepted"}
    integrations.register_adapter("notifications", send)
    item = f.invoke(SALES, "sales", "sms.send", {"customer_id": "customer-1", "body": "Follow-up"}, "api", "sms")
    f.approve(ADMIN, item["id"])
    ledger.get_entity("customer-1").attributes["consent"]["sms"] = False
    with pytest.raises(PermissionError):
        f.execute(SALES, item["id"])
    assert calls == []
    ledger.get_entity("customer-1").attributes["consent"]["sms"] = True
    assert f.execute(SALES, item["id"])["result"]["status"] == "accepted"
    assert calls[0]["idempotency_key"] == item["id"]
    f.execute(SALES, item["id"])
    assert len(calls) == 1


def test_timeline_uses_explicit_relationships_without_sensitive_fields():
    ledger.add_entity(Entity("customer-1", "Customer", {"FirstName": "Test", "SSN": "private"}))
    ledger.add_entity(Entity("finance-1", "FinanceContract", {"bank_account": "private"}))
    ledger.add_relationship(Relationship("customer-1", "lead-1", "HAS_LEAD"))
    ledger.add_relationship(Relationship("customer-1", "finance-1", "FINANCED_BY"))
    result = f.invoke(SALES, "sales", "customer.timeline.read", {"record_id": "customer-1"})
    assert result["source_records"] == ["customer-1", "lead-1"]
    assert "private" not in str(result)
    assert result["events"][0]["evidence_kind"] == "observed"


def test_projection_maps_actual_legacy_fields():
    ledger.add_entity(Entity("vehicle-1", "Vehicle", {"Make": "Honda", "Model": "Civic", "Year": "2024", "VIN": "private"}))
    result = f.invoke(SALES, "sales", "inventory.read", {"record_id": "vehicle-1"})
    assert result["records"][0]["attributes"]["make"] == "Honda"
    assert "VIN" not in str(result)


def test_background_worker_prepares_only_once_and_rechecks_current_role(monkeypatch):
    from core.auth import credential_store
    monkeypatch.setattr(credential_store, "get_record", lambda employee_id: {"role": "SALES"})
    agent_events.subscribe(SALES, "sales.stale_lead_recovery", True)
    assert agent_events.tick()["processed"] == 1
    assert agent_events.tick()["processed"] == 0
    items = f.proposals(SALES)
    assert len(items) == 1 and items[0]["status"] == "proposed"
    assert not any(e.entity_type == "LeadTask" for e in ledger.get_all().values())


def test_background_worker_cannot_use_revoked_role(monkeypatch):
    from core.auth import credential_store
    agent_events.subscribe(SALES, "sales.stale_lead_recovery", True)
    monkeypatch.setattr(credential_store, "get_record", lambda employee_id: {"role": "MARKETING"})
    agent_events.tick()
    assert f.proposals(SALES) == []
    assert agent_events.receipts(ADMIN)[0]["status"] == "blocked"


def mcp_client():
    app = FastAPI()
    app.include_router(router)
    app.include_router(mcp_router)
    app.dependency_overrides[employee] = lambda: SALES
    app.dependency_overrides[mcp_employee] = lambda: SALES
    return TestClient(app)


HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def test_mcp_initialize_discover_and_propose_follow_same_gateway():
    client = mcp_client()
    response = client.post("/agent-fabric/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert response.json()["result"]["protocolVersion"] == "2025-06-18"
    tools = client.post("/agent-fabric/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()
    assert len(tools["result"]["tools"]) == 3
    result = client.post("/agent-fabric/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nxtdeal_invoke", "arguments": {"department": "sales", "capability": "task.create", "input": {"lead_id": "lead-1", "description": "Test"}, "idempotency_key": "mcp"}}}).json()
    assert result["result"]["isError"] is False
    assert f.proposals(SALES)[0]["status"] == "proposed"


def test_mcp_origin_and_protocol_rejected():
    client = mcp_client()
    assert client.get("/agent-fabric/mcp", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/agent-fabric/mcp", headers={"Origin": "https://dealer1.dealeros.xyz"}).status_code == 403
    assert client.get("/agent-fabric/mcp").status_code == 405
    assert client.post("/agent-fabric/mcp", headers={**HEADERS, "MCP-Protocol-Version": "bad"}, json={}).status_code == 400
    assert client.post("/agent-fabric/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202


def test_mcp_cannot_approve_or_escalate_roles():
    client = mcp_client()
    result = client.post("/agent-fabric/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nxtdeal_invoke", "arguments": {"department": "gm", "capability": "analytics.read"}}}).json()
    assert result["result"]["isError"] is True


def test_csv_bridge_retains_provenance_on_real_import():
    from core.data_connections import create_connection, ingest_csv
    connection = create_connection("Test CSV", "csv", "sales", "admin-1")["connection"]
    result = ingest_csv(connection["id"], "inventory.csv", b"VIN,Year,Make,Model\nFABRICTESTVIN12345,2024,Honda,Civic\n")
    assert result["records_created"] == 1
    observations = [e for e in ledger.get_all().values() if e.entity_type == "SourceObservation"]
    assert observations[0].attributes["source_id"] == "FABRICTESTVIN12345"
    assert observations[0].attributes["source_timestamp"] is None


def test_api_credentials_cannot_approve_or_change_policy():
    item = propose()
    actor = {**ADMIN, "principal": "api"}
    with pytest.raises(PermissionError):
        f.approve(actor, item["id"])
    with pytest.raises(PermissionError):
        f.set_policy(actor, f.policy())


def test_failed_approval_persistence_cannot_enable_execution(monkeypatch):
    item = propose()
    def fail():
        raise OSError("Disk full")
    monkeypatch.setattr(f, "persist", fail)
    with pytest.raises(OSError):
        f.approve(ADMIN, item["id"])
    assert f.get_proposal(SALES, item["id"]).attributes["approved_by"] is None
    with pytest.raises(PermissionError):
        f.execute(SALES, item["id"])


def test_failed_policy_persistence_rolls_back(monkeypatch):
    old = f.policy()
    def fail():
        raise OSError("Disk full")
    monkeypatch.setattr(f, "persist", fail)
    with pytest.raises(OSError):
        f.set_policy(ADMIN, {**old, "max_autonomous_risk": 3})
    assert f.policy() == old


def test_source_change_requires_new_proposal():
    item = propose()
    f.approve(ADMIN, item["id"])
    ledger.get_entity("lead-1").attributes["status"] = "closed"
    with pytest.raises(ValueError, match="source record changed"):
        f.execute(SALES, item["id"])


def test_registered_connector_uses_central_secret_and_sanitized_result(monkeypatch):
    from core import agent_actions as actions
    monkeypatch.setattr(actions, "MODELS", dict(actions.MODELS))
    monkeypatch.setattr(actions, "CONNECTORS", {})
    monkeypatch.setattr("core.secrets.get_secret", lambda name: "vault-only")
    ledger.add_entity(Entity("crm-connection", "Connection", {"status": "connected"}))
    class CRMInput(actions.Input):
        lead_id: str
    calls = []
    def dispatch(actor, data, secret, key):
        assert secret == "vault-only"
        calls.append(key)
        return {"status": "executed", "token": "never-log-this"}
    actions.register_connector("crm.update", model=CRMInput, connection_id="crm-connection", credential_ref="CRM_TEST",
        validate_access=lambda actor, data: actions.require_record(actor, data["lead_id"], {"Lead"}), dispatch=dispatch)
    item = f.invoke(SALES, "sales", "crm.update", {"lead_id": "lead-1"}, "api", "crm")
    f.approve(ADMIN, item["id"])
    ledger.get_entity("crm-connection").attributes["status"] = "pending"
    with pytest.raises(ValueError):
        f.execute(SALES, item["id"])
    ledger.get_entity("crm-connection").attributes["status"] = "connected"
    result = f.execute(SALES, item["id"])
    assert calls == [item["id"]]
    assert "never-log-this" not in str(result)
    assert "vault-only" not in str(result)


def test_aged_inventory_automation_prepares_campaign_without_dispatch():
    ledger.add_entity(Entity("vehicle-aged", "Vehicle", {"Make": "Honda", "Model": "Civic", "DaysInStock": "65"}))
    result = f.run_automation(MARKETING, "marketing.aged_inventory_campaign", "vehicle-aged", "api", "aged")
    assert result["status"] == "proposed"
    assert result["input"]["make"] == "Honda"
    assert not any(e.entity_type == "Campaign" for e in ledger.get_all().values())


def test_reconciliation_records_human_confirmation_without_retry():
    item = propose()
    f.get_proposal(SALES, item["id"]).attributes["status"] = "needs_review"
    result = f.reconcile(ADMIN, item["id"], "confirmed_not_executed", "Task queue reviewed")
    assert result["status"] == "reconciled"
    with pytest.raises(ValueError):
        f.execute(SALES, item["id"])


def test_expired_approval_does_not_execute():
    item = propose()
    f.approve(ADMIN, item["id"])
    f.get_proposal(SALES, item["id"]).attributes["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="expired"):
        f.execute(SALES, item["id"])


def test_mutated_proposal_payload_is_rejected():
    item = propose()
    f.approve(ADMIN, item["id"])
    f.get_proposal(SALES, item["id"]).attributes["input"]["description"] = "Changed after approval"
    with pytest.raises(ValueError, match="no longer match"):
        f.execute(SALES, item["id"])


def test_inventory_matching_and_recommendations_are_observation_based():
    ledger.add_entity(Entity("vehicle-1", "Vehicle", {"Make": "Honda"}))
    ledger.add_relationship(Relationship("lead-1", "vehicle-1", "INTERESTED_IN"))
    result = f.invoke(SALES, "sales", "inventory.match", {"record_id": "lead-1"})
    assert result["records"][0]["id"] == "vehicle-1"
    assert result["evidence_kind"] == "observed"
    recommendation = f.invoke(SALES, "sales", "sales.next_best_action", {"record_id": "lead-1"})
    assert recommendation["decision"] == "prepare_follow_up"
    assert recommendation["probability"] is None


def test_canonical_revocation_overrides_legacy_consent():
    from core.agent_actions import channel_consent
    customer = Entity("customer-1", "Customer", {"consent": {"sms": True}})
    ledger.add_entity(customer)
    ledger.add_entity(Entity("consent-1", "Consent", {"customer_id": "customer-1", "channel": "sms", "status": "revoked", "occurred_at": "2026-10-01T12:00:00+00:00"}))
    assert channel_consent(customer, "sms") is False
    ledger.add_entity(Entity("consent-2", "Consent", {"customer_id": "customer-1", "channel": "sms", "status": "granted", "occurred_at": "2026-10-02T12:00:00+00:00"}))
    assert channel_consent(customer, "sms") is True
