"""
Tests for core/data_backup.py -- Administration's Data Management item: real
per-entity-type CSV export off the live graph, and a real graph.json backup/
restore action wrapping core/storage.py's own save_graph()/load_graph().

Backup/restore genuinely touches disk -- GRAPH_PATH is a module-level constant
frozen at import time (core/storage_paths.py computes it once, not re-read per
call, unlike storage_dir()/backups_dir() which read fresh every call), so these
tests monkeypatch data_backup.GRAPH_PATH and data_backup.backups_dir directly to
a real tmp_path, then let the real save_graph()/load_graph() functions run
against that isolated location -- the only way to meaningfully exercise real
file-copy backup/restore behavior.

Restore installs the independently parsed snapshot as replacement state. Tests
cover removal of post-snapshot entities and relationships without changing the
general legacy loader, and report when a backup predates its own catalog entry.

Run from backend/ with `pytest`.
"""

import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, DATA_BACKUP
from core import data_backup


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def isolated_backup_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(data_backup, "GRAPH_PATH", str(tmp_path / "graph.json"))
    monkeypatch.setattr(data_backup, "backups_dir", lambda: str(tmp_path / "backups"))
    return tmp_path


def _make_customer(customer_id, **attrs):
    entity = Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _write_real_graph_file(path):
    """Uses the real save_graph() against the currently-monkeypatched GRAPH_PATH
    to produce a real graph.json a create_backup() call can copy."""
    data_backup.save_graph(path)


class TestExportEntityTypeCsv:

    def test_no_entities_of_the_given_type_returns_an_error(self):
        filename, result = data_backup.export_entity_type_csv(CUSTOMER)

        assert filename is None
        assert "error" in result
        assert CUSTOMER in result["error"]

    def test_returns_a_real_filename_and_csv_text_for_matching_entities(self):
        _make_customer("CUST-1", FirstName="Joseph")

        filename, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        assert filename.startswith(f"{CUSTOMER}_export_")
        assert filename.endswith(".csv")
        assert "CUST-1" in csv_text
        assert "Joseph" in csv_text

    def test_id_column_is_always_first(self):
        _make_customer("CUST-1", FirstName="Joseph")

        _, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert header[0] == "id"

    def test_column_set_is_the_union_of_attributes_across_all_matching_entities(self):
        _make_customer("CUST-1", FirstName="Joseph")
        _make_customer("CUST-2", LastName="King")

        _, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert set(reader.fieldnames) == {"id", "FirstName", "LastName"}
        assert len(rows) == 2

    def test_missing_attribute_values_render_as_empty_cells_not_errors(self):
        _make_customer("CUST-1", FirstName="Joseph")
        _make_customer("CUST-2", LastName="King")

        _, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = {row["id"]: row for row in reader}
        assert rows["CUST-1"]["LastName"] == ""
        assert rows["CUST-2"]["FirstName"] == ""

    def test_dict_and_list_attribute_values_are_json_serialized(self):
        _make_customer("CUST-1", tags=["vip", "repeat"], meta={"score": 5})

        _, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        reader = csv.DictReader(io.StringIO(csv_text))
        row = next(reader)
        assert json.loads(row["tags"]) == ["vip", "repeat"]
        assert json.loads(row["meta"]) == {"score": 5}

    def test_only_entities_of_the_requested_type_are_included(self):
        _make_customer("CUST-1")
        vehicle = Entity(id="VEH-1", entity_type=VEHICLE, attributes={})
        ledger.add_entity(vehicle)

        _, csv_text = data_backup.export_entity_type_csv(CUSTOMER)

        assert "VEH-1" not in csv_text


