import copy
import pytest
from core import auth, auth_api


@pytest.mark.parametrize('operation', ['create', 'reset', 'list', 'unlock', 'lockout', 'allowlist', 'mfa'])
def test_temporary_admin_cannot_manage_credentials(monkeypatch, operation):
    store = auth.credential_store
    store.reset()
    store.set_credential('TEMP-ADMIN', 'Synthetic-password!42', 'ADMIN', must_change_password=True)
    store.set_credential('TARGET', 'Synthetic-target!42', 'SALES', must_change_password=False)
    token = auth.issue_token('TEMP-ADMIN', 'ADMIN', fresh_auth=True)
    before = copy.deepcopy(store.credentials)
    def forbidden(*args, **kwargs):
        pytest.fail('Denied request attempted persistence')
    monkeypatch.setattr(auth_api, 'save_credentials', forbidden)
    monkeypatch.setattr(auth_api, 'save_audit_log', forbidden)
    calls = {
        'create': lambda: auth_api.create_credential(token, 'NEW', 'ADMIN'),
        'reset': lambda: auth_api.reset_password(token, 'TARGET'),
        'list': lambda: auth_api.list_credentials(token),
        'unlock': lambda: auth_api.unlock_account(token, 'TARGET'),
        'lockout': lambda: auth_api.get_lockout_status(token, 'TARGET'),
        'allowlist': lambda: auth_api.set_ip_allowlist(token, 'TARGET', []),
        'mfa': lambda: auth_api.admin_disable_mfa(token, 'TARGET'),
    }
    try:
        assert 'error' in calls[operation]()
        assert store.credentials == before
    finally:
        store.reset()


@pytest.mark.parametrize('role', ['ADMIN', 'SALES', 'SERVICE'])
def test_temporary_session_denied_business_access_but_can_change_password(monkeypatch, role):
    from api.deps import _authenticate, _require_admin, _authorize_dashboard
    store = auth.credential_store
    previous = copy.deepcopy(store.credentials)
    store.set_credential('TEMP-STAFF', 'Synthetic-password!42', role, must_change_password=True)
    monkeypatch.setattr(auth_api, 'save_credentials', lambda *args: None)
    monkeypatch.setattr(auth_api, 'save_audit_log', lambda *args: None)
    try:
        token = auth.issue_token('TEMP-STAFF', role)
        header = 'Bearer ' + token
        for call in [lambda: _authenticate(header), lambda: _require_admin(header),
                     lambda: _authorize_dashboard(header, 'sales')]:
            assert call() == (None, {'error': 'Password change required'})
        assert auth_api.whoami(token)['employee_id'] == 'TEMP-STAFF'
        assert auth_api.whoami(token)['must_change_password'] is True
        changed = auth_api.change_password(token, 'Synthetic-password!42', 'Replacement-password!43')
        assert changed['success']
        assert auth_api.whoami(changed['token'])['must_change_password'] is False
        assert _authenticate('Bearer ' + changed['token'])[1] is None
        assert _authenticate(header)[1] is not None
    finally:
        store.load_credentials(previous)


def test_temporary_http_session_cannot_read_business_data_or_mutate():
    from fastapi.testclient import TestClient
    from api.app import app
    from core.dealeros import ledger
    store = auth.credential_store
    previous = copy.deepcopy(store.credentials)
    store.set_credential('TEMP-HTTP', 'Synthetic-password!42', 'ADMIN', must_change_password=True)
    token = auth.issue_token('TEMP-HTTP', 'ADMIN')
    before = copy.deepcopy({key: vars(value) for key, value in ledger.get_all().items()})
    client = TestClient(app)
    try:
        headers = {'Authorization': 'Bearer ' + token}
        assert client.get('/compliance/security-review', headers=headers).json() == {
            'error': 'Password change required'}
        assert client.post('/deals/NONEXISTENT-ONBOARDING/fund', headers=headers, json={}).json() == {
            'error': 'Password change required'}
        assert client.get('/auth/whoami', headers=headers).json()['employee_id'] == 'TEMP-HTTP'
        assert {key: vars(value) for key, value in ledger.get_all().items()} == before
    finally:
        client.close()
        store.load_credentials(previous)
