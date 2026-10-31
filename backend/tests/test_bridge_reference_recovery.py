"""Dependency diagnostics guide staged BHPH batches without resolving or activating them."""
from copy import deepcopy
import pytest

from core import dealer_bridge as b
from core.dealeros import ledger
from tests.test_bridge_bhph_terms import import_record
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


def pending_account(*, external=True):
    system = b.connect(A, "CSV", "Synthetic dependency recovery")["id"]
    fields = {field:{"source":field,"transform":"text"} for field in ["customer_id","contract_id","balance","currency"]}
    if external:
        for field, source in [("customer_id","customers"),("contract_id","contracts")]:
            fields[field] = {"source":field,"transform":"external_id","object_type":source}
    mapping = b.propose_mapping(A, system, "LoanAccount", "accounts", fields)["id"]
    b.approve_mapping(B, mapping)
    content = "external_id,modified_at,customer_id,contract_id,balance,currency\na1,2026-03-01T00:00:00Z,private-customer,private-contract,1000.00,USD\n"
    job = b.stage(A, mapping, content)["id"]
    return system, mapping, job, content


def test_all_missing_source_relationships_are_explained_without_ids_or_automatic_recovery():
    system, _, job, _ = pending_account()
    row = b.validate(A, job)[0]
    assert row["status"] == "quarantined"
    assert row["reference_issues"] == [
        {"field":"customer_id","source_object":"customers","expected_kind":"Customer","reason":"source_reference_unresolved"},
        {"field":"contract_id","source_object":"contracts","expected_kind":"FinanceContract","reason":"source_reference_unresolved"},
    ]
    assert "private-" not in str(row["reference_issues"])
    with pytest.raises(ValueError): b.activate(B, job)
    customer, _ = import_record(system, "Customer", "customers", "private-customer", {"first_name":"Synthetic dependency"})
    assert b.get(job,"BridgeJob")["status"] == "blocked"
    row = b.validate(A, job)[0]
    assert [issue["field"] for issue in row["reference_issues"]] == ["contract_id"]
    contract, _ = import_record(system,"FinanceContract","contracts","private-contract",
        {"customer_id":"private-customer","principal":"1000.00","currency":"USD"}, {"customer_id":"customers"})
    assert b.get(job,"BridgeJob")["status"] == "blocked"
    row = b.validate(A, job)[0]
    assert row["status"] == "ready" and "reference_issues" not in row
    assert not any(e.entity_type == "LoanAccount" for e in ledger.get_all().values())
    b.activate(B, job)
    accounts = [e for e in ledger.get_all().values() if e.entity_type == "LoanAccount"]
    assert len(accounts) == 1
    assert accounts[0].attributes["customer_id"] == customer.id
    assert accounts[0].attributes["contract_id"] == contract.id


def test_simulation_reports_dependencies_without_mutating_staged_job():
    _, mapping, job, content = pending_account()
    before = deepcopy(b.get(job,"BridgeJob"))
    simulated = b.simulate_mapping(A, mapping, content)
    assert simulated["stored"] is False and len(simulated["rows"][0]["reference_issues"]) == 2
    assert b.get(job,"BridgeJob") == before


def test_direct_canonical_references_remain_distinct_from_source_import_guidance():
    _, _, job, _ = pending_account(external=False)
    row = b.validate(A, job)[0]
    assert {issue["field"] for issue in row["reference_issues"]} == {"customer_id","contract_id"}
    assert all(issue["reason"] == "canonical_reference_unresolved" and "source_object" not in issue for issue in row["reference_issues"])
    assert "private-" not in str(row["reference_issues"])
