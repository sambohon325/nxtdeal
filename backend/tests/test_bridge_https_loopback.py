"""Real TLS/HTTP tests on disposable loopback only; no external network access."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import ssl
from threading import Thread
from types import SimpleNamespace

import pytest
pytest.importorskip("cryptography")  # Optional certificate-generation test dependency; transport uses stdlib only.
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from core.bridge_adapters.export_https import HTTPSExportConnector
from core.bridge_credentials import CredentialBroker
from core.bridge_sync import ConnectorFailure
from core import dealer_bridge as b, bridge_sync as sync, bridge_runtime as runtime
from tests.test_bridge_sync import configured, state_of, A, B, isolated  # noqa: F401


@pytest.fixture
def server(tmp_path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Disposable Bridge Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "server.pem", tmp_path / "server.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
    data = SimpleNamespace(status=200, requests=[], chunked=False, truncate=False, after_request=None,
        raw=json.dumps([{"external_id":"https-1", "modified_at":"2026-10-04T12:00:00Z", "name":"Synthetic HTTPS customer", "email":"https@example.invalid"}]).encode())
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args): pass
        def do_GET(self):
            data.requests.append((self.command, self.path, self.headers.get("Authorization")))
            if data.after_request: data.after_request()
            self.send_response(data.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            if data.status == 302: self.send_header("Location", "/must-not-follow")
            if data.chunked: self.send_header("Transfer-Encoding", "chunked")
            else: self.send_header("Content-Length", str(len(data.raw) + (10 if data.truncate else 0)))
            self.end_headers()
            try:
                if data.chunked:
                    for start in range(0, len(data.raw), 17):
                        chunk = data.raw[start:start + 17]
                        self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                else: self.wfile.write(data.raw)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.socket = server_context.wrap_socket(httpd.socket, server_side=True)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval":0.05}, daemon=True)
    thread.start()
    data.endpoint = f"https://127.0.0.1:{httpd.server_port}/authorized-export.json"
    data.context = client_context
    yield data
    httpd.shutdown(); httpd.server_close(); thread.join(5)
    assert not thread.is_alive()


def adapter(server, *, trusted=True):
    system, mapping, state, _ = configured()
    class Provider:
        def read(self, reference): return {"access_token":"loopback-synthetic-token"}
    broker = CredentialBroker()
    broker.grant(system, provider=Provider(), reference="vault/test-http", account_ref="test-account", environment="synthetic",
                 objects=["customers"], expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    connector = HTTPSExportConnector(endpoint=server.endpoint, broker=broker, system_id=system, secret_reference="vault/test-http",
        account_ref="test-account", environment="synthetic", object_type="customers", ssl_context=server.context if trusted else None)
    runtime.bind(system, connector, revision="https-test-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, False, 60, reviewed_binding_revision="https-test-1", reviewed_binding_environment="synthetic")
    return connector, state, broker, system


@pytest.mark.parametrize("chunked", [False, True], ids=["length", "chunked"])
def test_verified_tls_snapshot_requires_review_and_keeps_stable_cursor(server, chunked, monkeypatch):
    server.chunked = chunked
    _, state, _, _ = adapter(server)
    job = sync.run_once(A, state)["job_id"]
    assert state_of(state)["cursor"] is None
    b.validate(A, job); b.activate(B, job)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    later = sync.utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(sync, "utcnow", lambda: later)
    assert sync.run_once(A, state)["status"] == "idle"
    assert state_of(state)["pages_accepted"] == 1
    assert server.requests == [("GET", "/authorized-export.json", "Bearer loopback-synthetic-token")] * 2
    assert b.import_report(A, job)["receipt_integrity"] == "consistent"


def test_untrusted_certificate_never_transmits_http_authorization(server):
    connector, _, _, _ = adapter(server, trusted=False)
    with pytest.raises(ConnectorFailure) as error: connector.sync("customers")
    assert error.value.code == "permission_denied" and not server.requests


def test_redirect_is_not_followed_and_truncated_body_never_stages(server):
    connector, state, _, _ = adapter(server)
    server.status = 302
    with pytest.raises(ConnectorFailure) as error: connector.sync("customers")
    assert error.value.code == "permission_denied" and len(server.requests) == 1
    server.status, server.truncate = 200, True
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["pending_job_id"] is None and state_of(state)["cursor"] is None


def test_revocation_during_verified_tls_read_discards_response(server):
    _, state, broker, system = adapter(server)
    server.after_request = lambda: broker.revoke(system)
    assert sync.run_once(A, state)["status"] == "blocked"
    assert state_of(state)["last_error_code"] == "authentication_required"
    assert state_of(state)["pending_job_id"] is None and state_of(state)["cursor"] is None
