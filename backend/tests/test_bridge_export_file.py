import hashlib
import json

import pytest
from core.bridge_adapters.export_file import ExportFileConnector
from core.bridge_contracts import validated_capabilities
from core.bridge_sync import ConnectorFailure

CSV = "external_id,modified_at,name,email\n1,2026-01-01T00:00:00Z,Ada,ada@example.com\n"


def adapter(tmp_path, content=CSV, **kwargs):
    path = tmp_path / "export.csv"
    path.write_bytes(content.encode("utf-8"))
    return path, ExportFileConnector(path, object_type="customers", **kwargs)


def test_changed_bytes_and_unchanged_checkpoint(tmp_path):
    path, reader = adapter(tmp_path)
    first = reader.sync("customers")
    assert first.complete and len(first.records) == 1
    assert first.cursor == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert reader.sync("customers", first.cursor).records == ()
    path.write_text(CSV.replace("Ada", "Grace"), encoding="utf-8")
    second = reader.sync("customers", first.cursor)
    assert second.cursor != first.cursor and second.records[0].values["name"] == "Grace"
    assert reader.schema("customers") == ["external_id", "modified_at", "name", "email"]
    assert reader.health()["status"] == "ready"


@pytest.mark.parametrize("file_format", ["csv", "tsv", "json"])
def test_explicit_formats_and_custom_source_profile(tmp_path, file_format):
    content = "ID,Changed,Name\n1,2026-01-01T00:00:00Z,Ada\n"
    if file_format == "tsv":
        content = content.replace(",", "\t")
    if file_format == "json":
        content = json.dumps([{"ID": "1", "Changed": "2026-01-01T00:00:00Z", "Name": "Ada"}])
    _, reader = adapter(tmp_path, content, file_format=file_format,
                        source_columns={"external_id": "ID", "modified_at": "Changed"})
    record = reader.sync("customers").records[0]
    assert record.external_id == "1" and record.values["Name"] == "Ada"


@pytest.mark.parametrize("content", ["", "bad", CSV.replace("2026-01-01T00:00:00Z", "yesterday"), "x" * 1_000_001], ids=["empty", "headers", "time", "oversize"])
def test_invalid_snapshot_is_terminal_without_source_details(tmp_path, content):
    path, reader = adapter(tmp_path, content)
    with pytest.raises(ConnectorFailure) as error:
        reader.sync("customers")
    assert error.value.code == "source_changed" and not error.value.retryable
    assert str(path) not in str(error.value)
    assert reader.health() == {"status": "source_changed"}


def test_missing_file_retries_and_bad_unicode_blocks(tmp_path):
    path, reader = adapter(tmp_path)
    path.unlink()
    with pytest.raises(ConnectorFailure) as error:
        reader.sync("customers")
    assert error.value.retryable
    path.write_bytes(b"\xff")
    with pytest.raises(ConnectorFailure) as error:
        reader.sync("customers")
    assert error.value.code == "source_changed"


def test_object_cursor_and_capability_boundaries(tmp_path):
    _, reader = adapter(tmp_path)
    assert validated_capabilities(reader) == {"sync", "schema", "health"}
    for cursor in ["opaque", 42, "sha256:" + "z" * 64]:
        with pytest.raises(ConnectorFailure):
            reader.sync("customers", cursor)
    with pytest.raises(ConnectorFailure):
        reader.sync("payments")
    for capability in ["history", "write", "subscribe", "authenticate"]:
        with pytest.raises(ValueError):
            getattr(reader, capability)()


def test_relative_path_and_directory_rejected(tmp_path):
    with pytest.raises(ValueError):
        ExportFileConnector("relative.csv", object_type="customers")
    reader = ExportFileConnector(tmp_path, object_type="customers")
    with pytest.raises(ConnectorFailure) as error:
        reader.sync("customers")
    assert error.value.code == "permission_denied"


def test_changed_during_read_is_retryable(tmp_path, monkeypatch):
    _, reader = adapter(tmp_path)
    import core.bridge_adapters.export_file as module
    original = module.os.fstat
    calls = []
    def changed(fd):
        result = original(fd)
        calls.append(result)
        if len(calls) == 2:
            from types import SimpleNamespace
            return SimpleNamespace(st_dev=result.st_dev, st_ino=result.st_ino,
                                   st_size=result.st_size + 1, st_mtime_ns=result.st_mtime_ns,
                                   st_ctime_ns=result.st_ctime_ns)
        return result
    monkeypatch.setattr(module.os, "fstat", changed)
    with pytest.raises(ConnectorFailure) as error:
        reader.sync("customers")
    assert error.value.retryable
