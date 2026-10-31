"""Process-isolated pilot checks preserve production storage and source privacy."""
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend/tests/fixtures/bridge_pilot"


def bundle(tmp_path):
    folder = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, folder)
    return folder, json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def run(tmp_path, folder, manifest):
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    protected = tmp_path / "production-storage"
    protected.mkdir(exist_ok=True)
    marker = protected / "graph.json"
    marker.write_text('{"private":"must not load or modify"}', encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check_bridge_pilot.py"),
        "--manifest", str(path)], cwd=tmp_path, capture_output=True, text=True, timeout=30,
        env={**os.environ, "DEALEROS_STORAGE_DIR": str(protected), "DEALEROS_AUTH_SECRET": "private-existing-secret"})
    assert marker.read_text(encoding="utf-8") == '{"private":"must not load or modify"}'
    assert sorted(item.name for item in protected.iterdir()) == ["graph.json"]
    for private in ("private-existing-secret", str(tmp_path), "Synthetic pilot borrower", "customers-synthetic-1", "1000.00", "synthetic-dms"):
        assert private not in result.stdout + result.stderr
    return result, json.loads(result.stdout)


def test_related_csv_tsv_json_exports_resolve_in_disposable_graph(tmp_path):
    folder, manifest = bundle(tmp_path)
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == 0, result.stderr
    assert report["environment"] == "disposable_pilot_graph"
    assert not report["persisted"] and not report["production_access"]
    assert report["total_checked_rows"] == 3
    assert report["simulated_activated_steps"] == 3
    assert [step["outcomes"] for step in report["steps"]] == [{"ready": 1}] * 3
    assert all(step["reconciliation"]["status"] == "matched" for step in report["steps"])


@pytest.mark.parametrize("issue", ["wrong_order", "different_source", "missing_parent", "reconciliation"])
def test_first_issue_stops_processing_without_invented_dependencies(tmp_path, issue):
    folder, manifest = bundle(tmp_path)
    if issue == "wrong_order":
        manifest["steps"][0], manifest["steps"][1] = manifest["steps"][1], manifest["steps"][0]
    elif issue == "different_source": manifest["steps"][1]["source"] = "separate-crm"
    elif issue == "missing_parent":
        path = folder / "contracts.tsv"
        path.write_text(path.read_text(encoding="utf-8").replace("customers-synthetic-1", "missing-private-parent"), encoding="utf-8")
    else: manifest["steps"][0]["expectations"] = {"row_count": 2}
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == 1 and report["status"] == "issues_found"
    blocked = next(step for step in report["steps"] if step["status"] == "review_required")
    assert report["simulated_activated_steps"] == blocked["step"] - 1
    assert report["steps"][-1]["status"] == "not_checked_after_review_issue"
    if issue == "reconciliation": assert blocked["reconciliation"]["failed_check_types"] == ["row_count"]
    else: assert blocked["reference_issue_counts"] == {"source_reference_unresolved": 1}
    assert "missing-private-parent" not in result.stdout + result.stderr


def test_relationship_advisory_stops_disposable_activation(tmp_path):
    folder, manifest = bundle(tmp_path)
    with (folder / "customers.csv").open("a", encoding="utf-8") as stream:
        stream.write("second-private-customer,2026-10-04T12:00:00Z,Second synthetic borrower\n")
    manifest["steps"][0]["expectations"] = {"row_count": 2}
    path = folder / "accounts.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["customer_id"] = "second-private-customer"
    path.write_text(json.dumps(records), encoding="utf-8")
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == 1
    assert report["steps"][-1]["review_advisory_counts"] == {"contract_customer_differs": 1}
    assert report["simulated_activated_steps"] == 2
    assert "second-private-customer" not in result.stdout + result.stderr


