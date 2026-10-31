from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import admin, router
from core import bridge_discovery as discovery, bridge_runtime as runtime, dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_bridge_sync import configured, FakeConnector, A, B, API, isolated  # noqa: F401


class DiscoverConnector(FakeConnector):
    capabilities = frozenset({"sync", "discover", "schema"})
    def __init__(self):
        super().__init__()
        self.objects = ["customers", "unapproved_internal_object"]
        self.discovery_calls = 0
        self.on_discovery = None
    def discover(self):
        self.discovery_calls += 1
        if self.on_discovery: self.on_discovery()
        return self.objects
    def schema(self, object_type): return ["external_id", "modified_at"]


def bound():
    system, _, _, _ = configured()
    adapter = DiscoverConnector()
    runtime.bind(system, adapter, revision="discovery-1", objects=["customers", "inventory"], environment="synthetic")
    return system, adapter


def test_discovery_exposes_only_authorized_names_without_persisting_or_collecting():
    system, adapter = bound()
    before = {key: deepcopy(value.attributes) for key, value in ledger.entities.items()}
    report = discovery.discover_bound_objects(API, system)
    assert report["objects"] == ["customers"]
    assert report["authorized_not_reported"] == ["inventory"]
    assert report["environment"] == "synthetic" and not report["stored"]
    assert report["schema_inspection_available"]
    assert "unapproved_internal_object" not in str(report)
    assert before == {key: value.attributes for key, value in ledger.entities.items()}
    assert not adapter.calls and adapter.discovery_calls == 1


@pytest.mark.parametrize("result", [None, {"customers": []}, ["customers", "customers"], [" name"], ["x\n"], ["x" * 121], [1]], ids=["none", "envelope", "duplicate", "space", "control", "long", "number"])
def test_malformed_discovery_results_fail_closed(result):
    system, adapter = bound()
    adapter.objects = result
    with pytest.raises(ValueError, match="bounded object names"):
        discovery.discover_bound_objects(A, system)


@pytest.mark.parametrize("change", ["pause", "unbind", "replace"])
def test_changed_binding_discards_discovery(change):
    system, adapter = bound()
    def mutate():
        if change == "pause": bridge.set_system_paused(B, system, True, "Pause during synthetic discovery")
        elif change == "unbind": runtime.unbind(system)
        else: runtime.bind(system, DiscoverConnector(), revision="discovery-2", objects=["customers"], environment="synthetic")
    adapter.on_discovery = mutate
    with pytest.raises(ValueError): discovery.discover_bound_objects(A, system)


def test_no_discovery_without_capability_and_no_vendor_errors_exposed():
    system, _, _, adapter = configured()
    with pytest.raises(ValueError, match="not implemented"):
        discovery.discover_bound_objects(A, system)
    assert not adapter.calls
    system, adapter = bound()
    def fail(): raise RuntimeError("secret-provider-and-customer-data")
    adapter.on_discovery = fail
    with pytest.raises(ValueError) as error: discovery.discover_bound_objects(A, system)
    assert "secret-provider" not in str(error.value)


def test_discovery_api_requires_admin_workspace_scope_and_handles_empty_catalog():
    system, adapter = bound()
    adapter.objects = []
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: API
    client = TestClient(app)
    path = f"/dealer-bridge/systems/{system}/discover-objects"
    report = client.get(path).json()
    assert report["objects"] == [] and report["authorized_not_reported"] == ["customers", "inventory"]
    app.dependency_overrides[admin] = lambda: {**A, "workspace_id": "other"}
    assert client.get(path).status_code == 403
    assert adapter.discovery_calls == 1



def test_csv_helper_separates_upload_metadata_from_bound_object_discovery():
    from core.bridge_connectors import CsvConnector
    from tests.test_bridge_export_file import CSV
    assert CsvConnector().discover() == []
    assert CsvConnector(CSV).discover() == []
    helper = CsvConnector(CSV, object_type="customers")
    assert helper.discover() == ["customers"]
    assert helper.upload_contract()["transport"] == "upload"
