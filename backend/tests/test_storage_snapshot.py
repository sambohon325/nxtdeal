"""
Tests for core/storage_snapshot.py / core/storage_snapshot_network_api.py -- real,
read-only, non-PII storage/database instrumentation backing the NXTDeal Hub's
Infrastructure & Platform Operations "Databases"/"Storage" panels (Infra rebuild
slice 2 of 4). Every figure is read directly off disk / off the live in-memory
ledger at request time -- no fabricated telemetry, no PII, no raw credential or
entity content, counts and sizes only.

GRAPH_PATH/AUDIT_PATH/CREDENTIALS_PATH are frozen constants computed once at
import time (core/storage_paths.py), so tests monkeypatch storage_snapshot's own
bound names directly ("patch where it's used") rather than the DEALEROS_STORAGE_DIR
env var. uploads_dir()/backups_dir()/storage_dir() are read-fresh functions, so
those are monkeypatched as lambdas returning a real tmp_path subdirectory.

get_storage_snapshot() is exercised as a real, composed end-to-end call against
real files written to a real tmp_path -- no monkeypatching of the internal helper
functions themselves for that test, since the whole point is confirming the real
composition is correct.

Run from backend/ with `pytest`.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER
from core import storage_snapshot
from core import storage_snapshot_network_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


class TestSafeSize:

    def test_returns_the_real_size_of_an_existing_file(self, tmp_path):
        path = tmp_path / "f.txt"
        path.write_text("hello world")

        assert storage_snapshot._safe_size(str(path)) == len("hello world")

    def test_returns_none_for_a_missing_file(self, tmp_path):
        assert storage_snapshot._safe_size(str(tmp_path / "nope.txt")) is None


class TestSafeMtimeIso:

    def test_returns_a_real_iso_timestamp_for_an_existing_file(self, tmp_path):
        path = tmp_path / "f.txt"
        path.write_text("hi")

        result = storage_snapshot._safe_mtime_iso(str(path))

        assert result is not None
        assert "T" in result

    def test_returns_none_for_a_missing_file(self, tmp_path):
        assert storage_snapshot._safe_mtime_iso(str(tmp_path / "nope.txt")) is None


class TestCredentialCount:

    def test_returns_the_real_count_of_top_level_keys(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        path.write_text(json.dumps({"EMP-1": {}, "EMP-2": {}}))
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(path))

        assert storage_snapshot._credential_count() == 2

    def test_returns_none_when_the_file_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(tmp_path / "nope.json"))

        assert storage_snapshot._credential_count() is None

    def test_returns_none_for_malformed_json(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        path.write_text("not valid json")
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(path))

        assert storage_snapshot._credential_count() is None

    def test_returns_none_when_the_top_level_json_is_not_a_dict(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        path.write_text(json.dumps(["not", "a", "dict"]))
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(path))

        assert storage_snapshot._credential_count() is None


class TestAuditEventCount:

    def test_returns_the_real_count_of_events(self, tmp_path, monkeypatch):
        path = tmp_path / "audit.json"
        path.write_text(json.dumps([{"event": "a"}, {"event": "b"}, {"event": "c"}]))
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(path))

        assert storage_snapshot._audit_event_count() == 3

    def test_returns_none_when_the_file_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(tmp_path / "nope.json"))

        assert storage_snapshot._audit_event_count() is None

    def test_returns_none_for_malformed_json(self, tmp_path, monkeypatch):
        path = tmp_path / "audit.json"
        path.write_text("{not json")
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(path))

        assert storage_snapshot._audit_event_count() is None

    def test_returns_none_when_the_top_level_json_is_not_a_list(self, tmp_path, monkeypatch):
        path = tmp_path / "audit.json"
        path.write_text(json.dumps({"not": "a list"}))
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(path))

        assert storage_snapshot._audit_event_count() is None


class TestDirSummary:

    def test_a_directory_that_does_not_exist_returns_honest_zeros_not_an_error(self, tmp_path):
        result = storage_snapshot._dir_summary(str(tmp_path / "does_not_exist"))

        assert result == {
            "file_count": 0,
            "total_size_bytes": 0,
            "latest_file": None,
            "latest_modified_at": None,
        }

    def test_an_empty_existing_directory_returns_zeros(self, tmp_path):
        directory = tmp_path / "empty"
        directory.mkdir()

        result = storage_snapshot._dir_summary(str(directory))

        assert result["file_count"] == 0
        assert result["total_size_bytes"] == 0
        assert result["latest_file"] is None

    def test_real_files_produce_a_real_count_and_total_size(self, tmp_path):
        directory = tmp_path / "files"
        directory.mkdir()
        (directory / "a.json").write_text("12345")
        (directory / "b.json").write_text("1234567890")

        result = storage_snapshot._dir_summary(str(directory))

        assert result["file_count"] == 2
        assert result["total_size_bytes"] == 15

    def test_the_most_recently_modified_file_is_reported_as_latest(self, tmp_path):
        directory = tmp_path / "files"
        directory.mkdir()
        (directory / "older.json").write_text("x")
        time.sleep(0.02)
        (directory / "newer.json").write_text("y")

        result = storage_snapshot._dir_summary(str(directory))

        assert result["latest_file"] == "newer.json"
        assert result["latest_modified_at"] is not None

    def test_subdirectories_inside_the_directory_are_not_counted_as_files(self, tmp_path):
        directory = tmp_path / "files"
        directory.mkdir()
        (directory / "real_file.json").write_text("x")
        (directory / "a_subdir").mkdir()

        result = storage_snapshot._dir_summary(str(directory))

        assert result["file_count"] == 1


class TestGetStorageSnapshot:

    def test_real_end_to_end_composition_against_real_files_and_the_live_ledger(
        self, tmp_path, monkeypatch
    ):
        graph_path = tmp_path / "graph.json"
        audit_path = tmp_path / "audit.json"
        credentials_path = tmp_path / "credentials.json"
        uploads_path = tmp_path / "uploads"
        backups_path = tmp_path / "backups"

        graph_path.write_text(json.dumps({"entities": [], "relationships": []}))
        audit_path.write_text(json.dumps([{"event": "x"}, {"event": "y"}]))
        credentials_path.write_text(json.dumps({"EMP-1": {}}))
        uploads_path.mkdir()
        (uploads_path / "attachment.png").write_bytes(b"\x00" * 100)
        # backups_path is deliberately left non-existent -- confirms the real
        # honest "nothing here yet" zero-state, not a fabricated placeholder.

        monkeypatch.setattr(storage_snapshot, "GRAPH_PATH", str(graph_path))
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(audit_path))
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(credentials_path))
        monkeypatch.setattr(storage_snapshot, "uploads_dir", lambda: str(uploads_path))
        monkeypatch.setattr(storage_snapshot, "backups_dir", lambda: str(backups_path))
        monkeypatch.setattr(storage_snapshot, "storage_dir", lambda: "storage/tenants/DLR-00001")

        ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={}))
        ledger.add_entity(Entity(id="CUST-2", entity_type=CUSTOMER, attributes={}))

        result = storage_snapshot.get_storage_snapshot()

        assert result["storage_dir"] == "storage/tenants/DLR-00001"
        assert result["graph_json"]["entity_count"] == 2
        assert result["graph_json"]["relationship_count"] == 0
        assert result["graph_json"]["size_bytes"] == graph_path.stat().st_size
        assert result["graph_json"]["last_modified_at"] is not None
        assert result["audit_json"]["event_count"] == 2
        assert result["credentials_json"]["credential_count"] == 1
        assert result["uploads"]["file_count"] == 1
        assert result["uploads"]["total_size_bytes"] == 100
        assert result["backups"]["file_count"] == 0
        assert "note" in result
        assert isinstance(result["note"], str)
        assert len(result["note"]) > 0

    def test_a_fresh_empty_ledger_still_produces_a_real_zero_entity_count(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(storage_snapshot, "GRAPH_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setattr(storage_snapshot, "AUDIT_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setattr(storage_snapshot, "CREDENTIALS_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setattr(storage_snapshot, "uploads_dir", lambda: str(tmp_path / "uploads"))
        monkeypatch.setattr(storage_snapshot, "backups_dir", lambda: str(tmp_path / "backups"))

        result = storage_snapshot.get_storage_snapshot()

        assert result["graph_json"]["entity_count"] == 0
        assert result["graph_json"]["relationship_count"] == 0
        assert result["graph_json"]["size_bytes"] is None
        assert result["audit_json"]["event_count"] is None
        assert result["credentials_json"]["credential_count"] is None


class TestStorageSnapshotNetworkApi:

    def test_a_bad_network_key_returns_an_error_without_calling_get_storage_snapshot(
        self, monkeypatch
    ):
        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")

        def _should_not_be_called():
            raise AssertionError("get_storage_snapshot should not be called with a bad key")

        monkeypatch.setattr(storage_snapshot_network_api, "get_storage_snapshot", _should_not_be_called)

        result = storage_snapshot_network_api.get_storage_snapshot_api("wrong-key")

        assert "error" in result

    def test_a_valid_network_key_returns_the_real_storage_snapshot(self, monkeypatch):
        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")
        monkeypatch.setattr(
            storage_snapshot_network_api,
            "get_storage_snapshot",
            lambda: {"storage_dir": "storage", "note": "real"},
        )

        result = storage_snapshot_network_api.get_storage_snapshot_api("synthetic-shared-network-secret-for-tests-only")

        assert result == {"storage_dir": "storage", "note": "real"}

    def test_dev_fallback_cannot_read_storage_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("DEALEROS_NETWORK_KEY", raising=False)
        monkeypatch.setattr(
            storage_snapshot_network_api,
            "get_storage_snapshot",
            lambda: {"note": "real"},
        )

        result = storage_snapshot_network_api.get_storage_snapshot_api(
            "dev-only-insecure-network-key-change-me"
        )

        assert result == {"error": "invalid or missing X-NXTDeal-Network-Key"}