@pytest.mark.parametrize("invalid", ["version", "traversal", "absolute", "unknown_key", "oversize"])
def test_invalid_input_returns_sanitized_failure(tmp_path, invalid):
    folder, manifest = bundle(tmp_path)
    if invalid == "version": manifest["version"] = True
    elif invalid == "traversal": manifest["steps"][0]["export"] = "../private.csv"
    elif invalid == "absolute": manifest["steps"][0]["export"] = str(folder / "customers.csv")
    elif invalid == "unknown_key": manifest["steps"][0]["credentials"] = "must-not-use"
    else: (folder / "customers.csv").write_bytes(b"x" * 1_000_001)
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == 2 and report["status"] == "invalid_input"
    assert "must-not-use" not in result.stdout + result.stderr


@pytest.mark.parametrize("changed", [False, True])
def test_replayed_source_version_is_duplicate_or_requires_review(tmp_path, changed):
    folder, manifest = bundle(tmp_path)
    replay = deepcopy(manifest["steps"][0])
    replay["export"] = "replay.csv"
    content = (folder / "customers.csv").read_text(encoding="utf-8")
    if changed: content = content.replace("Synthetic pilot borrower", "Conflicting private borrower")
    (folder / "replay.csv").write_text(content, encoding="utf-8")
    manifest["steps"] = [manifest["steps"][0], replay]
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == (1 if changed else 0)
    assert report["steps"][1]["outcomes"] == {"quarantined" if changed else "duplicate": 1}
    assert report["simulated_activated_steps"] == (1 if changed else 2)
    assert "Conflicting private borrower" not in result.stdout + result.stderr


@pytest.mark.parametrize("bound", ["total_bytes", "total_rows"])
def test_bundle_wide_limits_apply_across_individually_bounded_files(tmp_path, bound):
    folder, manifest = bundle(tmp_path)
    if bound == "total_bytes":
        (folder / "customers.csv").write_bytes(b"x" * 700_000)
        manifest["steps"] = [deepcopy(manifest["steps"][0]) for _ in range(3)]
    else:
        content = "external_id,modified_at,first_name\n" + "".join(
            f"synthetic-{index},2026-10-04T12:00:00Z,Synthetic row\n" for index in range(501))
        (folder / "customers.csv").write_text(content, encoding="utf-8")
        step = manifest["steps"][0]
        step["expectations"] = {"row_count": 501}
        manifest["steps"] = [deepcopy(step), deepcopy(step)]
    result, report = run(tmp_path, folder, manifest)
    assert result.returncode == 2 and report["status"] == "invalid_input"


@pytest.mark.parametrize("change", ["none", "allocation", "reversal_reference", "unbalanced_journal"])
def test_bhph_accounting_bundle_checks_allocations_reversals_and_journals(tmp_path, change):
    folder, _ = bundle(tmp_path)
    manifest = json.loads((folder / "bhph-accounting-manifest.json").read_text(encoding="utf-8"))
    if change == "allocation":
        path = folder / "payments.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("90.00,8.00,2.00", "90.00,8.00,3.00"), encoding="utf-8")
    elif change == "reversal_reference":
        path = folder / "reversals.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        records[0]["reverses_payment_id"] = "missing-payment"
        path.write_text(json.dumps(records), encoding="utf-8")
    elif change == "unbalanced_journal":
        path = folder / "journal.tsv"
        path.write_text(path.read_text(encoding="utf-8").replace("credit\t100.00", "credit\t99.00"), encoding="utf-8")
    result, report = run(tmp_path, folder, manifest)
    if change == "none":
        assert result.returncode == 0
        assert report["total_checked_rows"] == 10 and report["simulated_activated_steps"] == 8
        assert report["steps"][-1]["reconciliation"] == {
            "status": "matched", "checks": 4, "matched_checks": 4, "failed_check_types": []}
    else:
        assert result.returncode == 1
        stopped = next(step for step in report["steps"] if step["status"] == "review_required")
        assert stopped["step"] == {"allocation": 4, "reversal_reference": 5, "unbalanced_journal": 8}[change]
        assert report["simulated_activated_steps"] == stopped["step"] - 1
        if change == "unbalanced_journal":
            assert "journal_balance" in stopped["reconciliation"]["failed_check_types"]
