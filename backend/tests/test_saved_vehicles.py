import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from core.customer_accounts import issue_customer_token

def seed_verified_account(cid):
    ledger.add_entity(Entity(id='S'+cid, entity_type=CUSTOMER_ACCOUNT, attributes={
        'status':'active', 'linked_customer_id':cid, 'email_verified':True,
        'link_proof':{'provider':'privateemail', 'channel':'email', 'customer_id':cid,
                      'recipient':cid.lower()+'@example.com', 'verified_at':'2026-01-01T00:00:00Z'}}))

def token(cid):
    return issue_customer_token('S'+cid)

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, CUSTOMER_ACCOUNT
from core import saved_vehicles as saved

@pytest.fixture(autouse=True)
def fixture(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(saved, 'save_graph', lambda path: None)
    for cid in ('C1','C2'):
        ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={'email':cid.lower()+'@example.com'}))
        seed_verified_account(cid)
    ledger.add_entity(Entity(id='V1',entity_type=VEHICLE,attributes={'Year':2024,'Make':'Example','Price':10000,'Cost':8000,'CustomerID':'private'}))
    yield
    ledger.reset()

def test_customer_isolation_and_public_fields():
    assert saved.set_saved_vehicle(token('C1'),'V1',True)['saved'] is True
    assert saved.get_saved_vehicles(token('C2'))['vehicles']==[]
    vehicle=saved.get_saved_vehicles(token('C1'))['vehicles'][0]
    assert vehicle['price']==10000
    assert 'Cost' not in vehicle and 'CustomerID' not in vehicle

def test_invalid_and_anonymous_tokens_cannot_read_or_write():
    for invalid_token in ('unknown', None):
        assert 'error' in saved.get_saved_vehicles(invalid_token)
        assert 'error' in saved.set_saved_vehicle(invalid_token,'V1',True)
    ledger.get_entity('SC1').attributes.pop('link_proof')
    assert saved.set_saved_vehicle(token('C1'),'V1',True)['reason']=='unverified'
    assert saved.FIELD not in ledger.get_entity('C1').attributes

def test_add_remove_idempotent_and_persisted(monkeypatch):
    snapshots=[]
    monkeypatch.setattr(saved,'save_graph',lambda path:snapshots.append(list(ledger.get_entity('C1').attributes[saved.FIELD])))
    saved.set_saved_vehicle(token('C1'),'V1',True);saved.set_saved_vehicle(token('C1'),'V1',True)
    saved.set_saved_vehicle(token('C1'),'V1',False);saved.set_saved_vehicle(token('C1'),'V1',False)
    assert snapshots==[['V1'],[]]

def test_inventory_resolved_live_and_unavailable_can_be_removed():
    saved.set_saved_vehicle(token('C1'),'V1',True)
    ledger.get_entity('V1').attributes['Price']=9000
    assert saved.get_saved_vehicles(token('C1'))['vehicles'][0]['price']==9000
    ledger.get_entity('V1').attributes['DateSold']='2026-10-03'
    assert saved.get_saved_vehicles(token('C1'))['vehicles']==[{'id':'V1','available':False}]
    assert 'error' in saved.set_saved_vehicle(token('C2'),'V1',True)
    assert saved.set_saved_vehicle(token('C1'),'V1',False)['saved'] is False

def test_persistence_failure_restores_previous_state(monkeypatch):
    def fail(path): raise OSError('fixture failure')
    monkeypatch.setattr(saved,'save_graph',fail)
    with pytest.raises(OSError): saved.set_saved_vehicle(token('C1'),'V1',True)
    assert saved.FIELD not in ledger.get_entity('C1').attributes
    ledger.get_entity('C1').attributes[saved.FIELD]=['V1']
    with pytest.raises(OSError): saved.set_saved_vehicle(token('C1'),'V1',False)
    assert ledger.get_entity('C1').attributes[saved.FIELD]==['V1']

