import hashlib
import hmac
import json
import time
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import marketing_operations as m
from staff_auth_fixture import staff_token
from core.dealeros import ledger
from core.entities import Entity


def headers(actor="sam", role="MARKETING", key=None):
    return {"Authorization": "Bearer " + staff_token(actor, role), **({"Idempotency-Key": key} if key else {})}


@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    ledger.add_entity(Entity("SYSCFG-00001", "SystemConfig", {"dealership_name":"Synthetic Dealer", "address_line1":"100 Test Street", "city":"Test City", "state":"TX", "zip_code":"75001"}))
    monkeypatch.setenv("NXTDEAL_MARKETING_PUBLIC_URL", "https://api.example.test")
    monkeypatch.setenv("NXTDEAL_MARKETING_DELIVERY_ENABLED", "true")
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setenv("NXTDEAL_MARKETING_APPROVER_EMPLOYEE_ID", "sam")
    monkeypatch.setenv("NXTDEAL_CHANNEL_GATEWAY_URL", "https://gateway.example.test/actions")
    monkeypatch.setenv("NXTDEAL_CHANNEL_GATEWAY_TOKEN", "test-only")
    monkeypatch.setenv("NXTDEAL_CHANNEL_CALLBACK_SECRET", "test-callback-secret")
    app = FastAPI()
    app.include_router(m.router)
    with TestClient(app) as client:
        yield client
    ledger.reset()


def draft(client, channel="social", **extra):
    response = client.post("/marketing/operations/actions", headers=headers(), json={"channel": channel, "body": "Test copy", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, action):
    return client.post(f'/marketing/operations/actions/{action["id"]}/decision', headers=headers(), json={"revision": action["revision"], "decision": "approve"})


def test_roles_reads_and_sole_approver(client):
    assert client.get("/marketing/operations").status_code == 401
    assert client.post("/marketing/operations/actions", headers=headers(role="SALES"), json={"channel": "social", "body": "Test"}).status_code == 403
    before = deepcopy(ledger.entities)
    data = client.get("/marketing/operations", headers=headers()).json()
    assert len(data["agents"]) == 8 and data["can_approve"]
    assert ledger.entities == before
    a = draft(client)
    assert client.post(f'/marketing/operations/actions/{a["id"]}/decision', headers=headers("another-admin", "ADMIN"), json={"revision": 1, "decision": "approve"}).status_code == 403


def test_model_run_idempotency_provenance_and_no_recipient_authority(client, monkeypatch):
    calls = []
    def plan(goal, context):
        calls.append(goal)
        return m.GeneratedPlan(summary="Proposal", actions=[m.ActionSpec(channel="sms", body="Draft", recipient_id="MODEL-INVENTED")]), {"provider": "test", "model": "test-model", "response_id": "proof"}
    monkeypatch.setattr(m, "plan_goal", plan)
    h = headers(key="test-idempotency-0001")
    goal = {"goal": "Promote recorded inventory", "agent_id": "inventory"}
    first = client.post("/marketing/operations/runs", headers=h, json=goal).json()
    second = client.post("/marketing/operations/runs", headers=h, json=goal).json()
    assert first == second and len(calls) == 1
    assert first["status"] == "awaiting_review" and first["provenance"]["provider"] == "test"
    action = ledger.get_entity(first["actions"][0])
    assert action.attributes["recipient_id"] is None and action.attributes["status"] == "draft"
    assert client.post("/marketing/operations/runs", headers=h, json={**goal, "goal": "Different goal"}).status_code == 409


def test_paused_and_failed_model_never_claim_success(client, monkeypatch):
    client.post("/marketing/operations/agents/creative", headers=headers(), json={"paused": True})
    assert client.post("/marketing/operations/runs", headers=headers(key="test-idempotency-0002"), json={"goal": "Draft a campaign", "agent_id": "creative"}).status_code == 423
    def fail(*_):
        raise RuntimeError("provider-key-must-not-leak")
    monkeypatch.setattr(m, "plan_goal", fail)
    result = client.post("/marketing/operations/runs", headers=headers(key="test-idempotency-0003"), json={"goal": "Draft a campaign"}).json()
    assert result["status"] == "failed" and "provider-key" not in json.dumps(result)
    assert not m.all_of(m.ACTION)


def test_edit_invalidates_approval_and_conflicts(client):
    a = draft(client)
    approved = approve(client, a).json()
    assert approved["status"] == "approved"
    url = f'/marketing/operations/actions/{a["id"]}'
    assert client.put(url, headers=headers(), json={"revision": 1, "channel": "social", "body": "Changed"}).status_code == 409
    edited = client.put(url, headers=headers(), json={"revision": 2, "channel": "social", "body": "Changed"}).json()
    assert edited["status"] == "draft" and edited["approved_by"] is None


def test_consent_rechecked_before_dispatch(client, monkeypatch):
    ledger.add_entity(Entity("C1", "Customer", {"email": "fixture@example.test"}))
    a = draft(client, "email", recipient_id="C1")
    assert approve(client, a).status_code == 409
    ledger.get_entity("C1").attributes["marketing_email_consent"] = True
    assert approve(client, a).status_code == 200
    ledger.get_entity("C1").attributes["DoNotContact"] = True
    monkeypatch.setattr(m, "send_gateway", lambda _: pytest.fail("Must not contact opted-out recipient"))
    assert client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers()).status_code == 409


