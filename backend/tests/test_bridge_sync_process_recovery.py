"""Fresh-process collector recovery; fictional connector, real isolated graph files."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


CHILD = r'''
import os, socket, sys
from datetime import timedelta
def forbidden(*args, **kwargs):
    raise AssertionError('Network forbidden in synthetic collector test')
socket.create_connection = forbidden
socket.socket.connect = forbidden
from core import dealer_bridge as bridge, bridge_sync as sync, bridge_runtime as runtime
from core.bridge_contracts import SourceRecord, SyncPage
from core.dealeros import ledger
from core.storage import load_graph
from core.storage_paths import GRAPH_PATH
phase, crash_point = sys.argv[1:]
actor = {'employee_id': 'synthetic-admin-a', 'role': 'ADMIN', 'bridge_principal': 'session'}
reviewer = {**actor, 'employee_id': 'synthetic-admin-b'}
sync.credential_store.get_record = lambda employee: {'role': 'ADMIN'}

class FictionalConnector:
    capabilities = frozenset({'sync'})
    calls = []
    def sync(self, object_type, cursor):
        self.calls.append((object_type, cursor))
        if phase == 'crash' and crash_point == 'reading':
            os._exit(23)
        return SyncPage((SourceRecord('customers', 'fictional-1', '2026-01-01T00:00:00Z',
            {'name': 'Fictional Visitor'}),), 'fictional-cursor-1', False)

connector = FictionalConnector()
if phase == 'crash':
    system = bridge.connect(actor, 'Frazer', 'Fictional recovery store')['id']
    mapping = bridge.propose_mapping(actor, system, 'Customer', 'customers',
        {'first_name': {'source': 'name', 'transform': 'text'}})['id']
    bridge.approve_mapping(reviewer, mapping)
    runtime.bind(system, connector, revision='fictional-v1', objects=['customers'])
    state_id = sync.configure(actor, mapping, True, 60)['id']
    result = sync.run_once(actor, state_id)
    if crash_point == 'activated':
        bridge.validate(actor, result['job_id'])
        bridge.activate(reviewer, result['job_id'])
    os._exit(23)

load_graph(GRAPH_PATH)
states = [e for e in ledger.get_all().values() if e.entity_type == 'BridgeSyncState']
assert len(states) == 1
state_id, state = states[0].id, states[0].attributes
assert not runtime._BINDINGS
try:
    sync.run_once(actor, state_id)
except (ValueError, PermissionError):
    pass
else:
    raise AssertionError('Missing runtime binding must block reads/checkpointing')
assert connector.calls == []
runtime.bind(state['system_id'], connector, revision='fictional-v1', objects=['customers'])
def customers():
    return [e for e in ledger.get_all().values() if e.entity_type == 'Customer']
if phase == 'recover':
    assert state['cursor'] is None and state['pages_accepted'] == 0
    if crash_point == 'reading':
        assert not state['pending_job_id'] and not customers()
        assert sync.run_once(actor, state_id)['status'] == 'busy'
        assert connector.calls == []
        clock = sync.utcnow()
        sync.utcnow = lambda: clock + timedelta(hours=1)
    if crash_point != 'activated':
        result = sync.run_once(actor, state_id)
        assert result['status'] == 'awaiting_review' and not customers()
        assert connector.calls == ([('customers', None)] if crash_point == 'reading' else [])
        job = result['job_id']
        assert sync.run_once(actor, state_id)['job_id'] == job
        bridge.validate(actor, job)
        try:
            bridge.activate({**reviewer, 'bridge_principal': 'api'}, job)
        except PermissionError:
            pass
        else:
            raise AssertionError('Recovery must not bypass interactive activation')
        bridge.activate(reviewer, job)
    else:
        assert len(customers()) == 1
    assert sync.run_once(actor, state_id)['status'] == 'checkpointed'
else:
    assert phase == 'verify' and connector.calls == []
assert state['cursor'] == 'fictional-cursor-1' and state['pages_accepted'] == 1
assert state['pending_job_id'] is None and len(customers()) == 1
assert len([e for e in ledger.get_all().values() if e.entity_type == 'BridgeJob']) == 1
assert len(bridge.chrono_observations(actor)) == 1
'''


@pytest.mark.parametrize('crash_point', ['reading', 'staged', 'activated'])
def test_collector_recovers_without_skipping_review_or_advancing_early(tmp_path, crash_point):
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'HOME', 'USERPROFILE'}}
    env.update(DEALEROS_STORAGE_DIR=str(tmp_path), DEALEROS_DEMO='false',
               PYTHON_DOTENV_DISABLED='1', PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    for phase, expected in [('crash', 23), ('recover', 0), ('verify', 0)]:
        result = subprocess.run([sys.executable, '-c', CHILD, phase, crash_point],
                                cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
