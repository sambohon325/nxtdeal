"""Lineage keeps source history separate from the editable current projection."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as b
from core.bridge_lineage import lookup
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, API, CSV, setup, imported, candidate_job, isolated  # noqa: F401


def test_history_orders_by_source_time_and_pages_without_changing_projection():
    system, mapping = setup()
    imported(CSV.replace("2026-01-01", "2026-03-01").replace("Ada,", "Newest,"), mapping)
    imported(CSV, mapping)
    imported(CSV.replace("2026-01-01", "2026-02-01").replace("Ada,", "Middle,"), mapping)
    result = lookup(API, system, "customers", "1", 2)
    assert result["current_values"]["first_name"] == "Newest"
    assert [event["values"]["first_name"] for event in result["observations"]] == ["Newest", "Middle"]
    assert result["total_observations"] == 3
    assert result["source"]["projection"] == "update"
    next_page = lookup(A, system, "customers", "1", 2, result["next_before_event_id"])
    assert [event["values"]["first_name"] for event in next_page["observations"]] == ["Ada"]
    assert next_page["next_before_event_id"] is None
    assert all(event["mapping_id"] == mapping for event in result["observations"])
    assert "not an as-of reconstruction" in result["notice"]


def test_current_values_show_dealership_edits_without_rewriting_source_history():
    system, mapping = setup()
    imported(CSV, mapping)
    original = lookup(A, system, "customers", "1")
    entity = ledger.get_entity(original["canonical_id"])
    entity.attributes.update(first_name="Local edit", FirstName="Local edit", internal_secret="never expose")
    result = lookup(A, system, "customers", "1")
    assert result["current_values"]["first_name"] == "Local edit"
    assert result["observations"][0]["values"]["first_name"] == "Ada"
    assert "internal_secret" not in result["current_values"]


def test_reviewed_link_explains_preserved_legacy_values():
    mapping, job, candidate = candidate_job()
    b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Source identity reviewed against existing customer")
    b.validate(A, job); b.activate(B, job)
    system = b.get(mapping, "BridgeMapping")["system_id"]
    result = lookup(A, system, "customers", "1")
    assert result["source"]["projection"] == "preserve"
    assert result["current_values"]["first_name"] == "Original"
    assert result["observations"][0]["values"]["first_name"] == "Ada"


def test_same_external_id_in_another_source_cannot_leak_events_or_cursor():
    system, mapping = setup()
    imported(CSV, mapping)
    other_system, other_mapping = setup()
    imported(CSV.replace("ada@example.com", "other@example.invalid"), other_mapping)
    first = lookup(A, system, "customers", "1")
    second = lookup(A, other_system, "customers", "1")
    assert first["canonical_id"] != second["canonical_id"]
    assert first["observations"][0]["event_id"] != second["observations"][0]["event_id"]
    with pytest.raises(ValueError, match="does not belong"):
        lookup(A, system, "customers", "1", before_event_id=second["observations"][0]["event_id"])
    with pytest.raises(ValueError):
        lookup(A, system, "wrong-object", "1")


def test_foreign_workspace_observations_and_targets_are_never_returned():
    system, mapping = setup()
    imported(CSV, mapping)
    result = lookup(A, system, "customers", "1")
    event = ledger.get_entity(result["observations"][0]["event_id"])
    ledger.add_entity(Entity("foreign-event", "SourceObservation", {**deepcopy(event.attributes), "workspace_id": "elsewhere"}))
    assert lookup(A, system, "customers", "1")["total_observations"] == 1
    with pytest.raises(PermissionError):
        lookup({**A, "workspace_id": "elsewhere"}, system, "customers", "1")
    ledger.get_entity(result["canonical_id"]).attributes["workspace_id"] = "elsewhere"
    with pytest.raises(ValueError, match="unavailable"):
        lookup(A, system, "customers", "1")


@pytest.mark.parametrize("limit", [0, 101, True, 1.5, "25"])
def test_history_page_limit_is_strict(limit):
    with pytest.raises(ValueError, match="page size"):
        lookup(A, "missing", "customers", "1", limit)


def test_lineage_http_is_admin_only_and_rejects_tenant_injection():
    system, mapping = setup()
    imported(CSV, mapping)
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    app.dependency_overrides[admin] = lambda: API
    body = {"system_id": system, "object_type": "customers", "external_id": "1"}
    assert client.post("/dealer-bridge/lineage", json=body).status_code == 200
    assert client.post("/dealer-bridge/lineage", json={**body, "workspace_id": "other"}).status_code == 422
    assert client.post("/dealer-bridge/lineage", json={**body, "limit": True}).status_code == 422
    app.dependency_overrides[admin] = lambda: {**A, "role": "SALES"}
    assert client.post("/dealer-bridge/lineage", json=body).status_code == 403
