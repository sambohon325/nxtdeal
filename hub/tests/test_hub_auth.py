"""
Tests for the NXTDeal Hub's real per-employee admin login (2026-07-23) -- the
replacement for the old single shared-secret X-NXTDeal-Hub-Key gate.

Covers, end to end via FastAPI's TestClient (which drives app.py's lifespan, so
the env-seed bootstrap actually runs):
  * env-bootstrap creates the first ADMIN from HUB_ADMIN_USERNAME/HUB_ADMIN_PASSWORD
  * POST /hub/auth/login: success returns {token, role, must_change_password};
    wrong password -> 401
  * GET /hub/auth/whoami with a Bearer token
  * POST /hub/auth/change-password self-service flow (and that it clears
    must_change_password)
  * a protected route (GET /hub/dealers) -> 401 without a token, 200 with a valid
    admin Bearer token
  * break-glass: with HUB_BREAK_GLASS armed the legacy X-NXTDeal-Hub-Key still
    works; with it unset the same key is rejected

Storage is fully isolated: HUB_CREDENTIALS_PATH is monkeypatched into tmp_path and
the module-level credential_store is reset around every test, so nothing here ever
touches the real hub/storage/hub_credentials.json. Run from hub/ with `pytest` (or
`pytest tests/test_hub_auth.py`), same as every other Hub test file.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)

if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)

import pytest
from fastapi.testclient import TestClient

import app
from hub_core.auth import credential_store
from hub_core.secrets import set_backend, EnvVarBackend

_DEV_FALLBACK_KEY = "dev-only-insecure-hub-key-change-me"


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point Hub credential persistence at a throwaway file and start every test
    from an empty credential_store. Also pins the real EnvVarBackend so
    monkeypatch.setenv() is actually seen by get_secret() (a prior test file could
    otherwise have left a FakeBackend swapped in -- see test_hub_secrets.py)."""

    # Authentication tests must never start the unrelated repository-writing auditor.
    monkeypatch.setattr(app, "start_code_auditor_scheduler", lambda: None)
    monkeypatch.setattr(app, "stop_code_auditor_scheduler", lambda: None)
    set_backend(EnvVarBackend())
    credential_store.reset()

    monkeypatch.setattr(app, "HUB_CREDENTIALS_PATH", str(tmp_path / "hub_credentials.json"))
    # Login tests exercise bootstrap, not repository scanning/auto-fixes. The
    # real scheduler runs immediately on lifespan startup and can edit source
    # in a clean checkout, even when storage uses a disposable directory.
    monkeypatch.setattr(app, "start_code_auditor_scheduler", lambda: None)
    monkeypatch.setattr(app, "stop_code_auditor_scheduler", lambda: None)

    yield

    credential_store.reset()
    set_backend(EnvVarBackend())


@pytest.fixture
def seeded_client(isolated_store, monkeypatch):
    """A started TestClient whose lifespan env-seeded a first ADMIN
    (hubadmin / bootstrap-pw-1). Entering the context manager is what triggers
    app.py's lifespan, so the bootstrap runs against the isolated store."""

    monkeypatch.setenv("HUB_ADMIN_USERNAME", "hubadmin")
    monkeypatch.setenv("HUB_ADMIN_PASSWORD", "bootstrap-pw-1")
    # Break-glass off by default unless a test opts in.
    monkeypatch.delenv("HUB_BREAK_GLASS", raising=False)

    with TestClient(app.app) as client:
        yield client


def _login(client, username, password):
    return client.post(
        "/hub/auth/login",
        json={"username": username, "password": password},
    )


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Env-bootstrap
# ---------------------------------------------------------------------------

def test_env_bootstrap_creates_admin(seeded_client):
    record = credential_store.get_record("hubadmin")

    assert record is not None
    assert record["role"] == "ADMIN"
    assert record["must_change_password"] is True
    assert record["created_by"] == "env_bootstrap"


