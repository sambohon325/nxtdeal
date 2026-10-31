"""Offline captured-page conformance. No vendor calls or production graph load.

python scripts/check_bridge_adapter.py --mapping mapping.json --pages pages.json
Exit codes: 0 fixture checks passed, 1 review issues, 2 invalid input/tool failure.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile


def read_json(path, limit):
    if not path.is_file():
        raise ValueError("Regular fixture file required")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Fixture exceeds limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate property")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Invalid numeric constant")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid)


def check(mapping_path, pages_path, *, require_terminal_page=False):
    if any(name == "core" or name.startswith("core.") for name in sys.modules):
        raise RuntimeError("Run this checker in a fresh standalone process")
    definition = read_json(mapping_path, 64_000)
    captured = read_json(pages_path, 2_000_000)
    required = {"kind", "object_type", "fields"}
    if not isinstance(definition, dict) or not required <= definition.keys() or set(definition) - required - {"source_columns"}:
        raise ValueError("Explicit canonical mapping required")
    if not isinstance(captured, dict) or set(captured) - {"pages", "initial_cursor", "page_expectations"} or not isinstance(captured.get("pages"), list) or not 1 <= len(captured["pages"]) <= 10:
        raise ValueError("Bounded captured pages required")
    with tempfile.TemporaryDirectory(prefix="nxtdeal-offline-contract-") as directory:
        # Set isolation before importing any application module. No stored graph
        # or credentials are loaded; this process has no runtime bindings.
        os.environ["DEALEROS_STORAGE_DIR"] = directory
        os.environ["DEALEROS_AUTH_SECRET"] = secrets.token_hex(32)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from core import dealer_bridge as bridge
        from core.bridge_contracts import SourceRecord, SyncPage
        from core.bridge_conformance import verify_pages
        bridge.save_graph = lambda path: None
        actor = {"employee_id": "OFFLINE-CONFORMANCE", "role": "ADMIN", "bridge_principal": "api"}
        system = bridge.connect(actor, "CSV", "Offline captured fixture")["id"]
        mapping = bridge.propose_mapping(actor, system, definition["kind"], definition["object_type"],
                                         definition["fields"], definition.get("source_columns"))["id"]
        pages = []
        count = 0
        for page in captured["pages"]:
            if not isinstance(page, dict) or set(page) != {"records", "cursor", "complete"} or not isinstance(page["records"], list):
                raise ValueError("Explicit page envelope required")
            count += len(page["records"])
            if count > 1000:
                raise ValueError("At most 1000 captured records")
            records = []
            for record in page["records"]:
                if not isinstance(record, dict) or set(record) != {"object_type", "external_id", "modified_at", "values"}:
                    raise ValueError("Explicit source record envelope required")
                records.append(SourceRecord(**record))
            pages.append(SyncPage(tuple(records), page["cursor"], page["complete"]))
        report = verify_pages(actor, mapping, pages, initial_cursor=captured.get("initial_cursor"), page_expectations=captured.get("page_expectations"), require_terminal_page=require_terminal_page)
        report["environment"] = "disposable_empty_graph"
        report["production_access"] = False
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--require-terminal-page", action="store_true", help="Report a review issue when the final captured page does not declare completion")
    args = parser.parse_args()
    try:
        report = check(args.mapping, args.pages, require_terminal_page=args.require_terminal_page)
    except Exception:
        # Do not echo source values, paths, raw parser exceptions or secrets.
        print(json.dumps({"status": "invalid_input", "production_access": False,
                          "notice": "Check bounded UTF-8 JSON fixtures and the documented mapping/page contracts. No production data was loaded."}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "fixture_checks_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
