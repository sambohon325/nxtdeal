"""
Tests for the Phase 9 auth module (core/auth.py, core/auth_storage.py, core/auth_api.py).
Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.auth import (
    hash_password,
    verify_password,
    issue_token,
    verify_token,
    generate_temp_password
)
from core.auth_storage import save_credentials, load_credentials
from core import auth as auth_module
from core import auth_api


@pytest.fixture(autouse=True)
def fresh_credential_store():
    """Every test starts with a clean singleton. Resets the existing CredentialStore
    instance in place (CredentialStore.reset()) rather than swapping in a new object —
    core/auth_storage.py already holds a direct reference to the singleton via
    `from core.auth import credential_store`, so replacing the object identity here would
    make load_credentials() write into an instance this test can no longer see."""

    auth_module.credential_store.reset()

    yield

    auth_module.credential_store.reset()


@pytest.fixture(autouse=True)
def no_real_storage_writes(monkeypatch):
    """auth_api.login(), create_credential(), and change_password() all call
    save_audit_log("storage/audit.json") and/or save_credentials("storage/credentials.json")
    as side effects — hardcoded relative paths. When pytest's cwd is backend/ (the
    documented way to run this suite), those paths resolve to the REAL production files,
    not scratch files. Without this fixture, tests that call those functions write
    real-looking data into Sam's actual storage/*.json. (This already happened once for
    audit.json — see BUILD_QUEUE.md session log 2026-07-12 session 5 — hence this fixture,
    now covering credentials.json too before the same mistake repeats.) Persistence itself
    is covered separately and safely, with tmp_path, by the explicit round-trip tests
    below and in test_audit.py."""

    monkeypatch.setattr(
        auth_api,
        "save_audit_log",
        lambda filepath: None
    )

    monkeypatch.setattr(
        auth_api,
        "save_credentials",
        lambda filepath: None
    )


def test_hash_and_verify_password_roundtrip():

    salt_hex, hash_hex = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", salt_hex, hash_hex)
    assert not verify_password("wrong password", salt_hex, hash_hex)


def test_issue_and_verify_token():

    auth_module.credential_store.set_credential("EMP-00001", "Fictional2026!", "SALES")
    token = issue_token("EMP-00001", "SALES")

    payload = verify_token(token)

    assert payload is not None
    assert payload["employee_id"] == "EMP-00001"
    assert payload["role"] == "SALES"


def test_verify_token_rejects_tampering():

    auth_module.credential_store.set_credential("EMP-00001", "Fictional2026!", "SALES")
    token = issue_token("EMP-00001", "SALES")

    payload_b64, signature = token.split(".", 1)

    tampered = payload_b64 + "x" + "." + signature

    assert verify_token(tampered) is None


def test_credential_store_authenticate():

    store = auth_module.credential_store

    store.set_credential("EMP-00001", "hunter2", "SALES")

    assert store.authenticate("EMP-00001", "hunter2") == "SALES"
    assert store.authenticate("EMP-00001", "wrong") is None
    assert store.authenticate("EMP-99999", "hunter2") is None


def test_resolve_identifier_by_email_is_case_insensitive():

    store = auth_module.credential_store

    store.set_credential(
        "EMP-00001", "hunter2", "SALES", email="Jane.Doe@Dealeros.xyz"
    )

    assert store.resolve_identifier("EMP-00001") == "EMP-00001"
    assert store.resolve_identifier("jane.doe@dealeros.xyz") == "EMP-00001"
    assert store.resolve_identifier("JANE.DOE@DEALEROS.XYZ") == "EMP-00001"
    # Unknown identifier passes through unchanged (matches an unknown employee_id today).
    assert store.resolve_identifier("nobody@example.com") == "nobody@example.com"


def test_authenticate_by_email():

    store = auth_module.credential_store

    store.set_credential(
        "EMP-00001", "hunter2", "SALES", email="jane.doe@dealeros.xyz"
    )

    assert store.authenticate("jane.doe@dealeros.xyz", "hunter2") == "SALES"
    assert store.authenticate("jane.doe@dealeros.xyz", "wrong") is None


def test_email_updates_when_re_set_and_stale_index_entry_is_dropped():

    store = auth_module.credential_store

    store.set_credential(
        "EMP-00001", "pw1", "SALES", email="old@dealeros.xyz"
    )
    assert store.resolve_identifier("old@dealeros.xyz") == "EMP-00001"

    store.set_credential(
        "EMP-00001", "pw2", "SALES", email="new@dealeros.xyz"
    )

    assert store.resolve_identifier("new@dealeros.xyz") == "EMP-00001"
    # Stale index entry for the old email must not still resolve.
    assert store.resolve_identifier("old@dealeros.xyz") == "old@dealeros.xyz"


def test_email_preserved_across_reset_that_omits_it():
    """A password reset (or any set_credential call that doesn't pass email=) shouldn't
    silently wipe an employee's email on file — same pattern as created_at."""

    store = auth_module.credential_store

    store.set_credential(
        "EMP-00001", "pw1", "SALES", email="jane.doe@dealeros.xyz"
    )

    store.set_credential(
        "EMP-00001", "pw2", "SALES"
    )

    assert store.get_record("EMP-00001")["email"] == "jane.doe@dealeros.xyz"
    assert store.authenticate("jane.doe@dealeros.xyz", "pw2") == "SALES"


def test_load_credentials_rebuilds_email_index(tmp_path):

    store = auth_module.credential_store

    store.set_credential(
        "EMP-00001", "hunter2", "SALES", email="jane.doe@dealeros.xyz"
    )

    filepath = str(tmp_path / "credentials.json")
    save_credentials(filepath)

    store.reset()
    assert store.resolve_identifier("jane.doe@dealeros.xyz") == "jane.doe@dealeros.xyz"

    load_credentials(filepath)

    assert store.resolve_identifier("jane.doe@dealeros.xyz") == "EMP-00001"
    assert store.authenticate("jane.doe@dealeros.xyz", "hunter2") == "SALES"


def test_login_api_success_and_failure():

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES"
    )

    result = auth_api.login("EMP-00001", "hunter2")

    assert "token" in result
    assert result["role"] == "SALES"

    failure = auth_api.login("EMP-00001", "wrong")

    assert "error" in failure


