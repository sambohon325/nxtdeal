"""Characterize the legacy mutation/persistence boundary before SQL migration."""

import json

import pytest

from core.entities import Entity
from core.json_graph_repository import JsonGraphRepository
from core.ledger import DealerLedger
from core.postgres_graph_repository import PostgresGraphRepository
from core.relationships import Relationship
from core.tenant_context import TenantContext


def test_live_mutation_and_explicit_save_round_trip(tmp_path):
    repo = JsonGraphRepository(TenantContext("workspace-a"))
    facade = DealerLedger(repo)
    item = Entity("VEH-1", "Vehicle", {"price": 100})
    assert facade.add_entity(item) is None
    assert facade.get_entity("VEH-1") is item
    facade.get_all()["VEH-1"].attributes["price"] = 200
    rel = Relationship("CUST-1", "VEH-1", "OWNS", "employee", "2026-09-30")
    facade.add_relationship(rel)
    facade.get_relationships().append(rel)  # duplicates/order remain supported
    path = str(tmp_path / "graph.json")
    assert not tmp_path.joinpath("graph.json").exists()
    facade.save(path)
    reopened = DealerLedger(JsonGraphRepository(TenantContext("workspace-a")))
    assert reopened.load(path) is True
    assert reopened.get_entity("VEH-1").attributes == {"price": 200}
    assert reopened.get_entity_relationships("CUST-1") == [rel, rel]
    assert reopened.get_entity_relationships("VEH-1") == [rel, rel]
    assert reopened.get_entity("missing") is None


def test_load_merges_and_accepts_legacy_relationship_provenance(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({
        "entities": [{"id": "A", "entity_type": "Vehicle", "attributes": {"loaded": True}}],
        "relationships": [{"source_id": "A", "target_id": "B", "relationship_type": "LINK"}],
    }), encoding="utf-8")
    facade = DealerLedger(tenant=TenantContext("a"))
    facade.add_entity(Entity("A", "Vehicle", {"old": True}))
    facade.add_entity(Entity("B", "Customer", {}))
    facade.load(str(path))
    facade.load(str(path))
    assert set(facade.get_all()) == {"A", "B"}
    assert facade.get_entity("A").attributes == {"loaded": True}
    assert len(facade.get_relationships()) == 2
    assert facade.get_relationships()[0].created_by is None


def test_missing_and_malformed_file_behavior(tmp_path):
    facade = DealerLedger()
    facade.add_entity(Entity("A", "Customer", {}))
    assert facade.load(str(tmp_path / "missing")) is False
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        facade.load(str(path))
    assert facade.get_entity("A") is not None


def test_demo_never_creates_or_overwrites_files(tmp_path, monkeypatch):
    facade = DealerLedger()
    path = tmp_path / "graph.json"
    path.write_text("original", encoding="utf-8")
    monkeypatch.setenv("DEALEROS_DEMO", "true")
    facade.add_entity(Entity("A", "Customer", {}))
    facade.save(str(path))
    facade.save(str(tmp_path / "new" / "graph.json"))
    assert path.read_text(encoding="utf-8") == "original"
    assert not (tmp_path / "new").exists()
    assert not (tmp_path / "graph.json.tmp").exists()


def test_two_bound_repositories_do_not_share_collections():
    first = DealerLedger(tenant=TenantContext("a", "group"))
    second = DealerLedger(tenant=TenantContext("b", "group"))
    first.add_entity(Entity("same-id", "Customer", {"name": "first"}))
    second.add_entity(Entity("same-id", "Customer", {"name": "second"}))
    first.add_relationship(Relationship("same-id", "vehicle", "OWNS"))
    first.reset()
    assert first.get_all() == {}
    assert second.get_entity("same-id").attributes["name"] == "second"
    assert second.get_relationships() == []


def test_context_cannot_be_rebound_or_mismatched():
    repo = JsonGraphRepository(TenantContext("a"))
    with pytest.raises(ValueError):
        DealerLedger(repo, tenant=TenantContext("b"))
    with pytest.raises(AttributeError):
        repo.tenant = TenantContext("b")


@pytest.mark.parametrize("workspace", ["", " ", " a", None])
def test_invalid_workspace_context_rejected(workspace):
    with pytest.raises(ValueError):
        TenantContext(workspace)


def test_postgres_scaffold_fails_before_any_work_can_run():
    with pytest.raises(NotImplementedError, match="not available"):
        PostgresGraphRepository(TenantContext("a"))


def test_collection_assignment_and_reset_keep_legacy_semantics():
    facade = DealerLedger()
    entities = {"A": Entity("A", "Customer", {})}
    relationships = [Relationship("A", "B", "LINK")]
    facade.entities = entities
    facade.relationships = relationships
    assert facade.get_all() is entities
    assert facade.get_relationships() is relationships
    facade.reset()
    assert facade.get_all() == {} and facade.get_all() is not entities
    assert facade.get_relationships() == [] and facade.get_relationships() is not relationships


def test_flush_failure_preserves_previous_snapshot_and_retry_succeeds(tmp_path, monkeypatch):
    from core import json_graph_repository as storage
    facade = DealerLedger(tenant=TenantContext("flush-test"))
    path = tmp_path / "graph.json"
    facade.add_entity(Entity("A", "Customer", {"version": 1}))
    facade.save(str(path))
    previous = path.read_bytes()
    facade.get_entity("A").attributes["version"] = 2
    real_fsync = storage.os.fsync
    observed = []

    def fail_flush(descriptor):
        # Buffered JSON must already be visible in the temporary file.
        snapshot = json.loads((tmp_path / "graph.json.tmp").read_text(encoding="utf-8"))
        observed.append(snapshot["entities"][0]["attributes"]["version"])
        raise OSError("Synthetic storage flush failure")

    monkeypatch.setattr(storage.os, "fsync", fail_flush)
    with pytest.raises(OSError, match="flush failure"):
        facade.save(str(path))
    assert observed == [2]
    assert path.read_bytes() == previous
    monkeypatch.setattr(storage.os, "fsync", real_fsync)
    facade.save(str(path))
    reopened = DealerLedger(tenant=TenantContext("flush-test"))
    reopened.load(str(path))
    assert reopened.get_entity("A").attributes == {"version": 2}
    assert not (tmp_path / "graph.json.tmp").exists()