class TestListExportableEntityTypes:

    def test_empty_ledger_returns_an_empty_dict(self):
        assert data_backup.list_exportable_entity_types() == {}

    def test_returns_real_counts_per_entity_type(self):
        _make_customer("CUST-1")
        _make_customer("CUST-2")
        ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))

        result = data_backup.list_exportable_entity_types()

        assert result[CUSTOMER] == 2
        assert result[VEHICLE] == 1

    def test_result_is_sorted_by_count_descending(self):
        _make_customer("CUST-1")
        _make_customer("CUST-2")
        _make_customer("CUST-3")
        ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))

        result = data_backup.list_exportable_entity_types()

        assert list(result.keys())[0] == CUSTOMER


class TestCreateBackup:

    def test_no_graph_file_exists_returns_an_error_and_creates_no_entity(self):
        result = data_backup.create_backup("EMP-1")

        assert "error" in result
        assert data_backup.list_backups() == []

    def test_a_real_graph_file_produces_a_real_backup_file_on_disk(self, isolated_backup_paths):
        _make_customer("CUST-1")
        _write_real_graph_file(data_backup.GRAPH_PATH)

        result = data_backup.create_backup("EMP-1", label="pre-migration")

        assert "error" not in result
        assert os.path.exists(result["path"])
        with open(result["path"]) as f:
            content = json.load(f)
        assert any(e["id"] == "CUST-1" for e in content["entities"])

    def test_returns_the_real_attribute_shape(self, isolated_backup_paths):
        _write_real_graph_file(data_backup.GRAPH_PATH)

        result = data_backup.create_backup("EMP-1", label="nightly")

        assert result["label"] == "nightly"
        assert result["created_by"] == "EMP-1"
        assert result["created_at"] is not None
        assert result["restored_at"] is None
        assert result["restored_by"] is None
        assert result["size_bytes"] > 0
        assert result["filename"].startswith("graph_")
        assert result["filename"].endswith(".json")

    def test_label_defaults_to_empty_string_when_not_given(self, isolated_backup_paths):
        _write_real_graph_file(data_backup.GRAPH_PATH)

        result = data_backup.create_backup("EMP-1")

        assert result["label"] == ""

    def test_the_backup_entity_is_added_to_the_ledger(self, isolated_backup_paths):
        _write_real_graph_file(data_backup.GRAPH_PATH)

        result = data_backup.create_backup("EMP-1")

        stored = ledger.get_entity(result["id"])
        assert stored is not None
        assert stored.entity_type == DATA_BACKUP


class TestListBackups:

    def test_empty_ledger_returns_an_empty_list(self):
        assert data_backup.list_backups() == []

    def test_returns_real_backups_sorted_by_created_at_descending(self, isolated_backup_paths):
        _write_real_graph_file(data_backup.GRAPH_PATH)

        older = data_backup.create_backup("EMP-1", label="older")
        newer = data_backup.create_backup("EMP-1", label="newer")

        # Force deterministic ordering regardless of real-clock resolution.
        ledger.get_entity(older["id"]).attributes["created_at"] = "2020-01-01T00:00:00+00:00"
        ledger.get_entity(newer["id"]).attributes["created_at"] = "2025-01-01T00:00:00+00:00"

        result = data_backup.list_backups()

        assert [b["id"] for b in result] == [newer["id"], older["id"]]

    def test_only_data_backup_entities_are_returned(self, isolated_backup_paths):
        _write_real_graph_file(data_backup.GRAPH_PATH)
        data_backup.create_backup("EMP-1")
        _make_customer("CUST-1")

        result = data_backup.list_backups()

        assert len(result) == 1
        assert result[0]["id"].startswith("BKUP")


