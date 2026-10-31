import base64
import hashlib
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hub_core import mysales_assistants as a, mysales_personal as p

ISSUER='https://hub.example.test'
WEB='https://apps.example.test'
CALLBACK='https://assistant.example.test/callback'
VERIFIER='v'*64

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('NXTDEAL_MYSALES_ENABLED','true')
    monkeypatch.setenv('NXTDEAL_MYSALES_DB',str(tmp_path/'personal.db'))
    monkeypatch.setenv('NXTDEAL_MYSALES_ASSISTANTS_ENABLED','true')
    monkeypatch.setenv('NXTDEAL_MYSALES_ASSISTANT_ISSUER',ISSUER)
    monkeypatch.setenv('NXTDEAL_MYSALES_WEB_ORIGIN',WEB)
    monkeypatch.setenv('NXTDEAL_MYSALES_ASSISTANT_CLIENTS',json.dumps({'test-client':{'provider':'chatgpt','name':'Test assistant','redirect_uris':[CALLBACK]}}))
    app=FastAPI(); app.include_router(p.router); app.include_router(a.router)
    return TestClient(app)

def account(c,email='rep@example.test'):
    r=c.post('/mysales/signup',json={'email':email,'name':'Rep','password':'synthetic-test-password'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def begin(c,scope='summary:read',**overrides):
    query={'client_id':'test-client','redirect_uri':CALLBACK,'state':'client-state','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256','response_type':'code','scope':scope,'resource':ISSUER+'/mysales/mcp'}
    query.update(overrides)
    return c.get('/mysales/oauth/authorize',params=query,follow_redirects=False)

def exchange(c,code,**overrides):
    data={'grant_type':'authorization_code','client_id':'test-client','redirect_uri':CALLBACK,'code':code,'code_verifier':VERIFIER,'resource':ISSUER+'/mysales/mcp'}
    data.update(overrides)
    return c.post('/mysales/oauth/token',data=data)

def link(c,h,scope='summary:read'):
    r=begin(c,scope); assert r.status_code==302,r.text
    handle=parse_qs(urlsplit(r.headers['location']).query)['connect'][0]
    details=c.get('/mysales/assistants/request/'+handle,headers=h)
    assert details.status_code==200
    r=c.post('/mysales/assistants/request/'+handle,headers=h,json={'approve':True})
    assert r.status_code==200,r.text
    code=parse_qs(urlsplit(r.json()['redirect']).query)['code'][0]
    result=exchange(c,code); assert result.status_code==200,result.text
    return result.json(),code,handle

def rpc(c,t,method='tools/list',params=None,**headers):
    return c.post('/mysales/mcp',headers={'Authorization':'Bearer '+t,**headers},json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})

def test_metadata_pkce_and_single_use(client):
    h=account(client); t,code,handle=link(client,h)
    assert client.get('/.well-known/oauth-authorization-server').json()['code_challenge_methods_supported']==['S256']
    assert client.get('/.well-known/oauth-protected-resource/mysales/mcp').json()['resource']==ISSUER+'/mysales/mcp'
    assert exchange(client,code).status_code==400
    assert client.post('/mysales/assistants/request/'+handle,headers=h,json={'approve':True}).status_code==404
    assert rpc(client,t['access_token'],'initialize',{'protocolVersion':'2025-06-18'}).json()['result']['protocolVersion']=='2025-06-18'
    names=[v['name'] for v in rpc(client,t['access_token']).json()['result']['tools']]
    assert names==['mysales_summary']
    assert rpc(client,t['access_token'],'tools/call',{'name':'mysales_contacts'}).json()['error']['code']==-32602
    assert client.get('/mysales/me',headers={'Authorization':'Bearer '+t['access_token']}).status_code==401
    assert rpc(client,h['Authorization'][7:]).status_code==401

@pytest.mark.parametrize('override',[{'redirect_uri':'https://attacker.example.test/'},{'client_id':'other'},{'resource':'https://other.example.test/mcp'},{'code_challenge_method':'plain'},{'scope':'staff:admin'},{'state':''},{'code_challenge':'bad'}])
def test_reject_invalid_authorization(client,override):
    assert begin(client,**override).status_code==400

def test_consent_required_bad_verifier_and_decline(client):
    h=account(client)
    r=begin(client); handle=parse_qs(urlsplit(r.headers['location']).query)['connect'][0]
    assert client.get('/mysales/assistants/request/'+handle).status_code==401
    assert exchange(client,handle).status_code==400
    r=client.post('/mysales/assistants/request/'+handle,headers=h,json={'approve':False})
    assert parse_qs(urlsplit(r.json()['redirect']).query)['error']==['access_denied']
    r=begin(client); handle=parse_qs(urlsplit(r.headers['location']).query)['connect'][0]
    r=client.post('/mysales/assistants/request/'+handle,headers=h,json={'approve':True})
    code=parse_qs(urlsplit(r.json()['redirect']).query)['code'][0]
    assert exchange(client,code,code_verifier='x'*64).status_code==400
    assert exchange(client,code,redirect_uri='https://attacker.example.test').status_code==400
    assert exchange(client,code).status_code==200

def test_owner_isolation_idempotency_and_audit(client):
    h=account(client); other=account(client,'other@example.test')
    client.post('/mysales/records/contacts',headers=other,json={'title':'Other private person'})
    t,_,_=link(client,h,'summary:read contacts:read tasks:read tasks:write')
    token=t['access_token']
    assert json.loads(rpc(client,token,'tools/call',{'name':'mysales_contacts'}).json()['result']['content'][0]['text'])['items']==[]
    params={'name':'mysales_create_followup','arguments':{'title':'Private followup','notes':'Sensitive notes','request_id':'retry-test-001'}}
    first=rpc(client,token,'tools/call',params).json()['result']; assert not first['isError']
    assert first['structuredContent']['created'] is True
    again=rpc(client,token,'tools/call',params).json()['result']['structuredContent']; assert again['created'] is False
    assert first['structuredContent']['id']==again['id']
    params['arguments']['title']='Different'
    assert rpc(client,token,'tools/call',params).json()['result']['isError'] is True
    assert len(client.get('/mysales/records/tasks',headers=h).json()['items'])==1
    assert client.get('/mysales/records/tasks',headers=other).json()['items']==[]
    status=client.get('/mysales/assistants',headers=h).json()
    assert 'Sensitive notes' not in json.dumps(status)
    grant=status['connections'][0]['id']
    assert client.delete('/mysales/assistants/'+grant,headers=other).status_code==404
    assert client.delete('/mysales/assistants/'+grant,headers=h).status_code==200
    assert rpc(client,token).status_code==401

def test_refresh_rotation_expiry_and_revocation(client):
    h=account(client); t,_,_=link(client,h)
    form={'grant_type':'refresh_token','client_id':'test-client','refresh_token':t['refresh_token'],'resource':ISSUER+'/mysales/mcp'}
    refreshed=client.post('/mysales/oauth/token',data=form)
    assert refreshed.status_code==200
    assert client.post('/mysales/oauth/token',data=form).status_code==400
    assert rpc(client,t['access_token']).status_code==401
    token=refreshed.json()['access_token']
    assert rpc(client,token).status_code==200
    assert client.post('/mysales/oauth/revoke',data={'client_id':'test-client','token':token}).status_code==200
    assert rpc(client,token).status_code==401
    t,_,_=link(client,h)
    with p.database() as con: con.execute('UPDATE assistant_tokens SET expires=0')
    assert rpc(client,t['access_token']).status_code==401

def test_disabled_removed_client_origin_and_payload_limits(client,monkeypatch):
    h=account(client); t,_,_=link(client,h)
    assert rpc(client,t['access_token'],Origin='https://untrusted.example.test').status_code==403
    assert client.post('/mysales/mcp',headers={'Authorization':'Bearer '+t['access_token']},content='x'*17000).status_code==413
    assert client.post('/mysales/mcp',headers={'Authorization':'Bearer '+t['access_token']},json=[]).status_code==400
    monkeypatch.setenv('NXTDEAL_MYSALES_ASSISTANTS_ENABLED','false')
    assert rpc(client,t['access_token']).status_code==503
    status=client.get('/mysales/assistants',headers=h).json(); assert status['available'] is False
    assert client.delete('/mysales/assistants/'+status['connections'][0]['id'],headers=h).status_code==200

def test_no_plaintext_tokens_and_restart(client):
    h=account(client); t,_,_=link(client,h)
    with p.database() as con:
        data=' '.join(r['hash'] for r in con.execute('SELECT hash FROM assistant_tokens'))
    assert t['access_token'] not in data and t['refresh_token'] not in data
    app=FastAPI(); app.include_router(p.router); app.include_router(a.router)
    assert rpc(TestClient(app),t['access_token']).status_code==200

def test_record_validation_and_inventory_honesty(client):
    h=account(client); t,_,_=link(client,h,'tasks:write inventory:read')
    result=rpc(client,t['access_token'],'tools/call',{'name':'mysales_inventory_connection'}).json()['result']['structuredContent']
    assert result['connection'] is None and result['feed_verified'] is False
    for args in [{'title':'Task','request_id':'valid-id-001','due':'not-a-date'},{'title':'Task','request_id':'valid-id-001','owner':'another'},{'title':'','request_id':'valid-id-001'}]:
        assert rpc(client,t['access_token'],'tools/call',{'name':'mysales_create_followup','arguments':args}).json()['result']['isError']

def test_retail_feed_projection_no_credentials_or_redirects(client,monkeypatch):
    h=account(client); t,_,_=link(client,h,'inventory:read')
    monkeypatch.setattr(p,'connection',lambda owner:{'name':'Test Dealer','api_base_url':'https://api.example.test'})
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,n):
            assert n==512001
            return json.dumps({'read_only':True,'as_of':'2026-10-06T10:00:00Z','items':[{'id':'V1','make':'Test','price':21000,'cost':16000,'customer':'private'}]}).encode()
    class Opener:
        def open(self,request,timeout):
            assert timeout==8
            assert request.full_url=='https://api.example.test/public/mysales/inventory'
            assert not request.has_header('Authorization') and not request.has_header('Cookie')
            return Response()
    def opener(*handlers):
        assert any(isinstance(handler,a.NoRedirect) for handler in handlers)
        return Opener()
    monkeypatch.setattr(a,'build_opener',opener)
    result=rpc(client,t['access_token'],'tools/call',{'name':'mysales_inventory'}).json()['result']['structuredContent']
    assert result['items']==[{'id':'V1','make':'Test','price':21000}]
    assert result['as_of']=='2026-10-06T10:00:00Z'
    def unavailable(*args): raise a.URLError('internal-address-must-not-leak')
    monkeypatch.setattr(a,'build_opener',unavailable)
    result=rpc(client,t['access_token'],'tools/call',{'name':'mysales_inventory'}).json()['result']
    assert result['isError'] is True and 'internal-address' not in json.dumps(result)

def test_rate_limit_and_removed_registration(client,monkeypatch):
    h=account(client); t,_,_=link(client,h)
    a.rate_limit('test-budget',1)
    with pytest.raises(a.HTTPException) as e: a.rate_limit('test-budget',1)
    assert e.value.status_code==429
    monkeypatch.setenv('NXTDEAL_MYSALES_ASSISTANT_CLIENTS',json.dumps({'replacement':{'provider':'claude','name':'Other assistant','redirect_uris':[CALLBACK]}}))
    assert rpc(client,t['access_token']).status_code==401
