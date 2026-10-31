from copy import deepcopy
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import admin, router
from core import dealer_bridge as b, bridge_preflight as preflight
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, CSV, setup, imported, isolated  # noqa: F401


def test_preflight_reports_missing_columns_without_storing_values(monkeypatch):
    _, mapping = setup()
    before = deepcopy(ledger.entities)
    def no_save(path):
        raise AssertionError("Preflight must not persist")
    monkeypatch.setattr(b, "save_graph", no_save)
    result = preflight.inspect(API, mapping, "external_id,modified_at,email\nprivate-id,bad-time,private@example.invalid\n")
    assert result["status"] == "missing_columns" and result["missing_columns"] == ["name"]
    assert result["row_count"] == 1 and not result["stored"]
    assert "private-id" not in str(result) and "private@example.invalid" not in str(result)
    assert ledger.entities == before


@pytest.mark.parametrize("file_format", ["csv", "tsv", "json"])
def test_blank_counts_are_distinct_from_absent_headers(file_format):
    _, mapping = setup()
    content = "external_id,modified_at,name,email\n1,2026-01-01T00:00:00Z, ,person@example.invalid\n"
    if file_format == "tsv":
        content = content.replace(",", "\t")
    elif file_format == "json":
        content = json.dumps([{"external_id": "1", "modified_at": "2026-01-01T00:00:00Z", "name": None, "email": "person@example.invalid"}])
    result = preflight.inspect(A, mapping, content, file_format)
    assert result["status"] == "columns_present"
    assert next(field for field in result["mapped_fields"] if field["source"] == "name")["blank_rows"] == 1
    assert next(field for field in result["mapped_fields"] if field["source"] == "email")["blank_rows"] == 0


def test_compare_only_consistent_activated_schema():
    _, mapping = setup()
    job = imported(mapping=mapping)
    result = preflight.inspect(A, mapping, "external_id,modified_at,name,email,new_column\n2,2026-01-01T00:00:00Z,Test,test@example.invalid,ignored\n")
    assert result["baseline_job_id"] == job and result["schema_comparison_available"]
    assert result["added_columns"] == ["new_column"] and result["removed_columns"] == []
    b.get(job, "BridgeJob")["headers"].append("invented")
    assert not preflight.inspect(A, mapping, CSV)["schema_comparison_available"]


def test_revocation_tampering_and_foreign_workspace_fail():
    _, mapping = setup()
    with pytest.raises(PermissionError):
        preflight.inspect({**A, "workspace_id": "other"}, mapping, CSV)
    b.revoke_mapping(B, mapping, "Synthetic replacement required")
    with pytest.raises(ValueError):
        preflight.inspect(A, mapping, CSV)


def test_preflight_api_rejects_extra_body_fields():
    _, mapping = setup()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/mappings/{mapping}/preflight"
    assert client.post(path, json={"content": CSV}).json()["status"] == "columns_present"
    assert client.post(path, json={"content": CSV, "workspace_id": "other"}).status_code == 422



def test_schema_baseline_survives_reviewed_cleanup_but_not_receipt_corruption():
    from core import bridge_retention as retention
    _, mapping = setup()
    job = imported(mapping=mapping)
    review = retention.preview(A, job)
    retention.cleanup(B, job, review["review_token"], "Synthetic retention verification")
    assert preflight.inspect(A, mapping, CSV)["schema_comparison_available"]
    b.get(job, "BridgeJob")["activation_receipt"]["checksum"] = "changed"
    assert not preflight.inspect(A, mapping, CSV)["schema_comparison_available"]


def test_empty_export_and_other_mapping_have_no_false_baseline():
    _, original = setup()
    imported(mapping=original)
    _, other = setup()
    result = preflight.inspect(A, other, "external_id,modified_at,name,email\n")
    assert result["status"] == "empty_export" and result["row_count"] == 0
    assert result["baseline_job_id"] is None and not result["schema_comparison_available"]
