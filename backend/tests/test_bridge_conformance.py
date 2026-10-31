from copy import deepcopy

import pytest

from core import dealer_bridge as bridge
from core.bridge_conformance import verify_pages
from core.bridge_contracts import SourceRecord, SyncPage
from core.dealeros import ledger
from tests.test_dealer_bridge import A, API, isolated, setup  # noqa: F401


def record(identity="captured-1", name="Synthetic", time="2026-10-04T19:00:00Z"):
    return SourceRecord("customers", identity, time, {"name": name, "email": f"{identity}@example.invalid"})


def test_fixture_check_is_nonpersistent_and_never_calls_connector(monkeypatch):
    _, mapping = setup(False)
    before = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    monkeypatch.setattr(bridge, "save_graph", lambda _: pytest.fail("Must not persist"))
    pages = [SyncPage((record(),), "opaque-secret-cursor", False), SyncPage((record("captured-2"),), None, True)]
    result = verify_pages(API, mapping, pages)
    assert result["status"] == "fixture_checks_passed" and not result["stored"]
    assert result["total_rows"] == 2
    assert "opaque-secret-cursor" not in str(result) and "@example.invalid" not in str(result)
    assert before == {key: value.attributes for key, value in ledger.entities.items()}
    assert result["fixture_hash"] == verify_pages(API, mapping, pages)["fixture_hash"]


def test_cross_page_same_time_conflict_is_detected_but_history_and_replay_are_allowed():
    _, mapping = setup()
    pages = [SyncPage((record(),), "page-2", False), SyncPage((record(name="Changed"),), None, True)]
    assert "cross_page_source_conflict" in {issue["code"] for issue in verify_pages(A, mapping, pages)["issues"]}
    pages[1] = SyncPage((record(),), None, True)
    assert verify_pages(A, mapping, pages)["status"] == "fixture_checks_passed"
    pages[1] = SyncPage((record(name="Changed", time="2026-10-04T20:00:00Z"),), None, True)
    assert verify_pages(A, mapping, pages)["status"] == "fixture_checks_passed"


def test_equivalent_timezones_detect_same_instant_conflicts():
    _, mapping = setup()
    pages = [SyncPage((record(),), "next", False), SyncPage((record(name="Different", time="2026-10-04T14:00:00-05:00"),), None, True)]
    assert verify_pages(A, mapping, pages)["issues"][0]["code"] == "cross_page_source_conflict"


def test_cursor_cycles_and_pages_after_completion_are_reported_without_tokens():
    _, mapping = setup()
    pages = [SyncPage((), "secret-a", False), SyncPage((), "secret-b", False), SyncPage((), "secret-a", False)]
    report = verify_pages(A, mapping, pages)
    assert report["issues"] == [{"page": 3, "code": "cursor_cycle"}]
    assert "secret-" not in str(report)
    assert verify_pages(A, mapping, [SyncPage((), "initial", False)], initial_cursor="initial")["status"] == "issues_found"
    assert verify_pages(A, mapping, [SyncPage((), None, True), SyncPage((), None, True)])["issues"][0]["code"] == "pages_after_completion"


def test_invalid_source_pages_and_missing_columns_have_sanitized_diagnostics():
    _, mapping = setup()
    malformed = SyncPage((SourceRecord("wrong", "id", "secret-time", {}),), None, True)
    assert verify_pages(A, mapping, [malformed])["issues"] == [{"page": 1, "code": "invalid_page_contract"}]
    missing = SyncPage((SourceRecord("customers", "id", "2026-10-04T19:00:00Z", {}),), None, True)
    assert verify_pages(A, mapping, [missing])["issues"][0]["code"] == "mapping_or_source_contract"


def test_bounded_inputs_and_workspace_checks():
    _, mapping = setup()
    for pages in [[], [SyncPage((), None, True)] * 11, iter([])]:
        with pytest.raises(ValueError):
            verify_pages(A, mapping, pages)
    with pytest.raises(ValueError, match="1000"):
        verify_pages(A, mapping, [SyncPage((record(),) * 600, "next", False), SyncPage((record(),) * 600, None, True)])
    with pytest.raises(PermissionError):
        verify_pages({**A, "workspace_id": "elsewhere"}, mapping, [SyncPage((), None, True)])


def test_even_empty_fixtures_cannot_pass_changed_or_revoked_mapping():
    _, mapping = setup()
    bridge.get(mapping, "BridgeMapping")["status"] = "revoked"
    with pytest.raises(ValueError, match="non-revoked"):
        verify_pages(A, mapping, [SyncPage((), None, True)])


