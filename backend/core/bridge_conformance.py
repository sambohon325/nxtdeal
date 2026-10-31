"""Offline captured-page checks against the actual Bridge import pipeline.

No adapter methods, credentials, runtime bindings, staging or approvals are used.
Passing captured fixtures is not proof of source completeness or vendor access.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from core import dealer_bridge as bridge
from core.bridge_contracts import SyncPage, timestamp
from core.bridge_sync import page_csv
from core.bridge_reconciliation import mapping_expectations, reconcile


def verify_pages(actor, mapping_id, pages, *, initial_cursor=None, page_expectations=None, require_terminal_page=False):
    bridge.authorize(actor)
    if type(require_terminal_page) is not bool:
        raise ValueError("Terminal-page requirement must be boolean")
    if not isinstance(pages, (list, tuple)) or not 1 <= len(pages) <= 10:
        raise ValueError("Supply 1 to 10 captured pages")
    if initial_cursor is not None and (not isinstance(initial_cursor, str) or not initial_cursor or len(initial_cursor) > 2048):
        raise ValueError("Bounded initial cursor required")
    if page_expectations is not None and (not isinstance(page_expectations, (list, tuple)) or len(page_expectations) != len(pages)):
        raise ValueError("Supply one expectation object per captured page")
    # Snapshot under the same lock as ordinary simulation. No graph changes occur.
    with bridge.LOCK:
        mapping = deepcopy(bridge.get(mapping_id, "BridgeMapping"))
        system = deepcopy(bridge.get(mapping["system_id"], "BridgeSystem"))
        if mapping["status"] == "revoked" or bridge.mapping_digest(mapping) != mapping["hash"]:
            raise ValueError("An unchanged, non-revoked mapping is required")
        expected_pages = [mapping_expectations(mapping, item) for item in (page_expectations if page_expectations is not None else [None] * len(pages))]
        report, issues, fingerprints, seen_records, seen_cursors = [], [], [], {}, set()
        cursor, total_rows, total_bytes = initial_cursor, 0, 0
        if cursor is not None:
            seen_cursors.add(cursor)
        terminal_page_captured = False
        for index, page in enumerate(pages, 1):
            terminal_page_captured = False
            expected = expected_pages[index - 1]
            if not isinstance(page, SyncPage):
                raise ValueError("Captured pages must use the SDK SyncPage contract")
            total_rows += len(page.records) if isinstance(page.records, tuple) else 0
            if total_rows > 1000:
                raise ValueError("Captured fixture exceeds 1000 total records")
            try:
                content = page_csv(page, mapping)
            except (ValueError, TypeError, OverflowError):
                # Do not reflect raw vendor payloads, cursors or exceptions.
                issues.append({"page": index, "code": "invalid_page_contract"})
                report.append({"page": index, "status": "invalid", "rows": None})
                continue
            terminal_page_captured = page.complete
            if not page.complete and page.cursor in seen_cursors:
                issues.append({"page": index, "code": "cursor_cycle"})
            if page.complete and index < len(pages):
                issues.append({"page": index, "code": "pages_after_completion"})
            if page.cursor is not None:
                seen_cursors.add(page.cursor)
            cursor = page.cursor
            encoded = (content or "").encode("utf-8")
            total_bytes += len(encoded)
            if total_bytes > 2_000_000:
                raise ValueError("Captured fixture exceeds 2 MB serialized total")
            fingerprints.append({"page": index, "sha256": sha256(encoded).hexdigest(),
                                 "cursor_hash": bridge.digest(cursor), "complete": page.complete})
            if content is None:
                summary = _reconciliation_summary([], expected)
                if summary["status"] in {"mismatch", "incomplete"}:
                    issues.append({"page": index, "code": "reconciliation_requires_review"})
                report.append({"page": index, "status": "empty", "rows": 0, "complete": page.complete, "reconciliation": summary})
                continue
            try:
                prepared = bridge.prepare_import(mapping, system, content, expected)
                checked = bridge.preview(prepared, mapping)
            except (ValueError, TypeError, OverflowError):
                issues.append({"page": index, "code": "mapping_or_source_contract"})
                report.append({"page": index, "status": "invalid", "rows": len(page.records)})
                continue
            for row, checked_row in zip(prepared["rows"], checked):
                if checked_row["status"] == "quarantined":
                    continue
                key = (row["external_id"], timestamp(row["modified_at"]))
                fingerprint = bridge.digest(checked_row.get("values", {}))
                previous = seen_records.get(key)
                if previous is not None and previous != fingerprint:
                    issues.append({"page": index, "row": checked_row["row"], "code": "cross_page_source_conflict"})
                seen_records[key] = fingerprint
            advisory_counts = dict(Counter(advisory["code"] for row in checked for advisory in row.get("review_advisories", [])))
            if advisory_counts:
                issues.append({"page": index, "code": "relationship_review_advisory"})
            counts = dict(Counter(row["status"] for row in checked))
            if counts.get("quarantined"):
                issues.append({"page": index, "code": "rows_require_review"})
            summary = _reconciliation_summary(checked, expected)
            if summary["status"] in {"mismatch", "incomplete"}:
                issues.append({"page": index, "code": "reconciliation_requires_review"})
            report.append({"page": index, "reconciliation": summary, "status": "checked", "rows": len(checked),
                           "outcomes": counts, "review_advisories": advisory_counts, "complete": page.complete,
                           "schema_hash": prepared["source_evidence"]["schema_hash"]})
        if require_terminal_page and not terminal_page_captured:
            issues.append({"page": len(pages), "code": "terminal_page_missing"})
        return {"status": "issues_found" if issues else "fixture_checks_passed", "stored": False,
                "terminal_page_captured": terminal_page_captured, "terminal_page_required": require_terminal_page,
                "mapping_id": mapping_id, "mapping_hash": mapping["hash"], "pages": report,
                "issues": issues, "total_rows": total_rows, "serialized_bytes": total_bytes,
                "fixture_hash": bridge.digest(fingerprints), "expectations_hash": bridge.digest(expected_pages),
                "notice": "Captured-page checks only. No connector was called, no cursor advanced and no records were staged. A terminal page is an adapter declaration, not proof of source completeness. Passing fixtures does not verify vendor access, source completeness, runtime behavior or production approval. Each page is evaluated against current graph state, not simulated activation of previous pages."}


def _reconciliation_summary(rows, expected):
    result = reconcile(rows, expected)
    checks = result["checks"]
    # Do not echo account/journal identities, source amounts or supplied totals.
    return {"status": result["status"], "checks": len(checks),
            "matched_checks": sum(check["matched"] for check in checks),
            "failed_check_types": sorted({check["check"] for check in checks if not check["matched"]})}
