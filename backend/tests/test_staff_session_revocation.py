"""Dealer staff sessions and pending MFA must follow current credentials."""
import base64
from copy import deepcopy
import hashlib
import hmac
import json

import pytest
from core import auth, auth_api
from api.deps import _require_admin


@pytest.fixture(autouse=True)
def fictional_staff(monkeypatch):
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-ADMIN', 'FictionalPassword2026!', 'ADMIN', must_change_password=False)
    monkeypatch.setattr(auth_api, 'save_credentials', lambda *args: None)
    monkeypatch.setattr(auth_api, 'save_audit_log', lambda *args: None)
    yield
    auth.credential_store.load_credentials(previous)


@pytest.mark.parametrize('issuer', [auth.issue_token, auth.issue_mfa_challenge_token])
@pytest.mark.parametrize('mutation', ['password', 'role', 'remove'])
def test_credential_change_revokes_session_and_pending_mfa(issuer, mutation):
    token = issuer('SYN-ADMIN', 'ADMIN')
    assert auth.verify_token(token)
    if mutation == 'password':
        auth.credential_store.set_credential('SYN-ADMIN', 'DifferentFictional2026!', 'ADMIN', must_change_password=False)
    elif mutation == 'role':
        auth.credential_store.set_role('SYN-ADMIN', 'SALES')
    else:
        auth.credential_store.reset()
    assert auth.verify_token(token) is None
    assert _require_admin('Bearer '+token)[1]


def test_password_change_returns_replacement_and_revokes_old_admin():
    token = auth.issue_token('SYN-ADMIN', 'ADMIN')
    result = auth_api.change_password(token, 'FictionalPassword2026!', 'DifferentFictional2026!')
    assert result['success']
    assert _require_admin('Bearer '+token)[1]
    assert _require_admin('Bearer '+result['token'])[1] is None


def test_challenge_cannot_change_password():
    token = auth.issue_mfa_challenge_token('SYN-ADMIN', 'ADMIN')
    assert 'error' in auth_api.change_password(token, 'FictionalPassword2026!', 'DifferentFictional2026!')


def test_credential_reload_preserves_bound_session():
    token = auth.issue_token('SYN-ADMIN', 'ADMIN')
    records = json.loads(json.dumps(auth.credential_store.credentials))
    auth.credential_store.reset()
    auth.credential_store.load_credentials(records)
    assert auth.verify_token(token)
    payload = base64.urlsafe_b64decode(token.split('.')[0]).decode()
    assert records['SYN-ADMIN']['hash'] not in payload
    assert records['SYN-ADMIN']['salt'] not in payload


def test_signed_legacy_token_is_rejected():
    token = auth.issue_token('SYN-ADMIN', 'ADMIN')
    payload = json.loads(base64.urlsafe_b64decode(token.split('.')[0]))
    del payload['credential_binding']
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(auth._secret(), encoded.encode(), hashlib.sha256).hexdigest()
    assert auth.verify_token(encoded+'.'+signature) is None


@pytest.mark.parametrize("action", [
    lambda token: auth_api.whoami(token),
    lambda token: auth_api.create_credential(token, "SYN-NEW", "ADMIN"),
    lambda token: auth_api.reset_password(token, "SYN-ADMIN"),
    lambda token: auth_api.list_credentials(token),
    lambda token: auth_api.admin_disable_mfa(token, "SYN-ADMIN"),
    lambda token: auth_api.get_lockout_status(token, "SYN-ADMIN"),
    lambda token: auth_api.unlock_account(token, "SYN-ADMIN"),
    lambda token: auth_api.set_ip_allowlist(token, "SYN-ADMIN", []),
])
def test_mfa_challenge_cannot_authenticate_staff_account_actions(action):
    before = deepcopy(auth.credential_store.credentials)
    token = auth.issue_mfa_challenge_token("SYN-ADMIN", "ADMIN")
    assert action(token) == {"error": "Invalid or expired token"}
    assert auth.credential_store.credentials == before



