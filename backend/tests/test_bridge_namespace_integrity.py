"""Source hashes are lookup keys, not a replacement for workspace/type validation."""
import pytest
from core import dealer_bridge as b
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, B, CSV, setup, imported, isolated  # noqa: F401


def test_system_map_excludes_explicit_foreign_legacy_connections():
    ledger.add_entity(Entity("old", "Connection", {"name": "Legacy current"}))
    ledger.add_entity(Entity("current", "Connection", {"name": "Scoped current", "workspace_id": ledger.tenant.workspace_id}))
    ledger.add_entity(Entity("foreign", "Connection", {"name": "Foreign confidential", "workspace_id": "foreign"}))
    assert {value["id"] for value in b.system_map(A)["legacy_connections"]} == {"old", "current"}


@pytest.mark.parametrize("field,value", [("workspace_id", "foreign"), ("system_id", "other"), ("object_type", "other"), ("external_id", "other")])
def test_corrupt_source_namespace_is_quarantined_before_target_disclosure(field, value):
    _, mapping = setup(); imported(mapping=mapping)
    link = next(entity for entity in ledger.entities.values() if entity.entity_type == "BridgeExternalID")
    link.attributes[field] = value
    job = b.stage(A, mapping, CSV.replace("2026-01-01", "2026-01-02"))["id"]
    preview = b.validate(A, job)[0]
    assert preview["status"] == "quarantined" and "target_id" not in preview
    assert preview["current_values"] == {} and preview["changes"] == []
    with pytest.raises(ValueError): b.activate(B, job)


def test_wrong_record_type_at_source_key_is_quarantined():
    _, mapping = setup(); imported(mapping=mapping)
    link = next(entity for entity in ledger.entities.values() if entity.entity_type == "BridgeExternalID")
    ledger.entities[link.id] = Entity(link.id, "OtherRecord", link.attributes)
    job = b.stage(A, mapping, CSV)["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"


@pytest.mark.parametrize("field,value", [("system_id", "other"), ("object_type", "other"), ("external_id", "other")])
def test_relationship_lookup_rejects_misbound_external_identity(field, value):
    system, customers = setup(); imported(mapping=customers)
    mapping = b.propose_mapping(A, system, "LoanAccount", "accounts", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": "customers"},
        "balance": {"source": "balance", "transform": "decimal"}, "currency": {"source": "currency", "transform": "text"}})["id"]
    b.approve_mapping(B, mapping)
    link = next(entity for entity in ledger.entities.values() if entity.entity_type == "BridgeExternalID")
    link.attributes[field] = value
    job = b.stage(A, mapping, "external_id,modified_at,customer,balance,currency\na1,2026-01-01T00:00:00Z,1,10,USD\n")["id"]
    assert b.validate(A, job)[0]["status"] == "quarantined"
