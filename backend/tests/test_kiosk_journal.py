from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import subprocess
import sys
import threading
import uuid

import pytest
from core import auth
from core.kiosk_checkin import KioskCheckin, CheckinConflict, CheckinThrottled, CheckinUnconfirmed
from core.kiosk_journal import KioskJournal
from core.kiosk_sessions import KioskSessions

KEY = b'fictional-test-key-not-for-use!!!0'


@pytest.fixture
def setup(tmp_path):
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-ADMIN', 'Fictional2026!', 'ADMIN', must_change_password=False)
    staff = auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    sessions = KioskSessions('synthetic-a')
    token = sessions.issue(staff, 'lobby')['token']
    KioskJournal(tmp_path / 'receipts.sqlite', KEY, initialize=True)
    yield tmp_path / 'receipts.sqlite', sessions, staff, token
    auth.credential_store.load_credentials(previous)


def submit(adapter, token, request, name='Fictional Visitor'):
    return adapter.submit(token, device_id='lobby', request_id=request, body={'name': name})


def test_recreated_adapter_and_reenrollment_do_not_repeat_confirmed_write(setup):
    path, sessions, staff, token = setup
    calls = []
    adapter = KioskCheckin(sessions, lambda *_: calls.append(1), KioskJournal(path, KEY))
    request = str(uuid.uuid4())
    expected = submit(adapter, token, request)
    sessions = KioskSessions('synthetic-a')  # Restart requires fresh authorized enrollment.
    token = sessions.issue(staff, 'lobby')['token']
    rebuilt = KioskCheckin(sessions, lambda *_: calls.append(2), KioskJournal(path, KEY))
    assert submit(rebuilt, token, request) == expected
    assert calls == [1]
    with pytest.raises(CheckinConflict):
        submit(rebuilt, token, request, 'Different Fictional Visitor')
    assert b'Fictional Visitor' not in path.read_bytes()
    assert token.encode() not in path.read_bytes()


@pytest.mark.parametrize('failure', [OSError, SystemExit])
def test_partial_write_or_abrupt_exit_leaves_uncertain_marker(setup, failure):
    path, sessions, staff, token = setup
    calls = []
    def fail(*_):
        calls.append(1)
        raise failure('Simulated failure after mutation')
    adapter = KioskCheckin(sessions, fail, KioskJournal(path, KEY))
    request = str(uuid.uuid4())
    with pytest.raises(SystemExit if failure is SystemExit else CheckinUnconfirmed):
        submit(adapter, token, request)
    token = sessions.issue(staff, 'lobby')['token']
    rebuilt = KioskCheckin(sessions, lambda *_: calls.append(2), KioskJournal(path, KEY))
    with pytest.raises(CheckinUnconfirmed):
        submit(rebuilt, token, request)
    assert calls == [1]


def test_separate_adapters_cannot_race_one_pending_write(setup):
    path, sessions, _, token = setup
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow(*_):
        calls.append(1)
        entered.set()
        assert release.wait(3)
    first = KioskCheckin(sessions, slow, KioskJournal(path, KEY))
    # Separate registry models a separate worker, with its own authorized token.
    peer_sessions = KioskSessions('synthetic-a')
    peer_token = peer_sessions.issue(auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True), 'lobby')['token']
    second = KioskCheckin(peer_sessions, lambda *_: calls.append(2), KioskJournal(path, KEY))
    request = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(submit, first, token, request)
        try:
            assert entered.wait(2)
            with pytest.raises(CheckinUnconfirmed):
                submit(second, peer_token, request)
        finally:
            release.set()
        assert running.result(timeout=2)['status'] == 'checked_in'
    assert submit(second, peer_token, request)['status'] == 'checked_in'
    assert calls == [1]


