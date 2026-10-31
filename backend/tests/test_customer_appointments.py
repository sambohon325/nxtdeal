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
from core.entity_types import CUSTOMER, CUSTOMER_ACCOUNT, APPOINTMENT
from core.customer_appointments import get_my_appointments, cancel_my_appointment


@pytest.fixture(autouse=True)
def fixture():
    ledger.reset()
    for cid in ('C1', 'C2'):
        ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={'email':cid.lower()+'@example.com'}))
        seed_verified_account(cid)
    yield
    ledger.reset()


def appointment(aid, customer, start, **extra):
    entity=Entity(id=aid, entity_type=APPOINTMENT, attributes={
        'customer_id':customer, 'scheduled_start':start, 'department':'Service',
        'appointment_type':'service', 'status':'confirmed', 'notes':'private notes',
        'checkin_link':{'token':'private-token'}, 'assigned_to':'EMP-PRIVATE', **extra})
    ledger.add_entity(entity)
    return entity


def test_own_calendar_is_live_ordered_and_allowlisted():
    late=appointment('A2','C1','2026-10-05T12:00:00Z')
    appointment('A1','C1','2026-10-04T12:00:00Z')
    appointment('OTHER','C2','2026-10-03T12:00:00Z')
    result=get_my_appointments(token('C1'))
    assert result['count']==2
    assert [a['id'] for a in result['appointments']]==['A1','A2']
    assert set(result['appointments'][0])=={'id','department','appointment_type','scheduled_start','scheduled_end','status','time_status'}
    late.attributes['status']='cancelled'
    assert get_my_appointments(token('C1'))['appointments'][1]['status']=='cancelled'


def test_no_customer_match_via_lead_link_and_empty_is_honest():
    appointment('LEAD-ONLY','C2','2026-10-04',lead_id='C1')
    assert get_my_appointments(token('C1'))=={'appointments':[],'count':0,'total_count':0,'next_offset':None}


def test_invalid_and_unverified_tokens_are_denied():
    for invalid_token in (None,'unknown'):
        assert 'error' in get_my_appointments(invalid_token)
    ledger.get_entity('SC1').attributes.pop('link_proof')
    assert get_my_appointments(token('C1'))['reason']=='unverified'


def test_calendar_orders_instants_across_offsets_without_rewriting_times():
    appointment('LATER', 'C1', '2026-10-04T08:00:00-05:00')
    appointment('EARLIER', 'C1', '2026-10-04T12:00:00Z')
    result = get_my_appointments(token('C1'))['appointments']
    assert [row['id'] for row in result] == ['EARLIER', 'LATER']
    assert result[1]['scheduled_start'] == '2026-10-04T08:00:00-05:00'


def test_calendar_separates_unknown_timezones_and_tolerates_invalid_legacy_times():
    appointment('LOCAL', 'C1', '2020-01-01T09:00:00')
    appointment('KNOWN', 'C1', '2026-10-04T12:00:00Z')
    for aid, value in [('BAD-A', None), ('BAD-B', 42), ('BAD-C', 'invalid')]:
        appointment(aid, 'C1', value)
    result = get_my_appointments(token('C1'))['appointments']
    assert [row['id'] for row in result] == ['KNOWN', 'LOCAL', 'BAD-A', 'BAD-B', 'BAD-C']
    assert ledger.get_entity('LOCAL').attributes['scheduled_start'] == '2020-01-01T09:00:00'


def test_equivalent_instants_have_deterministic_order():
    appointment('B', 'C1', '2026-10-04T07:00:00-05:00')
    appointment('A', 'C1', '2026-10-04T12:00:00Z')
    assert [row['id'] for row in get_my_appointments(token('C1'))['appointments']] == ['A', 'B']


