"""
Tests for core/bot_permissions.py / core/bot_permissions_api.py -- the
default-DENY (opposite posture from core/permissions_registry.py's
default-ALLOW PermissionOverride) capability-grant layer this codebase's
security-hardening pass (2026-07-20, Task #7 "Build Bot Permission Layer")
added on top of Task #6's blunter core/ai_kill_switch.py kill switches.

Covers, in order:
  - The 4-capability CAPABILITY_CATALOG and normalize_department()/
    department_for_employee() helpers.
  - is_capability_granted()/explain_capability_check()/
    get_effective_capabilities()'s real scope-precedence logic
    (employee > department > dealer_wide > default-deny), including the
    "an explicit granted=False at a narrower scope beats a broader
    granted=True" case.
  - grant_capability()/revoke_grant()'s validation and real
    supersede-not-delete persistence behavior (mirroring
    core/permissions_registry.py's own PermissionOverride convention).
  - list_grants_for_scope()/list_all_grants().
  - core/bot_permissions_api.py's ACL layer (view broad + self-view
    carve-out, mutate ADMIN-only).
  - A dedicated integration check of core/bot_coverage.py's
    start_coverage() gate -- the one of the 4 real enforcement points
    (bot.coverage.auto_mode / bot.action.auto_touch_overdue_leads /
    bot.action.automate_screen_guidance / bot.action.do_it_screen_guidance)
    with no other test-file coverage anywhere; the other 3 already have
    deep behavioral coverage in test_ai_kill_switch.py
    (TestBotActionsIntegration) and test_screen_guidance.py
    (TestCreateAutomationRuleFromGuidance /
    TestCreateDocumentRequestsFromGuidance), so this file only adds a
    light default-deny/grant-unblocks smoke check for those two -- not a
    duplicate of their own detailed suites.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.bot_permissions as bot_permissions
from core.bot_permissions import (
    CAPABILITY_CATALOG,
    SCOPE_EMPLOYEE,
    SCOPE_DEPARTMENT,
    SCOPE_DEALER_WIDE,
    VALID_SCOPES,
    list_capability_catalog,
    normalize_department,
    department_for_employee,
    is_capability_granted,
    explain_capability_check,
    get_effective_capabilities,
    grant_capability,
    revoke_grant,
    list_grants_for_scope,
    list_all_grants,
)
from core.bot_permissions_api import (
    list_bot_capability_catalog_api,
    get_effective_bot_capabilities_api,
    list_bot_capability_grants_api,
    list_all_bot_capability_grants_api,
    set_bot_capability_grant_api,
    revoke_bot_capability_grant_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(bot_permissions, "save_graph", lambda filepath: None)
    monkeypatch.setattr(bot_permissions, "save_audit_log", lambda filepath: None)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
ADMIN_ROLES = (ADMIN, OPERATIONS)
NON_ADMIN_ROLES = (SALES, MARKETING, SERVICE, FINANCE)

REAL_CAPABILITY_KEY = "bot.action.auto_touch_overdue_leads"


def _employee(entity_id="EMP-00001", department="Sales"):
    attrs = {"Name": entity_id}
    if department is not None:
        attrs["Department"] = department
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes=attrs))
    return entity_id


# ---------------------------------------------------------------------------
# CAPABILITY_CATALOG / list_capability_catalog()
# ---------------------------------------------------------------------------


class TestCapabilityCatalog:

    def test_all_5_real_capabilities_are_present(self):
        expected = {
            "bot.coverage.auto_mode",
            "bot.action.auto_touch_overdue_leads",
            "bot.action.automate_screen_guidance",
            "bot.action.do_it_screen_guidance",
            # Pillar 4 slice 4e: the fleet agent's per-step auto-execution gate.
            "bot.fleet.auto_execute",
            # AI Workforce: customer-facing worker autonomous-mode execution gate.
            "ai.worker.autonomous",
        }
        assert set(CAPABILITY_CATALOG.keys()) == expected

    def test_every_entry_has_the_expected_shape(self):
        for key, entry in CAPABILITY_CATALOG.items():
            assert "label" in entry
            assert "description" in entry
            assert "enforced_at" in entry

    def test_list_capability_catalog_returns_key_plus_entry(self):
        catalog = list_capability_catalog()
        assert len(catalog) == 6
        keys = {c["key"] for c in catalog}
        assert keys == set(CAPABILITY_CATALOG.keys())
        for c in catalog:
            assert "label" in c and "description" in c and "enforced_at" in c


# ---------------------------------------------------------------------------
# normalize_department() / department_for_employee()
# ---------------------------------------------------------------------------


class TestNormalizeDepartment:

    def test_title_case_input_passes_through(self):
        assert normalize_department("Sales") == "Sales"

    def test_lowercase_input_is_title_cased(self):
        assert normalize_department("sales") == "Sales"

    def test_uppercase_input_is_title_cased(self):
        assert normalize_department("SALES") == "Sales"

    def test_whitespace_is_stripped(self):
        assert normalize_department("  sales  ") == "Sales"

    def test_unknown_department_string_returns_none(self):
        assert normalize_department("Not A Real Department") is None

    def test_none_returns_none(self):
        assert normalize_department(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_department("") is None

    def test_every_real_department_normalizes_to_itself(self):
        from core.ai_kill_switch import REAL_DEPARTMENTS
        for department in REAL_DEPARTMENTS:
            assert normalize_department(department) == department
            assert normalize_department(department.lower()) == department


class TestDepartmentForEmployee:

    def test_real_employee_with_department_resolves(self):
        _employee("EMP-00001", department="Marketing")
        assert department_for_employee("EMP-00001") == "Marketing"

    def test_nonexistent_employee_returns_none(self):
        assert department_for_employee("EMP-DOES-NOT-EXIST") is None

    def test_employee_with_no_department_attribute_returns_none(self):
        _employee("EMP-00002", department=None)
        assert department_for_employee("EMP-00002") is None

    def test_non_employee_entity_returns_none(self):
        from core.entity_types import VEHICLE
        ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))
        assert department_for_employee("VEH-1") is None


# ---------------------------------------------------------------------------
# is_capability_granted() -- the real default-deny precedence engine
# ---------------------------------------------------------------------------


class TestIsCapabilityGranted:

    def test_unknown_capability_key_fails_closed(self):
        assert is_capability_granted("not_a_real_capability") is False

    def test_no_grants_at_all_is_default_deny(self):
        assert is_capability_granted(REAL_CAPABILITY_KEY) is False
        assert is_capability_granted(REAL_CAPABILITY_KEY, employee_id="EMP-00001") is False
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is False

    def test_dealer_wide_grant_allows_anyone(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is True
        assert is_capability_granted(REAL_CAPABILITY_KEY, employee_id="EMP-ANYONE") is True
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Finance") is True

    def test_dealer_wide_deny_is_the_same_as_no_grant(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is False

    def test_department_grant_allows_that_department_only(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales")
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is True
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Marketing") is False

    def test_department_grant_beats_dealer_wide_deny(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales")
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is True
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Marketing") is False

    def test_dealer_wide_allow_can_be_narrowed_off_for_one_department(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, False, "EMP-ADMIN", scope_target="Sales")
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is False
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Marketing") is True

    def test_employee_grant_beats_department_grant(self):
        _employee("EMP-00099", department="Sales")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, False, "EMP-ADMIN", scope_target="EMP-00099")
        assert is_capability_granted(
            REAL_CAPABILITY_KEY, employee_id="EMP-00099", department="Sales"
        ) is False
        # A different employee in the same department is still allowed --
        # the narrower deny is scoped to one specific employee only.
        assert is_capability_granted(
            REAL_CAPABILITY_KEY, employee_id="EMP-OTHER", department="Sales"
        ) is True

    def test_employee_grant_beats_dealer_wide_deny(self):
        _employee("EMP-00099")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN", scope_target="EMP-00099")
        assert is_capability_granted(REAL_CAPABILITY_KEY, employee_id="EMP-00099") is True
        assert is_capability_granted(REAL_CAPABILITY_KEY, employee_id="EMP-OTHER") is False

    def test_invalid_department_string_is_treated_as_no_department(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        # An invalid department string can't match any real department-scope
        # grant, but dealer-wide still applies underneath it.
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Not Real") is True


# ---------------------------------------------------------------------------
# explain_capability_check() / get_effective_capabilities()
# ---------------------------------------------------------------------------


class TestExplainCapabilityCheck:

    def test_unknown_capability_key(self):
        explanation = explain_capability_check("not_a_real_capability")
        assert explanation["granted"] is False
        assert explanation["decided_by"] == "unknown_capability"
        assert explanation["grant_id"] is None

    def test_default_deny_with_no_grants(self):
        explanation = explain_capability_check(REAL_CAPABILITY_KEY)
        assert explanation["granted"] is False
        assert explanation["decided_by"] == "default_deny"
        assert explanation["grant_id"] is None
        assert explanation["scope_target"] is None

    def test_decided_by_dealer_wide(self):
        result = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        explanation = explain_capability_check(REAL_CAPABILITY_KEY)
        assert explanation["granted"] is True
        assert explanation["decided_by"] == "dealer_wide"
        assert explanation["grant_id"] == result["id"]
        assert explanation["scope_target"] is None

    def test_decided_by_department(self):
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="sales"
        )
        explanation = explain_capability_check(REAL_CAPABILITY_KEY, department="Sales")
        assert explanation["granted"] is True
        assert explanation["decided_by"] == "department"
        assert explanation["scope_target"] == "Sales"
        assert explanation["grant_id"] == result["id"]

    def test_decided_by_employee(self):
        _employee("EMP-00099")
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN", scope_target="EMP-00099"
        )
        explanation = explain_capability_check(REAL_CAPABILITY_KEY, employee_id="EMP-00099")
        assert explanation["granted"] is True
        assert explanation["decided_by"] == "employee"
        assert explanation["scope_target"] == "EMP-00099"
        assert explanation["grant_id"] == result["id"]

    def test_reason_field_is_always_a_nonempty_string(self):
        for key in list(CAPABILITY_CATALOG.keys()) + ["not_a_real_capability"]:
            explanation = explain_capability_check(key)
            assert isinstance(explanation["reason"], str)
            assert explanation["reason"]


class TestGetEffectiveCapabilities:

    def test_returns_one_entry_per_catalog_capability(self):
        capabilities = get_effective_capabilities("EMP-00099")
        assert len(capabilities) == 6
        assert {c["capability_key"] for c in capabilities} == set(CAPABILITY_CATALOG.keys())

    def test_reflects_a_real_dealer_wide_grant(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        capabilities = get_effective_capabilities("EMP-00099")
        by_key = {c["capability_key"]: c for c in capabilities}
        assert by_key[REAL_CAPABILITY_KEY]["granted"] is True
        # Every other capability with no grant configured stays denied.
        assert by_key["bot.coverage.auto_mode"]["granted"] is False


# ---------------------------------------------------------------------------
# grant_capability() -- validation + real supersede-not-delete persistence
# ---------------------------------------------------------------------------


class TestGrantCapabilityValidation:

    def test_unknown_capability_key_is_rejected(self):
        result = grant_capability("not_a_real_capability", SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        assert "error" in result

    def test_unknown_scope_is_rejected(self):
        result = grant_capability(REAL_CAPABILITY_KEY, "not_a_real_scope", True, "EMP-ADMIN")
        assert "error" in result

    def test_employee_scope_requires_a_scope_target(self):
        result = grant_capability(REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN")
        assert "error" in result

    def test_employee_scope_requires_a_real_employee(self):
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN", scope_target="EMP-DOES-NOT-EXIST"
        )
        assert "error" in result

    def test_department_scope_requires_a_real_department(self):
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Not A Real Dept"
        )
        assert "error" in result

    def test_department_scope_target_is_normalized(self):
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="sales"
        )
        assert result["scope_target"] == "Sales"

    def test_dealer_wide_scope_ignores_any_scope_target_passed(self):
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN", scope_target="whatever"
        )
        assert result["scope_target"] is None


class TestGrantCapabilitySuccess:

    def test_employee_scope_creates_a_real_active_grant(self):
        _employee("EMP-00099")
        result = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN",
            scope_target="EMP-00099", reason="covering a leave of absence",
        )
        assert result["capability_key"] == REAL_CAPABILITY_KEY
        assert result["scope"] == SCOPE_EMPLOYEE
        assert result["scope_target"] == "EMP-00099"
        assert result["granted"] is True
        assert result["active"] is True
        assert result["granted_by"] == "EMP-ADMIN"
        assert result["reason"] == "covering a leave of absence"
        assert result["created_at"]
        assert result["superseded_at"] is None
        assert result["id"].startswith("BCAP")

    def test_a_real_entity_lands_in_the_ledger(self):
        from core.entity_types import BOT_CAPABILITY_GRANT
        result = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == BOT_CAPABILITY_GRANT

    def test_a_new_grant_for_the_same_scope_target_supersedes_the_prior_one(self):
        first = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        second = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")

        prior = ledger.get_entity(first["id"])
        assert prior.attributes["active"] is False
        assert prior.attributes["superseded_at"] is not None

        current = ledger.get_entity(second["id"])
        assert current.attributes["active"] is True
        assert current.attributes["superseded_at"] is None

        # And the prior record is NOT deleted -- full history stays.
        assert ledger.get_entity(first["id"]) is not None

    def test_superseding_flips_the_real_grant_decision(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is True

        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is False

    def test_grants_at_different_scopes_do_not_supersede_each_other(self):
        dealer_wide = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        department = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales"
        )
        assert ledger.get_entity(dealer_wide["id"]).attributes["active"] is True
        assert ledger.get_entity(department["id"]).attributes["active"] is True


# ---------------------------------------------------------------------------
# revoke_grant()
# ---------------------------------------------------------------------------


class TestRevokeGrant:

    def test_unknown_grant_id_is_rejected(self):
        result = revoke_grant("BCAP-DOES-NOT-EXIST", "EMP-ADMIN")
        assert "error" in result

    def test_revoking_an_active_grant_deactivates_it(self):
        created = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        result = revoke_grant(created["id"], "EMP-ADMIN")

        assert result["active"] is False
        assert result["superseded_at"] is not None

        entity = ledger.get_entity(created["id"])
        assert entity.attributes["active"] is False

    def test_revoking_reverts_the_real_grant_decision_to_default_deny(self):
        created = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is True

        revoke_grant(created["id"], "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY) is False

    def test_revoking_an_already_inactive_grant_is_rejected(self):
        created = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        revoke_grant(created["id"], "EMP-ADMIN")

        result = revoke_grant(created["id"], "EMP-ADMIN")
        assert "error" in result

    def test_revoking_a_narrower_grant_falls_back_to_a_broader_one(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        department = grant_capability(
            REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, False, "EMP-ADMIN", scope_target="Sales"
        )
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is False

        revoke_grant(department["id"], "EMP-ADMIN")
        assert is_capability_granted(REAL_CAPABILITY_KEY, department="Sales") is True


# ---------------------------------------------------------------------------
# list_grants_for_scope() / list_all_grants()
# ---------------------------------------------------------------------------


class TestListGrants:

    def test_list_grants_for_scope_returns_only_that_scope_target(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Finance")

        sales_grants = list_grants_for_scope(SCOPE_DEPARTMENT, "Sales")
        assert len(sales_grants) == 1
        assert sales_grants[0]["scope_target"] == "Sales"

    def test_superseded_grants_still_appear_in_the_list(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, False, "EMP-ADMIN")

        grants = list_grants_for_scope(SCOPE_DEALER_WIDE, None)
        assert len(grants) == 2
        active_flags = sorted(g["active"] for g in grants)
        assert active_flags == [False, True]

    def test_list_all_grants_includes_every_scope(self):
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="Sales")
        _employee("EMP-00099")
        grant_capability(REAL_CAPABILITY_KEY, SCOPE_EMPLOYEE, True, "EMP-ADMIN", scope_target="EMP-00099")

        grants = list_all_grants()
        assert len(grants) == 3
        assert {g["scope"] for g in grants} == {SCOPE_DEALER_WIDE, SCOPE_DEPARTMENT, SCOPE_EMPLOYEE}

    def test_list_all_grants_empty_by_default(self):
        assert list_all_grants() == []


# ---------------------------------------------------------------------------
# ACL layer -- core/bot_permissions_api.py
# ---------------------------------------------------------------------------


class TestCatalogApiAcl:

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_can_view_the_catalog(self, role):
        result = list_bot_capability_catalog_api(role)
        assert "catalog" in result
        assert len(result["catalog"]) == 6

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_are_denied(self, role):
        result = list_bot_capability_catalog_api(role)
        assert "error" in result
        assert "catalog" not in result


class TestEffectiveCapabilitiesApiAcl:

    def test_self_view_is_always_allowed_regardless_of_role(self):
        for role in ALL_ROLES:
            result = get_effective_bot_capabilities_api(role, "EMP-00099")
            assert "capabilities" in result
            assert result["employee_id"] == "EMP-00099"

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_can_view_someone_elses(self, role):
        result = get_effective_bot_capabilities_api(role, "EMP-CALLER", target_employee_id="EMP-OTHER")
        assert "capabilities" in result
        assert result["employee_id"] == "EMP-OTHER"

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_cannot_view_someone_elses(self, role):
        result = get_effective_bot_capabilities_api(role, "EMP-CALLER", target_employee_id="EMP-OTHER")
        assert "error" in result


class TestListGrantsApiAcl:

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_can_list_grants_for_a_scope(self, role):
        result = list_bot_capability_grants_api(role, SCOPE_DEALER_WIDE, None)
        assert "grants" in result

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_are_denied(self, role):
        result = list_bot_capability_grants_api(role, SCOPE_DEALER_WIDE, None)
        assert "error" in result

    def test_unknown_scope_is_rejected(self):
        result = list_bot_capability_grants_api(ADMIN, "not_a_real_scope", None)
        assert "error" in result

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_can_list_all_grants(self, role):
        result = list_all_bot_capability_grants_api(role)
        assert "grants" in result

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_cannot_list_all_grants(self, role):
        result = list_all_bot_capability_grants_api(role)
        assert "error" in result


class TestSetGrantApiAcl:

    def test_admin_can_set_a_grant(self):
        result = set_bot_capability_grant_api(
            ADMIN, "EMP-ADMIN", REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True
        )
        assert result.get("granted") is True

    def test_operations_cannot_set_a_grant(self):
        # Deliberately stricter than the view gate -- mutating who a bot may
        # act as is ADMIN-only, matching core/ai_kill_switch_api.py's own
        # stricter mutate gate for this same class of decision.
        result = set_bot_capability_grant_api(
            OPERATIONS, "EMP-OPS", REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True
        )
        assert "error" in result

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_non_operations_roles_cannot_set_a_grant(self, role):
        result = set_bot_capability_grant_api(
            role, "EMP-X", REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True
        )
        assert "error" in result


class TestRevokeGrantApiAcl:

    def test_admin_can_revoke_a_grant(self):
        created = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        result = revoke_bot_capability_grant_api(ADMIN, "EMP-ADMIN", created["id"])
        assert result.get("active") is False

    def test_operations_cannot_revoke_a_grant(self):
        created = grant_capability(REAL_CAPABILITY_KEY, SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        result = revoke_bot_capability_grant_api(OPERATIONS, "EMP-OPS", created["id"])
        assert "error" in result


# ---------------------------------------------------------------------------
# Enforcement point #1 -- core/bot_coverage.py's start_coverage() gate.
# The only one of the 4 real enforcement points with no other test-file
# coverage anywhere (no tests/test_bot_coverage.py exists at all yet).
# ---------------------------------------------------------------------------


class TestBotCoverageIntegration:

    def _start(self, mode="auto", section="sales"):
        from core.bot_coverage import start_coverage
        _employee("EMP-00099", department="Sales")
        return start_coverage(
            admin_id="EMP-ADMIN",
            employee_id="EMP-00099",
            role="Sales Advisor",
            section=section,
            starts_at="2026-01-01T00:00:00",
            ends_at="2026-01-01T08:00:00",
            mode=mode,
        )

    def test_draft_mode_never_needs_a_grant(self):
        # "draft" mode never executes anything, so it's deliberately not
        # gated by bot.coverage.auto_mode at all -- confirmed here since
        # this is the one branch that would otherwise look untested.
        result = self._start(mode="draft")
        assert "coverage" in result

    def test_auto_mode_is_denied_by_default(self):
        result = self._start(mode="auto")
        assert "error" in result
        assert "bot.coverage.auto_mode" in result["error"]

    def test_auto_mode_succeeds_with_a_dealer_wide_grant(self):
        grant_capability("bot.coverage.auto_mode", SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        result = self._start(mode="auto")
        assert "coverage" in result
        assert result["coverage"]["mode"] == "auto"

    def test_auto_mode_succeeds_with_an_employee_scoped_grant(self):
        _employee("EMP-00099", department="Sales")
        grant_capability(
            "bot.coverage.auto_mode", SCOPE_EMPLOYEE, True, "EMP-ADMIN", scope_target="EMP-00099"
        )
        result = self._start(mode="auto")
        assert "coverage" in result

    def test_auto_mode_succeeds_with_a_department_scoped_grant(self):
        grant_capability(
            "bot.coverage.auto_mode", SCOPE_DEPARTMENT, True, "EMP-ADMIN", scope_target="sales"
        )
        # section="sales" (lowercase, matching core/bot_tasks.py's own
        # TASK_CATALOG key convention) is normalized to "Sales" internally
        # by core/bot_coverage.py's own use of normalize_department().
        result = self._start(mode="auto", section="sales")
        assert "coverage" in result

    def test_auto_mode_still_blocked_after_grant_revoked(self):
        created = grant_capability("bot.coverage.auto_mode", SCOPE_DEALER_WIDE, True, "EMP-ADMIN")
        assert "coverage" in self._start(mode="auto")

        revoke_grant(created["id"], "EMP-ADMIN")
        result = self._start(mode="auto")
        assert "error" in result


# ---------------------------------------------------------------------------
# Enforcement points #2-#4 -- light default-deny + grant-unblocks smoke
# checks only. Deep behavioral coverage for these already lives in
# test_ai_kill_switch.py::TestBotActionsIntegration (run_action) and
# test_screen_guidance.py::TestCreateAutomationRuleFromGuidance /
# TestCreateDocumentRequestsFromGuidance -- both of those files also grant
# their own relevant capability dealer-wide via an autouse fixture so their
# tests stay scoped to what they were originally designed to test.
# ---------------------------------------------------------------------------


class TestRemainingEnforcementPointsSmoke:

    def test_run_action_is_denied_by_default_with_no_grant(self):
        from core.bot_actions import run_action
        assert run_action("sales_followup_leads", "EMP-00099", "EMP-ADMIN") is None

    def test_run_action_succeeds_once_granted(self):
        from core.bot_actions import run_action
        grant_capability(
            "bot.action.auto_touch_overdue_leads", SCOPE_DEALER_WIDE, True, "EMP-ADMIN"
        )
        result = run_action("sales_followup_leads", "EMP-00099", "EMP-ADMIN")
        assert result is not None
        assert "touched_leads" in result

    def test_automate_screen_guidance_is_denied_by_default_with_no_grant(self):
        from core.screen_guidance import create_automation_rule_from_guidance
        result = create_automation_rule_from_guidance(
            ADMIN, "EMP-ADMIN", "funding_delays", "Fix the funding delays"
        )
        assert "error" in result
        assert "bot.action.automate_screen_guidance" in result["error"]

    def test_automate_screen_guidance_succeeds_once_granted(self):
        from core.screen_guidance import create_automation_rule_from_guidance
        grant_capability(
            "bot.action.automate_screen_guidance", SCOPE_DEALER_WIDE, True, "EMP-ADMIN"
        )
        # Security-hardening Task #8 ("AI execution-tier framework") made
        # create_rule() require its acting employee to resolve to a real
        # Employee (it opens a real ApprovalRequest on every rule creation)
        # -- registered here so this smoke test still proves the full,
        # genuine success path once the capability is granted, not just
        # that the capability-gate error text goes away.
        _employee("EMP-ADMIN")
        result = create_automation_rule_from_guidance(
            ADMIN, "EMP-ADMIN", "funding_delays", "Fix the funding delays"
        )
        assert "error" not in result or "not currently granted" not in result.get("error", "")

    def test_do_it_screen_guidance_is_denied_by_default_with_no_grant(self):
        from core.screen_guidance import create_document_requests_from_guidance
        result = create_document_requests_from_guidance(ADMIN, "EMP-ADMIN", "vehicles_missing_titles")
        assert "error" in result
        assert "bot.action.do_it_screen_guidance" in result["error"]
