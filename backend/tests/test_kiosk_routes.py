from copy import deepcopy
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import auth
from core.kiosk_sessions import KioskSessions
from core.kiosk_checkin import KioskCheckin
from api.routers.kiosk import create_kiosk_router


@pytest.fixture
def context():
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-ADMIN', 'Fictional2026!', 'ADMIN', must_change_password=False)
    auth.credential_store.set_credential('SYN-SALES', 'Fictional2026!', 'SALES')
    admin = auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    sessions = KioskSessions('synthetic-a')
    writes = []
    adapter = KioskCheckin(sessions, lambda identity, fields: writes.append(fields))
    app = FastAPI()
    app.include_router(create_kiosk_router(sessions, enabled=True, checkin=adapter))
    with TestClient(app) as client:
        yield client, sessions, adapter, admin, writes
    auth.credential_store.load_credentials(previous)


def headers(token):
    return {'Authorization': 'Bearer ' + token}


def test_existing_staff_session_cannot_manage_kiosk_without_fresh_login(context):
    client, sessions, _, admin, _ = context
    grant = sessions.issue(admin, 'lobby')
    ordinary = auth.issue_token('SYN-ADMIN', 'ADMIN')
    for action in ('enroll', 'revoke'):
        response = client.post('/kiosk/' + action, headers=headers(ordinary), json={'device_id': 'lobby'})
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'
    assert sessions.verify(grant['token'], device_id='lobby', action=sessions.ACTION)


def enroll(client, admin):
    result = client.post('/kiosk/enroll', headers=headers(admin), json={'device_id': 'lobby'})
    assert result.status_code == 201
    assert result.headers['cache-control'] == 'no-store'
    return result.json()['token']


def body():
    return {'device_id': 'lobby', 'request_id': str(uuid.uuid4()), 'name': 'Fictional Visitor'}


def test_factory_disabled_by_default(context):
    _, sessions, _, _, _ = context
    app = FastAPI()
    app.include_router(create_kiosk_router(sessions))
    with TestClient(app) as client:
        assert client.post('/kiosk/enroll', json={'device_id': 'lobby'}).status_code == 404
        assert client.post('/kiosk/checkin', json=body()).status_code == 404


@pytest.mark.parametrize('kind,status', [('none', 401), ('sales', 403), ('mfa', 401)])
def test_enrollment_and_revocation_authorization(context, kind, status):
    client, _, _, _, writes = context
    token = {'none': '', 'sales': auth.issue_token('SYN-SALES', 'SALES', fresh_auth=True),
             'mfa': auth.issue_mfa_challenge_token('SYN-ADMIN', 'ADMIN')}[kind]
    for path in ('enroll', 'revoke'):
        result = client.post('/kiosk/' + path, headers=headers(token), json={'device_id': 'lobby'})
        assert result.status_code == status
        assert result.headers['cache-control'] == 'no-store'
    assert not writes


def test_http_flow_duplicate_conflict_revocation_and_minimal_receipt(context):
    client, _, _, admin, writes = context
    token = enroll(client, admin)
    data = body()
    for _ in range(2):
        result = client.post('/kiosk/checkin', headers=headers(token), json=data)
        assert result.status_code == 200
        assert result.json() == {'status': 'checked_in', 'receipt': data['request_id']}
    assert len(writes) == 1
    conflict = client.post('/kiosk/checkin', headers=headers(token), json={**data, 'name': 'Changed'})
    assert conflict.status_code == 409
    assert 'Changed' not in conflict.text
    assert client.post('/kiosk/revoke', headers=headers(token), json={'device_id': 'lobby'}).status_code == 401
    assert client.post('/kiosk/revoke', headers=headers(admin), json={'device_id': 'lobby'}).status_code == 200
    assert client.post('/kiosk/checkin', headers=headers(token), json=data).status_code == 401
    assert len(writes) == 1


@pytest.mark.parametrize('data,status', [('{',400), ('[]',422),
    ('{"device_id":"lobby","device_id":"other"}',400),
    ('{"name":NaN}',400), ('{"name":"' + 'x'*5000 + '"}',413)])
def test_bounded_json_and_no_echo(context, data, status):
    client, _, _, admin, writes = context
    token = enroll(client, admin)
    result = client.post('/kiosk/checkin', headers={**headers(token), 'Content-Type':'application/json'}, content=data)
    assert result.status_code == status
    assert result.headers['cache-control'] == 'no-store'
    assert len(result.content) < 100
    assert not writes


def test_fields_privacy_and_no_query_auth(context):
    client, _, _, admin, writes = context
    token = enroll(client, admin)
    assert client.post('/kiosk/checkin?token=' + token, json=body()).status_code == 401
    assert client.post('/kiosk/checkin', headers=headers(admin), json=body()).status_code == 401
    for extra in ({'name': 123}, {'name': 'x'*121}, {'tenant_id':'other'}, {'assigned_to':'SYN-ADMIN'}):
        result = client.post('/kiosk/checkin', headers=headers(token), json={**body(), **extra})
        assert result.status_code == 422
        assert result.json() == {'error':'invalid_fields'}
    assert client.post('/kiosk/checkin', headers=headers(token), content='text').status_code == 415
    assert not writes


def test_http_throttle_and_unknown_write_do_not_claim_success(context):
    client, _, adapter, admin, writes = context
    token = enroll(client, admin)
    adapter.MAX_PER_MINUTE = 1
    def fail(identity, fields):
        writes.append(fields)
        raise OSError('private internal path or data')
    adapter._writer = fail
    data = body()
    for _ in range(2):
        result = client.post('/kiosk/checkin', headers=headers(token), json=data)
        assert result.status_code == 503
        assert result.json()['retry_safe'] is False
        assert 'private' not in result.text
        assert result.headers['cache-control'] == 'no-store'
    limited = client.post('/kiosk/checkin', headers=headers(token), json=body())
    assert limited.status_code == 429
    assert limited.headers['retry-after'] == '60'
    assert len(writes) == 1

def test_pending_password_change_cannot_manage_or_use_kiosk(context):
    from core import auth_api
    client, sessions, _, admin, writes = context
    grant = enroll(client, admin)
    auth.credential_store.get_record('SYN-ADMIN')['must_change_password'] = True
    pending = auth_api.login('SYN-ADMIN', 'Fictional2026!')
    assert pending['must_change_password'] is True
    for action in ('enroll', 'revoke'):
        response = client.post('/kiosk/' + action, headers=headers(pending['token']),
                               json={'device_id': 'lobby'})
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'
    response = client.post('/kiosk/checkin', headers=headers(grant), json=body())
    assert response.status_code == 401
    assert not writes
    assert not sessions._grants
