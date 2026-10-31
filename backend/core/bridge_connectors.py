"""Catalog entries express requested coverage, never claims of vendor API access."""
import csv
import io
import json
from core.bridge_contracts import SourceRecord, SyncPage, source_timestamp, validated_capabilities

from core.bridge_catalog import CATALOG, GROUPS

class UnavailableConnector:
    capabilities = frozenset()
    def health(self):
        return {"status": "unavailable", "reason": "Vendor adapter and authorized access required"}
    def _unavailable(self, *args, **kwargs):
        raise ValueError("Capability unavailable: vendor adapter and authorized access required")
    _unavailable.bridge_unavailable = True
    authenticate = discover = schema = history = sync = subscribe = write = reconcile = _unavailable

REGISTRY = {name: UnavailableConnector() for name in CATALOG if name != "CSV"}

def source_columns_profile(source_columns=None):
    columns = {"external_id": "external_id", "modified_at": "modified_at"} if source_columns is None else source_columns
    if not isinstance(columns, dict) or set(columns) != {"external_id", "modified_at"} or any(not isinstance(v, str) or not v.strip() or len(v) > 120 for v in columns.values()) or len(set(columns.values())) != 2:
        raise ValueError("Distinct source ID and modified-time columns required")
    return dict(columns)


def inspect_csv(content, *, delimiter=","):
    """Bounded raw parsing shared by discovery and import; callers own persistence."""
    if delimiter not in (",", "\t"):
        raise ValueError("Only explicit CSV and TSV delimiters are supported")
    if not isinstance(content, str):
        raise ValueError("UTF-8 CSV text required")
    try:
        size = len(content.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("Export must contain valid UTF-8 text") from None
    if size > 1_000_000:
        raise ValueError("Discovery upload exceeds 1 MB")
    if "\x00" in content:
        raise ValueError("NUL characters are not supported in CSV exports")
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True, delimiter=delimiter)
        headers = reader.fieldnames or []
        if not headers or any(not h.strip() or len(h) > 120 or any(ord(c) < 32 for c in h) for h in headers) or len(headers) != len(set(headers)) or len(headers) > 100:
            raise ValueError("Unique bounded headers required; maximum 100 columns")
        rows = []
        for row in reader:
            if len(rows) >= 1000 or None in row or any(v is None for v in row.values()):
                raise ValueError("Invalid row width or more than 1000 rows")
            rows.append(row)
        return headers, rows
    except csv.Error as exc:
        raise ValueError("Malformed CSV export") from exc


def inspect_json(content):
    """Flat JSON export rows, preserving numeric lexemes without float rounding.

    This is a neutral file format, not a vendor response envelope or schema.
    Nested objects, mixed row shapes and booleans need an explicit adapter.
    """
    if not isinstance(content, str):
        raise ValueError("UTF-8 JSON text required")
    try:
        if len(content.encode("utf-8")) > 1_000_000:
            raise ValueError("Discovery upload exceeds 1 MB")
    except UnicodeEncodeError:
        raise ValueError("Export must contain valid UTF-8 text") from None
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Non-finite JSON numbers are unsupported")
    try:
        rows = json.loads(content.lstrip("\ufeff"), object_pairs_hook=pairs,
                          parse_int=str, parse_float=str, parse_constant=constant)
    except (json.JSONDecodeError, RecursionError):
        raise ValueError("Malformed or excessively nested JSON export") from None
    if not isinstance(rows, list) or not rows or len(rows) > 1000 or not isinstance(rows[0], dict):
        raise ValueError("JSON export must be an array of 1 to 1000 flat records")
    headers = list(rows[0])
    if not headers or len(headers) > 100 or any(not h.strip() or len(h) > 120 or any(ord(c) < 32 for c in h) for h in headers):
        raise ValueError("Unique bounded headers required; maximum 100 columns")
    try:
        for header in headers:
            header.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("JSON property names must contain valid Unicode") from None
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(headers):
            raise ValueError("JSON records must have the same property names")
        for key, value in row.items():
            if value is None:
                row[key] = ""
            elif not isinstance(value, str) or len(value) > 100_000 or "\x00" in value:
                raise ValueError("JSON values must be bounded text, numbers or null; nested values and booleans require an adapter")
            try:
                row[key].encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("JSON values must contain valid Unicode") from None
    return headers, rows


def inspect_file(content, file_format="csv"):
    if file_format == "csv":
        return inspect_csv(content)
    if file_format == "json":
        return inspect_json(content)
    if file_format == "tsv":
        return inspect_csv(content, delimiter="\t")
    raise ValueError("Supported export formats are csv, tsv and json")