@pytest.mark.parametrize('field', ['department', 'appointment_type', 'status', 'scheduled_start', 'scheduled_end'])
@pytest.mark.parametrize('value', [{'private_note':'fixture-private'}, ['fixture-private'], 'fixture-private', 42])
def test_malformed_calendar_values_do_not_escape_projection(field, value):
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z')
    appt.attributes[field] = value
    result = get_my_appointments(token('C1'))['appointments'][0]
    assert result[field] is None
    assert 'fixture-private' not in str(result)
    assert appt.attributes[field] is value


@pytest.mark.parametrize('start,state', [('2026-10-04T12:00:00Z','timezone_known'),
    ('2026-10-04T07:00:00-05:00','timezone_known'),
    ('2026-10-04T12:00:00','timezone_unknown'), ('2026-10-04','invalid')])
def test_calendar_time_state_does_not_guess_timezone(start, state):
    appointment('A', 'C1', start)
    result = get_my_appointments(token('C1'))['appointments'][0]
    assert result['time_status'] == state
    assert result['scheduled_start'] == (None if state == 'invalid' else start)


def test_calendar_pages_only_owned_records_and_bounds_default_response():
    for i in range(105):
        appointment(f'A{i:03}', 'C1', '2026-10-04T12:00:00Z')
        appointment(f'OTHER{i:03}', 'C2', '2026-10-01T12:00:00Z')
    first = get_my_appointments(token('C1'))
    assert first['count'] == 100 and first['total_count'] == 105
    assert first['next_offset'] == 100
    second = get_my_appointments(token('C1'), offset=first['next_offset'])
    assert second['count'] == 5 and second['next_offset'] is None
    ids = [row['id'] for row in first['appointments'] + second['appointments']]
    assert ids == [f'A{i:03}' for i in range(105)]
    empty = get_my_appointments(token('C1'), offset=999)
    assert empty == {'appointments':[], 'count':0, 'total_count':105, 'next_offset':None}


@pytest.mark.parametrize('options', [{'offset':-1}, {'offset':True}, {'offset':'0'},
    {'limit':0}, {'limit':101}, {'limit':False}, {'limit':1.5}])
def test_calendar_rejects_invalid_page_parameters(options):
    assert 'error' in get_my_appointments(token('C1'), **options)


@pytest.mark.parametrize('status', ['scheduled', 'confirmed'])
def test_customer_cancel_uses_canonical_history_and_is_idempotent(status, monkeypatch):
    from core import appointments
    saves = []
    monkeypatch.setattr(appointments, 'save_graph', lambda _: saves.append(True))
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status=status)
    result = cancel_my_appointment(token('C1'), 'A')
    assert result['appointment']['status'] == 'cancelled'
    assert result['notification_sent'] is False
    assert appt.attributes['status_history'][0]['by'] == 'customer:C1'
    assert cancel_my_appointment(token('C1'), 'A') == result
    assert len(saves) == 1 and len(appt.attributes['status_history']) == 1


@pytest.mark.parametrize('status', ['arrived', 'completed', 'no_show', 'invalid'])
def test_customer_cannot_cancel_started_or_closed_visit(status):
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status=status)
    assert 'error' in cancel_my_appointment(token('C1'), 'A')
    assert appt.attributes['status'] == status and 'status_history' not in appt.attributes


def test_customer_cancel_requires_verified_ownership():
    appt = appointment('A', 'C2', '2026-10-04T12:00:00Z', lead_id='C1')
    assert cancel_my_appointment(token('C1'), 'A') == cancel_my_appointment(token('C1'), 'missing')
    assert 'error' in cancel_my_appointment(None, 'A')
    ledger.get_entity('SC2').attributes.pop('link_proof')
    assert 'error' in cancel_my_appointment(token('C2'), 'A')
    assert appt.attributes['status'] == 'confirmed'


def test_failed_customer_cancel_restores_history_and_status(monkeypatch):
    from copy import deepcopy
    from core import appointments
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z')
    before = deepcopy(appt.attributes)
    def fail(_): raise OSError('fixture failure')
    monkeypatch.setattr(appointments, 'save_graph', fail)
    with pytest.raises(OSError): cancel_my_appointment(token('C1'), 'A')
    assert appt.attributes == before


