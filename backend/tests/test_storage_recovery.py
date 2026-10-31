"""
Regression tests for the boot-critical-storage hardening added in sessions 42-44:

  - core/audit_storage.py   (session 42): atomic save + _recover_partial_array on load
  - core/storage.py         (session 43): atomic save_graph (load has no JSON-recovery
                                          path, deliberately -- the atomic write IS the fix
                                          for the whole ~4MB database file), AND
                            (session 42): load_graph()'s _recover_id_counters() step, which
                                          bumps the in-memory IDGenerator counters past the
                                          highest already-loaded id per prefix so the first
                                          live-created entity after a restart can't reuse
                                          an id (e.g. "VEH-00001") and silently overwrite a
                                          real seeded entity via the ledger's no-collision-
                                          check dict write
  - core/auth_storage.py    (session 44): atomic save + _recover_partial_object on load

Those sessions verified this behavior with throwaway isolation tests run in /tmp and never
committed a permanent test for it, so a future edit to any of the three loaders could
silently reintroduce the "truncated JSON file bricks the backend on boot" bug with nothing
to catch it. This file is that permanent guard. It matches CLAUDE.md's "convert to a real
backend/tests/ pytest suite as each module gets touched" directive -- those three modules
were the ones just touched.

Two things are asserted for each hardened module:
  1. Atomic write -- save_* leaves the real file present and no leftover ".tmp" sibling,
     and overwriting an existing file works (os.replace swap).
  2. Corrupt/truncated recovery -- a half-written file recovers every COMPLETE record and
     drops only the partial trailing one, instead of raising and stopping boot.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import audit as audit_module
from core import auth as auth_module
from core import dealeros

from core.audit_storage import (
    save_audit_log,
    load_audit_log,
    _recover_partial_array,
)
from core.auth_storage import (
    save_credentials,
    load_credentials,
    _recover_partial_object,
)
from core.storage import save_graph, load_graph, _recover_id_counters

from core.entities import Entity
from core.relationships import Relationship


# --------------------------------------------------------------------------------------
# Fixtures -- reset the singletons in place (never swap the object identity, per the note
# in test_audit.py: the *_storage.py modules hold a direct reference to each singleton).
# --------------------------------------------------------------------------------------

def _reset_id_counters():
    # IDGenerator has no reset() method and core/storage.py holds a direct reference to the
    # dealeros.id_generator singleton, so mutate its counters dict in place (same "never swap
    # object identity" rule as the other singletons) rather than reassigning a fresh one.
    for prefix in dealeros.id_generator.counters:
        dealeros.id_generator.counters[prefix] = 0


@pytest.fixture(autouse=True)
def fresh_singletons():

    audit_module.audit_log.reset()
    auth_module.credential_store.reset()
    dealeros.ledger.reset()
    _reset_id_counters()

    yield

    audit_module.audit_log.reset()
    auth_module.credential_store.reset()
    dealeros.ledger.reset()
    _reset_id_counters()


# --------------------------------------------------------------------------------------
# core/audit_storage.py
# --------------------------------------------------------------------------------------

def test_audit_save_is_atomic_and_leaves_no_tmp(tmp_path):

    audit_module.audit_log.record(
        event_type="lead_assigned",
        summary="assigned",
        entity_id="LEAD-1",
        actor="routing_engine",
    )

    filepath = str(tmp_path / "audit.json")

    save_audit_log(filepath)

    assert os.path.exists(filepath)
    assert not os.path.exists(filepath + ".tmp")


def test_audit_save_overwrites_existing_file(tmp_path):

    filepath = str(tmp_path / "audit.json")

    audit_module.audit_log.record("a", "first")
    save_audit_log(filepath)

    # A second save must atomically replace the first file, not fail or leave a .tmp.
    audit_module.audit_log.record("b", "second")
    save_audit_log(filepath)

    assert not os.path.exists(filepath + ".tmp")

    audit_module.audit_log.reset()
    load_audit_log(filepath)

    assert len(audit_module.audit_log.get_all()) == 2


def test_recover_partial_array_drops_only_the_truncated_entry():

    # Two complete objects, then a dangling half-written third with no closing brace --
    # the exact shape an interrupted json.dump leaves behind.
    truncated = (
        '[\n'
        '    {"id": "AUDIT-00001", "event_type": "x", "entity_id": null,'
        ' "actor": "system", "summary": "s1", "details": {}, "timestamp": "t1"},\n'
        '    {"id": "AUDIT-00002", "event_type": "y", "entity_id": null,'
        ' "actor": "system", "summary": "s2", "details": {}, "timestamp": "t2"},\n'
        '    {"id": "AUDIT-000'
    )

    recovered = _recover_partial_array(truncated)

    assert isinstance(recovered, list)
    assert len(recovered) == 2
    assert [item["id"] for item in recovered] == ["AUDIT-00001", "AUDIT-00002"]


def test_recover_partial_array_returns_empty_when_nothing_salvageable():

    assert _recover_partial_array("[\n    {") == []      # no closing brace at all
    assert _recover_partial_array("not json at all") == []


def test_load_audit_log_recovers_from_truncated_file(tmp_path):

    filepath = str(tmp_path / "audit.json")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(
            '[\n'
            '    {"id": "AUDIT-00001", "event_type": "lead_assigned", "entity_id": "LEAD-1",'
            ' "actor": "system", "summary": "s1", "details": {}, "timestamp": "t1"},\n'
            '    {"id": "AUDIT-00002", "event_type": "lead_escalated", "entity_id": "LEAD-2",'
            ' "actor": "system", "summary": "s2", "details": {}, "timestamp": "t2"},\n'
            '    {"id": "AUDIT-00'
        )

    # Must NOT raise -- a truncated audit log cannot be allowed to stop the backend booting.
    load_audit_log(filepath)

    events = audit_module.audit_log.get_all()

    assert len(events) == 2
    assert {e.id for e in events} == {"AUDIT-00001", "AUDIT-00002"}


def test_load_audit_log_missing_file_is_noop(tmp_path):

    load_audit_log(str(tmp_path / "nope.json"))

    assert audit_module.audit_log.get_all() == []


# --------------------------------------------------------------------------------------
# core/auth_storage.py
# --------------------------------------------------------------------------------------

def test_credentials_save_is_atomic_and_leaves_no_tmp(tmp_path):

    auth_module.credential_store.set_credential("E1001", "pw", "SALES")

    filepath = str(tmp_path / "credentials.json")

    save_credentials(filepath)

    assert os.path.exists(filepath)
    assert not os.path.exists(filepath + ".tmp")


def test_credentials_save_load_round_trip(tmp_path):

    auth_module.credential_store.set_credential("E1001", "pw", "SALES")
    auth_module.credential_store.set_credential("E1002", "pw", "ADMIN")

    filepath = str(tmp_path / "credentials.json")
    save_credentials(filepath)

    auth_module.credential_store.reset()
    load_credentials(filepath)

    assert set(auth_module.credential_store.credentials.keys()) == {"E1001", "E1002"}


def test_recover_partial_object_drops_only_the_truncated_record():

    truncated = (
        '{\n'
        '    "E1001": {"salt": "a", "hash": "b", "role": "SALES"},\n'
        '    "E1002": {"salt": "c", "hash": "d'
    )

    recovered = _recover_partial_object(truncated)

    assert isinstance(recovered, dict)
    assert set(recovered.keys()) == {"E1001"}


def test_recover_partial_object_handles_brace_inside_partial_record():

    # The partial trailing record contains a nested "}" -- the naive single-rfind would
    # produce invalid JSON here, so this proves the walk-back loop is doing its job.
    truncated = (
        '{\n'
        '    "E1001": {"salt": "a", "hash": "b", "role": "SALES"},\n'
        '    "E1002": {"role": "ADMIN", "meta": {"x": 1}'
    )

    recovered = _recover_partial_object(truncated)

    assert set(recovered.keys()) == {"E1001"}


def test_recover_partial_object_returns_empty_when_nothing_salvageable():

    assert _recover_partial_object("{\n    \"E1001\": {") == {}
    assert _recover_partial_object("garbage") == {}


def test_load_credentials_recovers_from_truncated_file(tmp_path):

    filepath = str(tmp_path / "credentials.json")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(
            '{\n'
            '    "E1001": {"salt": "a", "hash": "b", "role": "SALES"},\n'
            '    "E1002": {"salt": "c", "hash": "d'
        )

    # Must NOT raise -- a truncated credentials file would otherwise both crash boot and
    # lock everyone out of login.
    load_credentials(filepath)

    assert set(auth_module.credential_store.credentials.keys()) == {"E1001"}


def test_load_credentials_missing_file_is_noop(tmp_path):

    load_credentials(str(tmp_path / "nope.json"))

    assert auth_module.credential_store.credentials == {}


# --------------------------------------------------------------------------------------
# core/storage.py (graph) -- atomic save; load_graph deliberately has no recovery path,
# so we only assert the write-side guarantee plus a clean round-trip.
# --------------------------------------------------------------------------------------

def test_save_graph_is_atomic_and_round_trips(tmp_path):

    dealeros.ledger.add_entity(
        Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Toyota"})
    )
    dealeros.ledger.add_entity(
        Entity(id="CUS-00001", entity_type="Customer", attributes={"Name": "Sam"})
    )
    dealeros.ledger.add_relationship(
        Relationship(
            source_id="CUS-00001",
            target_id="VEH-00001",
            relationship_type="OWNS",
        )
    )

    filepath = str(tmp_path / "graph.json")

    save_graph(filepath)

    assert os.path.exists(filepath)
    assert not os.path.exists(filepath + ".tmp")

    dealeros.ledger.reset()
    load_graph(filepath)

    assert set(dealeros.ledger.get_all().keys()) == {"VEH-00001", "CUS-00001"}
    assert len(dealeros.ledger.get_relationships()) == 1
    assert dealeros.ledger.get_all()["VEH-00001"].attributes["Make"] == "Toyota"


def test_save_graph_overwrites_existing_file(tmp_path):

    filepath = str(tmp_path / "graph.json")

    dealeros.ledger.add_entity(
        Entity(id="VEH-00001", entity_type="Vehicle", attributes={})
    )
    save_graph(filepath)

    dealeros.ledger.add_entity(
        Entity(id="VEH-00002", entity_type="Vehicle", attributes={})
    )
    save_graph(filepath)

    assert not os.path.exists(filepath + ".tmp")

    dealeros.ledger.reset()
    load_graph(filepath)

    assert set(dealeros.ledger.get_all().keys()) == {"VEH-00001", "VEH-00002"}


# --------------------------------------------------------------------------------------
# core/storage.py -- _recover_id_counters(): the session-42 fix that stops a post-restart
# live-created entity from reusing an id and silently overwriting a real seeded entity.
# --------------------------------------------------------------------------------------

def test_recover_id_counters_bumps_past_highest_loaded_id_per_prefix():

    dealeros.ledger.add_entity(
        Entity(id="VEH-00500", entity_type="Vehicle", attributes={})
    )
    dealeros.ledger.add_entity(
        Entity(id="VEH-00123", entity_type="Vehicle", attributes={})
    )
    dealeros.ledger.add_entity(
        Entity(id="LEAD-01000", entity_type="Lead", attributes={})
    )

    _recover_id_counters()

    # highest seen per prefix, not just the last-added one
    assert dealeros.id_generator.counters["VEH"] == 500
    assert dealeros.id_generator.counters["LEAD"] == 1000

    # untouched prefixes stay at 0
    assert dealeros.id_generator.counters["DEAL"] == 0


def test_recover_id_counters_next_generate_cannot_collide_with_loaded_entity():
    # This is the actual bug the fix exists for: without recovery, the first live-created
    # Vehicle after a restart would generate "VEH-00001" and overwrite the real one.
    dealeros.ledger.add_entity(
        Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Toyota"})
    )
    dealeros.ledger.add_entity(
        Entity(id="VEH-00002", entity_type="Vehicle", attributes={"Make": "Honda"})
    )

    _recover_id_counters()

    new_id = dealeros.id_generator.generate("VEH")

    assert new_id == "VEH-00003"
    assert new_id not in dealeros.ledger.get_all()


def test_recover_id_counters_ignores_non_matching_ids():
    # ids that don't match the PREFIX-<digits> shape must be skipped, not raise.
    dealeros.ledger.add_entity(
        Entity(id="not-an-id", entity_type="Vehicle", attributes={})
    )
    dealeros.ledger.add_entity(
        Entity(id="veh-00099", entity_type="Vehicle", attributes={})  # lowercase prefix
    )
    dealeros.ledger.add_entity(
        Entity(id="VEH-00007", entity_type="Vehicle", attributes={})
    )

    _recover_id_counters()

    assert dealeros.id_generator.counters["VEH"] == 7


def test_recover_id_counters_skips_unknown_prefix_without_error():
    # A well-formed id whose prefix isn't in the counters dict must be skipped (no KeyError).
    dealeros.ledger.add_entity(
        Entity(id="XYZ-00042", entity_type="Vehicle", attributes={})
    )

    _recover_id_counters()  # must not raise

    assert "XYZ" not in dealeros.id_generator.counters


def test_recover_id_counters_never_lowers_an_existing_counter():
    dealeros.id_generator.counters["VEH"] = 900

    dealeros.ledger.add_entity(
        Entity(id="VEH-00010", entity_type="Vehicle", attributes={})
    )

    _recover_id_counters()

    # a lower loaded id must not drag the counter back down
    assert dealeros.id_generator.counters["VEH"] == 900


def test_load_graph_recovers_id_counters_end_to_end(tmp_path):
    # load_graph() calls _recover_id_counters() as its last step -- prove the whole path.
    dealeros.ledger.add_entity(
        Entity(id="VEH-00250", entity_type="Vehicle", attributes={})
    )
    dealeros.ledger.add_entity(
        Entity(id="CAMP-00030", entity_type="Campaign", attributes={})
    )

    filepath = str(tmp_path / "graph.json")
    save_graph(filepath)

    dealeros.ledger.reset()
    _reset_id_counters()

    load_graph(filepath)

    assert dealeros.id_generator.counters["VEH"] == 250
    assert dealeros.id_generator.counters["CAMP"] == 30
    assert dealeros.id_generator.generate("VEH") == "VEH-00251"
