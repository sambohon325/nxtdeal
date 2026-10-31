from concurrent.futures import ThreadPoolExecutor
import hashlib
import shutil
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from core.kiosk_checkin import CheckinUnconfirmed
from core.kiosk_journal import KioskJournal

KEY = b'fictional-backup-test-key-only!!00'
IDENTITY = SimpleNamespace(tenant_id='synthetic-a', device_id='lobby')
FIELDS = {'name': 'Fictional Visitor', 'phone': '', 'reason': ''}


def test_backup_restore_preserves_confirmed_and_uncertain_without_rewriting(tmp_path):
    live = KioskJournal(tmp_path / 'live.sqlite', KEY, initialize=True)
    live.run(IDENTITY, 'confirmed', FIELDS, lambda: None)
    with pytest.raises(CheckinUnconfirmed):
        live.run(IDENTITY, 'uncertain', FIELDS, lambda: (_ for _ in ()).throw(OSError('fictional')))
    snapshot = tmp_path / 'snapshot.sqlite'
    assert live.backup_to(snapshot) == {'confirmed': 1, 'pending': 1}
    restored = tmp_path / 'restored.sqlite'
    shutil.copyfile(snapshot, restored)
    # Recovery uses only the copy, with the source moved out of the configured path.
    live.path.rename(tmp_path / 'offline.sqlite')
    journal = KioskJournal(restored, KEY)
    calls = []
    assert journal.run(IDENTITY, 'confirmed', FIELDS, lambda: calls.append(1))['status'] == 'checked_in'
    with pytest.raises(CheckinUnconfirmed):
        journal.run(IDENTITY, 'uncertain', FIELDS, lambda: calls.append(2))
    assert not calls
    journal.run(IDENTITY, 'new-after-restore', FIELDS, lambda: calls.append(3))
    reopened = KioskJournal(restored, KEY)
    reopened.run(IDENTITY, 'new-after-restore', FIELDS, lambda: calls.append(4))
    assert calls == [3]


def test_snapshot_during_inflight_write_retains_pending_boundary(tmp_path):
    journal = KioskJournal(tmp_path / 'live.sqlite', KEY, initialize=True)
    entered, release = threading.Event(), threading.Event()
    def writer():
        entered.set()
        assert release.wait(3)
    snapshot = tmp_path / 'snapshot.sqlite'
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(journal.run, IDENTITY, 'inflight', FIELDS, writer)
        try:
            assert entered.wait(2)
            assert journal.backup_to(snapshot) == {'pending': 1, 'confirmed': 0}
        finally:
            release.set()
        work.result(timeout=2)
    assert journal.inspect_snapshot(journal.path, KEY) == {'pending': 0, 'confirmed': 1}
    assert journal.inspect_snapshot(snapshot, KEY) == {'pending': 1, 'confirmed': 0}


def test_existing_destination_and_live_file_never_overwritten(tmp_path):
    journal = KioskJournal(tmp_path / 'live.sqlite', KEY, initialize=True)
    snapshot = tmp_path / 'snapshot.sqlite'
    journal.backup_to(snapshot)
    for target in (snapshot, journal.path):
        before = hashlib.sha256(target.read_bytes()).digest()
        with pytest.raises(FileExistsError):
            journal.backup_to(target)
        assert hashlib.sha256(target.read_bytes()).digest() == before


def test_validation_never_creates_repairs_or_modifies_bad_snapshot(tmp_path):
    missing = tmp_path / 'missing.sqlite'
    with pytest.raises(sqlite3.Error):
        KioskJournal.inspect_snapshot(missing, KEY)
    assert not missing.exists()
    corrupt = tmp_path / 'corrupt.sqlite'
    corrupt.write_bytes(b'fictional corrupt snapshot')
    with pytest.raises(sqlite3.Error):
        KioskJournal.inspect_snapshot(corrupt, KEY)
    assert corrupt.read_bytes() == b'fictional corrupt snapshot'
    journal = KioskJournal(tmp_path / 'live.sqlite', KEY, initialize=True)
    before = journal.path.read_bytes()
    with pytest.raises(ValueError):
        KioskJournal.inspect_snapshot(journal.path, b'x'*32)
    assert journal.path.read_bytes() == before


def test_failed_backup_removes_only_its_new_incomplete_file(tmp_path):
    journal = KioskJournal(tmp_path / 'live.sqlite', KEY, initialize=True)
    journal.path.write_bytes(b'fictional corrupt source')
    target = tmp_path / 'failed.sqlite'
    with pytest.raises(sqlite3.Error):
        journal.backup_to(target)
    assert not target.exists()
    assert journal.path.read_bytes() == b'fictional corrupt source'


def test_normal_startup_cannot_provision_missing_or_empty_journal(tmp_path):
    missing = tmp_path / 'missing.sqlite'
    with pytest.raises(sqlite3.Error):
        KioskJournal(missing, KEY)
    assert not missing.exists()
    missing.touch()
    with pytest.raises(sqlite3.Error):
        KioskJournal(missing, KEY)
    assert missing.read_bytes() == b''


def test_explicit_provisioning_never_replaces_existing_state(tmp_path):
    path = tmp_path / 'live.sqlite'
    KioskJournal(path, KEY, initialize=True)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        KioskJournal(path, KEY, initialize=True)
    assert path.read_bytes() == before
    path.write_bytes(b'corrupt but must be preserved for investigation')
    with pytest.raises(FileExistsError):
        KioskJournal(path, KEY, initialize=True)
    assert path.read_bytes() == b'corrupt but must be preserved for investigation'


@pytest.mark.parametrize('value', ['false', 'true', 1, None])
def test_provision_flag_rejects_ambiguous_configuration(tmp_path, value):
    path = tmp_path / 'live.sqlite'
    with pytest.raises(ValueError):
        KioskJournal(path, KEY, initialize=value)
    assert not path.exists()
