import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from core import lobby_information as lobby, system_config
from core.dealeros import ledger

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(system_config, 'save_graph', lambda *a: None)
    yield
    ledger.reset()

def test_anonymous_empty_read_never_creates_settings():
    assert lobby.get_public_lobby()=={'published':False,'content':{}}
    assert ledger.get_entity(system_config._CONFIG_ID) is None

def test_draft_publication_allowlist_and_unpublish():
    content={'lounge':'  Upstairs  ','guest_wifi':'Ask the service desk for guest access.'}
    assert lobby.update_lobby_settings('ADMIN','EMP1',content,False)['published'] is False
    assert lobby.get_public_lobby()['content']=={}
    lobby.update_lobby_settings('OPERATIONS','EMP2',content,True)
    entity=ledger.get_entity(system_config._CONFIG_ID)
    entity.attributes['lobby_information']['private_secret']='never expose'
    public=lobby.get_public_lobby()
    assert public=={'published':True,'content':{'lounge':'Upstairs','guest_wifi':content['guest_wifi']}}
    assert lobby.get_lobby_settings('ADMIN')['updated_by']=='EMP2'
    lobby.update_lobby_settings('ADMIN','EMP1',content,False)
    assert lobby.get_public_lobby()['content']=={}

@pytest.mark.parametrize('role',['SALES','SERVICE','FINANCE','MARKETING',None,''])
def test_non_admin_cannot_read_draft_or_mutate(role):
    assert 'error' in lobby.get_lobby_settings(role)
    assert 'error' in lobby.update_lobby_settings(role,'EMP',{'welcome':'Hi'},True)
    assert ledger.get_entity(system_config._CONFIG_ID) is None

@pytest.mark.parametrize('content,published',[({'password':'secret'},True),({'lounge':5},False),({'lounge':'x'*1001},False),({},True),({'welcome':'Hi'},'true')])
def test_invalid_changes_do_not_create_settings(content,published):
    assert 'error' in lobby.update_lobby_settings('ADMIN','EMP',content,published)
    assert ledger.get_entity(system_config._CONFIG_ID) is None

def test_failed_save_restores_previously_published_content(monkeypatch):
    lobby.update_lobby_settings('ADMIN','EMP',{'lounge':'Original'},True)
    def failed(*a): raise OSError('save failed')
    monkeypatch.setattr(system_config,'save_graph',failed)
    with pytest.raises(OSError): lobby.update_lobby_settings('ADMIN','EMP',{'lounge':'Changed'},False)
    assert lobby.get_public_lobby()['content']=={'lounge':'Original'}
