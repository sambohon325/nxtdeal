"""Check ordered authorized exports in a disposable in-memory pilot graph.

No vendor calls, existing graph reads, production approvals or persisted imports.
Passing steps are synthetically activated only inside this fresh process so later
steps can resolve their source references. No identity-review decisions are invented.
Exit codes: 0 fixture checks passed, 1 review issues, 2 invalid input/tool failure.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile

from check_bridge_adapter import read_json


def check(manifest_path):
    if any(name == "core" or name.startswith("core.") for name in sys.modules):
        raise RuntimeError("Run in a fresh standalone process")
    manifest_path = manifest_path.resolve()
    manifest = read_json(manifest_path, 128_000)
    if (not isinstance(manifest, dict) or set(manifest) != {"version", "steps"} or
            type(manifest["version"]) is not int or manifest["version"] != 1 or
            not isinstance(manifest["steps"], list) or not 1 <= len(manifest["steps"]) <= 10):
        raise ValueError("Bounded version-one pilot manifest required")
    prepared, byte_count = [], 0
    for step in manifest["steps"]:
        required = {"source", "mapping", "export", "format"}
        if not isinstance(step, dict) or not required <= step.keys() or set(step) - required - {"expectations"}:
            raise ValueError("Explicit pilot step required")
        if not isinstance(step["source"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", step["source"]):
            raise ValueError("Bounded source alias required")
        definition = step["mapping"]
        keys = {"kind", "object_type", "fields"}
        if not isinstance(definition, dict) or not keys <= definition.keys() or set(definition) - keys - {"source_columns"}:
            raise ValueError("Explicit canonical mapping required")
        if step["format"] not in {"csv", "tsv", "json"} or not isinstance(step["export"], str):
            raise ValueError("Explicit export format and relative path required")
        relative = Path(step["export"])
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError("Export must be inside the manifest directory")
        path = (manifest_path.parent / relative).resolve()
        if not path.is_relative_to(manifest_path.parent) or not path.is_file():
            raise ValueError("Regular local fixture inside manifest directory required")
        with path.open("rb") as stream:
            raw = stream.read(1_000_001)
        byte_count += len(raw)
        if len(raw) > 1_000_000 or byte_count > 2_000_000:
            raise ValueError("Pilot export byte limit exceeded")
        prepared.append((step, raw.decode("utf-8")))
    with tempfile.TemporaryDirectory(prefix="nxtdeal-offline-pilot-") as directory:
        os.environ["DEALEROS_STORAGE_DIR"] = directory
        os.environ["DEALEROS_AUTH_SECRET"] = secrets.token_hex(32)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from core import dealer_bridge as bridge
        bridge.save_graph = lambda path: None
        proposer = {"employee_id": "OFFLINE-PILOT-PROPOSER", "role": "ADMIN", "bridge_principal": "api"}
        reviewer = {"employee_id": "OFFLINE-PILOT-SIMULATED-REVIEWER", "role": "ADMIN", "bridge_principal": "session"}
        systems, reports, fingerprints = {}, [], []
        total_rows, simulated_activations, stopped = 0, 0, False
        for index, (step, content) in enumerate(prepared, 1):
            if stopped:
                reports.append({"step": index, "status": "not_checked_after_review_issue"})
                continue
            source = step["source"]
            if source not in systems:
                systems[source] = bridge.connect(proposer, "CSV", "Offline pilot source")["id"]
            definition = step["mapping"]
            mapping = bridge.propose_mapping(proposer, systems[source], definition["kind"], definition["object_type"],
                definition["fields"], definition.get("source_columns"))["id"]
            result = bridge.simulate_mapping(proposer, mapping, content, step.get("expectations"), step["format"])
            rows, reconciliation = result["rows"], result["reconciliation"]
            total_rows += len(rows)
            if total_rows > 1000:
                raise ValueError("Pilot exceeds 1000 total rows")
            outcomes = dict(Counter(row["status"] for row in rows))
            references = dict(Counter(issue["reason"] for row in rows for issue in row.get("reference_issues", [])))
            advisories = dict(Counter(item["code"] for row in rows for item in row.get("review_advisories", [])))
            stopped = bool(outcomes.get("quarantined") or advisories or reconciliation["status"] in {"mismatch", "incomplete"})
            checks = reconciliation["checks"]
            evidence = result["source_evidence"]
            fingerprints.append([result["mapping_hash"], evidence["export_sha256"], bridge.digest(step.get("expectations"))])
            reports.append({"step": index, "status": "review_required" if stopped else "fixture_checks_passed",
                "rows": len(rows), "outcomes": outcomes, "reference_issue_counts": references,
                "review_advisory_counts": advisories, "mapping_hash": result["mapping_hash"],
                "export_sha256": evidence["export_sha256"], "schema_hash": evidence["schema_hash"],
                "reconciliation": {"status": reconciliation["status"], "checks": len(checks),
                    "matched_checks": sum(item["matched"] for item in checks),
                    "failed_check_types": sorted({item["check"] for item in checks if not item["matched"]})}})
            if not stopped:
                bridge.approve_mapping(reviewer, mapping)
                job = bridge.stage(proposer, mapping, content, step.get("expectations"), step["format"])["id"]
                bridge.validate(proposer, job)
                bridge.activate(reviewer, job)
                simulated_activations += 1
        return {"status": "issues_found" if stopped else "fixture_checks_passed", "production_access": False,
            "persisted": False, "environment": "disposable_pilot_graph", "steps": reports,
            "total_checked_rows": total_rows, "export_bytes": byte_count,
            "simulated_activated_steps": simulated_activations,
            "checked_fixture_hash": bridge.digest(fingerprints),
            "notice": "Passing steps are synthetically approved and activated only in this disposable in-memory graph for dependency checks. No production graph, vendor, credentials or external sink is accessed. Source aliases isolate external IDs; no cross-source identity links are inferred. Processing stops at the first review issue. Passing fixtures does not establish production approval, financial completeness or vendor access. Paths, source aliases, record values and totals are omitted."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = check(args.manifest)
    except Exception:
        print(json.dumps({"status": "invalid_input", "production_access": False, "persisted": False,
            "notice": "Check the bounded version-one manifest, relative fixture paths and canonical mapping contracts. No production data was loaded."}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "fixture_checks_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
