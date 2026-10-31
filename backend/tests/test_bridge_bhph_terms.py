"""BHPH terms/allocations are typed observations, not servicing instructions."""
import csv
import io

import pytest

from core import dealer_bridge as b
from core.bridge_contracts import transform
from core.bridge_reconciliation import reconcile
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


def import_record(system, kind, object_type, external_id, values, references=None, *, modified_at="2026-03-01T00:00:00Z"):
    fields = {field: {"source": field, "transform": "text"} for field in values}
    for field, source_object in (references or {}).items():
        fields[field] = {"source": field, "transform": "external_id", "object_type": source_object}
    mapping = b.propose_mapping(A, system, kind, object_type, fields)["id"]
    b.approve_mapping(B, mapping)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["external_id", "modified_at", *values])
    writer.writeheader(); writer.writerow({"external_id": external_id, "modified_at": modified_at, **values})
    job = b.stage(A, mapping, stream.getvalue())["id"]
    preview = b.validate(A, job)
    if preview[0]["status"] != "quarantined":
        b.activate(B, job)
        identity = b.get("BRX-" + b.digest([ledger.tenant.workspace_id, system, object_type, external_id]), "BridgeExternalID")
        return ledger.get_entity(identity["target_id"]), preview[0]
    return None, preview[0]


def portfolio():
    system = b.connect(A, "CSV", "Synthetic BHPH export")["id"]
    customer, _ = import_record(system, "Customer", "customers", "customer-1", {"first_name": "Synthetic borrower"})
    contract, _ = import_record(system, "FinanceContract", "contracts", "contract-1", {
        "customer_id": "customer-1", "currency": "USD", "principal": "1000.00", "down_payment": "250.00",
        "installment_amount": "100.00", "annual_percentage_rate": "7.50", "term_months": "12",
        "starts_at": "2026-01-01T10:00:00-06:00"}, {"customer_id": "customers"})
    account, _ = import_record(system, "LoanAccount", "accounts", "account-1", {
        "customer_id": "customer-1", "contract_id": "contract-1", "currency": "USD", "balance": "1000.00",
        "past_due_amount": "100.00", "scheduled_payment": "100.00", "next_due_at": "2026-04-01T00:00:00Z"},
        {"customer_id": "customers", "contract_id": "contracts"})
    return system, customer, contract, account


def test_contract_terms_and_account_due_dates_are_preserved_without_native_contract():
    _, customer, contract, account = portfolio()
    assert contract.entity_type == "ImportedFinanceContract"
    assert contract.attributes["customer_id"] == customer.id
    assert contract.attributes["annual_percentage_rate"] == "7.50"
    assert contract.attributes["term_months"] == 12
    assert contract.attributes["starts_at"] == "2026-01-01T16:00:00+00:00"
    assert account.attributes["contract_id"] == contract.id
    assert account.attributes["past_due_amount"] == "100.00"
    assert not any(entity.entity_type == "FinanceContract" for entity in ledger.get_all().values())
    totals = reconcile([{"status": "ready", "values": contract.attributes}])["totals"]
    assert {total["field"] for total in totals} == {"principal", "down_payment", "installment_amount"}


def test_payment_reversal_links_original_observation_without_adjusting_balance():
    system, _, _, account = portfolio()
    values = {"account_id": "account-1", "paid_at": "2026-03-01T00:00:00Z", "amount": "100.00", "currency": "USD",
              "principal_amount": "80.00", "interest_amount": "15.00", "fee_amount": "5.00", "payment_method": "source-reported-method"}
    payment, _ = import_record(system, "Payment", "payments", "payment-1", values, {"account_id": "accounts"})
    reversal, _ = import_record(system, "Payment", "payments", "reversal-1", {
        **values, "amount": "-100.00", "principal_amount": "-80.00", "interest_amount": "-15.00", "fee_amount": "-5.00",
        "reverses_payment_id": "payment-1", "status": "reversed"}, {"account_id": "accounts", "reverses_payment_id": "payments"})
    assert payment.entity_type == reversal.entity_type == "ImportedPayment"
    assert reversal.attributes["reverses_payment_id"] == payment.id
    assert account.attributes["balance"] == "1000.00"
    assert not any(entity.entity_type == "Payment" for entity in ledger.get_all().values())


def test_reversal_cannot_reference_payment_on_another_account():
    system, _, _, _ = portfolio()
    payment, _ = import_record(system, "Payment", "payments", "payment-1", {
        "account_id": "account-1", "paid_at": "2026-03-01T00:00:00Z", "amount": "100", "currency": "USD"}, {"account_id": "accounts"})
    import_record(system, "LoanAccount", "accounts", "account-2", {"customer_id": "customer-1", "currency": "USD", "balance": "500"}, {"customer_id": "customers"})
    record, preview = import_record(system, "Payment", "payments", "reversal-1", {
        "account_id": "account-2", "paid_at": "2026-03-01T00:00:00Z", "amount": "-100", "currency": "USD", "reverses_payment_id": "payment-1"},
        {"account_id": "accounts", "reverses_payment_id": "payments"})
    assert record is None and "same loan account" in preview["errors"][0]


def test_existing_payment_cannot_become_its_own_reversal():
    system, _, _, _ = portfolio()
    values = {"account_id": "account-1", "paid_at": "2026-03-01T00:00:00Z", "amount": "100", "currency": "USD"}
    payment, _ = import_record(system, "Payment", "payments", "payment-1", values, {"account_id": "accounts"})
    record, preview = import_record(system, "Payment", "payments", "payment-1", {**values, "reverses_payment_id": "payment-1"},
        {"account_id": "accounts", "reverses_payment_id": "payments"}, modified_at="2026-03-02T00:00:00Z")
    assert record is None and "reference itself" in preview["errors"][0]
    assert "reverses_payment_id" not in payment.attributes


@pytest.mark.parametrize("kind", ["Payment", "PaymentSchedule"])
def test_complete_allocations_must_reconcile_exactly_while_partial_stays_explicit(kind):
    values = {"account_id": "canonical-account", "paid_at" if kind == "Payment" else "due_at": "2026-01-01T00:00:00Z",
              "amount": "100.00", "currency": "USD", "principal_amount": "80", "interest_amount": "15", "fee_amount": "4.99"}
    fields = {field: {"source": field, "transform": "text"} for field in values}
    with pytest.raises(ValueError, match="allocations must equal"):
        transform(kind, fields, values)
    values["fee_amount"] = "5.00"
    assert transform(kind, fields, values)["amount"] == "100.00"
    values.pop("fee_amount")
    result = transform(kind, fields, values)
    assert "fee_amount" not in result  # Missing allocation is not assumed to be zero.


@pytest.mark.parametrize("field,value", [("term_months", "-1"), ("term_months", "12.5"), ("annual_percentage_rate", "NaN"), ("annual_percentage_rate", 7.5)])
def test_invalid_contract_numeric_values_are_quarantined(field, value):
    with pytest.raises(ValueError):
        transform("FinanceContract", {field: {"source": "value", "transform": "text"}}, {"value": value})
