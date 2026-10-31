from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import io
import stat

import pytest
paramiko = pytest.importorskip("paramiko")
from core.bridge_adapters.export_sftp import SFTPExportConnector
from core import bridge_credentials as credentials
from core.bridge_sync import ConnectorFailure
from core.bridge_contracts import validated_capabilities
from tests.test_dealer_bridge import isolated, setup  # noqa: F401
from tests.test_bridge_export_file import CSV


class Provider:
    def read(self, reference): return {"username": "synthetic-user", "password": "synthetic-password"}


class Client:
    def __init__(self):
        self.raw = CSV.encode()
        self.closed = False
        self.file_closed = False
        self.sftp_closed = False
        self.trusted = True
        self.calls = []
        self.failure = None
        self.after_read = None
        self.size_override = None
        self.mode = stat.S_IFREG | 0o400
        self.mtime = 1
    def set_missing_host_key_policy(self, policy):
        assert isinstance(policy, paramiko.RejectPolicy)
    def load_host_keys(self, path): self.calls.append(("load_host_keys", path))
    def get_host_keys(self):
        return SimpleNamespace(lookup=lambda host: {"ssh-test": True} if self.trusted and host == "[sftp.example.invalid]:2222" else None)
    def connect(self, **kwargs):
        self.calls.append(("connect", kwargs))
        if self.failure: raise self.failure
    def open_sftp(self):
        owner = self
        class SFTP:
            def get_channel(self): return SimpleNamespace(settimeout=lambda timeout: owner.calls.append(("timeout", timeout)))
            def lstat(self, path):
                owner.calls.append(("lstat", path))
                return SimpleNamespace(st_mode=owner.mode, st_size=len(owner.raw) if owner.size_override is None else owner.size_override, st_mtime=owner.mtime)
            def open(self, path, mode):
                owner.calls.append(("open", path, mode))
                stream = io.BytesIO(owner.raw)
                class File:
                    def stat(self): return SimpleNamespace(st_mode=owner.mode, st_size=len(owner.raw), st_mtime=1)
                    def read(self, size):
                        owner.calls.append(("read", size))
                        chunk = stream.read(size)
                        if owner.after_read: owner.after_read()
                        return chunk
                    def close(self): owner.file_closed = True
                return File()
            def close(self): owner.sftp_closed = True
        return SFTP()
    def close(self): self.closed = True


def reader(tmp_path, monkeypatch, **overrides):
    system, _ = setup()
    broker = credentials.CredentialBroker()
    scope = dict(reference="vault/sftp", account_ref="synthetic-account", environment="synthetic", objects=["customers"])
    broker.grant(system, provider=Provider(), **scope, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    known = tmp_path / "known_hosts"; known.write_text("synthetic test trust fixture", encoding="utf-8")
    client = Client()
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)
    config = dict(host="sftp.example.invalid", port=2222, remote_path="/exports/customers.csv", known_hosts=known,
                  broker=broker, system_id=system, secret_reference=scope["reference"], account_ref=scope["account_ref"],
                  environment="synthetic", object_type="customers")
    config.update(overrides)
    return SFTPExportConnector(**config), client, broker, system


def test_fixed_path_read_only_snapshot_and_pinned_client_configuration(tmp_path, monkeypatch):
    adapter, client, _, _ = reader(tmp_path, monkeypatch)
    page = adapter.sync("customers")
    assert page.complete and page.records[0].external_id == "1"
    assert adapter.sync("customers", page.cursor).records == ()
    connect = next(args for action, *rest in client.calls if action == "connect" for args in rest)
    assert connect["allow_agent"] is False and connect["look_for_keys"] is False
    assert all(0 < connect[field] <= 10 for field in ("timeout", "auth_timeout", "banner_timeout", "channel_timeout"))
    assert ("open", "/exports/customers.csv", "rb") in client.calls
    assert client.closed and client.file_closed and client.sftp_closed
    assert validated_capabilities(adapter) == {"sync", "schema", "health"}
    assert adapter.schema("customers") == ["external_id", "modified_at", "name", "email"]


def test_unknown_host_is_rejected_before_authentication(tmp_path, monkeypatch):
    adapter, client, _, _ = reader(tmp_path, monkeypatch)
    client.trusted = False
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers")
    assert error.value.code == "permission_denied"
    assert not any(call[0] == "connect" for call in client.calls)
    assert client.closed


