"""Offline mapping check for one authorized CSV/TSV/flat JSON export.

No production graph is loaded, no connector is called, and no rows are staged.
Exit codes: 0 fixture checks passed, 1 review issues, 2 invalid input/tool failure.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

from check_bridge_adapter import read_json


def check(mapping_path, export_path, file_format, expectations_path=None):
    if any(name == "core" or name.startswith("core.") for name in sys.modules):
        raise RuntimeError("Run in a fresh standalone process")
    definition = read_json(mapping_path, 64_000)
    required = {"kind", "object_type", "fields"}
    if not isinstance(definition, dict) or not required <= definition.keys() or set(definition) - required - {"source_columns"}:
        raise ValueError("Explicit canonical mapping required")
    if file_format not in {"csv", "tsv", "json"} or not export_path.is_file():
        raise ValueError("Explicit bounded export format and regular file required")
    with export_path.open("rb") as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Export exceeds limit")
    content = raw.decode("utf-8")
    expected = read_json(expectations_path, 32_000) if expectations_path else None
    with tempfile.TemporaryDirectory(prefix="nxtdeal-offline-export-") as directory:
        os.environ["DEALEROS_STORAGE_DIR"] = directory
        os.environ["DEALEROS_AUTH_SECRET"] = secrets.token_hex(32)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from core import dealer_bridge as bridge
        bridge.save_graph = lambda path: None
        actor = {"employee_id":"OFFLINE-EXPORT-CHECK", "role":"ADMIN", "bridge_principal":"api"}
        system = bridge.connect(actor, "CSV", "Offline authorized export")["id"]
        mapping = bridge.propose_mapping(actor, system, definition["kind"], definition["object_type"],
            definition["fields"], definition.get("source_columns"))["id"]
        result = bridge.simulate_mapping(actor, mapping, content, expected, file_format)
        outcomes = dict(Counter(row["status"] for row in result["rows"]))
        references = Counter(issue["reason"] for row in result["rows"] for issue in row.get("reference_issues", []))
        reconciliation = result["reconciliation"]
        issues = bool(outcomes.get("quarantined")) or reconciliation["status"] in {"mismatch", "incomplete"}
        return {"status":"issues_found" if issues else "fixture_checks_passed", "stored":False,
            "production_access":False, "environment":"disposable_empty_graph", "file_format":file_format,
            "mapping_hash":result["mapping_hash"], "rows":len(result["rows"]), "outcomes":outcomes,
            "reference_issue_counts":dict(references),
            "export_sha256":result["source_evidence"]["export_sha256"],
            "schema_hash":result["source_evidence"]["schema_hash"],
            "reconciliation":{"status":reconciliation["status"], "checks":len(reconciliation["checks"]),
                "matched_checks":sum(item["matched"] for item in reconciliation["checks"]),
                "failed_check_types":sorted({item["check"] for item in reconciliation["checks"] if not item["matched"]})},
            "notice":"Offline export check against an empty disposable graph. Referenced records are not loaded, so dependency issues require separate review. No approval, staging, activation, source access or completeness is established. Source values, identifiers, headers and monetary totals are omitted from this report."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--export", dest="export_path", type=Path, required=True)
    parser.add_argument("--format", dest="file_format", choices=["csv","tsv","json"], required=True)
    parser.add_argument("--expectations", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.mapping, args.export_path, args.file_format, args.expectations)
    except Exception:
        print(json.dumps({"status":"invalid_input", "production_access":False,
            "notice":"Check bounded UTF-8 mapping, export and optional reconciliation fixtures. No production data was loaded."}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "fixture_checks_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