def test_messaging_websocket_rejects_pending_mfa():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from api.app import app
    # Importing app can load credentials; install this isolated test identity last.
    auth.credential_store.set_credential("SYN-ADMIN", "FictionalPassword2026!", "ADMIN")
    token = auth.issue_mfa_challenge_token("SYN-ADMIN", "ADMIN")
    with pytest.raises(WebSocketDisconnect) as denied:
        with TestClient(app).websocket_connect("/ws/messaging?token="+token):
            pytest.fail("Pending MFA challenge was accepted as a websocket session")
    assert denied.value.code == 4401

@pytest.mark.parametrize('mutation', ['password', 'role', 'remove'])
def test_http_routes_reject_revoked_staff_session(mutation):
    from fastapi.testclient import TestClient
    from api.app import app
    auth.credential_store.set_credential(
        'SYN-ADMIN', 'FictionalPassword2026!', 'ADMIN', must_change_password=False
    )
    client = TestClient(app)
    login = client.post('/auth/login', json={'employee_id': 'SYN-ADMIN', 'password': 'FictionalPassword2026!'})
    assert login.status_code == 200, login.text
    token = login.json()['token']
    headers = {'Authorization': 'Bearer '+token}
    assert isinstance(client.get('/auth/admin/credentials', headers=headers).json(), list)
    if mutation == 'password':
        response = client.post('/auth/change-password', headers=headers,
                               json={'old_password': 'FictionalPassword2026!',
                                     'new_password': 'DifferentFictional2026!'})
        assert response.status_code == 200 and response.json()['success'], response.text
        replacement = {'Authorization': 'Bearer '+response.json()['token']}
        assert isinstance(client.get('/auth/admin/credentials', headers=replacement).json(), list)
    elif mutation == 'role':
        auth.credential_store.set_role('SYN-ADMIN', 'SALES')
    else:
        auth.credential_store.reset()
    # The legacy account API uses an error body; Bridge uses an HTTP status.
    denied = client.get('/auth/admin/credentials', headers=headers)
    assert denied.json() == {'error': 'Invalid or expired token'}
    assert client.get('/dealer-bridge/system-map', headers=headers).status_code == 401
    client.close()

@pytest.mark.parametrize('mutation', ['password', 'role', 'remove', 'expire'])
def test_open_socket_stops_receiving_after_revocation(mutation, monkeypatch):
    import asyncio
    from core.ws_manager import ConnectionManager

    class Socket:
        def __init__(self):
            self.sent, self.closed = [], None
        async def accept(self):
            pass
        async def close(self, code):
            self.closed = code
        async def send_json(self, payload):
            self.sent.append(payload)

    async def scenario():
        manager = ConnectionManager()
        old, fresh = Socket(), Socket()
        token = auth.issue_token('SYN-ADMIN', 'ADMIN')
        assert await manager.connect('SYN-ADMIN', old, token)
        await manager.send_to_employee('SYN-ADMIN', {'event': 'before'})
        assert old.sent == [{'event': 'before'}]
        if mutation == 'password':
            auth.credential_store.set_credential('SYN-ADMIN', 'DifferentFictional2026!', 'ADMIN', must_change_password=False)
        elif mutation == 'role':
            auth.credential_store.set_role('SYN-ADMIN', 'SALES')
        elif mutation == 'remove':
            auth.credential_store.reset()
        else:
            now = auth.time.time()
            monkeypatch.setattr(auth.time, 'time', lambda: now + auth.TOKEN_TTL_SECONDS + 1)
        if mutation != 'remove':
            role = auth.credential_store.get_record('SYN-ADMIN')['role']
            assert await manager.connect('SYN-ADMIN', fresh, auth.issue_token('SYN-ADMIN', role))
        await manager.broadcast_direct_message('SYN-ADMIN', 'SYN-ADMIN', {'event': 'after'})
        assert old.sent == [{'event': 'before'}]
        assert old.closed == 4401
        assert old not in manager.connections.get('SYN-ADMIN', [])
        assert old not in manager._session_tokens
        if mutation != 'remove':
            assert fresh.sent == [{'event': 'after'}]
            assert fresh.closed is None
        manager.reset()
        assert not manager._session_tokens
    asyncio.run(scenario())

