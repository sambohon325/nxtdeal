from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import uuid

import pytest
from core import auth
from core.kiosk_sessions import KioskSessions
from core.kiosk_checkin import KioskCheckin, CheckinUnconfirmed, CheckinThrottled


@pytest.fixture
def setup():
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-ADMIN', 'Fictional2026!', 'ADMIN', must_change_password=False)
    staff = auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    sessions = KioskSessions('synthetic-a')
    token = sessions.issue(staff, 'lobby')['token']
    writes = []
    adapter = KioskCheckin(sessions, lambda identity, fields: writes.append((identity, fields)))
    yield sessions, staff, token, writes, adapter
    auth.credential_store.load_credentials(previous)


def submit(adapter, token, request_id=None, body=None):
    return adapter.submit(token, device_id='lobby', request_id=request_id or str(uuid.uuid4()),
                          body=body if body is not None else {'name': 'Fictional Visitor'})


def test_concurrent_replays_write_once_and_return_only_generic_receipt(setup):
    _, _, token, writes, adapter = setup
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: submit(adapter, token, key), range(12)))
    assert len(writes) == 1
    assert results == [{'status': 'checked_in', 'receipt': key}] * 12
    results[0]['status'] = 'tampered'
    assert submit(adapter, token, key)['status'] == 'checked_in'
    assert 'Fictional Visitor' not in repr(adapter._receipts)
    assert token not in repr(adapter._receipts)
    with pytest.raises(ValueError):
        submit(adapter, token, key, {'name': 'Another Fictional Visitor'})
    assert len(writes) == 1


@pytest.mark.parametrize('body', [None, [], {}, {'name': ' '}, {'name': 'x' * 121},
    {'name': 'Fictional', 'phone': 'x' * 41}, {'name': 'Fictional', 'reason': 'x' * 501},
    {'name': 'Fictional\nInjected'}, {'name': 'Fictional', 'assigned_to': 'ADMIN'},
    {'name': 'Fictional', 'tenant_id': 'other'}, {'name': 'Fictional', 'phone': 123}])
def test_invalid_or_privileged_input_cannot_write(setup, body):
    _, _, token, writes, adapter = setup
    with pytest.raises(ValueError):
        adapter.submit(token, device_id='lobby', request_id=str(uuid.uuid4()), body=body)
    assert not writes


def test_uncertain_write_is_not_repeated_or_reported_as_success(setup):
    sessions, _, token, writes, _ = setup
    def writer(identity, fields):
        writes.append(fields)
        raise OSError('fictional disk failure after partial mutation')
    adapter = KioskCheckin(sessions, writer)
    key = str(uuid.uuid4())
    for _ in range(2):
        with pytest.raises(CheckinUnconfirmed, match='Ask the front desk'):
            submit(adapter, token, key)
    assert len(writes) == 1


def test_throttle_allows_replay_but_caps_new_attempts_across_rotation(setup):
    sessions, staff, token, writes, adapter = setup
    keys = [str(uuid.uuid4()) for _ in range(adapter.MAX_PER_MINUTE)]
    for key in keys:
        submit(adapter, token, key)
    assert submit(adapter, token, keys[0])['status'] == 'checked_in'
    replacement = sessions.issue(staff, 'lobby')['token']
    with pytest.raises(CheckinThrottled):
        submit(adapter, replacement)
    assert len(writes) == adapter.MAX_PER_MINUTE


def test_capacity_does_not_evict_replay_protection(setup):
    _, _, token, writes, adapter = setup
    adapter.MAX_RECEIPTS = 1
    key = str(uuid.uuid4())
    submit(adapter, token, key)
    with pytest.raises(CheckinThrottled):
        submit(adapter, token)
    submit(adapter, token, key)
    assert len(writes) == 1


@pytest.mark.parametrize('key', ['', 'not-a-uuid', 123, 'a' * 10000])
def test_invalid_request_ids_cannot_write(setup, key):
    _, _, token, writes, adapter = setup
    with pytest.raises(ValueError):
        adapter.submit(token, device_id='lobby', request_id=key, body={'name': 'Fictional'})
    assert not writes


def test_throttle_window_recovers_without_discarding_receipt(setup, monkeypatch):
    import time
    _, _, token, writes, adapter = setup
    now = time.time()
    monkeypatch.setattr('core.kiosk_checkin.time.time', lambda: now)
    key = str(uuid.uuid4())
    adapter.MAX_PER_MINUTE = 1
    submit(adapter, token, key)
    with pytest.raises(CheckinThrottled):
        submit(adapter, token)
    monkeypatch.setattr('core.kiosk_checkin.time.time', lambda: now + 61)
    submit(adapter, token)
    submit(adapter, token, key)
    assert len(writes) == 2


def test_queued_write_rechecks_revocation_before_invoking_writer(setup):
    sessions, staff, token, writes, adapter = setup
    started = threading.Event()
    def queued():
        started.set()
        return submit(adapter, token)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with adapter._lock:
            result = pool.submit(queued)
            assert started.wait(1)
            sessions.revoke(staff, 'lobby')
        with pytest.raises(PermissionError):
            result.result(timeout=1)
    assert not writes


def test_revoked_grant_cannot_retrieve_even_a_cached_receipt(setup):
    sessions, staff, token, writes, adapter = setup
    key = str(uuid.uuid4())
    submit(adapter, token, key)
    sessions.revoke(staff, 'lobby')
    with pytest.raises(PermissionError):
        submit(adapter, token, key)
    assert len(writes) == 1


def test_real_walkin_uses_server_rotation_without_exposing_lead(setup):
    from core.dealeros import ledger
    from core.entities import Entity
    from core.entity_types import EMPLOYEE, LEAD
    sessions, _, token, _, _ = setup
    ledger.reset()
    try:
        ledger.add_entity(Entity(id='SYN-REP', entity_type=EMPLOYEE,
                                 attributes={'Department': 'Sales', 'FirstName': 'Fictional'}))
        result = submit(KioskCheckin(sessions), token,
                        body={'name': 'Fictional Visitor', 'phone': '', 'reason': 'Browse'})
        assert set(result) == {'status', 'receipt'}
        leads = [item for item in ledger.get_all().values() if item.entity_type == LEAD]
        assert len(leads) == 1
        assert leads[0].attributes['AssignedSalesperson'] == 'SYN-REP'
        assert leads[0].attributes['up_type'] == 'walk_in'
        assert leads[0].attributes['up_logged_by'] == 'KIOSK:lobby'
    finally:
        ledger.reset()