@pytest.mark.parametrize("failure,code", [(paramiko.AuthenticationException("secret-password"), "authentication_required"),
    (paramiko.SSHException("unknown host secret"), "permission_denied"), (TimeoutError("secret-host"), "unavailable")])
def test_safe_error_classification(tmp_path, monkeypatch, failure, code):
    adapter, client, _, _ = reader(tmp_path, monkeypatch)
    client.failure = failure
    assert adapter.health()["status"] == code
    assert client.closed


@pytest.mark.parametrize("change", ["symlink", "oversize", "changed", "revoked", "short"])
def test_unsafe_or_changed_remote_snapshot_is_never_returned(tmp_path, monkeypatch, change):
    adapter, client, broker, system = reader(tmp_path, monkeypatch)
    if change == "symlink": client.mode = stat.S_IFLNK | 0o777
    elif change == "oversize": client.size_override = 1_000_001
    elif change == "changed": client.after_read = lambda: setattr(client, "mtime", 2)
    elif change == "revoked": client.after_read = lambda: broker.revoke(system)
    else: client.size_override = len(client.raw) + 1
    with pytest.raises((ConnectorFailure, credentials.CredentialUnavailable)): adapter.sync("customers")
    assert client.closed and client.sftp_closed


@pytest.mark.parametrize("remote_path", ["relative.csv", "/a/../b", "/a//b", "/a/./b", "//server/file", "/a\\b", "/a\n"])
def test_only_fixed_normalized_absolute_remote_paths(tmp_path, monkeypatch, remote_path):
    with pytest.raises(ValueError, match="remote export path"):
        reader(tmp_path, monkeypatch, remote_path=remote_path)


def test_unauthorized_object_or_cursor_never_opens_transport(tmp_path, monkeypatch):
    adapter, client, _, _ = reader(tmp_path, monkeypatch)
    with pytest.raises(ConnectorFailure): adapter.sync("payments")
    with pytest.raises(ConnectorFailure): adapter.sync("customers", "vendor-opaque-cursor")
    assert not client.calls



@pytest.mark.parametrize("key_type,encrypted", [("rsa", False), ("rsa", True), ("ecdsa", False), ("ed25519", False)])
def test_explicit_private_keys_are_loaded_in_memory_without_password_fallback(tmp_path, monkeypatch, key_type, encrypted):
    if key_type == "ed25519":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        pem = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()).decode()
    else:
        key = paramiko.RSAKey.generate(2048) if key_type == "rsa" else paramiko.ECDSAKey.generate()
        stream = io.StringIO(); key.write_private_key(stream, password="synthetic-passphrase" if encrypted else None)
        pem = stream.getvalue()
    monkeypatch.setattr(Provider, "read", lambda self, reference: {"username": "synthetic-user", "private_key": pem, "passphrase": "synthetic-passphrase"})
    adapter, client, _, _ = reader(tmp_path, monkeypatch, authentication=key_type, encrypted_key=encrypted)
    before = set(tmp_path.iterdir())
    assert adapter.sync("customers").records
    connect = next(call[1] for call in client.calls if call[0] == "connect")
    assert isinstance(connect["pkey"], paramiko.PKey)
    assert "password" not in connect and "key_filename" not in connect
    assert connect["allow_agent"] is False and connect["look_for_keys"] is False
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("invalid", ["malformed", "encrypted_missing_passphrase", "rsa_too_small"])
def test_invalid_keys_fail_before_connection_with_safe_status(tmp_path, monkeypatch, invalid):
    values = {"username": "synthetic-user", "private_key": "invalid-synthetic-private-key"}
    encrypted = invalid == "encrypted_missing_passphrase"
    if invalid != "malformed":
        key = paramiko.RSAKey.generate(1024 if invalid == "rsa_too_small" else 2048)
        stream = io.StringIO(); key.write_private_key(stream, password="unprovided-passphrase" if encrypted else None)
        values["private_key"] = stream.getvalue()
    monkeypatch.setattr(Provider, "read", lambda self, reference: values)
    adapter, client, _, _ = reader(tmp_path, monkeypatch, authentication="rsa", encrypted_key=encrypted)
    assert adapter.health() == {"status": "authentication_required"}
    assert not any(call[0] == "connect" for call in client.calls)