@pytest.mark.parametrize('kind', ['mismatched_employee', 'mfa_challenge', 'malformed', 'revoked'])
def test_socket_registration_rejects_invalid_session_before_accept(kind):
    import asyncio
    from core.ws_manager import ConnectionManager

    class Socket:
        accepted = False
        closed = None
        async def accept(self):
            self.accepted = True
        async def close(self, code):
            self.closed = code

    async def scenario():
        manager, socket = ConnectionManager(), Socket()
        token = auth.issue_token('SYN-ADMIN', 'ADMIN')
        employee = 'SYN-ADMIN'
        if kind == 'mismatched_employee':
            employee = 'SYN-OTHER'
        elif kind == 'mfa_challenge':
            token = auth.issue_mfa_challenge_token('SYN-ADMIN', 'ADMIN')
        elif kind == 'malformed':
            token = 'fictional.invalid'
        else:
            auth.credential_store.reset()
        assert await manager.connect(employee, socket, token) is False
        assert not socket.accepted
        assert socket.closed == 4401
        assert not manager.connections
        assert not manager._session_tokens
    asyncio.run(scenario())


def test_failed_socket_delivery_cleans_up_without_blocking_other_connections():
    import asyncio
    from core.ws_manager import ConnectionManager

    class Socket:
        def __init__(self, fail=False):
            self.fail, self.sent = fail, []
        async def accept(self):
            pass
        async def close(self, code):
            self.closed = code
        async def send_json(self, payload):
            if self.fail:
                raise RuntimeError('Fictional disconnected socket')
            self.sent.append(payload)

    async def scenario():
        manager = ConnectionManager()
        failed, healthy = Socket(True), Socket()
        token = auth.issue_token('SYN-ADMIN', 'ADMIN')
        for socket in (failed, healthy):
            assert await manager.connect('SYN-ADMIN', socket, token)
        await manager.send_to_employee('SYN-ADMIN', {'event': 'fictional'})
        assert healthy.sent == [{'event': 'fictional'}]
        assert manager.connections == {'SYN-ADMIN': [healthy]}
        assert failed not in manager._session_tokens
        manager.disconnect('SYN-ADMIN', healthy)
        assert not manager.connections and not manager._session_tokens
    asyncio.run(scenario())

@pytest.mark.parametrize('issuer', [auth.issue_token, auth.issue_mfa_challenge_token])
def test_role_round_trip_does_not_revive_old_sessions(issuer):
    token = issuer('SYN-ADMIN', 'ADMIN')
    auth.credential_store.set_role('SYN-ADMIN', 'SALES')
    assert auth.verify_token(token) is None
    auth.credential_store.set_role('SYN-ADMIN', 'ADMIN')
    records = json.loads(json.dumps(auth.credential_store.credentials))
    auth.credential_store.reset()
    auth.credential_store.load_credentials(records)
    assert auth.verify_token(token) is None
    assert auth.verify_token(issuer('SYN-ADMIN', 'ADMIN'))


@pytest.mark.parametrize('mutation', ['password', 'role', 'remove', 'expire'])
def test_idle_socket_revocation_without_any_broadcast(mutation, monkeypatch):
    import asyncio
    from core.ws_manager import ConnectionManager

    async def scenario():
        receiving = asyncio.Event()

        class Socket:
            closed = None
            async def accept(self):
                pass
            async def receive(self):
                receiving.set()
                await asyncio.Event().wait()
            async def close(self, code):
                self.closed = code

        manager, socket = ConnectionManager(), Socket()
        manager.SESSION_CHECK_SECONDS = 0.01
        assert await manager.connect('SYN-ADMIN', socket, auth.issue_token('SYN-ADMIN', 'ADMIN'))
        task = asyncio.create_task(manager.listen('SYN-ADMIN', socket))
        await asyncio.wait_for(receiving.wait(), 1)
        if mutation == 'password':
            auth.credential_store.set_credential('SYN-ADMIN', 'ChangedFictional2026!', 'ADMIN')
        elif mutation == 'role':
            auth.credential_store.set_role('SYN-ADMIN', 'SALES')
        elif mutation == 'remove':
            auth.credential_store.reset()
        else:
            now = auth.time.time()
            monkeypatch.setattr(auth.time, 'time', lambda: now + auth.TOKEN_TTL_SECONDS + 1)
        await asyncio.wait_for(task, 1)
        assert socket.closed == 4401
        assert not manager.connections and not manager._session_tokens

    asyncio.run(scenario())


