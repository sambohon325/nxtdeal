"""
Tests for core/api_keys.py / core/api_keys_api.py -- Administration's "Identity &
Access" item (Administration Control Center rebuild): real, per-employee API keys
for programmatic/integration access, distinct from core/auth.py's session tokens.
Run from backend/ with `pytest`.

Covers: generate_api_key()'s attribute shape (only the raw_key's creation response
ever includes the plaintext key; key_hash is never echoed back by any serializer;
last4 matches the real raw key's own last 4 characters; employee-not-found rejected);
revoke_api_key()'s real state transition and double-revoke rejection; list_api_keys_
for_employee()/list_all_api_keys()'s filtering + newest-first ordering + key_hash
scrubbing; verify_api_key()'s real fail-closed contract (unknown key, wrong prefix,
revoked key, an employee whose credential has since been removed all return None;
a valid bound key returns {employee_id, role}; password/role/MFA changes invalidate
it, legacy keys fail closed, and internal bindings stay out of management output.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, API_KEY
from core import api_keys
from core import api_keys_api
from core import auth as auth_module
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def fresh_credential_store():
    auth_module.credential_store.reset()
    yield
    auth_module.credential_store.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(api_keys, "save_graph", lambda filepath: None)


def _make_employee(employee_id="EMP-1", name="Jane Doe"):
    entity = Entity(id=employee_id, entity_type=EMPLOYEE, attributes={"Name": name})
    ledger.add_entity(entity)
    auth_module.credential_store.set_credential(employee_id, "SyntheticPassword!42", SALES, must_change_password=False)
    return entity


class TestGenerateApiKey:

    def test_employee_not_found_rejected(self):
        result = api_keys.generate_api_key("EMP-DOES-NOT-EXIST", "My Key", "EMP-9")
        assert "error" in result
        assert "EMP-DOES-NOT-EXIST" in result["error"]

    def test_success_returns_plaintext_raw_key_starting_with_prefix(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", "My Integration Key", "EMP-9")

        assert "error" not in result
        assert result["raw_key"].startswith(api_keys._KEY_PREFIX)
        assert result["id"].startswith("APIK")

    def test_key_hash_never_echoed_back_in_the_creation_response(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")
        assert "key_hash" not in result

    def test_last4_matches_the_real_raw_keys_last_four_characters(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")
        assert result["last4"] == result["raw_key"][-4:]

    def test_attribute_shape(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        assert result["employee_id"] == "EMP-1"
        assert result["label"] == "My Key"
        assert result["active"] is True
        assert result["created_by"] == "EMP-9"
        assert result["created_at"]
        assert result["last_used_at"] is None
        assert result["revoked_by"] is None
        assert result["revoked_at"] is None

    def test_label_defaults_to_empty_string_when_falsy(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", None, "EMP-9")
        assert result["label"] == ""

    def test_two_keys_for_the_same_employee_get_distinct_ids_and_secrets(self):
        _make_employee()
        first = api_keys.generate_api_key("EMP-1", "Key A", "EMP-9")
        second = api_keys.generate_api_key("EMP-1", "Key B", "EMP-9")

        assert first["id"] != second["id"]
        assert first["raw_key"] != second["raw_key"]

    def test_real_api_key_entity_is_persisted_in_the_ledger(self):
        _make_employee()
        result = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == API_KEY
        # The ledger's own stored entity DOES carry key_hash -- only the
        # serialized/returned view scrubs it.
        assert entity.attributes["key_hash"]


class TestRevokeApiKey:

    def test_unknown_key_id_rejected(self):
        result = api_keys.revoke_api_key("APIK-BOGUS", "EMP-9")
        assert "error" in result

    def test_wrong_entity_type_rejected(self):
        _make_employee()
        result = api_keys.revoke_api_key("EMP-1", "EMP-9")
        assert "error" in result

    def test_successful_revoke_flips_active_and_stamps_revoked_fields(self):
        _make_employee()
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        result = api_keys.revoke_api_key(created["id"], "EMP-2")

        assert result["active"] is False
        assert result["revoked_by"] == "EMP-2"
        assert result["revoked_at"]
        # Revoke's own returned shape also never leaks key_hash.
        assert "key_hash" not in result

    def test_double_revoke_rejected(self):
        _make_employee()
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        api_keys.revoke_api_key(created["id"], "EMP-2")
        second = api_keys.revoke_api_key(created["id"], "EMP-2")

        assert second == {"error": "This API key is already revoked"}


class TestListApiKeys:

    def test_list_for_employee_only_returns_that_employees_keys(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")

        api_keys.generate_api_key("EMP-1", "Key A", "EMP-9")
        api_keys.generate_api_key("EMP-2", "Key B", "EMP-9")

        result = api_keys.list_api_keys_for_employee("EMP-1")
        assert len(result) == 1
        assert result[0]["label"] == "Key A"

    def test_list_for_employee_never_leaks_key_hash(self):
        _make_employee()
        api_keys.generate_api_key("EMP-1", "Key A", "EMP-9")

        result = api_keys.list_api_keys_for_employee("EMP-1")
        assert "key_hash" not in result[0]
        assert "id" in result[0]

    def test_list_all_returns_every_employees_keys(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")

        api_keys.generate_api_key("EMP-1", "Key A", "EMP-9")
        api_keys.generate_api_key("EMP-2", "Key B", "EMP-9")

        result = api_keys.list_all_api_keys()
        assert len(result) == 2

    def test_list_all_sorted_newest_first(self):
        _make_employee()
        first = api_keys.generate_api_key("EMP-1", "First", "EMP-9")
        second = api_keys.generate_api_key("EMP-1", "Second", "EMP-9")

        result = api_keys.list_all_api_keys()
        assert result[0]["id"] == second["id"]
        assert result[1]["id"] == first["id"]

    def test_no_keys_returns_empty_list(self):
        assert api_keys.list_all_api_keys() == []
        assert api_keys.list_api_keys_for_employee("EMP-1") == []


class TestVerifyApiKey:

    def test_none_or_empty_key_returns_none(self):
        assert api_keys.verify_api_key(None) is None
        assert api_keys.verify_api_key("") is None

    def test_key_missing_the_real_prefix_returns_none(self):
        assert api_keys.verify_api_key("not_a_real_prefix_abc123") is None

    def test_unknown_key_returns_none(self):
        assert api_keys.verify_api_key(f"{api_keys._KEY_PREFIX}totally-made-up-secret") is None

    def test_valid_active_key_with_a_real_credential_returns_employee_id_and_role(self):
        _make_employee()
        auth_module.credential_store.set_credential("EMP-1", "hunter2", SALES, must_change_password=False)
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        result = api_keys.verify_api_key(created["raw_key"])

        assert result == {"employee_id": "EMP-1", "role": SALES}

    def test_revoked_key_returns_none(self):
        _make_employee()
        auth_module.credential_store.set_credential("EMP-1", "hunter2", SALES, must_change_password=False)
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        api_keys.revoke_api_key(created["id"], "EMP-9")

        assert api_keys.verify_api_key(created["raw_key"]) is None

    def test_valid_key_but_no_credential_record_returns_none(self):
        _make_employee()
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")
        auth_module.credential_store.reset()

        assert api_keys.verify_api_key(created["raw_key"]) is None

    def test_role_change_invalidates_key_instead_of_expanding_privilege(self):
        _make_employee()
        auth_module.credential_store.set_credential("EMP-1", "hunter2", SALES, must_change_password=False)
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")

        assert api_keys.verify_api_key(created["raw_key"])["role"] == SALES

        # A key must never silently acquire a new role after issuance.
        auth_module.credential_store.set_credential("EMP-1", "hunter2", FINANCE, must_change_password=False)

        assert api_keys.verify_api_key(created["raw_key"]) is None

    def test_valid_key_updates_last_used_at_in_memory(self):
        _make_employee()
        auth_module.credential_store.set_credential("EMP-1", "hunter2", SALES, must_change_password=False)
        created = api_keys.generate_api_key("EMP-1", "My Key", "EMP-9")
        assert created["last_used_at"] is None

        api_keys.verify_api_key(created["raw_key"])

        entity = ledger.get_entity(created["id"])
        assert entity.attributes["last_used_at"] is not None


class TestApiKeysApiAcl:

    def test_generate_for_self_requires_no_special_role(self):
        _make_employee("EMP-1")
        result = api_keys_api.generate_api_key_api(SALES, "EMP-1", label="My Key")
        assert "error" not in result
        assert result["employee_id"] == "EMP-1"

    def test_generate_for_another_employee_requires_admin(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        result = api_keys_api.generate_api_key_api(SALES, "EMP-1", target_employee_id="EMP-2", label="x")
        assert "error" in result

    def test_generate_for_another_employee_allowed_for_admin(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        result = api_keys_api.generate_api_key_api(ADMIN, "EMP-1", target_employee_id="EMP-2", label="x")
        assert "error" not in result
        assert result["employee_id"] == "EMP-2"

    def test_revoke_own_key_requires_no_special_role(self):
        _make_employee("EMP-1")
        created = api_keys_api.generate_api_key_api(SALES, "EMP-1", label="x")
        result = api_keys_api.revoke_api_key_api(SALES, "EMP-1", created["id"])
        assert result["active"] is False

    def test_revoke_someone_elses_key_denied_for_non_admin(self):
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        created = api_keys_api.generate_api_key_api(ADMIN, "EMP-9", target_employee_id="EMP-1", label="x")

        result = api_keys_api.revoke_api_key_api(SALES, "EMP-2", created["id"])
        assert result == api_keys_api._ADMIN_ONLY_ERROR

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_revoke_someone_elses_key_allowed_for_admin_ops(self, role):
        _make_employee("EMP-1")
        _make_employee("EMP-2")
        created = api_keys_api.generate_api_key_api(ADMIN, "EMP-9", target_employee_id="EMP-1", label="x")

        result = api_keys_api.revoke_api_key_api(role, "EMP-2", created["id"])
        assert result["active"] is False

    def test_revoke_unknown_key_returns_not_found_before_checking_role(self):
        result = api_keys_api.revoke_api_key_api(SALES, "EMP-1", "APIK-BOGUS")
        assert "not found" in result["error"]

    def test_list_for_self_requires_no_special_role(self):
        _make_employee("EMP-1")
        api_keys_api.generate_api_key_api(SALES, "EMP-1", label="x")
        result = api_keys_api.list_api_keys_for_employee_api(SALES, "EMP-1")
        assert result["employee_id"] == "EMP-1"
        assert len(result["keys"]) == 1

    def test_list_for_someone_else_denied_for_non_admin(self):
        result = api_keys_api.list_api_keys_for_employee_api(SALES, "EMP-1", target_employee_id="EMP-2")
        assert result == api_keys_api._ADMIN_ONLY_ERROR

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_list_for_someone_else_allowed_for_admin_ops(self, role):
        _make_employee("EMP-2")
        api_keys_api.generate_api_key_api(ADMIN, "EMP-9", target_employee_id="EMP-2", label="x")
        result = api_keys_api.list_api_keys_for_employee_api(role, "EMP-1", target_employee_id="EMP-2")
        assert result["employee_id"] == "EMP-2"
        assert len(result["keys"]) == 1

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_list_all_allowed_for_admin_ops(self, role):
        result = api_keys_api.list_all_api_keys_api(role)
        assert result == {"keys": []}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_list_all_denied_for_other_roles(self, role):
        result = api_keys_api.list_all_api_keys_api(role)
        assert result == api_keys_api._ADMIN_ONLY_ERROR

@pytest.mark.parametrize("change", ["password", "mfa", "role_revision", "legacy", "malformed", "temporary_password"])
def test_account_security_changes_and_unbound_keys_fail_closed(change):
    _make_employee()
    store = auth_module.credential_store
    key = api_keys.generate_api_key("EMP-1", "Synthetic", "EMP-1")
    assert api_keys.verify_api_key(key["raw_key"])
    entity = ledger.get_entity(key["id"])
    if change == "password":
        store.set_credential("EMP-1", "ReplacementPassword!42", SALES, must_change_password=False)
    elif change == "mfa":
        setup = store.begin_mfa_enrollment("EMP-1")
        from core.mfa import totp_now
        assert "error" not in store.confirm_mfa_enrollment("EMP-1", totp_now(setup["secret"]))
    elif change == "role_revision":
        store.get_record("EMP-1")["role_version"] = 1
    elif change == "legacy":
        entity.attributes.pop("credential_binding")
    elif change == "malformed":
        entity.attributes["credential_binding"] = "non-ascii-\u2603"
    else:
        store.get_record("EMP-1")["must_change_password"] = True
    entity.attributes["last_used_at"] = None
    assert api_keys.verify_api_key(key["raw_key"]) is None
    assert entity.attributes["last_used_at"] is None


def test_binding_is_persisted_but_never_exposed_in_key_management(monkeypatch):
    from copy import deepcopy
    _make_employee()
    captured = []
    monkeypatch.setattr(api_keys, "save_graph", lambda *_: captured.extend(
        deepcopy(e.attributes) for e in ledger.get_all().values() if e.entity_type == API_KEY))
    key = api_keys.generate_api_key("EMP-1", "Synthetic", "EMP-1")
    assert captured[0]["credential_binding"]
    outputs = [key, *api_keys.list_all_api_keys(), *api_keys.list_api_keys_for_employee("EMP-1")]
    for output in outputs:
        assert "credential_binding" not in output
        assert "key_hash" not in output
    # Reconstruct the persisted credential/key state as a restart would do.
    credentials = deepcopy(auth_module.credential_store.credentials)
    auth_module.credential_store.reset()
    auth_module.credential_store.load_credentials(credentials)
    ledger.get_entity(key["id"]).attributes = captured[0]
    assert api_keys.verify_api_key(key["raw_key"])


@pytest.mark.parametrize("missing", [True, False])
def test_cannot_issue_for_missing_or_temporary_credential(missing):
    _make_employee()
    if missing:
        auth_module.credential_store.reset()
    else:
        auth_module.credential_store.get_record("EMP-1")["must_change_password"] = True
    assert "error" in api_keys.generate_api_key("EMP-1", "Synthetic", "EMP-1")
    assert api_keys.list_all_api_keys() == []

@pytest.mark.parametrize('expiry', [None, '', 'invalid', 123, '2026-01-01T00:00:00', '2000-01-01T00:00:00+00:00'])
def test_invalid_missing_or_elapsed_expiry_denies_without_last_use(expiry):
    _make_employee()
    result = api_keys.generate_api_key('EMP-1', 'expiry test', 'EMP-1')
    entity = ledger.get_entity(result['id'])
    if expiry is None:
        entity.attributes.pop('expires_at')
    else:
        entity.attributes['expires_at'] = expiry
    assert api_keys.verify_api_key(result['raw_key']) is None
    assert entity.attributes['last_used_at'] is None


def test_key_expires_at_exact_boundary_and_reports_expiry(monkeypatch):
    from datetime import datetime, timezone, timedelta
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant
    monkeypatch.setattr(api_keys, 'datetime', Clock)
    _make_employee()
    result = api_keys.generate_api_key('EMP-1', 'expiry test', 'EMP-1')
    expiry = datetime.fromisoformat(result['expires_at'])
    assert expiry - datetime.fromisoformat(result['created_at']) == timedelta(days=90)
    assert api_keys.list_api_keys_for_employee('EMP-1')[0]['expires_at'] == result['expires_at']
    instant = expiry - timedelta(microseconds=1)
    assert api_keys.verify_api_key(result['raw_key']) is not None
    prior_use = ledger.get_entity(result['id']).attributes['last_used_at']
    instant = expiry
    assert api_keys.verify_api_key(result['raw_key']) is None
    assert ledger.get_entity(result['id']).attributes['last_used_at'] == prior_use
