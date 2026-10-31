"""
Tests for core/repossessions.py + core/repossessions_api.py -- Finance's
"Repossessions" item, the fourth slice of the Retail Automotive Lending Platform
expansion (session 112 follow-up).

Covers: the Referral Queue (real loans in Collections' repossession_referral stage
with no open case yet, excluding already-repossessed/charged-off loans), the real
RepossessionCase lifecycle (referred -> assigned -> located -> recovered -> stored ->
disposed, with redeemed/cancelled as terminal off-ramps), storage fee accrual math,
the real Deficiency Balance calculation, disposition/redemption cascading into
core/loan_servicing.py's set_loan_status(), the real recovery-rate math, the
dashboard composition, and the ACL layer (ADMIN/OPERATIONS/FINANCE only).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT
from core import loan_servicing
from core import collections as collections_mod
from core import repossessions
from core import repossessions_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(repossessions, "save_graph", lambda filepath: None)
    monkeypatch.setattr(loan_servicing, "save_graph", lambda filepath: None)


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
    return loan_id


def _full_loan_setup(**loan_kwargs):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    return _add_loan(**loan_kwargs)


def _referral_loan_setup(loan_id="FIN-1", **loan_kwargs):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id=loan_id, **loan_kwargs)
    loan = ledger.get_entity(loan_id)
    loan.attributes["collection_stage"] = "repossession_referral"
    return loan_id


# ---------------------------------------------------------------------------
# get_referral_queue()
# ---------------------------------------------------------------------------

def test_get_referral_queue_empty_when_no_loans():
    result = repossessions.get_referral_queue()
    assert result == {"count": 0, "loans": []}


def test_get_referral_queue_includes_matching_loan():
    _referral_loan_setup()
    result = repossessions.get_referral_queue()
    assert result["count"] == 1
    row = result["loans"][0]
    assert row["loan_id"] == "FIN-1"
    assert row["finance_number"] == "FIN-1"
    assert row["customer_name"] == "Jane Doe"
    assert "current_balance" in row


def test_get_referral_queue_excludes_loans_not_in_referral_stage():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan()  # no collection_stage attribute at all
    result = repossessions.get_referral_queue()
    assert result["count"] == 0


def test_get_referral_queue_excludes_loans_with_an_open_case():
    _referral_loan_setup()
    repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.get_referral_queue()
    assert result["count"] == 0


def test_get_referral_queue_excludes_already_repossessed_loans():
    _referral_loan_setup()
    loan = ledger.get_entity("FIN-1")
    loan.attributes["loan_status"] = "repossessed"
    result = repossessions.get_referral_queue()
    assert result["count"] == 0


def test_get_referral_queue_excludes_already_charged_off_loans():
    _referral_loan_setup()
    loan = ledger.get_entity("FIN-1")
    loan.attributes["loan_status"] = "charged_off"
    result = repossessions.get_referral_queue()
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# create_case()
# ---------------------------------------------------------------------------

def test_create_case_rejects_unknown_loan():
    result = repossessions.create_case("FIN-999", "EMP-1")
    assert "error" in result


def test_create_case_rejects_when_open_case_already_exists():
    _full_loan_setup()
    first = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.create_case("FIN-1", "EMP-2")
    assert "error" in result
    assert first.id in result["error"]


def test_create_case_rejects_already_repossessed_loan():
    _full_loan_setup()
    loan = ledger.get_entity("FIN-1")
    loan.attributes["loan_status"] = "repossessed"
    result = repossessions.create_case("FIN-1", "EMP-1")
    assert "error" in result


def test_create_case_success_creates_real_case():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1", reason="90 days delinquent")
    assert not isinstance(case, dict)
    assert case.attributes["loan_id"] == "FIN-1"
    assert case.attributes["customer_id"] == "CUST-1"
    assert case.attributes["vehicle_id"] == "VEH-1"
    assert case.attributes["stage"] == "referred"
    assert case.attributes["reason"] == "90 days delinquent"
    assert case.attributes["referred_by"] == "EMP-1"
    assert len(case.attributes["stage_history"]) == 1
    assert case.attributes["stage_history"][0]["stage"] == "referred"
    assert case.id.startswith("REPO-")


def test_create_case_captures_balance_at_referral():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    assert case.attributes["balance_at_referral"] is not None
    assert case.attributes["balance_at_referral_basis"] is not None


# ---------------------------------------------------------------------------
# _advance() / assign_agent() / record_location() / record_recovery() /
# record_storage() -- the case lifecycle
# ---------------------------------------------------------------------------

def test_advance_rejects_unknown_case():
    result = repossessions._advance("REPO-999", "assigned", "EMP-1")
    assert "error" in result


def test_advance_rejects_moving_from_terminal_stage():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.cancel_case(case.id, "EMP-1")
    result = repossessions._advance(case.id, "assigned", "EMP-1")
    assert "error" in result
    assert "terminal" in result["error"]


def test_advance_rejects_invalid_transition():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    # referred -> recovered is not a valid direct transition
    result = repossessions._advance(case.id, "recovered", "EMP-1")
    assert "error" in result


def test_assign_agent_requires_agent_name():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.assign_agent(case.id, "", "EMP-1")
    assert "error" in result


def test_assign_agent_success():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.assign_agent(case.id, "Ace Recovery", "EMP-1", agency="Ace Auto Recovery LLC", phone="555-1234")
    assert not isinstance(result, dict)
    assert result.attributes["stage"] == "assigned"
    assert result.attributes["agent_name"] == "Ace Recovery"
    assert result.attributes["agent_agency"] == "Ace Auto Recovery LLC"
    assert result.attributes["agent_phone"] == "555-1234"
    assert len(result.attributes["stage_history"]) == 2


def test_record_location_requires_location():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    result = repossessions.record_location(case.id, "", "EMP-1")
    assert "error" in result


def test_record_location_rejects_before_assignment():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.record_location(case.id, "123 Main St", "EMP-1")
    assert "error" in result  # referred -> located is not a valid transition


def test_record_location_success():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    result = repossessions.record_location(case.id, "123 Main St", "EMP-1", notes="spotted at residence")
    assert not isinstance(result, dict)
    assert result.attributes["stage"] == "located"
    assert result.attributes["location"] == "123 Main St"


def test_record_recovery_success_with_defaults(monkeypatch):
    monkeypatch.setattr(repossessions, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    result = repossessions.record_recovery(case.id, "EMP-1", condition="fair", odometer=45000)
    assert result.attributes["stage"] == "recovered"
    assert result.attributes["recovered_at"] == "2026-07-01"
    assert result.attributes["recovered_condition"] == "fair"
    assert result.attributes["recovered_odometer"] == 45000


def test_record_recovery_accepts_explicit_date():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    result = repossessions.record_recovery(case.id, "EMP-1", recovered_date="2026-06-15")
    assert result.attributes["recovered_at"] == "2026-06-15"


def test_record_storage_requires_facility():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    repossessions.record_recovery(case.id, "EMP-1")
    result = repossessions.record_storage(case.id, "", "EMP-1")
    assert "error" in result


def test_record_storage_success(monkeypatch):
    monkeypatch.setattr(repossessions, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    repossessions.record_recovery(case.id, "EMP-1")
    result = repossessions.record_storage(case.id, "Ace Storage Yard", "EMP-1", daily_rate=15.0, transport_cost=250.0)
    assert result.attributes["stage"] == "stored"
    assert result.attributes["storage_facility"] == "Ace Storage Yard"
    assert result.attributes["storage_start_date"] == "2026-07-01"
    assert result.attributes["storage_daily_rate"] == 15.0
    assert result.attributes["transport_cost"] == 250.0


def _full_lifecycle_to_stored(monkeypatch, loan_id="FIN-1", daily_rate=15.0, transport_cost=250.0,
                                storage_start_date="2026-06-01"):
    case = repossessions.create_case(loan_id, "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    repossessions.record_recovery(case.id, "EMP-1")
    repossessions.record_storage(
        case.id, "Ace Storage Yard", "EMP-1",
        storage_start_date=storage_start_date, daily_rate=daily_rate, transport_cost=transport_cost,
    )
    return case.id


# ---------------------------------------------------------------------------
# _storage_fees_accrued()
# ---------------------------------------------------------------------------

def test_storage_fees_accrued_zero_when_no_start_date():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    fresh_case = repossessions._get_case(case.id)
    assert repossessions._storage_fees_accrued(fresh_case) == 0.0


def test_storage_fees_accrued_zero_when_rate_is_zero(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=0.0)
    case = repossessions._get_case(case_id)
    assert repossessions._storage_fees_accrued(case) == 0.0


def test_storage_fees_accrued_real_math_against_today(monkeypatch):
    monkeypatch.setattr(repossessions, "_today", lambda: __import__("datetime").date(2026, 6, 11))
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=15.0, storage_start_date="2026-06-01")
    case = repossessions._get_case(case_id)
    # 10 days elapsed (June 1 -> June 11) * $15/day = $150
    assert repossessions._storage_fees_accrued(case) == 150.0


def test_storage_fees_accrued_uses_disposition_sale_date_as_end(monkeypatch):
    monkeypatch.setattr(repossessions, "_today", lambda: __import__("datetime").date(2026, 12, 31))
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=15.0, storage_start_date="2026-06-01")
    case = repossessions._get_case(case_id)
    case.attributes["disposition"] = {"sale_date": "2026-06-06"}
    # 5 days (June 1 -> June 6), NOT the ~213 days to Dec 31
    assert repossessions._storage_fees_accrued(case) == 75.0


# ---------------------------------------------------------------------------
# compute_deficiency_balance()
# ---------------------------------------------------------------------------

def test_compute_deficiency_balance_unknown_case_errors():
    result = repossessions.compute_deficiency_balance("REPO-999")
    assert "error" in result


def test_compute_deficiency_balance_real_math_positive(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=0.0, transport_cost=200.0)
    monkeypatch.setattr(repossessions, "get_loan_financials",
                          lambda loan_id: {"current_balance": 8000.0, "current_balance_basis": "real_payment_ledger"})
    result = repossessions.compute_deficiency_balance(case_id)
    # 8000 balance + 0 storage + 200 transport - 0 sale price (no disposition yet)
    assert result["outstanding_balance"] == 8000.0
    assert result["transport_cost"] == 200.0
    assert result["sale_price"] == 0.0
    assert result["deficiency_balance"] == 8200.0


def test_compute_deficiency_balance_negative_is_a_real_surplus(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=0.0, transport_cost=0.0)
    case = repossessions._get_case(case_id)
    case.attributes["disposition"] = {"sale_price": 9500.0}
    monkeypatch.setattr(repossessions, "get_loan_financials",
                          lambda loan_id: {"current_balance": 8000.0, "current_balance_basis": "real_payment_ledger"})
    result = repossessions.compute_deficiency_balance(case_id)
    assert result["deficiency_balance"] == -1500.0


# ---------------------------------------------------------------------------
# record_disposition()
# ---------------------------------------------------------------------------

def test_record_disposition_rejects_bad_type(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions.record_disposition(case_id, "bogus", 5000.0, "EMP-1")
    assert "error" in result


def test_record_disposition_rejects_unknown_case():
    result = repossessions.record_disposition("REPO-999", "auction_sale", 5000.0, "EMP-1")
    assert "error" in result


def test_record_disposition_rejects_when_not_stored():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.record_disposition(case.id, "auction_sale", 5000.0, "EMP-1")
    assert "error" in result
    assert "stored" in result["error"]


def test_record_disposition_success_cascades_loan_status(monkeypatch):
    monkeypatch.setattr(repossessions, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=0.0, transport_cost=0.0)

    result = repossessions.record_disposition(case_id, "auction_sale", 7500.0, "EMP-1", buyer="ABC Auto Auction")
    assert not isinstance(result, dict)
    assert result.attributes["stage"] == "disposed"
    assert result.attributes["disposition"]["disposition_type"] == "auction_sale"
    assert result.attributes["disposition"]["sale_price"] == 7500.0
    assert result.attributes["disposition"]["buyer"] == "ABC Auto Auction"
    assert result.attributes["deficiency_balance"] is not None

    # cascaded into the real loan_servicing.set_loan_status() call
    assert loan_servicing.get_loan_status("FIN-1") == "repossessed"


# ---------------------------------------------------------------------------
# redeem_case()
# ---------------------------------------------------------------------------

def test_redeem_case_rejects_unknown_case():
    result = repossessions.redeem_case("REPO-999", 1000.0, "EMP-1")
    assert "error" in result


def test_redeem_case_rejects_when_already_disposed(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    repossessions.record_disposition(case_id, "auction_sale", 5000.0, "EMP-1")
    result = repossessions.redeem_case(case_id, 1000.0, "EMP-1")
    assert "error" in result


def test_redeem_case_rejects_when_already_cancelled():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.cancel_case(case.id, "EMP-1")
    result = repossessions.redeem_case(case.id, 1000.0, "EMP-1")
    assert "error" in result


def test_redeem_case_success_reactivates_loan():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    loan = ledger.get_entity("FIN-1")
    loan.attributes["loan_status"] = "repossessed"
    result = repossessions.redeem_case(case.id, 2500.0, "EMP-1", notes="paid in full")
    assert not isinstance(result, dict)
    assert result.attributes["stage"] == "redeemed"
    assert result.attributes["redemption_amount"] == 2500.0
    assert loan_servicing.get_loan_status("FIN-1") == "active"


# ---------------------------------------------------------------------------
# cancel_case()
# ---------------------------------------------------------------------------

def test_cancel_case_rejects_unknown_case():
    result = repossessions.cancel_case("REPO-999", "EMP-1")
    assert "error" in result


def test_cancel_case_rejects_when_already_terminal():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.cancel_case(case.id, "EMP-1")
    result = repossessions.cancel_case(case.id, "EMP-1")
    assert "error" in result


def test_cancel_case_success():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.cancel_case(case.id, "EMP-1", reason="customer caught up on payments")
    assert not isinstance(result, dict)
    assert result.attributes["stage"] == "cancelled"


# ---------------------------------------------------------------------------
# get_case() / list_cases() / get_case_history_for_loan()
# ---------------------------------------------------------------------------

def test_get_case_unknown_case_errors():
    result = repossessions.get_case("REPO-999")
    assert "error" in result


def test_get_case_full_composition():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions.get_case(case.id)
    assert result["id"] == case.id
    assert result["loan_id"] == "FIN-1"
    assert result["customer"]["id"] == "CUST-1"
    assert result["vehicle"]["id"] == "VEH-1"
    assert "current_balance" in result
    assert "storage_fees_accrued" in result
    assert result["deficiency"] is None  # not yet stored/disposed


def test_get_case_deficiency_present_once_stored(monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions.get_case(case_id)
    assert result["deficiency"] is not None
    assert "deficiency_balance" in result["deficiency"]


def test_list_cases_filters_by_status():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)

    case1 = repossessions.create_case("FIN-1", "EMP-1")
    case2 = repossessions.create_case("FIN-2", "EMP-1")
    repossessions.cancel_case(case2.id, "EMP-1")

    referred_only = repossessions.list_cases(status="referred")
    assert referred_only["count"] == 1
    assert referred_only["cases"][0]["id"] == case1.id

    cancelled_only = repossessions.list_cases(status="cancelled")
    assert cancelled_only["count"] == 1
    assert cancelled_only["cases"][0]["id"] == case2.id


def test_list_cases_filters_by_loan_id():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)
    repossessions.create_case("FIN-1", "EMP-1")
    repossessions.create_case("FIN-2", "EMP-1")

    result = repossessions.list_cases(loan_id="FIN-1")
    assert result["count"] == 1
    assert result["cases"][0]["loan_id"] == "FIN-1"


def test_get_case_history_for_loan_empty_when_no_cases():
    result = repossessions.get_case_history_for_loan("FIN-1")
    assert result == []


def test_get_case_history_for_loan_composes_real_events():
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    events = repossessions.get_case_history_for_loan("FIN-1")
    assert len(events) == 2
    assert all(e["type"] == "repossession_stage" for e in events)
    assert case.id in events[0]["note"]


# ---------------------------------------------------------------------------
# get_recovery_stats()
# ---------------------------------------------------------------------------

def test_get_recovery_stats_no_disposed_cases():
    result = repossessions.get_recovery_stats()
    assert result["disposed_case_count"] == 0
    assert result["total_sale_price"] == 0.0
    assert result["recovery_rate_pct"] is None


def test_get_recovery_stats_real_math(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(repossessions, "get_loan_financials",
                          lambda loan_id: {"current_balance": 5000.0, "current_balance_basis": "real_payment_ledger"})
    case_id = _full_lifecycle_to_stored(monkeypatch, daily_rate=0.0, transport_cost=0.0)
    repossessions.record_disposition(case_id, "auction_sale", 4500.0, "EMP-1")

    result = repossessions.get_recovery_stats()
    assert result["disposed_case_count"] == 1
    assert result["total_sale_price"] == 4500.0
    # deficiency = 5000 balance - 4500 sale = 500; amount_owed = sale_price + deficiency = 5000
    assert result["total_amount_owed_at_disposition"] == 5000.0
    assert result["recovery_rate_pct"] == 90.0


def test_get_recovery_stats_surplus_can_exceed_one_hundred_percent(monkeypatch):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    monkeypatch.setattr(repossessions, "get_loan_financials",
                          lambda loan_id: {"current_balance": 3000.0, "current_balance_basis": "real_payment_ledger"})
    case_id = _full_lifecycle_to_stored(monkeypatch, loan_id="FIN-1", daily_rate=0.0, transport_cost=0.0)
    repossessions.record_disposition(case_id, "auction_sale", 4000.0, "EMP-1")

    result = repossessions.get_recovery_stats()
    # deficiency = 3000 - 4000 = -1000 (surplus); amount_owed = 4000 + (-1000) = 3000
    assert result["total_amount_owed_at_disposition"] == 3000.0
    assert result["recovery_rate_pct"] == round(4000 / 3000 * 100, 2)
    assert result["recovery_rate_pct"] > 100.0


# ---------------------------------------------------------------------------
# get_repossessions_dashboard()
# ---------------------------------------------------------------------------

def test_get_repossessions_dashboard_empty():
    result = repossessions.get_repossessions_dashboard()
    assert result["referral_queue_count"] == 0
    assert result["open_cases"] == 0
    assert result["disposed_count"] == 0
    assert result["redeemed_count"] == 0
    assert result["total_deficiency_outstanding"] == 0.0


def test_get_repossessions_dashboard_real_composition(monkeypatch):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)
    _add_loan(loan_id="FIN-3", finance_number="FIN-3", link_customer=None, link_vehicle=None)

    loan3 = ledger.get_entity("FIN-3")
    loan3.attributes["collection_stage"] = "repossession_referral"

    monkeypatch.setattr(repossessions, "get_loan_financials",
                          lambda loan_id: {"current_balance": 5000.0, "current_balance_basis": "real_payment_ledger"})

    case1 = repossessions.create_case("FIN-1", "EMP-1")  # stays "referred" (open)
    case2_id = _full_lifecycle_to_stored(monkeypatch, loan_id="FIN-2", daily_rate=0.0, transport_cost=0.0)
    repossessions.record_disposition(case2_id, "auction_sale", 4500.0, "EMP-1")  # disposed

    result = repossessions.get_repossessions_dashboard()
    assert result["referral_queue_count"] == 1  # FIN-3
    assert result["open_cases"] == 1  # case1 still open
    assert result["stage_counts"]["referred"] == 1
    assert result["disposed_count"] == 1
    assert result["redeemed_count"] == 0
    assert result["total_deficiency_outstanding"] == 500.0  # 5000 - 4500


# ---------------------------------------------------------------------------
# ACL layer -- core/repossessions_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_referral_queue_api_denies_unauthorized_roles(role):
    result = repossessions_api.get_referral_queue_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_referral_queue_api_allows_authorized_roles(role):
    result = repossessions_api.get_referral_queue_api(role)
    assert "count" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_create_case_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = repossessions_api.create_case_api(role, "EMP-1", "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_create_case_api_allows_authorized_roles(role):
    ledger.reset()
    _full_loan_setup()
    result = repossessions_api.create_case_api(role, "EMP-1", "FIN-1")
    assert "id" in result
    assert result["stage"] == "referred"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_assign_agent_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.assign_agent_api(role, "EMP-1", case.id, "Ace")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_assign_agent_api_allows_authorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.assign_agent_api(role, "EMP-1", case.id, "Ace")
    assert result["stage"] == "assigned"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_location_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    result = repossessions_api.record_location_api(role, "EMP-1", case.id, "123 Main St")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_record_location_api_allows_authorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    result = repossessions_api.record_location_api(role, "EMP-1", case.id, "123 Main St")
    assert result["stage"] == "located"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_recovery_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    result = repossessions_api.record_recovery_api(role, "EMP-1", case.id)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_record_recovery_api_allows_authorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    result = repossessions_api.record_recovery_api(role, "EMP-1", case.id)
    assert result["stage"] == "recovered"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_storage_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    repossessions.record_recovery(case.id, "EMP-1")
    result = repossessions_api.record_storage_api(role, "EMP-1", case.id, "Ace Storage")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_record_storage_api_allows_authorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    repossessions.assign_agent(case.id, "Ace", "EMP-1")
    repossessions.record_location(case.id, "123 Main St", "EMP-1")
    repossessions.record_recovery(case.id, "EMP-1")
    result = repossessions_api.record_storage_api(role, "EMP-1", case.id, "Ace Storage")
    assert result["stage"] == "stored"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_disposition_api_denies_unauthorized_roles(role, monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions_api.record_disposition_api(role, "EMP-1", case_id, "auction_sale", 5000.0)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_record_disposition_api_allows_authorized_roles(role, monkeypatch):
    ledger.reset()
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions_api.record_disposition_api(role, "EMP-1", case_id, "auction_sale", 5000.0)
    assert result["stage"] == "disposed"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_redeem_case_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.redeem_case_api(role, "EMP-1", case.id, 1000.0)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_redeem_case_api_allows_authorized_roles(role):
    ledger.reset()
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.redeem_case_api(role, "EMP-1", case.id, 1000.0)
    assert result["stage"] == "redeemed"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_cancel_case_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.cancel_case_api(role, "EMP-1", case.id)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_cancel_case_api_allows_authorized_roles(role):
    ledger.reset()
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.cancel_case_api(role, "EMP-1", case.id)
    assert result["stage"] == "cancelled"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_compute_deficiency_balance_api_denies_unauthorized_roles(role, monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions_api.compute_deficiency_balance_api(role, case_id)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_compute_deficiency_balance_api_allows_authorized_roles(role, monkeypatch):
    _full_loan_setup()
    case_id = _full_lifecycle_to_stored(monkeypatch)
    result = repossessions_api.compute_deficiency_balance_api(role, case_id)
    assert "deficiency_balance" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_case_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.get_case_api(role, case.id)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_case_api_allows_authorized_roles(role):
    _full_loan_setup()
    case = repossessions.create_case("FIN-1", "EMP-1")
    result = repossessions_api.get_case_api(role, case.id)
    assert result["id"] == case.id


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_list_cases_api_denies_unauthorized_roles(role):
    result = repossessions_api.list_cases_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_list_cases_api_allows_authorized_roles(role):
    result = repossessions_api.list_cases_api(role)
    assert "count" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_repossessions_dashboard_api_denies_unauthorized_roles(role):
    result = repossessions_api.get_repossessions_dashboard_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_repossessions_dashboard_api_allows_authorized_roles(role):
    result = repossessions_api.get_repossessions_dashboard_api(role)
    assert "open_cases" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_recovery_stats_api_denies_unauthorized_roles(role):
    result = repossessions_api.get_recovery_stats_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_recovery_stats_api_allows_authorized_roles(role):
    result = repossessions_api.get_recovery_stats_api(role)
    assert "recovery_rate_pct" in result