@pytest.mark.parametrize('fail_first', [False, True])
def test_customer_cancel_survives_real_reload_without_duplicate_history(tmp_path, monkeypatch, fail_first):
    from core import appointments
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    path = str(tmp_path / 'customer-calendar.json')
    appointment('A', 'C1', '2026-10-04T12:00:00Z')
    appointment('OTHER', 'C2', '2026-10-04T12:00:00Z')
    customer_token = token('C1')
    ledger.save(path)
    before = (tmp_path / 'customer-calendar.json').read_bytes()
    if fail_first:
        def fail(_): raise OSError('fixture write failure')
        monkeypatch.setattr(appointments, 'save_graph', fail)
        with pytest.raises(OSError): cancel_my_appointment(customer_token, 'A')
        assert (tmp_path / 'customer-calendar.json').read_bytes() == before
        ledger.reset()
        assert ledger.load(path) is True
        assert ledger.get_entity('A').attributes['status'] == 'confirmed'
    monkeypatch.setattr(appointments, 'save_graph', lambda _: ledger.save(path))
    result = cancel_my_appointment(customer_token, 'A')
    assert result['notification_sent'] is False
    ledger.reset()
    assert ledger.load(path) is True
    stored = ledger.get_entity('A')
    assert stored.attributes['status'] == 'cancelled'
    assert len(stored.attributes['status_history']) == 1
    assert stored.attributes['status_history'][0]['by'] == 'customer:C1'
    assert ledger.get_entity('OTHER').attributes['status'] == 'confirmed'
    after = (tmp_path / 'customer-calendar.json').read_bytes()
    def unexpected_save(_): raise AssertionError('repeat cancellation must not save')
    monkeypatch.setattr(appointments, 'save_graph', unexpected_save)
    assert cancel_my_appointment(customer_token, 'A') == result
    assert (tmp_path / 'customer-calendar.json').read_bytes() == after


@pytest.mark.parametrize('history', [None, {}, 'legacy-history', 42])
@pytest.mark.parametrize('operation', ['cancel', 'reschedule'])
def test_malformed_history_does_not_partially_mutate_calendar(history, operation, monkeypatch):
    from copy import deepcopy
    from core import appointments
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status_history=history)
    before = deepcopy(appt.attributes)
    def unexpected_save(_): raise AssertionError('invalid history must not save')
    monkeypatch.setattr(appointments, 'save_graph', unexpected_save)
    result = (cancel_my_appointment(token('C1'), 'A') if operation == 'cancel' else
              appointments.reschedule_appointment('A', '2026-10-05T12:00:00Z', 'fixture-staff'))
    assert 'needs repair' in result['error']
    assert appt.attributes == before


def test_customer_confirmation_persists_and_repeat_does_not_write(tmp_path, monkeypatch):
    from core import appointments
    from core.customer_appointments import confirm_my_appointment
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    path = str(tmp_path / 'confirmation.json')
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status='scheduled')
    appointment('OTHER', 'C2', '2026-10-04T12:00:00Z', status='scheduled')
    customer_token = token('C1')
    monkeypatch.setattr(appointments, 'save_graph', lambda _: ledger.save(path))
    result = confirm_my_appointment(customer_token, 'A')
    assert result['appointment']['status'] == 'confirmed'
    assert result['notification_sent'] is False
    ledger.reset()
    assert ledger.load(path) is True
    assert ledger.get_entity('A').attributes['status_history'][0]['by'] == 'customer:C1'
    assert ledger.get_entity('OTHER').attributes['status'] == 'scheduled'
    def unexpected(_): raise AssertionError('repeat must not save')
    monkeypatch.setattr(appointments, 'save_graph', unexpected)
    assert confirm_my_appointment(customer_token, 'A') == result
    assert len(ledger.get_entity('A').attributes['status_history']) == 1


