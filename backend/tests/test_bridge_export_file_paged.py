import csv
import io

import pytest
from core.bridge_adapters.export_file_paged import PagedExportFileConnector
from core.bridge_sync import ConnectorFailure
from core import bridge_runtime as runtime, bridge_sync as sync, dealer_bridge as bridge
from tests.test_bridge_sync import configured, state_of, A, B, isolated  # noqa: F401


def content(count=3, delimiter=",", note="line one\nline two"):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["external_id", "modified_at", "name", "email", "note"])
    for index in range(count): writer.writerow([str(index), "2026-10-04T12:00:00Z", f"Synthetic {index}", f"qa{index}@example.invalid", note])
    return buffer.getvalue()


def reader(tmp_path, text=None, **options):
    path = tmp_path / "paged-export.csv"
    path.write_text(content() if text is None else text, encoding="utf-8", newline="")
    return path, PagedExportFileConnector(path, object_type="customers", page_size=options.pop("page_size", 2), **options)


@pytest.mark.parametrize("file_format", ["csv", "tsv"])
def test_logical_rows_page_correctly_with_quoted_newlines_and_stable_end_cursor(tmp_path, file_format):
    _, adapter = reader(tmp_path, content(delimiter="\t" if file_format == "tsv" else ","), file_format=file_format)
    first = adapter.sync("customers")
    assert [row.external_id for row in first.records] == ["0", "1"] and not first.complete
    assert first.records[0].values["note"] == "line one\nline two"
    second = adapter.sync("customers", first.cursor)
    assert [row.external_id for row in second.records] == ["2"] and second.complete
    empty = adapter.sync("customers", second.cursor)
    assert not empty.records and empty.cursor == second.cursor and empty.complete


def test_changed_incomplete_snapshot_blocks_but_completed_snapshot_can_restart(tmp_path):
    path, adapter = reader(tmp_path)
    first = adapter.sync("customers")
    end = adapter.sync("customers", first.cursor)
    path.write_text(content(4), encoding="utf-8", newline="")
    with pytest.raises(ConnectorFailure) as error: adapter.sync("customers", first.cursor)
    assert error.value.code == "source_changed" and not error.value.retryable
    fresh = adapter.sync("customers", end.cursor)
    assert [row.external_id for row in fresh.records] == ["0", "1"] and not fresh.complete
    assert fresh.cursor != first.cursor


def test_larger_than_one_megabyte_and_one_thousand_rows_stays_page_bounded(tmp_path):
    text = content(1501, note="x" * 700)
    assert len(text.encode()) > 1_000_000
    _, adapter = reader(tmp_path, text, page_size=500)
    cursor, counts = None, []
    while True:
        page = adapter.sync("customers", cursor)
        counts.append(len(page.records)); cursor = page.cursor
        if page.complete: break
    assert counts == [500, 500, 500, 1]


@pytest.mark.parametrize("invalid", ["opaque", "csvpage:v1:" + "a" * 64 + ":0:more", "csvpage:v1:" + "a" * 64 + ":999999:done"])
def test_invalid_or_unbounded_cursor_is_rejected(tmp_path, invalid):
    _, adapter = reader(tmp_path)
    with pytest.raises(ConnectorFailure): adapter.sync("customers", invalid)


def test_snapshot_row_and_byte_limits_and_bad_later_width_fail_before_first_page(tmp_path):
    path, adapter = reader(tmp_path)
    adapter.max_snapshot_rows = 2
    with pytest.raises(ConnectorFailure): adapter.sync("customers")
    adapter.max_snapshot_rows = 100_000
    adapter.max_snapshot_bytes = 10
    with pytest.raises(ConnectorFailure): adapter.sync("customers")
    adapter.max_snapshot_bytes = 25_000_000
    path.write_text(content() + "bad,row\n", encoding="utf-8", newline="")
    with pytest.raises(ConnectorFailure): adapter.sync("customers")