@pytest.mark.parametrize('exit_kind', ['disconnect', 'error', 'cancel'])
def test_socket_listener_releases_registration_on_every_exit(exit_kind):
    import asyncio
    from starlette.websockets import WebSocketDisconnect
    from core.ws_manager import ConnectionManager

    async def scenario():
        receiving = asyncio.Event()

        class Socket:
            async def accept(self):
                pass
            async def receive(self):
                receiving.set()
                if exit_kind == 'disconnect':
                    raise WebSocketDisconnect()
                if exit_kind == 'error':
                    raise RuntimeError('Fictional transport error')
                await asyncio.Event().wait()

        manager, socket = ConnectionManager(), Socket()
        assert await manager.connect('SYN-ADMIN', socket, auth.issue_token('SYN-ADMIN', 'ADMIN'))
        task = asyncio.create_task(manager.listen('SYN-ADMIN', socket))
        await asyncio.wait_for(receiving.wait(), 1)
        if exit_kind == 'cancel':
            task.cancel()
        expected = {'disconnect': WebSocketDisconnect, 'error': RuntimeError,
                    'cancel': asyncio.CancelledError}[exit_kind]
        with pytest.raises(expected):
            await task
        assert not manager.connections and not manager._session_tokens

    asyncio.run(scenario())


def test_healthy_idle_socket_survives_rechecks_and_still_receives_events(monkeypatch):
    import asyncio
    from core import ws_manager
    from core.ws_manager import ConnectionManager

    async def scenario():
        rechecked = asyncio.Event()
        checks = 0
        real_verify = ws_manager.verify_token

        def verify(token):
            nonlocal checks
            checks += 1
            if checks >= 4:
                rechecked.set()
            return real_verify(token)

        monkeypatch.setattr(ws_manager, 'verify_token', verify)

        class Socket:
            def __init__(self):
                self.receives, self.sent = 0, []
            async def accept(self):
                pass
            async def receive(self):
                self.receives += 1
                await asyncio.Event().wait()
            async def send_json(self, payload):
                self.sent.append(payload)

        manager, socket = ConnectionManager(), Socket()
        manager.SESSION_CHECK_SECONDS = 0.01
        assert await manager.connect('SYN-ADMIN', socket, auth.issue_token('SYN-ADMIN', 'ADMIN'))
        task = asyncio.create_task(manager.listen('SYN-ADMIN', socket))
        try:
            await asyncio.wait_for(rechecked.wait(), 1)
            assert not task.done()
            assert socket.receives == 1
            await manager.send_to_employee('SYN-ADMIN', {'event': 'still-connected'})
            assert socket.sent == [{'event': 'still-connected'}]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not manager.connections and not manager._session_tokens

    asyncio.run(scenario())


def test_messaging_route_closes_idle_revoked_session(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app
    from core.ws_manager import manager

    auth.credential_store.set_credential('SYN-ADMIN', 'FictionalPassword2026!', 'ADMIN', must_change_password=False)
    token = auth.issue_token('SYN-ADMIN', 'ADMIN')
    monkeypatch.setattr(manager, 'SESSION_CHECK_SECONDS', 0.01)
    with TestClient(app).websocket_connect('/ws/messaging?token=' + token) as socket:
        registered = set(manager.connections['SYN-ADMIN'])
        auth.credential_store.set_role('SYN-ADMIN', 'SALES')
        event = socket.receive()
        assert event['type'] == 'websocket.close'
        assert event['code'] == 4401
    assert not manager.connections.get('SYN-ADMIN')
    assert not registered.intersection(manager._session_tokens)