@pytest.mark.parametrize('status', ['arrived', 'completed', 'cancelled', 'no_show', 'invalid'])
def test_customer_confirmation_does_not_reopen_or_rewind_visit(status):
    from core.customer_appointments import confirm_my_appointment
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status=status)
    assert 'error' in confirm_my_appointment(token('C1'), 'A')
    assert appt.attributes['status'] == status and 'status_history' not in appt.attributes


def test_customer_confirmation_requires_current_proof_and_ownership():
    from core.customer_appointments import confirm_my_appointment
    from core.customer_accounts import revoke_customer_sessions
    appointment('A', 'C2', '2026-10-04T12:00:00Z', status='scheduled', lead_id='C1')
    assert confirm_my_appointment(token('C1'), 'A') == {'error':'Appointment not found'}
    old = token('C2')
    revoke_customer_sessions('SC2')
    assert confirm_my_appointment(old, 'A')['reason'] == 'token'
    ledger.get_entity('C2').attributes['email'] = 'changed@example.com'
    assert confirm_my_appointment(token('C2'), 'A')['reason'] == 'unverified'
    assert ledger.get_entity('A').attributes['status'] == 'scheduled'


def test_customer_confirmation_failed_save_can_retry(monkeypatch):
    from copy import deepcopy
    from core import appointments
    from core.customer_appointments import confirm_my_appointment
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status='scheduled')
    before = deepcopy(appt.attributes)
    with monkeypatch.context() as patch:
        def fail(_): raise OSError('fixture failure')
        patch.setattr(appointments, 'save_graph', fail)
        with pytest.raises(OSError): confirm_my_appointment(token('C1'), 'A')
    assert appt.attributes == before
    assert confirm_my_appointment(token('C1'), 'A')['appointment']['status'] == 'confirmed'
    assert len(appt.attributes['status_history']) == 1


@pytest.mark.parametrize('operation', ['confirm', 'cancel'])
@pytest.mark.parametrize('staff_save_fails', [False, True])
def test_customer_transition_waits_for_staff_save_and_rechecks_state(monkeypatch, operation, staff_save_fails):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    from core import appointments
    from core.customer_appointments import confirm_my_appointment
    entered, release = Event(), Event()
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status='scheduled')
    def block_staff_save(_):
        if appt.attributes['status'] == 'arrived':
            entered.set()
            assert release.wait(5)
            if staff_save_fails: raise OSError('fixture staff save failed')
    monkeypatch.setattr(appointments, 'save_graph', block_staff_save)
    action = confirm_my_appointment if operation == 'confirm' else cancel_my_appointment
    with ThreadPoolExecutor(max_workers=2) as pool:
        staff = pool.submit(appointments.update_status, 'A', 'arrived', 'fixture-staff')
        assert entered.wait(5)
        customer = pool.submit(action, token('C1'), 'A')
        try:
            with pytest.raises(TimeoutError): customer.result(timeout=0.1)
        finally:
            release.set()
        if staff_save_fails:
            with pytest.raises(OSError): staff.result()
            assert customer.result()['appointment']['status'] == ('confirmed' if operation == 'confirm' else 'cancelled')
            assert len(appt.attributes['status_history']) == 1
            assert appt.attributes['status_history'][0]['by'] == 'customer:C1'
        else:
            assert staff.result().attributes['status'] == 'arrived'
            assert 'error' in customer.result()
            assert len(appt.attributes['status_history']) == 1


def test_customer_waiting_for_appointment_lock_rechecks_revoked_session():
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from core import appointments
    from core.customer_appointments import confirm_my_appointment
    from core.customer_accounts import revoke_customer_sessions
    appt = appointment('A', 'C1', '2026-10-04T12:00:00Z', status='scheduled')
    customer_token = token('C1')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with appointments.appointment_lock('A'):
            pending = pool.submit(confirm_my_appointment, customer_token, 'A')
            with pytest.raises(TimeoutError): pending.result(timeout=0.1)
            revoke_customer_sessions('SC1')
        assert pending.result()['reason'] == 'token'
    assert appt.attributes['status'] == 'scheduled'