def test_each_collected_page_requires_activation_before_the_next_file_position(tmp_path):
    system, mapping, state, _ = configured()
    _, adapter = reader(tmp_path, page_size=2)
    runtime.bind(system, adapter, revision="paged-file-1", objects=["customers"], environment="synthetic")
    sync.configure(A, mapping, True, 60, reviewed_binding_revision="paged-file-1", reviewed_binding_environment="synthetic")
    first = sync.run_once(A, state)["job_id"]
    assert state_of(state)["cursor"] is None
    assert sync.run_once(A, state)["job_id"] == first
    bridge.validate(A, first); bridge.activate(B, first)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    first_cursor = state_of(state)["cursor"]
    second = sync.run_once(A, state)["job_id"]
    assert second != first and state_of(state)["cursor"] == first_cursor
    bridge.validate(A, second); bridge.activate(B, second)
    assert sync.run_once(B, state)["status"] == "checkpointed"
    assert state_of(state)["pages_accepted"] == 2
    assert bridge.import_report(A, first)["receipt_integrity"] == "consistent"
    assert bridge.import_report(A, second)["receipt_integrity"] == "consistent"



def grouped_content(groups):
    buffer = io.StringIO(); writer = csv.writer(buffer)
    writer.writerow(["external_id", "modified_at", "name", "email", "journal"])
    for index, group in enumerate(groups): writer.writerow([str(index), "2026-10-04T12:00:00Z", "Synthetic", "", group])
    return buffer.getvalue()


def test_grouped_pages_never_split_or_skip_contiguous_source_groups(tmp_path):
    _, adapter = reader(tmp_path, grouped_content(["a", "a", "b", "b", "c"]), page_size=3, group_by_source_column="journal")
    first = adapter.sync("customers")
    second = adapter.sync("customers", first.cursor)
    assert [row.external_id for row in first.records] == ["0", "1"]
    assert [row.external_id for row in second.records] == ["2", "3", "4"]
    assert not first.complete and second.complete
    assert not adapter.sync("customers", second.cursor).records


@pytest.mark.parametrize("groups", [["a", "b", "a"], ["a", "a", "a", "a"], ["a", ""], ["a", " b"]], ids=["noncontiguous", "oversized", "blank", "whitespace"])
def test_ambiguous_or_oversized_groups_block_before_first_page(tmp_path, groups):
    _, adapter = reader(tmp_path, grouped_content(groups), page_size=3, group_by_source_column="journal")
    with pytest.raises(ConnectorFailure): adapter.sync("customers")


def test_grouping_column_and_cursor_must_match_source_group_boundaries(tmp_path):
    _, missing = reader(tmp_path, group_by_source_column="missing")
    with pytest.raises(ConnectorFailure): missing.sync("customers")
    _, adapter = reader(tmp_path, grouped_content(["a", "a", "b", "b"]), page_size=2, group_by_source_column="journal")
    cursor = adapter.sync("customers").cursor.replace(":2:more", ":1:more")
    with pytest.raises(ConnectorFailure): adapter.sync("customers", cursor)


def test_grouped_journal_pages_each_pass_explicit_balance_reconciliation(tmp_path):
    from tests.test_bridge_accounting import CSV as JOURNAL, configured as journal_mapping
    mapping = journal_mapping()
    second = JOURNAL.split("\n", 1)[1].replace("line-", "other-").replace("journal-1", "journal-2")
    path = tmp_path / "journals.csv"; path.write_text(JOURNAL + second, encoding="utf-8", newline="")
    adapter = PagedExportFileConnector(path, object_type="journal_lines", page_size=4, group_by_source_column="journal_id")
    cursor = None
    for _ in range(2):
        page = adapter.sync("journal_lines", cursor)
        assert len(page.records) == 3
        text = sync.page_csv(page, bridge.get(mapping, "BridgeMapping"))
        job = bridge.stage(A, mapping, text, {"balanced_journals": True})["id"]
        bridge.validate(A, job)
        assert bridge.import_report(A, job)["reconciliation"]["status"] == "matched"
        bridge.activate(B, job)
        cursor = page.cursor
    assert page.complete
