"""Real SSH/SFTP protocol over loopback, ephemeral trust and synthetic data only."""
from datetime import datetime, timedelta, timezone
import os
import socket
import stat
import threading
from types import SimpleNamespace

import pytest
paramiko = pytest.importorskip("paramiko")
from core import bridge_credentials as credentials, bridge_runtime as runtime, bridge_sync as sync, dealer_bridge as bridge
from core.bridge_adapters.export_sftp import SFTPExportConnector
from core.bridge_sync import ConnectorFailure
from core.dealeros import ledger
from tests.test_bridge_sync import configured, A, B, API, state_of, isolated  # noqa: F401
from tests.test_bridge_export_file import CSV


@pytest.fixture
def sftp_server(tmp_path):
    host_key = paramiko.RSAKey.generate(2048)
    state = SimpleNamespace(raw=CSV.encode(), auth_attempts=0, reads=0, opens=[], transports=[], include_times=True, authorized_user_key=None, key_attempts=0)
    stop = threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0)); listener.listen(4); listener.settimeout(0.2)
    port = listener.getsockname()[1]
    known = tmp_path / "known_hosts"
    known.write_text(f"[127.0.0.1]:{port} {host_key.get_name()} {host_key.get_base64()}\n", encoding="utf-8")

    class Auth(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            state.auth_attempts += 1
            return paramiko.AUTH_SUCCESSFUL if (username, password) == ("fixture-user", "fixture-password") else paramiko.AUTH_FAILED
        def check_auth_publickey(self, username, key):
            state.key_attempts += 1
            return paramiko.AUTH_SUCCESSFUL if username == "fixture-user" and key == state.authorized_user_key else paramiko.AUTH_FAILED
        def get_allowed_auths(self, username): return "password,publickey"
        def check_channel_request(self, kind, channel_id):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def attributes():
        value = paramiko.SFTPAttributes()
        value.st_mode, value.st_size = stat.S_IFREG | 0o400, len(state.raw)
        if state.include_times: value.st_atime, value.st_mtime = 1, 1
        return value

    class Handle(paramiko.SFTPHandle):
        def stat(self): return attributes()
        def read(self, offset, length):
            state.reads += 1
            return state.raw[offset:offset + length]

    class Files(paramiko.SFTPServerInterface):
        def stat(self, path): return attributes() if path == "/exports/customers.csv" else paramiko.SFTP_NO_SUCH_FILE
        lstat = stat
        def open(self, path, flags, attr):
            state.opens.append((path, flags))
            if path != "/exports/customers.csv" or flags != os.O_RDONLY:
                return paramiko.SFTP_PERMISSION_DENIED
            return Handle(flags)

    def serve():
        while not stop.is_set():
            try: connection, _ = listener.accept()
            except socket.timeout: continue
            except OSError: break
            transport = paramiko.Transport(connection)
            transport.handshake_timeout = 5
            state.transports.append(transport)
            try:
                transport.add_server_key(host_key)
                transport.set_subsystem_handler("sftp", paramiko.SFTPServer, Files)
                transport.start_server(server=Auth())
                while transport.is_active() and not stop.wait(0.02): pass
            except (EOFError, OSError, paramiko.SSHException):
                pass  # Expected when a client rejects the pinned key or authentication.
            finally: transport.close()
    thread = threading.Thread(target=serve, name="synthetic-sftp-loopback", daemon=True)
    thread.start()
    try:
        yield state, port, known
    finally:
        stop.set(); listener.close()
        for transport in state.transports: transport.close()
        thread.join(timeout=6)
        assert not thread.is_alive(), "Synthetic loopback SFTP server did not stop"


class Provider:
    def __init__(self, password="fixture-password"): self.password = password
    def read(self, reference): return {"username": "fixture-user", "password": self.password}


def adapter_for(system, port, known, password="fixture-password", *, authentication="password", encrypted_key=False):
    broker = credentials.CredentialBroker()
    broker.grant(system, provider=Provider(password), reference="fixture/sftp", account_ref="fixture-account",
                 environment="synthetic", objects=["customers"], expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    return SFTPExportConnector(host="127.0.0.1", port=port, remote_path="/exports/customers.csv", known_hosts=known,
                              broker=broker, system_id=system, secret_reference="fixture/sftp", account_ref="fixture-account",
                              environment="synthetic", object_type="customers", timeout_seconds=3, authentication=authentication, encrypted_key=encrypted_key)


def test_real_sftp_page_stages_then_human_activation_checkpoints(sftp_server):
    server, port, known = sftp_server
    system, mapping, state, _ = configured()
    adapter = adapter_for(system, port, known)
    runtime.bind(system, adapter, revision="loopback-sftp-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="loopback-sftp-1", reviewed_binding_environment="synthetic")
    result = sync.run_once(A, state)
    assert result["status"] == "awaiting_review"
    assert state_of(state)["cursor"] is None
    assert server.auth_attempts == 1 and server.reads > 0
    assert server.opens == [("/exports/customers.csv", os.O_RDONLY)]
    assert not any(entity.entity_type == "Customer" for entity in ledger.entities.values())
    job = result["job_id"]
    bridge.validate(API, job)
    with pytest.raises(PermissionError): bridge.activate(API, job)
    bridge.activate(B, job)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    assert adapter.sync("customers", state_of(state)["cursor"]).records == ()
    report = bridge.import_report(A, job)
    assert report["receipt_integrity"] == "consistent"
    assert "fixture-password" not in str({key: value.attributes for key, value in ledger.entities.items()})


def test_real_host_key_mismatch_rejects_before_password_authentication(sftp_server, tmp_path):
    server, port, _ = sftp_server
    system, _, _, _ = configured()
    wrong = paramiko.RSAKey.generate(2048)
    trust = tmp_path / "wrong_known_hosts"
    trust.write_text(f"[127.0.0.1]:{port} {wrong.get_name()} {wrong.get_base64()}\n", encoding="utf-8")
    with pytest.raises(ConnectorFailure) as error: adapter_for(system, port, trust).sync("customers")
    assert error.value.code == "permission_denied" and not error.value.retryable
    assert server.auth_attempts == 0 and server.reads == 0


def test_real_authentication_failure_returns_safe_renewal_state(sftp_server):
    server, port, known = sftp_server
    system, _, _, _ = configured()
    report = adapter_for(system, port, known, "wrong-fixture-password").health()
    assert report == {"status": "authentication_required"}
    assert server.auth_attempts > 0 and server.reads == 0



def test_real_server_missing_timestamp_metadata_is_not_silently_accepted(sftp_server):
    server, port, known = sftp_server
    server.include_times = False
    system, _, _, _ = configured()
    with pytest.raises(ConnectorFailure) as error: adapter_for(system, port, known).sync("customers")
    assert error.value.code == "source_changed" and not error.value.retryable
    assert server.reads == 0



def test_real_private_key_authentication_uses_only_explicit_in_memory_key(sftp_server, monkeypatch):
    import io
    server, port, known = sftp_server
    key = paramiko.RSAKey.generate(2048)
    server.authorized_user_key = key
    buffer = io.StringIO(); key.write_private_key(buffer, password="fixture-key-passphrase")
    monkeypatch.setattr(Provider, "read", lambda self, reference: {"username": "fixture-user", "private_key": buffer.getvalue(), "passphrase": "fixture-key-passphrase"})
    system, _, _, _ = configured()
    adapter = adapter_for(system, port, known, authentication="rsa", encrypted_key=True)
    assert adapter.sync("customers").records[0].external_id == "1"
    assert server.key_attempts > 0 and server.auth_attempts == 0
