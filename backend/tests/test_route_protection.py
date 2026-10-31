"""
Tests for api/app.py's route-protection helpers: _authenticate/_require_admin (Phase 9
wrap-up) and _authorize_dashboard (per-department dashboard ACL). Importing api.app
exercises the full startup chain (loading storage/graph.json etc via relative paths) —
same as running `uvicorn api.app:app` for real, and a useful extra check that nothing in
that import chain is broken. Run from backend/ with `pytest` (cwd matters for the
relative storage/*.json paths api.app loads at import time, same as every other test
file in this directory).
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from api.app import _authenticate, _require_admin, _authorize_dashboard
from staff_auth_fixture import staff_token


def test_authenticate_rejects_missing_header():

    payload, error = _authenticate(None)

    assert payload is None
    assert "error" in error


def test_authenticate_rejects_malformed_header():

    payload, error = _authenticate("not-a-bearer-token")

    assert payload is None
    assert "error" in error


def test_authenticate_rejects_invalid_token():

    payload, error = _authenticate("Bearer this-token-does-not-exist")

    assert payload is None
    assert "error" in error


def test_authenticate_accepts_valid_token():

    token = staff_token("EMP-00001", "SALES")

    payload, error = _authenticate(f"Bearer {token}")

    assert error is None
    assert payload["employee_id"] == "EMP-00001"
    assert payload["role"] == "SALES"


def test_require_admin_rejects_non_admin_role():

    token = staff_token("EMP-00001", "SALES")

    payload, error = _require_admin(f"Bearer {token}")

    assert payload is None
    assert error == {"error": "Admin role required"}


def test_require_admin_accepts_admin_role():

    token = staff_token("EMP-00001", "ADMIN")

    payload, error = _require_admin(f"Bearer {token}")

    assert error is None
    assert payload["role"] == "ADMIN"


def test_require_admin_rejects_missing_header():

    payload, error = _require_admin(None)

    assert payload is None
    assert "error" in error


def test_authorize_dashboard_allows_role_on_the_list():

    token = staff_token("EMP-00001", "FINANCE")

    payload, error = _authorize_dashboard(f"Bearer {token}", "finance")

    assert error is None
    assert payload["role"] == "FINANCE"


def test_authorize_dashboard_rejects_role_not_on_the_list():

    token = staff_token("EMP-00001", "SALES")

    payload, error = _authorize_dashboard(f"Bearer {token}", "finance")

    assert payload is None
    assert "Forbidden" in error["error"]
    assert "finance" in error["error"]


def test_authorize_dashboard_rejects_missing_header():

    payload, error = _authorize_dashboard(None, "sales")

    assert payload is None
    assert "error" in error


def test_authorize_dashboard_admin_bypasses_every_key():

    token = staff_token("EMP-00001", "ADMIN")

    payload, error = _authorize_dashboard(f"Bearer {token}", "finance")

    assert error is None
    assert payload["role"] == "ADMIN"
