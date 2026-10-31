"""Tests for core/bank_reconciliation.py -- simulated bank feed generation, real
amount+date matching algorithm, and the confirm/review actions.

Uses the real ledger singleton (reset before/after every test, same pattern as
test_ai_tools.py's fresh_ledger fixture) since this module reads/writes real
Entity objects directly via core.dealeros.ledger, not through a mockable *_api
layer. save_graph is monkeypatched to a no-op in every test -- the conftest.py
isolated temp storage dir makes a real write harmless, but there's no need to
touch disk at all for a pure logic test."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.bank_reconciliation as br
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import BANK_TRANSACTION, GL_ENTRY


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_save(monkeypatch):
    monkeypatch.setattr(br, "save_graph", lambda path: None)


def _gl_entry(entry_id, entry_date, cash_amount, description="GL entry"):
    if cash_amount >= 0:
        line = {"account": "1000", "debit": cash_amount, "credit": 0}
    else:
        line = {"account": "1000", "debit": 0, "credit": -cash_amount}
    entity = Entity(
        id=entry_id,
        entity_type=GL_ENTRY,
        attributes={"entry_date": entry_date, "description": description, "lines": [line, {"account": "4000", "debit": 0, "credit": 0}]},
    )
    ledger.add_entity(entity)
    return entity


def _bank_txn(txn_id, posted_date, amount, status="unmatched", matched_gl_entry_id=None, source_reference=None, txn_type=None):
    entity = Entity(
        id=txn_id,
        entity_type=BANK_TRANSACTION,
        attributes={
            "posted_date": posted_date,
            "amount": amount,
            "type": txn_type or ("deposit" if amount >= 0 else "withdrawal"),
            "description": "Bank txn",
            "source_reference": source_reference or f"gl:{txn_id}",
            "matched_gl_entry_id": matched_gl_entry_id,
            "status": status,
        },
    )
    ledger.add_entity(entity)
    return entity


# ---------------------------------------------------------------------------
# _cash_amount()
# ---------------------------------------------------------------------------


class TestCashAmount:

    def test_debit_line_is_positive(self):
        entry = Entity(id="GLE-1", entity_type=GL_ENTRY, attributes={"lines": [{"account": "1000", "debit": 500.0, "credit": 0}]})

        assert br._cash_amount(entry) == 500.0

    def test_credit_line_is_negative(self):
        entry = Entity(id="GLE-1", entity_type=GL_ENTRY, attributes={"lines": [{"account": "1000", "debit": 0, "credit": 200.0}]})

        assert br._cash_amount(entry) == -200.0

    def test_ignores_non_cash_lines(self):
        entry = Entity(id="GLE-1", entity_type=GL_ENTRY, attributes={"lines": [
            {"account": "4000", "debit": 0, "credit": 999.0},
            {"account": "1000", "debit": 50.0, "credit": 0},
        ]})

        assert br._cash_amount(entry) == 50.0

    def test_no_lines(self):
        entry = Entity(id="GLE-1", entity_type=GL_ENTRY, attributes={})

        assert br._cash_amount(entry) == 0.0


# ---------------------------------------------------------------------------
# generate_simulated_bank_feed()
# ---------------------------------------------------------------------------


class TestGenerateSimulatedBankFeed:

    def test_creates_one_transaction_per_cash_gl_entry(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        _gl_entry("GLE-2", "2026-06-05", -300.0)
        _gl_entry("GLE-3", "2026-06-10", 0.0)  # no cash movement, skipped entirely

        result = br.generate_simulated_bank_feed("EMP-1")

        # 2 real deposit/withdrawal txns + at least 1 bank-only fee for the month
        assert result["generated_count"] >= 2
        created_txns = [ledger.get_entity(tid) for tid in result["generated_transaction_ids"]]
        gl_sourced = [t for t in created_txns if t.attributes["source_reference"].startswith("gl:")]
        assert len(gl_sourced) == 2
        amounts = sorted(t.attributes["amount"] for t in gl_sourced)
        assert amounts == [-300.0, 1000.0]
        for t in gl_sourced:
            assert t.attributes["basis"] == br.SIMULATED_BASIS
            assert t.attributes["created_by"] == "EMP-1"
            assert t.attributes["status"] == "unmatched"

    def test_idempotent_by_source_reference(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)

        first = br.generate_simulated_bank_feed("EMP-1")
        second = br.generate_simulated_bank_feed("EMP-1")

        assert first["generated_count"] > 0
        assert second["generated_count"] == 0

    def test_respects_date_range(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        _gl_entry("GLE-2", "2026-07-01", 500.0)

        result = br.generate_simulated_bank_feed("EMP-1", start_date="2026-07-01", end_date="2026-07-31")

        created_txns = [ledger.get_entity(tid) for tid in result["generated_transaction_ids"]]
        gl_sourced = [t for t in created_txns if t.attributes["source_reference"] == "gl:GLE-2"]
        assert len(gl_sourced) == 1
        excluded = [t for t in created_txns if t.attributes["source_reference"] == "gl:GLE-1"]
        assert len(excluded) == 0

    def test_bank_only_fee_item_is_negative_withdrawal(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)

        result = br.generate_simulated_bank_feed("EMP-1")

        created_txns = [ledger.get_entity(tid) for tid in result["generated_transaction_ids"]]
        fee_txns = [t for t in created_txns if t.attributes["source_reference"].startswith("bank_fee:")]
        assert len(fee_txns) == 1
        assert fee_txns[0].attributes["amount"] < 0
        assert fee_txns[0].attributes["type"] == "withdrawal"

    def test_no_cash_entries_creates_nothing(self):
        result = br.generate_simulated_bank_feed("EMP-1")

        assert result == {"generated_count": 0, "generated_transaction_ids": []}

    def test_save_graph_called_only_when_something_created(self, monkeypatch):
        calls = []
        monkeypatch.setattr(br, "save_graph", lambda path: calls.append(path))

        br.generate_simulated_bank_feed("EMP-1")
        assert calls == []

        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        br.generate_simulated_bank_feed("EMP-1")
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# _auto_match()
# ---------------------------------------------------------------------------


class TestAutoMatch:

    def test_matches_exact_amount_within_window(self):
        txn = _bank_txn("BTXN-1", "2026-06-03", 500.0)
        entry = _gl_entry("GLE-1", "2026-06-01", 500.0)

        matches = br._auto_match([txn], [entry])

        assert matches == [(txn, entry)]

    def test_amount_outside_tolerance_does_not_match(self):
        txn = _bank_txn("BTXN-1", "2026-06-01", 500.10)
        entry = _gl_entry("GLE-1", "2026-06-01", 500.0)

        assert br._auto_match([txn], [entry]) == []

    def test_date_outside_window_does_not_match(self):
        txn = _bank_txn("BTXN-1", "2026-06-10", 500.0)
        entry = _gl_entry("GLE-1", "2026-06-01", 500.0)

        assert br._auto_match([txn], [entry]) == []

    def test_already_matched_transaction_skipped(self):
        txn = _bank_txn("BTXN-1", "2026-06-01", 500.0, matched_gl_entry_id="GLE-99")
        entry = _gl_entry("GLE-1", "2026-06-01", 500.0)

        assert br._auto_match([txn], [entry]) == []

    def test_closest_date_wins_on_tie(self):
        txn = _bank_txn("BTXN-1", "2026-06-03", 500.0)
        far_entry = _gl_entry("GLE-1", "2026-06-01", 500.0)
        close_entry = _gl_entry("GLE-2", "2026-06-02", 500.0)

        matches = br._auto_match([txn], [far_entry, close_entry])

        assert matches == [(txn, close_entry)]

    def test_matched_gl_entry_only_used_once(self):
        txn1 = _bank_txn("BTXN-1", "2026-06-01", 500.0)
        txn2 = _bank_txn("BTXN-2", "2026-06-02", 500.0)
        entry = _gl_entry("GLE-1", "2026-06-01", 500.0)

        matches = br._auto_match([txn1, txn2], [entry])

        assert len(matches) == 1


# ---------------------------------------------------------------------------
# get_reconciliation_status()
# ---------------------------------------------------------------------------


class TestGetReconciliationStatus:

    def test_full_composition(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        _gl_entry("GLE-2", "2026-06-05", -200.0)
        _bank_txn("BTXN-1", "2026-06-02", 1000.0)  # will auto-match GLE-1
        _bank_txn("BTXN-2", "2026-06-06", -50.0)  # unmatched, no GL counterpart (e.g. fee)

        result = br.get_reconciliation_status()

        assert result["bank_account"] == br.SIMULATED_BANK_ACCOUNT
        assert result["auto_matched_count"] == 1
        assert result["auto_matches"][0]["transaction_id"] == "BTXN-1"
        assert result["auto_matches"][0]["gl_entry_id"] == "GLE-1"

        unmatched_txn_ids = {t["id"] for t in result["unmatched_transactions"]}
        assert unmatched_txn_ids == {"BTXN-2"}

        unmatched_gl_ids = {e["id"] for e in result["unmatched_gl_entries"]}
        assert unmatched_gl_ids == {"GLE-2"}

        expected_book = round(br.SIMULATED_BANK_ACCOUNT["starting_balance"] + 1000.0 - 200.0, 2)
        expected_bank = round(br.SIMULATED_BANK_ACCOUNT["starting_balance"] + 1000.0 - 50.0, 2)
        assert result["book_balance"] == expected_book
        assert result["bank_balance"] == expected_bank
        assert result["difference"] == round(expected_book - expected_bank, 2)

    def test_already_matched_transaction_excludes_its_gl_entry_from_unmatched(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        _bank_txn("BTXN-1", "2026-06-01", 1000.0, status="matched", matched_gl_entry_id="GLE-1")

        result = br.get_reconciliation_status()

        assert result["auto_matched_count"] == 0
        assert result["unmatched_gl_entries"] == []
        assert result["unmatched_transactions"] == []

    def test_already_reconciled_count(self):
        _bank_txn("BTXN-1", "2026-06-01", 100.0, status="reviewed")
        _bank_txn("BTXN-2", "2026-06-01", 200.0, status="unmatched")

        result = br.get_reconciliation_status()

        assert result["already_reconciled_count"] == 1

    def test_date_range_filters(self):
        _gl_entry("GLE-1", "2026-06-01", 1000.0)
        _gl_entry("GLE-2", "2026-07-01", 500.0)
        _bank_txn("BTXN-1", "2026-06-01", 1000.0)
        _bank_txn("BTXN-2", "2026-07-01", 500.0)

        result = br.get_reconciliation_status(start_date="2026-07-01", end_date="2026-07-31")

        all_txn_ids = {t["id"] for t in result["unmatched_transactions"]} | {m["transaction_id"] for m in result["auto_matches"]}
        assert all_txn_ids == {"BTXN-2"}


# ---------------------------------------------------------------------------
# confirm_match()
# ---------------------------------------------------------------------------


class TestConfirmMatch:

    def test_transaction_not_found(self):
        _gl_entry("GLE-1", "2026-06-01", 500.0)

        result = br.confirm_match("BTXN-999", "GLE-1", "EMP-1")

        assert "not found" in result["error"]

    def test_gl_entry_not_found(self):
        _bank_txn("BTXN-1", "2026-06-01", 500.0)

        result = br.confirm_match("BTXN-1", "GLE-999", "EMP-1")

        assert "not found" in result["error"]

    def test_already_matched(self):
        _bank_txn("BTXN-1", "2026-06-01", 500.0, matched_gl_entry_id="GLE-99")
        _gl_entry("GLE-1", "2026-06-01", 500.0)

        result = br.confirm_match("BTXN-1", "GLE-1", "EMP-1")

        assert "already matched" in result["error"]

    def test_amount_mismatch(self):
        _bank_txn("BTXN-1", "2026-06-01", 500.0)
        _gl_entry("GLE-1", "2026-06-01", 400.0)

        result = br.confirm_match("BTXN-1", "GLE-1", "EMP-1")

        assert "Amounts don't match" in result["error"]

    def test_success(self):
        _bank_txn("BTXN-1", "2026-06-01", 500.0)
        _gl_entry("GLE-1", "2026-06-01", 500.0)

        result = br.confirm_match("BTXN-1", "GLE-1", "EMP-1")

        assert result["matched_gl_entry_id"] == "GLE-1"
        assert result["status"] == "matched"
        assert result["matched_by"] == "EMP-1"
        assert result["matched_at"] is not None


# ---------------------------------------------------------------------------
# mark_transaction_reviewed()
# ---------------------------------------------------------------------------


class TestMarkTransactionReviewed:

    def test_not_found(self):
        result = br.mark_transaction_reviewed("BTXN-999", "EMP-1")

        assert "not found" in result["error"]

    def test_success(self):
        _bank_txn("BTXN-1", "2026-06-01", 500.0)

        result = br.mark_transaction_reviewed("BTXN-1", "EMP-1", note="Looks right")

        assert result["status"] == "reviewed"
        assert result["reviewed_by"] == "EMP-1"
        assert result["review_note"] == "Looks right"
        assert result["reviewed_at"] is not None


# ---------------------------------------------------------------------------
# list_transactions()
# ---------------------------------------------------------------------------


class TestListTransactions:

    def test_filters_by_status(self):
        _bank_txn("BTXN-1", "2026-06-01", 100.0, status="unmatched")
        _bank_txn("BTXN-2", "2026-06-02", 200.0, status="reviewed")

        result = br.list_transactions(status="reviewed")

        assert [t["id"] for t in result] == ["BTXN-2"]

    def test_filters_by_date_range(self):
        _bank_txn("BTXN-1", "2026-06-01", 100.0)
        _bank_txn("BTXN-2", "2026-07-01", 200.0)

        result = br.list_transactions(start_date="2026-07-01", end_date="2026-07-31")

        assert [t["id"] for t in result] == ["BTXN-2"]

    def test_sorted_by_posted_date(self):
        _bank_txn("BTXN-1", "2026-06-05", 100.0)
        _bank_txn("BTXN-2", "2026-06-01", 200.0)

        result = br.list_transactions()

        assert [t["id"] for t in result] == ["BTXN-2", "BTXN-1"]
