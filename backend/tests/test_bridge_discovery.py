from copy import deepcopy
import pytest
from core.bridge_discovery import discover_file
from core.bridge_connectors import inspect_csv
from core.dealeros import ledger
from tests.test_dealer_bridge import A, setup, isolated  # noqa: F401


def test_discovery_before_mapping_does_not_store_values_or_claim_semantics():
    system, _ = setup()
    before = deepcopy(ledger.entities)
    result = discover_file(A, system, "Customer", "External ID,Modified At,First Name,email,vendor_secret\nx,unknown,Ada,ada@example.com,secret-test-only\n")
    assert result["row_count"] == 1 and result["stored"] is False
    assert result["source_columns"] == {"external_id": "External ID", "modified_at": "Modified At"}
    assert result["suggestions"]["first_name"]["source"] == "First Name"
    assert "secret-test-only" not in str(result) and "ada@example.com" not in str(result)
    assert ledger.entities == before


def test_discovery_rejects_ambiguous_header_suggestions():
    system, _ = setup()
    result = discover_file(A, system, "Customer", "First Name,first_name,email\nAda,Ada,a@example.com\n")
    assert result["ambiguous_fields"] == ["first_name"]
    assert "first_name" not in result["suggestions"]


def test_relationships_need_explicit_source_object_review():
    system, _ = setup()
    result = discover_file(A, system, "LoanAccount", "Customer ID,balance,currency\n42,100.10,USD\n")
    assert result["reference_fields"] == {"customer_id": "Customer", "contract_id": "FinanceContract"}
    assert result["suggestions"]["customer_id"] == {"source": "Customer ID", "transform": "text"}
    assert result["suggestions"]["balance"]["transform"] == "decimal"
    assert result["source_columns"] == {}  # Customer ID is not assumed to be the loan's ID.


@pytest.mark.parametrize("content", ["a,a\n1,2", "a,b\n1", "a\n1,2", "\x00bad\n1", "a" * 121 + "\n1", 'a\n"unclosed', "a\n" + "x\n" * 1001])
def test_discovery_enforces_shared_parser_bounds(content):
    with pytest.raises(ValueError): inspect_csv(content)


def test_discovery_allows_header_only_and_checks_workspace_access():
    system, _ = setup()
    assert discover_file(A, system, "Customer", "email\n")["row_count"] == 0
    with pytest.raises(PermissionError): discover_file({**A, "role": "SALES"}, system, "Customer", "email\n")
    ledger.get_entity(system).attributes["workspace_id"] = "other"
    with pytest.raises(ValueError): discover_file(A, system, "Customer", "email\n")
