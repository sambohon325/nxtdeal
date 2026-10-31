"""Keep provider-free application imports covered even when CI sets a dummy key."""
import os
from pathlib import Path
import subprocess
import sys


def test_app_route_checks_in_fresh_process_without_provider_construction():
    backend = Path(__file__).resolve().parents[1]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('OPENAI_')}
    # Prevent dotenv from restoring credentials removed from this subprocess.
    environment['PYTHON_DOTENV_DISABLED'] = '1'
    program = '''
import socket
import ipaddress
from unittest.mock import patch
import pytest

def forbidden(*args, **kwargs):
    raise AssertionError('Provider construction or network access during startup')

original_connect = socket.socket.connect
def local_event_loop_connect(sock, address):
    # Windows asyncio constructs its socketpair with a loopback connect.
    if sock.family == getattr(socket, 'AF_UNIX', None):
        return original_connect(sock, address)
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original_connect(sock, address)
    return forbidden()

# The route suite imports the actual app and uses conftest's disposable storage.
# Fail before any provider or external transport can be used; no dummy key needed.
with patch('openai.OpenAI', side_effect=forbidden) as provider, \\
     patch.object(socket.socket, 'connect', local_event_loop_connect), \\
     patch.object(socket, 'create_connection', forbidden):
    result = pytest.main(['tests/test_route_protection.py',
                          'tests/test_provider_free_http.py', '-q', '--tb=short'])
    provider.assert_not_called()
raise SystemExit(result)
'''
    completed = subprocess.run([sys.executable, '-c', program], cwd=backend,
                               env=environment, capture_output=True, text=True,
                               timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
