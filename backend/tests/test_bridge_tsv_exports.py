"""Explicit tab-separated intake reuses reviewed identity and activation rules."""
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import admin, router
from core import dealer_bridge as bridge
from core.bridge_connectors import inspect_file, parse_export
from core.bridge_discovery import discover_file
from tests.test_dealer_bridge import A, B, API, isolated, setup  # noqa: F401

TSV = 'external_id\tmodified_at\tname\temail\tignored\n' \
      'tab-1\t2026-10-04T19:00:00Z\t"Synthetic\tName"\ttsv@example.invalid\tdiscard\n'


def test_tab_delimiter_is_explicit_and_quoted_tabs_are_data():
    headers, rows = inspect_file(TSV, "tsv")
    assert headers == ["external_id", "modified_at", "name", "email", "ignored"]
    assert rows[0]["name"] == "Synthetic\tName"
    with pytest.raises(ValueError):
        parse_export("Frazer", TSV)
    assert parse_export("Frazer", TSV, file_format="tsv")[1][0]["external_id"] == "tab-1"


def test_tsv_discovery_and_simulation_do_not_stage_or_retain_values():
    system, mapping = setup()
    result = discover_file(API, system, "Customer", TSV, "tsv")
    assert result["row_count"] == 1 and result["file_format"] == "tsv"
    assert "tsv@example.invalid" not in str(result)
    simulation = bridge.simulate_mapping(API, mapping, TSV, file_format="tsv")
    assert simulation["rows"][0]["status"] == "ready"
    assert not bridge.system_map(A)["jobs"]


def test_tsv_activation_keeps_original_fingerprint_and_approval_boundary():
    _, mapping = setup()
    job = bridge.stage(API, mapping, TSV, {"row_count": 1}, "tsv")["id"]
    state = bridge.get(job, "BridgeJob")
    assert state["source_evidence"]["file_format"] == "tsv"
    assert state["source_evidence"]["export_sha256"] == sha256(TSV.encode()).hexdigest()
    assert "discard" not in str(state)
    assert bridge.validate(A, job)[0]["status"] == "ready"
    with pytest.raises(PermissionError):
        bridge.activate(API, job)
    bridge.activate(B, job)
    assert bridge.get(job, "BridgeJob")["status"] == "activated"


@pytest.mark.parametrize("text", ['a\ta\n1\t2', 'a\tb\n1', 'a\tb\n1\t2\t3', 'a\tb\n"unfinished', 'a\tb\n1\t\x00'])
def test_invalid_tsv_structure_is_rejected(text):
    with pytest.raises(ValueError):
        inspect_file(text, "tsv")


def test_exact_custom_headers_multiline_values_and_bom():
    text = '\ufeff" source id "\tupdated\tname\n001\t2026-10-04T19:00:00Z\t"line1\nline2"\n'
    _, rows = parse_export("DealerCenter", text, {"external_id": " source id ", "modified_at": "updated"}, "tsv")
    assert rows[0]["external_id"] == "001"
    assert rows[0]["name"] == "line1\nline2"


def test_tsv_api_accepts_explicit_format_but_rejects_autodetection():
    system, mapping = setup()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: A
    client = TestClient(app)
    payload = {"content": TSV, "file_format": "tsv"}
    assert client.post(f"/dealer-bridge/systems/{system}/discover-file", json={**payload, "kind": "Customer"}).status_code == 200
    assert client.post(f"/dealer-bridge/mappings/{mapping}/test", json=payload).status_code == 200
    assert client.post("/dealer-bridge/imports", json={**payload, "mapping_id": mapping}).status_code == 200
    assert client.post("/dealer-bridge/imports", json={**payload, "mapping_id": mapping, "file_format": "auto"}).status_code == 422
