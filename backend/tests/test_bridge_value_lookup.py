"""Finite, reviewed translations; never executable expressions or guessed defaults."""
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import dealer_bridge as b
from core.bridge_contracts import transform, validate_mapping_spec
from core.dealeros import ledger
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401


def spec(values=None):
    return {"source": "source_status", "transform": "lookup", "values": values or {"A": "active", "C": "closed"}}


def configured():
    system = b.connect(A, "CSV", "Synthetic status export")["id"]
    mapping = b.propose_mapping(API, system, "Campaign", "campaigns", {"status": spec()})["id"]
    return system, mapping


def test_exact_translation_and_unknown_code_fail_closed():
    assert transform("Campaign", {"status": spec()}, {"source_status": " A "}) == {"status": "active"}
    for value in ["a", "Unknown", "private-source-code"]:
        with pytest.raises(ValueError, match="no approved translation") as error:
            transform("Campaign", {"status": spec()}, {"source_status": value})
        assert str(error.value) == "Source value has no approved translation"


@pytest.mark.parametrize("values", [{}, {" A": "active"}, {"A": "active "}, {"A": ""}, {1: "active"}, {"A": 1},
                                   {"A": {"nested": "active"}}, {"A": "x" * 121}, {"A\n": "active"},
                                   {str(index): "active" for index in range(101)}], ids=["empty", "source-space", "target-space", "blank", "numeric-key", "numeric-value", "nested", "long", "control", "too-many"])
def test_lookup_contract_is_bounded_and_unambiguous(values):
    with pytest.raises(ValueError): validate_mapping_spec("status", {"source": "code", "transform": "lookup", "values": values})


@pytest.mark.parametrize("target", ["customer_id", "amount", "vin", "occurred_at", "email", "first_name"])
def test_lookup_cannot_replace_identity_money_or_time_contracts(target):
    with pytest.raises(ValueError): validate_mapping_spec(target, spec())


def test_lookup_cannot_add_fallback_or_executable_code():
    for extra in [{"default": "active"}, {"expression": "eval(source)"}]:
        with pytest.raises(ValueError): validate_mapping_spec("status", {**spec(), **extra})
    assert transform("Campaign", {"status": spec({"literal": "${not_executed}"})}, {"source_status": "literal"}) == {"status": "${not_executed}"}


def test_normal_canonical_validation_still_applies_to_translated_currency():
    with pytest.raises(ValueError, match="currency"):
        transform("Vehicle", {"vin": {"source": "vin", "transform": "text"}, "currency": spec({"A": "dollars"})},
                  {"vin": "1HGCM82633A004352", "source_status": "A"})


def test_old_transformation_versions_do_not_gain_lookup_semantics():
    for version in (1, 2):
        with pytest.raises(ValueError, match="version 3"):
            transform("Campaign", {"status": spec()}, {"source_status": "A"}, version=version)
        assert transform("Campaign", {"status": {"source": "code", "transform": "text"}}, {"code": "A"}, version=version) == {"status": "A"}


def test_agent_can_simulate_but_human_approval_is_required_and_lookup_is_hashed():
    _, mapping = configured()
    content = "external_id,modified_at,source_status\n1,2026-01-01T00:00:00Z,A\n"
    before = deepcopy(ledger.entities)
    assert b.simulate_mapping(API, mapping, content)["rows"][0]["values"]["status"] == "active"
    assert {key: value.attributes for key, value in ledger.entities.items()} == {key: value.attributes for key, value in before.items()}
    job = b.stage(API, mapping, content)["id"]; b.validate(API, job)
    with pytest.raises(PermissionError): b.activate(B, job)
    with pytest.raises(PermissionError): b.approve_mapping(API, mapping)
    b.approve_mapping(B, mapping)
    definition = b.get(mapping, "BridgeMapping")
    definition["fields"]["status"]["values"]["A"] = "closed"
    with pytest.raises(PermissionError): b.activate(B, job)


def test_unmapped_codes_quarantine_whole_job_without_silent_partial_activation():
    _, mapping = configured(); b.approve_mapping(B, mapping)
    job = b.stage(A, mapping, "external_id,modified_at,source_status\n1,2026-01-01T00:00:00Z,A\n2,2026-01-01T00:00:00Z,X\n")["id"]
    assert [row["status"] for row in b.validate(A, job)] == ["ready", "quarantined"]
    with pytest.raises(ValueError): b.activate(B, job)
    assert not any(entity.entity_type == "Campaign" for entity in ledger.entities.values())


def test_api_accepts_reviewable_lookup_table_and_rejects_nested_payload():
    system, _ = configured()
    app = FastAPI(); app.include_router(router); app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    body = {"system_id": system, "kind": "Campaign", "object_type": "campaigns", "fields": {"status": spec()}}
    response = client.post("/dealer-bridge/mappings", json=body)
    assert response.status_code == 200
    definition = b.get(response.json()["id"], "BridgeMapping")
    assert definition["fields"]["status"]["values"] == {"A": "active", "C": "closed"}
    body["fields"]["status"]["values"] = {"A": {"bad": "value"}}
    assert client.post("/dealer-bridge/mappings", json=body).status_code == 422
