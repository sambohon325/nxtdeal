"""Hard process exits around credential replacement; synthetic files, no network."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

CHILD = r'''
import os, socket, sys
from types import SimpleNamespace

def forbidden(*args, **kwargs):
    raise AssertionError('Network forbidden')
socket.create_connection = forbidden
socket.socket.connect = forbidden
from core import auth_storage
phase, path = sys.argv[1:]
auth_storage.credential_store = SimpleNamespace(credentials={'synthetic': {'mfa_version': 2}})
replace = auth_storage.os.replace

def interrupted_replace(source, destination):
    if phase == 'before':
        os._exit(23)
    replace(source, destination)
    os._exit(24)
auth_storage.os.replace = interrupted_replace
auth_storage.save_credentials(path)
raise AssertionError('Expected process exit')
'''


@pytest.mark.parametrize('phase,exit_code,version', [('before', 23, 1), ('after', 24, 2)])
def test_interrupted_replace_retains_complete_credential_snapshot(tmp_path, phase, exit_code, version):
    target = tmp_path / 'credentials.json'
    target.write_text(json.dumps({'synthetic': {'mfa_version': 1}}), encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if key.upper() in
           {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'}}
    env.update(DEALEROS_STORAGE_DIR=str(tmp_path), PYTHON_DOTENV_DISABLED='1',
               PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, '-c', CHILD, phase, str(target)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert json.loads(target.read_text(encoding='utf-8')) == {'synthetic': {'mfa_version': version}}
    leftovers = list(tmp_path.glob('.credentials-*.tmp'))
    if phase == 'before':
        # Abrupt exit cannot execute finally cleanup; the private temp is not the active file.
        assert len(leftovers) == 1
        assert json.loads(leftovers[0].read_text()) == {'synthetic': {'mfa_version': 2}}
        if os.name == 'posix':
            assert leftovers[0].stat().st_mode & 0o077 == 0
    else:
        assert leftovers == []
