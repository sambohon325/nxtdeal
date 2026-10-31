"""Bounded paginated local CSV/TSV snapshots; each page requires normal review."""
import csv
import hashlib
import io
import re

from core.bridge_adapters.export_file import ExportFileConnector
from core.bridge_connectors import inspect_csv, parse_export
from core.bridge_contracts import SourceRecord, SyncPage
from core.bridge_sync import ConnectorFailure


class PagedExportFileConnector(ExportFileConnector):
    transport = "local_paged_export_snapshot"
    max_snapshot_bytes = 25_000_000
    max_snapshot_rows = 100_000

    def __init__(self, path, *, object_type, vendor="CSV", file_format="csv", source_columns=None, page_size=500, group_by_source_column=None):
        if file_format not in {"csv", "tsv"} or type(page_size) is not int or not 1 <= page_size <= 1000:
            raise ValueError("CSV/TSV and a page size between 1 and 1000 required")
        super().__init__(path, object_type=object_type, vendor=vendor, file_format=file_format, source_columns=source_columns)
        if group_by_source_column is not None and (not isinstance(group_by_source_column, str) or
                not group_by_source_column.strip() or len(group_by_source_column) > 120 or
                any(ord(char) < 32 for char in group_by_source_column)):
            raise ValueError("Bounded source grouping column required")
        self._page_size = page_size
        self._group_by = group_by_source_column

    def _select_rows(self, reader, headers, offset):
        if self._group_by is not None and self._group_by not in headers:
            raise ValueError("Missing source grouping column")
        selected, total, group, group_start = [], 0, [], 0
        seen, current, page_full = set(), None, False
        def finish_group():
            nonlocal page_full
            if not group: return
            if group_start < offset < group_start + len(group):
                raise ValueError("Cursor falls inside a source group")
            if group_start >= offset and not page_full:
                if len(selected) + len(group) <= self._page_size:
                    selected.extend(group)
                else:
                    page_full = True
        for index, row in enumerate(reader):
            total = index + 1
            if total > self.max_snapshot_rows or None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid bounded export")
            if self._group_by is None:
                if offset <= index < offset + self._page_size: selected.append(row)
                continue
            key = row[self._group_by]
            if not key.strip() or key != key.strip() or len(key) > 500 or any(ord(char) < 32 for char in key):
                raise ValueError("Bounded nonempty group identity required")
            if key != current:
                finish_group()
                if key in seen: raise ValueError("Source groups must be contiguous")
                seen.add(key)
                current, group, group_start = key, [], index
            group.append(row)
            if len(group) > self._page_size: raise ValueError("Source group exceeds page size")
        finish_group()
        return selected, total

    def _page(self, cursor):
        prior_hash, offset, prior_complete = None, 0, False
        reviewed_restart = False
        if cursor is not None:
            if not isinstance(cursor, str): raise ConnectorFailure(code="source_changed")
            restart = re.fullmatch(r"csvrestart:v1:([0-9a-f]{64})", cursor)
            if restart:
                prior_hash, reviewed_restart = restart[1], True
            else:
                match = re.fullmatch(r"csvpage:v1:([0-9a-f]{64}):([0-9]{1,6}):(more|done)", cursor)
                if not match: raise ConnectorFailure(code="source_changed")
                prior_hash, offset, prior_complete = match[1], int(match[2]), match[3] == "done"
                if not 1 <= offset <= self.max_snapshot_rows: raise ConnectorFailure(code="source_changed")
        raw = self._read()
        fingerprint = hashlib.sha256(raw).hexdigest()
        if prior_hash is not None and prior_hash != fingerprint:
            if reviewed_restart or not prior_complete:
                raise ConnectorFailure(code="source_changed")
            offset = 0
        delimiter = "\t" if self._format == "tsv" else ","
        try:
            content = raw.decode("utf-8").lstrip("\ufeff")
            if "\x00" in content: raise ValueError("Invalid export")
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter, strict=True)
            headers = reader.fieldnames or []
            header_buffer = io.StringIO(); csv.writer(header_buffer, delimiter=delimiter).writerow(headers)
            inspect_csv(header_buffer.getvalue(), delimiter=delimiter)
            selected, total = self._select_rows(reader, headers, offset)
            if not total or offset > total or (prior_hash == fingerprint and prior_complete and offset != total):
                raise ValueError("Invalid source position")
            if prior_hash == fingerprint and not prior_complete and offset == total:
                raise ValueError("Incomplete cursor has no remaining rows")
            if not selected:
                if not set(self._columns.values()) <= set(headers): raise ValueError("Missing source columns")
                return headers, SyncPage((), cursor, True)
            buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=headers, delimiter=delimiter)
            writer.writeheader(); writer.writerows(selected)
            _, rows = parse_export(self._vendor, buffer.getvalue(), self._columns, self._format)
        except (ValueError, UnicodeError, csv.Error):
            raise ConnectorFailure(code="source_changed") from None
        next_offset = offset + len(selected)
        complete = next_offset == total
        token = f"csvpage:v1:{fingerprint}:{next_offset}:{'done' if complete else 'more'}"
        return headers, SyncPage(tuple(SourceRecord(self._object_type, row["external_id"], row["modified_at"], row) for row in rows), token, complete)

    def reviewed_restart_cursor(self, object_type):
        """Validate a first page and pin a human-reviewed restart to these bytes."""
        self._check_object(object_type)
        page = self._page(None)[1]
        return "csvrestart:v1:" + page.cursor.split(":")[2]

    def sync(self, object_type, cursor=None):
        self._check_object(object_type)
        return self._page(cursor)[1]

    def schema(self, object_type):
        self._check_object(object_type)
        return self._page(None)[0]

    def health(self):
        try: self._page(None)
        except ConnectorFailure as error: return {"status": error.code}
        return {"status": "ready"}
