"""Trusted local snapshot export reader; never a vendor API or history feed.

The runtime operator owns path authorization and filesystem permissions. No path
is accepted from HTTP. Bind one instance to one object and a versioned system
binding. The cursor fingerprints original bytes; import evidence fingerprints
collector-normalized CSV. Neither fingerprint establishes vendor authenticity.
"""
import os
from pathlib import Path
import stat

from core.bridge_adapters.export_snapshot import ExportSnapshotConnector
from core.bridge_sync import ConnectorFailure


class ExportFileConnector(ExportSnapshotConnector):
    transport = "local_export_snapshot"
    max_snapshot_bytes = 1_000_000

    def __init__(self, path, *, object_type, vendor="CSV", file_format="csv", source_columns=None):
        path = Path(path)
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError("An absolute canonical export path is required")
        super().__init__(object_type=object_type, vendor=vendor, file_format=file_format, source_columns=source_columns)
        self._path = path

    @staticmethod
    def _signature(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def _read(self):
        try:
            # Trusted operators must restrict parent-directory changes. These
            # checks detect substitution; they are not a filesystem sandbox.
            if self._path.resolve() != self._path:
                raise ConnectorFailure(code="permission_denied")
            before = self._path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ConnectorFailure(code="permission_denied")
            if before.st_size > self.max_snapshot_bytes:
                raise ConnectorFailure(code="source_changed")
            with self._path.open("rb") as source:
                opened = os.fstat(source.fileno())
                if self._signature(before) != self._signature(opened):
                    raise ConnectorFailure()
                raw = source.read(self.max_snapshot_bytes + 1)
                after = os.fstat(source.fileno())
            if (self._signature(opened) != self._signature(after) or
                    self._signature(after) != self._signature(self._path.lstat())):
                raise ConnectorFailure()
            if len(raw) > self.max_snapshot_bytes:
                raise ConnectorFailure(code="source_changed")
            return raw
        except ConnectorFailure:
            raise
        except PermissionError:
            raise ConnectorFailure(code="permission_denied") from None
        except OSError:
            raise ConnectorFailure() from None

