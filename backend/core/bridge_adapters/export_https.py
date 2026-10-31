"""Fixed-endpoint HTTPS snapshot reader for trusted operator configuration.

No endpoint or credentials come from an HTTP request. GET only, verified TLS,
no redirects/proxies/cookies, no source writes and no inferred historical feed.
"""
import http.client
import ipaddress
import re
import ssl
import time
from urllib.parse import urlsplit

from core.bridge_adapters.export_snapshot import ExportSnapshotConnector
from core.bridge_credentials import CredentialUnavailable
from core.bridge_sync import ConnectorFailure


class HTTPSExportConnector(ExportSnapshotConnector):
    transport = "https_export_snapshot"
    MIME_TYPES = {"csv": "text/csv", "tsv": "text/tab-separated-values", "json": "application/json"}

    def __init__(self, *, endpoint, broker, system_id, secret_reference, account_ref,
                 environment, object_type, vendor="CSV", file_format="json", source_columns=None,
                 timeout_seconds=10, ssl_context=None):
        super().__init__(object_type=object_type, vendor=vendor, file_format=file_format, source_columns=source_columns)
        try:
            if (not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048 or
                    not endpoint.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in endpoint)):
                raise ValueError()
            url = urlsplit(endpoint)
            host, port, path = url.hostname, url.port or 443, url.path or "/"
            if (url.scheme != "https" or not host or url.username is not None or url.password is not None or
                    url.query or url.fragment or "?" in endpoint or "#" in endpoint or
                    not 1 <= port <= 65535 or url.port == 0 or not path.startswith("/") or path.startswith("//") or "\\" in endpoint):
                raise ValueError()
            if ":" in host: ipaddress.IPv6Address(host)
            elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host): raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Explicit bounded HTTPS export endpoint without credentials, query or fragment required") from None
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 15:
            raise ValueError("HTTPS operation timeout must be 1 to 15 seconds")
        if environment not in {"synthetic", "sandbox", "production"}:
            raise ValueError("Explicit source environment required")
        context = ssl.create_default_context() if ssl_context is None else ssl_context
        self._check_tls(context)
        context.set_alpn_protocols(["http/1.1"])
        self._host, self._port, self._path = host, port, path
        self._context, self._timeout, self._broker, self._system_id = context, timeout_seconds, broker, system_id
        self._scope = dict(reference=secret_reference, account_ref=account_ref, environment=environment, objects=[object_type])

    @staticmethod
    def _check_tls(context):
        if (not isinstance(context, ssl.SSLContext) or not context.check_hostname or
                context.verify_mode != ssl.CERT_REQUIRED or context.minimum_version < ssl.TLSVersion.TLSv1_2):
            raise ValueError("Verified TLS 1.2 or newer with hostname checking is required")

    @staticmethod
    def _headers(response):
        headers = {}
        raw = response.getheaders()
        if len(raw) > 100: raise ConnectorFailure(code="source_changed")
        protected = {"content-length", "content-type", "content-encoding", "transfer-encoding", "retry-after"}
        for key, value in raw:
            key = key.lower()
            if key in protected:
                if key in headers or not isinstance(value, str) or len(value) > 8192:
                    raise ConnectorFailure(code="source_changed")
                headers[key] = value.strip()
        return headers

    def _read(self):
        connection = response = None
        deadline = time.monotonic() + 60
        def remaining():
            value = min(self._timeout, deadline - time.monotonic())
            if value <= 0: raise ConnectorFailure()
            return value
        try:
            self._check_tls(self._context)
            material = self._broker.resolve(self._system_id, **self._scope)
            token = material.require("access_token")
            if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token): raise CredentialUnavailable()
            material.assert_current()
            connection = http.client.HTTPSConnection(self._host, self._port, timeout=remaining(), context=self._context)
            connection.connect()
            socket = connection.sock
            socket.settimeout(remaining())
            material.assert_current()
            connection.request("GET", self._path, headers={"Authorization": "Bearer " + token,
                "Accept": self.MIME_TYPES[self._format], "Accept-Encoding": "identity", "Connection": "close"})
            socket.settimeout(remaining())
            response = connection.getresponse()
            headers = self._headers(response)
            status = response.status
            if status == 401: raise CredentialUnavailable()
            if status == 403 or 300 <= status < 400: raise ConnectorFailure(code="permission_denied")
            if status in {429, 503}:
                delay = headers.get("retry-after", "")
                seconds = int(delay) if re.fullmatch(r"[0-9]{1,5}", delay) and 1 <= int(delay) <= 86400 else None
                raise ConnectorFailure(code="rate_limited" if status == 429 else "unavailable", retry_after_seconds=seconds)
            if status == 408 or 500 <= status < 600: raise ConnectorFailure()
            if status != 200: raise ConnectorFailure(code="source_changed")
            content_type = headers.get("content-type", "").lower()
            if not re.fullmatch(re.escape(self.MIME_TYPES[self._format]) + r'\s*(?:;\s*charset\s*=\s*(?:utf-8|"utf-8"))?\s*', content_type):
                raise ConnectorFailure(code="source_changed")
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise ConnectorFailure(code="source_changed")
            length = headers.get("content-length")
            transfer = headers.get("transfer-encoding")
            if transfer is not None and (transfer.lower() != "chunked" or length is not None):
                raise ConnectorFailure(code="source_changed")
            if length is not None and (not re.fullmatch(r"[0-9]{1,7}", length) or not 1 <= int(length) <= 1_000_000):
                raise ConnectorFailure(code="source_changed")
            chunks, size = [], 0
            while True:
                socket.settimeout(remaining())
                chunk = response.read1(min(32768, 1_000_001 - size))
                if not isinstance(chunk, bytes): raise ConnectorFailure(code="source_changed")
                if not chunk: break
                size += len(chunk)
                if size > 1_000_000: raise ConnectorFailure(code="source_changed")
                chunks.append(chunk)
                if response.isclosed(): break
            if not size or length is not None and size != int(length): raise ConnectorFailure(code="source_changed")
            remaining()
            material.assert_current()
            return b"".join(chunks)
        except (ConnectorFailure, CredentialUnavailable):
            raise
        except (ssl.SSLError, ssl.CertificateError, PermissionError):
            raise ConnectorFailure(code="permission_denied") from None
        except (OSError, http.client.HTTPException):
            raise ConnectorFailure() from None
        except Exception:
            raise ConnectorFailure(code="source_changed") from None
        finally:
            for resource in (response, connection):
                if resource is not None:
                    try: resource.close()
                    except Exception: pass

    def health(self):
        try: self._parsed()
        except CredentialUnavailable: return {"status": "authentication_required"}
        except ConnectorFailure as error: return {"status": error.code}
        return {"status": "ready"}
