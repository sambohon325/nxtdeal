"""
Test coverage for core/asset_management.py -- Finance's "Assets" (Collateral
Management) item: real Title status (reused verbatim from core/document_
workflows.py), real Lien tracking with a real paid-off-only release gate,
real dealer-entered Insurance with a real lapsed check, and a real Loan-to-
Value ratio blending a real book value with core/pricing_desk.py's SIMULATED
market value.

Ledger fixtures (FinanceContract/Vehicle/Lender + real COVERS/FUNDED_BY
relationships) drive the module's own real _get_loan/_linked_vehicle_id/
_linked_lender_id/_default_lienholder/_parse_date logic directly (all
reused, unmocked, from core.loan_servicing). The composed engines this
module reads from -- get_loan_status/get_loan_financials (core.loan_
servicing), get_title_status (core.document_workflows), get_market_pricing
(core.pricing_desk) -- are all top-level imports into this module's own
namespace, so each is monkeypatched directly on `am.*` to isolate this
module's own composition/aggregation logic from those (separately-scoped)
engines' own internals.

Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.asset_management as am

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import FINANCE_CONTRACT, VEHICLE, LENDER

import pytest


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _loan(loan_id, attributes=None):
    ledger.add_entity(Entity(id=loan_id, entity_type=FINANCE_CONTRACT, attributes=attributes or {}))
    return ledger.get_entity(loan_id)


def _vehicle(vehicle_id, price=None):
    attrs = {}
    if price is not None:
        attrs["Price"] = price
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vehicle_id)


def _lender(lender_id, name=None):
    attrs = {}
    if name is not None:
        attrs["Name"] = name
    ledger.add_entity(Entity(id=lender_id, entity_type=LENDER, attributes=attrs))
    return ledger.get_entity(lender_id)


def _covers(loan_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=loan_id, target_id=vehicle_id, relationship_type="COVERS"))


def _funded_by(loan_id, lender_id):
    ledger.add_relationship(Relationship(source_id=loan_id, target_id=lender_id, relationship_type="FUNDED_BY"))


class TestNowDateIso:

    def test_returns_isoformat_of_today(self, monkeypatch):
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))
        assert am._now_date_iso() == "2026-07-20"


class TestParseDate:

    def test_none_returns_none(self):
        assert am._parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert am._parse_date("") is None

    def test_valid_date_string(self):
        assert am._parse_date("2026-07-20") == date(2026, 7, 20)

    def test_datetime_string_sliced_to_date(self):
        assert am._parse_date("2026-07-20T10:30:00") == date(2026, 7, 20)

    def test_invalid_string_returns_none(self):
        assert am._parse_date("not-a-date") is None


class TestAllLoans:

    def test_returns_only_finance_contracts(self):
        _loan("FIN-1")
        _loan("FIN-2")
        _vehicle("VEH-1")

        result = am._all_loans()

        assert {loan.id for loan in result} == {"FIN-1", "FIN-2"}


class TestDefaultLienholder:

    def test_returns_linked_lender_name(self):
        loan = _loan("FIN-1")
        _lender("LEND-1", name="First National")
        _funded_by("FIN-1", "LEND-1")

        assert am._default_lienholder(loan) == "First National"

    def test_linked_lender_without_name_falls_back_to_default(self):
        loan = _loan("FIN-1")
        _lender("LEND-1")
        _funded_by("FIN-1", "LEND-1")

        assert am._default_lienholder(loan) == am._DEFAULT_LIENHOLDER

    def test_no_linked_lender_falls_back_to_default(self):
        loan = _loan("FIN-1")
        assert am._default_lienholder(loan) == am._DEFAULT_LIENHOLDER

    def test_linked_entity_not_a_lender_falls_back_to_default(self):
        loan = _loan("FIN-1")
        _vehicle("VEH-1")
        _funded_by("FIN-1", "VEH-1")

        assert am._default_lienholder(loan) == am._DEFAULT_LIENHOLDER


class TestGetLienStatus:

    def test_loan_not_found_returns_error(self):
        result = am.get_lien_status("FIN-999")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_no_stored_status_defaults_to_active(self):
        _loan("FIN-1")
        result = am.get_lien_status("FIN-1")
        assert result["lien_status"] == "active"
        assert result["is_stored_value"] is False

    def test_stored_released_status_returned(self):
        _loan("FIN-1", {"lien_status": "released"})
        result = am.get_lien_status("FIN-1")
        assert result["lien_status"] == "released"
        assert result["is_stored_value"] is True

    def test_stored_invalid_status_falls_back_to_active_but_flagged_stored(self):
        _loan("FIN-1", {"lien_status": "bogus"})
        result = am.get_lien_status("FIN-1")
        assert result["lien_status"] == "active"
        assert result["is_stored_value"] is True

    def test_stored_lienholder_name_used_when_present(self):
        _loan("FIN-1", {"lienholder_name": "Custom Bank"})
        result = am.get_lien_status("FIN-1")
        assert result["lienholder_name"] == "Custom Bank"

    def test_falls_back_to_default_lienholder_when_not_stored(self):
        _loan("FIN-1")
        result = am.get_lien_status("FIN-1")
        assert result["lienholder_name"] == am._DEFAULT_LIENHOLDER

    def test_released_at_and_by_returned_raw(self):
        _loan("FIN-1", {"lien_released_at": "2026-01-01", "lien_released_by": "EMP-1"})
        result = am.get_lien_status("FIN-1")
        assert result["lien_released_at"] == "2026-01-01"
        assert result["lien_released_by"] == "EMP-1"

    def test_missing_released_fields_are_none(self):
        _loan("FIN-1")
        result = am.get_lien_status("FIN-1")
        assert result["lien_released_at"] is None
        assert result["lien_released_by"] is None


class TestUpdateLienholder:

    def test_empty_lienholder_name_returns_error(self):
        result = am.update_lienholder("FIN-1", "", "EMP-1")
        assert result == {"error": "lienholder_name is required"}

    def test_none_lienholder_name_returns_error(self):
        result = am.update_lienholder("FIN-1", None, "EMP-1")
        assert result == {"error": "lienholder_name is required"}

    def test_loan_not_found_returns_error(self):
        result = am.update_lienholder("FIN-999", "New Bank", "EMP-1")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_valid_update_sets_lienholder_and_returns_status(self):
        _loan("FIN-1")
        result = am.update_lienholder("FIN-1", "New Bank", "EMP-1")
        assert result["lienholder_name"] == "New Bank"

    def test_history_accumulates_across_calls(self):
        _loan("FIN-1")
        am.update_lienholder("FIN-1", "Bank A", "EMP-1")
        am.update_lienholder("FIN-1", "Bank B", "EMP-2")

        loan = ledger.get_entity("FIN-1")
        history = loan.attributes["lienholder_history"]
        assert len(history) == 2
        assert history[0] == {"lienholder_name": "Bank A", "by": "EMP-1"}
        assert history[1] == {"lienholder_name": "Bank B", "by": "EMP-2"}


class TestReleaseLien:

    def test_loan_not_found_returns_error(self):
        result = am.release_lien("FIN-999", "EMP-1")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_already_released_returns_error(self):
        _loan("FIN-1", {"lien_status": "released"})
        result = am.release_lien("FIN-1", "EMP-1")
        assert result == {"error": "Lien is already released"}

    def test_loan_not_paid_off_returns_error(self, monkeypatch):
        _loan("FIN-1")
        monkeypatch.setattr(am, "get_loan_status", lambda loan_id: "active")

        result = am.release_lien("FIN-1", "EMP-1")

        assert "not paid off" in result["error"]
        assert "'active'" in result["error"]

    def test_paid_off_releases_lien(self, monkeypatch):
        _loan("FIN-1")
        monkeypatch.setattr(am, "get_loan_status", lambda loan_id: "paid_off")
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))

        result = am.release_lien("FIN-1", "EMP-1", reason="Loan paid off")

        assert result["lien_status"] == "released"
        loan = ledger.get_entity("FIN-1")
        assert loan.attributes["lien_released_at"] == "2026-07-20"
        assert loan.attributes["lien_released_by"] == "EMP-1"
        assert loan.attributes["lien_release_reason"] == "Loan paid off"


class TestGetInsuranceStatus:

    def test_loan_not_found_returns_error(self):
        result = am.get_insurance_status("FIN-999")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_no_insurance_on_file(self):
        _loan("FIN-1")
        result = am.get_insurance_status("FIN-1")
        assert result["on_file"] is False
        assert "No insurance information on file" in result["note"]

    def test_insurance_not_lapsed_when_expiration_in_future(self, monkeypatch):
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))
        _loan("FIN-1", {"insurance": {
            "carrier": "Acme Insurance", "policy_number": "P1",
            "expiration_date": "2030-01-01", "loss_payee_confirmed": True,
        }})

        result = am.get_insurance_status("FIN-1")

        assert result["on_file"] is True
        assert result["is_lapsed"] is False
        assert result["carrier"] == "Acme Insurance"

    def test_insurance_lapsed_when_expiration_in_past(self, monkeypatch):
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))
        _loan("FIN-1", {"insurance": {
            "carrier": "Acme Insurance", "policy_number": "P1",
            "expiration_date": "2020-01-01",
        }})

        result = am.get_insurance_status("FIN-1")

        assert result["is_lapsed"] is True

    def test_no_expiration_date_is_not_lapsed(self):
        _loan("FIN-1", {"insurance": {"carrier": "Acme Insurance", "policy_number": "P1"}})
        result = am.get_insurance_status("FIN-1")
        assert result["is_lapsed"] is False

    def test_loss_payee_confirmed_defaults_to_false(self):
        _loan("FIN-1", {"insurance": {"carrier": "Acme Insurance", "policy_number": "P1", "expiration_date": "2030-01-01"}})
        result = am.get_insurance_status("FIN-1")
        assert result["loss_payee_confirmed"] is False


class TestUpdateInsurance:

    def test_missing_carrier_returns_error(self):
        result = am.update_insurance("FIN-1", "", "P1", "2030-01-01", True, "EMP-1")
        assert "required" in result["error"]

    def test_missing_policy_number_returns_error(self):
        result = am.update_insurance("FIN-1", "Acme", "", "2030-01-01", True, "EMP-1")
        assert "required" in result["error"]

    def test_missing_expiration_date_returns_error(self):
        result = am.update_insurance("FIN-1", "Acme", "P1", "", True, "EMP-1")
        assert "required" in result["error"]

    def test_invalid_expiration_date_format_returns_error(self):
        result = am.update_insurance("FIN-1", "Acme", "P1", "not-a-date", True, "EMP-1")
        assert result == {"error": "expiration_date must be a valid date (YYYY-MM-DD)"}

    def test_loan_not_found_returns_error(self):
        result = am.update_insurance("FIN-999", "Acme", "P1", "2030-01-01", True, "EMP-1")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_valid_update_stores_all_fields(self, monkeypatch):
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))
        _loan("FIN-1")

        result = am.update_insurance("FIN-1", "Acme", "P1", "2030-01-01", True, "EMP-1")

        assert result["on_file"] is True
        assert result["carrier"] == "Acme"
        assert result["policy_number"] == "P1"
        assert result["loss_payee_confirmed"] is True
        assert result["updated_by"] == "EMP-1"
        assert result["updated_at"] == "2026-07-20"

    def test_loss_payee_confirmed_coerced_to_bool(self):
        _loan("FIN-1")
        result = am.update_insurance("FIN-1", "Acme", "P1", "2030-01-01", 0, "EMP-1")
        assert result["loss_payee_confirmed"] is False


class TestGetCollateralValuation:

    def test_loan_not_found_returns_error(self):
        result = am.get_collateral_valuation("FIN-999")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_no_linked_vehicle_returns_error(self):
        _loan("FIN-1")
        result = am.get_collateral_valuation("FIN-1")
        assert "no linked vehicle" in result["error"]

    def test_full_valuation_computes_ltv(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000, "basis": "simulated_market_data"})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000, "current_balance_basis": "real_payment_ledger"})

        result = am.get_collateral_valuation("FIN-1")

        assert result["book_value"] == 18000
        assert result["book_value_basis"] == "real_vehicle_price"
        assert result["market_value"] == 20000
        assert result["market_value_basis"] == "simulated_market_data"
        assert result["current_balance"] == 10000
        assert result["current_balance_basis"] == "real_payment_ledger"
        assert result["loan_to_value_pct"] == 50.0

    def test_ltv_none_when_market_value_zero(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 0})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000})

        result = am.get_collateral_valuation("FIN-1")

        assert result["loan_to_value_pct"] is None

    def test_ltv_none_when_current_balance_none(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": None})

        result = am.get_collateral_valuation("FIN-1")

        assert result["loan_to_value_pct"] is None

    def test_market_not_a_dict_treated_as_no_market_value(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: None)
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000})

        result = am.get_collateral_valuation("FIN-1")

        assert result["market_value"] is None
        assert result["market_value_basis"] is None
        assert result["loan_to_value_pct"] is None

    def test_financials_not_a_dict_treated_as_no_balance(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: None)

        result = am.get_collateral_valuation("FIN-1")

        assert result["current_balance"] is None
        assert result["current_balance_basis"] is None

    def test_vehicle_without_price_produces_zero_book_value(self, monkeypatch):
        # vehicle.attributes.get("Price") is missing -> _safe_float(None,
        # default=0.0) -> 0.0, not None: the module's own _safe_float
        # helper always coerces a missing/unparseable Price to a real
        # float default rather than propagating None.
        _loan("FIN-1")
        _vehicle("VEH-1")
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000})

        result = am.get_collateral_valuation("FIN-1")

        assert result["book_value"] == 0.0


class TestGetAssetSummary:

    def test_loan_not_found_returns_error(self):
        result = am.get_asset_summary("FIN-999")
        assert result == {"error": "Loan 'FIN-999' not found"}

    def test_composes_all_4_sections_with_linked_vehicle(self, monkeypatch):
        _loan("FIN-1")
        _vehicle("VEH-1", price=18000)
        _covers("FIN-1", "VEH-1")
        monkeypatch.setattr(am, "get_title_status", lambda vehicle_id: {"is_complete": True})
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000})

        result = am.get_asset_summary("FIN-1")

        assert result["title"] == {"is_complete": True}
        assert result["lien"]["lien_status"] == "active"
        assert result["insurance"]["on_file"] is False
        assert result["valuation"]["loan_to_value_pct"] == 50.0

    def test_no_linked_vehicle_reports_title_error_and_valuation_error(self):
        _loan("FIN-1")

        result = am.get_asset_summary("FIN-1")

        assert result["title"] == {"error": "No linked vehicle"}
        assert "no linked vehicle" in result["valuation"]["error"]


class TestGetAssetPortfolioDashboard:

    def test_empty_portfolio(self):
        result = am.get_asset_portfolio_dashboard()
        assert result["total_loans"] == 0
        assert result["total_book_value"] == 0.0
        assert result["average_loan_to_value_pct"] is None

    def test_aggregates_across_multiple_loans(self, monkeypatch):
        monkeypatch.setattr(am, "_today", lambda: date(2026, 7, 20))
        monkeypatch.setattr(am, "get_market_pricing", lambda vehicle_id: {"market_avg_price": 20000, "basis": "simulated_market_data"})
        monkeypatch.setattr(am, "get_loan_financials", lambda loan_id: {"current_balance": 10000, "current_balance_basis": "x"})

        def _title(vehicle_id):
            return {"is_complete": vehicle_id != "VEH-1"}
        monkeypatch.setattr(am, "get_title_status", _title)

        # Loan 1: missing title, no insurance, default (active) lien.
        _loan("FIN-1")
        _vehicle("VEH-1", price=15000)
        _covers("FIN-1", "VEH-1")

        # Loan 2: complete title, lapsed insurance, released lien.
        _loan("FIN-2", {"lien_status": "released", "insurance": {
            "carrier": "Acme", "policy_number": "P2", "expiration_date": "2020-01-01",
        }})
        _vehicle("VEH-2", price=25000)
        _covers("FIN-2", "VEH-2")

        # Loan 3: complete title, current insurance, default (active) lien, no price on file.
        _loan("FIN-3", {"insurance": {
            "carrier": "Acme", "policy_number": "P3", "expiration_date": "2030-01-01",
        }})
        _vehicle("VEH-3")
        _covers("FIN-3", "VEH-3")

        result = am.get_asset_portfolio_dashboard()

        assert result["total_loans"] == 3
        assert result["total_book_value"] == 40000.0
        assert result["total_market_value"] == 60000.0
        assert result["total_market_value_basis"] == "simulated_market_data"
        assert result["total_outstanding_balance"] == 30000.0
        assert result["average_loan_to_value_pct"] == 50.0
        assert result["missing_title_count"] == 1
        assert result["lapsed_insurance_count"] == 1
        assert result["no_insurance_on_file_count"] == 1
        assert result["active_lien_count"] == 2
        assert result["released_lien_count"] == 1

    def test_note_field_present(self):
        result = am.get_asset_portfolio_dashboard()
        assert "note" in result
        assert "SIMULATED" in result["note"]
