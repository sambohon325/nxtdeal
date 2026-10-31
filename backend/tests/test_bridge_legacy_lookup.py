"""Imported vehicles remain reachable through established VIN intake lookups."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from core import dealer_bridge as b
from core.dealeros import ledger, registry
from core.entities import Entity
from core.ledger import DealerLedger
from core.registry import EntityRegistry, AmbiguousVehicleIdentity
from core.vehicle_intake import create_vehicle
from tests.test_dealer_bridge import A, B, setup, imported, isolated  # noqa: F401

VIN = "1HGCM82633A004352"


def test_bridge_vehicle_lookup_works_without_registry_mutation():
    system, _ = setup()
    mapping = b.propose_mapping(A, system, "Vehicle", "inventory", {"vin": {"source": "vin", "transform": "upper"}})["id"]
    b.approve_mapping(B, mapping)
    before = deepcopy(registry.vehicle_vins)
    imported(f"external_id,modified_at,vin\nv1,2026-01-01T00:00:00Z,{VIN}\n", mapping)
    target = next(entity for entity in ledger.get_all().values() if entity.entity_type == "Vehicle")
    assert registry.find_vehicle(VIN) == target.id
    assert registry.find_vehicle(VIN.lower()) == target.id
    assert registry.vehicle_vins == before
    vehicle, error = create_vehicle(VIN, 2003, "Honda", "Accord", "", "", 100, "Used", 1000, 500, "", "BHPH Used Lot")
    assert vehicle is None and "already exists" in error
    assert len([entity for entity in ledger.get_all().values() if entity.entity_type == "Vehicle"]) == 1


def test_lookup_tracks_graph_updates_without_stale_fallback_cache():
    local = DealerLedger()
    index = EntityRegistry(local)
    vehicle = Entity("V1", "Vehicle", {"vin": VIN})
    local.add_entity(vehicle)
    assert index.find_vehicle(VIN) == "V1"
    vehicle.attributes["vin"] = "1HGCM82633A004353"
    assert index.find_vehicle(VIN) is None
    assert index.find_vehicle("1HGCM82633A004353") == "V1"
    local.reset()
    assert index.find_vehicle("1HGCM82633A004353") is None


def test_duplicate_unindexed_vin_is_not_silently_linked():
    local = DealerLedger()
    index = EntityRegistry(local)
    for target in ["V1", "V2"]:
        local.add_entity(Entity(target, "Vehicle", {"VIN": VIN}))
    assert index.find_vehicle(VIN) is None
    with pytest.raises(AmbiguousVehicleIdentity): index.find_vehicle(VIN, require_unique=True)
    assert index.vehicle_vins == {}


def test_fallback_is_workspace_scoped_and_vehicle_only():
    local = DealerLedger()
    index = EntityRegistry(local)
    local.add_entity(Entity("OTHER", "Customer", {"VIN": VIN}))
    local.add_entity(Entity("FOREIGN", "Vehicle", {"VIN": VIN, "workspace_id": "foreign"}))
    assert index.find_vehicle(VIN) is None
    assert index.find_vehicle(None) is None and index.find_vehicle("") is None


def test_independent_registry_retains_original_semantics():
    index = EntityRegistry()
    assert index.find_vehicle(VIN) is None
    index.register_vehicle(VIN, "registered")
    assert index.find_vehicle(VIN) == "registered"
    assert index.find_vehicle(VIN.lower()) is None


def test_legacy_inventory_import_skips_bridge_vehicle_without_duplicate(tmp_path):
    from imports.inventory_import import import_inventory
    ledger.add_entity(Entity("BRIDGE-V", "Vehicle", {"vin": VIN, "workspace_id": ledger.tenant.workspace_id}))
    path = tmp_path / "inventory.csv"
    path.write_text(f"VIN,Year,Make,Model\n{VIN},2003,Honda,Accord\n", encoding="utf-8")
    assert import_inventory(str(path)) == (0, 1)
    assert list(ledger.entities) == ["BRIDGE-V"]


def test_native_intake_reports_ambiguous_graph_identity_without_mutation():
    for target in ["V1", "V2"]:
        ledger.add_entity(Entity(target, "Vehicle", {"VIN": VIN}))
    before = deepcopy(ledger.entities)
    vehicle, error = create_vehicle(VIN, 2003, "Honda", "Accord", "", "", 100, "Used", 1000, 500, "", "BHPH Used Lot")
    assert vehicle is None and "multiple vehicles" in error
    assert ledger.entities == before


def test_fallback_cannot_link_a_vehicle_from_failed_bridge_commit(monkeypatch):
    saving, release, reading = Event(), Event(), Event()
    def fail(_):
        saving.set()
        assert release.wait(5)
        raise OSError("Synthetic save failure")
    monkeypatch.setattr(b, "save_graph", fail)
    def create():
        with b.mutation(A):
            b.add("Vehicle", {"vin": VIN})
    def lookup():
        reading.set()
        return registry.find_vehicle(VIN)
    with ThreadPoolExecutor(max_workers=2) as workers:
        writer = workers.submit(create)
        assert saving.wait(5)
        reader = workers.submit(lookup)
        assert reading.wait(5)
        try:
            assert not reader.done()
        finally:
            release.set()
        with pytest.raises(OSError): writer.result(timeout=5)
        assert reader.result(timeout=5) is None
