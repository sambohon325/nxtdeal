import hashlib
from types import SimpleNamespace
from contextlib import closing
import sqlite3

import pytest
from core.kiosk_journal import KioskJournal
from core.kiosk_checkin import CheckinUnconfirmed

KEY = b'fictional-pending-review-key-00000'


def pending(journal, tenant, request, name='Fictional Visitor'):
    with pytest.raises(CheckinUnconfirmed):
        journal.run(SimpleNamespace(tenant_id=tenant, device_id='lobby'), request,
                    {'name': name}, lambda: (_ for _ in ()).throw(OSError('unknown write')))


def test_report_is_tenant_scoped_paginated_and_does_not_change_receipts(tmp_path):
    path = tmp_path / 'journal.sqlite'
    journal = KioskJournal(path, KEY, initialize=True)
    pending(journal, 'synthetic-a', 'a1')
    pending(journal, 'synthetic-a', 'a2')
    pending(journal, 'synthetic-b', 'b1', 'Other fictional visitor')
    journal.run(SimpleNamespace(tenant_id='synthetic-a', device_id='lobby'), 'confirmed', {}, lambda: None)
    before = hashlib.sha256(path.read_bytes()).digest()
    first = journal.pending_report('synthetic-a', limit=1)
    second = journal.pending_report('synthetic-a', limit=1, offset=first['next_offset'])
    assert first['pending_count'] == second['pending_count'] == 2
    assert [first['items'][0]['request_id'], second['items'][0]['request_id']] == ['a1', 'a2']
    assert second['next_offset'] is None
    assert set(first['items'][0]) == {'device_id', 'request_id', 'reserved_at'}
    assert first['retry_safe'] is False and first['requires_quiesced_graph_review'] is True
    assert 'Fictional' not in repr(first) and 'fingerprint' not in repr(first)
    assert journal.pending_report('missing')['pending_count'] == 0
    assert hashlib.sha256(path.read_bytes()).digest() == before
    # Looking at a pending item never clears it or authorizes re-execution.
    calls = []
    with pytest.raises(CheckinUnconfirmed):
        journal.run(SimpleNamespace(tenant_id='synthetic-a', device_id='lobby'), 'a1',
                    {'name':'Fictional Visitor'}, lambda: calls.append(1))
    assert not calls


@pytest.mark.parametrize('kwargs', [{'limit':0}, {'limit':101}, {'limit':True},
                                   {'offset':-1}, {'offset':'0'}, {'offset':False}])
def test_invalid_pagination_rejected(tmp_path, kwargs):
    journal = KioskJournal(tmp_path / 'journal.sqlite', KEY, initialize=True)
    with pytest.raises(ValueError):
        journal.pending_report('synthetic-a', **kwargs)


def test_missing_or_wrong_key_report_does_not_repair_source(tmp_path):
    path = tmp_path / 'journal.sqlite'
    journal = KioskJournal(path, KEY, initialize=True)
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute('UPDATE metadata SET proof=? WHERE id=1', (b'wrong',))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        journal.pending_report('synthetic-a')
    assert path.read_bytes() == before
    path.unlink()
    with pytest.raises(sqlite3.Error):
        journal.pending_report('synthetic-a')
    assert not path.exists()
