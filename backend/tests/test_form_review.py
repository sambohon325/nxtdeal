from copy import deepcopy
from datetime import date
import pytest
from pydantic import ValidationError
from core.form_review import PacketDraft, assess_packet_draft
from core.contracting_readiness import execution_block

TODAY = date(2026, 10, 14)


def candidate():
    evidence = {"reference": "REVIEW-EXAMPLE", "reviewer": "Reviewer placeholder", "reviewed_on": "2026-10-01", "review_due": "2026-11-01"}
    scope = {"dealer_id": "DLR-1", "location_id": "LOC-1", "selling_state": "TX", "buyer_state": "TX", "delivery_state": "TX",
             "registration_state": "TX", "transaction": "dealer_held_installment", "vehicle": "used", "payment_frequency": "monthly"}
    form = {"form_id": "SAMPLE-ONLY", "revision": "1", "publisher": "Example", "sha256": "a" * 64, "effective_on": "2026-01-01",
            "dealer_id": "DLR-1", "location_id": "LOC-1", "jurisdiction": "TX", "transaction": "dealer_held_installment", "vehicle": "used",
            "rights": ["populate", "reproduce", "print", "sign", "distribute"], "rights_evidence": deepcopy(evidence), "applicability_evidence": deepcopy(evidence)}
    result = {"scope": scope, "forms": [form], "required_form_ids": ["SAMPLE-ONLY"]}
    for field in ("form_list_evidence", "calculation_evidence", "mapping_evidence", "external_review_evidence", "signature_delivery_evidence", "retention_evidence", "security_evidence"):
        result[field] = deepcopy(evidence)
    return result


def assess(data):
    return assess_packet_draft(PacketDraft.model_validate(data), today=TODAY)


def test_complete_claims_never_enable_execution_or_verify_evidence(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    data = candidate(); before = deepcopy(data)
    result = assess(data)
    assert result["assessment"] == "evidence_claims_complete"
    assert not result["production_enabled"] and not result["executable"] and not result["evidence_verified"]
    assert execution_block("sign")["blocked"]
    assert data == before


@pytest.mark.parametrize("field", ["selling_state", "buyer_state", "delivery_state", "registration_state"])
def test_cross_border_scope_is_not_silently_accepted(field):
    data = candidate(); data["scope"][field] = "OK"
    assert any(gap["reason"] == "separate_jurisdiction_review_required" for gap in assess(data)["gaps"])


@pytest.mark.parametrize("field", ["dealer_id", "location_id", "jurisdiction", "transaction", "vehicle"])
def test_form_scope_must_match_transaction(field):
    values = {"dealer_id": "DLR-2", "location_id": "LOC-2", "jurisdiction": "OK", "transaction": "lease", "vehicle": "new"}
    data = candidate(); data["forms"][0][field] = values[field]
    assert {"field": f"forms[0].{field}", "reason": "scope_mismatch"} in assess(data)["gaps"]


@pytest.mark.parametrize("field,value,reason", [
    ("revoked", True, "revoked_evidence"), ("review_due", "2026-10-14", "review_expired"),
    ("reviewed_on", "2026-10-15", "invalid_review_dates"), ("review_due", "2026-09-01", "invalid_review_dates"),
])
def test_evidence_time_and_revocation(field, value, reason):
    data = candidate(); data["forms"][0]["rights_evidence"][field] = value
    assert {"field": "forms[0].rights_evidence", "reason": reason} in assess(data)["gaps"]


def test_missing_retired_and_duplicate_forms_cannot_pass():
    data = candidate(); data["required_form_ids"].append("MISSING")
    data["forms"][0]["retired_on"] = "2026-10-14"
    data["forms"].append(deepcopy(data["forms"][0]))
    reasons = {gap["reason"] for gap in assess(data)["gaps"]}
    assert {"form_retired", "duplicate_form_id", "required_form_missing:MISSING"} <= reasons


def test_missing_rights_and_review_evidence_are_explicit():
    data = candidate(); data["forms"][0]["rights"].remove("sign")
    del data["calculation_evidence"]
    reasons = {gap["reason"] for gap in assess(data)["gaps"]}
    assert {"packet_use_rights_incomplete", "missing_evidence"} <= reasons


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(production_enabled=True),
    lambda data: data["forms"][0].update(sha256="not-a-hash"),
    lambda data: data["scope"].update(dealer_id=" "),
    lambda data: data.update(forms=data["forms"] * 101),
])
def test_invalid_schema_and_enable_flags_rejected(mutation):
    data = candidate(); mutation(data)
    with pytest.raises(ValidationError):
        PacketDraft.model_validate(data)


def test_http_preflight_requires_authorized_role_and_never_writes():
    from fastapi.testclient import TestClient
    from api.app import app
    from core.auth import credential_store, issue_token
    from core.permissions import FINANCE, SALES
    from core.dealeros import ledger
    client = TestClient(app); before = deepcopy(ledger.get_all())
    assert "error" in client.post("/compliance/forms/preflight", json=candidate()).json()
    for role in (SALES, FINANCE):
        credential_store.set_credential("EMP-FORMS", "Fictional2026!", role, must_change_password=False)
        headers = {"Authorization": "Bearer " + issue_token("EMP-FORMS", role)}
        result = client.post("/compliance/forms/preflight", json=candidate(), headers=headers).json()
        assert ("error" in result) == (role == SALES)
        if role == FINANCE:
            assert result["production_enabled"] is False
    assert ledger.get_all() == before
