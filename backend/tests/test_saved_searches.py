import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copy import deepcopy
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
from core.entity_types import CUSTOMER, CUSTOMER_ACCOUNT, VEHICLE
from core import saved_searches as saved


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(saved, 'save_graph', lambda _: None)
    for cid in ('C1', 'C2'):
        ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={'email':cid.lower()+'@example.com'}))
        seed_verified_account(cid)
    yield
    ledger.reset()


def test_create_update_remove_are_owned_and_do_not_enable_delivery():
    created = saved.save_search(token('C1'), {'make': ' Example ', 'max_price': 20000})
    row = created['search']
    assert row['criteria']['make'] == 'Example'
    assert created['delivery_enabled'] is False
    assert saved.get_saved_searches(token('C2'))['count'] == 0
    assert 'error' in saved.save_search(token('C2'), {'make': 'Other'}, row['id'])
    assert 'error' in saved.remove_search(token('C2'), row['id'])
    updated = saved.save_search(token('C1'), {'body_style': 'SUV'}, row['id'])['search']
    assert updated['created_at'] == row['created_at']
    assert updated['criteria'] == {'body_style': 'SUV'}
    updated['criteria']['body_style'] = 'mutated response'
    assert saved.get_saved_searches(token('C1'))['searches'][0]['criteria']['body_style'] == 'SUV'
    assert saved.remove_search(token('C1'), row['id']) == {'removed': True}
    assert saved.get_saved_searches(token('C1'))['count'] == 0


@pytest.mark.parametrize('criteria', [None, [], {}, {'email':'private'}, {'make':''},
    {'make':'x'*81}, {'max_price':True}, {'max_price':float('nan')},
    {'max_price':float('inf')}, {'min_price':-1}, {'min_price':100,'max_price':99}])
def test_invalid_criteria_never_mutate(criteria):
    assert 'error' in saved.save_search(token('C1'), criteria)
    assert saved.FIELD not in ledger.get_entity('C1').attributes


def test_identity_required_for_every_operation():
    ledger.get_entity('SC1').attributes.pop('link_proof')
    for invalid_token in ('unknown', None, 'C1'):
        assert 'error' in saved.get_saved_searches(invalid_token)
        assert 'error' in saved.save_search(invalid_token, {'make':'Example'})
        assert 'error' in saved.remove_search(invalid_token, 'anything')


@pytest.mark.parametrize('operation', ['create', 'update', 'remove'])
def test_save_failures_restore_exact_previous_state(monkeypatch, operation):
    row = saved.save_search(token('C1'), {'make':'Example'})['search']
    customer = ledger.get_entity('C1')
    before = deepcopy(customer.attributes)
    def fail(_): raise OSError('fixture save failure')
    monkeypatch.setattr(saved, 'save_graph', fail)
    with pytest.raises(OSError):
        if operation == 'remove': saved.remove_search(token('C1'), row['id'])
        else: saved.save_search(token('C1'), {'make':'New'}, row['id'] if operation == 'update' else None)
    assert customer.attributes == before


def test_first_save_failure_removes_new_field(monkeypatch):
    def fail(_): raise OSError('fixture save failure')
    monkeypatch.setattr(saved, 'save_graph', fail)
    with pytest.raises(OSError): saved.save_search(token('C1'), {'make':'Example'})
    assert saved.FIELD not in ledger.get_entity('C1').attributes


def test_limit_and_malformed_state_fail_closed():
    for i in range(saved.MAX_SEARCHES):
        assert 'search' in saved.save_search(token('C1'), {'model':str(i)})
    assert 'error' in saved.save_search(token('C1'), {'model':'overflow'})
    customer = ledger.get_entity('C1')
    customer.attributes[saved.FIELD] = {'broken':'retain'}
    assert 'error' in saved.get_saved_searches(token('C1'))
    assert 'error' in saved.save_search(token('C1'), {'make':'Example'})
    assert customer.attributes[saved.FIELD] == {'broken':'retain'}


