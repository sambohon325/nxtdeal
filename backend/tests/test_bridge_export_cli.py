import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend/tests/fixtures/bridge_conformance"


def run(tmp_path, content=None, file_format="csv", definition=None, expectations=None):
    export = FIXTURES / "customer-export.csv"
    if content is not None:
        export = tmp_path / "private-export.txt"
        export.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    mapping = FIXTURES / "mapping.json"
    if definition is not None:
        mapping = tmp_path / "mapping.json"
        mapping.write_text(json.dumps(definition), encoding="utf-8")
    protected = tmp_path / "existing-storage"
    protected.mkdir(exist_ok=True)
    marker = protected / "graph.json"
    marker.write_text('{"private":"must remain untouched"}', encoding="utf-8")
    args = [sys.executable, str(ROOT / "scripts/check_bridge_export.py"), "--mapping", str(mapping),
            "--export", str(export), "--format", file_format]
    if expectations is not None:
        expected = tmp_path / "expectations.json"
        expected.write_text(json.dumps(expectations), encoding="utf-8")
        args += ["--expectations", str(expected)]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=30,
        env={**os.environ,"DEALEROS_STORAGE_DIR":str(protected),"DEALEROS_AUTH_SECRET":"synthetic-existing-secret"})
    assert marker.read_text(encoding="utf-8") == '{"private":"must remain untouched"}'
    assert sorted(path.name for path in protected.iterdir()) == ["graph.json"]
    assert "synthetic-existing-secret" not in result.stdout + result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr
    return result


def test_documented_export_checks_without_reading_existing_storage(tmp_path):
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["rows"] == 1 and report["outcomes"] == {"ready":1}
    assert not report["production_access"] and not report["stored"]
    assert "synthetic-export-1" not in result.stdout and "@example.invalid" not in result.stdout
    assert len(report["export_sha256"]) == 64


@pytest.mark.parametrize("file_format", ["tsv","json"])
def test_explicit_formats_use_same_mapping_pipeline(tmp_path, file_format):
    row = {"external_id":"private-id","modified_at":"2026-10-04T12:00:00Z","name":"Private Name","email":"private@example.invalid"}
    content = json.dumps([row]) if file_format == "json" else "\t".join(row)+"\n"+"\t".join(row.values())+"\n"
    result = run(tmp_path, content, file_format)
    assert result.returncode == 0
    assert json.loads(result.stdout)["file_format"] == file_format
    assert "Private Name" not in result.stdout and "private-id" not in result.stdout


def test_review_and_reconciliation_failures_return_nonzero_without_values(tmp_path):
    mismatch = run(tmp_path, expectations={"row_count":2})
    assert mismatch.returncode == 1
    assert json.loads(mismatch.stdout)["reconciliation"]["failed_check_types"] == ["row_count"]
    invalid = run(tmp_path, "external_id,modified_at,name,email\nprivate,2026-10-04T12:00:00Z,Private,not-an-email\n")
    assert invalid.returncode == 1 and json.loads(invalid.stdout)["outcomes"] == {"quarantined":1}
    assert "not-an-email" not in invalid.stdout and "Private" not in invalid.stdout


@pytest.mark.parametrize("content", [b"\xff", b"x"*1_000_001, b"private malformed export"], ids=["encoding","size","shape"])
def test_invalid_files_are_redacted(tmp_path, content):
    result = run(tmp_path, content)
    assert result.returncode == 2 and json.loads(result.stdout)["status"] == "invalid_input"
    assert "private malformed" not in result.stdout + result.stderr


def test_dependencies_are_honestly_unresolved_in_empty_graph(tmp_path):
    definition = {"kind":"LoanAccount","object_type":"accounts","fields":{
        "customer_id":{"source":"customer","transform":"external_id","object_type":"customers"},
        "balance":{"source":"balance","transform":"decimal"},"currency":{"source":"currency","transform":"text"}}}
    result = run(tmp_path, "external_id,modified_at,customer,balance,currency\na1,2026-10-04T12:00:00Z,private-customer,1234.56,USD\n", definition=definition)
    assert result.returncode == 1
    assert json.loads(result.stdout)["reference_issue_counts"] == {"source_reference_unresolved":1}
    assert "private-customer" not in result.stdout and "1234.56" not in result.stdout
