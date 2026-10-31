from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from core import dealer_bridge as b, bridge_storage as storage
from core.dealeros import ledger
from core.entities import Entity

A = {"employee_id": "admin", "role": "ADMIN", "bridge_principal": "session"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    previous = ledger.entities, ledger.relationships
    ledger.entities, ledger.relationships = {}, []
    monkeypatch.setattr(b, "save_graph", lambda path: None)
    yield
    ledger.entities, ledger.relationships = previous


def test_unrelated_concurrent_entity_survives_failed_bridge_save(monkeypatch):
    def fail(path):
        ledger.add_entity(Entity("LEGACY-UNRELATED", "Customer", {"name": "Saved by another operation"}))
        raise OSError("disk unavailable")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(OSError): b.connect(A, "CSV", "Source")
    assert list(ledger.entities) == ["LEGACY-UNRELATED"]
    assert storage.current() is None


def test_untouched_field_survives_rollback_on_same_record(monkeypatch):
    source = b.connect(A, "CSV", "Source")["id"]
    before = deepcopy(ledger.get_entity(source).attributes)
    def fail(path):
        ledger.get_entity(source).attributes["other_module_note"] = "Concurrent edit"
        raise OSError("disk unavailable")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(OSError): b.set_system_paused(A, source, True, "Review source behavior")
    attributes = ledger.get_entity(source).attributes
    assert attributes == {**before, "other_module_note": "Concurrent edit"}


def test_same_field_conflict_is_preserved_and_reported(monkeypatch):
    source = b.connect(A, "CSV", "Source")["id"]
    def fail(path):
        ledger.get_entity(source).attributes["pause_reason"] = "Different concurrent action"
        raise OSError("disk unavailable")
    monkeypatch.setattr(b, "save_graph", fail)
    with pytest.raises(storage.PersistenceConflict): b.set_system_paused(A, source, True, "Original review reason")
    assert ledger.get_entity(source).attributes["pause_reason"] == "Different concurrent action"


def test_nested_mutations_commit_once_and_rollback_together(monkeypatch):
    calls = []
    monkeypatch.setattr(b, "save_graph", lambda path: calls.append(path))
    with b.mutation(A):
        b.connect(A, "CSV", "Source")
        b.connect(A, "CSV", "Second source")
    assert len(calls) == 1
    before = deepcopy(ledger.entities)
    with pytest.raises(ValueError):
        with b.mutation(A):
            b.connect(A, "CSV", "Third source")
            raise ValueError("abort")
    assert ledger.entities == before


def test_read_only_mutation_does_not_save(monkeypatch):
    source = b.connect(A, "CSV", "Source")["id"]
    def unexpected(path): raise AssertionError("No change should be persisted")
    monkeypatch.setattr(b, "save_graph", unexpected)
    with b.mutation(A):
        b.get(source, "BridgeSystem")


def test_system_map_never_exposes_uncommitted_bridge_mutation(monkeypatch):
    saving, release, reading = Event(), Event(), Event()
    def fail_save(path):
        saving.set()
        assert release.wait(3)
        raise OSError("Synthetic failed commit")
    monkeypatch.setattr(b, "save_graph", fail_save)
    def read():
        reading.set()
        return b.system_map(A)
    with ThreadPoolExecutor(max_workers=2) as workers:
        writer = workers.submit(b.connect, A, "CSV", "Uncommitted source")
        assert saving.wait(3)
        reader = workers.submit(read)
        assert reading.wait(3)
        try:
            assert not reader.done()
        finally:
            release.set()
        with pytest.raises(OSError): writer.result(timeout=3)
        assert reader.result(timeout=3)["systems"] == []
