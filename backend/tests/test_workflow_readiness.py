"""Negative production tests for simulated trust and financial side effects."""
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core import dealeros_verify as verify
from core import payments, payments_api, loan_accounting
from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import FINANCE_CONTRACT, AUTO_DRAFT, PAYMENT
from core.workflow_readiness import simulation_block, workflow_readiness


@pytest.fixture(autouse=True)
def production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    ledger.reset()
    yield
    ledger.reset()


def loan():
    entity = Entity("FIN-TEST", FINANCE_CONTRACT, {
        "AmountFinanced": "12000", "MonthlyPayment": "300", "APR": "9", "TermMonths": "48",
        "ContractDate": "2026-10-01", "payment_portal_link": {"token": "sample-private-link", "revoked": False},
    })
    ledger.add_entity(entity)
    return entity


def session():
    result = verify.start_verification(email="sample@example.invalid", phone="5550100100")
    return ledger.get_entity(result["verification"]["id"])


@pytest.mark.parametrize("workflow", ["customer_verification", "electronic_payments", "automatic_payments", "unknown"])
@pytest.mark.parametrize("flag", ["", "0", "invalid"])
def test_release_gate_defaults_to_denial(monkeypatch, workflow, flag):
    monkeypatch.setenv("DEALEROS_DEMO", flag)
    assert simulation_block(workflow)["blocked"] is True
    assert all(not item["production_enabled"] for item in workflow_readiness().values())


@pytest.mark.parametrize("action", [
    lambda v: verify.request_email_code(v), lambda v: verify.request_sms_code(v),
    lambda v: verify.confirm_email_code(v, "123456"), lambda v: verify.confirm_sms_code(v, "123456"),
    lambda v: verify.submit_identity(v, "SAMPLE-ID"), lambda v: verify.submit_credit_verification(v, "CAPP-OLD"),
])
def test_verification_never_returns_a_code_or_mutates_trust_in_production(action):
    entity = session()
    before = deepcopy(entity.attributes)
    result = action(entity.id)
    assert result["code"] == "workflow_not_ready"
    assert "dev_code" not in result
    assert entity.attributes == before


def test_old_simulated_tiers_and_tokens_cannot_grant_access(monkeypatch):
    entity = session()
    entity.attributes.update({"tier": "credit_verified", "email_verified": True, "phone_verified": True,
                              "identity": {"license_verified": True, "basis": "simulated"},
                              "credit": {"credit_verified": True}})
    before = deepcopy(entity.attributes)
    for capability in ("create_deal", "reserve_vehicle", "negotiate", "contracting", "schedule_delivery", "save_vehicles"):
        assert not verify.can(entity, capability)
        assert verify.require_capability(entity.id, capability)[0] is False
    view = verify.get_verification(entity.id)
    assert view["tier"] == "anonymous"
    assert not view["identity_verified"] and not view["credit_verified"] and not view["email_verified"]
    assert verify.verification_summary()["verified_humans_or_above"] == 0
    assert verify.list_verifications(tier="credit_verified")["total"] == 0
    assert verify.can(entity, "browse_inventory")
    assert entity.attributes == before  # Preserve history; change its authority, not its stored evidence.


@pytest.mark.parametrize("method", ["ach", "debit_card", "credit_card", "cash_app", "venmo", "apple_pay", "google_pay"])
def test_electronic_receipts_cannot_change_balance_or_allocate_ids(method, monkeypatch):
    item = loan()
    before = deepcopy(item.attributes)
    counters = dict(id_generator.counters)
    monkeypatch.setattr(payments, "_simulate_gateway_result", lambda *args: pytest.fail("No gateway simulation in production"))
    result = payments_api.record_payment_api("ADMIN", "EMP-1", item.id, 300, method)
    assert result["code"] == "workflow_not_ready"
    assert item.attributes == before and list(ledger.get_all()) == [item.id]
    assert id_generator.counters == counters


@pytest.mark.parametrize("method", ["cash", "ach", "credit_card"])
def test_public_payment_portal_cannot_self_credit(method):
    loan()
    result = payments.submit_public_payment("sample-private-link", 300, method)
    assert result["blocked"] is True
    assert not payments.list_payments_for_loan("FIN-TEST")


def test_staff_cash_receipt_remains_available_and_is_honestly_labeled():
    loan()
    receipt = payments_api.record_payment_api("FINANCE", "EMP-1", "FIN-TEST", 300, "cash")
    assert receipt.attributes["basis"] == "staff_recorded_cash"
    assert receipt.attributes["status"] == "approved"
    assert "processor settlement" in receipt.attributes["disclaimer"]


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_invalid_cash_amount_does_not_corrupt_ledger(amount):
    loan()
    assert "error" in payments.record_payment("FIN-TEST", amount, "cash", "EMP-1")
    assert not payments.list_payments_for_loan("FIN-TEST")


def test_auto_draft_denial_does_not_consume_due_run():
    loan()
    draft = Entity("DRFT-OLD", AUTO_DRAFT, {"loan_id": "FIN-TEST", "amount": 300, "method": "cash",
                                           "status": "active", "day_of_month": payments._today().day})
    ledger.add_entity(draft)
    before = deepcopy(draft.attributes)
    assert payments.create_auto_draft("FIN-TEST", 300, "ach", 1, "EMP-1")["blocked"]
    assert payments.run_due_auto_drafts("EMP-1")["blocked"]
    assert draft.attributes == before
    assert not payments.list_payments_for_loan("FIN-TEST")


def test_revoked_payment_link_exposes_no_financial_data():
    item = loan()
    payments.revoke_payment_portal_link(item.id, "EMP-1")
    result = payments.get_public_portal_view("sample-private-link")
    assert result["revoked"] is True and "error" in result
    assert "balance" not in result and "recent_payments" not in result and "customer_name" not in result


def test_historical_simulated_receipts_cannot_be_posted_individually_or_in_bulk():
    loan()
    cash = Entity("PMT-CASH", PAYMENT, {"loan_id": "FIN-TEST", "status": "approved", "method": "cash",
                                       "basis": "staff_recorded_cash", "payment_date": "2026-10-14"})
    simulated = Entity("PMT-SAMPLE", PAYMENT, {"loan_id": "FIN-TEST", "status": "approved", "method": "ach",
                                               "basis": "simulated_payment_gateway", "payment_date": "2026-10-14"})
    ledger.add_entity(cash)
    ledger.add_entity(simulated)
    assert loan_accounting.post_payment_to_ledger(simulated.id, "EMP-1")["blocked"]
    assert loan_accounting.post_all_due("2026-10-14", "EMP-1")["blocked"]
    assert "posting_status" not in cash.attributes and "posting_status" not in simulated.attributes


def test_isolated_demo_still_supports_verification_and_payment_examples(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    entity = session()
    for request, confirm in [(verify.request_email_code, verify.confirm_email_code), (verify.request_sms_code, verify.confirm_sms_code)]:
        result = request(entity.id)
        confirm(entity.id, result["dev_code"])
    assert verify.submit_identity(entity.id, "SAMPLE-ID")["verification"]["identity_verified"]
    assert verify.can(entity, "create_deal")
    loan()
    assert hasattr(payments.record_payment("FIN-TEST", 300, "ach", "EMP-1"), "id")
    assert simulation_block("unknown")["blocked"]