def test_provider_acceptance_and_no_duplicate_dispatch(client, monkeypatch):
    a = approve(client, draft(client)).json()
    calls = []
    monkeypatch.setattr(m, "send_gateway", lambda action: calls.append(action) or "provider-123")
    url = f'/marketing/operations/actions/{a["id"]}/dispatch'
    result = client.post(url, headers=headers()).json()
    assert result["status"] == "accepted" and result["provider_reference"] == "provider-123"
    assert client.post(url, headers=headers()).status_code == 409 and len(calls) == 1


def test_unknown_outcome_requires_reconciliation(client, monkeypatch):
    a = approve(client, draft(client)).json()
    def fail(_):
        raise TimeoutError("uncertain")
    monkeypatch.setattr(m, "send_gateway", fail)
    url = f'/marketing/operations/actions/{a["id"]}'
    assert client.post(url + "/dispatch", headers=headers()).json()["status"] == "unknown"
    assert client.post(url + "/dispatch", headers=headers()).status_code == 409
    result = client.post(url + "/reconcile", headers=headers(), json={"provider_reference": "confirmed-1", "status": "delivered", "evidence": "Confirmed in test provider console"}).json()
    assert result["status_source"] == "human_provider_reconciliation"


def test_missing_gateway_and_future_schedule(client, monkeypatch):
    a = approve(client, draft(client, scheduled_at="2099-01-01T00:00:00Z")).json()
    url = f'/marketing/operations/actions/{a["id"]}/dispatch'
    assert client.post(url, headers=headers()).status_code == 409
    monkeypatch.delenv("NXTDEAL_CHANNEL_GATEWAY_TOKEN")
    assert client.post(url, headers=headers()).status_code == 503
    assert client.post("/marketing/operations/actions", headers=headers(), json={"channel": "social", "body": "Test", "scheduled_at": "2099-01-01T00:00:00"}).status_code == 422


def callback(client, a, event_id, status, ref="provider-123", signed=True):
    body = json.dumps({"action_id": a["id"], "provider_reference": ref, "event_id": event_id, "status": status, "text": "Customer response"}).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(b"test-callback-secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return client.post("/marketing/operations/provider-events", content=body, headers={"X-Nxtdeal-Timestamp": timestamp, "X-Nxtdeal-Signature": signature if signed else "invalid"})


def test_signed_callbacks_match_references_replay_and_never_regress_delivery(client, monkeypatch):
    a = approve(client, draft(client)).json()
    monkeypatch.setattr(m, "send_gateway", lambda _: "provider-123")
    client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers())
    assert callback(client, a, "e1", "delivered", signed=False).status_code == 401
    assert callback(client, a, "e1", "delivered", ref="wrong").status_code == 409
    assert callback(client, a, "e1", "delivered").status_code == 200
    assert callback(client, a, "e1", "delivered").json()["replay"]
    assert callback(client, a, "e2", "failed").status_code == 200
    assert ledger.get_entity(a["id"]).attributes["status"] == "delivered"
    assert len(m.all_of(m.EVENT)) == 2


