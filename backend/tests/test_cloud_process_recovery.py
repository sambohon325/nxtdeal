"""Hard exit after fake cloud upload; no network or real cloud configuration."""
import os
from pathlib import Path
import subprocess
import sys


CHILD = r'''
import hashlib, json, os, socket, sys
from pathlib import Path
def forbidden(*args, **kwargs):
    raise AssertionError('Network forbidden')
socket.create_connection = forbidden
socket.socket.connect = forbidden
from core import dealer_cloud as cloud
root = Path(os.environ['DEALEROS_STORAGE_DIR'])
remote = root.parent / 'fictional-remote'
remote.mkdir(exist_ok=True)
phase = sys.argv[1]
calls = []
def transport(connection, action, name, content=None):
    assert connection == 'fixture'
    calls.append(action)
    target = remote / Path(name).name
    if action == 'rcat':
        target.write_bytes(content)
        if phase == 'crash':
            os._exit(23)
        return b''
    return target.read_bytes()
cloud.transport = transport
if phase == 'crash':
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    (root / 'graph.json').write_text('{"entities":[],"relationships":[]}')
    with cloud.db() as con:
        values = cloud.settings(con)
    values.update(backup_connection='fixture', public_key=pem)
    cloud.configure(values, 'SYNTHETIC-ADMIN')
    cloud.run_backup('SYNTHETIC-ADMIN')
    raise AssertionError('Expected hard exit')

runs = cloud.status()['runs']
assert len(runs) == 1 and runs[0]['state'] == 'running'
prior = runs[0]
assert prior['connection'] == 'fixture'
assert prior['object'] == 'backups/' + prior['id'] + '.nxtbackup'
uploaded = remote / Path(prior['object']).name
blob = uploaded.read_bytes()
assert prior['sha256'] == hashlib.sha256(blob).hexdigest()
assert prior['bytes'] == len(blob)
assert 'verified_at' not in prior
try:
    cloud.run_backup('SYNTHETIC-ADMIN')
except cloud.CloudError:
    pass
else:
    raise AssertionError('An unexpired lease must block restart')
assert calls == []
# Simulate elapsed lease time, not a real operational lease override.
with cloud.db() as con:
    expires = con.execute('SELECT until FROM leases WHERE id=1').fetchone()[0]
cloud.time.time = lambda: expires + 1
fresh = cloud.run_backup('SYNTHETIC-ADMIN')
assert fresh['state'] == 'verified_transfer' and fresh['id'] != prior['id']
old = next(r for r in cloud.status()['runs'] if r['id'] == prior['id'])
assert old['state'] == 'interrupted' and old['object'] == prior['object']
assert old['sha256'] == prior['sha256'] and 'verified_at' not in old
assert uploaded.read_bytes() == blob  # No deletion or overwrite of uncertain upload.
assert len(list(remote.iterdir())) == 2 and calls == ['rcat', 'cat']
'''


def test_interrupted_upload_keeps_destination_and_digest_for_review(tmp_path):
    root = tmp_path / 'tenant'
    root.mkdir()
    # Windows Python resolves user-installed dependencies through APPDATA.
    # Retain OS profile paths without inheriting provider or application secrets.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'}}
    env.update(DEALEROS_STORAGE_DIR=str(root), PYTHON_DOTENV_DISABLED='1',
               PYTHONPATH=str(Path(__file__).resolve().parents[1]),
               NXTDEAL_CLOUD_BACKUPS_ENABLED='true',
               NXTDEAL_CLOUD_CONNECTIONS='{"fixture":{"provider":"s3","remote":"fictional","root":"fictional"}}')
    for phase, expected in [('crash', 23), ('recover', 0)]:
        result = subprocess.run([sys.executable, '-c', CHILD, phase], cwd=tmp_path,
                                env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
