"""Public HTTPS probes with a DNS-pinned connection and no redirects/proxies."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit


class UnsafeDestination(ValueError):
    pass


def public_https_target(url):
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise UnsafeDestination("An absolute public HTTPS URL is required")
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeDestination("Invalid HTTPS URL") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port != 443):
        raise UnsafeDestination("Use public HTTPS on port 443 without credentials or fragments")
    host = parsed.hostname.encode("idna").decode("ascii")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise UnsafeDestination("Destination has no public address")
    for _, _, _, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if (not ip.is_global or ip.is_multicast or getattr(ip, "ipv4_mapped", None) is not None
                or getattr(ip, "sixtofour", None) is not None or getattr(ip, "teredo", None) is not None):
            raise UnsafeDestination("Private, reserved and mapped addresses are not allowed")
    return host, addresses[0][4][0], parsed.path or "/", parsed.query


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the checked literal IP, retaining the original TLS hostname.
        # No second DNS lookup can change the destination after validation.
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def probe_public_https(url, timeout=5):
    host, address, path, query = public_https_target(url)
    connection = _PinnedHTTPSConnection(host, address, timeout)
    try:
        connection.request("GET", path + ("?" + query if query else ""),
                           headers={"User-Agent": "NXTdeal-Connection-Check/1"})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise UnsafeDestination("Redirects are not followed; configure the final HTTPS endpoint")
        if response.status >= 400:
            raise ValueError("Endpoint returned HTTP " + str(response.status))
        return response.status
    finally:
        connection.close()


def public_https_json(url, *, timeout=5, body=None):
    """Bounded JSON transport for OIDC; never forwards credentials to redirects."""
    import json
    host, address, path, query = public_https_target(url)
    connection = _PinnedHTTPSConnection(host, address, timeout)
    try:
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request("POST" if body is not None else "GET",
                           path + ("?" + query if query else ""), body=body, headers=headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise UnsafeDestination("Identity endpoint returned an unsuccessful HTTP status")
        limit = 1024 * 1024
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Identity response exceeds the size limit")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Identity response must be an object")
        return result
    finally:
        connection.close()
