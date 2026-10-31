"""
Tests for core/workflow_automation.py -- the real "if this real condition, then
this real action" rule engine (Administration Control Center rebuild). Added
per BUILD_QUEUE.md's standing "convert to a real pytest suite as each module
gets touched" rule (CAF-00123 missing_test_coverage work).

Important distinction from the ALREADY-covered tests/test_thin_wrapper_batch_4.py:
that file exclusively mocks core.workflow_automation_api's own functions via
monkeypatch.setattr(), exercising only that thin ACL/wrapper layer's own
role-gating and error-passthrough -- it never calls into this module's real
business logic (the 3 real trigger condition functions, the 2 real action
functions, evaluate_rules()'s own dedup/batching, or get_automation_dashboard()'s
run_now toggle). This file is the first real coverage of core/workflow_automation.py
itself.

No save_graph stubbing -- same precedent tests/test_manager_dashboard.py/
tests/test_lead_aging.py already establish: conftest.py points
DEALEROS_STORAGE_DIR at an isolated tempdir for the whole test session, so
letting create_rule()/set_rule_active()/update_rule()/delete_rule()/
evaluate_rules()'s own unconditional save_graph() calls (and the real
create_task()/send_direct_message() calls the action functions delegate to)
write for real is harmless and fully deterministic.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DEAL, LEAD, VEHICLE, EMPLOYEE, OPERATIONS_TASK, MESSAGE

from core import workflow_automation as wa


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _hours_ago_iso(n):
    return (datetime.now(timezone.utc) - timedelta(hours=n)).isoformat()


def _add_employee(entity_id="EMP-1"):
    ledger.add_entity(Entity(id=entity_id, entity_type=EMPLOYEE, attributes={}))
    return entity_id


def _add_manager_employee(entity_id="EMP-MANAGER-AUTO"):
    """Security-hardening pass (2026-07-20, Task #8): a manager-tier Employee
    (core/bot_tasks.py's infer_tier() resolves "manager" in Title -> TIER_MANAGER),
    used to clear the real Approval Hierarchy step create_rule() now attaches to
    every new AutomationRule. add_entity() overwrites idempotently, so calling
    this repeatedly (or alongside _add_employee(entity_id) for the same id) is
    harmless."""
    ledger.add_entity(Entity(
        id=entity_id, entity_type=EMPLOYEE, attributes={"Title": "Sales Manager"},
    ))
    return entity_id


def _approve_and_activate(rule, approver_id=None):
    """Security-hardening pass (2026-07-20, Task #8): core/workflow_automation.py's
    entire rule engine is now AUTONOMOUS tier -- create_rule() always starts a
    fresh rule inactive with a real, pending core/permissions_registry.py
    ApprovalRequest attached, and set_rule_active(True) refuses to run until that
    request's real status is "approved". This test-only convenience clears that
    real step via a real manager-tier employee, then activates -- so every
    existing test in this file that assumes _make_task_rule()/_make_dm_rule()
    hands back an immediately-active rule keeps working unchanged."""
    from core.permissions_registry import approve_step

    if isinstance(rule, dict) and "error" in rule:
        return rule

    approver_id = approver_id or _add_manager_employee()
    approval = approve_step(rule.attributes["approval_request_id"], approver_id)
    if isinstance(approval, dict) and approval.get("error"):
        return approval

    return wa.set_rule_active(rule.id, True, updated_by=approver_id)


def _add_deal(entity_id, status="financing", updated_at=None):
    ledger.add_entity(Entity(
        id=entity_id,
        entity_type=DEAL,
        attributes={"status": status, "updated_at": updated_at},
    ))
    return entity_id


def _add_lead(entity_id, pipeline_state="NEW", state_since=None, created_at=None):
    attrs = {"PipelineState": pipeline_state}
    if state_since is not None:
        attrs["PipelineStateSince"] = state_since
    if created_at is not None:
        attrs["CreatedAt"] = created_at
    ledger.add_entity(Entity(id=entity_id, entity_type=LEAD, attributes=attrs))
    return entity_id


def _add_vehicle(entity_id, price=50000, date_sold=None):
    ledger.add_entity(Entity(
        id=entity_id,
        entity_type=VEHICLE,
        attributes={"Price": price, "DateSold": date_sold},
    ))
    return entity_id


def _make_task_rule(name="Stalled Deal Alert", trigger_type="deal_stage_stalled",
                     trigger_params=None, priority="high", created_by="EMP-ADMIN"):
    """Security-hardening pass (2026-07-20, Task #8): create_rule() now requires
    created_by to resolve to a real Employee (it's the Approval Request's real
    requester) and always starts the rule inactive/pending -- this helper
    registers created_by, creates the rule, then clears the real approval step
    and activates it, so callers keep getting back an immediately-usable, active
    rule exactly like before this security pass."""
    _add_employee(created_by)
    rule = wa.create_rule(
        name=name,
        trigger_type=trigger_type,
        trigger_params=trigger_params or {"stage": "financing", "threshold_hours": 24},
        action_type="create_operations_task",
        action_params={"priority": priority, "detail_template": "Custom detail"},
        created_by=created_by,
    )
    return _approve_and_activate(rule)


def _make_dm_rule(notify_employee_id, name="DM Alert", trigger_type="deal_stage_stalled",
                   trigger_params=None, created_by="EMP-ADMIN"):
    """See _make_task_rule()'s own docstring -- identical created_by registration
    + approve + activate convenience, for the send_notification_dm action type."""
    _add_employee(created_by)
    rule = wa.create_rule(
        name=name,
        trigger_type=trigger_type,
        trigger_params=trigger_params or {"stage": "financing", "threshold_hours": 24},
        action_type="send_notification_dm",
        action_params={"notify_employee_id": notify_employee_id, "message_template": "Custom message"},
        created_by=created_by,
    )
    return _approve_and_activate(rule)


# --- Catalog constants -------------------------------------------------------

class TestCatalogs:
    def test_trigger_catalog_types_match_trigger_types_list(self):
        assert wa.TRIGGER_TYPES == [t["type"] for t in wa.TRIGGER_CATALOG]
        assert set(wa.TRIGGER_TYPES) == {"deal_stage_stalled", "lead_no_contact", "vehicle_aging_price"}

    def test_action_catalog_types_match_action_types_list(self):
        assert wa.ACTION_TYPES == [a["type"] for a in wa.ACTION_CATALOG]
        assert set(wa.ACTION_TYPES) == {"create_operations_task", "send_notification_dm"}

    def test_every_trigger_catalog_entry_has_a_real_params_list(self):
        for entry in wa.TRIGGER_CATALOG:
            assert "label" in entry
            assert "description" in entry
            assert isinstance(entry["params"], list) and len(entry["params"]) >= 1

    def test_every_action_catalog_entry_has_a_real_params_list(self):
        for entry in wa.ACTION_CATALOG:
            assert "label" in entry
            assert "description" in entry
            assert isinstance(entry["params"], list) and len(entry["params"]) >= 1


# --- create_rule ---------------------------------------------------------------

class TestCreateRule:
    def test_invalid_trigger_type_returns_error(self):
        result = wa.create_rule(
            name="Bad", trigger_type="not_a_real_trigger", trigger_params={},
            action_type="create_operations_task", action_params={}, created_by="EMP-1",
        )
        assert "error" in result

    def test_invalid_action_type_returns_error(self):
        result = wa.create_rule(
            name="Bad", trigger_type="deal_stage_stalled", trigger_params={},
            action_type="not_a_real_action", action_params={}, created_by="EMP-1",
        )
        assert "error" in result

    def test_send_notification_dm_with_no_employee_id_returns_error(self):
        result = wa.create_rule(
            name="Bad DM", trigger_type="deal_stage_stalled", trigger_params={},
            action_type="send_notification_dm", action_params={}, created_by="EMP-1",
        )
        assert "error" in result

    def test_send_notification_dm_with_unknown_employee_id_returns_error(self):
        result = wa.create_rule(
            name="Bad DM", trigger_type="deal_stage_stalled", trigger_params={},
            action_type="send_notification_dm",
            action_params={"notify_employee_id": "EMP-DOES-NOT-EXIST"},
            created_by="EMP-1",
        )
        assert "error" in result

    def test_send_notification_dm_with_a_non_employee_entity_id_returns_error(self):
        # A real entity id that resolves, but to the WRONG entity type -- the
        # module's own validation checks target.entity_type == EMPLOYEE, not
        # just "does this id exist at all."
        _add_deal("DEAL-1")
        result = wa.create_rule(
            name="Bad DM", trigger_type="deal_stage_stalled", trigger_params={},
            action_type="send_notification_dm",
            action_params={"notify_employee_id": "DEAL-1"},
            created_by="EMP-1",
        )
        assert "error" in result

    def test_send_notification_dm_with_a_real_employee_succeeds(self):
        _add_employee("EMP-2")
        rule = _make_dm_rule("EMP-2")
        assert not isinstance(rule, dict) or "error" not in rule
        assert rule.entity_type == "AutomationRule"

    def test_create_operations_task_needs_no_employee_id(self):
        rule = _make_task_rule()
        assert rule.entity_type == "AutomationRule"

    def test_created_rule_has_the_real_default_attributes(self, monkeypatch):
        # create_rule() calls _now_iso() separately for created_at and
        # updated_at -- freeze it so the two are directly comparable rather
        # than asserting equality against two independently-captured
        # microsecond-precision real timestamps.
        monkeypatch.setattr(wa, "_now_iso", lambda: "FIXED-TIME")

        rule = _make_task_rule(name="My Rule", priority="urgent")

        assert rule.attributes["name"] == "My Rule"
        assert rule.attributes["trigger_type"] == "deal_stage_stalled"
        assert rule.attributes["action_type"] == "create_operations_task"
        assert rule.attributes["is_active"] is True
        assert rule.attributes["times_fired"] == 0
        assert rule.attributes["last_run_at"] is None
        assert rule.attributes["created_by"] == "EMP-ADMIN"
        assert rule.attributes["created_at"] == rule.attributes["updated_at"] == "FIXED-TIME"

    def test_created_rule_is_persisted_in_the_ledger(self):
        rule = _make_task_rule()
        assert ledger.get_entity(rule.id) is rule

    def test_missing_description_defaults_to_empty_string(self):
        _add_employee("EMP-1")
        rule = wa.create_rule(
            name="No Desc", trigger_type="vehicle_aging_price", trigger_params={},
            action_type="create_operations_task", action_params={}, created_by="EMP-1",
        )
        assert rule.attributes["description"] == ""


# --- Security-hardening pass (2026-07-20, Task #8): autonomous-tier Approval
# Chain gating ------------------------------------------------------------------
#
# core/workflow_automation.py's entire rule engine is classified "autonomous"
# by core/ai_execution_tier.py -- it decides-and-acts unattended, with no human
# reviewing a given fired action before it happens. Per that classification's
# own requires_approval_chain() contract, a brand-new rule can no longer start
# active: create_rule() now creates a real core/permissions_registry.py
# ApprovalRequest (chain "autonomous_ai_rule_activation") and set_rule_active()
# refuses to flip is_active True until that request's own LIVE status resolves
# to "approved". These tests exercise that gating directly, bypassing the
# _make_task_rule()/_make_dm_rule() convenience helpers (which auto-clear it)
# so the raw, ungated behavior is actually verified somewhere in this suite.

class TestAutonomousApprovalGating:
    def test_create_rule_defaults_to_inactive_and_pending_approval(self):
        _add_employee("EMP-1")
        rule = wa.create_rule(
            name="Gated Rule", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        assert not isinstance(rule, dict) or "error" not in rule
        assert rule.attributes["is_active"] is False
        assert rule.attributes["execution_tier"] == "autonomous"
        assert rule.attributes["approval_status"] == "pending"
        assert rule.attributes["approval_request_id"].startswith("APPR")

    def test_create_rule_with_unknown_created_by_employee_returns_error(self):
        result = wa.create_rule(
            name="No Requester", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-DOES-NOT-EXIST",
        )
        assert isinstance(result, dict) and "error" in result
        # No orphaned AutomationRule should have been persisted when the
        # approval-request creation itself failed.
        assert wa.list_rules() == []

    def test_set_rule_active_true_rejected_before_approval(self):
        _add_employee("EMP-1")
        rule = wa.create_rule(
            name="Not Yet Approved", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        result = wa.set_rule_active(rule.id, True, updated_by="EMP-1")
        assert isinstance(result, dict) and "error" in result
        assert "approved" in result["error"] or "pending" in result["error"]
        assert rule.attributes["is_active"] is False

    def test_set_rule_active_true_succeeds_after_manager_tier_approval(self):
        from core.permissions_registry import approve_step

        _add_employee("EMP-1")
        manager_id = _add_manager_employee()
        rule = wa.create_rule(
            name="Approvable", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        approval = approve_step(rule.attributes["approval_request_id"], manager_id)
        assert not isinstance(approval, dict) or "error" not in approval

        result = wa.set_rule_active(rule.id, True, updated_by=manager_id)
        assert not isinstance(result, dict) or "error" not in result
        assert result.attributes["is_active"] is True
        assert result.attributes["approval_status"] == "approved"

    def test_set_rule_active_true_rejected_when_approval_request_rejected(self):
        from core.permissions_registry import reject_step

        _add_employee("EMP-1")
        manager_id = _add_manager_employee()
        rule = wa.create_rule(
            name="Rejected Rule", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        rejection = reject_step(
            rule.attributes["approval_request_id"], manager_id, reason="Not needed right now",
        )
        assert not isinstance(rejection, dict) or "error" not in rejection

        result = wa.set_rule_active(rule.id, True, updated_by=manager_id)
        assert isinstance(result, dict) and "error" in result
        assert rule.attributes["is_active"] is False

    def test_set_rule_active_false_is_never_gated_even_before_approval(self):
        _add_employee("EMP-1")
        rule = wa.create_rule(
            name="Deactivate Anytime", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        # Already inactive/pending -- deactivating (a no-op direction, never the
        # risky one) must never require approval at all.
        result = wa.set_rule_active(rule.id, False, updated_by="EMP-1")
        assert not isinstance(result, dict) or "error" not in result
        assert result.attributes["is_active"] is False

    def test_set_rule_active_true_with_missing_approval_request_id_returns_error(self):
        _add_employee("EMP-1")
        rule = wa.create_rule(
            name="Corrupted Legacy Rule", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        del rule.attributes["approval_request_id"]

        result = wa.set_rule_active(rule.id, True, updated_by="EMP-1")
        assert isinstance(result, dict) and "error" in result

    def test_reactivating_after_deactivation_still_honors_the_original_approval(self):
        # Approval, once granted, is a real standing permission for this rule to
        # run autonomously -- not a single-use activation token -- so toggling
        # off and back on again should not require a second approval pass.
        from core.permissions_registry import approve_step

        _add_employee("EMP-1")
        manager_id = _add_manager_employee()
        rule = wa.create_rule(
            name="Toggle Twice", trigger_type="deal_stage_stalled",
            trigger_params={"stage": "financing", "threshold_hours": 24},
            action_type="create_operations_task",
            action_params={"priority": "high"},
            created_by="EMP-1",
        )
        approve_step(rule.attributes["approval_request_id"], manager_id)
        wa.set_rule_active(rule.id, True, updated_by=manager_id)

        wa.set_rule_active(rule.id, False, updated_by=manager_id)
        result = wa.set_rule_active(rule.id, True, updated_by=manager_id)
        assert not isinstance(result, dict) or "error" not in result
        assert result.attributes["is_active"] is True

    def test_helper_functions_end_up_with_an_active_rule(self):
        # Meta-test confirming _make_task_rule()/_make_dm_rule()'s own contract,
        # since the overwhelming majority of this file's other tests silently
        # depend on it.
        task_rule = _make_task_rule()
        assert not isinstance(task_rule, dict) or "error" not in task_rule
        assert task_rule.attributes["is_active"] is True
        assert task_rule.attributes["approval_status"] == "approved"

        _add_employee("EMP-2")
        dm_rule = _make_dm_rule("EMP-2")
        assert not isinstance(dm_rule, dict) or "error" not in dm_rule
        assert dm_rule.attributes["is_active"] is True
        assert dm_rule.attributes["approval_status"] == "approved"


# --- list_rules / get_rule ----------------------------------------------------

class TestListAndGetRule:
    def test_list_rules_returns_every_rule_by_default(self):
        _make_task_rule(name="Rule A")
        _make_task_rule(name="Rule B")

        rules = wa.list_rules()
        assert len(rules) == 2

    def test_list_rules_active_only_excludes_deactivated_rules(self):
        r1 = _make_task_rule(name="Active Rule")
        r2 = _make_task_rule(name="Inactive Rule")
        wa.set_rule_active(r2.id, False, updated_by="EMP-1")

        active = wa.list_rules(active_only=True)
        assert [r.id for r in active] == [r1.id]

    def test_list_rules_sorted_newest_first(self, monkeypatch):
        # create_rule() calls _now_iso() twice per rule (created_at, then
        # updated_at) -- a strictly-increasing counter-backed timestamp
        # covers that without having to pre-count exactly how many calls
        # each helper makes.
        counter = iter(range(1, 100))
        monkeypatch.setattr(wa, "_now_iso", lambda: f"2020-01-01T00:00:{next(counter):02d}+00:00")

        r1 = _make_task_rule(name="Oldest")
        r2 = _make_task_rule(name="Middle")
        r3 = _make_task_rule(name="Newest")

        rules = wa.list_rules()
        assert [r.id for r in rules] == [r3.id, r2.id, r1.id]

    def test_get_rule_returns_the_real_rule(self):
        rule = _make_task_rule()
        fetched = wa.get_rule(rule.id)
        assert fetched is rule

    def test_get_rule_returns_none_for_unknown_id(self):
        assert wa.get_rule("AUTOR-DOES-NOT-EXIST") is None

    def test_get_rule_returns_none_for_an_id_of_the_wrong_entity_type(self):
        _add_deal("DEAL-1")
        assert wa.get_rule("DEAL-1") is None


# --- set_rule_active -----------------------------------------------------------

class TestSetRuleActive:
    def test_deactivating_an_active_rule(self):
        rule = _make_task_rule()
        result = wa.set_rule_active(rule.id, False, updated_by="EMP-1")
        assert result.attributes["is_active"] is False

    def test_reactivating_a_deactivated_rule(self):
        rule = _make_task_rule()
        wa.set_rule_active(rule.id, False, updated_by="EMP-1")
        result = wa.set_rule_active(rule.id, True, updated_by="EMP-1")
        assert result.attributes["is_active"] is True

    def test_unknown_rule_id_returns_error(self):
        result = wa.set_rule_active("AUTOR-BOGUS", False, updated_by="EMP-1")
        assert "error" in result

    def test_updated_at_changes_on_toggle(self, monkeypatch):
        # _make_task_rule() itself now makes several real _now_iso() calls of
        # its own (create_rule()'s created_at/updated_at, plus the helper's own
        # approve-and-activate set_rule_active() call) -- build and activate the
        # rule first, with the REAL clock, then freeze the clock only for the
        # explicit toggle under test.
        rule = _make_task_rule()
        original_updated_at = rule.attributes["updated_at"]

        monkeypatch.setattr(wa, "_now_iso", lambda: "T1")

        wa.set_rule_active(rule.id, False, updated_by="EMP-1")
        assert rule.attributes["updated_at"] == "T1"
        assert rule.attributes["updated_at"] != original_updated_at


# --- update_rule -----------------------------------------------------------------

class TestUpdateRule:
    def test_unknown_rule_id_returns_error(self):
        result = wa.update_rule("AUTOR-BOGUS", updated_by="EMP-1", name="New Name")
        assert "error" in result

    def test_partial_update_only_changes_the_given_fields(self):
        rule = _make_task_rule(name="Original Name")
        original_trigger_params = dict(rule.attributes["trigger_params"])

        wa.update_rule(rule.id, updated_by="EMP-1", name="New Name")

        assert rule.attributes["name"] == "New Name"
        assert rule.attributes["trigger_params"] == original_trigger_params

    def test_update_description(self):
        rule = _make_task_rule()
        wa.update_rule(rule.id, updated_by="EMP-1", description="Updated description")
        assert rule.attributes["description"] == "Updated description"

    def test_update_trigger_params(self):
        rule = _make_task_rule()
        wa.update_rule(rule.id, updated_by="EMP-1", trigger_params={"stage": "contract", "threshold_hours": 96})
        assert rule.attributes["trigger_params"] == {"stage": "contract", "threshold_hours": 96}

    def test_update_action_params_on_a_create_operations_task_rule_needs_no_employee_check(self):
        rule = _make_task_rule()
        wa.update_rule(rule.id, updated_by="EMP-1", action_params={"priority": "low", "detail_template": ""})
        assert rule.attributes["action_params"]["priority"] == "low"

    def test_update_action_params_on_a_dm_rule_with_invalid_employee_returns_error(self):
        _add_employee("EMP-2")
        rule = _make_dm_rule("EMP-2")

        result = wa.update_rule(rule.id, updated_by="EMP-1", action_params={"notify_employee_id": "EMP-BOGUS"})
        assert "error" in result
        # The rule's own real action_params are left unchanged by the rejected update.
        assert rule.attributes["action_params"]["notify_employee_id"] == "EMP-2"

    def test_update_action_params_on_a_dm_rule_with_a_valid_employee_succeeds(self):
        _add_employee("EMP-2")
        _add_employee("EMP-3")
        rule = _make_dm_rule("EMP-2")

        result = wa.update_rule(rule.id, updated_by="EMP-1", action_params={"notify_employee_id": "EMP-3"})
        assert result.attributes["action_params"]["notify_employee_id"] == "EMP-3"

    def test_updated_at_bumped_on_a_real_change(self, monkeypatch):
        # Same reasoning as TestSetRuleActive's own test_updated_at_changes_on_
        # toggle -- build the rule first with the real clock, then freeze it
        # only for the explicit update() call under test.
        rule = _make_task_rule()
        original_updated_at = rule.attributes["updated_at"]

        monkeypatch.setattr(wa, "_now_iso", lambda: "T1")

        wa.update_rule(rule.id, updated_by="EMP-1", name="Renamed")
        assert rule.attributes["updated_at"] == "T1"
        assert rule.attributes["updated_at"] != original_updated_at


# --- delete_rule -----------------------------------------------------------------

class TestDeleteRule:
    def test_delete_removes_the_rule_from_the_ledger(self):
        rule = _make_task_rule()
        result = wa.delete_rule(rule.id)

        assert result == {"deleted": rule.id}
        assert ledger.get_entity(rule.id) is None

    def test_delete_unknown_rule_returns_error(self):
        result = wa.delete_rule("AUTOR-BOGUS")
        assert "error" in result


# --- Trigger condition functions ------------------------------------------------

class TestFindDealStageStalled:
    def test_deal_in_matching_stage_past_threshold_matches(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(50))
        matches = wa._find_deal_stage_stalled({"stage": "financing", "threshold_hours": 24})
        assert [d.id for d, _ in matches] == ["DEAL-1"]

    def test_deal_in_matching_stage_below_threshold_does_not_match(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(2))
        matches = wa._find_deal_stage_stalled({"stage": "financing", "threshold_hours": 24})
        assert matches == []

    def test_deal_in_a_different_stage_is_excluded_regardless_of_age(self):
        _add_deal("DEAL-1", status="contract", updated_at=_hours_ago_iso(500))
        matches = wa._find_deal_stage_stalled({"stage": "financing", "threshold_hours": 24})
        assert matches == []

    def test_deal_with_no_updated_at_never_matches(self):
        _add_deal("DEAL-1", status="financing", updated_at=None)
        matches = wa._find_deal_stage_stalled({"stage": "financing", "threshold_hours": 24})
        assert matches == []

    def test_default_stage_and_threshold_apply_when_params_omitted(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(49))
        matches = wa._find_deal_stage_stalled({})
        assert [d.id for d, _ in matches] == ["DEAL-1"]

    def test_detail_message_names_the_real_deal_and_hours(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(50))
        matches = wa._find_deal_stage_stalled({"stage": "financing", "threshold_hours": 24})
        _, detail = matches[0]
        assert "DEAL-1" in detail
        assert "financing" in detail


class TestFindLeadNoContact:
    def test_open_lead_with_no_notes_and_old_pipeline_since_matches(self):
        _add_lead("LEAD-1", pipeline_state="CONTACTED", state_since=_hours_ago_iso(100))
        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert [l.id for l, _ in matches] == ["LEAD-1"]

    def test_open_lead_below_threshold_does_not_match(self):
        _add_lead("LEAD-1", pipeline_state="CONTACTED", state_since=_hours_ago_iso(5))
        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert matches == []

    def test_sold_lead_is_excluded_regardless_of_age(self):
        _add_lead("LEAD-1", pipeline_state="SOLD", state_since=_hours_ago_iso(1000))
        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert matches == []

    def test_lost_lead_is_excluded_regardless_of_age(self):
        _add_lead("LEAD-1", pipeline_state="LOST", state_since=_hours_ago_iso(1000))
        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert matches == []

    def test_falls_back_to_created_at_when_no_pipeline_state_since(self):
        _add_lead("LEAD-1", pipeline_state="NEW", created_at=_hours_ago_iso(200))
        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert [l.id for l, _ in matches] == ["LEAD-1"]

    def test_a_real_recent_field_note_prevents_the_lead_from_matching(self):
        from core.field_notes import create_field_note

        _add_lead("LEAD-1", pipeline_state="CONTACTED", state_since=_hours_ago_iso(500))
        create_field_note(
            department="Sales", category="call", body="Called the customer",
            created_by="EMP-1", linked_entity_id="LEAD-1",
        )

        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert matches == []

    def test_a_real_stale_field_note_still_lets_the_lead_match(self):
        from core.field_notes import create_field_note

        _add_lead("LEAD-1", pipeline_state="CONTACTED", state_since=_hours_ago_iso(500))
        note = create_field_note(
            department="Sales", category="call", body="Old call",
            created_by="EMP-1", linked_entity_id="LEAD-1",
        )
        # Backdate the note itself so it's older than the threshold too.
        note.attributes["created_at"] = _hours_ago_iso(200)

        matches = wa._find_lead_no_contact({"threshold_hours": 72})
        assert [l.id for l, _ in matches] == ["LEAD-1"]


class TestFindVehicleAgingPrice:
    def test_unsold_vehicle_at_or_above_threshold_matches(self):
        _add_vehicle("VEH-1", price=45000, date_sold=None)
        matches = wa._find_vehicle_aging_price({"min_price": 40000})
        assert [v.id for v, _ in matches] == ["VEH-1"]

    def test_unsold_vehicle_exactly_at_threshold_matches(self):
        _add_vehicle("VEH-1", price=40000, date_sold=None)
        matches = wa._find_vehicle_aging_price({"min_price": 40000})
        assert [v.id for v, _ in matches] == ["VEH-1"]

    def test_unsold_vehicle_below_threshold_does_not_match(self):
        _add_vehicle("VEH-1", price=10000, date_sold=None)
        matches = wa._find_vehicle_aging_price({"min_price": 40000})
        assert matches == []

    def test_sold_vehicle_is_excluded_regardless_of_price(self):
        _add_vehicle("VEH-1", price=90000, date_sold="2026-01-01")
        matches = wa._find_vehicle_aging_price({"min_price": 40000})
        assert matches == []

    def test_default_threshold_applies_when_params_omitted(self):
        _add_vehicle("VEH-1", price=41000, date_sold=None)
        matches = wa._find_vehicle_aging_price({})
        assert [v.id for v, _ in matches] == ["VEH-1"]


# --- evaluate_rules (the meat) --------------------------------------------------

class TestEvaluateRules:
    def test_no_active_rules_returns_zeroed_summary(self):
        result = wa.evaluate_rules()
        assert result["rules_evaluated"] == 0
        assert result["fired_count"] == 0
        assert result["fired"] == []
        assert result["errors"] == []
        assert "evaluated_at" in result

    def test_matching_condition_fires_and_creates_a_real_operations_task(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        result = wa.evaluate_rules()

        assert result["rules_evaluated"] == 1
        assert result["fired_count"] == 1
        assert result["errors"] == []

        fired = result["fired"][0]
        assert fired["rule_id"] == rule.id
        assert fired["entity_id"] == "DEAL-1"
        task_id = fired["action_result"]["created_task_id"]

        task = ledger.get_entity(task_id)
        assert task.entity_type == OPERATIONS_TASK
        assert task.attributes["linked_entity_id"] == "DEAL-1"
        assert task.attributes["source_entity_id"] == "DEAL-1"
        assert task.attributes["priority"] == "high"
        assert "Custom detail" in task.attributes["detail"]
        assert rule.attributes["name"] in task.attributes["detail"]

    def test_non_matching_condition_does_not_fire(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(1))
        _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        result = wa.evaluate_rules()
        assert result["fired_count"] == 0

    def test_inactive_rule_is_never_evaluated(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})
        wa.set_rule_active(rule.id, False, updated_by="EMP-1")

        result = wa.evaluate_rules()
        assert result["rules_evaluated"] == 0
        assert result["fired_count"] == 0

    def test_send_notification_dm_action_fires_a_real_direct_message(self):
        _add_employee("EMP-2")
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_dm_rule("EMP-2", trigger_params={"stage": "financing", "threshold_hours": 24})

        result = wa.evaluate_rules()

        assert result["fired_count"] == 1
        message_id = result["fired"][0]["action_result"]["sent_message_id"]

        message = ledger.get_entity(message_id)
        assert message.entity_type == MESSAGE
        assert message.attributes["recipient_id"] == "EMP-2"
        assert message.attributes["sender_id"] == wa.AUTOMATION_ACTOR_ID
        assert "Custom message" in message.attributes["content"]
        assert rule.attributes["name"] in message.attributes["content"]

    def test_a_rule_only_fires_once_per_entity_dedup(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        first = wa.evaluate_rules()
        assert first["fired_count"] == 1

        second = wa.evaluate_rules()
        assert second["fired_count"] == 0
        assert second["rules_evaluated"] == 1  # the rule itself is still evaluated

    def test_dedup_is_per_entity_a_new_matching_entity_still_fires(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})
        wa.evaluate_rules()

        _add_deal("DEAL-2", status="financing", updated_at=_hours_ago_iso(100))
        second = wa.evaluate_rules()

        assert second["fired_count"] == 1
        assert second["fired"][0]["entity_id"] == "DEAL-2"

    def test_times_fired_and_last_run_at_update_on_a_real_fire(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        assert rule.attributes["times_fired"] == 0
        assert rule.attributes["last_run_at"] is None

        wa.evaluate_rules()

        assert rule.attributes["times_fired"] == 1
        assert rule.attributes["last_run_at"] is not None

    def test_last_run_at_updates_even_when_nothing_matches(self):
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})
        assert rule.attributes["last_run_at"] is None

        wa.evaluate_rules()

        assert rule.attributes["last_run_at"] is not None
        assert rule.attributes["times_fired"] == 0

    def test_evaluate_rules_with_a_specific_rule_id_only_evaluates_that_rule(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _add_deal("DEAL-2", status="financing", updated_at=_hours_ago_iso(100))

        rule_a = _make_task_rule(name="Rule A", trigger_params={"stage": "financing", "threshold_hours": 24})
        rule_b = _make_task_rule(name="Rule B", trigger_params={"stage": "financing", "threshold_hours": 24})

        result = wa.evaluate_rules(rule_id=rule_a.id)

        assert result["rules_evaluated"] == 1
        assert rule_a.attributes["times_fired"] > 0
        assert rule_b.attributes["times_fired"] == 0

    def test_evaluate_rules_with_an_inactive_rule_id_evaluates_nothing(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})
        wa.set_rule_active(rule.id, False, updated_by="EMP-1")

        result = wa.evaluate_rules(rule_id=rule.id)
        assert result["rules_evaluated"] == 0

    def test_unknown_trigger_or_action_type_on_a_rule_is_reported_as_an_error(self):
        # Simulates a rule whose attributes were corrupted/edited outside the
        # normal create_rule()/update_rule() validation path -- evaluate_rules()
        # should degrade gracefully (an error entry, no crash) rather than raise.
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})
        rule.attributes["trigger_type"] = "not_a_real_trigger_type"

        result = wa.evaluate_rules()

        assert result["fired_count"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["rule_id"] == rule.id
        assert "Unknown trigger/action type" in result["errors"][0]["error"]
        # A rule that hit the unknown-type branch is `continue`d past entirely --
        # it never reaches the last_run_at stamp at the bottom of the loop.
        assert rule.attributes["last_run_at"] is None

    def test_a_real_action_error_lands_in_errors_and_is_retried_not_deduped(self):
        # send_notification_dm's own action function returns a real error dict
        # when notify_employee_id is empty -- create_rule()/update_rule() both
        # block this from happening through the normal API, so this simulates
        # the edge case via a direct attribute mutation (the same technique the
        # unknown-trigger-type test above uses) to exercise the action
        # function's own error branch.
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _add_employee("EMP-2")
        rule = _make_dm_rule("EMP-2", trigger_params={"stage": "financing", "threshold_hours": 24})
        rule.attributes["action_params"] = {}

        result = wa.evaluate_rules()

        assert result["fired_count"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["entity_id"] == "DEAL-1"

        # A FAILED action must NOT be recorded as a fired/dedup execution — otherwise the rule is
        # permanently suppressed for this entity even after the failure cause clears.
        assert rule.attributes["times_fired"] == 0
        assert wa.list_executions(rule_id=rule.id) == []

        # So a fresh pass re-evaluates the same entity and errors again (retry), rather than being
        # silently deduped away.
        second = wa.evaluate_rules()
        assert second["fired_count"] == 0
        assert len(second["errors"]) == 1
        assert second["errors"][0]["entity_id"] == "DEAL-1"

        # And once the cause is fixed, it fires cleanly (no stale dedup blocking it).
        rule.attributes["action_params"] = {"notify_employee_id": "EMP-2"}
        third = wa.evaluate_rules()
        assert third["fired_count"] == 1
        assert len(wa.list_executions(rule_id=rule.id)) == 1


# --- Execution log -----------------------------------------------------------------

class TestListExecutions:
    def test_no_executions_returns_empty_list(self):
        assert wa.list_executions() == []

    def test_filters_by_rule_id(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _add_deal("DEAL-2", status="financing", updated_at=_hours_ago_iso(100))
        rule_a = _make_task_rule(name="Rule A", trigger_params={"stage": "financing", "threshold_hours": 24})
        rule_b = _make_task_rule(name="Rule B", trigger_params={"stage": "financing", "threshold_hours": 24})

        wa.evaluate_rules(rule_id=rule_a.id)
        wa.evaluate_rules(rule_id=rule_b.id)

        executions_a = wa.list_executions(rule_id=rule_a.id)
        assert len(executions_a) == 2
        assert all(e.attributes["rule_id"] == rule_a.id for e in executions_a)

    def test_limit_caps_the_result(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _add_deal("DEAL-2", status="financing", updated_at=_hours_ago_iso(100))
        _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        wa.evaluate_rules()

        assert len(wa.list_executions(limit=1)) == 1

    def test_sorted_newest_first(self, monkeypatch):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        _add_deal("DEAL-2", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        real_now_iso = wa._now_iso
        timestamps = iter(["2020-01-01T00:00:00+00:00"] * 3 + ["2022-01-01T00:00:00+00:00"] * 3)
        monkeypatch.setattr(wa, "_now_iso", lambda: next(timestamps, real_now_iso()))

        wa.evaluate_rules()

        _add_deal("DEAL-3", status="financing", updated_at=_hours_ago_iso(100))
        wa.evaluate_rules()

        executions = wa.list_executions(rule_id=rule.id)
        fired_ats = [e.attributes["fired_at"] for e in executions]
        assert fired_ats == sorted(fired_ats, reverse=True)


# --- get_automation_dashboard ---------------------------------------------------

class TestGetAutomationDashboard:
    def test_default_run_now_true_actually_evaluates(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        dashboard = wa.get_automation_dashboard()

        assert dashboard["last_evaluation"]["fired_count"] == 1
        assert rule.attributes["times_fired"] == 1
        assert len(dashboard["recent_executions"]) == 1

    def test_run_now_false_does_not_evaluate_at_all(self):
        _add_deal("DEAL-1", status="financing", updated_at=_hours_ago_iso(100))
        rule = _make_task_rule(trigger_params={"stage": "financing", "threshold_hours": 24})

        dashboard = wa.get_automation_dashboard(run_now=False)

        assert dashboard["last_evaluation"] == {"rules_evaluated": 0, "fired_count": 0, "fired": [], "errors": []}
        assert rule.attributes["times_fired"] == 0
        assert wa.list_executions() == []

    def test_dashboard_shape_includes_catalogs_and_rule_counts(self):
        _make_task_rule(name="Active One")
        inactive = _make_task_rule(name="Inactive One")
        wa.set_rule_active(inactive.id, False, updated_by="EMP-1")

        dashboard = wa.get_automation_dashboard(run_now=False)

        assert len(dashboard["rules"]) == 2
        assert dashboard["active_rule_count"] == 1
        assert dashboard["trigger_catalog"] == wa.TRIGGER_CATALOG
        assert dashboard["action_catalog"] == wa.ACTION_CATALOG

    def test_no_rules_at_all_returns_an_empty_but_well_shaped_dashboard(self):
        dashboard = wa.get_automation_dashboard()

        assert dashboard["rules"] == []
        assert dashboard["active_rule_count"] == 0
        assert dashboard["last_evaluation"]["rules_evaluated"] == 0
        assert dashboard["recent_executions"] == []
