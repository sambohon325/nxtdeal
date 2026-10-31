"""User credential mutations must not accept integration keys or stale sessions."""
import importlib
import pytest
from core import auth, api_keys
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE
app = importlib.import_module('api.app')

@pytest.fixture
def actor(monkeypatch):
    ledger.reset()
    auth.credential_store.reset()
    auth.credential_store.set_credential('ADMIN-SYNTHETIC', 'Synthetic-password-only!42', 'ADMIN', must_change_password=False)
    ledger.add_entity(Entity('ADMIN-SYNTHETIC', EMPLOYEE, {}))
    monkeypatch.setattr(api_keys, 'save_graph', lambda *_: None)
    calls=[]
    monkeypatch.setattr(app, 'create_user_api', lambda *a: calls.append(a) or {'ok':True})
    monkeypatch.setattr(app, 'update_user_role_api', lambda *a: calls.append(a) or {'ok':True})
    yield calls
    ledger.reset()
    auth.credential_store.reset()

@pytest.mark.parametrize('mode', ['key','stale','fresh','mfa_incomplete'])
@pytest.mark.parametrize('route', ['create','role'])
def test_user_mutations_require_recent_interactive_admin(actor, monkeypatch, mode, route):
    if mode == 'key':
        token=api_keys.generate_api_key('ADMIN-SYNTHETIC','Synthetic','ADMIN-SYNTHETIC')['raw_key']
    else:
        token=auth.issue_token('ADMIN-SYNTHETIC','ADMIN',fresh_auth=mode!='stale')
    if mode == 'mfa_incomplete':
        monkeypatch.setattr(auth.credential_store,'is_mfa_enabled',lambda *_:True)
    if route == 'create':
        result=app.users_create(app.CreateUserRequest(first_name='Synthetic',last_name='User',email='',role='SALES'), 'Bearer '+token)
    else:
        result=app.users_update_role('TARGET-SYNTHETIC',app.UpdateUserRoleRequest(new_role='ADMIN'), 'Bearer '+token)
    if mode == 'fresh':
        assert result == {'ok':True} and len(actor)==1
    else:
        assert result.get('code') == 'fresh_login_required'
        assert actor == []
