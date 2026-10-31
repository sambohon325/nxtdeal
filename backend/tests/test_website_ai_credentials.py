import json
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from test_website_studio import site
from core import website_ai_credentials as vault

class Provider:
    def __init__(self,fail=False):
        self.fail=fail;self.calls=[];self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if self.fail:raise RuntimeError('SECRET must never leave provider boundary')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"reply_text":"connected"}'))])

@pytest.fixture
def encrypted(tmp_path,monkeypatch):
    monkeypatch.setenv('DEALEROS_AI_CREDENTIAL_KEY',Fernet.generate_key().decode())
    monkeypatch.setattr(vault,'storage_dir',lambda:str(tmp_path))
    return tmp_path

def test_save_reload_encryption_scope_rotate_disconnect(encrypted,monkeypatch):
    key='synthetic-private-key-123456'
    result=vault.save('one','openai','gpt-4o-mini',key)
    assert result['status']=='saved' and key not in json.dumps(result)
    assert key.encode() not in vault._path('one').read_bytes()
    assert vault.status('two')['configured'] is False
    assert vault.status('one')['configured'] is True
    provider=Provider();monkeypatch.setattr(vault,'_client',lambda data:provider)
    assert vault.test_connection('one')['status']=='connected'
    assert provider.calls[0]['messages']==[{'role':'user','content':'Return JSON with reply_text set to connected.'}]
    assert vault.completion('one',messages=[]).choices
    vault.save('one','openai','gpt-4o-mini','synthetic-replacement-key')
    with pytest.raises(ValueError):vault.completion('one',messages=[])
    assert vault.disconnect('one')['configured'] is False
    assert not vault._path('one').exists()

def test_failure_and_missing_storage_fail_closed(encrypted,monkeypatch):
    vault.save('one','openai','gpt-4o-mini','synthetic-private-key')
    monkeypatch.setattr(vault,'_client',lambda data:Provider(fail=True))
    result=vault.test_connection('one');assert result['status']=='test_failed' and 'SECRET' not in json.dumps(result)
    monkeypatch.delenv('DEALEROS_AI_CREDENTIAL_KEY')
    with pytest.raises(ValueError):vault.save('two','openai','gpt-4o-mini','synthetic-private-key')
    assert not vault._path('two').exists()

def test_changed_credentials_cannot_inherit_old_success(encrypted,monkeypatch):
    vault.save('one','openai','gpt-4o-mini','synthetic-private-key')
    provider=Provider()
    def construct(data):
        vault.disconnect('one');vault.save('one','openai','gpt-4o-mini','synthetic-new-private-key')
        return provider
    monkeypatch.setattr(vault,'_client',construct)
    with pytest.raises(ValueError,match='changed'):vault.test_connection('one')
    assert vault.status('one')['status']=='saved'

def test_http_admin_only_no_public_key(encrypted,site,monkeypatch):
    from api.app import app
    from fastapi.testclient import TestClient
    from core.auth import credential_store
    from copy import deepcopy
    previous=deepcopy(credential_store.credentials)
    c=TestClient(app)
    try:
        headers={}
        for actor,role in [('SYN-API-ADMIN','ADMIN'),('SYN-API-SALES','SALES')]:
            credential_store.set_credential(actor,'Synthetic-password2026!',role,must_change_password=False)
            token=c.post('/auth/login',json={'employee_id':actor,'password':'Synthetic-password2026!'}).json()['token']
            headers[role]={'Authorization':'Bearer '+token}
        path='/websites/'+site.id+'/assistant-connection';body={'provider':'openai','model':'gpt-4o-mini','api_key':'synthetic-private-key'}
        assert 'error' in c.put(path,json=body).json()
        assert 'error' in c.put(path,json=body,headers=headers['SALES']).json()
        assert body['api_key'] not in c.put(path,json={'api_key':body['api_key']},headers=headers['ADMIN']).text
        saved=c.put(path,json=body,headers=headers['ADMIN']).json();assert saved['configured'] and body['api_key'] not in json.dumps(saved)
        monkeypatch.setattr(vault,'_client',lambda data:Provider())
        assert c.post(path+'/test',headers=headers['ADMIN']).json()['status']=='connected'
        assert 'api_key' not in c.get(path,headers=headers['ADMIN']).text
        assert body['api_key'] not in c.get('/websites/'+site.id,headers=headers['ADMIN']).text
        assert c.delete(path,headers=headers['ADMIN']).json()['configured'] is False
    finally:c.close();credential_store.load_credentials(previous)
