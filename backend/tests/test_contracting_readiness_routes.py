"""Exercise the contracting boundary over the real HTTP routes with isolated storage."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from api.app import app
from core.auth import issue_token, credential_store
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DEAL


@pytest.fixture(autouse=True)
def production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    ledger.reset()
    credential_store.set_credential("EMP-REVIEW", "Fictional2026!", "ADMIN", must_change_password=False)
    ledger.add_entity(Entity("DEAL-REVIEW", DEAL, {"status": "contract", "contract": {"amount_financed": 1000}}))
    yield
    ledger.reset()


def test_http_admin_cannot_execute_unreviewed_worksheet():
    # No lifespan/background jobs: test route dispatch and auth only.
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + issue_token("EMP-REVIEW", "ADMIN")}
    for path, body in [
        ("/deals/DEAL-REVIEW/fund", {}),
        ("/esignature", {"linked_deal_id": "DEAL-REVIEW", "signers": [{"name": "Sample", "role": "customer"}]}),
    ]:
        result = client.post(path, json=body, headers=headers).json()
        assert result["code"] == "contract_execution_not_ready"
    assert ledger.get_entity("DEAL-REVIEW").attributes["status"] == "contract"
    assert list(ledger.get_all()) == ["DEAL-REVIEW"]


def test_http_readiness_is_available_to_authenticated_reviewers():
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + issue_token("EMP-REVIEW", "ADMIN")}
    result = client.get("/compliance/rules", headers=headers).json()
    assert result["contracting_readiness"]["production_enabled"] is False
    assert result["contracting_readiness"]["first_review_jurisdiction"] == "TX"
    assert "error" in client.get("/compliance/rules").json()


def test_http_public_verification_cannot_create_simulated_trust():
    client = TestClient(app)
    for path, body in [("/public/verify/start", {"email": "sample@example.invalid"}),
                       ("/public/verify/legacy-token/request-code", {"channel": "email"}),
                       ("/public/verify/legacy-token/identity", {"license_number": "SAMPLE", "selfie_provided": True})]:
        result = client.post(path, json=body).json()
        assert result["reason"] == "provider_unavailable"
        assert "dev_code" not in result
    assert list(ledger.get_all()) == ["DEAL-REVIEW"]


def test_http_staff_electronic_and_public_cash_payments_cannot_credit_loan():
    from core.entity_types import FINANCE_CONTRACT
    from core import payments
    ledger.add_entity(Entity("FIN-REVIEW", FINANCE_CONTRACT, {
        "AmountFinanced": "12000", "MonthlyPayment": "300", "APR": "9", "TermMonths": "48",
        "ContractDate": "2026-10-01", "payment_portal_link": {"token": "review-link", "revoked": False}}))
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + issue_token("EMP-REVIEW", "ADMIN")}
    result = client.post("/loan-servicing/FIN-REVIEW/payments", json={"amount": 300, "method": "ach"}, headers=headers).json()
    assert result["code"] == "workflow_not_ready"
    result = client.post("/public/pay/review-link/submit", json={"amount": 300, "method": "cash"}).json()
    assert result["code"] == "workflow_not_ready"
    assert not payments.list_payments_for_loan("FIN-REVIEW")
