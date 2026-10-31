"""Reject oversized connector pages incrementally and fence expired read replies."""
from datetime import timedelta
import pytest
from core import dealer_bridge as b, bridge_sync as sync
from core.bridge_contracts import SourceRecord, SyncPage
from core.bridge_connectors import inspect_csv, parse_csv
from tests.test_bridge_sync import A, B, configured, state_of, isolated  # noqa: F401


def page(values):
    return SyncPage(tuple(SourceRecord("customers", str(index), "2026-01-01T00:00:00Z", value)
                          for index, value in enumerate(values)), "next", True)


def test_oversized_values_rejected_before_serialization_or_later_rows(monkeypatch):
    _, mapping, _, _ = configured()
    class MustNotVisit(str):
        def __str__(self):
            raise AssertionError("Oversized page processing continued")
    data = page([{"name": "x" * 100000}] * 11 + [{"name": MustNotVisit("sentinel")}])
    def no_writer(*args, **kwargs):
        raise AssertionError("Oversized page reached CSV serialization")
    monkeypatch.setattr(sync.csv, "DictWriter", no_writer)
    with pytest.raises(ValueError, match="staging limit"):
        sync.page_csv(data, b.get(mapping, "BridgeMapping"))


def test_excessive_column_count_is_rejected_before_iterating_dictionary():
    _, mapping, _, _ = configured()
    class Columns(dict):
        def items(self):
            raise AssertionError("Invalid column set was iterated")
    data = page([Columns({str(index): "value" for index in range(101)})])
    with pytest.raises(ValueError, match="source record"):
        sync.page_csv(data, b.get(mapping, "BridgeMapping"))


@pytest.mark.parametrize("value, count", [('"' * 100000, 6), ("é" * 100000, 6), ("😀" * 100000, 3)], ids=["quotes", "two-byte-text", "four-byte-text"])
def test_limit_counts_csv_escaping_and_utf8_bytes(value, count):
    _, mapping, _, _ = configured()
    with pytest.raises(ValueError, match="staging limit"):
        sync.page_csv(page([{"name": value}] * count), b.get(mapping, "BridgeMapping"))


def test_bounded_page_preserves_quoted_unicode_and_line_breaks():
    _, mapping, _, _ = configured()
    value = 'Zoë, "Example"\nSecond line 😀'
    content = sync.page_csv(page([{"name": value, "email": "example@example.invalid"}]), b.get(mapping, "BridgeMapping"))
    assert parse_csv(content)[1][0]["name"] == value


@pytest.mark.parametrize("values", [{"name": "\ud800"}, {"\ud800": "value"}, {"name\n": "value"}])
def test_invalid_text_contract_never_enters_staging(values):
    _, mapping, state, adapter = configured()
    adapter.page = page([values])
    assert sync.run_once(A, state)["status"] == "blocked"
    assert not any(entity.entity_type == "BridgeJob" for entity in sync.ledger.get_all().values())
    assert state_of(state)["last_error_code"] == "contract_review"


def test_csv_surrogate_rejected_without_echoing_data():
    with pytest.raises(ValueError, match="valid UTF-8 text") as failure:
        inspect_csv("name\nprivate\ud800\n")
    assert "private" not in str(failure.value)


@pytest.mark.parametrize("failure", [None, TimeoutError("late timeout")])
def test_expired_response_cannot_stage_or_change_retry_state(monkeypatch, failure):
    _, _, state, adapter = configured()
    current = sync.utcnow()
    monkeypatch.setattr(sync, "utcnow", lambda: current)
    adapter.failure = failure
    def expire():
        nonlocal current
        current += timedelta(seconds=sync.LEASE_SECONDS)
    adapter.during_read = expire
    assert sync.run_once(A, state) == {"status": "lease_lost"}
    assert state_of(state)["pending_job_id"] is None and state_of(state)["cursor"] is None
    assert state_of(state)["attempts"] == 0
    adapter.during_read = None; adapter.failure = None
    assert sync.run_once(B, state)["status"] == "awaiting_review"


def test_connector_receipt_records_collection_revision_and_transport():
    system, _, state, _ = configured()
    job = sync.run_once(A, state)["job_id"]
    b.validate(A, job); b.activate(B, job)
    receipt = b.import_report(A, job)["activation_receipt"]
    assert receipt["transport"] == "connector_read" and receipt["binding_revision"] == "test-1"
    assert receipt["sync_state_id"] == state and receipt["collection_mode"] == "sync"
    assert b.get(system, "BridgeSystem")["import_health"]["transport"] == "connector_read"
