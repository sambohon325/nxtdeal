"""Shared bounded snapshot parsing and content cursors for read-only transports."""
import hashlib
import re
from core.bridge_connectors import UnavailableConnector, parse_export, source_columns_profile
from core.bridge_contracts import SourceRecord, SyncPage
from core.bridge_sync import ConnectorFailure


class ExportSnapshotConnector(UnavailableConnector):
    capabilities = frozenset({"sync", "schema", "health"})
    transport = "export_snapshot"

    def __init__(self, *, object_type, vendor="CSV", file_format="csv", source_columns=None):
        if file_format not in {"csv", "tsv", "json"}:
            raise ValueError("Unsupported export format")
        if not isinstance(object_type, str) or not object_type.strip() or len(object_type) > 120:
            raise ValueError("Bounded source object required")
        self._object_type = object_type
        self._vendor = vendor
        self._format = file_format
        self._columns = source_columns_profile(source_columns)

    def _read(self):
        raise NotImplementedError("A bounded read-only transport is required")

    def _parsed(self):
        raw = self._read()
        try:
            headers, rows = parse_export(self._vendor, raw.decode("utf-8"), self._columns, self._format)
        except (ValueError, UnicodeError):
            raise ConnectorFailure(code="source_changed") from None
        return headers, rows, "sha256:" + hashlib.sha256(raw).hexdigest()

    def _check_object(self, object_type):
        if object_type != self._object_type:
            raise ConnectorFailure(code="permission_denied")

    def schema(self, object_type):
        self._check_object(object_type)
        return self._parsed()[0]

    def sync(self, object_type, cursor=None):
        self._check_object(object_type)
        if cursor is not None and (not isinstance(cursor, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", cursor)):
            raise ConnectorFailure(code="source_changed")
        _, rows, fingerprint = self._parsed()
        records = () if cursor == fingerprint else tuple(
            SourceRecord(object_type, row["external_id"], row["modified_at"], row) for row in rows)
        return SyncPage(records, fingerprint, True)

    def health(self):
        try:
            self._parsed()
        except ConnectorFailure as error:
            return {"status": error.code}
        return {"status": "ready", "transport": self.transport}
