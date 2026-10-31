"""Additive migration markers cannot reinterpret malformed or foreign state."""
from copy import deepcopy

import pytest

from core import dealer_bridge as bridge
from core.dealer_bridge_migrations import migrate, VERSION_ID
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, API, isolated  # noqa: F401


@pytest.mark.parametrize("version", [True, False, 1.0, "1", None, 0, 2, []])
def test_unsupported_marker_version_is_rejected_without_changes(version):
    ledger.add_entity(Entity(VERSION_ID, "BridgeSchemaVersion", {"version": version, "workspace_id": ledger.tenant.workspace_id}))
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError, match="Unsupported"):
        migrate(A)
    assert ledger.entities == before


@pytest.mark.parametrize("kind,workspace", [("Customer", None), ("BridgeSchemaVersion", "foreign-workspace")])
def test_conflicting_marker_identity_is_never_overwritten(kind, workspace):
    ledger.add_entity(Entity(VERSION_ID, kind, {"version": 1, "workspace_id": workspace or ledger.tenant.workspace_id}))
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError, match="not valid"):
        migrate(A)
    assert ledger.entities == before


def test_failed_migration_save_restores_marker_and_audit(monkeypatch):
    ledger.add_entity(Entity("legacy", "Connection", {"name": "Existing source"}))
    before = deepcopy(ledger.entities)
    def fail(_):
        raise OSError("Synthetic persistence failure")
    monkeypatch.setattr(bridge, "save_graph", fail)
    with pytest.raises(OSError):
        migrate(A)
    assert ledger.entities == before


def test_migration_requires_human_and_second_run_is_read_only(monkeypatch):
    with pytest.raises(PermissionError):
        migrate(API)
    assert not ledger.entities
    assert migrate(A) == {"version": 1, "changed": True}
    before = deepcopy(ledger.entities)
    monkeypatch.setattr(bridge, "save_graph", lambda _: pytest.fail("Idempotent migration must not save"))
    assert migrate(A) == {"version": 1, "changed": False}
    assert ledger.entities == before
    audits = [e for e in ledger.entities.values() if e.entity_type == "BridgeAudit"]
    assert len(audits) == 1 and audits[0].attributes["action"] == "schema.migrate.v1"



def test_migration_marker_and_legacy_records_survive_real_reload(tmp_path, monkeypatch):
    from core.storage import save_graph
    path = str(tmp_path / "migration-graph.json")
    monkeypatch.setattr(bridge, "save_graph", save_graph)
    monkeypatch.setattr(bridge, "GRAPH_PATH", path)
    ledger.add_entity(Entity("legacy", "Connection", {"name": "Existing source", "old_vendor_id": "unchanged"}))
    migrate(A)
    before = deepcopy(ledger.entities)
    ledger.reset()
    ledger.load(path)
    assert ledger.entities == before
    assert ledger.get_entity("legacy").attributes == {"name": "Existing source", "old_vendor_id": "unchanged"}
    assert migrate(A) == {"version": 1, "changed": False}
