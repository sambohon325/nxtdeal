import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from api.routers import system_config as routes
from core import system_config, system_config_api
from core.dealeros import ledger

@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(system_config,'save_graph',lambda *a:None)
    def auth(value):
        return ({'role':value,'employee_id':'SERVER_EMP'},None) if value else (None,{'error':'Sign in required'})
    monkeypatch.setattr(routes,'_authenticate',auth)
    app=FastAPI();app.include_router(routes.router)
    yield TestClient(app)
    ledger.reset()

def test_draft_publish_unpublish_and_server_editor(client):
    payload={'content':{'lounge':'Upstairs'},'published':False}
    r=client.put('/system-config/lobby',headers={'Authorization':'ADMIN'},json=payload)
    assert r.status_code==200 and r.json()['updated_by']=='SERVER_EMP'
    assert client.get('/public/lobby').json()=={'published':False,'content':{}}
    payload['published']=True
    assert client.put('/system-config/lobby',headers={'Authorization':'OPERATIONS'},json=payload).status_code==200
    public=client.get('/public/lobby')
    assert public.headers['cache-control']=='no-store'
    assert public.json()=={'published':True,'content':{'lounge':'Upstairs'}}
    payload['published']=False
    client.put('/system-config/lobby',headers={'Authorization':'ADMIN'},json=payload)
    assert client.get('/public/lobby').json()['content']=={}
    assert 'lobby_information' not in system_config_api.get_system_config_api('SERVICE')
    assert 'lobby_information' in system_config_api.get_system_config_api('ADMIN')

@pytest.mark.parametrize('role,status',[(None,401),('SERVICE',403),('SALES',403),('UNKNOWN',403)])
def test_unauthorized_cannot_read_or_write(client,role,status):
    headers={'Authorization':role} if role else {}
    assert client.get('/system-config/lobby',headers=headers).status_code==status
    assert client.put('/system-config/lobby',headers=headers,json={'content':{'welcome':'Hi'},'published':True}).status_code==status
    assert ledger.get_entity(system_config._CONFIG_ID) is None

@pytest.mark.parametrize('payload,status',[
    ({'content':{'unknown':'value'},'published':True},400),
    ({'content':{},'published':True},400),
    ({'content':{'welcome':5},'published':False},422),
    ({'content':{'welcome':'Hi'},'published':'true'},422),
    ({'content':{'welcome':'Hi'},'published':True,'employee_id':'FORGED'},422),
])
def test_invalid_payload_cannot_publish(client,payload,status):
    assert client.put('/system-config/lobby',headers={'Authorization':'ADMIN'},json=payload).status_code==status
    assert client.get('/public/lobby').json()['content']=={}
