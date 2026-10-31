from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import agent_fabric as f
from core.dealeros import ledger
from core.entities import Entity
from core.department_agents import PACKS, PROVIDERS
from api.routers.agent_fabric import router, employee, DealerPolicy

SALES = {"employee_id": "sales-1", "role": "SALES"}
ADMIN = {"employee_id": "admin-1", "role": "ADMIN"}
MARKETING = {"employee_id": "marketing-1", "role": "MARKETING"}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    previous = ledger.entities, ledger.relationships
    ledger.entities, ledger.relationships = {}, []
    monkeypatch.setattr(f, "persist", lambda: None)
    monkeypatch.setattr("core.lead_tasks.save_graph", lambda path: None)
    monkeypatch.setattr("core.ai_spend.dealer_ai_enabled", lambda: True)
    monkeypatch.setattr("core.ai_kill_switch.is_bot_enabled", lambda: True)
    monkeypatch.setattr("core.ai_kill_switch.is_workflow_automation_enabled", lambda: True)
    monkeypatch.setattr("core.ai_kill_switch.get_ai_kill_switches", lambda: {})
    ledger.add_entity(Entity("lead-1", "Lead", {
        "status": "open", "last_activity_at": (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat(),
        "email": "private@example.com", "token": "secret",
    }))
    yield
    ledger.entities, ledger.relationships = previous


def propose(actor=SALES, key="test"):
    return f.invoke(actor, "sales", "task.create", {"lead_id": "lead-1", "description": "Follow up"}, "claude", key)


def test_all_department_definitions_and_provider_manifests_share_one_contract():
    assert len(PACKS) == 12
    for provider in PROVIDERS:
        result = f.manifest(SALES, "sales", provider)
        assert result["agent"]["id"] == "nxtdeal.sales"
        assert "sms.send" not in [t["name"] for t in result["tools"]]


def test_marketing_and_gm_have_no_sensitive_bypass():
    for actor, department in [(MARKETING, "marketing"), (ADMIN, "gm")]:
        with pytest.raises(PermissionError):
            f.invoke(actor, department, "banking.transfer", {})
    with pytest.raises(PermissionError):
        f.manifest(SALES, "gm", "api")


def test_approval_and_replay_create_one_real_task_and_timeline_event():
    proposal = propose()
    with pytest.raises(PermissionError):
        f.execute(SALES, proposal["id"])
    f.approve(ADMIN, proposal["id"])
    result = f.execute(SALES, proposal["id"])
    assert result["status"] == "executed"
    assert f.execute(SALES, proposal["id"])["result"] == result["result"]
    assert propose()["id"] == proposal["id"]
    task = ledger.get_entity(result["result"]["task_id"])
    assert task.entity_type == "LeadTask"
    assert task.attributes["created_by"] == SALES["employee_id"]
    assert sum(e.entity_type == "LeadTask" for e in ledger.get_all().values()) == 1
    assert ledger.get_entity(result["timeline_event_id"]).attributes["provider"] == "claude"


def test_self_approval_and_cross_employee_access_denied():
    own = propose(ADMIN)
    with pytest.raises(PermissionError):
        f.approve(ADMIN, own["id"])
    proposal = propose()
    with pytest.raises(PermissionError):
        f.execute({"employee_id": "sales-2", "role": "SALES"}, proposal["id"])


def test_policy_is_rechecked_after_approval():
    proposal = propose()
    f.approve(ADMIN, proposal["id"])
    f.set_policy(ADMIN, DealerPolicy(disabled=["task.create"]).model_dump())
    with pytest.raises(PermissionError):
        f.execute(SALES, proposal["id"])


def test_employee_overlay_can_only_narrow_access():
    f.set_policy(ADMIN, DealerPolicy(employee_limits={"sales-1": ["lead.read", "campaign.publish"]}).model_dump())
    assert f.enabled_capabilities(SALES, "sales") == {"lead.read"}


def test_changed_request_cannot_reuse_idempotency_key():
    propose()
    with pytest.raises(ValueError):
        f.invoke(SALES, "sales", "task.create", {"lead_id": "lead-1", "description": "Different"}, "api", "test")


def test_kill_switch_blocks_approved_execution(monkeypatch):
    proposal = propose()
    f.approve(ADMIN, proposal["id"])
    monkeypatch.setattr("core.ai_kill_switch.get_ai_kill_switches", lambda: {"departments": {"Sales": {"active": True}}})
    with pytest.raises(PermissionError):
        f.execute(SALES, proposal["id"])


def test_stale_automation_deduplicates_and_never_sends_messages():
    first = f.run_automation(SALES, "sales.stale_lead_recovery", "lead-1", "api", "one")
    second = f.run_automation(SALES, "sales.stale_lead_recovery", "lead-1", "chatgpt", "two")
    assert first["id"] == second["id"]
    assert first["status"] == "proposed"
    ledger.get_entity("lead-1").attributes.pop("last_activity_at")
    assert f.run_automation(SALES, "sales.stale_lead_recovery", "lead-1", "api", None)["status"] == "skipped"


def test_reads_are_projected_and_audits_do_not_contain_raw_payloads():
    result = f.invoke(SALES, "sales", "lead.read", {})
    assert "private@example.com" not in str(result)
    assert "secret" not in str(result)
    events = [e.attributes for e in ledger.get_all().values() if e.entity_type == "AgentFabricEvent"]
    assert events[0]["source_records"] == ["lead-1"]
    assert "input" not in events[0]
    assert f.invoke(SALES, "sales", "chrono.analyze", {})["status"] == "unavailable"


def test_uncertain_execution_is_not_retried(monkeypatch):
    proposal = propose()
    f.approve(ADMIN, proposal["id"])
    def fail(*args):
        raise RuntimeError("sensitive upstream error")
    monkeypatch.setattr("core.lead_tasks.create_task", fail)
    with pytest.raises(ValueError, match="human review"):
        f.execute(SALES, proposal["id"])
    with pytest.raises(ValueError, match="cannot be retried"):
        f.execute(SALES, proposal["id"])


def test_routes_require_auth_and_reject_client_identity():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/agent-fabric/catalog").status_code == 401
    app.dependency_overrides[employee] = lambda: SALES
    assert client.get("/agent-fabric/catalog").status_code == 200
    assert client.post("/agent-fabric/invoke", json={"department": "sales", "capability": "lead.read", "role": "ADMIN"}).status_code == 422
    assert client.put("/agent-fabric/policy", json={}).status_code == 403
    assert client.post("/agent-fabric/invoke", json={"department": "gm", "capability": "analytics.read"}).status_code == 403


def test_rejection_is_terminal():
    proposal = propose()
    assert f.reject(SALES, proposal["id"])["status"] == "rejected"
    with pytest.raises(ValueError):
        f.execute(SALES, proposal["id"])


def test_provenance_retains_source_history_and_deduplicates(monkeypatch):
    from chrono.contracts import Observation
    from core.agent_data_bridge import retain_provenance
    monkeypatch.setattr("core.agent_data_bridge.save_graph", lambda path: None)
    ledger.add_entity(Entity("connection-1", "Connection", {"credentials": "must-not-copy"}))
    timestamp = datetime.now(timezone.utc).isoformat()
    observation = Observation("lead-1", timestamp, "observed", "crm", "external-1", timestamp, timestamp, .9)
    first = retain_provenance("connection-1", observation)
    assert retain_provenance("connection-1", observation) == first
    assert ledger.get_entity(first).attributes["source_id"] == "external-1"
    assert "must-not-copy" not in str(ledger.get_entity(first).attributes)
    assert ledger.get_entity("lead-1").attributes["status"] == "open"


def test_catalog_hides_other_employee_limits():
    f.set_policy(ADMIN, DealerPolicy(employee_limits={"other-user": ["lead.read"]}).model_dump())
    assert "employee_limits" not in f.catalog(SALES)["policy"]


def test_proposals_and_audit_survive_graph_reload(tmp_path):
    proposal = propose()
    f.approve(ADMIN, proposal["id"])
    path = str(tmp_path / "graph.json")
    ledger.save(path)
    ledger.reset()
    ledger.load(path)
    assert f.get_proposal(SALES, proposal["id"]).attributes["approved_by"] == ADMIN["employee_id"]
    assert propose()["id"] == proposal["id"]
    assert any(e.entity_type == "AgentFabricEvent" and e.attributes["decision"] == "approved" for e in ledger.get_all().values())


@pytest.mark.parametrize("data", [
    {"lead_id": [], "description": "Follow up"},
    {"lead_id": "lead-1", "description": "Follow up", "due_at": True},
    {"lead_id": "lead-1", "description": "Follow up", "token": "secret"},
])
def test_task_contract_rejects_malformed_or_unexpected_input(data):
    with pytest.raises(ValueError):
        f.invoke(SALES, "sales", "task.create", data, "api", "malformed")
