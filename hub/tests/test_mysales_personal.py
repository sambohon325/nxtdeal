import os, sqlite3
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hub_core.mysales_personal import router, digest
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('NXTDEAL_MYSALES_ENABLED','true');monkeypatch.setenv('NXTDEAL_MYSALES_DB',str(tmp_path/'personal.db'))
    app=FastAPI();app.include_router(router);return TestClient(app)
def signup(c,email='rep@example.test'):
    r=c.post('/mysales/signup',json={'name':'Rep','email':email,'password':'Local-test-password-123'});assert r.status_code==200,r.text;return r.json()
def headers(a):return {'Authorization':'Bearer '+a['token']}
def test_signup_session_persistence_revocation(client):
    a=signup(client);assert a['account']['email_verified'] is False
    con=sqlite3.connect(os.environ['NXTDEAL_MYSALES_DB']);assert con.execute('SELECT hash FROM sessions').fetchone()[0]==digest(a['token']);con.close()
    app=FastAPI();app.include_router(router);again=TestClient(app)
    assert again.get('/mysales/me',headers=headers(a)).status_code==200
    assert again.post('/mysales/logout',headers=headers(a)).status_code==200
    assert client.get('/mysales/me',headers=headers(a)).status_code==401
    assert client.post('/mysales/login',json={'email':'REP@example.test','password':'Local-test-password-123'}).status_code==200
def test_ownership_and_auth_boundaries(client):
    a,b=signup(client),signup(client,'other@example.test')
    r=client.post('/mysales/records/contacts',headers=headers(a),json={'title':'Private'}).json()
    assert client.get('/mysales/records/contacts',headers=headers(b)).json()=={'items':[]}
    assert client.put('/mysales/records/contacts/'+r['id'],headers=headers(b),json={'title':'Stolen'}).status_code==404
    assert client.get('/mysales/records/contacts').status_code==401
    assert client.get('/mysales/me',headers={'Authorization':'Bearer staff-token'}).status_code==401
    assert client.post('/mysales/records/connection',headers=headers(a),json={'title':'fake'}).status_code==404
def test_throttle_disabled_and_expiry(client,monkeypatch):
    a=signup(client)
    con=sqlite3.connect(os.environ['NXTDEAL_MYSALES_DB']);con.execute('UPDATE sessions SET expires=0');con.commit();con.close()
    assert client.get('/mysales/me',headers=headers(a)).status_code==401
    for _ in range(10):assert client.post('/mysales/login',json={'email':'none@example.test','password':'wrong'}).status_code==401
    assert client.post('/mysales/login',json={'email':'none@example.test','password':'wrong'}).status_code==429
    monkeypatch.setenv('NXTDEAL_MYSALES_ENABLED','false')
    assert client.post('/mysales/signup',json={'email':'fresh@example.test','name':'Rep','password':'Local-test-password-123'}).status_code==503
def test_optional_connection_preserves_account(client,monkeypatch):
    from hub_core import mysales_personal as m
    a=signup(client);monkeypatch.setattr(m,'resolve_connection',lambda value:{'dealer_id':value,'name':'Dealer','api_base_url':'https://api.example.test'})
    for dealer in ('DLR-A','DLR-B'):
        assert client.put('/mysales/inventory-connection',headers=headers(a),json={'dealership':dealer}).status_code==200
        assert client.get('/mysales/me',headers=headers(a)).json()['id']==a['account']['id']
    assert client.get('/mysales/inventory-connection',headers=headers(a)).json()['dealer_id']=='DLR-B'
    assert client.delete('/mysales/inventory-connection',headers=headers(a)).status_code==200
    assert client.get('/mysales/inventory-connection',headers=headers(a)).json() is None

def test_dealer_resolution_rejects_unknown_suspended_and_insecure(client,monkeypatch):
    from types import SimpleNamespace
    from hub_core import dealers_api
    from hub_core.dealer_registry import registry
    a=signup(client)
    monkeypatch.setattr(registry,'get',lambda key:None)
    monkeypatch.setattr(registry,'get_by_slug',lambda key:None)
    assert client.put('/mysales/inventory-connection',headers=headers(a),json={'dealership':'unknown'}).status_code==404
    dealer=SimpleNamespace(dealer_id='D1',status='suspended',name='Dealer')
    monkeypatch.setattr(registry,'get',lambda key:dealer)
    assert client.put('/mysales/inventory-connection',headers=headers(a),json={'dealership':'D1'}).status_code==404
    dealer.status='active'
    monkeypatch.setattr(dealers_api,'resolve_dealer_api',lambda key:{'api_base_url':'http://insecure.example'})
    assert client.put('/mysales/inventory-connection',headers=headers(a),json={'dealership':'D1'}).status_code==409
    assert client.get('/mysales/inventory-connection',headers=headers(a)).json() is None

def test_page_publication_is_explicit_and_snapshot_based(client):
    a=signup(client);b=signup(client,'second@example.test')
    slug=client.get('/mysales/page',headers=headers(a)).json()['slug']
    public='/mysales/public/pages/'+slug
    assert client.get(public).status_code==404
    draft={'headline':'Meet Jordan','email':'public@example.test','bio':'First draft'}
    assert client.put('/mysales/page',headers=headers(a),json=draft).status_code==200
    assert client.get(public).status_code==404
    assert client.put('/mysales/page/publication',headers=headers(a),json={'published':True}).status_code==200
    assert client.get(public).json()['bio']=='First draft'
    draft['bio']='Private unfinished edits'
    client.put('/mysales/page',headers=headers(a),json=draft)
    assert client.get(public).json()['bio']=='First draft'
    assert client.get('/mysales/page',headers=headers(b)).json()['draft']['bio']==''
    assert 'account' not in client.get(public).json()
    assert 'draft' not in client.get(public).json()
    assert client.put('/mysales/page/publication',headers=headers(b),json={'published':False}).status_code==409
    client.put('/mysales/page/publication',headers=headers(a),json={'published':False})
    assert client.get(public).status_code==404

def test_page_rejects_unsafe_links_and_never_autopublishes_login_email(client):
    a=signup(client)
    assert client.get('/mysales/page',headers=headers(a)).json()['draft']['email']==''
    for link in ['javascript:alert(1)','https://user:pass@example.test','http://example.test','https://example.test/ has-space']:
        assert client.put('/mysales/page',headers=headers(a),json={'headline':'Page','calendar_link':link}).status_code==422

def test_sqlite_backup_restores_personal_records_and_sessions(client,tmp_path,monkeypatch):
    a=signup(client)
    client.post('/mysales/records/tasks',headers=headers(a),json={'title':'Follow up tomorrow'})
    backup=tmp_path/'restored.db'
    with sqlite3.connect(os.environ['NXTDEAL_MYSALES_DB']) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
        assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    monkeypatch.setenv('NXTDEAL_MYSALES_DB',str(backup))
    assert client.get('/mysales/me',headers=headers(a)).status_code==200
    assert client.get('/mysales/records/tasks',headers=headers(a)).json()['items'][0]['title']=='Follow up tomorrow'