def test_paid_budget_allocation(client, monkeypatch):
    monkeypatch.setenv("NXTDEAL_MARKETING_MEDIA_LIMIT", "100")
    assert approve(client, draft(client, "paid_media", budget=60)).status_code == 200
    assert approve(client, draft(client, "paid_media", budget=60)).status_code == 409


def test_disk_failure_prevents_provider_call(client, monkeypatch):
    a = approve(client, draft(client)).json()
    def fail(_):
        raise OSError("Test disk full")
    monkeypatch.setattr(m, "save_graph", fail)
    monkeypatch.setattr(m, "send_gateway", lambda _: pytest.fail("Dispatch must persist before I/O"))
    with pytest.raises(OSError):
        client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers())
    assert ledger.get_entity(a["id"]).attributes["status"] == "approved"


def test_delivery_defaults_closed(client, monkeypatch):
    monkeypatch.delenv("NXTDEAL_MARKETING_DELIVERY_ENABLED")
    a = approve(client, draft(client)).json()
    assert client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers()).status_code == 503
    assert not client.get("/marketing/operations", headers=headers()).json()["provider_configured"]


@pytest.mark.parametrize("limit", ["invalid", "nan", "inf"])
def test_invalid_budget_configuration_fails_closed(client, monkeypatch, limit):
    monkeypatch.setenv("NXTDEAL_MARKETING_MEDIA_LIMIT", limit)
    assert approve(client, draft(client, "paid_media", budget=1)).status_code == 409


def test_inflight_dispatch_cannot_be_reconciled(client):
    a = draft(client)
    m.update(ledger.get_entity(a["id"]), {"status": "dispatching"})
    assert client.post(f'/marketing/operations/actions/{a["id"]}/reconcile', headers=headers(), json={"provider_reference": "ref", "status": "accepted", "evidence": "Provider console evidence"}).status_code == 409


def test_bulk_drafts_are_atomic_consent_checked_and_idempotent(client):
    for rid in ["C1", "C2"]:
        ledger.add_entity(Entity(rid, "Customer", {"phone": "+15555550123", "marketing_sms_consent": True}))
    payload = {"channel": "sms", "body": "Draft only", "recipient_ids": ["C1", "C2", "C1"]}
    h = headers(key="test-bulk-idempotency-001")
    result = client.post("/marketing/operations/bulk-actions", headers=h, json=payload)
    assert result.status_code == 200
    assert result.json()["recipient_count"] == 2
    assert client.post("/marketing/operations/bulk-actions", headers=h, json=payload).json() == result.json()
    assert len(m.all_of(m.ACTION)) == 2
    assert all(a.attributes["status"] == "draft" for a in m.all_of(m.ACTION))
    ledger.get_entity("C2").attributes["DoNotContact"] = True
    assert client.post("/marketing/operations/bulk-actions", headers=headers(key="test-bulk-idempotency-002"), json=payload).status_code == 409
    assert len(m.all_of(m.ACTION)) == 2


def test_bulk_disk_failure_rolls_back_all_actions(client, monkeypatch):
    ledger.add_entity(Entity("C1", "Customer", {"email": "fixture@example.test", "marketing_email_consent": True}))
    def fail(_):
        raise OSError("Disk full")
    monkeypatch.setattr(m, "save_graph", fail)
    with pytest.raises(OSError):
        client.post("/marketing/operations/bulk-actions", headers=headers(key="test-bulk-idempotency-003"), json={"channel": "email", "body": "Draft", "recipient_ids": ["C1"]})
    assert not m.all_of(m.ACTION)
    assert not m.all_of("MarketingCommunicationBatch")


def test_return_for_changes_preserves_feedback_and_requires_fresh_review(client, monkeypatch):
    monkeypatch.setattr(m, "send_gateway", lambda *_: pytest.fail("Review must never dispatch"))
    a = draft(client)
    url = f'/marketing/operations/actions/{a["id"]}'
    request = {"revision": a["revision"], "decision": "reject", "note": "  Clarify the fictional offer.  "}
    assert client.post(url + "/decision", headers=headers("writer"), json=request).status_code == 403
    assert client.post(url + "/decision", headers=headers(), json={**request, "note": "  "}).status_code == 422
    returned = client.post(url + "/decision", headers=headers(), json=request).json()
    assert returned["status"] == "rejected"
    assert returned["review_note"] == "Clarify the fictional offer."
    assert client.post(url + "/decision", headers=headers(), json=request).status_code == 409
    queue = client.get('/marketing/operations', headers=headers("writer")).json()
    assert any(x["id"] == a["id"] and x["review_note"] == returned["review_note"] for x in queue["actions"])
    edited = client.put(url, headers=headers("writer"), json={"revision": returned["revision"], "channel": "social", "body": "Corrected fictional offer"}).json()
    assert edited["status"] == "draft" and edited["approved_by"] is None
    assert edited["review_note"] == returned["review_note"]
    approved = approve(client, edited).json()
    assert approved["status"] == "approved" and approved["review_note"] is None


