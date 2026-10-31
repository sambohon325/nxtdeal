from copy import deepcopy
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.dealer_bridge import admin, router
from core.bridge_adapters.adf import inspect
from core.dealeros import ledger
from tests.test_dealer_bridge import A, API, isolated, setup  # noqa: F401

ADF = '<adf><prospect><id source="Provider">private-id</id><requestdate>2026-10-04T10:00:00-05:00</requestdate><customer><contact><name part="full">Private Name</name><email>private@example.com</email></contact></customer><vehicle><make>Example</make></vehicle></prospect></adf>'


def test_discovery_keeps_creation_semantics_and_returns_no_values():
    report = inspect(ADF)
    assert report["row_count"] == 1 and report["rows"][0]["issues"] == []
    assert report["timestamp_semantics"] == {"requestdate": "lead_created_at", "modified_at": "not_provided"}
    assert report["content_hash"] == sha256(ADF.encode()).hexdigest()
    assert not report["stored"] and not report["import_available"]
    for value in ("private-id", "private@example.com", "Private Name", "Example", "Provider"):
        assert value not in str(report)


def test_repeated_values_require_explicit_selection():
    document = ADF.replace('<id source="Provider">private-id</id>', '<id>one</id><id>two</id>').replace('<email>private@example.com</email>', '<email>a</email><email>b</email>').replace('</prospect>', '<vehicle/></prospect>')
    assert set(inspect(document)["rows"][0]["issues"]) == {"source_id_selection_required", "contact_value_selection_required", "vehicle_selection_required"}


@pytest.mark.parametrize("content,issue", [
    ('<adf><prospect/></adf>', 'stable_source_id_required'),
    (ADF.replace('2026-10-04T10:00:00-05:00', '2026-10-04T10:00:00'), 'timezone_aware_creation_time_required'),
    (ADF.replace('</prospect>', '<requestdate>2026-10-04T10:00:00Z</requestdate></prospect>'), 'single_creation_time_required'),
    (ADF.replace('</customer>', '<contact/></customer>'), 'customer_contact_selection_required'),
], ids=['missing-id', 'naive-time', 'repeated-time', 'repeated-contact'])
def test_missing_or_ambiguous_structure_is_review_evidence(content, issue):
    assert issue in inspect(content)["rows"][0]["issues"]


@pytest.mark.parametrize("content", [
    '<!DOCTYPE adf [<!ENTITY secret SYSTEM "file:///private">]><adf><prospect>&secret;</prospect></adf>',
    '<!DOCTYPE adf SYSTEM "https://example.invalid/private"><adf><prospect/></adf>',
    '<adf xmlns="https://example.invalid"><prospect/></adf>',
    '<adf><unexpected/></adf>', '<adf/>', '<adf><prospect></adf>',
    '<adf>' + '<prospect/>' * 1001 + '</adf>',
    '<adf>' + '<x>' * 33 + '</x>' * 33 + '</adf>',
    '<adf><prospect>' + '<x/>' * 20000 + '</prospect></adf>',
    '<adf><prospect>' + 'x' * 1_000_000 + '</prospect></adf>',
    '<?xml version="1.0" encoding="ISO-8859-1"?><adf><prospect/></adf>',
    '\ud800',
], ids=['entity', 'external-dtd', 'namespace', 'unknown-root-child', 'empty', 'malformed', 'rows', 'depth', 'nodes', 'bytes', 'encoding', 'unicode'])
def test_unsafe_or_unsupported_xml_is_rejected_without_payload_echo(content):
    with pytest.raises(ValueError) as error:
        inspect(content)
    assert 'file:///' not in str(error.value) and 'https://' not in str(error.value)


def test_api_discovery_is_scoped_and_does_not_persist_or_enable_import():
    system, _ = setup()
    before = deepcopy(ledger.entities)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{system}/discover-adf"
    result = client.post(path, json={"content": ADF})
    assert result.status_code == 200 and result.json()["stored"] is False
    assert {k: v.attributes for k, v in ledger.entities.items()} == {k: v.attributes for k, v in before.items()}
    assert client.post('/dealer-bridge/imports', json={"mapping_id": "anything", "content": ADF, "file_format": "adf"}).status_code == 422
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "other"}
    assert client.post(path, json={"content": ADF}).status_code == 403


def test_bom_and_xml_entities_preserve_original_fingerprint():
    content = chr(0xfeff) + ADF.replace('Private Name', 'Synthetic &amp; Example')
    report = inspect(content)
    assert report["content_hash"] == sha256(content.encode("utf-8")).hexdigest()
    assert report["source_bytes"] == len(content.encode("utf-8"))
    assert report["rows"][0]["issues"] == []
