"""Tests for core/general_ledger.py -- the real double-entry chart-of-accounts
engine blending real (Payment/funded-Deal sourced) postings with SIMULATED
(floorplan interest/payroll/overhead/other income) ones.

Uses the real ledger singleton for Deal/Vehicle/GlEntry entities (this module
reads core.dealeros.ledger directly for Deals/Vehicles), same reset-fixture
pattern as test_bank_reconciliation.py. _all_payments()/is_period_closed() are
imported bare names on the module -- monkeypatched directly, since Payment is a
separate entity this module never reads out of the ledger itself."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.general_ledger as gl
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import GL_ENTRY, DEAL, VEHICLE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_save(monkeypatch):
    monkeypatch.setattr(gl, "save_graph", lambda path: None)


@pytest.fixture(autouse=True)
def default_stubs(monkeypatch):
    monkeypatch.setattr(gl, "_all_payments", lambda: [])
    monkeypatch.setattr(gl, "is_period_closed", lambda entry_date: False)


def _payment(payment_id, status="approved", posting_status="posted", payment_date="2026-06-01", amount=500.0, interest=100.0, principal=400.0, loan_id="FIN-1"):
    return Entity(id=payment_id, entity_type="Payment", attributes={
        "status": status, "posting_status": posting_status, "payment_date": payment_date,
        "amount": amount, "interest_portion": interest, "principal_portion": principal, "loan_id": loan_id,
    })


def _deal(deal_id, status="funded", vehicle_id="VEH-1", updated_at="2026-06-01T10:00:00"):
    entity = Entity(id=deal_id, entity_type=DEAL, attributes={"status": status, "vehicle_id": vehicle_id, "updated_at": updated_at})
    ledger.add_entity(entity)
    return entity


def _vehicle(vehicle_id, price=20000.0, cost=17000.0):
    entity = Entity(id=vehicle_id, entity_type=VEHICLE, attributes={"Price": price, "Cost": cost})
    ledger.add_entity(entity)
    return entity


def _gl_entry(entry_id, entry_date, lines, account_type_row=None, source_reference=None):
    entity = Entity(id=entry_id, entity_type=GL_ENTRY, attributes={
        "entry_date": entry_date, "lines": lines, "source_reference": source_reference or entry_id, "description": "test entry",
    })
    ledger.add_entity(entity)
    return entity


# ---------------------------------------------------------------------------
# get_chart_of_accounts()
# ---------------------------------------------------------------------------


class TestGetChartOfAccounts:

    def test_returns_full_catalog_copy(self):
        result = gl.get_chart_of_accounts()

        assert result == gl.CHART_OF_ACCOUNTS
        assert result is not gl.CHART_OF_ACCOUNTS  # a copy, not the live list


# ---------------------------------------------------------------------------
# _create_entry()
# ---------------------------------------------------------------------------


class TestCreateEntry:

    def test_balanced_entry_succeeds(self):
        entry = gl._create_entry(
            entry_date="2026-06-01", description="Test", source="test", source_reference="test:1",
            created_by="EMP-1",
            lines=[{"account": "1000", "debit": 100.0, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100.0}],
        )

        assert entry.entity_type == GL_ENTRY
        assert entry.attributes["basis"] == "real"
        assert ledger.get_entity(entry.id) is entry

    def test_unbalanced_entry_raises(self):
        with pytest.raises(ValueError, match="Unbalanced entry"):
            gl._create_entry(
                entry_date="2026-06-01", description="Test", source="test", source_reference="test:1",
                created_by="EMP-1",
                lines=[{"account": "1000", "debit": 100.0, "credit": 0}, {"account": "4000", "debit": 0, "credit": 50.0}],
            )


# ---------------------------------------------------------------------------
# sync_real_entries() -- payments
# ---------------------------------------------------------------------------


class TestSyncRealEntriesPayments:

    def test_creates_entry_for_approved_posted_payment(self, monkeypatch):
        monkeypatch.setattr(gl, "_all_payments", lambda: [_payment("PMT-1")])

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 1
        entry = ledger.get_entity(result["synced_entry_ids"][0])
        assert entry.attributes["source"] == "loan_payment"
        assert entry.attributes["source_reference"] == "payment:PMT-1"
        lines = {l["account"]: l for l in entry.attributes["lines"]}
        assert lines["1000"]["debit"] == 500.0
        assert lines["4100"]["credit"] == 100.0
        assert lines["1100"]["credit"] == 400.0

    def test_non_approved_payment_skipped(self, monkeypatch):
        monkeypatch.setattr(gl, "_all_payments", lambda: [_payment("PMT-1", status="declined")])

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0

    def test_unposted_payment_skipped(self, monkeypatch):
        monkeypatch.setattr(gl, "_all_payments", lambda: [_payment("PMT-1", posting_status="unposted")])

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0

    def test_idempotent_by_source_reference(self, monkeypatch):
        monkeypatch.setattr(gl, "_all_payments", lambda: [_payment("PMT-1")])

        first = gl.sync_real_entries("EMP-1")
        second = gl.sync_real_entries("EMP-1")

        assert first["synced_count"] == 1
        assert second["synced_count"] == 0

    def test_closed_period_skipped(self, monkeypatch):
        monkeypatch.setattr(gl, "_all_payments", lambda: [_payment("PMT-1", payment_date="2026-06-01")])
        monkeypatch.setattr(gl, "is_period_closed", lambda entry_date: entry_date == "2026-06-01")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0
        assert result["skipped_closed_period"] == ["PMT-1"]


# ---------------------------------------------------------------------------
# sync_real_entries() -- deals
# ---------------------------------------------------------------------------


class TestSyncRealEntriesDeals:

    def test_creates_entry_with_cogs_for_funded_deal(self):
        _vehicle("VEH-1", price=20000.0, cost=17000.0)
        _deal("DEAL-1")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 1
        entry = ledger.get_entity(result["synced_entry_ids"][0])
        assert entry.attributes["source"] == "vehicle_sale"
        lines = {l["account"]: l for l in entry.attributes["lines"]}
        assert lines["1000"]["debit"] == 20000.0
        assert lines["4000"]["credit"] == 20000.0
        assert lines["5000"]["debit"] == 17000.0
        assert lines["1300"]["credit"] == 17000.0

    def test_zero_cost_omits_cogs_lines(self):
        _vehicle("VEH-1", price=20000.0, cost=0.0)
        _deal("DEAL-1")

        result = gl.sync_real_entries("EMP-1")

        entry = ledger.get_entity(result["synced_entry_ids"][0])
        accounts = {l["account"] for l in entry.attributes["lines"]}
        assert accounts == {"1000", "4000"}

    def test_non_funded_deal_skipped(self):
        _vehicle("VEH-1")
        _deal("DEAL-1", status="contract")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0

    def test_zero_price_skipped(self):
        _vehicle("VEH-1", price=0.0, cost=0.0)
        _deal("DEAL-1")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0

    def test_missing_vehicle_skipped(self):
        _deal("DEAL-1", vehicle_id="VEH-999")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0

    def test_idempotent_by_source_reference(self):
        _vehicle("VEH-1")
        _deal("DEAL-1")

        first = gl.sync_real_entries("EMP-1")
        second = gl.sync_real_entries("EMP-1")

        assert first["synced_count"] == 1
        assert second["synced_count"] == 0

    def test_closed_period_skipped(self, monkeypatch):
        _vehicle("VEH-1")
        _deal("DEAL-1", updated_at="2026-06-01T10:00:00")
        monkeypatch.setattr(gl, "is_period_closed", lambda entry_date: entry_date == "2026-06-01")

        result = gl.sync_real_entries("EMP-1")

        assert result["synced_count"] == 0
        assert result["skipped_closed_period"] == ["DEAL-1"]

    def test_save_graph_called_only_when_something_created(self, monkeypatch):
        calls = []
        monkeypatch.setattr(gl, "save_graph", lambda path: calls.append(path))

        gl.sync_real_entries("EMP-1")
        assert calls == []

        _vehicle("VEH-1")
        _deal("DEAL-1")
        gl.sync_real_entries("EMP-1")
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# generate_simulated_entries()
# ---------------------------------------------------------------------------


class TestGenerateSimulatedEntries:

    def test_closed_period_returns_error(self, monkeypatch):
        monkeypatch.setattr(gl, "is_period_closed", lambda entry_date: True)

        result = gl.generate_simulated_entries(2026, 6, "EMP-1")

        assert "closed" in result["error"]

    def test_success_creates_payroll_overhead_other_income(self):
        result = gl.generate_simulated_entries(2026, 6, "EMP-1", floorplan_exposure=0.0)

        assert result["period_key"] == "2026-06"
        # payroll + overhead + other_income always created (floorplan skipped since exposure=0)
        assert result["generated_count"] == 3
        sources = {ledger.get_entity(eid).attributes["source"] for eid in result["generated_entry_ids"]}
        assert sources == {"simulated_payroll", "simulated_overhead", "simulated_other_income"}

    def test_floorplan_exposure_adds_floorplan_interest_entry(self):
        result = gl.generate_simulated_entries(2026, 6, "EMP-1", floorplan_exposure=1_000_000.0)

        assert result["generated_count"] == 4
        sources = {ledger.get_entity(eid).attributes["source"] for eid in result["generated_entry_ids"]}
        assert "simulated_floorplan_interest" in sources

    def test_generated_entries_carry_simulated_basis(self):
        result = gl.generate_simulated_entries(2026, 6, "EMP-1")

        for eid in result["generated_entry_ids"]:
            entry = ledger.get_entity(eid)
            assert entry.attributes["basis"] == gl.SIMULATED_BASIS
            assert entry.attributes["disclaimer"]

    def test_already_generated_period_returns_error(self):
        gl.generate_simulated_entries(2026, 6, "EMP-1")

        result = gl.generate_simulated_entries(2026, 6, "EMP-1")

        assert "already exist" in result["error"]

    def test_deterministic_across_calls(self):
        gl.generate_simulated_entries(2026, 6, "EMP-1")
        first_payroll = next(
            ledger.get_entity(e.id).attributes["lines"][0]["debit"]
            for e in gl._all_entries() if e.attributes["source"] == "simulated_payroll"
        )

        ledger.reset()
        gl.generate_simulated_entries(2026, 6, "EMP-1")
        second_payroll = next(
            ledger.get_entity(e.id).attributes["lines"][0]["debit"]
            for e in gl._all_entries() if e.attributes["source"] == "simulated_payroll"
        )

        assert first_payroll == second_payroll


# ---------------------------------------------------------------------------
# delete_entry()
# ---------------------------------------------------------------------------


class TestDeleteEntry:

    def test_not_found(self):
        result = gl.delete_entry("GLE-999", "EMP-1")

        assert "not found" in result["error"]

    def test_closed_period_rejected(self, monkeypatch):
        entry = gl._create_entry(
            entry_date="2026-06-01", description="Test", source="test", source_reference="test:1", created_by="EMP-1",
            lines=[{"account": "1000", "debit": 100.0, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100.0}],
        )
        monkeypatch.setattr(gl, "is_period_closed", lambda entry_date: True)

        result = gl.delete_entry(entry.id, "EMP-1")

        assert "closed" in result["error"]
        assert ledger.get_entity(entry.id) is not None

    def test_success(self):
        entry = gl._create_entry(
            entry_date="2026-06-01", description="Test", source="test", source_reference="test:1", created_by="EMP-1",
            lines=[{"account": "1000", "debit": 100.0, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100.0}],
        )

        result = gl.delete_entry(entry.id, "EMP-1")

        assert result == {"deleted": entry.id, "deleted_by": "EMP-1"}
        assert ledger.get_entity(entry.id) is None


# ---------------------------------------------------------------------------
# get_general_ledger()
# ---------------------------------------------------------------------------


class TestGetGeneralLedger:

    def test_filters_by_account_number(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 100, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100}])
        _gl_entry("GLE-2", "2026-06-02", [{"account": "5000", "debit": 50, "credit": 0}, {"account": "1300", "debit": 0, "credit": 50}])

        result = gl.get_general_ledger(account_number="4000")

        assert result["count"] == 1
        assert result["entries"][0]["id"] == "GLE-1"

    def test_filters_by_date_range(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 100, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100}])
        _gl_entry("GLE-2", "2026-07-01", [{"account": "1000", "debit": 200, "credit": 0}, {"account": "4000", "debit": 0, "credit": 200}])

        result = gl.get_general_ledger(start_date="2026-07-01", end_date="2026-07-31")

        assert [e["id"] for e in result["entries"]] == ["GLE-2"]

    def test_sorted_and_limited(self):
        _gl_entry("GLE-2", "2026-06-05", [{"account": "1000", "debit": 100, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100}])
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 200, "credit": 0}, {"account": "4000", "debit": 0, "credit": 200}])

        result = gl.get_general_ledger(limit=1)

        assert result["count"] == 2  # count reflects the full matched set; limit only trims the returned entries list
        assert len(result["entries"]) == 1
        assert result["entries"][0]["id"] == "GLE-1"


# ---------------------------------------------------------------------------
# get_trial_balance()
# ---------------------------------------------------------------------------


class TestGetTrialBalance:

    def test_aggregates_and_balances(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 100, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100}])
        _gl_entry("GLE-2", "2026-06-02", [{"account": "5000", "debit": 50, "credit": 0}, {"account": "1000", "debit": 0, "credit": 50}])

        result = gl.get_trial_balance()

        assert result["total_debit"] == 150.0
        assert result["total_credit"] == 150.0
        assert result["balanced"] is True
        cash_row = next(r for r in result["rows"] if r["account_number"] == "1000")
        assert cash_row["debit"] == 100.0
        assert cash_row["credit"] == 50.0

    def test_date_range_filter(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 100, "credit": 0}, {"account": "4000", "debit": 0, "credit": 100}])
        _gl_entry("GLE-2", "2026-07-01", [{"account": "1000", "debit": 200, "credit": 0}, {"account": "4000", "debit": 0, "credit": 200}])

        result = gl.get_trial_balance(start_date="2026-07-01", end_date="2026-07-31")

        assert result["total_debit"] == 200.0


# ---------------------------------------------------------------------------
# get_income_statement()
# ---------------------------------------------------------------------------


class TestGetIncomeStatement:

    def test_computes_revenue_expense_net_income(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 1000, "credit": 0}, {"account": "4000", "debit": 0, "credit": 1000}])
        _gl_entry("GLE-2", "2026-06-02", [{"account": "5000", "debit": 300, "credit": 0}, {"account": "1000", "debit": 0, "credit": 300}])

        result = gl.get_income_statement()

        assert result["revenue"]["total"] == 1000.0
        assert result["expenses"]["total"] == 300.0
        assert result["net_income"] == 700.0

    def test_zero_net_lines_excluded(self):
        result = gl.get_income_statement()

        assert result["revenue"]["lines"] == []
        assert result["expenses"]["lines"] == []
        assert result["net_income"] == 0.0


# ---------------------------------------------------------------------------
# get_balance_sheet()
# ---------------------------------------------------------------------------


class TestGetBalanceSheet:

    def test_computes_assets_liabilities_equity(self):
        # Owner's equity contribution + cash asset, matching (assets = liabilities + equity)
        _gl_entry("GLE-1", "2026-06-01", [{"account": "1000", "debit": 5000, "credit": 0}, {"account": "3000", "debit": 0, "credit": 5000}])

        result = gl.get_balance_sheet()

        assert result["assets"]["total"] == 5000.0
        assert result["equity"]["owners_equity"] == 5000.0
        assert result["balances"] is True

    def test_liability_line_sign(self):
        _gl_entry("GLE-1", "2026-06-01", [{"account": "5100", "debit": 400, "credit": 0}, {"account": "2000", "debit": 0, "credit": 400}])

        result = gl.get_balance_sheet()

        liability_row = next(r for r in result["liabilities"]["lines"] if r["account"] == "Floorplan Payable")
        assert liability_row["balance"] == 400.0
        assert result["liabilities"]["total"] == 400.0


def test_general_ledger_offset_reaches_entries_beyond200():
    for i in range(205):
        _gl_entry(f"GLE-{i:04d}", "2026-06-01", [{"account":"1000","debit":1,"credit":0}])
    seen=[]
    for offset in range(0,205,4):
        page=gl.get_general_ledger(limit=4,offset=offset)
        assert page["count"]==205
        seen.extend(e["id"] for e in page["entries"])
    assert seen==[f"GLE-{i:04d}" for i in range(205)]
    assert gl.get_general_ledger(offset=205)["entries"]==[]
    assert len(gl.get_general_ledger(limit=999)["entries"])==200
    assert gl.get_general_ledger(offset=-1,limit=1)["entries"][0]["id"]=="GLE-0000"
