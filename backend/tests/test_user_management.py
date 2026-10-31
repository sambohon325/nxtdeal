"""
Bumper-parity user management (2026-07-25): create a user (Employee entity + login +
role) in one admin action, reassign roles without a password reset, and the new BDC
role. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import EMPLOYEE
from core.auth import credential_store
from core.permissions import ADMIN, SALES, BDC, OPERATIONS, DASHBOARD_ACCESS, ENTITY_ACCESS, LEAD
from core.security import can_access_dashboard, can_access_entity
from core import user_management, user_management_api
from core.auth_api import VALID_ROLES


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    credential_store.reset()
    yield
    ledger.reset()
    credential_store.reset()


# --- BDC role wiring ---

def test_bdc_is_a_valid_assignable_role():
    assert BDC in VALID_ROLES
    roles = {r["role"] for r in user_management_api.list_roles_api()["roles"]}
    assert BDC in roles


def test_bdc_role_sees_scoped_dashboards_only():
    # BDC can work the lead-followup surface + its own dashboard...
    assert can_access_dashboard(BDC, "bdc") is True
    assert can_access_dashboard(BDC, "pipeline") is True
    assert can_access_dashboard(BDC, "followup") is True
    assert can_access_entity(BDC, LEAD) is True
    # ...but not finance/service or the sales-management dashboards.
    assert can_access_dashboard(BDC, "finance") is False
    assert can_access_dashboard(BDC, "service") is False
    assert can_access_dashboard(BDC, "leaderboard") is False


def test_bdc_endpoints_allow_the_bdc_role():
    from core import bdc_api
    assert BDC in bdc_api._BDC_ROLES


# --- create_user ---

def test_create_user_makes_employee_and_login():
    result = user_management_api.create_user_api(
        ADMIN, "EMP-ADMIN", "Casey", "Reyes", "casey@dealer.com", BDC,
        department="Sales", title="BDC Rep",
    )
    assert "error" not in result
    emp_id = result["employee_id"]
    assert result["role"] == BDC
    assert result["temp_password"]              # returned once
    assert result["must_change_password"] is True
    # Employee entity exists with the canonical shape.
    entity = user_management.get_employee(emp_id)
    assert entity is not None and entity.entity_type == EMPLOYEE
    assert entity.attributes["FirstName"] == "Casey"
    assert entity.attributes["Department"] == "Sales"
    # And the login works with the returned temp password, resolving to the BDC role.
    assert credential_store.authenticate(emp_id, result["temp_password"]) == BDC
    # Login-by-email also works.
    assert credential_store.authenticate("casey@dealer.com", result["temp_password"]) == BDC


def test_create_user_requires_admin_and_validates():
    # Non-admin blocked.
    assert "error" in user_management_api.create_user_api(SALES, "EMP-1", "A", "B", "", BDC)
    assert len(user_management.list_employees()) == 0
    # Bad role rejected.
    assert "error" in user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "A", "B", "", "WIZARD")
    # Missing name rejected.
    assert "error" in user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "", "B", "", SALES)


def test_create_user_rejects_duplicate_email():
    first = user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "A", "B", "dup@x.com", SALES)
    assert "error" not in first
    second = user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "C", "D", "dup@x.com", SALES)
    assert "error" in second


# --- role assignment ---

def test_update_user_role_changes_role_without_password_reset():
    created = user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "Sam", "Lee", "sam@x.com", SALES)
    emp_id, pw = created["employee_id"], created["temp_password"]
    result = user_management_api.update_user_role_api(ADMIN, "EMP-ADMIN", emp_id, BDC)
    assert result["old_role"] == SALES and result["new_role"] == BDC
    # Password is unchanged; the role now authenticates as BDC.
    assert credential_store.authenticate(emp_id, pw) == BDC


def test_update_user_role_guards():
    created = user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "Sam", "Lee", "", SALES)
    emp_id = created["employee_id"]
    assert "error" in user_management_api.update_user_role_api(SALES, "EMP-1", emp_id, BDC)  # not admin
    assert "error" in user_management_api.update_user_role_api(ADMIN, "EMP-ADMIN", emp_id, "WIZARD")  # bad role
    assert "error" in user_management_api.update_user_role_api(ADMIN, "EMP-ADMIN", "EMP-NOPE", BDC)  # no login
    assert "error" in user_management_api.update_user_role_api(ADMIN, "EMP-ADMIN", emp_id, SALES)  # already SALES


# --- roster ---

def test_list_users_joins_entities_and_logins():
    user_management_api.create_user_api(ADMIN, "EMP-ADMIN", "Ann", "Poe", "ann@x.com", BDC)
    roster = user_management_api.list_users_api(ADMIN)
    assert roster["count"] == 1
    row = roster["users"][0]
    assert row["role"] == BDC and row["has_login"] is True and row["name"] == "Ann Poe"
    # Non-privileged role can't see the roster.
    assert "error" in user_management_api.list_users_api(SALES)
