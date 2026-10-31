"""Receipt triage must preserve records, distinguish evidence, and restrict access."""
from copy import deepcopy
import json
import pytest
from core.entities import Entity
from core.entity_types import PAYMENT, FINANCE_CONTRACT
from core.payment_review import build_payment_review, payment_review_api
from core.permissions import ADMIN, OPERATIONS, FINANCE, SALES


def receipt(identifier="PMT-1", **overrides):
    attrs = {"loan_id": "FIN-1", "amount": "123.45", "method": "ach", "status": "approved",
             "basis": "simulated_payment_gateway", "recorded_by": "EMP-1"}
    attrs.update(overrides)
    return Entity(identifier, PAYMENT, attrs)


def review(*items, **kwargs):
    return build_payment_review([Entity("FIN-1", FINANCE_CONTRACT, {}), *items], **kwargs)


def test_simulation_is_flagged_even_if_posted_without_mutation_or_private_fields():
    item = receipt(posting_status="posted", notes="PRIVATE NOTE", token="PRIVATE TOKEN", customer_name="PRIVATE NAME")
    original = deepcopy(item)
    result = review(item)
    assert result["records"][0]["reasons"] == ["simulated_payment"]
    assert result["records"][0]["posted"] is True
    assert result["flagged_approved_receipt_total"] == "123.45"
    assert result["reconciled"] is False and result["read_only"] is True
    assert "PRIVATE" not in json.dumps(result)
    assert item == original


def test_staff_cash_is_not_confused_with_simulated_electronic_settlement():
    result = review(receipt(method="cash", basis="staff_recorded_cash"), receipt("PMT-2", method="cash"))
    assert result["flagged_payments"] == 1
    assert result["records"][0]["reasons"] == ["legacy_cash_provenance"]


@pytest.mark.parametrize("actor", ["customer_via_payment_portal", "auto_draft:EMP-1", "", None])
def test_cash_label_does_not_hide_untrusted_receipt(actor):
    result = review(receipt(method="cash", basis="staff_recorded_cash", recorded_by=actor))
    assert "inconsistent_cash_provenance" in result["records"][0]["reasons"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "bad", None, "1e1000", "1e-1000000"])
def test_invalid_amounts_never_enter_totals(value):
    result = review(receipt(amount=value))
    assert result["flagged_approved_receipt_total"] == "0"
    assert result["records"][0]["amount"] is None
    assert "invalid_amount" in result["records"][0]["reasons"]


def test_unknown_provenance_missing_loan_and_declines_are_distinguished():
    result = review(receipt(basis=None, loan_id="missing", status="declined"))
    assert result["flagged_approved_receipt_total"] == "0"
    assert result["records"][0]["reasons"] == ["unreviewed_payment_basis", "missing_finance_contract"]


def test_paging_keeps_full_counts_and_deterministic_order():
    result = review(receipt("PMT-3"), receipt("PMT-1"), receipt("PMT-2"), offset=1, limit=1)
    assert result["scanned_payments"] == result["flagged_payments"] == 3
    assert result["flagged_approved_receipt_total"] == "370.35"
    assert result["records"][0]["payment_id"] == "PMT-2"
    assert result["has_more"] is True


@pytest.mark.parametrize("offset,limit", [(-1, 10), (0, 0), (0, 201), (True, 10), (0, "10")])
def test_invalid_paging(offset, limit):
    assert "error" in review(offset=offset, limit=limit)


@pytest.mark.parametrize("role", [SALES, "CUSTOMER", "", None])
def test_unprivileged_caller_cannot_read_receipts(role):
    assert "error" in payment_review_api(role)


@pytest.mark.parametrize("role", [ADMIN, OPERATIONS, FINANCE])
def test_financial_review_roles_can_read_snapshot(role):
    assert payment_review_api(role)["read_only"] is True


def test_http_endpoint_checks_auth_and_role():
    from fastapi.testclient import TestClient
    from api.app import app
    from core.auth import credential_store, issue_token
    client = TestClient(app)
    assert "error" in client.get("/compliance/payment-review").json()
    for role, allowed in [(SALES, False), (FINANCE, True)]:
        credential_store.set_credential("EMP-REVIEW", "Fictional2026!", role, must_change_password=False)
        headers = {"Authorization": "Bearer " + issue_token("EMP-REVIEW", role)}
        result = client.get("/compliance/payment-review", headers=headers).json()
        assert ("error" not in result) == allowed