def test_missing_wrong_type_limit_and_boolean_validation():
    for vid in ('missing','C2'):
        assert 'error' in saved.set_saved_vehicle(token('C1'),vid,True)
    assert 'error' in saved.set_saved_vehicle(token('C1'),'V1','true')
    ledger.get_entity('C1').attributes[saved.FIELD]=[f'old-{i}' for i in range(saved.MAX_SAVED)]
    assert 'error' in saved.set_saved_vehicle(token('C1'),'V1',True)

def test_compare_saved_vehicles_preserves_order_and_live_public_projection():
    ledger.add_entity(Entity(id='V2', entity_type=VEHICLE, attributes={'Make':'Second','Price':20000,'Cost':10000}))
    saved.set_saved_vehicle(token('C1'),'V1',True)
    saved.set_saved_vehicle(token('C1'),'V2',True)
    result=saved.compare_saved_vehicles(token('C1'),['V2','V1'])
    assert [v['id'] for v in result['vehicles']]==['V2','V1']
    assert result['count']==2 and result['vehicles'][0]['price']==20000
    assert all('Cost' not in v for v in result['vehicles'])
    ledger.get_entity('V1').attributes['DateSold']='2026-10-03'
    assert saved.compare_saved_vehicles(token('C1'),['V2','V1'])['vehicles'][1]=={'id':'V1','available':False}

@pytest.mark.parametrize('selection', [None, 'V1', [], ['V1'], ['V1','V1'], ['V1',{}], ['V1',' '], ['1','2','3','4','5']])
def test_compare_rejects_invalid_selection(selection):
    assert 'error' in saved.compare_saved_vehicles(token('C1'),selection)


def test_compare_cannot_access_another_customers_saved_list_or_unsaved_inventory(monkeypatch):
    ledger.add_entity(Entity(id='V2', entity_type=VEHICLE, attributes={'Price':20000}))
    ledger.get_entity('C1').attributes[saved.FIELD]=['V1','V2']
    assert 'error' in saved.compare_saved_vehicles(token('C2'),['V1','V2'])
    assert 'error' in saved.compare_saved_vehicles(None,['V1','V2'])
    assert 'error' in saved.compare_saved_vehicles(token('C1'),['V1','C2'])
    def unexpected_save(_): raise AssertionError('comparison must be read only')
    monkeypatch.setattr(saved,'save_graph',unexpected_save)
    assert saved.compare_saved_vehicles(token('C1'),['V1','V2'])['count']==2

@pytest.mark.parametrize('legacy', ['V1', {'V1':True}, 42, None])
def test_malformed_saved_container_is_empty_without_mutating_data(legacy):
    customer=ledger.get_entity('C1')
    customer.attributes[saved.FIELD]=legacy
    assert saved.get_saved_vehicles(token('C1'))=={'vehicles':[],'count':0}
    assert customer.attributes[saved.FIELD] is legacy


@pytest.mark.parametrize('legacy', ['V1', {'V1':True}, 42, None,
    ['V1', 'V1'], ['V1', {}], ['V1', ' bad'], ['V1'] * 101])
@pytest.mark.parametrize('adding', [True, False])
def test_edit_rejects_malformed_saved_data_without_loss(monkeypatch, legacy, adding):
    customer = ledger.get_entity('C1')
    customer.attributes[saved.FIELD] = legacy
    def unexpected_save(_):
        raise AssertionError('malformed saved data must not be persisted')
    monkeypatch.setattr(saved, 'save_graph', unexpected_save)
    result = saved.set_saved_vehicle(token('C1'), 'V1', adding)
    assert 'need repair' in result['error']
    assert customer.attributes[saved.FIELD] is legacy


def test_malformed_references_are_ignored_and_valid_order_is_retained():
    customer=ledger.get_entity('C1')
    legacy=[{},None,[],12,'',' ',' V1','V1','V1','missing','x'*129]
    customer.attributes[saved.FIELD]=legacy
    result=saved.get_saved_vehicles(token('C1'))
    assert [v['id'] for v in result['vehicles']]==['V1','missing']
    assert result['vehicles'][1]=={'id':'missing','available':False}
    assert customer.attributes[saved.FIELD] is legacy
    assert saved.compare_saved_vehicles(token('C1'),['missing','V1'])['count']==2