def test_preview_uses_current_inventory_and_does_not_persist_or_expose_private_fields(monkeypatch):
    sid = saved.save_search(token('C1'), {'make':'example', 'model':'one', 'min_price':100, 'max_price':200})['search']['id']
    for vid, price, sold in [('yes',100,None),('high',201,None),('unknown',None,None),('sold',150,'2026-10-01')]:
        ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={
            'Make':'Example', 'Model':'One', 'Price':price, 'DateSold':sold, 'Cost':90}))
    def unexpected(_): raise AssertionError('preview must not save')
    monkeypatch.setattr(saved, 'save_graph', unexpected)
    result = saved.preview_search_matches(token('C1'), sid)
    assert result['vehicle_ids'] == ['yes']
    assert result['total_count'] == 1 and result['delivery_enabled'] is False
    assert 'Cost' not in str(result)
    assert result['observed_at'].endswith('+00:00')
    ledger.get_entity('yes').attributes['DateSold'] = '2026-10-03'
    assert saved.preview_search_matches(token('C1'), sid)['vehicle_ids'] == []
    assert 'error' in saved.preview_search_matches(token('C2'), sid)
    assert 'error' in saved.preview_search_matches(None, sid)


def test_body_style_matching_is_explicitly_unavailable():
    sid = saved.save_search(token('C1'), {'body_style':'SUV'})['search']['id']
    assert saved.preview_search_matches(token('C1'), sid)['reason'] == 'unsupported_inventory_field'


@pytest.mark.parametrize('price', [True, '$100', '1,000', '', 'NaN', 'Infinity', '1e500', '1'*81, float('nan'), float('inf'), -1, 10**500])
def test_preview_excludes_malformed_prices(price):
    sid = saved.save_search(token('C1'), {'min_price':0})['search']['id']
    ledger.add_entity(Entity(id='V1', entity_type=VEHICLE, attributes={'Price':price}))
    assert saved.preview_search_matches(token('C1'), sid)['vehicle_ids'] == []


@pytest.mark.parametrize('price', ['100', ' 100.00 ', '1e2'])
def test_preview_accepts_existing_numeric_string_inventory_prices(price):
    sid = saved.save_search(token('C1'), {'min_price':100, 'max_price':100})['search']['id']
    ledger.add_entity(Entity(id='V1', entity_type=VEHICLE, attributes={'Price':price}))
    assert saved.preview_search_matches(token('C1'), sid)['vehicle_ids'] == ['V1']
    assert ledger.get_entity('V1').attributes['Price'] == price


def test_preview_bounds_results_and_reports_truncation():
    sid = saved.save_search(token('C1'), {'make':'Example'})['search']['id']
    for i in range(101):
        ledger.add_entity(Entity(id=f'V{i:03}', entity_type=VEHICLE, attributes={'Make':'Example'}))
    result = saved.preview_search_matches(token('C1'), sid)
    assert len(result['vehicle_ids']) == 100
    assert result['vehicle_ids'][0] == 'V000'
    assert result['total_count'] == 101 and result['truncated'] is True


def test_searches_survive_real_graph_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    path = str(tmp_path / 'fixture-graph.json')
    monkeypatch.setattr(saved, 'save_graph', lambda _: ledger.save(path))
    row = saved.save_search(token('C1'), {'make':'Example', 'min_price':0, 'max_price':25000})['search']
    ledger.reset()
    assert ledger.load(path) is True
    restored = saved.get_saved_searches(token('C1'))
    assert restored['searches'] == [row]
    assert restored['delivery_enabled'] is False
    assert saved.get_saved_searches(token('C2'))['count'] == 0
    saved.save_search(token('C1'), {'model':'Changed'}, row['id'])
    ledger.reset()
    ledger.load(path)
    assert saved.get_saved_searches(token('C1'))['searches'][0]['criteria'] == {'model':'Changed'}
    saved.remove_search(token('C1'), row['id'])
    ledger.reset()
    ledger.load(path)
    assert saved.get_saved_searches(token('C1'))['count'] == 0


def test_reads_are_detached_and_do_not_expose_unrecognized_record_fields():
    row = saved.save_search(token('C1'), {'make':'Example'})['search']
    ledger.get_entity('C1').attributes[saved.FIELD][0]['internal_note'] = 'private'
    result = saved.get_saved_searches(token('C1'))
    assert 'internal_note' not in result['searches'][0]
    result['searches'][0]['criteria']['make'] = 'Mutated'
    assert saved.get_saved_searches(token('C1'))['searches'][0]['criteria']['make'] == 'Example'
    assert saved.get_saved_searches(token('C1'))['searches'][0]['id'] == row['id']


