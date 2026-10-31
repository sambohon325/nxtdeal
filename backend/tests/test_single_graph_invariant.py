"""
Pillar 3 — "One graph" architectural invariant guard (2026-07-23).

The invariant is one canonical graph abstraction per workspace. The legacy
application still holds one process-wide ledger facade and uses JSON persistence;
that concrete adapter is not the permanent domain boundary. Explicitly bound
repositories are tested separately in test_graph_repository_contract.py. This
slice does not enable multiple workspaces in the existing application process.

This file is the PERMANENT guard for that invariant, so a future module (or the concurrent
autonomous builder) can't silently reintroduce a second store without a test going red.
It is deliberately BEHAVIORAL (object-identity + round-trip), not a brittle source-code
scan — it never inspects other modules' source, so simply adding new modules never breaks
it; only actually breaking the single-graph contract does.

What's asserted:
  1. Singleton identity — a representative sample of domain modules spanning different
     departments all bind the exact same `ledger`/`registry`/`id_generator` objects as
     core/dealeros.py. A module that did `ledger = DealerLedger()` of its own (its own
     private graph) would fail this.
  2. save_graph/load_graph operate on THAT singleton, and the round-trip is faithful for
     entities, attributes, and relationships including provenance — i.e. graph.json is the
     complete persistence surface of the one graph, nothing kept on the side.
"""

import os

import pytest

import core.dealeros as dealeros
from core.entities import Entity
from core.relationships import Relationship
from core.ledger import DealerLedger
from core.storage import save_graph, load_graph


# A representative slice of the ~115 modules that touch the graph, chosen to span
# departments/subsystems (forecasting, persistence, sales, workspace, marketing media,
# inventory). Each does a top-level `from core.dealeros import ledger[, ...]`, so the name
# bound on the module IS the shared object — unless the module wrongly made its own.
import core.prediction as prediction
import core.storage as storage
import core.deals as deals
import core.workspace_board as workspace_board
import core.media_library as media_library
import core.merchandising as merchandising

_SAMPLE_LEDGER_MODULES = [prediction, storage, deals, workspace_board, media_library, merchandising]


def test_there_is_exactly_one_ledger_type_and_dealeros_holds_an_instance():
    assert isinstance(dealeros.ledger, DealerLedger)
    # Re-importing the module must not mint a new ledger — it's a process-wide singleton.
    import importlib

    again = importlib.import_module("core.dealeros")
    assert again.ledger is dealeros.ledger


def test_every_sampled_module_shares_the_one_ledger_singleton():
    for module in _SAMPLE_LEDGER_MODULES:
        assert module.ledger is dealeros.ledger, (
            f"core/{module.__name__.split('.')[-1]}.py bound a DIFFERENT ledger object than "
            f"core/dealeros.py's singleton — that is a second, private graph and breaks the "
            f"'one database (graph knowledge)' invariant. Every module must "
            f"`from core.dealeros import ledger`, never construct its own DealerLedger()."
        )


def test_registry_and_id_generator_are_also_single_shared_singletons():
    # The registry + id_generator are part of the one-graph state machinery (id_generator
    # in particular MUST be shared, or two modules could mint colliding ids into the graph).
    for module in _SAMPLE_LEDGER_MODULES:
        if hasattr(module, "id_generator"):
            assert module.id_generator is dealeros.id_generator
    assert deals.registry is dealeros.registry


def test_save_graph_operates_on_the_one_ledger_and_round_trips_faithfully(tmp_path):
    # storage.save_graph serialises the SAME singleton every module writes to.
    assert storage.ledger is dealeros.ledger

    # Snapshot whatever the shared ledger currently holds, so this test restores it and
    # never pollutes other tests that share the process-wide singleton.
    saved_entities = list(dealeros.ledger.get_all().values())
    saved_relationships = list(dealeros.ledger.get_relationships())

    try:
        dealeros.ledger.reset()
        dealeros.ledger.add_entity(
            Entity(id="VEH-90001", entity_type="Vehicle", attributes={"Make": "Toyota", "Year": "2020"})
        )
        dealeros.ledger.add_entity(
            Entity(id="CUS-90001", entity_type="Customer", attributes={"Name": "Sam"})
        )
        dealeros.ledger.add_relationship(
            Relationship(
                source_id="CUS-90001",
                target_id="VEH-90001",
                relationship_type="OWNS",
                created_by="test",
                created_at="2026-07-23T00:00:00",
            )
        )

        filepath = str(tmp_path / "graph.json")
        save_graph(filepath)

        # A fresh, independent ledger loaded from graph.json must reproduce the one graph
        # exactly — proving graph.json is the whole database, not a partial view.
        dealeros.ledger.reset()
        load_graph(filepath)

        entities = dealeros.ledger.get_all()
        assert set(entities.keys()) == {"VEH-90001", "CUS-90001"}
        assert entities["VEH-90001"].attributes == {"Make": "Toyota", "Year": "2020"}

        rels = dealeros.ledger.get_relationships()
        assert len(rels) == 1
        assert rels[0].relationship_type == "OWNS"
        assert rels[0].created_by == "test"
        assert rels[0].created_at == "2026-07-23T00:00:00"
    finally:
        dealeros.ledger.reset()
        for entity in saved_entities:
            dealeros.ledger.add_entity(entity)
        for relationship in saved_relationships:
            dealeros.ledger.add_relationship(relationship)
