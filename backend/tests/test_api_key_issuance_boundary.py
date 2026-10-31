import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers import identity_access
from core import auth, api_keys
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, API_KEY


@pytest.fixture
def fixture(monkeypatch):
    ledger.reset()
    store = auth.credential_store
    store.reset()
    store.set_credential("EMP-BOUNDARY", "Synthetic-password-only!42", "SALES", must_change_password=False)
    ledger.add_entity(Entity(id="EMP-BOUNDARY", entity_type=EMPLOYEE, attributes={}))
    monkeypatch.setattr(api_keys, "save_graph", lambda *_: None)
    app = FastAPI()
    app.include_router(identity_access.router)
    yield TestClient(app), store
    ledger.reset()
    store.reset()


def count_keys():
    return sum(e.entity_type == API_KEY for e in ledger.get_all().values())


def create(client, token):
    return client.post("/api-keys", headers={"Authorization": "Bearer " + token}, json={"label":"Synthetic"}).json()


def test_existing_api_key_cannot_mint_replacement(fixture):
    client, _ = fixture
    key = api_keys.generate_api_key("EMP-BOUNDARY", "Original", "EMP-BOUNDARY")
    assert create(client, key["raw_key"])["code"] == "fresh_login_required"
    assert count_keys() == 1


@pytest.mark.parametrize("mode", ["not_fresh", "expired_freshness", "future", "temporary_password", "mfa_not_completed"])
def test_issuance_denials_have_no_side_effects(fixture, monkeypatch, mode):
    client, store = fixture
    if mode == "temporary_password":
        store.get_record("EMP-BOUNDARY")["must_change_password"] = True
    if mode == "mfa_not_completed":
        monkeypatch.setattr(store, "is_mfa_enabled", lambda *_: True)
    now = time.time()
    offset = -301 if mode == "expired_freshness" else 60 if mode == "future" else 0
    with monkeypatch.context() as context:
        context.setattr(auth.time, "time", lambda: now + offset)
        token = auth.issue_token("EMP-BOUNDARY", "SALES", fresh_auth=mode != "not_fresh")
    result = create(client, token)
    if mode == "temporary_password":
        assert result == {"error": "Password change required"}
    else:
        assert result["code"] == "fresh_login_required"
    assert count_keys() == 0


def test_recent_interactive_session_can_create_own_key(fixture):
    client, _ = fixture
    token = auth.issue_token("EMP-BOUNDARY", "SALES", fresh_auth=True)
    result = create(client, token)
    assert "raw_key" in result and count_keys() == 1


def test_recent_session_cannot_create_other_employee_key(fixture):
    client, _ = fixture
    token = auth.issue_token("EMP-BOUNDARY", "SALES", fresh_auth=True)
    result = client.post("/api-keys", headers={"Authorization":"Bearer " + token},
                         json={"target_employee_id":"EMP-OTHER"}).json()
    assert "error" in result and count_keys() == 0

@pytest.mark.parametrize("target_role", ["ADMIN", "FINANCE", "SALES", "OPERATIONS"])
def test_operations_cannot_issue_another_principals_credential(fixture, target_role):
    client, store = fixture
    store.set_credential("EMP-BOUNDARY", "Synthetic-password-only!42", "OPERATIONS", must_change_password=False)
    store.set_credential("EMP-TARGET", "Synthetic-target-only!42", target_role, must_change_password=False)
    ledger.add_entity(Entity(id="EMP-TARGET", entity_type=EMPLOYEE, attributes={}))
    token = auth.issue_token("EMP-BOUNDARY", "OPERATIONS", fresh_auth=True)
    result = client.post("/api-keys", headers={"Authorization": "Bearer " + token},
                         json={"target_employee_id": "EMP-TARGET"}).json()
    assert "error" in result
    assert "raw_key" not in result
    assert count_keys() == 0

@pytest.mark.parametrize("caller_role,target", [("OPERATIONS", "EMP-BOUNDARY"), ("ADMIN", "EMP-TARGET")])
def test_authorized_issuance_preserves_self_service_and_admin_delegation(fixture, caller_role, target):
    client, store = fixture
    store.set_credential("EMP-BOUNDARY", "Synthetic-password-only!42", caller_role, must_change_password=False)
    store.set_credential("EMP-TARGET", "Synthetic-target-only!42", "SALES", must_change_password=False)
    ledger.add_entity(Entity(id="EMP-TARGET", entity_type=EMPLOYEE, attributes={}))
    token = auth.issue_token("EMP-BOUNDARY", caller_role, fresh_auth=True)
    result = client.post("/api-keys", headers={"Authorization": "Bearer " + token},
                         json={"target_employee_id": target}).json()
    assert "error" not in result
    assert count_keys() == 1
    verified = api_keys.verify_api_key(result["raw_key"])
    assert verified["employee_id"] == target
    assert verified["role"] == (caller_role if target == "EMP-BOUNDARY" else "SALES")


def test_admin_api_key_cannot_extend_its_own_lifetime(fixture, monkeypatch):
    from api.deps import _authenticate
    from core import entity_update_api
    from copy import deepcopy
    _, store = fixture
    store.set_credential('EMP-BOUNDARY', 'Synthetic-password-only!42', 'ADMIN', must_change_password=False)
    key = api_keys.generate_api_key('EMP-BOUNDARY', 'Synthetic', 'EMP-BOUNDARY')
    actor, error = _authenticate('Bearer ' + key['raw_key'])
    assert error is None
    before = deepcopy(ledger.get_entity(key['id']).attributes)
    writes = []
    monkeypatch.setattr(entity_update_api, 'save_graph', lambda *_: writes.append('graph'))
    monkeypatch.setattr(entity_update_api, 'save_audit_log', lambda *_: writes.append('audit'))
    result = entity_update_api.update_entity_api(actor['role'], actor['employee_id'], key['id'],
                                               {'expires_at': '2099-01-01T00:00:00+00:00'})
    assert 'error' in result
    assert ledger.get_entity(key['id']).attributes == before
    assert writes == []