def test_env_bootstrap_is_idempotent_and_does_not_clobber_changed_password(
    isolated_store, monkeypatch
):
    """A second boot must NOT reset the password back to the env value or flip
    must_change_password back to True (the documented 'only seed if absent' choice)."""

    monkeypatch.setenv("HUB_ADMIN_USERNAME", "hubadmin")
    monkeypatch.setenv("HUB_ADMIN_PASSWORD", "bootstrap-pw-1")
    monkeypatch.delenv("HUB_BREAK_GLASS", raising=False)

    # First boot seeds the admin, then the admin changes their own password.
    with TestClient(app.app) as client:
        token = _login(client, "hubadmin", "bootstrap-pw-1").json()["token"]
        resp = client.post(
            "/hub/auth/change-password",
            json={"old_password": "bootstrap-pw-1", "new_password": "chosen-pw-2"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200

    # Second boot (same env) must leave the changed password intact.
    with TestClient(app.app) as client:
        assert _login(client, "hubadmin", "bootstrap-pw-1").status_code == 401
        ok = _login(client, "hubadmin", "chosen-pw-2")
        assert ok.status_code == 200
        assert ok.json()["must_change_password"] is False


def test_no_bootstrap_when_env_absent(isolated_store, monkeypatch):
    monkeypatch.delenv("HUB_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("HUB_ADMIN_PASSWORD", raising=False)

    with TestClient(app.app):
        assert credential_store.get_record("hubadmin") is None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success_returns_token(seeded_client):
    resp = _login(seeded_client, "hubadmin", "bootstrap-pw-1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["role"] == "ADMIN"
    assert body["must_change_password"] is True


def test_login_wrong_password_401(seeded_client):
    assert _login(seeded_client, "hubadmin", "wrong").status_code == 401


def test_login_unknown_user_401(seeded_client):
    assert _login(seeded_client, "nobody", "whatever").status_code == 401


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------

def test_whoami_with_bearer(seeded_client):
    token = _login(seeded_client, "hubadmin", "bootstrap-pw-1").json()["token"]

    resp = seeded_client.get("/hub/auth/whoami", headers=_bearer(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["employee_id"] == "hubadmin"
    assert body["role"] == "ADMIN"
    assert body["must_change_password"] is True


def test_whoami_without_token_401(seeded_client):
    assert seeded_client.get("/hub/auth/whoami").status_code == 401


# ---------------------------------------------------------------------------
# change-password
# ---------------------------------------------------------------------------

def test_change_password_flow(seeded_client):
    token = _login(seeded_client, "hubadmin", "bootstrap-pw-1").json()["token"]

    resp = seeded_client.post(
        "/hub/auth/change-password",
        json={"old_password": "bootstrap-pw-1", "new_password": "brand-new-pw-9"},
        headers=_bearer(token),
    )
    assert resp.status_code == 200

    # Old password no longer works; new one does and clears the forced-change flag.
    assert _login(seeded_client, "hubadmin", "bootstrap-pw-1").status_code == 401
    ok = _login(seeded_client, "hubadmin", "brand-new-pw-9")
    assert ok.status_code == 200
    assert ok.json()["must_change_password"] is False


def test_change_password_wrong_old_400(seeded_client):
    token = _login(seeded_client, "hubadmin", "bootstrap-pw-1").json()["token"]

    resp = seeded_client.post(
        "/hub/auth/change-password",
        json={"old_password": "not-it", "new_password": "brand-new-pw-9"},
        headers=_bearer(token),
    )
    assert resp.status_code == 400


def test_change_password_without_token_401(seeded_client):
    resp = seeded_client.post(
        "/hub/auth/change-password",
        json={"old_password": "x", "new_password": "y"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected route (the admin gate)
# ---------------------------------------------------------------------------

def test_protected_route_requires_token(seeded_client):
    assert seeded_client.get("/hub/dealers").status_code == 401


def test_protected_route_with_admin_bearer(seeded_client):
    token = _login(seeded_client, "hubadmin", "bootstrap-pw-1").json()["token"]

    assert seeded_client.get("/hub/dealers", headers=_bearer(token)).status_code == 200


def test_protected_route_rejects_garbage_bearer(seeded_client):
    assert seeded_client.get(
        "/hub/dealers", headers=_bearer("not-a-real-token")
    ).status_code == 401


def test_root_stays_public(seeded_client):
    assert seeded_client.get("/").status_code == 200


# ---------------------------------------------------------------------------
# Break-glass (env-gated legacy shared key)
# ---------------------------------------------------------------------------

def test_break_glass_off_key_rejected(seeded_client, monkeypatch):
    monkeypatch.delenv("HUB_BREAK_GLASS", raising=False)

    resp = seeded_client.get(
        "/hub/dealers",
        headers={"X-NXTDeal-Hub-Key": _DEV_FALLBACK_KEY},
    )
    assert resp.status_code == 401


def test_break_glass_on_key_works(seeded_client, monkeypatch):
    monkeypatch.setenv("HUB_BREAK_GLASS", "true")
    monkeypatch.setenv("NXTDEAL_HUB_KEY", "real-break-glass-key")

    ok = seeded_client.get(
        "/hub/dealers",
        headers={"X-NXTDeal-Hub-Key": "real-break-glass-key"},
    )
    assert ok.status_code == 200

    # Wrong key still rejected even with break-glass armed.
    bad = seeded_client.get(
        "/hub/dealers",
        headers={"X-NXTDeal-Hub-Key": "wrong-key"},
    )
    assert bad.status_code == 401


def test_break_glass_on_but_no_key_still_401(seeded_client, monkeypatch):
    monkeypatch.setenv("HUB_BREAK_GLASS", "1")

    assert seeded_client.get("/hub/dealers").status_code == 401


def test_password_change_revokes_old_session_and_returns_working_replacement(seeded_client):
    token = _login(seeded_client, 'hubadmin', 'bootstrap-pw-1').json()['token']
    changed = seeded_client.post('/hub/auth/change-password', headers=_bearer(token),
        json={'old_password':'bootstrap-pw-1','new_password':'Changed-fictional-123'})
    assert changed.status_code == 200
    replacement = changed.json()['token']
    assert replacement != token
    for path in ('/hub/dealers', '/hub/auth/whoami'):
        assert seeded_client.get(path, headers=_bearer(token)).status_code == 401
        assert seeded_client.get(path, headers=_bearer(replacement)).status_code == 200
    assert seeded_client.post('/hub/auth/change-password', headers=_bearer(token),
        json={'old_password':'Changed-fictional-123','new_password':'Another-fictional-123'}).status_code == 401


def test_changed_role_and_removed_credentials_revoke_old_admin_session(seeded_client):
    token = _login(seeded_client, 'hubadmin', 'bootstrap-pw-1').json()['token']
    credential_store.get_record('hubadmin')['role'] = 'SALES'
    assert seeded_client.get('/hub/dealers', headers=_bearer(token)).status_code == 401
    assert seeded_client.get('/hub/auth/whoami', headers=_bearer(token)).status_code == 401
    credential_store.get_record('hubadmin')['role'] = 'ADMIN'
    credential_store.credentials.pop('hubadmin')
    assert seeded_client.get('/hub/dealers', headers=_bearer(token)).status_code == 401


def test_session_binding_survives_credential_reload_without_exposing_hash(seeded_client):
    import base64
    import json
    from hub_core.hub_credentials_storage import load_hub_credentials
    token = _login(seeded_client, 'hubadmin', 'bootstrap-pw-1').json()['token']
    payload = json.loads(base64.urlsafe_b64decode(token.split('.')[0]))
    record = credential_store.get_record('hubadmin')
    assert record['hash'] not in json.dumps(payload)
    assert record['salt'] not in json.dumps(payload)
    credential_store.reset()
    load_hub_credentials(app.HUB_CREDENTIALS_PATH)
    assert seeded_client.get('/hub/dealers', headers=_bearer(token)).status_code == 200


def test_signed_legacy_session_without_credential_binding_is_rejected(seeded_client):
    import base64
    import hashlib
    import hmac
    import json
    from hub_core.auth import _secret
    token = _login(seeded_client, 'hubadmin', 'bootstrap-pw-1').json()['token']
    payload = json.loads(base64.urlsafe_b64decode(token.split('.')[0]))
    payload.pop('credential_binding')
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    legacy = encoded + '.' + hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    assert seeded_client.get('/hub/dealers', headers=_bearer(legacy)).status_code == 401


@pytest.mark.parametrize('token', [None, b'bytes.token', 42, 'invalid.\u00e9', '\ud800.signature'])
def test_malformed_token_is_rejected_without_exception(token):
    from hub_core.auth import verify_token
    assert verify_token(token) is None


def test_non_ascii_bearer_header_returns_401_instead_of_server_error(seeded_client):
    headers = {b'authorization': b'Bearer invalid.\xc3\xa9'}
    assert seeded_client.get('/hub/dealers', headers=headers).status_code == 401
    assert seeded_client.get('/hub/auth/whoami', headers=headers).status_code == 401
