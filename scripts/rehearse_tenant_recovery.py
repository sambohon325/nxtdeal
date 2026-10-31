"""Fresh-process tenant workers for the offline synthetic Hub recovery rehearsal."""
import json
import os
from pathlib import Path
import subprocess
import sys

from synthetic_dealership import ROOT, PASSWORD, clean_environment, create


def run_tenants(base, stage):
    for number in (1, 2):
        root = base/'tenants'/f'tenant{number}'
        if stage == 'seed':
            create(root)  # Brand-new temporary fixture; never an existing dealer store.
        env = clean_environment(root)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), stage, str(number)],
                                cwd=root, env=env, text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(f'Synthetic tenant {number} {stage} failed:\n{result.stderr}')


def worker(stage, number):
    root = Path.cwd()
    assert os.environ.get('NXTDEAL_SYNTHETIC') == 'true'
    clean_environment(root)  # Validate marker before application imports.
    assert Path(os.environ['DEALEROS_STORAGE_DIR']).resolve() == root/'dealer'
    from fastapi.testclient import TestClient
    from api.app import app
    from core.dealeros import ledger
    from core.entities import Entity
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    client = TestClient(app)  # Lifespan disabled: no scheduled jobs or provider delivery.
    own = f'SYN-TENANT-{number}'
    peer = f'SYN-TENANT-{3-number}'
    if stage == 'seed':
        ledger.add_entity(Entity(id=own, entity_type='Customer', attributes={
            'name':f'Fictional Tenant {number} Only', 'synthetic':True}))
        save_graph(GRAPH_PATH)
        result = client.post('/auth/login', json={'employee_id':'EMP-00001','password':PASSWORD})
        assert result.status_code == 200
        (root/'proof.json').write_text(json.dumps({'token':result.json()['token']}))
    else:
        assert ledger.get_entity(own).attributes['name'] == f'Fictional Tenant {number} Only'
        assert ledger.get_entity(peer) is None
        own_token = json.loads((root/'proof.json').read_text())['token']
        peer_token = json.loads((root.parent/f'tenant{3-number}'/'proof.json').read_text())['token']
        assert client.get('/dealer-bridge/system-map', headers={'Authorization':'Bearer '+own_token}).status_code == 200
        assert client.get('/dealer-bridge/system-map', headers={'Authorization':'Bearer '+peer_token}).status_code == 401
        login = client.post('/auth/login', json={'employee_id':'EMP-00003','password':PASSWORD})
        assert login.status_code == 200
        assert client.get('/dealer-bridge/system-map', headers={'Authorization':'Bearer '+login.json()['token']}).status_code == 403
        new_id = own+'-AFTER-RESTORE'
        if stage == 'write_after_restore':
            ledger.get_entity(own).attributes['recovery_note'] = 'Fictional write after recovery'
            ledger.add_entity(Entity(id=new_id, entity_type='Customer', attributes={
                'name':f'Fictional New Tenant {number} Customer', 'synthetic':True}))
            save_graph(GRAPH_PATH)
        elif stage == 'verify_after_write':
            assert ledger.get_entity(own).attributes['recovery_note'] == 'Fictional write after recovery'
            assert ledger.get_entity(new_id).attributes['name'] == f'Fictional New Tenant {number} Customer'
            assert ledger.get_entity(peer+'-AFTER-RESTORE') is None
    print(json.dumps({'tenant':number,'stage':stage,'result':'passed'}))


if __name__ == '__main__':
    stage, number = sys.argv[1:]
    assert stage in ('seed', 'restore', 'write_after_restore', 'verify_after_write') and number in ('1','2')
    worker(stage, int(number))