@pytest.mark.parametrize('vehicle_id', [' ',' V1','V1 ','x'*129,{},None])
def test_invalid_vehicle_id_rejected_without_write(vehicle_id, monkeypatch):
    def fail(_): raise AssertionError('must not persist invalid ID')
    monkeypatch.setattr(saved,'save_graph',fail)
    assert 'error' in saved.set_saved_vehicle(token('C1'),vehicle_id,True)
    assert 'error' in saved.compare_saved_vehicles(token('C1'),['V1',vehicle_id])
    assert saved.FIELD not in ledger.get_entity('C1').attributes

@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), 'NaN', '$10,000', {'private':'fixture'}, ['fixture'], 10**500])
def test_invalid_inventory_numbers_are_unknown_without_rewriting(value):
    vehicle = ledger.get_entity('V1')
    vehicle.attributes.update(Price=value, Mileage=value)
    saved.set_saved_vehicle(token('C1'), 'V1', True)
    result = saved.get_saved_vehicles(token('C1'))['vehicles'][0]
    assert result['price'] is None and result['mileage'] is None
    assert vehicle.attributes['Price'] is value


def test_numeric_imports_and_text_projection_are_safe():
    vehicle = ledger.get_entity('V1')
    vehicle.attributes.update(Year='2024', Price='10000.50', Mileage='12345',
                              Make={'private':'fixture'}, Model=['fixture'], Trim='x'*201)
    saved.set_saved_vehicle(token('C1'), 'V1', True)
    result = saved.get_saved_vehicles(token('C1'))['vehicles'][0]
    assert result['year'] == 2024 and result['price'] == 10000.5 and result['mileage'] == 12345
    assert result['make'] is None and result['model'] is None and result['trim'] is None
    assert vehicle.attributes['Price'] == '10000.50'


@pytest.mark.parametrize('first_fails', [False, True])
def test_overlapping_vehicle_saves_preserve_successful_edits(monkeypatch, first_fails):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    ledger.add_entity(Entity(id='V2', entity_type=VEHICLE, attributes={'Make':'Example'}))
    entered, release = Event(), Event()
    calls = []
    def persist(_):
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
            if first_fails: raise OSError('fixture first failure')
    monkeypatch.setattr(saved, 'save_graph', persist)
    customer_token = token('C1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(saved.set_saved_vehicle, customer_token, 'V1', True)
        assert entered.wait(5)
        second = pool.submit(saved.set_saved_vehicle, customer_token, 'V2', True)
        try:
            with pytest.raises(TimeoutError): second.result(timeout=0.1)
        finally:
            release.set()
        if first_fails:
            with pytest.raises(OSError): first.result()
        else:
            assert first.result()['saved'] is True
        assert second.result()['saved'] is True
    assert ledger.get_entity('C1').attributes[saved.FIELD] == (['V2'] if first_fails else ['V1','V2'])


def test_vehicle_read_waits_for_failed_save_rollback(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    entered, release = Event(), Event()
    def fail(_):
        entered.set()
        assert release.wait(5)
        raise OSError('fixture failure')
    monkeypatch.setattr(saved, 'save_graph', fail)
    customer_token = token('C1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(saved.set_saved_vehicle, customer_token, 'V1', True)
        assert entered.wait(5)
        reader = pool.submit(saved.get_saved_vehicles, customer_token)
        try:
            with pytest.raises(TimeoutError): reader.result(timeout=0.1)
        finally:
            release.set()
        with pytest.raises(OSError): writer.result()
        assert reader.result()['vehicles'] == []


def test_waiting_vehicle_edit_rechecks_session_revocation():
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from core.customer_accounts import revoke_customer_sessions
    customer_token = token('C1')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with saved._SAVED_LOCK:
            pending = pool.submit(saved.set_saved_vehicle, customer_token, 'V1', True)
            with pytest.raises(TimeoutError): pending.result(timeout=0.1)
            revoke_customer_sessions('SC1')
        assert pending.result()['reason'] == 'token'
    assert saved.FIELD not in ledger.get_entity('C1').attributes
