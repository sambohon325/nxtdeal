import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import agent_oauth as oauth
from core.auth import credential_store
from api.routers.agent_oauth import router, _requests
from api.routers.agent_fabric import employee, router as fabric_router
from api.routers.agent_mcp import router as mcp_router

ADMIN = {"employee_id": "owner", "role": "ADMIN", "principal": "session"}
USER = {"employee_id": "user", "role": "SALES", "principal": "session"}
VERIFIER = "V" * 64
CALLBACK = "https://assistant.example/oauth/callback"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("NXTDEAL_PUBLIC_API_URL", "https://api.example")
    monkeypatch.setenv("NXTDEAL_PUBLIC_APP_URL", "https://app.example")
    monkeypatch.setattr(credential_store, "credentials", {
        "owner": {"role": "ADMIN", "hash": "owner-password"},
        "user": {"role": "SALES", "hash": "user-password"},
    })
    _requests.clear()


def authorize(scopes="nxtdeal:read nxtdeal:propose", actor=USER, departments=None):
    client = oauth.register_client(ADMIN, "Assistant", [CALLBACK])
    params = {"client_id": client["client_id"], "response_type": "code", "redirect_uri": CALLBACK,
              "resource": oauth.resource(), "scope": scopes, "state": "client-state",
              "code_challenge_method": "S256", "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")}
    request_id = oauth.begin(params)
    result = oauth.consent(actor, request_id, departments or ["sales"], True)
    code = parse_qs(urlsplit(result["redirect_url"]).query)["code"][0]
    return {"grant_type": "authorization_code", "client_id": client["client_id"], "redirect_uri": CALLBACK,
            "resource": oauth.resource(), "code": code, "code_verifier": VERIFIER}, request_id


def test_full_code_flow_scoped_token_and_hash_only_storage():
    params, request_id = authorize()
    tokens = oauth.exchange(params)
    actor = oauth.verify(tokens["access_token"])
    assert actor["employee_id"] == "user"
    assert actor["principal"] == "oauth"
    assert actor["oauth_departments"] == ["sales"]
    with oauth.database() as db:
        dump = " ".join(db.iterdump())
    for secret in (tokens["access_token"], tokens["refresh_token"], params["code"], request_id):
        assert secret not in dump
    assert "owner-password" not in dump
    assert oauth.connections(USER)["grants"][0]["revoked"] == 0


@pytest.mark.parametrize("field,value", [("code_verifier", "x" * 64), ("redirect_uri", "https://evil.example"), ("resource", "https://other.example/mcp"), ("client_id", "wrong")])
def test_exchange_binding_failures_do_not_consume_valid_code(field, value):
    params, _ = authorize()
    with pytest.raises(ValueError):
        oauth.exchange({**params, field: value})
    assert oauth.verify(oauth.exchange(params)["access_token"])


def test_code_replay_revokes_issued_tokens():
    params, _ = authorize()
    first = oauth.exchange(params)
    with pytest.raises(ValueError):
        oauth.exchange(params)
    assert oauth.verify(first["access_token"]) is None


def test_refresh_rotation_replay_revokes_entire_family():
    params, _ = authorize()
    first = oauth.exchange(params)
    refresh = {"grant_type": "refresh_token", "resource": oauth.resource(), "client_id": params["client_id"], "refresh_token": first["refresh_token"]}
    second = oauth.exchange(refresh)
    assert oauth.verify(second["access_token"])
    with pytest.raises(ValueError):
        oauth.exchange(refresh)
    assert oauth.verify(first["access_token"]) is None
    assert oauth.verify(second["access_token"]) is None