def test_per_page_row_count_expectations_include_empty_pages_without_source_values():
    _, mapping = setup()
    pages = [SyncPage((record(),), "next", False), SyncPage((), "end", True)]
    before = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    passed = verify_pages(API, mapping, pages, page_expectations=[{"row_count": 1}, {"row_count": 0}])
    assert passed["status"] == "fixture_checks_passed"
    assert [page["reconciliation"]["status"] for page in passed["pages"]] == ["matched", "matched"]
    failed = verify_pages(API, mapping, pages, page_expectations=[{"row_count": 1}, {"row_count": 2}])
    assert failed["issues"] == [{"page": 2, "code": "reconciliation_requires_review"}]
    assert failed["pages"][1]["reconciliation"]["failed_check_types"] == ["row_count"]
    assert failed["expectations_hash"] != passed["expectations_hash"]
    assert failed["fixture_hash"] == passed["fixture_hash"]
    assert before == {key: value.attributes for key, value in ledger.entities.items()}


def test_complete_journal_and_totals_are_checked_without_printing_financial_values():
    from tests.test_bridge_accounting import configured, CSV
    from core.bridge_connectors import parse_csv
    mapping = configured()
    rows = parse_csv(CSV)[1]
    def page(records):
        return SyncPage(tuple(SourceRecord("journal_lines", row["external_id"], row["modified_at"], row) for row in records), None, True)
    expected = [{"balanced_journals": True, "row_count": 3, "totals": [{"field": "amount", "currency": "USD", "amount": "0.60"}]}]
    report = verify_pages(API, mapping, [page(rows)], page_expectations=expected)
    assert report["status"] == "fixture_checks_passed"
    assert report["pages"][0]["reconciliation"]["matched_checks"] == 4
    assert "journal-1" not in str(report) and "0.60" not in str(report)
    rows[2]["amount"] = "0.21"
    report = verify_pages(API, mapping, [page(rows)], page_expectations=expected)
    assert report["status"] == "issues_found"
    assert report["pages"][0]["reconciliation"]["failed_check_types"] == ["journal_balance", "monetary_total"]
    assert "0.21" not in str(report)


def test_invalid_reconciliation_contracts_are_rejected_even_for_empty_pages():
    _, mapping = setup()
    empty = [SyncPage((), None, True)]
    for expected in [[], {}, [None, None], [{"row_count": True}], [{"balanced_journals": True}],
                     [{"totals": [{"field": "amount", "currency": "USD", "amount": "1.00"}]}]]:
        with pytest.raises(ValueError): verify_pages(A, mapping, empty, page_expectations=expected)



def test_partial_capture_is_explicit_and_can_require_terminal_page():
    _, mapping = setup()
    pages = [SyncPage((record(),), "private-next-cursor", False)]
    partial = verify_pages(A, mapping, pages)
    assert partial["status"] == "fixture_checks_passed"
    assert not partial["terminal_page_captured"] and not partial["terminal_page_required"]
    required = verify_pages(A, mapping, pages, require_terminal_page=True)
    assert required["status"] == "issues_found"
    assert required["issues"] == [{"page": 1, "code": "terminal_page_missing"}]
    assert required["terminal_page_required"] and "private-next-cursor" not in str(required)
    pages.append(SyncPage((), None, True))
    complete = verify_pages(A, mapping, pages, require_terminal_page=True)
    assert complete["terminal_page_captured"] and complete["status"] == "fixture_checks_passed"


def test_invalid_terminal_envelope_cannot_satisfy_capture_requirement():
    _, mapping = setup()
    invalid = SyncPage((SourceRecord("wrong", "id", "private-time", {}),), None, True)
    result = verify_pages(A, mapping, [invalid], require_terminal_page=True)
    assert not result["terminal_page_captured"]
    assert {issue["code"] for issue in result["issues"]} == {"invalid_page_contract", "terminal_page_missing"}


@pytest.mark.parametrize("value", [1, None, "true", []])
def test_terminal_requirement_uses_explicit_boolean(value):
    _, mapping = setup()
    with pytest.raises(ValueError, match="boolean"):
        verify_pages(A, mapping, [SyncPage((), None, True)], require_terminal_page=value)



def test_relationship_advisories_are_visible_in_sanitized_capture_report():
    from tests.test_bridge_relationship_advisories import staged_difference
    job_id, _, other, contract, _ = staged_difference()
    job = bridge.get(job_id, "BridgeJob")
    row = job["rows"][0]
    page = SyncPage((SourceRecord("review_accounts", row["external_id"], row["modified_at"], row),), None, True)
    report = verify_pages(A, job["mapping_id"], [page])
    assert report["status"] == "issues_found"
    assert report["issues"] == [{"page": 1, "code": "relationship_review_advisory"}]
    assert report["pages"][0]["review_advisories"] == {"contract_customer_differs": 1}
    assert other.id not in str(report) and contract.id not in str(report)
