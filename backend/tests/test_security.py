"""
Tests for core/security.py's can_access_entity (entity-type-level access, used by Phase
9's /search, /entity/{id}, /question) and can_access_dashboard (per-department dashboard
ACL, used by every /dashboard/* route — see core/permissions.py's DASHBOARD_ACCESS for
where these role assumptions came from). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from core.security import can_access_entity, can_access_dashboard
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.entity_types import VEHICLE, FINANCE_CONTRACT, EMPLOYEE, CAMPAIGN


def test_role_in_entity_access_list_is_allowed():

    assert can_access_entity(SALES, VEHICLE) is True


def test_role_not_in_entity_access_list_is_denied():

    # SALES is not listed under FINANCE_CONTRACT in core/permissions.py's ENTITY_ACCESS.
    assert can_access_entity(SALES, FINANCE_CONTRACT) is False
    assert can_access_entity(FINANCE, FINANCE_CONTRACT) is True


def test_admin_always_allowed_for_known_entity_types():

    assert can_access_entity(ADMIN, VEHICLE) is True
    assert can_access_entity(ADMIN, FINANCE_CONTRACT) is True


def test_admin_allowed_even_for_entity_types_missing_from_entity_access():
    """EMPLOYEE exists in core/entity_types.py but has no ENTITY_ACCESS entry in
    core/permissions.py. Without the ADMIN bypass, even an admin would be denied here —
    this is the bug fixed in core/security.py during the Phase 9 wrap-up. (CAMPAIGN used
    to be another example here, but session 31 gave it a real ENTITY_ACCESS entry, so it
    is no longer a "missing entry" case — admins now reach it via the entry, not the
    bypass.)"""

    assert can_access_entity(ADMIN, EMPLOYEE) is True


def test_non_admin_denied_for_entity_types_missing_from_entity_access():

    assert can_access_entity(SALES, EMPLOYEE) is False
    # CAMPAIGN gained a broad-internal ENTITY_ACCESS entry in session 31 that includes
    # SERVICE, so a SERVICE role can now legitimately reach it — the campaign engine's
    # access is enforced at the approve/activate layer, not by hiding the entity.
    assert can_access_entity(SERVICE, CAMPAIGN) is True


def test_dashboard_access_allows_listed_roles():

    assert can_access_dashboard(SALES, "sales") is True
    assert can_access_dashboard(MARKETING, "sales") is True
    assert can_access_dashboard(SERVICE, "service") is True
    assert can_access_dashboard(FINANCE, "finance") is True


def test_dashboard_access_denies_unlisted_roles():

    # SERVICE isn't in DASHBOARD_ACCESS["finance"] — F&I-specific data.
    assert can_access_dashboard(SERVICE, "finance") is False

    # MARKETING can see the lead/pipeline dashboards but not sales-rep performance
    # management ones (workload/leaderboard/manager/salesperson/velocity/escalations).
    assert can_access_dashboard(MARKETING, "leaderboard") is False
    assert can_access_dashboard(MARKETING, "workload") is False


def test_dashboard_access_marketing_sees_pipeline_but_not_rep_performance():

    assert can_access_dashboard(MARKETING, "pipeline") is True
    assert can_access_dashboard(MARKETING, "followup") is True
    assert can_access_dashboard(MARKETING, "salesperson") is False


def test_executive_dashboard_restricted_to_admin_and_operations():

    assert can_access_dashboard(ADMIN, "executive") is True
    assert can_access_dashboard(OPERATIONS, "executive") is True
    assert can_access_dashboard(SALES, "executive") is False
    assert can_access_dashboard(MARKETING, "executive") is False
    assert can_access_dashboard(SERVICE, "executive") is False
    assert can_access_dashboard(FINANCE, "executive") is False


def test_dealership_admin_has_operational_dashboards_but_needs_system_scope():

    for key in ("sales", "service", "finance", "executive", "leaderboard"):
        assert can_access_dashboard(ADMIN, key) is True


def test_operations_sees_every_dashboard():
    """OPERATIONS is listed on every DASHBOARD_ACCESS entry except the ADMIN-only audit
    one — mirrors it being on every ENTITY_ACCESS entry too."""

    for key in (
        "sales", "service", "finance", "executive", "pipeline", "followup",
        "salesperson", "manager", "leaderboard", "workload", "velocity", "escalations"
    ):
        assert can_access_dashboard(OPERATIONS, key) is True

    assert can_access_dashboard(OPERATIONS, "audit") is False


def test_unknown_dashboard_key_denied_for_non_admin():

    assert can_access_dashboard(SALES, "not_a_real_dashboard") is False
    assert can_access_dashboard(ADMIN, "not_a_real_dashboard") is True


def test_system_scope_is_required_in_addition_to_admin_role():
    from core.administration_access import system_admin_context
    assert not can_access_dashboard(ADMIN, "audit")
    token = system_admin_context.set(True)
    try:
        assert can_access_dashboard(ADMIN, "audit")
        assert not can_access_dashboard("SALES", "audit")
    finally:
        system_admin_context.reset(token)
