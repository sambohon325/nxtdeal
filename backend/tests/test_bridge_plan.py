"""Migration order follows reviewed source references, not invented vendor rules."""
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as b
from core.bridge_plan import import_order
from core.dealeros import ledger
from core.entities import Entity
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, API, setup, imported, isolated  # noqa: F401


def mapping(system, kind, source, fields, approved=True):
    record = b.propose_mapping(A, system, kind, source, fields)["id"]
    if approved:
        b.approve_mapping(B, record)
    return record


def account_mapping(system, customer_source="customers"):
    return mapping(system, "LoanAccount", "accounts", {
        "customer_id": {"source": "customer", "transform": "external_id", "object_type": customer_source},
        "balance": {"source": "balance", "transform": "decimal"}, "currency": {"source": "currency", "transform": "text"}})


def test_customer_account_payment_order_is_read_only_and_agent_accessible(monkeypatch):
    system, customer = setup()
    account_mapping(system)
    mapping(system, "Payment", "payments", {
        "account_id": {"source": "account", "transform": "external_id", "object_type": "accounts"}})
    imported(mapping=customer)
    before = deepcopy(ledger.entities)
    def forbidden(*_):
        raise AssertionError("Import guidance must not persist")
    monkeypatch.setattr(b, "save_graph", forbidden)
    result = import_order(API, system)
    assert result["steps"] == [["customers"], ["accounts"], ["payments"]]
    assert result["stored"] is False and result["status"] == "guidance_only"
    customer_node = next(node for node in result["objects"] if node["object_type"] == "customers")
    assert customer_node["existing_links"] == 1
    assert ledger.entities == before


def test_missing_dependency_does_not_invent_a_vendor_mapping():
    system, _ = setup()
    account_mapping(system, "unknown_contacts")
    node = next(node for node in import_order(A, system)["objects"] if node["object_type"] == "accounts")
    assert node["references"][0]["status"] == "mapping_required"
    assert node["warnings"]


def test_unapproved_revoked_and_changed_definitions_are_excluded():
    system, _ = setup()
    pending = mapping(system, "Vehicle", "inventory", {"vin": {"source": "VIN", "transform": "text"}}, False)
    revoked = account_mapping(system)
    b.revoke_mapping(B, revoked, "Replace incorrect source mapping")
    changed = mapping(system, "Campaign", "campaigns", {"name": {"source": "name", "transform": "text"}})
    b.get(changed, "BridgeMapping")["object_type"] = "changed"
    result = import_order(A, system)
    assert result["steps"] == [["customers"]]
    assert result["excluded_mappings"] == {"changed_definition": 1, "proposed": 1, "revoked": 1}


def test_multiple_approved_versions_are_choices_not_silently_selected():
    system, first = setup()
    second = mapping(system, "Customer", "customers", {"email": {"source": "email", "transform": "lower"}})
    node = import_order(A, system)["objects"][0]
    assert set(node["mapping_ids"]) == {first, second}
    assert any("Choose" in warning for warning in node["warnings"])


def test_self_references_require_prior_records_not_an_impossible_topological_step():
    system, _ = setup()
    mapping(system, "Payment", "payments", {
        "reverses_payment_id": {"source": "original", "transform": "external_id", "object_type": "payments"},
        "account_id": {"source": "canonical_account", "transform": "text"}})
    node = next(node for node in import_order(A, system)["objects"] if node["object_type"] == "payments")
    assert node["step"] == 1
    assert node["references"][0]["status"] == "prior_records_required"
    assert node["direct_reference_fields"] == ["account_id"]


def test_wrong_type_and_cycle_are_flagged_for_review():
    system, _ = setup()
    mapping(system, "Payment", "first", {"account_id": {"source": "account", "transform": "external_id", "object_type": "second"}})
    mapping(system, "Payment", "second", {"account_id": {"source": "account", "transform": "external_id", "object_type": "first"}})
    result = import_order(A, system)
    for node in result["objects"]:
        if node["object_type"] == "customers":
            continue
        assert node["step"] is None
        assert node["references"][0]["status"] == "type_mismatch"
        assert any("cycle" in warning for warning in node["warnings"])


def test_other_system_and_workspace_mappings_and_links_are_not_used():
    system, _ = setup()
    other, _ = setup()
    account_mapping(system, "other_customers")
    mapping(other, "Customer", "other_customers", {"email": {"source": "email", "transform": "text"}})
    ledger.add_entity(Entity("FOREIGN-LINK", "BridgeExternalID", {"workspace_id": "foreign", "system_id": system,
                                                              "object_type": "other_customers", "kind": "Customer"}))
    node = next(node for node in import_order(A, system)["objects"] if node["object_type"] == "accounts")
    assert node["references"][0]["status"] == "mapping_required"
    assert node["references"][0]["existing_links"] == 0
    with pytest.raises(PermissionError): import_order({**A, "workspace_id": "foreign"}, system)


def test_import_order_route_is_read_only_and_admin_scoped():
    system, _ = setup()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    assert client.get(f"/dealer-bridge/systems/{system}/import-order").json()["stored"] is False
    app.dependency_overrides[admin] = lambda: {**A, "role": "SALES"}
    assert client.get(f"/dealer-bridge/systems/{system}/import-order").status_code == 403


@pytest.mark.parametrize("source", [" customers", "customers ", "customers\n"])
def test_source_names_cannot_create_unreachable_lineage_namespaces(source):
    system, _ = setup()
    with pytest.raises(ValueError):
        mapping(system, "Customer", source, {"email": {"source": "email", "transform": "text"}})
    with pytest.raises(ValueError):
        account_mapping(system, source)
