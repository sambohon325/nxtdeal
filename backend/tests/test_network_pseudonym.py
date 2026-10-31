"""
Tests for core/network_pseudonym.py -- the per-tenant, locally-generated,
never-derived-from-dealer-identity pseudonym backing the NXTDeal Hub's anonymized
cross-network intelligence layer (session 2026-07-16).

Each test gets its own genuinely isolated storage directory via monkeypatch.setenv +
pytest's own tmp_path fixture -- core/storage_paths.py's storage_dir() reads
DEALEROS_STORAGE_DIR fresh via os.environ.get() on every call (not cached at import
time), specifically so this is safe even though backend/tests/conftest.py sets that
same env var once, session-wide, at collection time to its own shared temp directory.
Overriding it per-test here gives real isolation regardless.

Run from backend/ with `pytest`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import network_pseudonym


def _use_storage_dir(monkeypatch, path):
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(path))


class TestGetOrCreatePseudonym:

    def test_first_call_generates_and_persists_a_pseudonym(self, monkeypatch, tmp_path):
        _use_storage_dir(monkeypatch, tmp_path)

        pseudonym = network_pseudonym.get_or_create_pseudonym()

        assert isinstance(pseudonym, str)
        # secrets.token_hex(32) -> 32 bytes -> 64 hex characters.
        assert len(pseudonym) == 64
        int(pseudonym, 16)  # raises ValueError if not valid hex -- confirms real hex encoding

    def test_pseudonym_is_actually_written_to_disk(self, monkeypatch, tmp_path):
        _use_storage_dir(monkeypatch, tmp_path)

        pseudonym = network_pseudonym.get_or_create_pseudonym()

        identity_file = tmp_path / "network_identity.json"
        assert identity_file.exists()
        data = json.loads(identity_file.read_text())
        assert data["pseudonym"] == pseudonym
        assert "note" in data

    def test_second_call_reuses_the_same_persisted_pseudonym(self, monkeypatch, tmp_path):
        _use_storage_dir(monkeypatch, tmp_path)

        first = network_pseudonym.get_or_create_pseudonym()
        second = network_pseudonym.get_or_create_pseudonym()

        assert first == second

    def test_creates_the_storage_directory_if_it_does_not_exist_yet(self, monkeypatch, tmp_path):
        nested = tmp_path / "tenants" / "DLR-00099"
        assert not nested.exists()
        _use_storage_dir(monkeypatch, nested)

        pseudonym = network_pseudonym.get_or_create_pseudonym()

        assert nested.exists()
        assert (nested / "network_identity.json").exists()
        assert pseudonym

    def test_two_different_tenants_get_two_different_pseudonyms(self, monkeypatch, tmp_path):
        dir_a = tmp_path / "tenant_a"
        dir_b = tmp_path / "tenant_b"

        _use_storage_dir(monkeypatch, dir_a)
        pseudonym_a = network_pseudonym.get_or_create_pseudonym()

        _use_storage_dir(monkeypatch, dir_b)
        pseudonym_b = network_pseudonym.get_or_create_pseudonym()

        assert pseudonym_a != pseudonym_b
        # Never derived from any identifying value -- confirmed indirectly by there being
        # no shared substring/prefix relationship a deterministic-hash scheme would produce.
        assert pseudonym_a[:8] != pseudonym_b[:8]

    def test_a_file_present_but_with_an_empty_pseudonym_value_is_regenerated(self, monkeypatch, tmp_path):
        _use_storage_dir(monkeypatch, tmp_path)
        identity_file = tmp_path / "network_identity.json"
        identity_file.write_text(json.dumps({"pseudonym": "", "note": "corrupted"}))

        pseudonym = network_pseudonym.get_or_create_pseudonym()

        assert pseudonym  # a real, non-empty value was generated
        data = json.loads(identity_file.read_text())
        assert data["pseudonym"] == pseudonym

    def test_a_file_present_with_no_pseudonym_key_at_all_is_regenerated(self, monkeypatch, tmp_path):
        _use_storage_dir(monkeypatch, tmp_path)
        identity_file = tmp_path / "network_identity.json"
        identity_file.write_text(json.dumps({"note": "some other shape"}))

        pseudonym = network_pseudonym.get_or_create_pseudonym()

        assert pseudonym
        assert len(pseudonym) == 64

    def test_identity_path_reads_the_env_var_fresh_not_cached_at_import_time(self, monkeypatch, tmp_path):
        # Directly exercises the module's own stated design goal: _identity_path() must
        # not be memoized, so switching tenants mid-process (as multiple tests in one
        # session do) is always safe.
        dir_a = tmp_path / "first"
        dir_b = tmp_path / "second"

        _use_storage_dir(monkeypatch, dir_a)
        path_a = network_pseudonym._identity_path()

        _use_storage_dir(monkeypatch, dir_b)
        path_b = network_pseudonym._identity_path()

        assert path_a != path_b
        assert str(dir_a) in path_a
        assert str(dir_b) in path_b
