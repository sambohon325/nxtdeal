"""
Tests for the bulk credential import (imports/credential_import.py / the
run_credential_import.py CLI it powers). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import auth as auth_module
from core import audit as audit_module
from imports.credential_import import import_credentials


@pytest.fixture(autouse=True)
def fresh_state():
    """import_credentials() mutates the real credential_store and audit_log singletons
    (it doesn't touch disk itself — that's run_credential_import.py's job — but it does
    write into memory), so reset both around every test the same way test_auth.py and
    test_audit.py do."""

    auth_module.credential_store.reset()
    audit_module.audit_log.reset()

    yield

    auth_module.credential_store.reset()
    audit_module.audit_log.reset()


def _write_csv(tmp_path, rows):

    path = tmp_path / "employees.csv"

    lines = ["employee_id,role"]
    lines.extend(f"{employee_id},{role}" for employee_id, role in rows)

    path.write_text("\n".join(lines), encoding="utf-8")

    return str(path)


def test_import_creates_credentials_for_every_row(tmp_path):

    csv_path = _write_csv(
        tmp_path,
        [
            ("EMP-00001", "SALES"),
            ("EMP-00002", "SERVICE"),
            ("EMP-00003", "FINANCE")
        ]
    )

    report = import_credentials(csv_path)

    assert len(report) == 3
    assert {entry["employee_id"] for entry in report} == {
        "EMP-00001", "EMP-00002", "EMP-00003"
    }

    for entry in report:
        assert len(entry["temp_password"]) == 12

    # Every employee can actually log in with their generated temp password.
    for entry in report:
        role = auth_module.credential_store.authenticate(
            entry["employee_id"], entry["temp_password"]
        )
        assert role == entry["role"]


def test_import_is_case_insensitive_on_role(tmp_path):

    csv_path = _write_csv(tmp_path, [("EMP-00001", "sales")])

    report = import_credentials(csv_path)

    assert report[0]["role"] == "SALES"


def test_import_rejects_unknown_role_without_creating_anything(tmp_path):

    csv_path = _write_csv(
        tmp_path,
        [
            ("EMP-00001", "SALES"),
            ("EMP-00002", "NOT_A_REAL_ROLE")
        ]
    )

    with pytest.raises(ValueError):
        import_credentials(csv_path)

    # All-or-nothing: the valid row before the bad one must NOT have been created.
    assert auth_module.credential_store.get_record("EMP-00001") is None


def test_import_rejects_missing_employee_id(tmp_path):

    csv_path = _write_csv(tmp_path, [("", "SALES")])

    with pytest.raises(ValueError):
        import_credentials(csv_path)


def test_import_handles_utf8_bom(tmp_path):
    """Windows tools (PowerShell's `Out-File -Encoding utf8`, Notepad's default "UTF-8"
    save) prepend a BOM to text files. Make sure a BOM-prefixed CSV still parses
    correctly instead of silently corrupting the first header field (this happened for
    real — see BUILD_QUEUE.md session log)."""

    path = tmp_path / "employees.csv"

    content = "employee_id,role\nEMP-00001,SALES\n"

    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

    report = import_credentials(str(path))

    assert len(report) == 1
    assert report[0]["employee_id"] == "EMP-00001"


def test_import_with_email_column_supports_login_by_email(tmp_path):
    """The `email` column is optional (2026-07-13 session 20) — rows that have one can
    log in with either their employee_id or that email afterward; rows without one just
    get email=None, same as before this column existed."""

    path = tmp_path / "employees.csv"

    content = (
        "employee_id,role,email\n"
        "EMP-00001,SALES,jane.doe@dealeros.xyz\n"
        "EMP-00002,SERVICE,\n"
    )

    path.write_text(content, encoding="utf-8")

    report = import_credentials(str(path))

    by_id = {entry["employee_id"]: entry for entry in report}

    assert by_id["EMP-00001"]["email"] == "jane.doe@dealeros.xyz"
    assert by_id["EMP-00002"]["email"] is None

    role = auth_module.credential_store.authenticate(
        "jane.doe@dealeros.xyz", by_id["EMP-00001"]["temp_password"]
    )
    assert role == "SALES"


def test_import_records_audit_events(tmp_path):

    csv_path = _write_csv(tmp_path, [("EMP-00001", "SALES")])

    import_credentials(csv_path)

    events = audit_module.audit_log.get_by_type("credential_created")

    assert len(events) == 1
    assert events[0].entity_id == "EMP-00001"
    assert events[0].actor == "bulk_import"
