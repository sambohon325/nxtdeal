"""
Tests for core/loan_servicing.py + core/loan_servicing_api.py -- Finance's Portfolio /
Loan Management screen (session 111 follow-up, "Finance Retail Lending Platform").

Covers: the real fixed-rate amortization engine, the loan_status computed-default
convention (active/paid_off/repossessed/charged_off), the real-vs-SIMULATED payment
status blend (core/payments.py's real ledger preferred over this module's own
deterministic SIMULATED estimate the moment real payments exist for a loan), borrower/
vehicle/lender composition (including the honest "not on file" employment/reference
gaps), the composed loan timeline, the portfolio dashboard's real aggregate math, and
the ACL layer (ADMIN/OPERATIONS/FINANCE only, matching core/payments_api.py's own
uniform gate).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT, LENDER, CREDIT_APPLICATION
from core import loan_servicing
from core import loan_servicing_api
from core import payments
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(loan_servicing, "save_graph", lambda filepath: None)
    monkeypatch.setattr(payments, "save_graph", lambda filepath: None)


_STAFF_ROLES = (ADMIN, OPERATIONS, FINANCE)
_DENIED_ROLES = (SALES, MARKETING, SERVICE)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    ))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", make="Honda", model="Civic", year="2025"):
    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year},
    ))
    return vehicle_id


def _add_lender(lender_id="LENDER-1", name="First Auto Finance"):
    ledger.add_entity(Entity(
        id=lender_id,
        entity_type=LENDER,
        attributes={"Name": name},
    ))
    return lender_id


def _add_loan(
    loan_id="FIN-1",
    amount_financed=12000.0,
    apr=9.0,
    term_months=48,
    monthly_payment=298.62,
    contract_date="2026-01-01",
    finance_number="FIN-1",
    link_customer="CUST-1",
    link_vehicle="VEH-1",
    link_lender=None,
    extra_attributes=None,
):
    attrs = {
        "FinanceNumber": finance_number,
        "AmountFinanced": amount_financed,
        "APR": apr,
        "TermMonths": term_months,
        "MonthlyPayment": monthly_payment,
        "ContractDate": contract_date,
    }
    if extra_attributes:
        attrs.update(extra_attributes)
    ledger.add_entity(Entity(id=loan_id, entity_type=FINANCE_CONTRACT, attributes=attrs))
    if link_customer:
        ledger.add_relationship(Relationship(
            source_id=link_customer, target_id=loan_id, relationship_type="FINANCED_BY",
        ))
    if link_vehicle:
        ledger.add_relationship(Relationship(
            source_id=loan_id, target_id=link_vehicle, relationship_type="COVERS",
        ))
    if link_lender:
        ledger.add_relationship(Relationship(
            source_id=loan_id, target_id=link_lender, relationship_type="FUNDED_BY",
        ))
    return loan_id


def _full_loan_setup(**loan_kwargs):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    return _add_loan(**loan_kwargs)


def _add_credit_application(app_id="CAPP-1", customer_id="CUST-1", employer_name="Acme Co",
                             employment_status="employed", monthly_income=5000.0,
                             created_at="2026-01-01T00:00:00+00:00"):
    ledger.add_entity(Entity(
        id=app_id,
        entity_type=CREDIT_APPLICATION,
        attributes={
            "customer_id": customer_id,
            "status": "approved",
            "created_at": created_at,
            "applicant": {
                "employer_name": employer_name,
                "employment_status": employment_status,
                "monthly_income": monthly_income,
            },
        },
    ))
    return app_id


# ---------------------------------------------------------------------------
# compute_amortization_schedule()
# ---------------------------------------------------------------------------

def test_compute_amortization_schedule_empty_for_nonpositive_principal():
    assert loan_servicing.compute_amortization_schedule(0, 9.0, 48) == []
    assert loan_servicing.compute_amortization_schedule(-100, 9.0, 48) == []


def test_compute_amortization_schedule_empty_for_nonpositive_term():
    assert loan_servicing.compute_amortization_schedule(12000, 9.0, 0) == []
    assert loan_servicing.compute_amortization_schedule(12000, 9.0, -1) == []


def test_compute_amortization_schedule_zero_apr_is_flat_principal_split():
    schedule = loan_servicing.compute_amortization_schedule(12000.0, 0.0, 12)
    assert len(schedule) == 12
    for row in schedule:
        assert row["interest_portion"] == 0.0
    # every period pays down an even share of principal
    assert abs(schedule[0]["principal_portion"] - 1000.0) < 0.01
    assert schedule[-1]["balance"] == 0.0


def test_compute_amortization_schedule_standard_case_real_interest_math():
    schedule = loan_servicing.compute_amortization_schedule(12000.0, 9.0, 48)
    assert len(schedule) == 48
    first = schedule[0]
    # a real, non-zero interest component on period 1
    assert first["interest_portion"] > 0
    assert first["principal_portion"] > 0
    assert first["payment"] > 0
    # payment amounts should be roughly constant across periods (standard amortization)
    assert abs(first["payment"] - schedule[1]["payment"]) < 0.02


def test_compute_amortization_schedule_final_period_lands_exactly_on_zero_balance():
    schedule = loan_servicing.compute_amortization_schedule(12000.0, 9.0, 48)
    assert schedule[-1]["balance"] == 0.0


def test_compute_amortization_schedule_period_numbers_are_sequential():
    schedule = loan_servicing.compute_amortization_schedule(5000.0, 6.5, 6)
    assert [row["period"] for row in schedule] == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# get_loan_financials()
# ---------------------------------------------------------------------------

def test_get_loan_financials_unknown_loan_errors():
    result = loan_servicing.get_loan_financials("FIN-999")
    assert "error" in result


def test_get_loan_financials_zero_elapsed_balance_equals_principal(monkeypatch):
    _full_loan_setup(contract_date="2026-06-01")
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 6, 1))
    result = loan_servicing.get_loan_financials("FIN-1")
    assert result["months_elapsed"] == 0
    assert result["current_balance"] == result["original_amount"]
    assert result["current_balance_basis"] == "schedule_implied_estimate"


def test_get_loan_financials_partway_through_schedule_real_math(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", amount_financed=12000.0, apr=9.0, term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    result = loan_servicing.get_loan_financials("FIN-1")
    assert result["months_elapsed"] == 6
    assert result["terms_remaining"] == 42
    assert result["current_balance"] < 12000.0
    assert result["current_balance"] > 0
    assert result["current_balance_basis"] == "schedule_implied_estimate"
    assert len(result["payment_schedule"]) == 48


def test_get_loan_financials_switches_basis_once_real_payments_exist(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", amount_financed=12000.0, apr=9.0, term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    # This test covers ledger selection, not the ID-seeded simulated gateway.
    # Pin approval so earlier suites cannot change its outcome via the PMT counter.
    monkeypatch.setattr(payments, "_simulate_gateway_result", lambda *args: {"approved": True, "decline_reason": None})

    # before any real payment, basis is the schedule-implied estimate
    before = loan_servicing.get_loan_financials("FIN-1")
    assert before["current_balance_basis"] == "schedule_implied_estimate"

    payments.record_payment("FIN-1", 298.62, "ach", recorded_by="EMP-1", payment_date="2026-06-15")

    after = loan_servicing.get_loan_financials("FIN-1")
    assert after["current_balance_basis"] == "real_payment_ledger"
    assert loan_servicing.get_portfolio_dashboard()["total_outstanding_balance"] == after["current_balance"]


def test_get_loan_financials_missing_contract_date_handled():
    _full_loan_setup(contract_date=None)
    result = loan_servicing.get_loan_financials("FIN-1")
    assert "error" not in result


# ---------------------------------------------------------------------------
# get_loan_status() / set_loan_status()
# ---------------------------------------------------------------------------

def test_get_loan_status_unknown_loan_errors():
    result = loan_servicing.get_loan_status("FIN-999")
    assert isinstance(result, dict)
    assert "error" in result


def test_get_loan_status_computed_default_active_when_not_fully_elapsed(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    status = loan_servicing.get_loan_status("FIN-1")
    assert status == "active"


def test_get_loan_status_computed_default_paid_off_when_fully_elapsed(monkeypatch):
    _full_loan_setup(contract_date="2020-01-01", term_months=12)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 1, 1))
    status = loan_servicing.get_loan_status("FIN-1")
    assert status == "paid_off"


def test_get_loan_status_stored_value_takes_precedence(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1", "Test repo")
    status = loan_servicing.get_loan_status("FIN-1")
    assert status == "repossessed"


def test_set_loan_status_rejects_bad_status():
    _full_loan_setup()
    result = loan_servicing.set_loan_status("FIN-1", "bogus_status", "EMP-1")
    assert isinstance(result, dict)
    assert "error" in result


def test_set_loan_status_rejects_unknown_loan():
    result = loan_servicing.set_loan_status("FIN-999", "active", "EMP-1")
    assert isinstance(result, dict)
    assert "error" in result


def test_set_loan_status_bad_status_checked_before_unknown_loan():
    # validation order: an unknown status is rejected even on an unknown loan id,
    # confirming status validity is checked first
    result = loan_servicing.set_loan_status("FIN-999", "bogus_status", "EMP-1")
    assert isinstance(result, dict)
    assert "error" in result


def test_set_loan_status_success_returns_entity_and_appends_history():
    _full_loan_setup()
    result = loan_servicing.set_loan_status("FIN-1", "charged_off", "EMP-1", "written off")
    assert not isinstance(result, dict)
    assert result.attributes["loan_status"] == "charged_off"
    history = result.attributes.get("loan_status_history", [])
    assert len(history) == 1
    assert history[0]["status"] == "charged_off"
    assert history[0]["set_by"] == "EMP-1"
    assert history[0]["reason"] == "written off"


def test_set_loan_status_multiple_calls_append_full_history():
    _full_loan_setup()
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1", "first")
    result = loan_servicing.set_loan_status("FIN-1", "charged_off", "EMP-2", "second")
    history = result.attributes.get("loan_status_history", [])
    assert len(history) == 2
    assert history[0]["status"] == "repossessed"
    assert history[1]["status"] == "charged_off"


@pytest.mark.parametrize("status", loan_servicing.LOAN_STATUSES)
def test_set_loan_status_accepts_every_valid_status(status):
    _full_loan_setup()
    result = loan_servicing.set_loan_status("FIN-1", status, "EMP-1")
    assert not isinstance(result, dict)
    assert result.attributes["loan_status"] == status


# ---------------------------------------------------------------------------
# get_simulated_payment_status()
# ---------------------------------------------------------------------------

def test_get_simulated_payment_status_unknown_loan_errors():
    result = loan_servicing.get_simulated_payment_status("FIN-999")
    assert "error" in result


def test_get_simulated_payment_status_zero_elapsed_forces_current(monkeypatch):
    _full_loan_setup(contract_date="2026-07-01")
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    result = loan_servicing.get_simulated_payment_status("FIN-1")
    assert result["bucket"] == "current"
    assert result["basis"] == loan_servicing.SIMULATED_BASIS
    assert result["amount_past_due"] == 0


def test_get_simulated_payment_status_deterministic_per_loan_id(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    first = loan_servicing.get_simulated_payment_status("FIN-1")
    second = loan_servicing.get_simulated_payment_status("FIN-1")
    assert first["bucket"] == second["bucket"]
    assert first["days_past_due"] == second["days_past_due"]


def test_get_simulated_payment_status_stored_status_short_circuits_bucket(monkeypatch):
    _full_loan_setup(contract_date="2026-07-01")
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    # even at zero elapsed months, a stored repossessed status wins
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1")
    result = loan_servicing.get_simulated_payment_status("FIN-1")
    assert result["bucket"] == "repossessed"


def test_get_simulated_payment_status_paid_off_maps_to_current_bucket(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    loan_servicing.set_loan_status("FIN-1", "paid_off", "EMP-1")
    result = loan_servicing.get_simulated_payment_status("FIN-1")
    assert result["bucket"] == "current"


def test_get_simulated_payment_status_prefers_real_data_once_payments_exist(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))

    before = loan_servicing.get_simulated_payment_status("FIN-1")
    assert before["basis"] == loan_servicing.SIMULATED_BASIS

    payments.record_payment("FIN-1", 298.62, "ach", "2026-06-15", "EMP-1")

    after = loan_servicing.get_simulated_payment_status("FIN-1")
    assert after["basis"] != loan_servicing.SIMULATED_BASIS


# ---------------------------------------------------------------------------
# get_loan_timeline()
# ---------------------------------------------------------------------------

def test_get_loan_timeline_unknown_loan_errors():
    result = loan_servicing.get_loan_timeline("FIN-999")
    assert "error" in result


def test_get_loan_timeline_includes_originated_and_funded_events():
    _full_loan_setup(contract_date="2026-01-01")
    result = loan_servicing.get_loan_timeline("FIN-1")
    types = [e["type"] for e in result["events"]]
    assert "originated" in types
    assert "funded" in types


def test_get_loan_timeline_includes_status_change_events():
    _full_loan_setup(contract_date="2026-01-01")
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1", "test")
    result = loan_servicing.get_loan_timeline("FIN-1")
    types = [e["type"] for e in result["events"]]
    assert "status_change" in types


def test_get_loan_timeline_includes_real_payment_events(monkeypatch):
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    payments.record_payment("FIN-1", 298.62, "cash", "2026-06-15", "EMP-1")
    result = loan_servicing.get_loan_timeline("FIN-1")
    assert len(result["payment_history"]["entries"]) == 1


def test_get_loan_timeline_collection_activity_always_empty_placeholder():
    _full_loan_setup(contract_date="2026-01-01")
    result = loan_servicing.get_loan_timeline("FIN-1")
    assert result["collection_activity"]["entries"] == []


def test_get_loan_timeline_no_repossession_case_yields_empty_entries():
    _full_loan_setup(contract_date="2026-01-01")
    result = loan_servicing.get_loan_timeline("FIN-1")
    assert result["repossession_events"]["entries"] == []


def test_get_loan_timeline_events_sorted_chronologically():
    _full_loan_setup(contract_date="2026-01-01")
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1", "later event")
    result = loan_servicing.get_loan_timeline("FIN-1")
    ats = [e["at"] for e in result["events"] if e.get("at")]
    assert ats == sorted(ats)


def test_get_loan_timeline_missing_contract_date_no_crash():
    _full_loan_setup(contract_date=None)
    result = loan_servicing.get_loan_timeline("FIN-1")
    assert "error" not in result


# ---------------------------------------------------------------------------
# get_loan_detail() -- full composition
# ---------------------------------------------------------------------------

def test_get_loan_detail_unknown_loan_errors():
    result = loan_servicing.get_loan_detail("FIN-999")
    assert "error" in result


def test_get_loan_detail_full_composition_with_all_links():
    _add_customer("CUST-1", first="Jane", last="Doe")
    _add_vehicle("VEH-1", make="Toyota", model="Camry")
    _add_lender("LENDER-1", name="First Auto Finance")
    _add_loan(link_lender="LENDER-1")

    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["borrower"]["customer"]["id"] == "CUST-1"
    assert result["vehicle"]["vehicle"]["id"] == "VEH-1"
    assert result["lender"]["id"] == "LENDER-1"
    assert "contract" in result
    assert "payment_status" in result
    assert "timeline" in result


def test_get_loan_detail_references_always_not_on_file():
    _full_loan_setup()
    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["borrower"]["references"]["on_file"] is False


def test_get_loan_detail_vehicle_collateral_status_matches_loan_status():
    _full_loan_setup()
    loan_servicing.set_loan_status("FIN-1", "repossessed", "EMP-1")
    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["vehicle"]["collateral_status"] == "repossessed"


def test_get_loan_detail_employment_not_on_file_when_no_customer_linked():
    _add_loan(link_customer=None)
    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["borrower"]["employment"]["on_file"] is False


def test_get_loan_detail_employment_not_on_file_when_no_credit_app():
    _full_loan_setup()
    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["borrower"]["employment"]["on_file"] is False


def test_get_loan_detail_employment_real_when_credit_app_exists():
    _full_loan_setup()
    _add_credit_application(
        customer_id="CUST-1", employer_name="Acme Co", employment_status="employed",
        monthly_income=5000.0,
    )
    result = loan_servicing.get_loan_detail("FIN-1")
    employment = result["borrower"]["employment"]
    assert employment["on_file"] is True
    assert employment["employer_name"] == "Acme Co"
    assert employment["employment_status"] == "employed"


def test_get_loan_detail_lender_none_when_unlinked():
    _full_loan_setup()
    result = loan_servicing.get_loan_detail("FIN-1")
    assert result["lender"] is None


# ---------------------------------------------------------------------------
# get_portfolio_dashboard()
# ---------------------------------------------------------------------------

def test_get_portfolio_dashboard_empty_portfolio():
    result = loan_servicing.get_portfolio_dashboard()
    assert result["total_loans"] == 0
    assert result["loans"] == []


def test_get_portfolio_dashboard_real_counts():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)
    loan_servicing.set_loan_status("FIN-2", "paid_off", "EMP-1")

    result = loan_servicing.get_portfolio_dashboard()
    assert result["total_loans"] == 2
    assert result["payoffs"] == 1


def test_get_portfolio_dashboard_outstanding_balance_only_sums_active_loans(monkeypatch):
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1", amount_financed=12000.0, contract_date="2026-01-01")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", amount_financed=8000.0, contract_date="2026-01-01",
               link_customer=None, link_vehicle=None)
    loan_servicing.set_loan_status("FIN-2", "paid_off", "EMP-1")

    result = loan_servicing.get_portfolio_dashboard()
    fin1 = loan_servicing.get_loan_financials("FIN-1")
    # only FIN-1 (active) contributes; FIN-2 (paid_off) is excluded
    assert abs(result["total_outstanding_balance"] - fin1["schedule_implied_balance"]) < 0.01


def test_get_portfolio_dashboard_bucket_filter_narrows_loans_list(monkeypatch):
    monkeypatch.setattr(loan_servicing, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1", contract_date="2026-07-01")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", contract_date="2026-01-01",
               link_customer=None, link_vehicle=None)
    loan_servicing.set_loan_status("FIN-2", "repossessed", "EMP-1")

    result = loan_servicing.get_portfolio_dashboard(bucket="repossessed")
    assert result["loans_count"] == 1
    assert result["loans"][0]["id"] == "FIN-2"
    # bucket filter doesn't change the portfolio-wide total
    assert result["total_loans"] == 2


def test_get_portfolio_dashboard_limit_truncates_loans_but_not_loans_count():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    for i in range(5):
        _add_loan(loan_id=f"FIN-{i}", finance_number=f"FIN-{i}", link_customer=None, link_vehicle=None)

    result = loan_servicing.get_portfolio_dashboard(limit=2)
    assert len(result["loans"]) == 2
    assert result["loans_count"] == 5


def test_get_portfolio_dashboard_delinquency_buckets_present():
    _full_loan_setup()
    result = loan_servicing.get_portfolio_dashboard()
    for bucket in loan_servicing.DELINQUENCY_BUCKETS:
        assert bucket in result["delinquency_buckets"]


# ---------------------------------------------------------------------------
# ACL layer -- core/loan_servicing_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_loan_detail_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_detail_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_loan_detail_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_detail_api(role, "FIN-1")
    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_loan_financials_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_financials_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_loan_financials_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_financials_api(role, "FIN-1")
    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_loan_timeline_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_timeline_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_loan_timeline_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_timeline_api(role, "FIN-1")
    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_loan_status_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_loan_status_api(role, "FIN-1")
    assert "error" in result


def test_get_loan_status_api_normalizes_plain_string_into_dict():
    _full_loan_setup(contract_date="2026-01-01", term_months=48)
    result = loan_servicing_api.get_loan_status_api(ADMIN, "FIN-1")
    assert result["loan_id"] == "FIN-1"
    assert "loan_status" in result
    assert isinstance(result["loan_status"], str)


def test_get_loan_status_api_passes_through_core_error_dict():
    result = loan_servicing_api.get_loan_status_api(ADMIN, "FIN-999")
    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_set_loan_status_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.set_loan_status_api(role, "EMP-1", "FIN-1", "repossessed")
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_set_loan_status_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.set_loan_status_api(role, "EMP-1", "FIN-1", "repossessed")
    assert not isinstance(result, dict)


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_simulated_payment_status_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_simulated_payment_status_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_simulated_payment_status_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_simulated_payment_status_api(role, "FIN-1")
    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_portfolio_dashboard_api_denies_unauthorized_roles(role):
    result = loan_servicing_api.get_portfolio_dashboard_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_portfolio_dashboard_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = loan_servicing_api.get_portfolio_dashboard_api(role)
    assert "error" not in result
    assert "total_loans" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_compute_amortization_schedule_api_denies_unauthorized_roles(role):
    result = loan_servicing_api.compute_amortization_schedule_api(role, 12000.0, 9.0, 48)
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_compute_amortization_schedule_api_allows_authorized_roles_standalone(role):
    # no loan_id required -- a standalone what-if calculator
    result = loan_servicing_api.compute_amortization_schedule_api(role, 12000.0, 9.0, 48)
    assert isinstance(result, dict)
    assert "error" not in result
    assert len(result["schedule"]) == 48
