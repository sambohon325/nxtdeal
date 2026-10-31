from copy import deepcopy
import json
import pytest
from core.permissions import ADMIN, OPERATIONS, FINANCE, SALES
from core.security_review import build_security_review, security_review_api


def test_mfa_gaps_are_counted_without_disclosing_credentials_or_people():
    records = [{"role": ADMIN, "mfa_enabled": False, "email": "private@example.invalid", "salt": "SECRET"},
               {"role": OPERATIONS, "mfa_enabled": True, "employee_id": "PRIVATE-ID"},
               {"role": SALES, "mfa_enabled": False, "hash": "SECRET"}]
    before = deepcopy(records)
    report = build_security_review(records, demo=False)
    assert report["mfa"]["not_enrolled"] == 2
    assert report["mfa"]["admin_operations_not_enrolled"] == 1
    assert report["mfa"]["status"] == "enrollment_gaps"
    serialized = json.dumps(report)
    assert all(value not in serialized for value in ("SECRET", "PRIVATE-ID", "private@example.invalid"))
    assert records == before


@pytest.mark.parametrize("records,status", [([], "no_records"), ([{"role": ADMIN, "mfa_enabled": True}], "enrollment_observed")])
def test_empty_or_fully_enrolled_roster_never_means_verified(records, status):
    report = build_security_review(records, demo=False)
    assert report["mfa"]["status"] == status
    assert report["production_verified"] is False
    assert report["mfa"]["mandatory_enrollment_verified"] is False
    assert len(report["verification_required"]) == 8


def test_truthy_but_invalid_enrollment_value_does_not_count():
    assert build_security_review([{"mfa_enabled": "false"}], demo=True)["mfa"]["enrolled"] == 0


@pytest.mark.parametrize("role", [FINANCE, SALES, "CUSTOMER", None])
def test_unprivileged_roles_cannot_read_security_posture(role):
    assert "error" in security_review_api(role)


def test_endpoint_auth_and_no_secrets(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app
    from core.auth import credential_store, issue_token
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    client = TestClient(app)
    assert "error" in client.get("/compliance/security-review").json()
    credential_store.set_credential("EMP-SECURITY-REVIEW", "Fictional2026!", ADMIN, must_change_password=False)
    headers = {"Authorization": "Bearer " + issue_token("EMP-SECURITY-REVIEW", ADMIN)}
    result = client.get("/compliance/security-review", headers=headers).json()
    assert result["runtime_mode"] == "sample_data_only"
    assert result["production_verified"] is False
    assert not result["contracting"]["production_enabled"]
    assert all(not value["production_enabled"] for value in result["workflows"].values())
    assert "Fictional2026!" not in json.dumps(result)
