"""Concurrent persistence must not serialize tentative Bridge mutations."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from core import dealer_bridge as bridge
from core.dealeros import ledger
from core.entities import Entity
from core.ledger import DealerLedger


def test_concurrent_saves_wait_before_snapshot_and_swap(tmp_path, monkeypatch):
    local = DealerLedger()
    local.add_entity(Entity("A", "Customer", {"name": "Original"}))
    path = str(tmp_path / "graph.json")
    encoding, release, second_started = Event(), Event(), Event()
    original_dump = json.dump
    calls = []

    def encode(data, output, **kwargs):
        calls.append(data)
        if len(calls) == 1:
            encoding.set()
            assert release.wait(5)
        return original_dump(data, output, **kwargs)

    def second_save():
        second_started.set()
        local.save(path)

    monkeypatch.setattr(json, "dump", encode)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(local.save, path)
        assert encoding.wait(5)
        local.get_entity("A").attributes["name"] = "Later"
        second = workers.submit(second_save)
        assert second_started.wait(5)
        try:
            assert len(calls) == 1
            assert not second.done()
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert calls[0]["entities"][0]["attributes"]["name"] == "Original"
    assert json.loads(tmp_path.joinpath("graph.json").read_text())["entities"][0]["attributes"]["name"] == "Later"
    assert not tmp_path.joinpath("graph.json.tmp").exists()


@pytest.mark.parametrize("commit", [False, True])
def test_other_save_waits_for_bridge_commit_or_rollback(tmp_path, monkeypatch, commit):
    previous = ledger.entities, ledger.relationships
    ledger.entities, ledger.relationships = {}, []
    saving, release, other_started = Event(), Event(), Event()
    path = str(tmp_path / "graph.json")
    actor = {"employee_id": "admin", "role": "ADMIN", "bridge_principal": "session"}

    def bridge_save(_):
        saving.set()
        assert release.wait(5)
        if not commit:
            raise OSError("Synthetic save failure")
        ledger.save(path)  # Reentrant: Bridge already holds the shared guard.

    def other_save():
        # Existing domain modules may still mutate directly. Preserve that work.
        ledger.add_entity(Entity("LEGACY", "Customer", {"name": "Independent"}))
        other_started.set()
        ledger.save(path)

    monkeypatch.setattr(bridge, "save_graph", bridge_save)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            writer = workers.submit(bridge.connect, actor, "CSV", "Tentative")
            assert saving.wait(5)
            other = workers.submit(other_save)
            assert other_started.wait(5)
            try:
                assert not other.done()
                assert not tmp_path.joinpath("graph.json").exists()
            finally:
                release.set()
            if commit:
                source = writer.result(timeout=5)
            else:
                with pytest.raises(OSError, match="Synthetic"):
                    writer.result(timeout=5)
            other.result(timeout=5)
        persisted = json.loads(tmp_path.joinpath("graph.json").read_text())["entities"]
        assert any(row["id"] == "LEGACY" for row in persisted)
        if commit:
            assert any(row["id"] == source["id"] for row in persisted)
        else:
            assert [row["id"] for row in persisted] == ["LEGACY"]
    finally:
        ledger.entities, ledger.relationships = previous


def test_guard_releases_after_encoding_failure(tmp_path):
    local = DealerLedger()
    local.add_entity(Entity("A", "Customer", {"bad": object()}))
    path = str(tmp_path / "graph.json")
    with pytest.raises(TypeError):
        local.save(path)
    local.get_entity("A").attributes = {"recovered": True}
    with ThreadPoolExecutor(max_workers=1) as worker:
        worker.submit(local.save, path).result(timeout=5)
    assert json.loads(tmp_path.joinpath("graph.json").read_text())["entities"][0]["attributes"] == {"recovered": True}