def test_oversized_integer_criteria_fail_without_overflow():
    assert 'error' in saved.save_search(token('C1'), {'max_price':10**500})
    assert saved.FIELD not in ledger.get_entity('C1').attributes

@pytest.mark.parametrize('created,updated', [
    ('not-a-time','2026-10-03T12:00:00+00:00'),
    ('2026-10-03','2026-10-03T12:00:00+00:00'),
    ('2026-10-03T12:00:00','2026-10-03T13:00:00'),
    ('2026-10-03T12:00:00+00:00',''),
    ('2026-10-03T12:00:00+00:00','2026-10-03T06:59:59-05:00'),
    ('9999-01-01T12:00:00+00:00','9999-01-01T12:00:00+00:00'),
    ('2026-10-03T12:00:00+00:00','9999-01-01T12:00:00+00:00'),
])
def test_invalid_temporal_state_is_not_exposed_or_overwritten(created, updated):
    customer=ledger.get_entity('C1')
    customer.attributes[saved.FIELD]=[{'id':'fixture','criteria':{'make':'Example'},
        'created_at':created,'updated_at':updated}]
    before=deepcopy(customer.attributes)
    assert 'error' in saved.get_saved_searches(token('C1'))
    assert 'error' in saved.preview_search_matches(token('C1'),'fixture')
    assert 'error' in saved.save_search(token('C1'),{'make':'Changed'},'fixture')
    assert 'error' in saved.remove_search(token('C1'),'fixture')
    assert customer.attributes == before


def test_valid_offset_instants_preserve_original_timestamp_provenance():
    row={'id':'fixture','criteria':{'make':'Example'},
         'created_at':'2026-10-03T12:00:00Z','updated_at':'2026-10-03T07:00:00-05:00'}
    ledger.get_entity('C1').attributes[saved.FIELD]=[row]
    assert saved.get_saved_searches(token('C1'))['searches'] == [row]


def test_search_timestamp_equal_to_observed_instant_is_valid(monkeypatch):
    from datetime import datetime, timezone
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(saved, 'datetime', FixedClock)
    row = {'id':'fixture', 'criteria':{'make':'Example'},
           'created_at':'2026-10-04T07:00:00-05:00',
           'updated_at':'2026-10-04T12:00:00Z'}
    ledger.get_entity('C1').attributes[saved.FIELD] = [row]
    assert saved.get_saved_searches(token('C1'))['searches'] == [row]


def test_clock_regression_does_not_rewrite_last_observed_update(monkeypatch):
    from datetime import datetime, timezone
    row=saved.save_search(token('C1'),{'make':'Example'})['search']
    class EarlierClock:
        @staticmethod
        def now(tz): return datetime(2000,1,1,tzinfo=timezone.utc)
    monkeypatch.setattr(saved,'datetime',EarlierClock)
    EarlierClock.fromisoformat = datetime.fromisoformat
    before=deepcopy(ledger.get_entity('C1').attributes)
    assert 'error' in saved.save_search(token('C1'),{'make':'Changed'},row['id'])
    assert ledger.get_entity('C1').attributes == before


def test_preview_pages_all_matches_and_keeps_customer_search_ownership(monkeypatch):
    sid = saved.save_search(token('C1'), {'make':'Example'})['search']['id']
    for i in reversed(range(205)):
        ledger.add_entity(Entity(id=f'V{i:03}', entity_type=VEHICLE, attributes={'Make':'Example'}))
    before = deepcopy(ledger.get_entity('C1').attributes)
    def unexpected(_): raise AssertionError('paging must not persist')
    monkeypatch.setattr(saved, 'save_graph', unexpected)
    ids, offset = [], 0
    while offset is not None:
        result = saved.preview_search_matches(token('C1'), sid, offset=offset, limit=40)
        assert result['total_count'] == 205 and result['delivery_enabled'] is False
        assert len(result['vehicle_ids']) <= 40
        assert result['truncated'] == (result['next_offset'] is not None)
        ids.extend(result['vehicle_ids'])
        offset = result['next_offset']
    assert ids == [f'V{i:03}' for i in range(205)]
    empty = saved.preview_search_matches(token('C1'), sid, offset=999)
    assert empty['vehicle_ids'] == [] and empty['next_offset'] is None
    assert 'error' in saved.preview_search_matches(token('C2'), sid, offset=100)
    assert ledger.get_entity('C1').attributes == before
    ledger.get_entity('V204').attributes['DateSold'] = '2026-10-04'
    live = saved.preview_search_matches(token('C1'), sid, offset=200)
    assert live['total_count'] == 204 and 'V204' not in live['vehicle_ids']


