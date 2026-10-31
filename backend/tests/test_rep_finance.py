"""
Tests for MySales self-accounting (core/rep_finance.py + _api.py) — 2026-07-24. Run from
backend/ with `pytest`.

Covers: linking a bank returns deterministic simulated accounts (idempotent, flagged
simulated); setting/updating a budget (one per category) and spend aggregation from this
month's transactions; recording commissions + status totals; the overview combining
everything; and the rules-based advisor flagging an over-budget category and pending income.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import rep_finance as fin
from core import rep_finance_api as fin_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def test_link_bank_is_deterministic_idempotent_and_simulated():
    first = fin.link_bank("EMP-1")
    assert first["simulated"] is True
    assert first["already_linked"] is False
    assert len(first["accounts"]) == 2

    # Idempotent — linking again returns the same accounts, no duplicates.
    again = fin.link_bank("EMP-1")
    assert again["already_linked"] is True
    assert len(fin.list_accounts("EMP-1")) == 2

    # Deterministic — a fresh ledger for the same rep yields the same balances.
    balance = fin.list_accounts("EMP-1")[0]["balance"]
    ledger.reset()
    assert fin.link_bank("EMP-1")["accounts"][0]["balance"] == balance


def test_set_budget_upserts_and_tracks_spend():
    fin.link_bank("EMP-1")
    fin.set_budget("EMP-1", "Groceries", 300)
    fin.set_budget("EMP-1", "Groceries", 400)  # update, not duplicate
    budgets = fin.list_budgets("EMP-1")
    grocery = [b for b in budgets if b["category"] == "Groceries"]
    assert len(grocery) == 1
    assert grocery[0]["limit"] == 400
    # spent is aggregated from this month's transactions (>= 0), remaining computed.
    assert grocery[0]["spent"] >= 0
    assert grocery[0]["remaining"] == round(400 - grocery[0]["spent"], 2)


def test_set_budget_validation():
    assert "error" in fin.set_budget("EMP-1", "", 100)
    assert "error" in fin.set_budget("EMP-1", "Dining", "abc")
    assert "error" in fin.set_budget("EMP-1", "Dining", -5)


def test_commissions_record_and_totals():
    fin.record_commission("EMP-1", 500, status="paid", source="Deal DEAL-1")
    fin.record_commission("EMP-1", 250, status="pending")
    fin.record_commission("EMP-1", 300, status="projected")
    assert "error" in fin.record_commission("EMP-1", 100, status="bogus")
    assert "error" in fin.record_commission("EMP-1", "notnum")

    overview = fin.get_overview("EMP-1")
    totals = overview["commissions"]["totals"]
    assert totals["paid"] == 500
    assert totals["pending"] == 250
    assert totals["projected"] == 300


def test_overview_shape_and_cash_total():
    fin.link_bank("EMP-1")
    overview = fin.get_overview("EMP-1")
    assert overview["linked"] is True
    assert overview["provider_live"] is False
    assert overview["cash_total"] == round(sum(a["balance"] for a in overview["accounts"]), 2)
    assert isinstance(overview["advisor"], list)


@pytest.mark.parametrize("day", [1, 15, 31])
def test_advisor_flags_over_budget_and_pending_income(monkeypatch, day):
    # The simulated account may have no spend this month on its first day.
    # Supply a known transaction and clock instead of depending on random offsets.
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, day, 12, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    monkeypatch.setattr(fin, "datetime", FixedDatetime)
    fin.link_bank("EMP-1")
    account = fin._account_entities("EMP-1")[0]
    account.attributes["transactions"] = [{
        "date": f"2026-10-{day:02d}", "name": "Test purchase",
        "category": "Groceries", "amount": -20,
    }]
    fin.set_budget("EMP-1", "Groceries", 1)
    fin.record_commission("EMP-1", 400, status="pending")

    insights = fin.advisor("EMP-1")
    titles = " ".join(i["title"].lower() for i in insights)
    assert any(i["type"] == "warning" for i in insights)
    assert "over budget" in titles
    assert "commission" in titles


def test_api_wrappers_shape():
    fin_api.link_bank_api("EMP-1")
    assert "budgets" in fin_api.list_budgets_api("EMP-1")
    assert "commissions" in fin_api.list_commissions_api("EMP-1")
    assert "insights" in fin_api.advisor_api("EMP-1")
    assert fin_api.get_overview_api("EMP-1")["linked"] is True



def test_registered_provider_does_not_turn_demo_data_into_live_banking(monkeypatch):
    monkeypatch.setattr(fin.integrations_registry, "is_live", lambda capability: True)
    events = []
    monkeypatch.setattr(fin.audit_log, "record", lambda **event: events.append(event))
    result = fin.link_bank("EMP-DEMO")
    assert result["simulated"] is True
    assert result["connection_verified"] is False
    assert all(account["source"] == "simulated" for account in result["accounts"])
    assert events[0]["details"]["simulated"] is True
    assert "simulated" in events[0]["summary"]
    overview = fin.get_overview("EMP-DEMO")
    assert overview["provider_available"] is True
    assert overview["provider_live"] is False
    assert overview["connection_verified"] is False
    again = fin.link_bank("EMP-DEMO")
    assert again["already_linked"] is True
    assert again["simulated"] is True
    assert again["connection_verified"] is False
    assert len(events) == 1


def test_legacy_source_is_not_rewritten_or_treated_as_verified(monkeypatch):
    fin.link_bank("EMP-LEGACY")
    account = fin._account_entities("EMP-LEGACY")[0]
    account.attributes["source"] = "plaid"
    monkeypatch.setattr(fin.integrations_registry, "is_live", lambda capability: True)
    result = fin.link_bank("EMP-LEGACY")
    assert result["already_linked"] is True
    assert result["connection_verified"] is False
    assert account.attributes["source"] == "plaid"
    assert fin.get_overview("EMP-LEGACY")["provider_live"] is False
