"""
Tests for core/collections.py + core/collections_api.py -- Finance's Collections
screen (session 112 follow-up, third slice of the Retail Lending Platform expansion).

Covers: the Collection Work Queue (auto-prioritized, bucketed by 3/7/15/30/60-day
thresholds), the real, transparent rules-based risk score + priority recommendation
(explicitly NOT a machine-learning model), the Collection Path lifecycle
(get_collection_stage's computed-default-then-real-value convention +
advance_collection_stage's real, audited transitions), Call/Text/Email contact
logging (reusing core/field_notes.py verbatim), the composed Agent Workspace, the
Collections Dashboard, and the ACL layer (ADMIN/OPERATIONS/FINANCE only, matching
core/loan_servicing_api.py's/core/payments_api.py's own uniform gate).
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
from core import collections_api
from core import payments
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(collections_mod, "save_graph", lambda filepath: None)
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
):
    ledger.add_entity(Entity(
        id=loan_id,
        entity_type=FINANCE_CONTRACT,
        attributes={
            "FinanceNumber": finance_number,
            "AmountFinanced": amount_financed,
            "APR": apr,
            "TermMonths": term_months,
            "MonthlyPayment": monthly_payment,
            "ContractDate": contract_date,
        },
    ))
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


def _fake_status(days_past_due=45, basis="simulated_payment_status", amount_past_due=500.0,
                  bucket="60_day"):
    def fn(loan_id):
        return {
            "loan_id": loan_id,
            "bucket": bucket,
            "days_past_due": days_past_due,
            "amount_past_due": amount_past_due,
            "basis": basis,
            "last_payment_date": None,
        }
    return fn


# ---------------------------------------------------------------------------
# _queue_bucket() / suggest_collection_stage() -- pure functions, boundary values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("days,expected", [
    (None, None),
    (0, None),
    (2, None),
    (3, "3_day"),
    (6, "3_day"),
    (7, "7_day"),
    (14, "7_day"),
    (15, "15_day"),
    (29, "15_day"),
    (30, "30_day"),
    (59, "30_day"),
    (60, "60_day"),
    (200, "60_day"),
])
def test_queue_bucket_thresholds(days, expected):
    assert collections_mod._queue_bucket(days) == expected


@pytest.mark.parametrize("days,expected_stage", [
    (None, None),
    (2, None),
    (3, "friendly_reminder"),
    (7, "late_notice"),
    (15, "demand_notice"),
    (30, "recovery_review"),
    (60, "repossession_referral"),
])
def test_suggest_collection_stage_matches_queue_bucket(days, expected_stage):
    assert collections_mod.suggest_collection_stage(days) == expected_stage


# ---------------------------------------------------------------------------
# get_collection_stage()
# ---------------------------------------------------------------------------

def test_get_collection_stage_unknown_loan_errors():
    result = collections_mod.get_collection_stage("FIN-999")
    assert isinstance(result, dict)
    assert "error" in result


def test_get_collection_stage_computed_default_from_days_past_due(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=20))
    stage = collections_mod.get_collection_stage("FIN-1")
    assert stage == "demand_notice"


def test_get_collection_stage_computed_default_none_when_current(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=0))
    stage = collections_mod.get_collection_stage("FIN-1")
    assert stage is None


def test_get_collection_stage_stored_value_takes_precedence(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=3))
    collections_mod.advance_collection_stage("FIN-1", "repossession_referral", "EMP-1")
    stage = collections_mod.get_collection_stage("FIN-1")
    assert stage == "repossession_referral"


# ---------------------------------------------------------------------------
# advance_collection_stage()
# ---------------------------------------------------------------------------

def test_advance_collection_stage_rejects_bad_stage():
    _full_loan_setup()
    result = collections_mod.advance_collection_stage("FIN-1", "bogus", "EMP-1")
    assert "error" in result


def test_advance_collection_stage_rejects_unknown_loan():
    result = collections_mod.advance_collection_stage("FIN-999", "late_notice", "EMP-1")
    assert "error" in result


def test_advance_collection_stage_bad_stage_checked_before_unknown_loan():
    result = collections_mod.advance_collection_stage("FIN-999", "bogus", "EMP-1")
    assert "error" in result


def test_advance_collection_stage_success_sets_attribute_and_history():
    _full_loan_setup()
    result = collections_mod.advance_collection_stage("FIN-1", "late_notice", "EMP-1", "second notice")
    assert not isinstance(result, dict)
    assert result.attributes["collection_stage"] == "late_notice"
    history = result.attributes.get("collection_stage_history", [])
    assert len(history) == 1
    assert history[0]["stage"] == "late_notice"
    assert history[0]["by"] == "EMP-1"
    assert history[0]["reason"] == "second notice"


def test_advance_collection_stage_multiple_calls_append_full_history():
    _full_loan_setup()
    collections_mod.advance_collection_stage("FIN-1", "late_notice", "EMP-1")
    result = collections_mod.advance_collection_stage("FIN-1", "demand_notice", "EMP-2")
    history = result.attributes.get("collection_stage_history", [])
    assert len(history) == 2
    assert history[0]["stage"] == "late_notice"
    assert history[1]["stage"] == "demand_notice"


@pytest.mark.parametrize("stage", collections_mod.COLLECTION_STAGES)
def test_advance_collection_stage_accepts_every_valid_stage(stage):
    _full_loan_setup()
    result = collections_mod.advance_collection_stage("FIN-1", stage, "EMP-1")
    assert not isinstance(result, dict)
    assert result.attributes["collection_stage"] == stage


# ---------------------------------------------------------------------------
# compute_risk_score()
# ---------------------------------------------------------------------------

def test_compute_risk_score_unknown_loan_propagates_error():
    result = collections_mod.compute_risk_score("FIN-999")
    assert "error" in result


def test_compute_risk_score_real_math_and_basis(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status",
                          _fake_status(days_past_due=20, basis="real_payment_ledger"))
    result = collections_mod.compute_risk_score("FIN-1")
    # score = min(60, 20) + min(30, 0*15) + (10 if no payments and days>0 else 0)
    assert result["score"] == 20 + 0 + 10
    assert result["days_past_due"] == 20
    assert result["broken_promises"] == 0
    assert result["basis"] == "real_payment_ledger"


def test_compute_risk_score_days_component_caps_at_sixty(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=999))
    result = collections_mod.compute_risk_score("FIN-1")
    assert result["score"] == 70  # 60 (capped days) + 0 broken + 10 no-payment penalty


def test_compute_risk_score_no_penalty_when_a_real_payment_exists(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    payments.record_payment("FIN-1", 298.62, "cash", "2026-06-15", "EMP-1")
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=5))
    result = collections_mod.compute_risk_score("FIN-1")
    # no +10 no-payment penalty since a real payment exists
    assert result["score"] == 5


def test_compute_risk_score_broken_promise_component(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2027, 1, 1))
    payments.create_promise_to_pay("FIN-1", "2026-06-01", 200.0, "test", "EMP-1")
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=0))
    result = collections_mod.compute_risk_score("FIN-1")
    assert result["broken_promises"] == 1
    # 0 days + min(30, 1*15) + no penalty (days_past_due is 0)
    assert result["score"] == 15


@pytest.mark.parametrize("days,broken,expected_tier", [
    (0, 0, "low"),
    (29, 0, "low"),
    (30, 0, "elevated"),
    (59, 0, "elevated"),
    (60, 0, "high"),
])
def test_compute_risk_score_tier_boundaries(monkeypatch, days, broken, expected_tier):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "_broken_promises_count", lambda loan_id: broken)
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=days))
    result = collections_mod.compute_risk_score("FIN-1")
    assert result["tier"] == expected_tier


# ---------------------------------------------------------------------------
# get_priority_recommendation()
# ---------------------------------------------------------------------------

def test_get_priority_recommendation_unknown_loan_propagates_error():
    result = collections_mod.get_priority_recommendation("FIN-999")
    assert "error" in result


def test_get_priority_recommendation_recovery_risk_on_high_tier(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=90))
    result = collections_mod.get_priority_recommendation("FIN-1")
    assert result["recommendation"] == "recovery_risk"
    assert result["label"] == "Recovery Risk -- Escalate"


def test_get_priority_recommendation_recovery_risk_on_two_plus_broken_promises(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "_broken_promises_count", lambda loan_id: 2)
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=5))
    result = collections_mod.get_priority_recommendation("FIN-1")
    assert result["recommendation"] == "recovery_risk"


def test_get_priority_recommendation_high_probability_when_low_tier_and_days_le_seven(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=5))
    result = collections_mod.get_priority_recommendation("FIN-1")
    assert result["recommendation"] == "high_probability_to_pay"
    assert result["label"] == "High Probability To Pay -- Contact Today"


def test_get_priority_recommendation_high_probability_when_low_tier_and_kept_promise(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    payments.record_payment("FIN-1", 500.0, "cash", "2026-06-20", "EMP-1")
    payments.create_promise_to_pay("FIN-1", "2026-06-25", 200.0, "test", "EMP-1")
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=20))
    result = collections_mod.get_priority_recommendation("FIN-1")
    assert result["recommendation"] == "high_probability_to_pay"


def test_get_priority_recommendation_standard_follow_up_otherwise(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=20))
    result = collections_mod.get_priority_recommendation("FIN-1")
    assert result["recommendation"] == "standard_follow_up"
    assert result["label"] == "Standard Follow-Up"


# ---------------------------------------------------------------------------
# get_collection_queue()
# ---------------------------------------------------------------------------

def test_get_collection_queue_excludes_current_loans(monkeypatch):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")

    def fake_status(loan_id):
        return {"loan_id": loan_id, "bucket": "current", "days_past_due": 0,
                 "amount_past_due": 0, "basis": "simulated_payment_status"}
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", fake_status)

    result = collections_mod.get_collection_queue()
    assert result["total_in_queue"] == 0


def test_get_collection_queue_includes_delinquent_loans_with_real_fields(monkeypatch):
    _add_customer("CUST-1", first="Jane", last="Doe")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-42")

    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", _fake_status(days_past_due=10))
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])

    result = collections_mod.get_collection_queue()
    assert result["total_in_queue"] == 1
    row = result["loans"][0]
    assert row["loan_id"] == "FIN-1"
    assert row["finance_number"] == "FIN-42"
    assert row["customer_name"] == "Jane Doe"
    assert row["days_past_due"] == 10
    assert row["queue_bucket"] == "7_day"


def test_get_collection_queue_bucket_filter():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)

    # rely on real deterministic seeded statuses -- confirm the filter narrows to
    # only the matching bucket, regardless of which specific bucket that is
    all_rows = collections_mod.get_collection_queue()
    for bucket in collections_mod.QUEUE_BUCKETS:
        filtered = collections_mod.get_collection_queue(bucket=bucket)
        assert filtered["total_in_queue"] == all_rows["bucket_counts"][bucket]
        for row in filtered["loans"]:
            assert row["queue_bucket"] == bucket


def test_get_collection_queue_sorted_worst_first(monkeypatch):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)

    def fake_status(loan_id):
        days = 10 if loan_id == "FIN-1" else 55
        return {"loan_id": loan_id, "bucket": None, "days_past_due": days,
                 "amount_past_due": 0, "basis": "simulated_payment_status"}
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", fake_status)
    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])

    result = collections_mod.get_collection_queue()
    assert [r["loan_id"] for r in result["loans"]] == ["FIN-2", "FIN-1"]


# ---------------------------------------------------------------------------
# log_contact() / get_contact_history()
# ---------------------------------------------------------------------------

def test_log_contact_rejects_bad_channel():
    _full_loan_setup()
    result = collections_mod.log_contact("FIN-1", "carrier_pigeon", "notes", "EMP-1")
    assert "error" in result


def test_log_contact_rejects_unknown_loan():
    result = collections_mod.log_contact("FIN-999", "call", "notes", "EMP-1")
    assert "error" in result


def test_log_contact_success_creates_real_field_note():
    _full_loan_setup()
    result = collections_mod.log_contact("FIN-1", "call", "Left voicemail", "EMP-1")
    assert not isinstance(result, dict)
    assert result.attributes["department"] == "Finance"
    assert result.attributes["category"] == "call"
    assert result.attributes["body"] == "Left voicemail"
    assert result.attributes["linked_entity_id"] == "FIN-1"


def test_get_contact_history_returns_logged_contacts():
    _full_loan_setup()
    collections_mod.log_contact("FIN-1", "call", "first", "EMP-1")
    collections_mod.log_contact("FIN-1", "text", "second", "EMP-1")
    history = collections_mod.get_contact_history("FIN-1")
    assert len(history) == 2


def test_get_contact_history_scoped_to_loan():
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)
    collections_mod.log_contact("FIN-1", "call", "for fin-1", "EMP-1")
    collections_mod.log_contact("FIN-2", "call", "for fin-2", "EMP-1")
    history = collections_mod.get_contact_history("FIN-1")
    assert len(history) == 1
    assert history[0].attributes["body"] == "for fin-1"


# ---------------------------------------------------------------------------
# get_agent_workspace()
# ---------------------------------------------------------------------------

def test_get_agent_workspace_unknown_loan_errors():
    result = collections_mod.get_agent_workspace("FIN-999")
    assert "error" in result


def test_get_agent_workspace_full_composition():
    _add_customer("CUST-1", first="Jane", last="Doe")
    _add_vehicle("VEH-1", make="Toyota", model="Camry")
    _add_loan(finance_number="FIN-1")

    result = collections_mod.get_agent_workspace("FIN-1")
    assert result["loan_id"] == "FIN-1"
    assert result["customer"]["id"] == "CUST-1"
    assert result["vehicle"]["id"] == "VEH-1"
    assert result["references"]["on_file"] is False
    assert "employment" in result
    assert "payment_status" in result
    assert "risk_score" in result
    assert "priority_recommendation" in result
    assert result["promises_to_pay"] == []
    assert result["contact_history"] == []


def test_get_agent_workspace_last_payment_none_when_no_payments():
    _full_loan_setup()
    result = collections_mod.get_agent_workspace("FIN-1")
    assert result["last_payment"] is None


def test_get_agent_workspace_last_payment_real_when_payment_exists(monkeypatch):
    _full_loan_setup()
    monkeypatch.setattr(payments, "_today", lambda: __import__("datetime").date(2026, 7, 1))
    payments.record_payment("FIN-1", 298.62, "cash", "2026-06-15", "EMP-1")
    result = collections_mod.get_agent_workspace("FIN-1")
    assert result["last_payment"] is not None
    assert result["last_payment"]["amount"] == 298.62
    assert result["last_payment"]["method"] == "cash"


def test_get_agent_workspace_includes_contact_history():
    _full_loan_setup()
    collections_mod.log_contact("FIN-1", "email", "reminder sent", "EMP-1")
    result = collections_mod.get_agent_workspace("FIN-1")
    assert len(result["contact_history"]) == 1
    assert result["contact_history"][0]["category"] == "email"
    assert result["contact_history"][0]["body"] == "reminder sent"


# ---------------------------------------------------------------------------
# get_collections_dashboard()
# ---------------------------------------------------------------------------

def test_get_collections_dashboard_empty_portfolio():
    result = collections_mod.get_collections_dashboard()
    assert result["total_in_queue"] == 0
    for stage in collections_mod.COLLECTION_STAGES:
        assert result["stage_counts"][stage] == 0
    assert result["recovery_risk_count"] == 0
    assert result["contact_today_count"] == 0


def test_get_collections_dashboard_real_counts(monkeypatch):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    _add_loan(loan_id="FIN-1", finance_number="FIN-1")
    _add_loan(loan_id="FIN-2", finance_number="FIN-2", link_customer=None, link_vehicle=None)

    monkeypatch.setattr(collections_mod, "list_payments_for_loan", lambda loan_id, include_declined=False: [1])

    def fake_status(loan_id):
        days = 90 if loan_id == "FIN-1" else 5
        return {"loan_id": loan_id, "bucket": None, "days_past_due": days,
                 "amount_past_due": 100, "basis": "simulated_payment_status"}
    monkeypatch.setattr(collections_mod, "get_simulated_payment_status", fake_status)

    collections_mod.advance_collection_stage("FIN-1", "repossession_referral", "EMP-1")

    result = collections_mod.get_collections_dashboard()
    assert result["total_in_queue"] == 2
    assert result["stage_counts"]["repossession_referral"] == 1
    assert result["recovery_risk_count"] == 1
    assert result["contact_today_count"] == 1


# ---------------------------------------------------------------------------
# ACL layer -- core/collections_api.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_collection_queue_api_denies_unauthorized_roles(role):
    result = collections_api.get_collection_queue_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_collection_queue_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_collection_queue_api(role)
    assert "total_in_queue" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_agent_workspace_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_agent_workspace_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_agent_workspace_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_agent_workspace_api(role, "FIN-1")
    assert "loan_id" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_collection_stage_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_collection_stage_api(role, "FIN-1")
    assert "error" in result


def test_get_collection_stage_api_normalizes_into_dict():
    _full_loan_setup()
    result = collections_api.get_collection_stage_api(ADMIN, "FIN-1")
    assert result["loan_id"] == "FIN-1"
    assert "collection_stage" in result


def test_get_collection_stage_api_passes_through_core_error():
    result = collections_api.get_collection_stage_api(ADMIN, "FIN-999")
    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_advance_collection_stage_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.advance_collection_stage_api(role, "EMP-1", "FIN-1", "late_notice")
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_advance_collection_stage_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.advance_collection_stage_api(role, "EMP-1", "FIN-1", "late_notice")
    assert not isinstance(result, dict)


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_compute_risk_score_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.compute_risk_score_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_compute_risk_score_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.compute_risk_score_api(role, "FIN-1")
    assert "score" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_priority_recommendation_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_priority_recommendation_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_priority_recommendation_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_priority_recommendation_api(role, "FIN-1")
    assert "recommendation" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_log_contact_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.log_contact_api(role, "EMP-1", "FIN-1", "call", "notes")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_log_contact_api_allows_authorized_roles(role):
    _full_loan_setup()
    result = collections_api.log_contact_api(role, "EMP-1", "FIN-1", "call", "notes")
    assert "id" in result
    assert result["category"] == "call"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_contact_history_api_denies_unauthorized_roles(role):
    _full_loan_setup()
    result = collections_api.get_contact_history_api(role, "FIN-1")
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_contact_history_api_allows_authorized_roles(role):
    _full_loan_setup()
    collections_mod.log_contact("FIN-1", "call", "hi", "EMP-1")
    result = collections_api.get_contact_history_api(role, "FIN-1")
    assert result["count"] == 1


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_collections_dashboard_api_denies_unauthorized_roles(role):
    result = collections_api.get_collections_dashboard_api(role)
    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_get_collections_dashboard_api_allows_authorized_roles(role):
    result = collections_api.get_collections_dashboard_api(role)
    assert "total_in_queue" in result