class TestRestoreBackup:

    def test_unknown_backup_id_returns_an_error(self):
        result = data_backup.restore_backup("BKUP-BOGUS", "EMP-1")

        assert "error" in result
        assert "not found" in result["error"]

    def test_an_entity_of_the_wrong_type_is_rejected(self):
        _make_customer("CUST-1")

        result = data_backup.restore_backup("CUST-1", "EMP-1")

        assert "error" in result
        assert "not found" in result["error"]

    def test_a_backup_with_a_missing_path_attribute_returns_an_error(self):
        entity = Entity(id="BKUP-1", entity_type=DATA_BACKUP, attributes={"path": None})
        ledger.add_entity(entity)

        result = data_backup.restore_backup("BKUP-1", "EMP-1")

        assert "error" in result
        assert "no longer exists" in result["error"]

    def test_a_backup_whose_file_was_deleted_from_disk_returns_an_error(self, tmp_path):
        missing_path = str(tmp_path / "gone.json")
        entity = Entity(id="BKUP-1", entity_type=DATA_BACKUP, attributes={"path": missing_path})
        ledger.add_entity(entity)

        result = data_backup.restore_backup("BKUP-1", "EMP-1")

        assert "error" in result

    def test_a_real_restore_brings_back_the_backed_up_entity_state(self, isolated_backup_paths):
        customer = _make_customer("CUST-1", FirstName="Joseph")
        _write_real_graph_file(data_backup.GRAPH_PATH)
        backup = data_backup.create_backup("EMP-1")

        # Mutate live state after the backup was taken.
        customer.attributes["FirstName"] = "Modified"

        result = data_backup.restore_backup(backup["id"], "EMP-2")

        assert "error" not in result
        restored_customer = ledger.get_entity("CUST-1")
        assert restored_customer.attributes["FirstName"] == "Joseph"

    def test_restore_removes_entities_added_after_snapshot(
        self, isolated_backup_paths
    ):
        _make_customer("CUST-1", FirstName="Joseph")
        _write_real_graph_file(data_backup.GRAPH_PATH)
        backup = data_backup.create_backup("EMP-1")

        _make_customer("CUST-2", FirstName="Ann")

        data_backup.restore_backup(backup["id"], "EMP-2")

        assert ledger.get_entity("CUST-2") is None

    def test_restore_updates_metadata_when_snapshot_contains_its_catalog_entry(self, isolated_backup_paths):
        import shutil
        _write_real_graph_file(data_backup.GRAPH_PATH)
        backup = data_backup.create_backup("EMP-1")
        # Explicit fixture: snapshot includes its own existing catalog entry.
        shutil.copyfile(data_backup.GRAPH_PATH, backup["path"])
        result = data_backup.restore_backup(backup["id"], "EMP-2")
        assert result["restored_by"] == "EMP-2"
        assert ledger.get_entity(backup["id"]).attributes["restored_at"] is not None

    def test_a_restore_whose_own_record_does_not_survive_a_ledger_reset_returns_a_warning(
        self, isolated_backup_paths, monkeypatch
    ):
        _write_real_graph_file(data_backup.GRAPH_PATH)
        backup = data_backup.create_backup("EMP-1")

        result = data_backup.restore_backup(backup["id"], "EMP-2")

        assert "warning" in result
        assert backup["id"] in result["warning"]


def test_same_second_backups_preserve_distinct_recovery_points(monkeypatch):
    from datetime import datetime, timezone
    from pathlib import Path
    class FixedClock:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 10, 3, 20, 32, tzinfo=timezone.utc)
    monkeypatch.setattr(data_backup, 'datetime', FixedClock)
    _make_customer('CUST-1', FirstName='First')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    first = data_backup.create_backup('EMP-1')
    original = Path(first['path']).read_bytes()
    ledger.get_entity('CUST-1').attributes['FirstName'] = 'Second'
    _write_real_graph_file(data_backup.GRAPH_PATH)
    second = data_backup.create_backup('EMP-1')
    assert first['path'] != second['path']
    assert Path(first['path']).read_bytes() == original
    assert Path(second['path']).read_bytes() != original


def test_backup_name_collision_never_overwrites_existing_file(monkeypatch, isolated_backup_paths):
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(data_backup, 'uuid4', lambda: SimpleNamespace(hex='collision'))
    _write_real_graph_file(data_backup.GRAPH_PATH)
    first = data_backup.create_backup('EMP-1')
    original = Path(first['path']).read_bytes()
    # Derive the already-observed timestamp so the second generated path matches.
    stamp = first['filename'].removeprefix('graph_').removesuffix('_collision.json')
    class FixedClock:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone
            return datetime.strptime(stamp, '%Y%m%d_%H%M%S').replace(tzinfo=timezone.utc)
    monkeypatch.setattr(data_backup, 'datetime', FixedClock)
    with pytest.raises(FileExistsError):
        data_backup.create_backup('EMP-2')
    assert Path(first['path']).read_bytes() == original
    assert len(data_backup.list_backups()) == 1


