"""Relationship differences require review without inventing borrower semantics."""
from copy import deepcopy

import pytest

from core import dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401
from tests.test_bridge_bhph_terms import portfolio, import_record


def staged_difference():
    system, customer, contract, account = portfolio()
    other, _ = import_record(system, "Customer", "customers", "customer-2", {"first_name": "Other source borrower"})
    fields = {key: {"source": key, "transform": "text"} for key in ["customer_id", "contract_id", "balance", "currency"]}
    mapping = bridge.propose_mapping(A, system, "LoanAccount", "review_accounts", fields)["id"]
    bridge.approve_mapping(B, mapping)
    content = f"external_id,modified_at,customer_id,contract_id,balance,currency\nreview-account,2026-04-01T00:00:00Z,{other.id},{contract.id},1000,USD\n"
    job = bridge.stage(A, mapping, content)["id"]
    return job, customer, other, contract, account


def test_different_customer_is_visible_advisory_without_rewriting_source_facts():
    job, customer, other, contract, account = staged_difference()
    before = deepcopy(contract.attributes), deepcopy(account.attributes)
    row = bridge.validate(A, job)[0]
    assert row["status"] == "ready" and row["errors"] == []
    summary = bridge.get(job, "BridgeJob")["reconciliation"]
    assert summary["review_advisory_rows"] == 1 and summary["status"] == "not_requested"
    public_job = next(item for item in bridge.system_map(A)["jobs"] if item["id"] == job)
    assert public_job["reconciliation"]["review_advisory_rows"] == 1
    assert "preview" not in public_job
    assert row["review_advisories"][0]["code"] == "contract_customer_differs"
    assert row["values"]["customer_id"] == other.id
    assert customer.id not in str(row["review_advisories"])
    bridge.activate(B, job)
    assert (contract.attributes, account.attributes) == before
    assert bridge.get(job, "BridgeJob")["status"] == "activated"


def test_changed_reference_advisory_requires_fresh_validation():
    job, _, other, contract, _ = staged_difference()
    bridge.validate(A, job)
    contract.attributes["customer_id"] = other.id
    with pytest.raises(ValueError, match="Graph changed"):
        bridge.activate(B, job)
    row = bridge.validate(A, job)[0]
    assert "review_advisories" not in row
    bridge.activate(B, job)


def test_matching_or_unspecified_contract_customer_has_no_invented_advisory():
    system, _, contract, _ = portfolio()
    for index, customer in enumerate(["customer-1", None]):
        if customer is None:
            contract.attributes.pop("customer_id")
        _, row = import_record(system, "LoanAccount", "accounts", f"additional-{index}",
            {"customer_id": "customer-1", "contract_id": "contract-1", "balance": "50", "currency": "USD"},
            {"customer_id": "customers", "contract_id": "contracts"})
        assert "review_advisories" not in row



def test_changed_differing_borrower_invalidates_same_worded_advisory():
    job, _, _, contract, _ = staged_difference()
    first = bridge.validate(A, job)[0]["review_advisories"][0]
    source = bridge.get(job, "BridgeJob")["system_id"]
    third, _ = import_record(source, "Customer", "customers", "customer-3", {"first_name": "Third source borrower"})
    contract.attributes["customer_id"] = third.id
    with pytest.raises(ValueError, match="Graph changed"):
        bridge.activate(B, job)
    second = bridge.validate(A, job)[0]["review_advisories"][0]
    assert first["message"] == second["message"]
    assert first["reference_hash"] != second["reference_hash"]
    assert third.id not in str(second)
    bridge.activate(B, job)



def test_combined_queue_exposes_advisory_count_without_borrower_details():
    from core.bridge_review_queue import read
    job, customer, other, contract, _ = staged_difference()
    bridge.validate(A, job)
    before = deepcopy(ledger.entities)
    item = next(row for row in read(A)["jobs"] if row["id"] == job)
    assert item["review_advisory_rows"] == 1
    assert customer.id not in str(item) and other.id not in str(item) and contract.id not in str(item)
    assert "preview" not in item and "rows" not in item
    assert ledger.entities == before
    contract.attributes["customer_id"] = other.id
    assert next(row for row in read(A)["jobs"] if row["id"] == job)["review_advisory_rows"] == 1
    bridge.validate(A, job)
    assert next(row for row in read(A)["jobs"] if row["id"] == job)["review_advisory_rows"] == 0