def _parse_csv(content, source_columns=None):
    return normalize_rows(*inspect_csv(content), source_columns)


def normalize_rows(headers, raw_rows, source_columns=None):
    columns = source_columns_profile(source_columns)
    if not set(columns.values()) <= set(headers):
        raise ValueError("Export must include the configured source ID and modified-time columns")
    rows = []
    for row in raw_rows:
        normalized = {key: row[source] for key, source in columns.items()}
        if not normalized["external_id"].strip() or normalized["external_id"] != normalized["external_id"].strip() or len(normalized["external_id"]) > 500:
            raise ValueError("Non-empty external ID without surrounding whitespace required")
        for key, value in normalized.items():
            if key in row and row[key] != value:
                raise ValueError("Source column conflicts with a reserved identity column")
        source_timestamp(normalized["modified_at"])
        rows.append({**row, **normalized})
    if not rows:
        raise ValueError("Empty export")
    return headers, rows

def parse_csv(content, source_columns=None):
    try:
        return _parse_csv(content, source_columns)
    except csv.Error as exc:
        raise ValueError("Malformed CSV export") from exc


def parse_export(vendor, content, source_columns=None, file_format="csv"):
    if file_format == "tsv":
        return normalize_rows(*inspect_csv(content, delimiter="\t"), source_columns)
    if file_format == "json":
        return normalize_rows(*inspect_json(content), source_columns)
    if file_format != "csv":
        raise ValueError("Supported export formats are csv, tsv and json")
    if vendor == "Frazer":
        from core.bridge_adapters.frazer import FrazerExportAdapter
        return FrazerExportAdapter(source_columns).parse(content)
    return parse_csv(content, source_columns)


class CsvConnector(UnavailableConnector):
    capabilities = frozenset(CATALOG["CSV"]["capabilities"])
    def __init__(self, content=None, *, object_type=None):
        if object_type is not None and (not isinstance(object_type, str) or not object_type.strip() or len(object_type) > 120):
            raise ValueError("Bounded source object required")
        self.content = content
        self.object_type = object_type
    def discover(self):
        if self.content is None or self.object_type is None:
            return []
        parse_csv(self.content)
        return [self.object_type]
    def upload_contract(self):
        return {"transport": "upload", "max_rows": 1000, "required_columns": ["external_id", "modified_at"]}
    def _check_object(self, object_type):
        if self.object_type is not None and object_type != self.object_type:
            raise ValueError("Source object does not match this export binding")

    def schema(self, object_type):
        self._check_object(object_type)
        if self.content is None:
            raise ValueError("Bind an authorized export before discovery")
        return parse_csv(self.content)[0]
    def sync(self, object_type, cursor=None):
        self._check_object(object_type)
        if cursor is not None:
            raise ValueError("CSV discovery is one bounded page; cursors are unsupported")
        if self.content is None:
            raise ValueError("Bind an authorized export before sync")
        rows = parse_csv(self.content)[1]
        return SyncPage(tuple(SourceRecord(object_type, row["external_id"], row["modified_at"], row) for row in rows), None, True)
    def health(self):
        if self.content is None:
            return {"status": "unavailable", "transport": "manual_upload"}
        try:
            parse_csv(self.content)
        except (ValueError, TypeError):
            return {"status": "source_changed", "transport": "manual_upload"}
        return {"status": "ready", "transport": "manual_upload"}

REGISTRY["CSV"] = CsvConnector()

def register_connector(name, adapter):
    """Trusted startup extension only; no HTTP registration or automatic writes."""
    if name not in CATALOG or name == "CSV":
        raise ValueError("Use a known vendor catalog entry")
    capabilities = validated_capabilities(adapter)
    REGISTRY[name] = adapter
    # Registration alone never asserts authenticated/healthy or grants write access.
    CATALOG[name] = {**CATALOG[name], "status": "adapter_registered", "capabilities": sorted(capabilities)}

# File-profile scaffolding is independent from live API registration/access.
CATALOG["Frazer"]["export_profile"] = "dealer_supplied_unverified"
CATALOG["Frazer"]["access_reference"] = "https://www.frazer.com/frazer-partner-program"
CATALOG["Wayne Reaves"]["access_reference"] = "https://www.waynereaves.com/partners"
CATALOG["DealerSocket IDMS"]["access_reference"] = "https://dealersocket.com/solutions/dms-independent/"