def test_failed_backup_copy_removes_partial_file_without_record(monkeypatch, isolated_backup_paths):
    _write_real_graph_file(data_backup.GRAPH_PATH)
    def fail(source, destination):
        destination.write(b'partial')
        raise OSError('fixture copy failure')
    monkeypatch.setattr(data_backup.shutil, 'copyfileobj', fail)
    with pytest.raises(OSError, match='fixture copy failure'):
        data_backup.create_backup('EMP-1')
    assert list((isolated_backup_paths / 'backups').iterdir()) == []
    assert data_backup.list_backups() == []


def test_backup_metadata_failure_keeps_file_but_not_phantom_record(monkeypatch, isolated_backup_paths):
    from pathlib import Path
    _make_customer('CUST-1', FirstName='Recovery fixture')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    original = Path(data_backup.GRAPH_PATH).read_bytes()
    real_save = data_backup.save_graph
    def fail(_):
        raise OSError('fixture metadata failure')
    monkeypatch.setattr(data_backup, 'save_graph', fail)
    with pytest.raises(OSError, match='fixture metadata failure'):
        data_backup.create_backup('EMP-1')
    assert data_backup.list_backups() == []
    files = list((isolated_backup_paths / 'backups').iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == original
    monkeypatch.setattr(data_backup, 'save_graph', real_save)
    retry = data_backup.create_backup('EMP-1')
    assert len(data_backup.list_backups()) == 1
    assert Path(retry['path']) != files[0]
    assert files[0].read_bytes() == original


def test_failed_backup_sync_removes_unconfirmed_file(monkeypatch, isolated_backup_paths):
    _write_real_graph_file(data_backup.GRAPH_PATH)
    def fail(_):
        raise OSError('fixture sync failure')
    monkeypatch.setattr(data_backup.os, 'fsync', fail)
    with pytest.raises(OSError, match='fixture sync failure'):
        data_backup.create_backup('EMP-1')
    assert data_backup.list_backups() == []
    assert list((isolated_backup_paths / 'backups').iterdir()) == []


@pytest.mark.parametrize('content', [b'{truncated', b'{}', b'{"entities":[{"id":"broken"}],"relationships":[]}', b'{"entities":[],"relationships":[{}]}'])
def test_invalid_restore_does_not_replace_live_file_or_mutate_ledger(content):
    from pathlib import Path
    from copy import deepcopy
    _make_customer('CUST-1', FirstName='Live fixture')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    Path(backup['path']).write_bytes(content)
    before_file = Path(data_backup.GRAPH_PATH).read_bytes()
    before_entities = deepcopy(ledger.entities)
    before_relationships = deepcopy(ledger.relationships)
    result = data_backup.restore_backup(backup['id'], 'EMP-2')
    assert 'could not be validated' in result['error']
    assert Path(data_backup.GRAPH_PATH).read_bytes() == before_file
    assert ledger.entities == before_entities
    assert ledger.relationships == before_relationships


def test_restore_replaces_relationships_without_appending_duplicates():
    from core.relationships import Relationship
    _make_customer('CUST-1')
    _make_customer('CUST-2')
    original = Relationship('CUST-1', 'CUST-2', 'fixture', created_by='EMP-1')
    ledger.add_relationship(original)
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    record = ledger.get_entity(backup['id'])
    ledger.add_relationship(Relationship('CUST-2', 'CUST-1', 'later'))
    for _ in range(2):
        ledger.add_entity(record)  # External fixture retains the catalog reference.
        result = data_backup.restore_backup(backup['id'], 'EMP-2')
        assert 'error' not in result
        assert ledger.relationships == [original]


@pytest.mark.parametrize('failure', ['copy', 'sync', 'replace'])
def test_restore_staging_failure_preserves_live_graph(monkeypatch, isolated_backup_paths, failure):
    from pathlib import Path
    from copy import deepcopy
    _make_customer('CUST-1', FirstName='Original')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    ledger.get_entity('CUST-1').attributes['FirstName'] = 'Current'
    _write_real_graph_file(data_backup.GRAPH_PATH)
    before = Path(data_backup.GRAPH_PATH).read_bytes()
    entities = deepcopy(ledger.entities)
    def fail(*args):
        if failure == 'copy': args[1].write(b'partial')
        raise OSError('fixture staging failure')
    monkeypatch.setattr(data_backup.shutil if failure == 'copy' else data_backup.os,
                        'copyfileobj' if failure == 'copy' else ('fsync' if failure == 'sync' else 'replace'), fail)
    with pytest.raises(OSError, match='fixture staging failure'):
        data_backup.restore_backup(backup['id'], 'EMP-2')
    assert Path(data_backup.GRAPH_PATH).read_bytes() == before
    assert ledger.entities == entities
    assert list(isolated_backup_paths.glob('.restore-*')) == []


def test_restore_installs_validated_staging_even_if_backup_changes(monkeypatch, isolated_backup_paths):
    from pathlib import Path
    from core.json_graph_repository import JsonGraphRepository
    _make_customer('CUST-1', FirstName='Snapshot')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    expected = Path(backup['path']).read_bytes()
    original_load = JsonGraphRepository.load
    def load_and_change_source(repository, path):
        result = original_load(repository, path)
        Path(backup['path']).write_bytes(b'{changed after preflight')
        return result
    monkeypatch.setattr(JsonGraphRepository, 'load', load_and_change_source)
    result = data_backup.restore_backup(backup['id'], 'EMP-2')
    assert 'error' not in result
    assert Path(data_backup.GRAPH_PATH).read_bytes() == expected
    assert ledger.get_entity('CUST-1').attributes['FirstName'] == 'Snapshot'
    assert list(isolated_backup_paths.glob('.restore-*')) == []


def test_restore_retains_consumed_id_high_water_mark():
    _make_customer('CUST-00900')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    previous = data_backup.id_generator.counters.get('CUST', 0)
    data_backup.id_generator.counters['CUST'] = 1200
    try:
        result = data_backup.restore_backup(backup['id'], 'EMP-2')
        assert 'error' not in result
        assert data_backup.id_generator.generate('CUST') == 'CUST-01201'
    finally:
        data_backup.id_generator.counters['CUST'] = previous

@pytest.mark.parametrize('same_attributes', [True, False])
def test_restore_rejects_duplicate_entity_ids_without_data_loss(same_attributes, isolated_backup_paths):
    from pathlib import Path
    from copy import deepcopy
    _make_customer('CUST-1', FirstName='Live customer')
    _write_real_graph_file(data_backup.GRAPH_PATH)
    backup = data_backup.create_backup('EMP-1')
    first = {'id': 'CUST-2', 'entity_type': 'Customer', 'attributes': {'FirstName': 'Snapshot'}}
    second = deepcopy(first)
    if not same_attributes:
        second['attributes']['FirstName'] = 'Conflicting customer'
    Path(backup['path']).write_text(json.dumps({'entities': [first, second], 'relationships': []}), encoding='utf-8')
    before_file = Path(data_backup.GRAPH_PATH).read_bytes()
    before_entities = deepcopy(ledger.entities)
    before_relationships = deepcopy(ledger.relationships)
    result = data_backup.restore_backup(backup['id'], 'EMP-2')
    assert 'could not be validated' in result['error']
    assert Path(data_backup.GRAPH_PATH).read_bytes() == before_file
    assert ledger.entities == before_entities
    assert ledger.relationships == before_relationships
    assert list(isolated_backup_paths.glob('.restore-*')) == []