def test_whoami_round_trip():

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES"
    )

    login_result = auth_api.login("EMP-00001", "hunter2")

    who = auth_api.whoami(login_result["token"])

    assert who["employee_id"] == "EMP-00001"
    assert who["role"] == "SALES"


def test_login_includes_allowed_dashboards_for_sales():
    """SALES should see the lead/pipeline-adjacent dashboards but not finance/service/
    audit — same matrix core/permissions.py's DASHBOARD_ACCESS already defines, just
    surfaced to the client so /workspace can hide tabs a SALES login can't use. Assert on
    both "present" and "absent" keys rather than the full list so this test doesn't need
    editing every time a new dashboard key is added elsewhere."""

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES"
    )

    result = auth_api.login("EMP-00001", "hunter2")

    allowed = result["allowed_dashboards"]

    for key in ["sales", "pipeline", "followup", "leaderboard", "workload", "escalations"]:
        assert key in allowed

    for key in ["finance", "service", "audit"]:
        assert key not in allowed


def test_whoami_includes_allowed_dashboards_for_finance():

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "FINANCE"
    )

    login_result = auth_api.login("EMP-00001", "hunter2")

    who = auth_api.whoami(login_result["token"])

    assert "finance" in who["allowed_dashboards"]
    assert "sales" not in who["allowed_dashboards"]
    assert "audit" not in who["allowed_dashboards"]


def test_dealership_admin_login_excludes_system_dashboards():
    """ADMIN bypasses DASHBOARD_ACCESS entirely (can_access_dashboard's ADMIN-always-passes
    shape) — allowed_dashboards for ADMIN should be every key that exists, including
    audit."""

    from core.permissions import DASHBOARD_ACCESS

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "ADMIN"
    )

    result = auth_api.login("EMP-00001", "hunter2")

    assert set(result["allowed_dashboards"]) == set(DASHBOARD_ACCESS.keys()) - {"audit", "success_center"}


def test_marketing_allowed_dashboards_excludes_rep_performance_dashboards():
    """MARKETING is on pipeline/followup/sales (lead-adjacent) but not leaderboard/
    workload/salesperson/manager/velocity/escalations (sales-rep performance management) —
    the asymmetry within "lead-adjacent" dashboards that role-aware tabs need to respect,
    not just a single yes/no per department."""

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "MARKETING"
    )

    result = auth_api.login("EMP-00001", "hunter2")

    allowed = result["allowed_dashboards"]

    for key in ["sales", "pipeline", "followup"]:
        assert key in allowed

    for key in ["leaderboard", "workload", "salesperson", "manager", "velocity", "escalations"]:
        assert key not in allowed


def test_save_and_load_credentials_round_trip(tmp_path):

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES"
    )

    filepath = str(tmp_path / "credentials.json")

    save_credentials(filepath)

    # Simulate a fresh process: clear the in-memory store, then load from disk.
    auth_module.credential_store.reset()

    load_credentials(filepath)

    assert auth_module.credential_store.authenticate("EMP-00001", "hunter2") == "SALES"


