from datetime import datetime, timedelta, timezone
import io
import ssl
from types import SimpleNamespace

import pytest
from core.bridge_adapters import export_https as transport
from core.bridge_credentials import CredentialBroker, CredentialUnavailable
from core.bridge_sync import ConnectorFailure
from core.bridge_contracts import validated_capabilities
from tests.test_dealer_bridge import isolated, setup  # noqa: F401
from tests.test_bridge_export_file import CSV


class Provider:
    token = "synthetic-token-ONLY"
    def read(self, reference): return {"access_token": self.token}


class Response:
    def __init__(self):
        self.status = 200
        self.raw = CSV.encode()
        self.headers = [("Content-Type", "text/csv"), ("Content-Length", str(len(self.raw)))]
        self.closed = False
        self.after_read = None
        self.stream = None
    def getheaders(self): return self.headers
    def read1(self, size):
        if self.stream is None: self.stream = io.BytesIO(self.raw)
        chunk = self.stream.read(size)
        if self.after_read: self.after_read()
        return chunk
    def isclosed(self): return False
    def close(self): self.closed = True


class Connection:
    def __init__(self):
        self.response = Response()
        self.calls, self.timeouts = [], []
        self.sock = SimpleNamespace(settimeout=lambda seconds: self.timeouts.append(seconds))
        self.closed = False
        self.failure = None
    def connect(self):
        self.calls.append("connect")
        if self.failure: raise self.failure
    def request(self, method, path, *, headers): self.calls.append((method, path, headers))
    def getresponse(self): return self.response
    def close(self): self.closed = True