def test_automatic_footer_unsubscribe_suppresses_duplicates(client, monkeypatch):
    for rid in ("C1", "C2"):
        ledger.add_entity(Entity(rid, "Customer", {"email":"fixture@example.test", "marketing_email_consent":True}))
    a = approve(client, draft(client, "email", recipient_id="C1")).json()
    assert "100 Test Street" in a["send_body"]
    path = "/marketing/operations/unsubscribe/" + a["unsubscribe_token"]
    other = approve(client, draft(client, "email", recipient_id="C2")).json()
    assert client.get(path).status_code == 200
    assert not m.email_footer.is_suppressed("fixture@example.test")
    assert client.post(path, content="List-Unsubscribe=One-Click").status_code == 200
    assert client.post(path).status_code == 200
    assert m.email_footer.is_suppressed("FIXTURE@example.test")
    monkeypatch.setattr(m, "send_gateway", lambda _: pytest.fail("Unsubscribed address must not send"))
    assert client.post(f'/marketing/operations/actions/{other["id"]}/dispatch', headers=headers()).status_code == 409
    assert approve(client, draft(client, "email", recipient_id="C2")).status_code == 409
    assert client.post(path+"tampered").status_code == 404
    assert ledger.get_entity("C1").attributes["marketing_email_consent"] is True


def test_footer_missing_profile_and_changed_address_block_send(client, monkeypatch):
    ledger.add_entity(Entity("C1", "Customer", {"email":"fixture@example.test", "marketing_email_consent":True}))
    profile = ledger.get_entity("SYSCFG-00001")
    profile.attributes["city"] = ""
    a = draft(client, "email", recipient_id="C1")
    assert approve(client, a).status_code == 409
    profile.attributes["city"] = "Test City"
    approved = approve(client, a).json()
    assert approved["unsubscribe_url"].startswith("https://api.example.test/")
    profile.attributes["address_line1"] = "200 Changed Street"
    monkeypatch.setattr(m, "send_gateway", lambda _: pytest.fail("Address changed after approval"))
    response = client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers())
    assert response.status_code == 409
    assert "address" in response.json()["detail"]


def test_email_sent_payload_contains_footer(client, monkeypatch):
    ledger.add_entity(Entity("C1", "Customer", {"email":"fixture@example.test", "marketing_email_consent":True}))
    a = approve(client, draft(client, "email", recipient_id="C1")).json()
    seen=[]
    monkeypatch.setattr(m.marketing_delivery, "configured", lambda channel: False)
    monkeypatch.setattr(m, "send_gateway", lambda payload: seen.append(payload) or "fixture-ref")
    assert client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers()).json()["status"] == "accepted"
    assert "100 Test Street" in seen[0]["body"] and a["unsubscribe_url"] in seen[0]["body"]


def test_response_routes_after_receipt_and_retries_without_losing_event(client, monkeypatch):
    a = approve(client, draft(client)).json()
    monkeypatch.setattr(m, "send_gateway", lambda _: "provider-123")
    a = client.post(f'/marketing/operations/actions/{a["id"]}/dispatch', headers=headers()).json()
    from api.routers import campaign_workflow
    calls=[]
    def broken():
        calls.append(True)
        raise RuntimeError("Synthetic routing unavailable")
    monkeypatch.setattr(campaign_workflow, "sync_recorded_responses", broken)
    assert callback(client,a,"reply-1","response").status_code==200
    assert len(m.all_of(m.EVENT))==1
    monkeypatch.setattr(campaign_workflow,"sync_recorded_responses",lambda:calls.append(True))
    assert callback(client,a,"reply-1","response").json()["replay"]
    assert len(calls)==2 and len(m.all_of(m.EVENT))==1
