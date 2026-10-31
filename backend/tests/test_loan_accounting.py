"""
Tests for core/loan_accounting.py + core/loan_accounting_api.py -- the real
cash-basis sub-ledger built off core/payments.py's real Payment records (session
112 follow-up).

Covers: the real interest/principal/cash summary math, the daily ledger
composition + posting workflow, bulk post-all-due, month-end close (including its
real "every approved payment in the period must be posted first" guard), the
reopen escape hatch (ADMIN-only, audited), and the ACL layer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import PAYMENT
from core import loan_accounting
from core import loan_accounting_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(loan_accounting, "save_graph", lambda filepath: None)


_STAFF_ROLES = (ADMIN, OPERATIONS, FINANCE)
_DENIED_ROLES = (SALES, MARKETING, SERVICE)


def _add_payment(
    payment_id,
    loan_id="FIN-1",
    amount=300.0,
    interest_portion=75.0,
    principal_portion=225.0,
    payment_date="2026-06-01",
    status="approved",
    posting_status="unposted",
    method="ach",
):
    ledger.add_entity(Entity(
        id=payment_id,
        entity_type=PAYMENT,
        attributes={
            "loan_id": loan_id,
            "amount": amount,
            "interest_portion": interest_portion,
            "principal_portion": principal_portion,
            "payment_date": payment_date,
            "status": status,
            "posting_status": posting_status,
            "method": method,
        },
    ))
    return payment_id


# ---------------------------------------------------------------------------
# Accounting periods -- get_period / is_period_closed / list_periods
# ---------------------------------------------------------------------------

def test_get_period_returns_none_when_no_period_exists():
    assert loan_accounting.get_period("2026-06") is None


def test_is_period_closed_false_for_bad_date():
    assert loan_accounting.is_period_closed("not-a-date") is False


def test_is_period_closed_false_when_no_period_on_file():
    assert loan_accounting.is_period_closed("2026-06-15") is False


def test_list_periods_empty_when_none_exist():
    assert loan_accounting.list_periods() == []


def test_list_periods_sorted_descending():
    loan_accounting.close_accounting_period(2026, 5, "EMP-1")
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    periods = loan_accounting.list_periods()
    assert [p.attributes["period_key"] for p in periods] == ["2026-06", "2026-05"]


# ---------------------------------------------------------------------------
# close_accounting_period()
# ---------------------------------------------------------------------------

def test_close_accounting_period_rejects_non_integer_year_month():
    result = loan_accounting.close_accounting_period("not-a-year", 6, "EMP-1")
    assert "error" in result


def test_close_accounting_period_rejects_bad_month_range():
    result_low = loan_accounting.close_accounting_period(2026, 0, "EMP-1")
    assert "error" in result_low

    result_high = loan_accounting.close_accounting_period(2026, 13, "EMP-1")
    assert "error" in result_high


def test_close_accounting_period_success_with_no_activity():
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    assert result["period_key"] == "2026-06"
    assert result["status"] == "closed"
    assert result["closed_by"] == "EMP-1"

    period = loan_accounting.get_period("2026-06")
    assert period.attributes["status"] == "closed"


def test_close_accounting_period_rejects_already_closed():
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-2")
    assert "error" in result
    assert "already closed" in result["error"]


def test_close_accounting_period_rejects_when_unposted_payments_exist():
    _add_payment("PMT-1", payment_date="2026-06-05", posting_status="unposted")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    assert "error" in result
    assert "unposted" in result["error"]
    assert result["unposted_payment_ids"] == ["PMT-1"]


def test_close_accounting_period_succeeds_once_all_payments_posted():
    _add_payment("PMT-1", payment_date="2026-06-05", posting_status="posted")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    assert result["status"] == "closed"


def test_close_accounting_period_ignores_payments_outside_the_period():
    _add_payment("PMT-1", payment_date="2026-07-05", posting_status="unposted")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    assert result["status"] == "closed"


def test_close_accounting_period_ignores_non_approved_payments():
    _add_payment("PMT-1", payment_date="2026-06-05", posting_status="unposted", status="pending")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    assert result["status"] == "closed"


# ---------------------------------------------------------------------------
# reopen_accounting_period()
# ---------------------------------------------------------------------------

def test_reopen_accounting_period_rejects_when_not_closed():
    result = loan_accounting.reopen_accounting_period(2026, 6, "EMP-1")
    assert "error" in result


def test_reopen_accounting_period_success():
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting.reopen_accounting_period(2026, 6, "ADMIN-1")
    assert result["status"] == "open"

    period = loan_accounting.get_period("2026-06")
    assert period.attributes["status"] == "open"
    assert period.attributes["reopened_by"] == "ADMIN-1"


def test_reopen_then_reclose_a_period():
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    loan_accounting.reopen_accounting_period(2026, 6, "ADMIN-1")
    result = loan_accounting.close_accounting_period(2026, 6, "EMP-2")
    assert result["status"] == "closed"


# ---------------------------------------------------------------------------
# get_loan_accounting_summary()
# ---------------------------------------------------------------------------

def test_get_loan_accounting_summary_empty():
    result = loan_accounting.get_loan_accounting_summary()
    assert result["payment_count"] == 0
    assert result["interest_income_recognized"] == 0.0
    assert result["principal_reduction"] == 0.0
    assert result["cash_collected"] == 0.0
    assert result["posted_count"] == 0
    assert result["unposted_count"] == 0


def test_get_loan_accounting_summary_real_math():
    _add_payment("PMT-1", amount=300.0, interest_portion=75.0, principal_portion=225.0, posting_status="posted")
    _add_payment("PMT-2", amount=300.0, interest_portion=70.0, principal_portion=230.0, posting_status="unposted")

    result = loan_accounting.get_loan_accounting_summary()
    assert result["payment_count"] == 2
    assert result["interest_income_recognized"] == 145.0
    assert result["principal_reduction"] == 455.0
    assert result["cash_collected"] == 600.0
    assert result["posted_count"] == 1
    assert result["unposted_count"] == 1


def test_get_loan_accounting_summary_interest_plus_principal_equals_cash():
    _add_payment("PMT-1", amount=298.62, interest_portion=91.61, principal_portion=207.01)
    _add_payment("PMT-2", amount=298.62, interest_portion=90.20, principal_portion=208.42)
    result = loan_accounting.get_loan_accounting_summary()
    assert round(result["interest_income_recognized"] + result["principal_reduction"], 2) == result["cash_collected"]


def test_get_loan_accounting_summary_excludes_non_approved_payments():
    _add_payment("PMT-1", amount=300.0, status="pending")
    result = loan_accounting.get_loan_accounting_summary()
    assert result["payment_count"] == 0


def test_get_loan_accounting_summary_respects_date_range():
    _add_payment("PMT-1", payment_date="2026-05-15", amount=100.0, interest_portion=25.0, principal_portion=75.0)
    _add_payment("PMT-2", payment_date="2026-06-15", amount=100.0, interest_portion=20.0, principal_portion=80.0)

    result = loan_accounting.get_loan_accounting_summary(start_date="2026-06-01", end_date="2026-06-30")
    assert result["payment_count"] == 1
    assert result["cash_collected"] == 100.0


# ---------------------------------------------------------------------------
# get_daily_ledger()
# ---------------------------------------------------------------------------

def test_get_daily_ledger_rejects_bad_date():
    result = loan_accounting.get_daily_ledger("not-a-date")
    assert "error" in result


def test_get_daily_ledger_empty_day():
    result = loan_accounting.get_daily_ledger("2026-06-15")
    assert result["entries"] == []
    assert result["totals"]["cash"] == 0.0


def test_get_daily_ledger_real_composition():
    _add_payment("PMT-1", loan_id="FIN-1", amount=300.0, interest_portion=75.0, principal_portion=225.0, payment_date="2026-06-01", method="ach")
    _add_payment("PMT-2", loan_id="FIN-2", amount=200.0, interest_portion=40.0, principal_portion=160.0, payment_date="2026-06-01", method="cash")
    _add_payment("PMT-3", loan_id="FIN-3", amount=500.0, payment_date="2026-06-02")  # different day

    result = loan_accounting.get_daily_ledger("2026-06-01")
    assert result["date"] == "2026-06-01"
    assert result["period_closed"] is False
    assert len(result["entries"]) == 2
    assert result["totals"]["cash"] == 500.0
    assert result["totals"]["interest_income"] == 115.0
    assert result["totals"]["principal_reduction"] == 385.0

    entry = next(e for e in result["entries"] if e["payment_id"] == "PMT-1")
    assert entry["method"] == "ach"
    assert entry["lines"][0] == {"account": "Cash", "debit": 300.0, "credit": 0}
    assert entry["lines"][1] == {"account": "Interest Income", "debit": 0, "credit": 75.0}
    assert entry["lines"][2] == {"account": "Loan Principal Receivable", "debit": 0, "credit": 225.0}


def test_get_daily_ledger_reflects_period_closed_flag():
    _add_payment("PMT-1", payment_date="2026-06-01", posting_status="posted")
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting.get_daily_ledger("2026-06-01")
    assert result["period_closed"] is True


# ---------------------------------------------------------------------------
# get_unposted_payments()
# ---------------------------------------------------------------------------

def test_get_unposted_payments_empty_when_all_posted():
    _add_payment("PMT-1", posting_status="posted")
    assert loan_accounting.get_unposted_payments() == []


def test_get_unposted_payments_real_sorted_list():
    _add_payment("PMT-1", payment_date="2026-06-10", posting_status="unposted")
    _add_payment("PMT-2", payment_date="2026-06-01", posting_status="unposted")
    _add_payment("PMT-3", payment_date="2026-06-05", posting_status="posted")

    result = loan_accounting.get_unposted_payments()
    assert [e["payment_id"] for e in result] == ["PMT-2", "PMT-1"]


# ---------------------------------------------------------------------------
# post_payment_to_ledger()
# ---------------------------------------------------------------------------

def test_post_payment_to_ledger_unknown_payment_errors():
    result = loan_accounting.post_payment_to_ledger("PMT-999", "EMP-1")
    assert "error" in result


def test_post_payment_to_ledger_rejects_non_approved_payment():
    _add_payment("PMT-1", status="pending")
    result = loan_accounting.post_payment_to_ledger("PMT-1", "EMP-1")
    assert "error" in result
    assert "not approved" in result["error"]


def test_post_payment_to_ledger_rejects_already_posted():
    _add_payment("PMT-1", posting_status="posted")
    result = loan_accounting.post_payment_to_ledger("PMT-1", "EMP-1")
    assert "error" in result
    assert "already posted" in result["error"]


def test_post_payment_to_ledger_rejects_when_period_closed():
    _add_payment("PMT-1", payment_date="2026-06-05", posting_status="posted")
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")

    _add_payment("PMT-2", payment_date="2026-06-10", posting_status="unposted")
    result = loan_accounting.post_payment_to_ledger("PMT-2", "EMP-1")
    assert "error" in result
    assert "closed" in result["error"]


def test_post_payment_to_ledger_success():
    _add_payment("PMT-1", posting_status="unposted")
    result = loan_accounting.post_payment_to_ledger("PMT-1", "EMP-1")
    assert result["posting_status"] == "posted"

    payment = ledger.get_entity("PMT-1")
    assert payment.attributes["posting_status"] == "posted"
    assert payment.attributes["posted_by"] == "EMP-1"
    assert payment.attributes["posted_at"] is not None


# ---------------------------------------------------------------------------
# post_all_due()
# ---------------------------------------------------------------------------

def test_post_all_due_rejects_bad_date():
    result = loan_accounting.post_all_due("not-a-date", "EMP-1")
    assert "error" in result


def test_post_all_due_rejects_when_period_closed():
    _add_payment("PMT-1", payment_date="2026-06-05", posting_status="posted")
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting.post_all_due("2026-06-05", "EMP-1")
    assert "error" in result


def test_post_all_due_empty_when_nothing_due():
    result = loan_accounting.post_all_due("2026-06-15", "EMP-1")
    assert result["posted_count"] == 0
    assert result["posted_payment_ids"] == []


def test_post_all_due_bulk_posts_real_payments():
    _add_payment("PMT-1", payment_date="2026-06-01", posting_status="unposted")
    _add_payment("PMT-2", payment_date="2026-06-01", posting_status="unposted")
    _add_payment("PMT-3", payment_date="2026-06-01", posting_status="posted")  # already posted
    _add_payment("PMT-4", payment_date="2026-06-02", posting_status="unposted")  # different day

    result = loan_accounting.post_all_due("2026-06-01", "EMP-1")
    assert result["posted_count"] == 2
    assert set(result["posted_payment_ids"]) == {"PMT-1", "PMT-2"}

    assert ledger.get_entity("PMT-1").attributes["posting_status"] == "posted"
    assert ledger.get_entity("PMT-2").attributes["posting_status"] == "posted"
    assert ledger.get_entity("PMT-4").attributes["posting_status"] == "unposted"


# ---------------------------------------------------------------------------
# ACL layer -- core/loan_accounting_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_loan_accounting_summary_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.get_loan_accounting_summary_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_loan_accounting_summary_api_allows_authorized_roles(role):
    result = loan_accounting_api.get_loan_accounting_summary_api(role)
    assert "payment_count" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_daily_ledger_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.get_daily_ledger_api(role, "2026-06-01")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_daily_ledger_api_allows_authorized_roles(role):
    result = loan_accounting_api.get_daily_ledger_api(role, "2026-06-01")
    assert "entries" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_unposted_payments_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.get_unposted_payments_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_unposted_payments_api_allows_authorized_roles(role):
    result = loan_accounting_api.get_unposted_payments_api(role)
    assert "unposted" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_post_payment_to_ledger_api_denies_unauthorized_roles(role):
    _add_payment("PMT-1")
    result = loan_accounting_api.post_payment_to_ledger_api(role, "PMT-1", "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_post_payment_to_ledger_api_allows_authorized_roles(role):
    ledger.reset()
    _add_payment("PMT-1")
    result = loan_accounting_api.post_payment_to_ledger_api(role, "PMT-1", "EMP-1")
    assert result["posting_status"] == "posted"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_post_all_due_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.post_all_due_api(role, "2026-06-01", "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_post_all_due_api_allows_authorized_roles(role):
    result = loan_accounting_api.post_all_due_api(role, "2026-06-01", "EMP-1")
    assert "posted_count" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_close_accounting_period_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.close_accounting_period_api(role, 2026, 6, "EMP-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_close_accounting_period_api_allows_authorized_roles(role):
    ledger.reset()
    result = loan_accounting_api.close_accounting_period_api(role, 2026, 6, "EMP-1")
    assert result["status"] == "closed"


@pytest.mark.parametrize("role", (SALES, MARKETING, SERVICE, OPERATIONS, FINANCE))
def test_reopen_accounting_period_api_denies_non_admin_roles(role):
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting_api.reopen_accounting_period_api(role, 2026, 6, "EMP-1")
    assert "error" in result


def test_reopen_accounting_period_api_allows_admin():
    loan_accounting.close_accounting_period(2026, 6, "EMP-1")
    result = loan_accounting_api.reopen_accounting_period_api(ADMIN, 2026, 6, "ADMIN-1")
    assert result["status"] == "open"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_list_periods_api_denies_unauthorized_roles(role):
    result = loan_accounting_api.list_periods_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_list_periods_api_allows_authorized_roles(role):
    result = loan_accounting_api.list_periods_api(role)
    assert "periods" in result
