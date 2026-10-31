"""Optional fixed-path SFTP snapshot reader with explicit host trust and grants.

Trusted operator startup only. No host/path/credentials are accepted over HTTP.
No directory browsing, source writes, deletion inference or historical feed.
"""
from pathlib import Path, PurePosixPath
import ipaddress
import io
import re
import stat
import time

from core.bridge_adapters.export_snapshot import ExportSnapshotConnector
from core.bridge_credentials import CredentialUnavailable
from core.bridge_sync import ConnectorFailure


class SFTPExportConnector(ExportSnapshotConnector):
    transport = "sftp_export_snapshot"

    def __init__(self, *, host, port=22, remote_path, known_hosts, broker, system_id,
                 secret_reference, account_ref, environment, object_type, vendor="CSV",
                 file_format="csv", source_columns=None, timeout_seconds=10, authentication="password", encrypted_key=False):
        super().__init__(object_type=object_type, vendor=vendor, file_format=file_format, source_columns=source_columns)
        if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}", host):
            raise ValueError("Explicit bounded SFTP hostname required")
        if ":" in host:
            try: ipaddress.IPv6Address(host)
            except ValueError: raise ValueError("Invalid SFTP hostname") from None
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Explicit SFTP port required")
        if (not isinstance(remote_path, str) or not remote_path.startswith("/") or len(remote_path) > 1024 or
                "\\" in remote_path or any(ord(char) < 32 for char in remote_path) or
                str(PurePosixPath(remote_path)) != remote_path or ".." in PurePosixPath(remote_path).parts or remote_path.startswith("//")):
            raise ValueError("Absolute normalized remote export path required")
        path = Path(known_hosts)
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError("Absolute canonical known-hosts file required")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 15:
            raise ValueError("SFTP operation timeout must be 1 to 15 seconds")
        if environment not in {"synthetic", "sandbox", "production"}:
            raise ValueError("Explicit source environment required")
        if authentication not in ("password", "rsa", "ecdsa", "ed25519") or type(encrypted_key) is not bool or authentication == "password" and encrypted_key:
            raise ValueError("Explicit supported SFTP authentication method required")
        self._authentication, self._encrypted_key = authentication, encrypted_key
        self._host, self._port, self._remote_path, self._known_hosts = host, port, remote_path, path
        self._broker, self._system_id, self._timeout = broker, system_id, timeout_seconds
        self._scope = dict(reference=secret_reference, account_ref=account_ref, environment=environment, objects=[object_type])

    def _authentication_args(self, material, paramiko):
        if self._authentication == "password":
            return {"password": material.require("password")}
        key_class = {"rsa": paramiko.RSAKey, "ecdsa": paramiko.ECDSAKey, "ed25519": paramiko.Ed25519Key}[self._authentication]
        try:
            with io.StringIO(material.require("private_key")) as stream:
                key = key_class.from_private_key(stream, password=material.require("passphrase") if self._encrypted_key else None)
            if self._authentication == "rsa" and key.get_bits() < 2048:
                raise CredentialUnavailable()
        except Exception:
            raise CredentialUnavailable() from None
        return {"pkey": key}

    @staticmethod
    def _signature(info):
        fields = [getattr(info, field, None) for field in ("st_mode", "st_size", "st_mtime")]
        if any(type(value) is not int or value < 0 for value in fields):
            raise ConnectorFailure(code="source_changed")
        if not stat.S_ISREG(fields[0]):
            raise ConnectorFailure(code="permission_denied")
        if fields[1] > 1_000_000:
            raise ConnectorFailure(code="source_changed")
        return tuple(fields)

    def _read(self):
        try:
            import paramiko
        except ImportError:
            raise ConnectorFailure(code="source_changed") from None
        client = sftp = source = None
        deadline = time.monotonic() + 60
        def remaining():
            value = min(self._timeout, deadline - time.monotonic())
            if value <= 0: raise ConnectorFailure()
            return value
        try:
            info = self._known_hosts.lstat()
            if (self._known_hosts.resolve() != self._known_hosts or not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000):
                raise ConnectorFailure(code="permission_denied")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.load_host_keys(str(self._known_hosts))
            host_key_name = self._host if self._port == 22 else f"[{self._host}]:{self._port}"
            if not client.get_host_keys().lookup(host_key_name):
                raise ConnectorFailure(code="permission_denied")
            material = self._broker.resolve(self._system_id, **self._scope)
            authentication = self._authentication_args(material, paramiko)
            material.assert_current()
            client.connect(hostname=self._host, port=self._port, username=material.require("username"),
                           **authentication, allow_agent=False, look_for_keys=False,
                           timeout=remaining(), banner_timeout=remaining(), auth_timeout=remaining(), channel_timeout=remaining())
            sftp = client.open_sftp()
            channel = sftp.get_channel()
            channel.settimeout(remaining())
            before = self._signature(sftp.lstat(self._remote_path))
            channel.settimeout(remaining())
            source = sftp.open(self._remote_path, "rb")
            channel.settimeout(remaining())
            if self._signature(source.stat()) != before: raise ConnectorFailure()
            chunks, size = [], 0
            while True:
                channel.settimeout(remaining())
                chunk = source.read(min(32768, 1_000_001 - size))
                if not isinstance(chunk, bytes): raise ConnectorFailure(code="source_changed")
                if not chunk: break
                size += len(chunk)
                if size > 1_000_000: raise ConnectorFailure(code="source_changed")
                chunks.append(chunk)
            channel.settimeout(remaining())
            after = self._signature(source.stat())
            channel.settimeout(remaining())
            if before != after or after != self._signature(sftp.lstat(self._remote_path)) or size != after[1]:
                raise ConnectorFailure()
            remaining()
            material.assert_current()
            return b"".join(chunks)
        except (ConnectorFailure, CredentialUnavailable):
            raise
        except paramiko.AuthenticationException:
            raise CredentialUnavailable() from None
        except (paramiko.BadHostKeyException, paramiko.SSHException, PermissionError):
            raise ConnectorFailure(code="permission_denied") from None
        except (OSError, EOFError):
            raise ConnectorFailure() from None
        except Exception:
            raise ConnectorFailure(code="source_changed") from None
        finally:
            for resource in (source, sftp, client):
                if resource is not None:
                    try: resource.close()
                    except Exception: pass

    def health(self):
        try:
            self._parsed()
        except CredentialUnavailable:
            return {"status": "authentication_required"}
        except ConnectorFailure as error:
            return {"status": error.code}
        return {"status": "ready"}