def test_code_exchange_is_atomic_across_connections():
    params, _ = authorize()
    def exchange():
        try:
            return oauth.exchange(params)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exchange(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert oauth.verify(next(r for r in results if r)["access_token"]) is None


@pytest.mark.parametrize("change", ["disabled", "password", "deleted", "ip_restriction", "password_required"])
def test_current_employee_restrictions_revoke_effective_access(change):
    params, _ = authorize()
    token = oauth.exchange(params)["access_token"]
    if change == "disabled": credential_store.credentials["user"]["disabled"] = True
    elif change == "password": credential_store.credentials["user"]["hash"] = "changed"
    elif change == "deleted": credential_store.credentials.pop("user")
    elif change == "ip_restriction": credential_store.credentials["user"]["ip_allowlist"] = ["192.0.2.1"]
    else: credential_store.credentials["user"]["must_change_password"] = True
    assert oauth.verify(token) is None


def test_read_only_scope_and_department_are_intersected_with_current_role():
    from core import agent_fabric as fabric
    params, _ = authorize("nxtdeal:read")
    token = oauth.exchange(params)["access_token"]
    actor = oauth.verify(token)
    assert "task.create" not in fabric.enabled_capabilities(actor, "sales")
    with pytest.raises(PermissionError): fabric.enabled_capabilities(actor, "gm")
    assert [a["department"] for a in fabric.catalog(actor)["agents"]] == ["sales"]
    credential_store.credentials["user"]["role"] = "MARKETING"
    actor = oauth.verify(token)
    assert actor["role"] == "MARKETING"
    with pytest.raises(PermissionError): fabric.enabled_capabilities(actor, "sales")


def test_revocation_owned_grants_and_client_disable():
    params, _ = authorize()
    tokens = oauth.exchange(params)
    grant = oauth.connections(USER)["grants"][0]["id"]
    oauth.revoke(ADMIN, grant)
    assert oauth.verify(tokens["access_token"])
    oauth.revoke(USER, grant)
    assert oauth.verify(tokens["access_token"]) is None
    params, _ = authorize()
    tokens = oauth.exchange(params)
    oauth.disable_client(ADMIN, params["client_id"])
    assert oauth.verify(tokens["access_token"]) is None


@pytest.mark.parametrize("url", ["http://example.com/callback", "https://example.com/#x", "https://x:y@example.com", "https://example.com/cb?next=other", "https://example.com\\@evil.example", "https://example.com/\ncallback"])
def test_invalid_callback_registration(url):
    with pytest.raises(ValueError): oauth.register_client(ADMIN, "Bad", [url])


def test_api_credentials_cannot_register_or_consent():
    with pytest.raises(PermissionError): oauth.register_client({**ADMIN, "principal": "api"}, "AI", [CALLBACK])
    with pytest.raises(PermissionError): oauth.consent({**USER, "principal": "api"}, "request", ["sales"], True)


def test_expiry_and_wrong_audience(monkeypatch):
    params, _ = authorize()
    tokens = oauth.exchange(params)
    with oauth.database() as db: db.execute("UPDATE tokens SET expires=0 WHERE kind='access'")
    assert oauth.verify(tokens["access_token"]) is None
    monkeypatch.setenv("NXTDEAL_PUBLIC_API_URL", "https://wrong.example")
    with pytest.raises(ValueError): oauth.exchange({"grant_type": "refresh_token", "resource": oauth.resource(), "client_id": params["client_id"], "refresh_token": tokens["refresh_token"]})


def test_http_metadata_challenges_and_real_oauth_mcp():
    app = FastAPI()
    app.include_router(router); app.include_router(mcp_router); app.include_router(fabric_router)
    client = TestClient(app)
    assert client.get("/.well-known/oauth-protected-resource/agent-fabric/mcp").json()["resource"] == oauth.resource()
    assert client.get("/.well-known/oauth-authorization-server").json()["code_challenge_methods_supported"] == ["S256"]
    headers = {"Accept": "application/json, text/event-stream"}
    assert "resource_metadata=" in client.post("/agent-fabric/mcp", headers=headers, json={}).headers["www-authenticate"]
    params, _ = authorize("nxtdeal:read")
    response = client.post("/agent-oauth/token", data=params)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    headers["Authorization"] = "Bearer " + response.json()["access_token"]
    catalog = client.post("/agent-fabric/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nxtdeal_catalog"}}).json()
    assert json.loads(catalog["result"]["content"][0]["text"])["agents"][0]["department"] == "sales"
    assert client.get("/agent-fabric/catalog", headers=headers).status_code == 401
    rejected = client.post("/agent-fabric/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nxtdeal_invoke", "arguments": {"department": "sales", "capability": "task.create", "input": {"lead_id": "x", "description": "x"}}}}).json()
    assert rejected["result"]["isError"] is True


def test_invalid_requests_never_redirect_to_unregistered_url():
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    response = client.get("/agent-oauth/authorize?client_id=bad&redirect_uri=https://evil.example", follow_redirects=False)
    assert response.status_code == 400 and "location" not in response.headers
    assert client.post("/agent-oauth/token", content="code=a&code=b", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 400
    assert client.post("/agent-oauth/token", content="a" * 8193, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 400


def test_consent_rollback_preserves_request_when_persistence_fails(monkeypatch):
    params, _ = authorize()
    # A SQL failure during token issuance must not consume the authorization code.
    real_issue = oauth.issue
    monkeypatch.setattr(oauth, "issue", lambda *_: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(RuntimeError): oauth.exchange(params)
    monkeypatch.setattr(oauth, "issue", real_issue)
    assert oauth.exchange(params)["access_token"]


def test_authorization_review_deny_and_one_use_consent():
    client = oauth.register_client(ADMIN, "AI", [CALLBACK])
    params = {"client_id": client["client_id"], "response_type": "code", "redirect_uri": CALLBACK,
              "resource": oauth.resource(), "scope": "nxtdeal:read", "state": "state<&",
              "code_challenge_method": "S256", "code_challenge": "A" * 43}
    request_id = oauth.begin(params)
    review = oauth.review(USER, request_id)
    assert review["client_name"] == "AI" and "sales" in review["departments"]
    with pytest.raises(ValueError): oauth.consent(USER, request_id, ["gm"], True)
    result = oauth.consent(USER, request_id, [], False)
    assert parse_qs(urlsplit(result["redirect_url"]).query) == {"state": ["state<&"], "error": ["access_denied"]}
    with pytest.raises(ValueError): oauth.consent(USER, request_id, ["sales"], True)
    assert oauth.connections(USER)["grants"] == []


@pytest.mark.parametrize("field,value", [("code_challenge_method", "plain"), ("code_challenge", "short"), ("scope", "nxtdeal:read admin"), ("response_type", "token"), ("resource", "https://wrong.example"), ("state", "")])
def test_authorization_parameters_fail_closed(field, value):
    client = oauth.register_client(ADMIN, "AI", [CALLBACK])
    params = {"client_id": client["client_id"], "response_type": "code", "redirect_uri": CALLBACK,
              "resource": oauth.resource(), "scope": "nxtdeal:read", "state": "state",
              "code_challenge_method": "S256", "code_challenge": "A" * 43}
    with pytest.raises(ValueError): oauth.begin({**params, field: value})


def test_public_auth_rate_budget():
    import time
    _requests.extend([time.monotonic()] * 300)
    app = FastAPI(); app.include_router(router)
    response = TestClient(app).post("/agent-oauth/token", data={})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_token_revocation_does_not_revoke_other_clients():
    params, _ = authorize()
    tokens = oauth.exchange(params)
    oauth.revoke_token(tokens["refresh_token"], "wrong-client")
    assert oauth.verify(tokens["access_token"])
    oauth.revoke_token(tokens["refresh_token"], params["client_id"])
    assert oauth.verify(tokens["access_token"]) is None
