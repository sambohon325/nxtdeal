"""Fictional HTTP -> real walk-in -> journal/graph recovery acceptance.

Only the opt-in router is mounted in an isolated test app. No production app,
provider, network listener or operational enrollment is enabled.
"""
from contextlib import contextmanager
from copy import deepcopy
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.kiosk import create_kiosk_router
from core import auth
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD
from core.kiosk_checkin import KioskCheckin, _write_walk_in
from core.kiosk_journal import KioskJournal
from core.kiosk_sessions import KioskSessions
from core.storage import load_graph, save_graph

KEY = b'fictional-http-recovery-key-only!!'


@pytest.fixture
def staff():
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    ledger.reset()
    try:
        auth.credential_store.set_credential('SYN-ADMIN', 'Fictional2026!', 'ADMIN', must_change_password=False)
        ledger.add_entity(Entity(id='SYN-REP', entity_type=EMPLOYEE,
                                 attributes={'Department': 'Sales', 'FirstName': 'Fictional'}))
        yield auth.issue_token('SYN-ADMIN', 'ADMIN', fresh_auth=True)
    finally:
        ledger.reset()
        auth.credential_store.load_credentials(previous)


def headers(token):
    return {'Authorization': 'Bearer ' + token}


@contextmanager
def application(path, staff, writer=None):
    sessions = KioskSessions('synthetic-recovery')
    journal = KioskJournal(path, KEY)
    app = FastAPI()
    app.include_router(create_kiosk_router(sessions, enabled=True,
        checkin=KioskCheckin(sessions, writer=writer, journal=journal)))
    with TestClient(app) as client:
        grant = client.post('/kiosk/enroll', headers=headers(staff), json={'device_id': 'lobby'})
        assert grant.status_code == 201
        yield client, grant.json()['token'], journal


def leads():
    return {key: deepcopy(item.attributes) for key, item in ledger.get_all().items()
            if item.entity_type == LEAD}


@pytest.mark.parametrize('uncertain', [False, True])
def test_quiesced_graph_and_journal_restore_preserves_http_replay(staff, tmp_path, uncertain):
    path = tmp_path / 'live.sqlite'
    KioskJournal(path, KEY, initialize=True)
    data = {'device_id': 'lobby', 'request_id': str(uuid.uuid4()),
            'name': 'Fictional Recovery Visitor', 'reason': 'Synthetic acceptance'}

    def write_then_fail(identity, fields):
        _write_walk_in(identity, fields)
        raise OSError('fictional failure after real ledger persistence')

    with application(path, staff, write_then_fail if uncertain else None) as (client, token, journal):
        result = client.post('/kiosk/checkin', headers=headers(token), json=data)
        assert result.status_code == (503 if uncertain else 200)
        assert result.headers['cache-control'] == 'no-store'
        if uncertain:
            assert result.json()['retry_safe'] is False
        else:
            assert result.json() == {'status': 'checked_in', 'receipt': data['request_id']}
        original = leads()
        assert len(original) == 1
        attributes = next(iter(original.values()))
        assert attributes['AssignedSalesperson'] == 'SYN-REP'
        assert attributes['up_logged_by'] == 'KIOSK:lobby'
        # No requests/writers are running: this pair is intentionally quiesced.
        graph_copy = tmp_path / 'graph-snapshot.json'
        save_graph(str(graph_copy))
        restored = tmp_path / 'restored.sqlite'
        assert journal.backup_to(restored) == {
            'pending': int(uncertain), 'confirmed': int(not uncertain)}

    path.rename(tmp_path / 'offline.sqlite')
    ledger.reset()
    load_graph(str(graph_copy))
    assert leads() == original
    # Rebuild all request/session/adapter state; only copied stores survive.
    with application(restored, staff) as (client, replacement, journal):
        assert replacement != token
        assert client.post('/kiosk/checkin', headers=headers(token), json=data).status_code == 401
        replay = client.post('/kiosk/checkin', headers=headers(replacement), json=data)
        assert replay.status_code == (503 if uncertain else 200)
        assert replay.json() == result.json()
        assert leads() == original
        conflict = client.post('/kiosk/checkin', headers=headers(replacement),
                               json={**data, 'name': 'Other Fictional Visitor'})
        assert conflict.status_code == 409
        assert leads() == original
        assert journal.pending_report('synthetic-recovery')['pending_count'] == int(uncertain)
        # A separately identified visitor remains possible after recovery.
        new = client.post('/kiosk/checkin', headers=headers(replacement),
                          json={**data, 'request_id': str(uuid.uuid4()), 'name': 'Next Fictional Visitor'})
        assert new.status_code == 200
        assert len(leads()) == 2


def test_lost_journal_returns_private_unconfirmed_http_without_graph_write(staff, tmp_path):
    path = tmp_path / 'live.sqlite'
    KioskJournal(path, KEY, initialize=True)
    with application(path, staff) as (client, token, _):
        path.rename(tmp_path / 'offline.sqlite')
        result = client.post('/kiosk/checkin', headers=headers(token), json={
            'device_id': 'lobby', 'request_id': str(uuid.uuid4()), 'name': 'Fictional Visitor'})
        assert result.status_code == 503
        assert result.json()['retry_safe'] is False
        assert result.headers['cache-control'] == 'no-store'
        assert 'Fictional Visitor' not in result.text
        assert str(tmp_path) not in result.text
        assert not path.exists()
        assert not leads()