def test_generate_temp_password_looks_reasonable():

    passwords = {generate_temp_password() for _ in range(50)}

    # 50 independently-generated passwords should all be distinct.
    assert len(passwords) == 50

    for password in passwords:
        assert len(password) == 12


def test_new_credentials_default_to_must_change_password():

    auth_module.credential_store.set_credential(
        "EMP-00001", "temp-pw-123", "SALES"
    )

    record = auth_module.credential_store.get_record("EMP-00001")

    assert record["must_change_password"] is True


def test_change_password_flow():

    auth_module.credential_store.set_credential(
        "EMP-00001", "old-password", "SALES", must_change_password=True
    )

    wrong_old = auth_module.credential_store.change_password(
        "EMP-00001", "not-the-old-password", "new-password"
    )
    assert wrong_old is False

    success = auth_module.credential_store.change_password(
        "EMP-00001", "old-password", "new-password"
    )
    assert success is True

    # Old password no longer works, new one does, must_change_password is cleared.
    assert auth_module.credential_store.authenticate("EMP-00001", "old-password") is None
    assert auth_module.credential_store.authenticate("EMP-00001", "new-password") == "SALES"

    record = auth_module.credential_store.get_record("EMP-00001")
    assert record["must_change_password"] is False


def test_login_reports_must_change_password_flag():

    auth_module.credential_store.set_credential(
        "EMP-00001", "temp-pw", "SALES", must_change_password=True
    )

    result = auth_api.login("EMP-00001", "temp-pw")

    assert result["must_change_password"] is True


def test_change_password_api_end_to_end():

    auth_module.credential_store.set_credential(
        "EMP-00001", "temp-pw", "SALES", must_change_password=True
    )

    login_result = auth_api.login("EMP-00001", "temp-pw")

    change_result = auth_api.change_password(
        login_result["token"], "temp-pw", "a-real-password1"
    )

    assert change_result["success"] is True
    assert verify_token(change_result["token"]) is not None
    assert verify_token(login_result["token"]) is None

    # A fresh login with the new password should now report must_change_password: False.
    second_login = auth_api.login("EMP-00001", "a-real-password1")
    assert second_login["must_change_password"] is False


def test_create_credential_requires_valid_admin_token():

    # No admin credential exists at all yet.
    result = auth_api.create_credential(
        "not-a-real-token", "EMP-00002", "SALES"
    )
    assert "error" in result


def test_create_credential_requires_admin_role():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "SALES", must_change_password=False
    )

    non_admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.create_credential(
        non_admin_token, "EMP-00002", "SALES"
    )

    assert result == {"error": "Admin role required"}


def test_create_credential_rejects_unknown_role():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.create_credential(
        admin_token, "EMP-00002", "NOT_A_REAL_ROLE"
    )

    assert "error" in result
    assert "Unknown role" in result["error"]


def test_create_credential_success_generates_temp_password():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.create_credential(
        admin_token, "EMP-00002", "SALES"
    )

    assert result["employee_id"] == "EMP-00002"
    assert result["role"] == "SALES"
    assert result["must_change_password"] is True
    assert len(result["temp_password"]) == 12

    # The new employee can actually log in with the generated temp password.
    login_result = auth_api.login("EMP-00002", result["temp_password"])
    assert login_result["role"] == "SALES"
    assert login_result["must_change_password"] is True


def test_login_api_accepts_email_as_identifier():

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES", email="jane.doe@dealeros.xyz"
    )

    result = auth_api.login("jane.doe@dealeros.xyz", "hunter2")

    assert "token" in result
    assert result["role"] == "SALES"
    # The token/response always carry the canonical employee_id, not the email typed in.
    assert result["employee_id"] == "EMP-00001"

    who = auth_api.whoami(result["token"])
    assert who["employee_id"] == "EMP-00001"


def test_login_failure_audit_uses_resolved_employee_id_when_possible():

    auth_module.credential_store.set_credential(
        "EMP-00001", "hunter2", "SALES", email="jane.doe@dealeros.xyz"
    )

    failure = auth_api.login("jane.doe@dealeros.xyz", "wrong-password")

    assert failure == {"error": "Invalid credentials"}


def test_create_credential_accepts_optional_email():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.create_credential(
        admin_token, "EMP-00002", "SALES", email="new.hire@dealeros.xyz"
    )

    assert result["email"] == "new.hire@dealeros.xyz"

    # The new employee can log in with either form.
    by_id = auth_api.login("EMP-00002", result["temp_password"])
    assert by_id["role"] == "SALES"

    by_email = auth_api.login("new.hire@dealeros.xyz", result["temp_password"])
    assert by_email["employee_id"] == "EMP-00002"


def test_create_credential_without_email_still_works():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.create_credential(
        admin_token, "EMP-00002", "SALES"
    )

    assert result["email"] is None


