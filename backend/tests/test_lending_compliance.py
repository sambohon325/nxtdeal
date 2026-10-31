"""
Tests for core/lending_compliance.py + core/lending_compliance_api.py -- OFAC/SDN
Screening + IRS Form 8300 Cash Reporting (session 112 follow-up).

Covers: get_ofac_screening_status()'s computed-default ("not_screened") vs. real
recorded value, record_ofac_screening()'s funded-deal guard, the real cash-payment
ledger + $10,000 threshold + first-qualifying-payment-date clock-start math,
get_form_8300_status()'s none/pending/overdue/filed states, file_form_8300()'s
guards, the obligations queue, the composed dashboard, and the ACL layer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE
from core import deals as deals_mod
from core import lending_compliance
from core import lending_compliance_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(deals_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lending_compliance, "save_graph", lambda filepath: None)


_VIEW_STAFF_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING, SERVICE)
_COMPLIANCE_STAFF_ROLES = (ADMIN, OPERATIONS, FINANCE)
_COMPLIANCE_DENIED_ROLES = (SALES, MARKETING, SERVICE)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe", credit_score="700"):
    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last, "CreditScore": credit_score},
    ))
    return customer_id


def _add_vehicle(vehicle_id="VEH-1", make="Honda", model="Civic", year="2025", price=25000.0, cost=20000.0):
    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year, "Price": price, "Cost": cost},
    ))
    return vehicle_id


def _add_deal(customer_id="CUST-1", vehicle_id="VEH-1", created_by="EMP-1"):
    return deals_mod.create_deal(customer_id, vehicle_id, created_by)


def _full_deal_setup(**kwargs):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    return _add_deal(**kwargs)


# ---------------------------------------------------------------------------
# get_ofac_screening_status()
# ---------------------------------------------------------------------------

def test_get_ofac_screening_status_unknown_deal_errors():
    result = lending_compliance.get_ofac_screening_status("DEAL-999")
    assert "error" in result


def test_get_ofac_screening_status_computed_default_not_screened():
    deal = _full_deal_setup()
    result = lending_compliance.get_ofac_screening_status(deal.id)
    assert result["status"] == "not_screened"
    assert result["cleared"] is False
    assert result["screened_by"] is None


def test_get_ofac_screening_status_reflects_cleared():
    deal = _full_deal_setup()
    lending_compliance.record_ofac_screening(deal.id, True, "EMP-1")
    result = lending_compliance.get_ofac_screening_status(deal.id)
    assert result["status"] == "cleared"
    assert result["cleared"] is True


def test_get_ofac_screening_status_reflects_potential_match():
    deal = _full_deal_setup()
    lending_compliance.record_ofac_screening(deal.id, False, "EMP-1", notes="name match found")
    result = lending_compliance.get_ofac_screening_status(deal.id)
    assert result["status"] == "potential_match"
    assert result["cleared"] is False
    assert result["notes"] == "name match found"


# ---------------------------------------------------------------------------
# record_ofac_screening()
# ---------------------------------------------------------------------------

def test_record_ofac_screening_unknown_deal_errors():
    result = lending_compliance.record_ofac_screening("DEAL-999", True, "EMP-1")
    assert "error" in result


def test_record_ofac_screening_rejects_already_funded_deal():
    deal = _full_deal_setup()
    deal.attributes["status"] = "funded"
    result = lending_compliance.record_ofac_screening(deal.id, True, "EMP-1")
    assert "error" in result
    assert "funded" in result["error"]


def test_record_ofac_screening_success_stores_real_record():
    deal = _full_deal_setup()
    result = lending_compliance.record_ofac_screening(deal.id, True, "EMP-1", notes="all clear")
    assert result["status"] == "cleared"
    stored = deal.attributes["ofac_screening"]
    assert stored["screened"] is True
    assert stored["cleared"] is True
    assert stored["screened_by"] == "EMP-1"
    assert stored["notes"] == "all clear"
    assert stored["screened_at"] is not None


def test_record_ofac_screening_replaces_prior_result():
    deal = _full_deal_setup()
    lending_compliance.record_ofac_screening(deal.id, False, "EMP-1", notes="potential match")
    result = lending_compliance.record_ofac_screening(deal.id, True, "EMP-2", notes="cleared on manual review")
    assert result["status"] == "cleared"
    assert result["screened_by"] == "EMP-2"


# ---------------------------------------------------------------------------
# record_cash_payment()
# ---------------------------------------------------------------------------

def test_record_cash_payment_unknown_deal_errors():
    result = lending_compliance.record_cash_payment("DEAL-999", 5000, "2026-06-01", "EMP-1")
    assert "error" in result


def test_record_cash_payment_rejects_non_numeric_amount():
    deal = _full_deal_setup()
    result = lending_compliance.record_cash_payment(deal.id, "not-a-number", "2026-06-01", "EMP-1")
    assert "error" in result


def test_record_cash_payment_rejects_non_positive_amount():
    deal = _full_deal_setup()
    result = lending_compliance.record_cash_payment(deal.id, 0, "2026-06-01", "EMP-1")
    assert "error" in result

    result_negative = lending_compliance.record_cash_payment(deal.id, -100, "2026-06-01", "EMP-1")
    assert "error" in result_negative


def test_record_cash_payment_rejects_bad_date():
    deal = _full_deal_setup()
    result = lending_compliance.record_cash_payment(deal.id, 5000, "not-a-date", "EMP-1")
    assert "error" in result


def test_record_cash_payment_defaults_to_today(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 15))
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 5000, None, "EMP-1")
    payments = deal.attributes["cash_payments"]
    assert payments[0]["payment_date"] == "2026-06-15"


def test_record_cash_payment_success_appends_real_record():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 5000.005, "2026-06-01", "EMP-1")
    payments = deal.attributes["cash_payments"]
    assert len(payments) == 1
    assert payments[0]["amount"] == 5000.01  # rounded to 2 decimals
    assert payments[0]["payment_date"] == "2026-06-01"
    assert payments[0]["recorded_by"] == "EMP-1"
    assert payments[0]["recorded_at"] is not None


def test_record_cash_payment_below_threshold_returns_none_status():
    deal = _full_deal_setup()
    result = lending_compliance.record_cash_payment(deal.id, 5000, "2026-06-01", "EMP-1")
    assert result["status"] == "none"
    assert result["obligation"] is False


# ---------------------------------------------------------------------------
# get_form_8300_status() -- none / pending / overdue / filed
# ---------------------------------------------------------------------------

def test_get_form_8300_status_unknown_deal_errors():
    result = lending_compliance.get_form_8300_status("DEAL-999")
    assert "error" in result


def test_get_form_8300_status_none_with_no_cash_payments():
    deal = _full_deal_setup()
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["status"] == "none"
    assert result["total_cash_received"] == 0.0


def test_get_form_8300_status_none_below_threshold():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 9999, "2026-06-01", "EMP-1")
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["status"] == "none"


def test_get_form_8300_status_pending_just_crossed_threshold(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 5))
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 10500, "2026-06-01", "EMP-1")
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["obligation"] is True
    assert result["status"] == "pending"
    assert result["trigger_date"] == "2026-06-01"
    assert result["days_elapsed"] == 4
    assert result["days_remaining"] == 11  # 15 - 4


def test_get_form_8300_status_overdue_past_the_fifteen_day_window(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 17))
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 10500, "2026-06-01", "EMP-1")
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["status"] == "overdue"
    assert result["days_elapsed"] == 16
    assert result["days_overdue"] == 1


def test_get_form_8300_status_multiple_smaller_payments_use_real_crossing_date(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 20))
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 4000, "2026-06-01", "EMP-1")
    lending_compliance.record_cash_payment(deal.id, 4000, "2026-06-05", "EMP-1")
    lending_compliance.record_cash_payment(deal.id, 4000, "2026-06-10", "EMP-1")
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["total_cash_received"] == 12000.0
    # crosses $10,000 on the 3rd payment, dated 2026-06-10, not the first payment's date
    assert result["trigger_date"] == "2026-06-10"
    assert result["days_elapsed"] == 10
    assert result["status"] == "pending"


def test_get_form_8300_status_filed():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 11000, "2026-06-01", "EMP-1")
    lending_compliance.file_form_8300(deal.id, "EMP-1")
    result = lending_compliance.get_form_8300_status(deal.id)
    assert result["status"] == "filed"
    assert result["filed"] is True
    assert result["filing"] is not None


# ---------------------------------------------------------------------------
# file_form_8300()
# ---------------------------------------------------------------------------

def test_file_form_8300_unknown_deal_errors():
    result = lending_compliance.file_form_8300("DEAL-999", "EMP-1")
    assert "error" in result


def test_file_form_8300_rejects_double_filing():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 11000, "2026-06-01", "EMP-1")
    lending_compliance.file_form_8300(deal.id, "EMP-1")
    result = lending_compliance.file_form_8300(deal.id, "EMP-2")
    assert "error" in result
    assert "already" in result["error"]


def test_file_form_8300_rejects_below_threshold():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 5000, "2026-06-01", "EMP-1")
    result = lending_compliance.file_form_8300(deal.id, "EMP-1")
    assert "error" in result
    assert "below" in result["error"]


def test_file_form_8300_success_stores_real_filing():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 12000, "2026-06-01", "EMP-1")
    result = lending_compliance.file_form_8300(deal.id, "EMP-1", filing_date="2026-06-10")
    assert result["status"] == "filed"
    filing = deal.attributes["form_8300"]
    assert filing["filed"] is True
    assert filing["filed_by"] == "EMP-1"
    assert filing["filing_date"] == "2026-06-10"
    assert filing["amount"] == 12000.0


def test_file_form_8300_defaults_filing_date_to_today(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 12))
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 12000, "2026-06-01", "EMP-1")
    lending_compliance.file_form_8300(deal.id, "EMP-1")
    assert deal.attributes["form_8300"]["filing_date"] == "2026-06-12"


# ---------------------------------------------------------------------------
# get_form_8300_obligations()
# ---------------------------------------------------------------------------

def test_get_form_8300_obligations_empty_when_no_cash_deals():
    _full_deal_setup()
    result = lending_compliance.get_form_8300_obligations()
    assert result == []


def test_get_form_8300_obligations_excludes_none_status():
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 5000, "2026-06-01", "EMP-1")
    result = lending_compliance.get_form_8300_obligations()
    assert result == []


def test_get_form_8300_obligations_includes_pending_and_overdue(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 20))
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_vehicle("VEH-2")
    deal_pending = _add_deal(vehicle_id="VEH-1")
    deal_overdue = _add_deal(vehicle_id="VEH-2")

    lending_compliance.record_cash_payment(deal_pending.id, 11000, "2026-06-18", "EMP-1")  # 2 days elapsed
    lending_compliance.record_cash_payment(deal_overdue.id, 11000, "2026-06-01", "EMP-1")  # 19 days elapsed

    result = lending_compliance.get_form_8300_obligations()
    assert len(result) == 2
    statuses = {r["deal_id"]: r["status"] for r in result}
    assert statuses[deal_pending.id] == "pending"
    assert statuses[deal_overdue.id] == "overdue"


def test_get_form_8300_obligations_filters_by_status(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 20))
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_vehicle("VEH-2")
    deal_pending = _add_deal(vehicle_id="VEH-1")
    deal_overdue = _add_deal(vehicle_id="VEH-2")

    lending_compliance.record_cash_payment(deal_pending.id, 11000, "2026-06-18", "EMP-1")
    lending_compliance.record_cash_payment(deal_overdue.id, 11000, "2026-06-01", "EMP-1")

    overdue_only = lending_compliance.get_form_8300_obligations(status="overdue")
    assert len(overdue_only) == 1
    assert overdue_only[0]["deal_id"] == deal_overdue.id


# ---------------------------------------------------------------------------
# get_lending_compliance_dashboard()
# ---------------------------------------------------------------------------

def test_get_lending_compliance_dashboard_empty():
    result = lending_compliance.get_lending_compliance_dashboard()
    assert result["ofac"]["unscreened_or_potential_match_count"] == 0
    assert result["form_8300"]["overdue_count"] == 0
    assert result["form_8300"]["pending_count"] == 0
    assert result["form_8300"]["filed_count"] == 0
    assert "note" in result


def test_get_lending_compliance_dashboard_real_composition(monkeypatch):
    monkeypatch.setattr(lending_compliance, "_today", lambda: __import__("datetime").date(2026, 6, 20))
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_vehicle("VEH-2")
    _add_vehicle("VEH-3")
    deal_unscreened = _add_deal(vehicle_id="VEH-1")
    deal_cleared = _add_deal(vehicle_id="VEH-2")
    deal_cash = _add_deal(vehicle_id="VEH-3")

    lending_compliance.record_ofac_screening(deal_cleared.id, True, "EMP-1")
    lending_compliance.record_cash_payment(deal_cash.id, 11000, "2026-06-01", "EMP-1")

    result = lending_compliance.get_lending_compliance_dashboard()
    # unscreened deal_unscreened + unscreened deal_cash (never separately OFAC-screened)
    assert result["ofac"]["unscreened_or_potential_match_count"] == 2
    assert result["form_8300"]["overdue_count"] == 1
    assert result["form_8300"]["pending_count"] == 0


def test_get_lending_compliance_dashboard_excludes_funded_deals_from_ofac():
    deal = _full_deal_setup()
    deal.attributes["status"] = "funded"
    result = lending_compliance.get_lending_compliance_dashboard()
    assert result["ofac"]["unscreened_or_potential_match_count"] == 0


# ---------------------------------------------------------------------------
# ACL layer -- core/lending_compliance_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_lending_compliance_dashboard_api_denies_unauthorized_roles(role):
    result = lending_compliance_api.get_lending_compliance_dashboard_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_STAFF_ROLES)
def test_get_lending_compliance_dashboard_api_allows_authorized_roles(role):
    result = lending_compliance_api.get_lending_compliance_dashboard_api(role)
    assert "ofac" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_ofac_screening_status_api_denies_unauthorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.get_ofac_screening_status_api(role, deal.id)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_STAFF_ROLES)
def test_get_ofac_screening_status_api_allows_authorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.get_ofac_screening_status_api(role, deal.id)
    assert result["status"] == "not_screened"


@pytest.mark.parametrize("role", _COMPLIANCE_DENIED_ROLES)
def test_record_ofac_screening_api_denies_unauthorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.record_ofac_screening_api(role, deal.id, True, "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _COMPLIANCE_STAFF_ROLES)
def test_record_ofac_screening_api_allows_authorized_roles(role):
    ledger.reset()
    deal = _full_deal_setup()
    result = lending_compliance_api.record_ofac_screening_api(role, deal.id, True, "EMP-1")
    assert result["status"] == "cleared"


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_record_cash_payment_api_denies_unauthorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.record_cash_payment_api(role, deal.id, 5000, "2026-06-01", "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_STAFF_ROLES)
def test_record_cash_payment_api_allows_authorized_roles(role):
    ledger.reset()
    deal = _full_deal_setup()
    result = lending_compliance_api.record_cash_payment_api(role, deal.id, 5000, "2026-06-01", "EMP-1")
    assert "total_cash_received" in result


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_form_8300_status_api_denies_unauthorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.get_form_8300_status_api(role, deal.id)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_STAFF_ROLES)
def test_get_form_8300_status_api_allows_authorized_roles(role):
    deal = _full_deal_setup()
    result = lending_compliance_api.get_form_8300_status_api(role, deal.id)
    assert result["status"] == "none"


@pytest.mark.parametrize("role", _COMPLIANCE_DENIED_ROLES)
def test_file_form_8300_api_denies_unauthorized_roles(role):
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 11000, "2026-06-01", "EMP-1")
    result = lending_compliance_api.file_form_8300_api(role, deal.id, "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _COMPLIANCE_STAFF_ROLES)
def test_file_form_8300_api_allows_authorized_roles(role):
    ledger.reset()
    deal = _full_deal_setup()
    lending_compliance.record_cash_payment(deal.id, 11000, "2026-06-01", "EMP-1")
    result = lending_compliance_api.file_form_8300_api(role, deal.id, "EMP-1")
    assert result["status"] == "filed"


@pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
def test_get_form_8300_obligations_api_denies_unauthorized_roles(role):
    result = lending_compliance_api.get_form_8300_obligations_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _VIEW_STAFF_ROLES)
def test_get_form_8300_obligations_api_allows_authorized_roles(role):
    result = lending_compliance_api.get_form_8300_obligations_api(role)
    assert "obligations" in result
