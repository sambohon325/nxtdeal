"""Run the actual standalone command without sharing the test process graph."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend/tests/fixtures/bridge_conformance"
SCRIPT = ROOT / "scripts/check_bridge_adapter.py"


def run(tmp_path, content=None, mapping=None, *, require_terminal_page=False):
    pages = FIXTURES / "pages.json"
    if content is not None:
        pages = tmp_path / "captured.json"
        pages.write_text(content, encoding="utf-8")
    protected = tmp_path / "existing-storage"
    protected.mkdir(exist_ok=True)
    marker = protected / "graph.json"
    marker.write_text('{"private": "must remain untouched"}', encoding="utf-8")
    env = {**os.environ, "DEALEROS_STORAGE_DIR": str(protected), "DEALEROS_AUTH_SECRET": "existing-secret-do-not-print"}
    result = subprocess.run([sys.executable, str(SCRIPT), "--mapping", str(mapping or FIXTURES / "mapping.json"), "--pages", str(pages)] + (["--require-terminal-page"] if require_terminal_page else []),
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert marker.read_text() == '{"private": "must remain untouched"}'
    assert sorted(path.name for path in protected.iterdir()) == ["graph.json"]
    assert "existing-secret" not in result.stdout + result.stderr
    return result


def test_standalone_fixture_reports_without_production_access(tmp_path):
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "fixture_checks_passed" and not report["production_access"]
    assert report["total_rows"] == 1 and report["environment"] == "disposable_empty_graph"
    assert "synthetic@example.invalid" not in result.stdout and "synthetic-1" not in result.stdout


def test_source_contract_issues_have_nonzero_exit_without_payloads(tmp_path):
    captured = json.loads((FIXTURES / "pages.json").read_text())
    captured["pages"][0]["records"][0]["modified_at"] = "private-invalid-time"
    result = run(tmp_path, json.dumps(captured))
    assert result.returncode == 1
    assert json.loads(result.stdout)["issues"] == [{"page": 1, "code": "invalid_page_contract"}]
    assert "private-invalid-time" not in result.stdout + result.stderr


def test_duplicate_json_keys_and_oversized_inputs_are_sanitized(tmp_path):
    for content in ['{"pages":[],"pages":"private-duplicate-value"}', "x" * 2_000_001]:
        result = run(tmp_path, content)
        assert result.returncode == 2 and json.loads(result.stdout)["status"] == "invalid_input"
        assert "private-duplicate-value" not in result.stdout + result.stderr
        assert str(tmp_path) not in result.stdout + result.stderr


def test_cli_reconciliation_expectations_change_exit_code_without_source_values(tmp_path):
    captured = json.loads((FIXTURES / "pages.json").read_text(encoding="utf-8"))
    captured["page_expectations"] = [{"row_count": 1}]
    passed = run(tmp_path, json.dumps(captured))
    assert passed.returncode == 0
    captured["page_expectations"] = [{"row_count": 2}]
    failed = run(tmp_path, json.dumps(captured))
    assert failed.returncode == 1
    result = json.loads(failed.stdout)
    assert result["issues"] == [{"page": 1, "code": "reconciliation_requires_review"}]
    assert result["pages"][0]["reconciliation"]["failed_check_types"] == ["row_count"]
    assert "synthetic@example.invalid" not in failed.stdout


def test_documented_journal_fixture_passes_financial_conformance(tmp_path):
    result = run(tmp_path, (FIXTURES / "journal-pages.json").read_text(encoding="utf-8"), FIXTURES / "journal-mapping.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["pages"][0]["reconciliation"] == {"status": "matched", "checks": 4, "matched_checks": 4, "failed_check_types": []}
    assert "synthetic-journal" not in result.stdout and "0.60" not in result.stdout



def test_cli_terminal_requirement_rejects_partial_and_accepts_final_capture(tmp_path):
    captured = json.loads((FIXTURES / "pages.json").read_text(encoding="utf-8"))
    captured["pages"][0].update(cursor="secret-next-page", complete=False)
    partial = run(tmp_path, json.dumps(captured))
    assert partial.returncode == 0 and not json.loads(partial.stdout)["terminal_page_captured"]
    required = run(tmp_path, json.dumps(captured), require_terminal_page=True)
    assert required.returncode == 1
    assert json.loads(required.stdout)["issues"] == [{"page": 1, "code": "terminal_page_missing"}]
    assert "secret-next-page" not in required.stdout + required.stderr
    captured["pages"].append({"records": [], "cursor": None, "complete": True})
    complete = run(tmp_path, json.dumps(captured), require_terminal_page=True)
    assert complete.returncode == 0
    assert json.loads(complete.stdout)["terminal_page_captured"]