def reader(monkeypatch, **overrides):
    system, _ = setup()
    broker, provider = CredentialBroker(), Provider()
    scope = dict(reference="vault/https", account_ref="synthetic-account", environment="synthetic", objects=["customers"])
    broker.grant(system, provider=provider, **scope, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    connection = Connection()
    constructed = []
    def build(host, port, **kwargs):
        constructed.append((host, port, kwargs))
        return connection
    monkeypatch.setattr(transport.http.client, "HTTPSConnection", build)
    config = dict(endpoint="https://exports.example.invalid:8443/customers.csv", broker=broker, system_id=system,
                  secret_reference=scope["reference"], account_ref=scope["account_ref"], environment="synthetic",
                  object_type="customers", file_format="csv")
    config.update(overrides)
    return transport.HTTPSExportConnector(**config), connection, broker, system, provider, constructed


def test_fixed_get_verified_tls_and_snapshot_cursor(monkeypatch):
    adapter, connection, _, _, _, constructed = reader(monkeypatch)
    assert validated_capabilities(adapter) == {"sync", "schema", "health"}
    page = adapter.sync("customers")
    assert page.complete and page.records[0].external_id == "1"
    host, port, options = constructed[0]
    assert (host, port) == ("exports.example.invalid", 8443)
    assert options["context"].check_hostname and options["context"].verify_mode == ssl.CERT_REQUIRED
    assert 0 < options["timeout"] <= 10
    assert connection.calls[1] == ("GET", "/customers.csv", {"Authorization": "Bearer synthetic-token-ONLY", "Accept": "text/csv", "Accept-Encoding": "identity", "Connection": "close"})
    assert connection.closed and connection.response.closed
    assert all(0 < value <= 10 for value in connection.timeouts)
    connection.response = Response()
    assert adapter.sync("customers", page.cursor).records == ()


@pytest.mark.parametrize("status,code,retryable", [(301,"permission_denied",False), (302,"permission_denied",False),
    (403,"permission_denied",False), (404,"source_changed",False), (429,"rate_limited",True),
    (503,"unavailable",True), (500,"unavailable",True), (204,"source_changed",False)])
def test_http_failures_do_not_read_body_follow_redirect_or_expose_payload(monkeypatch, status, code, retryable):
    adapter, connection, _, _, _, _ = reader(monkeypatch)
    connection.response.status = status
    connection.response.headers += [("Location", "https://unrelated.invalid/private"), ("Retry-After", "37")]
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers")
    assert error.value.code == code and error.value.retryable is retryable
    assert error.value.retry_after_seconds == (37 if status in {429, 503} else None)
    assert connection.response.stream is None and connection.closed
    assert len(connection.calls) == 2
    assert "private" not in str(error.value)


@pytest.mark.parametrize("headers", [[("Content-Type","text/html")], [("Content-Type","text/csv"),("Content-Encoding","gzip")],
    [("Content-Type","text/csv"),("Content-Length","1000001")], [("Content-Type","text/csv"),("Content-Length","-1")],
    [("Content-Type","text/csv"),("Content-Length","5"),("content-length","5")],
    [("Content-Type","text/csv"),("Content-Length","5"),("Transfer-Encoding","chunked")],
    [("Content-Type","text/csv"),("Transfer-Encoding","unknown")]], ids=["html","compressed","large","negative","duplicate","ambiguous","transfer"])
def test_unsupported_or_ambiguous_response_headers_fail_closed(monkeypatch, headers):
    adapter, connection, _, _, _, _ = reader(monkeypatch)
    connection.response.headers = headers
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers")
    assert error.value.code == "source_changed" and connection.response.stream is None


def test_payload_bounds_length_and_inflight_revocation(monkeypatch):
    adapter, connection, broker, system, _, _ = reader(monkeypatch)
    connection.response.headers = [("Content-Type", "text/csv")]
    connection.response.raw = b"x" * 1_000_001
    with pytest.raises(ConnectorFailure): adapter.sync("customers")
    connection.response = Response(); connection.response.headers[-1] = ("Content-Length", "1")
    with pytest.raises(ConnectorFailure): adapter.sync("customers")
    connection.response = Response(); connection.response.after_read = lambda: broker.revoke(system)
    with pytest.raises(CredentialUnavailable): adapter.sync("customers")
    connection.calls.clear()
    with pytest.raises(CredentialUnavailable): adapter.sync("customers")
    assert connection.calls == []


def test_authentication_header_injection_and_tls_failure_are_sanitized(monkeypatch):
    adapter, connection, _, _, provider, _ = reader(monkeypatch)
    provider.token = "secret\r\nX-Injected: bad"
    with pytest.raises(CredentialUnavailable): adapter.sync("customers")
    assert not connection.calls
    provider.token = "synthetic-token"
    connection.failure = ssl.SSLCertVerificationError("PRIVATE TLS ENDPOINT")
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers")
    assert error.value.code == "permission_denied" and "PRIVATE" not in str(error.value)
    connection.failure = None; connection.response.status = 401
    assert adapter.health() == {"status": "authentication_required"}


@pytest.mark.parametrize("endpoint", ["http://example.invalid/file", "https://user:secret@example.invalid/file",
    "https://example.invalid/file?token=secret", "https://example.invalid/file#fragment", "https://example.invalid:0/file",
    "https://example.invalid//file", "https://example.invalid/\nfile"], ids=["http","userinfo","query","fragment","port","path","control"])
def test_endpoint_is_fixed_https_without_url_credentials(monkeypatch, endpoint):
    with pytest.raises(ValueError): reader(monkeypatch, endpoint=endpoint)


def test_unverified_or_later_weakened_tls_is_rejected(monkeypatch):
    context = ssl._create_unverified_context()
    with pytest.raises(ValueError): reader(monkeypatch, ssl_context=context)
    adapter, connection, _, _, _, _ = reader(monkeypatch)
    adapter._context.check_hostname = False
    with pytest.raises(ConnectorFailure): adapter.sync("customers")
    assert connection.calls == []


@pytest.mark.parametrize("content_type,accepted", [("text/csv; charset=UTF-8", True), ('text/csv; charset="utf-8"', True),
    ("text/csv; charset=iso-8859-1", False), ("text/csv; charset=utf-8; charset=latin1", False)], ids=["utf8","quoted","legacy","duplicate"])
def test_declared_text_encoding_must_be_unambiguous_utf8(monkeypatch, content_type, accepted):
    adapter, connection, _, _, _, _ = reader(monkeypatch)
    connection.response.headers[0] = ("Content-Type", content_type)
    if accepted: assert adapter.sync("customers").records
    else:
        with pytest.raises(ConnectorFailure): adapter.sync("customers")


@pytest.mark.parametrize("delay", ["999999999999", "-1", "0", "tomorrow", "86401"], ids=["huge","negative","zero","date","limit"])
def test_invalid_retry_after_is_not_reflected_or_used(monkeypatch, delay):
    adapter, connection, _, _, _, _ = reader(monkeypatch)
    connection.response.status = 429
    connection.response.headers.append(("Retry-After", delay))
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers")
    assert error.value.retry_after_seconds is None and error.value.code == "rate_limited"