def test_wrong_key_corruption_and_capacity_fail_closed(setup):
    path, sessions, _, token = setup
    journal = KioskJournal(path, KEY)
    journal.MAX_RECEIPTS = 1
    calls = []
    adapter = KioskCheckin(sessions, lambda *_: calls.append(1), journal)
    request = str(uuid.uuid4())
    submit(adapter, token, request)
    with pytest.raises(CheckinThrottled):
        submit(adapter, token, str(uuid.uuid4()))
    with pytest.raises(ValueError):
        KioskJournal(path, b'x' * 32)
    assert submit(adapter, token, request)['status'] == 'checked_in'
    path.write_bytes(b'not a database')
    with pytest.raises(CheckinUnconfirmed):
        submit(adapter, token, request)
    assert calls == [1]


def test_rate_limit_persists_across_adapter_recreation(setup):
    path, sessions, _, token = setup
    calls = []
    journal = KioskJournal(path, KEY)
    journal.MAX_PER_MINUTE = 1
    submit(KioskCheckin(sessions, lambda *_: calls.append(1), journal), token, str(uuid.uuid4()))
    rebuilt = KioskJournal(path, KEY)
    rebuilt.MAX_PER_MINUTE = 1
    with pytest.raises(CheckinThrottled):
        submit(KioskCheckin(sessions, lambda *_: calls.append(2), rebuilt), token, str(uuid.uuid4()))
    assert calls == [1]


def test_process_exit_after_side_effect_cannot_replay_writer(setup):
    path, sessions, _, token = setup
    request = str(uuid.uuid4())
    marker = path.with_suffix('.fictional-write')
    script = '''
import os, sys
from pathlib import Path
from types import SimpleNamespace
from core.kiosk_journal import KioskJournal
journal = KioskJournal(sys.argv[1], bytes.fromhex(sys.argv[4]))
def writer():
    Path(sys.argv[3]).write_text('fictional side effect', encoding='utf-8')
    os._exit(23)
journal.run(SimpleNamespace(tenant_id='synthetic-a', device_id='lobby'), sys.argv[2],
            {'name':'Fictional Visitor','phone':'','reason':''}, writer)
'''
    child = subprocess.run([sys.executable, '-c', script, str(path), request, str(marker), KEY.hex()],
                           capture_output=True, timeout=10)
    assert child.returncode == 23, child.stderr.decode()
    assert marker.read_text(encoding='utf-8') == 'fictional side effect'
    calls = []
    rebuilt = KioskCheckin(sessions, lambda *_: calls.append(1), KioskJournal(path, KEY))
    with pytest.raises(CheckinUnconfirmed):
        submit(rebuilt, token, request)
    assert not calls


def test_missing_live_journal_is_not_silently_recreated(setup):
    path, sessions, _, token = setup
    journal = KioskJournal(path, KEY)
    path.unlink()
    calls = []
    with pytest.raises(CheckinUnconfirmed):
        submit(KioskCheckin(sessions, lambda *_: calls.append(1), journal), token, str(uuid.uuid4()))
    assert not path.exists()
    assert not calls


def test_missing_reservation_after_write_cannot_report_confirmed(setup):
    import sqlite3
    path, sessions, _, token = setup
    journal = KioskJournal(path, KEY)
    def interrupted_restore(*_):
        # Simulate an inconsistent journal restore while a graph write is active.
        with sqlite3.connect(path) as db:
            db.execute('DELETE FROM receipts')
    with pytest.raises(CheckinUnconfirmed):
        submit(KioskCheckin(sessions, interrupted_restore, journal), token, str(uuid.uuid4()))


def test_replaced_journal_with_different_key_denies_new_write(setup):
    import shutil
    path, sessions, _, token = setup
    journal = KioskJournal(path, KEY)
    replacement = path.with_name('replacement.sqlite')
    KioskJournal(replacement, b'z'*32, initialize=True)
    shutil.copyfile(replacement, path)
    calls = []
    with pytest.raises(CheckinUnconfirmed):
        submit(KioskCheckin(sessions, lambda *_: calls.append(1), journal), token, str(uuid.uuid4()))
    assert not calls
