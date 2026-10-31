"""Hard-exit/restart rehearsal with real graph persistence and a local fake sink."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


CHILD = r'''
import json, os, socket, sqlite3, sys
from datetime import timedelta
from pathlib import Path

def no_network(*args, **kwargs):
    raise AssertionError('Network forbidden in synthetic recovery')
socket.create_connection = no_network
socket.socket.connect = no_network

from core import dealer_bridge as bridge, bridge_chrono as outbox
from core.storage import load_graph
from core.storage_paths import GRAPH_PATH
from chrono.delivery import DeliveryReceipt

root = Path(os.environ['DEALEROS_STORAGE_DIR'])
assert Path(GRAPH_PATH).resolve().parent == root.resolve()
phase, crash_point = sys.argv[1:]
actor = {'employee_id': 'synthetic-admin-a', 'role': 'ADMIN', 'bridge_principal': 'session'}
reviewer = {**actor, 'employee_id': 'synthetic-admin-b'}
outbox.credential_store.get_record = lambda employee: {'role': 'ADMIN'}

class LocalSink:
    supports_idempotency = True
    calls = 0

    def deliver(self, *, workspace_id, events):
        self.calls += 1
        if phase == 'crash' and crash_point == 'before_accept':
            os._exit(23)
        with sqlite3.connect(root / 'fake_sink.sqlite') as db:
            db.execute('CREATE TABLE IF NOT EXISTS accepted (event_id TEXT PRIMARY KEY)')
            db.executemany('INSERT OR IGNORE INTO accepted VALUES (?)', [(e.event_id,) for e in events])
        if phase == 'crash':
            os._exit(23)  # Accepted durably, but no local acknowledgement exists.
        return DeliveryReceipt(tuple(e.event_id for e in events))

sink = LocalSink()
if phase == 'crash':
    system = bridge.connect(actor, 'CSV', 'Fictional recovery source')['id']
    mapping = bridge.propose_mapping(actor, system, 'Customer', 'customers',
        {'first_name': {'source': 'name', 'transform': 'text'}})['id']
    bridge.approve_mapping(reviewer, mapping)
    job = bridge.stage(actor, mapping,
        'external_id,modified_at,name\n1,2026-01-01T00:00:00Z,Fictional Ada\n2,2026-01-01T00:00:00Z,Fictional Grace\n')['id']
    bridge.validate(actor, job)
    bridge.activate(reviewer, job)
    outbox.bind_sink('synthetic-local-sink', 'v1', sink)
    outbox.configure(actor, True, 'synthetic-local-sink', 'v1')
    outbox.deliver_once(actor)
    raise AssertionError('Expected hard exit')

load_graph(GRAPH_PATH)
assert outbox._BINDING is None  # Runtime binding never restored from stored policy.
try:
    outbox.deliver_once(actor)
except ValueError:
    pass
else:
    raise AssertionError('Restart without trusted binding must fail closed')
assert sink.calls == 0
outbox.bind_sink('synthetic-local-sink', 'v1', sink)
if phase == 'recover':
    before = outbox.receipts(actor)
    assert len(before) == 2 and all(r['status'] == 'in_flight' and r['attempts'] == 1 for r in before)
    if crash_point == 'after_accept':
        with sqlite3.connect(root / 'fake_sink.sqlite') as db:
            prior_accepted = {row[0] for row in db.execute('SELECT event_id FROM accepted')}
        assert prior_accepted == {r['event_id'] for r in before}
    else:
        assert not (root / 'fake_sink.sqlite').exists()
    assert outbox.deliver_once(actor)['status'] == 'idle'  # Unexpired lease prevents premature replay.
    assert sink.calls == 0
    clock = outbox.utcnow()
    outbox.utcnow = lambda: clock + timedelta(seconds=outbox.LEASE_SECONDS + 1)
    assert outbox.deliver_once(actor)['delivered'] == 2
    assert sink.calls == 1
else:
    assert phase == 'verify'
    assert outbox.deliver_once(actor)['status'] == 'idle'
    assert sink.calls == 0
receipts = outbox.receipts(actor)
assert len(receipts) == 2 and all(r['status'] == 'delivered' and r['attempts'] == 2 for r in receipts)
with sqlite3.connect(root / 'fake_sink.sqlite') as db:
    accepted = {row[0] for row in db.execute('SELECT event_id FROM accepted')}
assert accepted == {r['event_id'] for r in receipts}
assert len(bridge.chrono_observations(actor)) == 2
print(json.dumps({'phase': phase, 'accepted': len(accepted)}))
'''


@pytest.mark.parametrize('crash_point', ['before_accept', 'after_accept'])
def test_hard_exit_recovery_requires_binding_and_replays_stable_ids(tmp_path, crash_point):
    backend = Path(__file__).resolve().parents[1]
    # Do not inherit live service credentials, repository modes or provider settings.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'HOME', 'USERPROFILE'}}
    env.update(DEALEROS_STORAGE_DIR=str(tmp_path), DEALEROS_DEMO='false',
               PYTHON_DOTENV_DISABLED='1', PYTHONPATH=str(backend))
    for phase, expected in [('crash', 23), ('recover', 0), ('verify', 0)]:
        result = subprocess.run([sys.executable, '-c', CHILD, phase, crash_point],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
