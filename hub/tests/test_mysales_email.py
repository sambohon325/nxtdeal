import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hub_core import mysales_personal as personal, mysales_email as email, mysales_assistants as assistants


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('NXTDEAL_MYSALES_ENABLED', 'true')
    monkeypatch.setenv('NXTDEAL_MYSALES_DB', str(tmp_path/'accounts.db'))
    monkeypatch.setenv('NXTDEAL_MYSALES_EMAIL_ENABLED', 'true')
    monkeypatch.setenv('NXTDEAL_MYSALES_SMTP_USERNAME', 'sender@example.test')
    monkeypatch.setenv('NXTDEAL_MYSALES_SMTP_PASSWORD', 'fixture')
    mail = []
    monkeypatch.setattr(email, 'send_email', lambda address, purpose, token: mail.append((address, purpose, token)))
    app = FastAPI(); app.include_router(personal.router)
    client = TestClient(app)
    def signup(address):
        result = client.post('/mysales/signup', json={'name':'Fixture', 'email':address, 'password':'Original-password-123'})
        assert result.status_code == 200
        return result.json()
    a, b = signup('a@example.test'), signup('b@example.test')
    return client, mail, a, b


def headers(account):
    return {'Authorization': 'Bearer '+account['token']}


def test_disabled_and_unknown_account(setup, monkeypatch):
    client, mail, a, _ = setup
    known = client.post('/mysales/password/request', json={'email':'a@example.test'})
    unknown = client.post('/mysales/password/request', json={'email':'unknown@example.test'})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mail) == 1
    assert mail[0][2] not in known.text
    monkeypatch.setenv('NXTDEAL_MYSALES_EMAIL_ENABLED', 'false')
    assert client.get('/mysales/email/status').json() == {'available':False}
    assert client.post('/mysales/password/request', json={'email':'a@example.test'}).status_code == 503
    assert client.post('/mysales/email/request', headers=headers(a)).status_code == 503
    assert len(mail) == 1


def test_verification_owner_purpose_expiry_and_replay(setup):
    client, mail, a, b = setup
    assert client.post('/mysales/email/request', headers=headers(a)).status_code == 202
    code = mail[-1][2]
    with personal.database() as con:
        assert con.execute('SELECT hash FROM email_challenges').fetchone()[0] == personal.digest(code)
    assert client.post('/mysales/email/verify', headers=headers(b), json={'code':code}).status_code == 400
    assert client.post('/mysales/password/reset', json={'code':code,'password':'New-password-123'}).status_code == 400
    assert client.post('/mysales/email/verify', headers=headers(a), json={'code':code}).status_code == 200
    assert client.get('/mysales/me', headers=headers(a)).json()['email_verified'] is True
    assert client.get('/mysales/me', headers=headers(b)).json()['email_verified'] is False
    assert client.post('/mysales/email/verify', headers=headers(a), json={'code':code}).status_code == 400
    client.post('/mysales/email/request', headers=headers(b))
    with personal.database() as con: con.execute('UPDATE email_challenges SET expires=0')
    assert client.post('/mysales/email/verify', headers=headers(b), json={'code':mail[-1][2]}).status_code == 400


def test_reset_revokes_only_owner_and_all_old_proofs(setup):
    client, mail, a, b = setup
    client.post('/mysales/records/contacts', headers=headers(a), json={'title':'Keep this contact'})
    with personal.database() as con:
        assistants.schema(con)
        for label, account in [('a',a),('b',b)]:
            con.execute('INSERT INTO assistant_grants VALUES (?,?,?,?,?,0)',(label,account['account']['id'],'fixture','tasks:read',1))
            con.execute('INSERT INTO assistant_requests VALUES (?,?,?,?,?,?,?,?,?,0)',(label,'fixture','https://example.test','state','challenge','tasks:read',9999999999,account['account']['id'],label))
    client.post('/mysales/email/request', headers=headers(a)); verify = mail[-1][2]
    client.post('/mysales/password/request', json={'email':'a@example.test'}); code = mail[-1][2]
    result = client.post('/mysales/password/reset', json={'code':code,'password':'Replacement-password-123'})
    assert result.status_code == 200
    assert client.get('/mysales/me',headers=headers(a)).status_code == 401
    assert client.get('/mysales/me',headers=headers(b)).status_code == 200
    assert client.post('/mysales/password/reset', json={'code':code,'password':'Replacement-password-456'}).status_code == 400
    assert client.post('/mysales/login',json={'email':'a@example.test','password':'Original-password-123'}).status_code == 401
    restored = client.post('/mysales/login',json={'email':'a@example.test','password':'Replacement-password-123'}).json()
    assert restored['account']['email_verified'] is True
    assert client.get('/mysales/records/contacts',headers=headers(restored)).json()['items'][0]['title'] == 'Keep this contact'
    assert client.post('/mysales/email/verify', headers=headers(restored), json={'code':verify}).status_code == 400
    with personal.database() as con:
        assert dict(con.execute('SELECT id,revoked FROM assistant_grants')) == {'a':1,'b':0}
        assert [r[0] for r in con.execute('SELECT id FROM assistant_requests')] == ['b']


def test_resend_replaces_code_and_failed_delivery_invalidates(setup, monkeypatch):
    client, mail, _, _ = setup
    for _ in range(2): client.post('/mysales/password/request', json={'email':'a@example.test'})
    assert client.post('/mysales/password/reset', json={'code':mail[0][2],'password':'Replacement-password-123'}).status_code == 400
    def fail(*args): raise RuntimeError('secret SMTP details')
    monkeypatch.setattr(email, 'send_email', fail)
    result = client.post('/mysales/password/request',json={'email':'a@example.test'})
    assert result.status_code == 202 and 'secret' not in result.text
    with personal.database() as con: assert con.execute('SELECT count(*) FROM email_challenges').fetchone()[0] == 0


def test_concurrent_reset_is_single_use(setup):
    client, mail, _, _ = setup
    client.post('/mysales/password/request', json={'email':'a@example.test'})
    def reset(_):
        return client.post('/mysales/password/reset',json={'code':mail[-1][2],'password':'Replacement-password-123'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset, range(2))) == [200,400]
