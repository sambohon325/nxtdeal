import socket
import pytest
from core import outbound_http as outbound


@pytest.mark.parametrize("url", ["http://example.com", "file:///etc/passwd", "https://user:pass@example.com", "https://example.com:8443", "https://example.com/#fragment", "https://example.com/\r\nx: y"])
def test_invalid_urls_never_resolve(monkeypatch, url):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("Unexpected DNS lookup"))
    with pytest.raises(outbound.UnsafeDestination):
        outbound.public_https_target(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "100.64.0.1", "0.0.0.0", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "224.0.0.1", "2002:7f00:1::"])
def test_internal_destinations_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))])
    with pytest.raises(outbound.UnsafeDestination):
        outbound.public_https_target("https://example.com")


def test_mixed_public_and_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (ip, 443)) for ip in ["93.184.216.34", "127.0.0.1"]])
    with pytest.raises(outbound.UnsafeDestination):
        outbound.public_https_target("https://example.com")


def test_connection_pins_ip_and_preserves_tls_hostname(monkeypatch):
    seen = []
    class TLS:
        def wrap_socket(self, raw, server_hostname):
            seen.append(server_hostname)
            return raw
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: seen.append(address) or object())
    conn = outbound._PinnedHTTPSConnection("example.com", "93.184.216.34", 5)
    conn._context = TLS()
    conn.connect()
    assert seen == [("93.184.216.34", 443), "example.com"]


def test_redirect_is_not_followed(monkeypatch):
    calls = []
    class Connection:
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): calls.append(args)
        def getresponse(self): return type("Response", (), {"status": 302})()
        def close(self): calls.append("closed")
    monkeypatch.setattr(outbound, "public_https_target", lambda url: ("example.com", "93.184.216.34", "/", ""))
    monkeypatch.setattr(outbound, "_PinnedHTTPSConnection", Connection)
    with pytest.raises(outbound.UnsafeDestination):
        outbound.probe_public_https("https://example.com")
    assert calls == [("GET", "/"), "closed"]


@pytest.mark.parametrize("status,body", [(302, b"{}"), (200, b"x" * (1024 * 1024 + 1)), (200, b"[]")], ids=["redirect", "oversize", "nonobject"])
def test_identity_transport_rejects_redirects_oversize_and_nonobjects(monkeypatch, status, body):
    closed = []
    class Connection:
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self):
            return type("Response", (), {"status": status, "read": lambda self, limit: body[:limit]})()
        def close(self): closed.append(True)
    monkeypatch.setattr(outbound, "public_https_target", lambda url: ("example.com", "93.184.216.34", "/", ""))
    monkeypatch.setattr(outbound, "_PinnedHTTPSConnection", Connection)
    with pytest.raises(ValueError):
        outbound.public_https_json("https://example.com", body=b"client_secret=test")
    assert closed == [True]
