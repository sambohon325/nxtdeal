import json
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import admin, router
from core import dealer_bridge as bridge
from core.bridge_connectors import inspect_json, parse_export
from core.bridge_discovery import discover_file
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated, setup  # noqa: F401

ROW = {"external_id": "json-1", "modified_at": "2026-10-04T01:00:00Z", "name": "Synthetic", "email": "qa@example.invalid"}


def test_json_discovery_returns_headers_and_counts_without_values_or_writes():
    system, _ = setup()
    count = len(ledger.entities)
    result = discover_file(A, system, "Customer", json.dumps([ROW]), "json")
    assert result["row_count"] == 1 and result["file_format"] == "json"
    assert result["source_columns"] == {"external_id": "external_id", "modified_at": "modified_at"}
    assert "qa@example.invalid" not in str(result)
    assert len(ledger.entities) == count


def test_json_staging_retains_original_hash_and_only_mapped_values():
    _, mapping = setup()
    content = json.dumps([{**ROW, "unmapped": "discard-me"}])
    job = bridge.stage(API, mapping, content, {"row_count": 1}, "json")["id"]
    record = bridge.get(job, "BridgeJob")
    assert "discard-me" not in str(record)
    assert record["source_evidence"]["export_sha256"] == sha256(content.encode()).hexdigest()
    assert record["source_evidence"]["file_format"] == "json"
    assert bridge.validate(A, job)[0]["status"] == "ready"
    with pytest.raises(PermissionError):
        bridge.activate(API, job)
    bridge.activate(B, job)
    assert any(e.entity_type == "Customer" for e in ledger.entities.values())


def test_numeric_lexemes_keep_precision_and_large_identifiers():
    _, rows = inspect_json('[{"id":9007199254740993,"money":123456789012345.123456,"optional":null}]')
    assert rows == [{"id": "9007199254740993", "money": "123456789012345.123456", "optional": ""}]


def test_custom_identity_columns_and_header_spaces_are_preserved():
    content = json.dumps([{" source id ": "0001", "updated": ROW["modified_at"], " name ": "Example"}])
    headers, rows = parse_export("Frazer", content, {"external_id": " source id ", "modified_at": "updated"}, "json")
    assert headers == [" source id ", "updated", " name "]
    assert rows[0]["external_id"] == "0001" and rows[0][" name "] == "Example"


@pytest.mark.parametrize("content", ["{}", "[]", "null", "[1]", "[{},{}]", '[{"x":1,"x":2}]',
    '[{"x":true}]', '[{"x":false}]', '[{"x":[]}]', '[{"x":{}}]', '[{"x":NaN}]',
    '[{"x":Infinity}]', '[{"x":1},{"y":2}]', '[{"x":1},null]', '[{"":1}]',
    '[{"x":"\\u0000"}]', '[{"x":"\\ud800"}]', '[{"\\ud800":"x"}]',
    '[{"x":"' + 'a' * 100_001 + '"}]', '[' * 2000 + ']' * 2000,
    json.dumps([{"x": "y"}] * 1001), ' ' * 1_000_001], ids=lambda value: sha256(value.encode()).hexdigest()[:12])
def test_invalid_json_is_bounded_and_rejected_without_echoing_values(content):
    with pytest.raises(ValueError):
        inspect_json(content)


def test_identity_errors_and_unsupported_format_do_not_stage():
    _, mapping = setup()
    for row in [{**ROW, "external_id": " spaced "}, {**ROW, "modified_at": "2026-10-04"}]:
        with pytest.raises(ValueError):
            bridge.stage(A, mapping, json.dumps([row]), file_format="json")
    with pytest.raises(ValueError, match="formats"):
        bridge.stage(A, mapping, json.dumps([ROW]), file_format="xml")
    assert not bridge.system_map(A)["jobs"]


def test_simulation_and_api_require_explicit_json_format():
    system, mapping = setup()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: A
    client = TestClient(app)
    payload = {"content": json.dumps([ROW]), "file_format": "json"}
    response = client.post(f"/dealer-bridge/mappings/{mapping}/test", json=payload)
    assert response.status_code == 200 and response.json()["rows"][0]["status"] == "ready"
    assert not bridge.system_map(A)["jobs"]
    assert client.post(f"/dealer-bridge/systems/{system}/discover-file", json={**payload, "kind": "Customer"}).status_code == 200
    assert client.post("/dealer-bridge/imports", json={**payload, "mapping_id": mapping}).status_code == 200
    assert client.post("/dealer-bridge/imports", json={**payload, "mapping_id": mapping, "file_format": "xml"}).status_code == 422
    with pytest.raises(ValueError):
        bridge.stage(A, mapping, payload["content"])
