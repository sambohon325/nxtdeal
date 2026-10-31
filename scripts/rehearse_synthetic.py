"""Repeatable synthetic sign-in, owner-isolation and graph recovery rehearsal.

Runs native application code in fresh child processes with private fixture stores.
Does not send provider messages, start schedulers or certify production recovery.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from synthetic_dealership import clean_environment, ROOT, PASSWORD


def dealer_rehearsal():
    from fastapi.testclient import TestClient
    from api.app import app
    from core.dealeros import ledger
    from core.entities import Entity
    from core import data_backup
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    client = TestClient(app)  # No context manager: do not run scheduler lifespan.
    assert client.get('/dealer-bridge/system-map').status_code == 401
    logins = {}
    for i in range(1, 8):
        response = client.post('/auth/login', json={'employee_id':f'EMP-{i:05}', 'password':PASSWORD})
        assert response.status_code == 200, response.status_code
        token = response.json()['token']
        logins[i] = {'Authorization':'Bearer '+token}
        assert client.get('/search?q=Fictional', headers=logins[i]).status_code == 200
    assert client.get('/dealer-bridge/system-map', headers=logins[1]).status_code == 200
    assert client.get('/dealer-bridge/system-map', headers=logins[3]).status_code == 403
    inventory = client.get('/menu/data?department=Inventory&item_key=inventory', headers=logins[3])
    assert inventory.status_code == 200
    assert 'Fictional' in inventory.text and '20100' in inventory.text
    day = client.get('/sales/my-day', headers=logins[3])
    assert day.status_code == 200 and 'Fictional Lead 1' in day.text
    visitor = client.post('/up-system/log', headers=logins[1],
                          json={'up_type':'walk_in','first_name':'Synthetic Visitor','phone':None,'email':None})
    assert visitor.status_code == 200 and visitor.json().get('assigned_to') == 'EMP-00003', visitor.text
    before = json.loads(Path(GRAPH_PATH).read_text())
    backup = data_backup.create_backup('EMP-00001', 'Synthetic recovery rehearsal')
    assert 'error' not in backup
    ledger.add_entity(Entity(id='SYN-AFTER-BACKUP', entity_type='Customer', attributes={'synthetic':True}))
    save_graph(GRAPH_PATH)
    assert 'SYN-AFTER-BACKUP' in Path(GRAPH_PATH).read_text()
    result = data_backup.restore_backup(backup['id'], 'EMP-00002')
    assert 'error' not in result
    assert ledger.get_entity('SYN-AFTER-BACKUP') is None
    assert json.loads(Path(GRAPH_PATH).read_text()) == before
    print(json.dumps({'stage':'dealer', 'staff_logins':7, 'bridge_role_boundary':'passed',
                      'graph_restore':'passed', 'entities':len(before['entities'])}))


def dealer_restart():
    from fastapi.testclient import TestClient
    from api.app import app
    from core.dealeros import ledger
    assert ledger.get_entity('SYN-AFTER-BACKUP') is None
    assert ledger.get_entity('CUST-00001').attributes['synthetic'] is True
    response = TestClient(app).post('/auth/login', json={'employee_id':'EMP-00001','password':PASSWORD})
    assert 'token' in response.json()
    print(json.dumps({'stage':'dealer_restart', 'restored_graph_and_login':'passed'}))


def service_rehearsal(restart=False):
    from fastapi.testclient import TestClient
    from api.app import app
    client = TestClient(app)
    def login(employee):
        value = client.post('/auth/login', json={'employee_id':employee, 'password':PASSWORD}).json()
        return {'Authorization':'Bearer '+value['token']}
    service = login('EMP-00005')
    state_path = Path('service-rehearsal.json')
    if restart:
        state = json.loads(state_path.read_text())
        ro_id, item_key = state['ro_id'], state['item_key']
        inspection = client.get(f'/repair-orders/{ro_id}/inspection', headers=service).json()
        assert inspection['status'] == 'completed'
        assert inspection['items'][item_key]['status'] == 'red'
        assert inspection['items'][item_key]['concern_created'] is True
        workspace = client.get(f'/repair-orders/{ro_id}', headers=service).json()
        assert len(workspace['concerns']) == state['concerns']
        print(json.dumps({'stage':'service_restart', 'inspection_and_concern_persistence':'passed'}))
        return
    sales = login('EMP-00003')
    ro = client.post('/repair-orders', headers=service, json={
        'vehicle_id':'VEH-00001', 'customer_id':'CUST-00001',
        'description':'Fictional service inspection rehearsal'}).json()
    assert 'error' not in ro, ro
    ro_id = ro['id']
    path = f'/repair-orders/{ro_id}/inspection'
    assert 'error' in client.post(path+'/start', headers=sales).json()
    started = client.post(path+'/start', headers=service).json()
    assert started['status'] == 'in_progress'
    item_key = next(iter(started['items']))
    for key in started['items']:
        result = client.post(path+'/item', headers=service, json={
            'item_key':key, 'status':'red' if key == item_key else 'green',
            'notes':'Fictional inspection finding' if key == item_key else ''}).json()
        assert 'error' not in result, result
    assert 'error' in client.post(path+'/item', headers=service,
                                 json={'item_key':item_key, 'status':'invalid', 'notes':''}).json()
    completed = client.post(path+'/complete', headers=service).json()
    assert completed['status'] == 'completed' and completed['summary']['red'] == 1
    converted = client.post(path+'/create-concerns', headers=service,
                            json={'item_keys':[item_key]}).json()
    assert converted['created_concerns_for'] == [item_key]
    count = len(converted['workspace']['concerns'])
    repeated = client.post(path+'/create-concerns', headers=service,
                           json={'item_keys':[item_key]}).json()
    assert repeated['created_concerns_for'] == []
    assert repeated['already_had_concerns'] == [item_key]
    assert len(repeated['workspace']['concerns']) == count
    state_path.write_text(json.dumps({'ro_id':ro_id, 'item_key':item_key, 'concerns':count}))
    print(json.dumps({'stage':'service', 'inspection_items':len(started['items']),
                      'sales_write_denial':'passed', 'inspection_to_concern_retry':'passed'}))


def customer_rehearsal(restart=False):
    from fastapi.testclient import TestClient
    from api.app import app
    from uuid import uuid4
    client = TestClient(app)  # No scheduler or provider lifespan.
    state_path = Path('customer-rehearsal.json')
    if restart:
        state = json.loads(state_path.read_text())
        for token in state['revoked']:
            assert 'error' in client.get('/customer/me', headers={'Authorization':'Bearer '+token}).json()
        for account in state['accounts']:
            login = client.post('/public/customer/login', json={'email':account['email'], 'password':PASSWORD})
            headers = {'Authorization':'Bearer '+login.json()['account']['token']}
            me = client.get('/customer/me', headers=headers).json()['account']
            assert me['account_id'] == account['account_id'] and me['linked'] is False
        from core.dealeros import ledger
        locked = state['accounts'][-1]
        challenge = ledger.get_entity(locked['account_id']).attributes['challenges']['email']
        rejected = client.post('/customer/link/confirm', headers=headers,
                               json={'channel':'email', 'code':challenge['code']}).json()
        assert 'Too many attempts' in rejected.get('error', ''), rejected
        print(json.dumps({'stage':'customer_restart', 'login_and_revoked_sessions_persist':'passed',
                          'verification_attempt_limit_persisted':'passed'}))
        return
    accounts = []
    for i in range(2):
        email = f'synthetic-customer-{uuid4().hex}@example.test'
        response = client.post('/public/customer/signup', json={
            'email':email, 'password':PASSWORD, 'name':f'Fictional Customer Account {i}'})
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['match_found'] is False
        accounts.append(value['account'])
    first, second = [{'Authorization':'Bearer '+a['token']} for a in accounts]
    for headers, account in zip((first, second), accounts):
        me = client.get('/customer/me', headers=headers).json()['account']
        assert me['account_id'] == account['account_id'] and me['linked'] is False
        assert client.get('/dealer-bridge/system-map', headers=headers).status_code == 401
    assert accounts[0]['account_id'] != accounts[1]['account_id']
    assert 'error' in client.post('/public/customer/login', json={
        'email':accounts[0]['email'], 'password':'WrongFictional2026!'}).json()
    assert 'error' in client.post('/public/customer/signup', json={
        'email':accounts[0]['email'], 'password':PASSWORD}).json()
    again = client.post('/public/customer/login', json={
        'email':accounts[0]['email'], 'password':PASSWORD}).json()['account']['token']
    logout = client.post('/customer/logout', headers=first)
    assert logout.status_code == 200 and 'error' not in logout.json()
    for token in (accounts[0]['token'], again):
        assert 'error' in client.get('/customer/me', headers={'Authorization':'Bearer '+token}).json()
    assert client.get('/customer/me', headers=second).json()['account']['account_id'] == accounts[1]['account_id']
    # A matching CRM contact is not proof of ownership. Stub an acknowledged
    # provider delivery; production must continue rejecting simulated delivery.
    from unittest.mock import patch
    from core import customer_accounts
    from core.dealeros import ledger
    from core.entities import Entity
    matched_email = f'synthetic-matched-{uuid4().hex}@example.test'
    customer_id = f'SYN-MATCH-{uuid4().hex}'
    ledger.add_entity(Entity(id=customer_id, entity_type='Customer',
                            attributes={'name':'Fictional Matched Customer', 'email':matched_email,
                                        'synthetic':True}))
    with patch.object(customer_accounts.integrations_registry, 'is_live', return_value=True), \
         patch.object(customer_accounts.integrations_registry, 'send_notification',
                      return_value={'simulated':False, 'sent':True}) as delivery:
        signup = client.post('/public/customer/signup', json={
            'email':matched_email, 'password':PASSWORD, 'name':'Fictional Matched Customer'}).json()
        assert signup['match_found'] is True and not signup.get('dev_code')
        matched = signup['account']
        headers = {'Authorization':'Bearer '+matched['token']}
        requested = client.post('/customer/link/request-code', headers=headers, json={'channel':'email'}).json()
        assert requested.get('delivery') == 'sent' and not requested.get('dev_code'), requested
        assert delivery.call_count == 2
        assert all(call.args[0] == matched_email for call in delivery.call_args_list)
    challenge = ledger.get_entity(matched['account_id']).attributes['challenges']['email']
    wrong = '111111' if challenge['code'] != '111111' else '222222'
    assert 'error' in client.post('/customer/link/confirm', headers=headers,
                                  json={'channel':'email', 'code':wrong}).json()
    assert client.post('/customer/link/confirm', headers=headers,
                       json={'channel':'email', 'code':'not-a-code'}).status_code == 422
    # A code belongs to its account, and expiry must reject even the correct code.
    peer = client.post('/customer/link/confirm', headers=second,
                       json={'channel':'email', 'code':challenge['code']}).json()
    assert 'error' in peer
    assert client.get('/customer/me', headers=second).json()['account']['linked'] is False
    with patch.object(customer_accounts.time, 'time', return_value=challenge['expires_at'] + 1):
        expired = client.post('/customer/link/confirm', headers=headers,
                              json={'channel':'email', 'code':challenge['code']}).json()
        assert 'expired' in expired.get('error', ''), expired
    for _ in range(customer_accounts.OTP_MAX_ATTEMPTS - challenge['attempts']):
        assert 'error' in client.post('/customer/link/confirm', headers=headers,
                                     json={'channel':'email', 'code':wrong}).json()
    locked = client.post('/customer/link/confirm', headers=headers,
                         json={'channel':'email', 'code':challenge['code']}).json()
    assert 'Too many attempts' in locked.get('error', ''), locked
    me = client.get('/customer/me', headers=headers).json()['account']
    assert me['linked'] is False and me['linked_customer_id'] is None
    for route in ('vehicles', 'service', 'messages', 'approvals', 'status'):
        denied = client.get('/public/garage/'+route, params={'token':matched['token']})
        assert denied.status_code == 503 and denied.json()['reason'] == 'provider_unavailable'
    accounts.append(matched)
    state_path.write_text(json.dumps({'accounts':[{'email':a['email'], 'account_id':a['account_id']} for a in accounts],
                                     'revoked':[accounts[0]['token'], again]}))
    print(json.dumps({'stage':'customer', 'accounts':len(accounts), 'matched_without_proof':'unlinked',
                      'disabled_garage_boundary':'passed', 'separate_identity_and_staff_denial':'passed',
                      'expired_code_attempt_limit_and_peer_rejection':'passed',
                      'logout_revokes_all_own_sessions':'passed', 'peer_session_preserved':'passed',
                      'provider_delivery':'not_exercised'}))


def personal_rehearsal():
    from fastapi.testclient import TestClient
    from synthetic_hub import app
    import sqlite3
    from uuid import uuid4
    client = TestClient(app)
    accounts=[]
    for _ in range(2):
        email=f'{uuid4().hex}@example.test'
        result=client.post('/mysales/signup',json={'name':'Synthetic Rep','email':email,'password':PASSWORD})
        assert result.status_code == 200
        accounts.append(result.json())
    first,other=[{'Authorization':'Bearer '+a['token']} for a in accounts]
    row=client.post('/mysales/records/contacts',headers=first,json={'title':'Fictional Buyer'}).json()
    assert 'id' in row
    assert client.get('/mysales/records/contacts',headers=other).json()['items'] == []
    assert client.put('/mysales/records/contacts/'+row['id'],headers=other,
                      json={'title':'Should not change'}).status_code == 404
    assert client.post('/mysales/logout',headers=first).status_code == 200
    assert client.get('/mysales/me',headers=first).status_code == 401
    root=Path(os.environ['NXTDEAL_MYSALES_DB'])
    # SQLite online backup API, never copy a live database file.
    recovered=root.with_name('mysales-recovered.sqlite3')
    with sqlite3.connect(root) as source, sqlite3.connect(recovered) as destination:
        source.backup(destination)
    os.environ['NXTDEAL_MYSALES_DB']=str(recovered)
    restored=TestClient(app)
    login=restored.post('/mysales/login',json={'email':accounts[0]['account']['email'],'password':PASSWORD})
    headers={'Authorization':'Bearer '+login.json()['token']}
    assert restored.get('/mysales/records/contacts',headers=headers).json()['items'][0]['id']==row['id']
    assert restored.get('/mysales/me',headers=first).status_code == 401
    print(json.dumps({'stage':'personal', 'signup_owner_isolation_logout':'passed',
                      'sqlite_backup_recovery':'passed', 'provider_delivery':'not_exercised'}))


def bridge_rehearsal():
    from check_bridge_pilot import check
    report = check(ROOT/'backend/tests/fixtures/bridge_pilot/bhph-accounting-manifest.json')
    assert report['status'] == 'fixture_checks_passed'
    assert report['production_access'] is False and report['persisted'] is False
    print(json.dumps({'stage':'bridge', 'bhph_accounting_reversals':'passed',
                      'rows':report['total_checked_rows'],
                      'steps':report['simulated_activated_steps'],
                      'fixture_hash':report['checked_fixture_hash']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--worker',choices=['dealer','dealer_restart','service','service_restart','customer','customer_restart','personal','bridge','bridge_replay'])
    args=parser.parse_args()
    root=Path(args.directory).resolve()
    env=clean_environment(root)
    if args.worker:
        if os.environ.get('NXTDEAL_SYNTHETIC') != 'true':
            raise SystemExit('Must run through isolated parent')
        assert Path(os.environ['DEALEROS_STORAGE_DIR']).resolve() == root/'dealer'
        {'dealer':dealer_rehearsal,'dealer_restart':dealer_restart,'personal':personal_rehearsal,
         'bridge':bridge_rehearsal,'bridge_replay':bridge_rehearsal,
         'customer':customer_rehearsal,'customer_restart':lambda: customer_rehearsal(True),
         'service':service_rehearsal,'service_restart':lambda: service_rehearsal(True)}[args.worker]()
        return
    evidence=[]
    for stage in ['dealer','dealer_restart','service','service_restart','customer','customer_restart','personal','bridge','bridge_replay']:
        service_root = ROOT / ('hub' if stage == 'personal' else 'backend')
        env['PYTHONPATH']=os.pathsep.join([str(service_root),str(ROOT/'scripts')])
        result=subprocess.run([sys.executable,__file__,str(root),'--worker',stage],cwd=root,
                              env=env,text=True,capture_output=True)
        if result.returncode:
            # Only this synthetic child uses these inputs. Keep actionable failure
            # diagnostics in CI; do not log its environment or generated auth secret.
            print(result.stderr, file=sys.stderr)
            raise SystemExit(f"Synthetic {stage} rehearsal failed ({result.returncode})")
        evidence.append(json.loads(result.stdout.strip().splitlines()[-1]))
    assert evidence[-1] == evidence[-2], 'Synthetic Bridge replay changed its evidence'
    evidence.pop()
    evidence[-1]['independent_process_replay'] = 'passed'
    from rehearse_hub_recovery import rehearse
    evidence.append(rehearse(root))
    report={'scope':'synthetic_only','checks':evidence,'production_readiness':False}
    (root/'rehearsal.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