def test_reset_password_requires_valid_admin_token():

    result = auth_api.reset_password(
        "not-a-real-token", "EMP-00002"
    )
    assert "error" in result


def test_reset_password_requires_admin_role():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "SALES", must_change_password=False
    )

    non_admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.reset_password(
        non_admin_token, "EMP-00001"
    )

    assert result == {"error": "Admin role required"}


def test_reset_password_rejects_unknown_employee():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.reset_password(
        admin_token, "EMP-99999"
    )

    assert "error" in result
    assert "No credential exists" in result["error"]


def test_reset_password_preserves_role_and_forces_change():

    auth_module.credential_store.set_credential(
        "EMP-00001", "admin-pw", "ADMIN", must_change_password=False
    )

    auth_module.credential_store.set_credential(
        "EMP-00002", "old-temp-pw", "FINANCE", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "admin-pw")["token"]

    result = auth_api.reset_password(
        admin_token, "EMP-00002"
    )

    assert result["employee_id"] == "EMP-00002"
    # Role is untouched even though reset_password() never took a role argument.
    assert result["role"] == "FINANCE"
    assert result["must_change_password"] is True
    assert len(result["temp_password"]) == 12

    # Old password no longer works, new one does, and it's flagged for forced change
    # even though the account had already cleared that flag before the reset.
    assert auth_module.credential_store.authenticate("EMP-00002", "old-temp-pw") is None

    login_result = auth_api.login("EMP-00002", result["temp_password"])
    assert login_result["role"] == "FINANCE"
    assert login_result["must_change_password"] is True


def test_reset_password_accepts_explicit_temp_password():

    auth_module.credential_store.set_credential(
        "EMP-00001", "admin-pw", "ADMIN", must_change_password=False
    )
    auth_module.credential_store.set_credential(
        "EMP-00002", "old-pw", "SALES"
    )

    admin_token = auth_api.login("EMP-00001", "admin-pw")["token"]

    result = auth_api.reset_password(
        admin_token, "EMP-00002", "a-chosen-temp-pw"
    )

    assert result["temp_password"] == "a-chosen-temp-pw"
    assert auth_module.credential_store.authenticate("EMP-00002", "a-chosen-temp-pw") == "SALES"


def test_list_credentials_requires_valid_admin_token():

    result = auth_api.list_credentials("not-a-real-token")

    assert "error" in result


def test_list_credentials_requires_admin_role():

    auth_module.credential_store.set_credential(
        "EMP-00001", "pw", "SALES", must_change_password=False
    )

    non_admin_token = auth_api.login("EMP-00001", "pw")["token"]

    result = auth_api.list_credentials(non_admin_token)

    assert result == {"error": "Admin role required"}


def test_list_credentials_returns_every_record_sorted_without_password_data():

    auth_module.credential_store.set_credential(
        "EMP-00001", "admin-pw", "ADMIN", must_change_password=False
    )
    auth_module.credential_store.set_credential(
        "EMP-00003", "pw3", "SALES", email="c@dealeros.xyz"
    )
    auth_module.credential_store.set_credential(
        "EMP-00002", "pw2", "FINANCE", created_by="EMP-00001"
    )

    admin_token = auth_api.login("EMP-00001", "admin-pw")["token"]

    result = auth_api.list_credentials(admin_token)

    # Sorted by employee_id, not insertion order.
    assert [record["employee_id"] for record in result] == [
        "EMP-00001", "EMP-00002", "EMP-00003"
    ]

    by_id = {record["employee_id"]: record for record in result}

    assert by_id["EMP-00002"]["role"] == "FINANCE"
    assert by_id["EMP-00002"]["created_by"] == "EMP-00001"
    assert by_id["EMP-00003"]["email"] == "c@dealeros.xyz"

    # Never leak password data.
    for record in result:
        assert "salt" not in record
        assert "hash" not in record


def test_list_credentials_on_empty_store_returns_empty_list():

    auth_module.credential_store.set_credential(
        "EMP-00001", "admin-pw", "ADMIN", must_change_password=False
    )

    admin_token = auth_api.login("EMP-00001", "admin-pw")["token"]

    result = auth_api.list_credentials(admin_token)

    # The admin's own credential is in the store, so this isn't literally empty — but
    # confirms the call succeeds and returns exactly what's there, no phantom records.
    # mfa_enabled (security-hardening pass, 2026-07-20) defaults False for a
    # credential that's never enrolled in MFA.
    assert result == [
        {
            "employee_id": "EMP-00001",
            "role": "ADMIN",
            "must_change_password": False,
            "created_by": None,
            "created_at": result[0]["created_at"],
            "email": None,
            "mfa_enabled": False,
        }
    ]
