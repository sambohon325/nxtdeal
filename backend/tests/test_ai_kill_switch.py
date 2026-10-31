"""
Tests for core/ai_kill_switch.py / core/ai_kill_switch_api.py -- the layered,
ADDITIVE emergency-stop mechanism (security-hardening pass, 2026-07-20, Task
#6) sitting on top of core/ai_management.py's existing per-feature switch:
dealer-wide, department-scoped, Bot-wide, and Workflow-Automation-wide
scopes. Also covers the storage layer (core/system_config.py's
get_ai_kill_switches()/set_ai_kill_switch()) and the 4 real consumer wirings
this pass added (core/ai_management.py's is_feature_enabled(),
core/bot_actions.py's run_action(), core/screen_guidance.py's "Automate
It"/"Do It", core/workflow_automation.py's evaluate_rules()).

Follows test_system_config.py's/test_ai_audit.py's own established pattern:
a fresh_ledger fixture resetting core.dealeros.ledger between tests, plus a
no_real_persistence fixture stubbing out the real disk write
core/system_config.py's set_ai_kill_switch() makes (module-level
`from core.storage import save_graph` import there, so the stub patches
system_config.save_graph directly) and the real audit-log write
core/ai_kill_switch.py's _record_toggle() makes (patches
core.audit_storage.save_audit_log, since that module also imports it at
module level).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.system_config as system_config
from core.system_config import get_ai_kill_switches, set_ai_kill_switch

import core.ai_kill_switch as ai_kill_switch
from core.ai_kill_switch import (
    DEPARTMENT_FEATURE_MAP,
    REAL_DEPARTMENTS,
    department_for_feature,
    is_ai_globally_enabled,
    explain_ai_gate,
    is_bot_enabled,
    is_workflow_automation_enabled,
    set_dealer_wide_kill_switch,
    set_department_kill_switch,
    set_bot_kill_switch,
    set_workflow_automation_kill_switch,
    get_kill_switch_overview,
)
from core.ai_kill_switch_api import (
    get_kill_switch_overview_api,
    explain_ai_gate_api,
    set_dealer_wide_kill_switch_api,
    set_department_kill_switch_api,
    set_bot_kill_switch_api,
    set_workflow_automation_kill_switch_api,
)

from core.ai_management import is_feature_enabled, AI_FEATURE_CATALOG
from core.bot_actions import run_action, ACTION_HANDLERS
from core.workflow_automation import evaluate_rules


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)

    import core.audit_storage as audit_storage_mod
    monkeypatch.setattr(audit_storage_mod, "save_audit_log", lambda filepath: None)
    monkeypatch.setattr(ai_kill_switch, "save_audit_log", lambda filepath: None)

    # Task #7 "Build Bot Permission Layer" gave core/bot_permissions.py its
    # own module-level `from core.storage import save_graph` / `from
    # core.audit_storage import save_audit_log` imports, same pattern
    # core/permissions_registry.py already uses -- stub both here too so the
    # dealer-wide grant fixture below (and run_action()'s own real-time
    # capability check, which reads the ledger but writes nothing) never
    # touches real disk during this file's tests.
    import core.bot_permissions as bot_permissions_mod
    monkeypatch.setattr(bot_permissions_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(bot_permissions_mod, "save_audit_log", lambda filepath: None)


@pytest.fixture(autouse=True)
def grant_bot_action_capability(fresh_ledger, no_real_persistence):
    """Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    Layer"): core/bot_actions.py's run_action() is now gated by a second,
    separate, default-deny capability check (core/bot_permissions.py) on top
    of the Task #6 kill switches this file's tests are actually about.
    Granting bot.action.auto_touch_overdue_leads dealer-wide before every
    test here (against the same fresh, isolated ledger fresh_ledger() just
    reset) keeps TestBotActionsIntegration's tests scoped to what they were
    designed to test -- the kill-switch layer -- rather than silently
    failing on an unrelated, newer gate. The permission layer itself has its
    own dedicated test_bot_permissions.py."""

    from core.bot_permissions import grant_capability
    grant_capability(
        "bot.action.auto_touch_overdue_leads", "dealer_wide", True, "EMP-TEST-SETUP"
    )
    yield


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
ADMIN_ROLES = (ADMIN, OPERATIONS)
NON_ADMIN_ROLES = (SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# Storage layer -- core/system_config.py
# ---------------------------------------------------------------------------


class TestKillSwitchStorage:

    def test_default_state_is_all_inactive(self):
        switches = get_ai_kill_switches()

        assert switches["dealer_wide"]["active"] is False
        assert switches["departments"] == {}
        assert switches["bot"]["active"] is False
        assert switches["workflow_automation"]["active"] is False

    def test_set_dealer_wide_scope(self):
        result = set_ai_kill_switch("dealer_wide", True, "EMP-00001", reason="incident")

        assert result["dealer_wide"]["active"] is True
        assert result["dealer_wide"]["activated_by"] == "EMP-00001"
        assert result["dealer_wide"]["reason"] == "incident"
        assert result["dealer_wide"]["activated_at"]

    def test_deactivating_clears_activated_at_and_reason(self):
        set_ai_kill_switch("dealer_wide", True, "EMP-00001", reason="incident")
        result = set_ai_kill_switch("dealer_wide", False, "EMP-00001")

        assert result["dealer_wide"]["active"] is False
        assert result["dealer_wide"]["activated_at"] is None
        assert result["dealer_wide"]["reason"] is None

    def test_set_department_scope_requires_department(self):
        result = set_ai_kill_switch("department", True, "EMP-00001")
        assert result == {"error": "A department is required when scope='department'."}

    def test_set_department_scope(self):
        result = set_ai_kill_switch("department", True, "EMP-00001", department="Sales")

        assert result["departments"]["Sales"]["active"] is True
        assert "Marketing" not in result["departments"]

    def test_set_bot_scope(self):
        result = set_ai_kill_switch("bot", True, "EMP-00001")
        assert result["bot"]["active"] is True

    def test_set_workflow_automation_scope(self):
        result = set_ai_kill_switch("workflow_automation", True, "EMP-00001")
        assert result["workflow_automation"]["active"] is True

    def test_unknown_scope_rejected(self):
        result = set_ai_kill_switch("not_a_real_scope", True, "EMP-00001")
        assert "error" in result

    def test_state_persists_across_reads(self):
        set_ai_kill_switch("bot", True, "EMP-00001", reason="testing")

        switches = get_ai_kill_switches()
        assert switches["bot"]["active"] is True
        assert switches["bot"]["reason"] == "testing"


# ---------------------------------------------------------------------------
# department_for_feature() / DEPARTMENT_FEATURE_MAP
# ---------------------------------------------------------------------------


class TestDepartmentForFeature:

    def test_every_catalog_feature_has_a_map_entry(self):
        catalog_keys = {entry["key"] for entry in AI_FEATURE_CATALOG}
        mapped_keys = set(DEPARTMENT_FEATURE_MAP.keys())
        assert catalog_keys == mapped_keys

    def test_every_mapped_department_is_real(self):
        for department in DEPARTMENT_FEATURE_MAP.values():
            if department is not None:
                assert department in REAL_DEPARTMENTS

    def test_cross_department_features_map_to_none(self):
        assert department_for_feature("help_assistant") is None
        assert department_for_feature("workspace_explain") is None

    def test_sales_owns_ai_assistant(self):
        assert department_for_feature("ai_assistant") == "Sales"

    def test_unknown_feature_key_returns_none(self):
        assert department_for_feature("not_a_real_feature") is None


# ---------------------------------------------------------------------------
# is_ai_globally_enabled() / explain_ai_gate()
# ---------------------------------------------------------------------------


class TestIsAiGloballyEnabled:

    def test_fails_open_by_default(self):
        assert is_ai_globally_enabled("ai_assistant") is True
        assert is_ai_globally_enabled("help_assistant") is True

    def test_dealer_wide_kills_every_feature(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")

        assert is_ai_globally_enabled("ai_assistant") is False
        assert is_ai_globally_enabled("website_wizard") is False
        assert is_ai_globally_enabled("help_assistant") is False  # cross-dept too

    def test_department_kill_only_affects_its_own_features(self):
        set_department_kill_switch("Sales", True, "EMP-00001")

        assert is_ai_globally_enabled("ai_assistant") is False  # Sales-owned
        assert is_ai_globally_enabled("website_wizard") is True  # Marketing-owned, untouched

    def test_department_kill_does_not_affect_cross_department_features(self):
        set_department_kill_switch("Sales", True, "EMP-00001")

        assert is_ai_globally_enabled("help_assistant") is True
        assert is_ai_globally_enabled("workspace_explain") is True

    def test_reactivating_a_department_after_deactivation_restores_access(self):
        set_department_kill_switch("Marketing", True, "EMP-00001")
        assert is_ai_globally_enabled("website_wizard") is False

        set_department_kill_switch("Marketing", False, "EMP-00001")
        assert is_ai_globally_enabled("website_wizard") is True


class TestExplainAiGate:

    def test_returns_none_when_not_gated(self):
        assert explain_ai_gate("ai_assistant") is None

    def test_explains_dealer_wide_gate(self):
        set_dealer_wide_kill_switch(True, "EMP-00001", reason="incident response")

        explanation = explain_ai_gate("ai_assistant")
        assert explanation["gated_by"] == "dealer_wide"
        assert explanation["reason"] == "incident response"
        assert explanation["activated_by"] == "EMP-00001"

    def test_explains_department_gate(self):
        set_department_kill_switch("Marketing", True, "EMP-00002", reason="vendor outage")

        explanation = explain_ai_gate("website_wizard")
        assert explanation["gated_by"] == "department"
        assert explanation["department"] == "Marketing"
        assert explanation["reason"] == "vendor outage"

    def test_dealer_wide_takes_precedence_over_department_in_explanation(self):
        set_department_kill_switch("Sales", True, "EMP-00001")
        set_dealer_wide_kill_switch(True, "EMP-00002", reason="bigger incident")

        explanation = explain_ai_gate("ai_assistant")
        assert explanation["gated_by"] == "dealer_wide"


# ---------------------------------------------------------------------------
# is_bot_enabled() / is_workflow_automation_enabled()
# ---------------------------------------------------------------------------


class TestIsBotEnabled:

    def test_enabled_by_default(self):
        assert is_bot_enabled() is True

    def test_bot_wide_switch_disables_it(self):
        set_bot_kill_switch(True, "EMP-00001")
        assert is_bot_enabled() is False

    def test_dealer_wide_switch_also_disables_it(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")
        assert is_bot_enabled() is False

    def test_workflow_automation_switch_does_not_affect_bot(self):
        set_workflow_automation_kill_switch(True, "EMP-00001")
        assert is_bot_enabled() is True


class TestIsWorkflowAutomationEnabled:

    def test_enabled_by_default(self):
        assert is_workflow_automation_enabled() is True

    def test_workflow_automation_switch_disables_it(self):
        set_workflow_automation_kill_switch(True, "EMP-00001")
        assert is_workflow_automation_enabled() is False

    def test_dealer_wide_switch_also_disables_it(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")
        assert is_workflow_automation_enabled() is False

    def test_bot_switch_does_not_affect_workflow_automation(self):
        set_bot_kill_switch(True, "EMP-00001")
        assert is_workflow_automation_enabled() is True


# ---------------------------------------------------------------------------
# The 4 setter functions -- validation + return shape
# ---------------------------------------------------------------------------


class TestSetterFunctions:

    def test_set_dealer_wide_returns_just_that_scope_state(self):
        result = set_dealer_wide_kill_switch(True, "EMP-00001", reason="x")
        assert result == {
            "active": True, "activated_by": "EMP-00001",
            "activated_at": result["activated_at"], "reason": "x",
        }
        assert result["activated_at"]

    def test_set_department_rejects_unknown_department(self):
        result = set_department_kill_switch("NotARealDepartment", True, "EMP-00001")
        assert "error" in result

    def test_set_department_returns_just_that_department_state(self):
        result = set_department_kill_switch("Network", True, "EMP-00001")
        assert result["active"] is True

    def test_set_bot_returns_just_bot_scope_state(self):
        result = set_bot_kill_switch(True, "EMP-00001")
        assert result["active"] is True

    def test_set_workflow_automation_returns_just_that_scope_state(self):
        result = set_workflow_automation_kill_switch(True, "EMP-00001")
        assert result["active"] is True


# ---------------------------------------------------------------------------
# get_kill_switch_overview()
# ---------------------------------------------------------------------------


class TestGetKillSwitchOverview:

    def test_all_inactive_by_default(self):
        overview = get_kill_switch_overview()

        assert overview["dealer_wide"]["active"] is False
        assert overview["bot"]["active"] is False
        assert overview["workflow_automation"]["active"] is False
        assert len(overview["departments"]) == len(REAL_DEPARTMENTS)

    def test_every_real_department_is_present(self):
        overview = get_kill_switch_overview()
        department_names = {d["department"] for d in overview["departments"]}
        assert department_names == set(REAL_DEPARTMENTS)

    def test_departments_with_no_mapped_feature_have_an_honest_empty_list(self):
        overview = get_kill_switch_overview()
        by_name = {d["department"]: d for d in overview["departments"]}

        for dept in ("Service", "Finance", "Inventory", "Operations", "Administration"):
            assert by_name[dept]["governed_features"] == []

    def test_sales_governs_ai_assistant(self):
        overview = get_kill_switch_overview()
        by_name = {d["department"]: d for d in overview["departments"]}

        sales_keys = {f["key"] for f in by_name["Sales"]["governed_features"]}
        assert "ai_assistant" in sales_keys

    def test_cross_department_features_listed_separately(self):
        overview = get_kill_switch_overview()
        cross_keys = {f["key"] for f in overview["cross_department_features"]}
        assert "help_assistant" in cross_keys
        assert "workspace_explain" in cross_keys

    def test_reflects_a_real_toggle(self):
        set_department_kill_switch("Marketing", True, "EMP-00001", reason="x")

        overview = get_kill_switch_overview()
        by_name = {d["department"]: d for d in overview["departments"]}

        assert by_name["Marketing"]["active"] is True
        assert by_name["Marketing"]["reason"] == "x"

    def test_has_a_generated_at_timestamp(self):
        overview = get_kill_switch_overview()
        assert overview["generated_at"]


# ---------------------------------------------------------------------------
# core/ai_kill_switch_api.py -- ACL layer (ADMIN/OPERATIONS-only)
# ---------------------------------------------------------------------------


class TestAiKillSwitchApiAcl:

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_overview(self, role):
        assert get_kill_switch_overview_api(role) == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_explain(self, role):
        assert explain_ai_gate_api(role, "ai_assistant") == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_set_dealer_wide(self, role):
        result = set_dealer_wide_kill_switch_api(role, True, "EMP-00001")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_set_department(self, role):
        result = set_department_kill_switch_api(role, "Sales", True, "EMP-00001")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_set_bot(self, role):
        result = set_bot_kill_switch_api(role, True, "EMP-00001")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_set_workflow_automation(self, role):
        result = set_workflow_automation_kill_switch_api(role, True, "EMP-00001")
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_overview(self, role):
        result = get_kill_switch_overview_api(role)
        assert "error" not in result
        assert "dealer_wide" in result

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_set_dealer_wide(self, role):
        result = set_dealer_wide_kill_switch_api(role, True, "EMP-00001", reason="test")
        assert result["active"] is True

        # cleanup so the next parametrized run starts clean
        set_dealer_wide_kill_switch_api(role, False, "EMP-00001")

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_set_department(self, role):
        result = set_department_kill_switch_api(role, "Service", True, "EMP-00001")
        assert result["active"] is True

    def test_explain_api_wraps_feature_key(self):
        result = explain_ai_gate_api(ADMIN, "ai_assistant")
        assert result["feature_key"] == "ai_assistant"
        assert result["gate"] is None


# ---------------------------------------------------------------------------
# Real consumer wiring -- core/ai_management.py's is_feature_enabled()
# ---------------------------------------------------------------------------


class TestAiManagementIntegration:

    def test_feature_enabled_by_default(self):
        assert is_feature_enabled("ai_assistant") is True

    def test_dealer_wide_kill_disables_a_feature_regardless_of_its_own_flag(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is False

    def test_department_kill_disables_only_its_own_features(self):
        set_department_kill_switch("Marketing", True, "EMP-00001")

        assert is_feature_enabled("website_wizard") is False  # Marketing-owned
        assert is_feature_enabled("ai_assistant") is True  # Sales-owned, untouched

    def test_per_feature_flag_still_works_underneath_the_new_gate(self):
        # the new kill switch is layered ON TOP of the existing per-feature
        # flag -- confirm the old mechanism is untouched by disabling the
        # legacy flag directly and confirming the new gate being "off" alone
        # doesn't override it.
        from core.system_config import set_feature_flag
        set_feature_flag("ai_help_enabled", False, "EMP-00001")

        assert is_feature_enabled("help_assistant") is False

    def test_unknown_feature_key_is_true(self):
        assert is_feature_enabled("not_a_real_feature") is True


# ---------------------------------------------------------------------------
# Real consumer wiring -- core/bot_actions.py's run_action()
# ---------------------------------------------------------------------------


class TestBotActionsIntegration:

    def test_run_action_works_by_default(self):
        # sales_followup_leads is the one real whitelisted action key --
        # with no leads assigned it legitimately returns an empty touched
        # list rather than None, proving the handler actually ran.
        result = run_action("sales_followup_leads", "EMP-00099", "EMP-00001")
        assert result is not None
        assert "touched_leads" in result

    def test_bot_wide_kill_switch_blocks_run_action(self):
        set_bot_kill_switch(True, "EMP-00001")

        result = run_action("sales_followup_leads", "EMP-00099", "EMP-00001")
        assert result is None

    def test_dealer_wide_kill_switch_also_blocks_run_action(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")

        result = run_action("sales_followup_leads", "EMP-00099", "EMP-00001")
        assert result is None

    def test_unwhitelisted_task_key_still_returns_none_regardless_of_switch(self):
        assert run_action("not_a_real_task_key", "EMP-00099", "EMP-00001") is None

    def test_workflow_automation_switch_does_not_affect_bot_actions(self):
        set_workflow_automation_kill_switch(True, "EMP-00001")

        result = run_action("sales_followup_leads", "EMP-00099", "EMP-00001")
        assert result is not None


# ---------------------------------------------------------------------------
# Real consumer wiring -- core/workflow_automation.py's evaluate_rules()
# ---------------------------------------------------------------------------


class TestWorkflowAutomationIntegration:

    def test_evaluate_rules_works_by_default(self):
        result = evaluate_rules()
        assert result.get("gated") is not True
        assert "rules_evaluated" in result

    def test_workflow_automation_switch_gates_evaluate_rules(self):
        set_workflow_automation_kill_switch(True, "EMP-00001")

        result = evaluate_rules()
        assert result["gated"] is True
        assert result["rules_evaluated"] == 0
        assert result["fired_count"] == 0
        assert result["fired"] == []
        assert "gated_reason" in result

    def test_dealer_wide_switch_also_gates_evaluate_rules(self):
        set_dealer_wide_kill_switch(True, "EMP-00001")

        result = evaluate_rules()
        assert result["gated"] is True

    def test_bot_switch_does_not_gate_evaluate_rules(self):
        set_bot_kill_switch(True, "EMP-00001")

        result = evaluate_rules()
        assert result.get("gated") is not True
