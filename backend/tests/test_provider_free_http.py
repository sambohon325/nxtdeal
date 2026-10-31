"""Actual ASGI HTTP routes with fictional auth; no scheduler/provider activation."""
from copy import deepcopy

from fastapi.testclient import TestClient

from api.app import app
from core.auth import credential_store


def test_non_ai_http_login_identity_role_denial_and_revocation():
    previous = deepcopy(credential_store.credentials)
    # Not entering TestClient's context intentionally leaves lifespan schedulers
    # off. This verifies HTTP routing, not background-worker startup readiness.
    client = TestClient(app)
    try:
        credential_store.set_credential('SYN-NO-AI', 'Fictional-no-provider2026!', 'SALES')
        root = client.get('/')
        assert root.status_code == 200
        assert root.json() == {'application': 'NXTDeal', 'status': 'running'}
        login = client.post('/auth/login', json={
            'employee_id': 'SYN-NO-AI', 'password': 'Fictional-no-provider2026!'})
        assert login.status_code == 200
        token = login.json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        identity = client.get('/auth/whoami', headers=headers).json()
        assert identity['employee_id'] == 'SYN-NO-AI'
        assert identity['role'] == 'SALES'
        denied = client.get('/auth/admin/credentials', headers=headers).json()
        assert 'error' in denied
        assert 'credentials' not in denied
        credential_store.set_credential('SYN-NO-AI', 'Changed-fictional2026!', 'SALES')
        assert 'error' in client.get('/auth/whoami', headers=headers).json()
        assert 'error' in client.get('/auth/whoami').json()
    finally:
        client.close()
        credential_store.load_credentials(previous)