@pytest.mark.parametrize('options', [{'offset':-1}, {'offset':True}, {'offset':'0'},
    {'limit':0}, {'limit':101}, {'limit':False}, {'limit':1.5}])
def test_preview_rejects_invalid_paging(options):
    sid = saved.save_search(token('C1'), {'make':'Example'})['search']['id']
    assert 'error' in saved.preview_search_matches(token('C1'), sid, **options)


@pytest.mark.parametrize('operation', ['create', 'update', 'remove'])
def test_saved_search_edits_preserve_unexposed_metadata(operation):
    first = saved.save_search(token('C1'), {'make':'Example'})['search']['id']
    second = saved.save_search(token('C1'), {'model':'One'})['search']['id']
    customer = ledger.get_entity('C1')
    for row in customer.attributes[saved.FIELD]:
        row['import_provenance'] = {'reference':'fixture-private', 'details':[row['id']]}
    if operation == 'create':
        response = saved.save_search(token('C1'), {'make':'New'})
    elif operation == 'update':
        response = saved.save_search(token('C1'), {'make':'Changed'}, first)
    else:
        response = saved.remove_search(token('C1'), first)
    rows = {row['id']:row for row in customer.attributes[saved.FIELD]}
    assert rows[second]['import_provenance'] == {'reference':'fixture-private','details':[second]}
    if operation != 'remove':
        assert rows[first]['import_provenance']['details'] == [first]
    else:
        assert first not in rows
    assert 'fixture-private' not in str(response)
    assert 'import_provenance' not in str(saved.get_saved_searches(token('C1')))


def test_failed_saved_search_edit_restores_metadata_exactly(monkeypatch):
    sid = saved.save_search(token('C1'), {'make':'Example'})['search']['id']
    customer = ledger.get_entity('C1')
    customer.attributes[saved.FIELD][0]['import_provenance'] = {'private':['fixture']}
    original = customer.attributes[saved.FIELD]
    before = deepcopy(original)
    def fail(_): raise OSError('fixture failure')
    monkeypatch.setattr(saved, 'save_graph', fail)
    with pytest.raises(OSError): saved.save_search(token('C1'), {'make':'Changed'}, sid)
    assert customer.attributes[saved.FIELD] is original
    assert customer.attributes[saved.FIELD] == before


@pytest.mark.parametrize('first_fails', [False, True])
def test_overlapping_search_saves_wait_and_preserve_committed_edits(monkeypatch, first_fails):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    entered, release = Event(), Event()
    calls = []
    def persist(_):
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
            if first_fails: raise OSError('fixture first save failure')
    monkeypatch.setattr(saved, 'save_graph', persist)
    customer_token = token('C1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(saved.save_search, customer_token, {'make':'First'})
        assert entered.wait(5)
        second = pool.submit(saved.save_search, customer_token, {'make':'Second'})
        try:
            with pytest.raises(TimeoutError): second.result(timeout=0.1)
        finally:
            release.set()
        if first_fails:
            with pytest.raises(OSError): first.result()
        else:
            assert 'search' in first.result()
        assert 'search' in second.result()
    names = [row['criteria']['make'] for row in saved.get_saved_searches(customer_token)['searches']]
    assert names == (['Second'] if first_fails else ['First', 'Second'])


def test_search_read_does_not_observe_a_failed_pending_write(monkeypatch):
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
        writer = pool.submit(saved.save_search, customer_token, {'make':'Pending'})
        assert entered.wait(5)
        reader = pool.submit(saved.get_saved_searches, customer_token)
        try:
            with pytest.raises(TimeoutError): reader.result(timeout=0.1)
        finally:
            release.set()
        with pytest.raises(OSError): writer.result()
        assert reader.result()['searches'] == []
