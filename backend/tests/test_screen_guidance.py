"""
Tests for core/screen_guidance.py -- "Help Me With This Screen," a pure
composition/read layer over core/enterprise_risk_center.py's real exception
engine and core/readiness_recommendations.py's real 12-rule recommendation
engine (plus three special-cased department branches -- readiness/
administration/network -- that reuse other already-real engines directly),
turning both into the same {key, title, description, prompt, priority}
contract core/bot_tasks.py's generate_tasks() already established. Also
covers the module's two real one-click actions -- create_automation_rule_
from_guidance() ("Automate It", a live core/workflow_automation.py
AutomationRule) and create_document_requests_from_guidance() ("Do It", a
real bulk core/document_workflows.py request_document() call) -- and the
small pure helpers (_priority_for/_prompt_for/_do_it_for/_automation_for).

Added per BUILD_QUEUE.md's standing "convert to a real pytest suite as each
module gets touched" rule (CAF-00123 missing_test_coverage work).

Testing strategy, matching this module's own layered design:
- Small pure helpers (_priority_for/_prompt_for/_do_it_for) are tested
  directly, no mocking needed.
- _automation_for/create_automation_rule_from_guidance are tested against
  REAL core/workflow_automation.py ledger state (the real
  create_automation_rule_from_guidance action itself is used to create a
  real active rule, then _automation_for is re-checked to confirm the
  tier-3 "already automated" detection fires for real) -- no hand-guessed
  create_rule() param shapes are used anywhere in this file.
- _already_requested/create_document_requests_from_guidance are tested
  against REAL core/document_workflows.py + core/operations_tasks.py state
  (real Vehicle/Deal entities, real request_document() calls to seed
  existing open tasks), with only the upstream get_risk_center_overview()
  call faked via monkeypatch.setattr(sg, "get_risk_center_overview", fake)
  -- that name is imported by plain `from X import Y` at module load time,
  so it's directly patchable on the sg module object.
- _readiness_guidance/_administration_guidance/_network_guidance and the
  main get_screen_guidance() dispatcher are tested by monkeypatching their
  composed source functions (all bound the same directly-patchable
  from-import way) rather than building out real enterprise_risk_center/
  readiness_recommendations/governance/network_playbooks scenarios --
  those engines already have their own dedicated, real-data test suites.
- get_screen_guidance()'s own real, DEFERRED (in-function) import of
  core/coaching.py's apply_intensity_to_tasks is NOT directly patchable via
  monkeypatch.setattr(sg, "apply_intensity_to_tasks", fake) -- a deferred
  `from X import Y` inside a function body creates a fresh local name each
  call, never touching sg's own module globals. Most tests below rely
  instead on that function's real, confirmed Productive-tier passthrough
  behavior (employee_id=None + no overrides -> intensity defaults to
  "productive"/"default", a pure no-op over the guidance list) -- and one
  dedicated test patches the true source, core.coaching.apply_intensity_to_
  tasks, via the string-target form to explicitly prove the wiring works.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DEAL, EMPLOYEE

import core.screen_guidance as sg
from core.screen_guidance import (
    _automation_for,
    _do_it_for,
    _already_requested,
    _priority_for,
    _prompt_for,
    create_automation_rule_from_guidance,
    create_document_requests_from_guidance,
    get_screen_guidance,
    _NOT_YET_SCOPED_NOTE,
)
from core.workflow_automation import list_rules, set_rule_active
from core.permissions_registry import approve_step
from core.document_workflows import request_document


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def grant_bot_capabilities(fresh_ledger):
    """Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    Layer"): create_automation_rule_from_guidance()/create_document_requests_
    from_guidance() are now gated by core/bot_permissions.py's own separate,
    additive, default-deny capability check, checked BEFORE either function's
    own real logic runs. This module's own tests here predate that gate and
    are about the automation-rule/document-request CREATION logic itself
    (this file's whole stated testing strategy), not about the permission
    layer (which gets its own dedicated test_bot_permissions.py) -- granting
    both real capabilities dealer-wide before every test, against the same
    fresh, isolated ledger fresh_ledger() just reset, keeps these tests
    scoped to what they were actually designed to test rather than silently
    failing on an unrelated, newer gate.

    Also registers "EMP-1" as a real, manager-tier Employee. Security-
    hardening Task #8 ("AI execution-tier framework") made
    core/workflow_automation.py's create_rule() require its `created_by`
    argument to resolve to a real Employee (it now opens a real
    core/permissions_registry.py ApprovalRequest on every rule creation) --
    every test in this file that calls create_automation_rule_from_guidance
    passes "EMP-1" as the acting employee_id, so without this, every one of
    those calls would fail with an "Employee not found" style error before
    ever reaching the logic this file is actually testing. Manager-tier
    (not just any real Employee) so the same "EMP-1" id can also self-
    approve the resulting request directly in tests that need a genuinely
    ACTIVE rule (e.g. tier-3 "already automated" detection, which only
    counts active rules) -- core/permissions_registry.py's approve_step()
    has no self-approval restriction, confirmed by reading its source."""

    from core.bot_permissions import grant_capability
    grant_capability(
        "bot.action.automate_screen_guidance", "dealer_wide", True, "EMP-TEST-SETUP"
    )
    grant_capability(
        "bot.action.do_it_screen_guidance", "dealer_wide", True, "EMP-TEST-SETUP"
    )
    _employee("EMP-1")
    yield


def _employee(entity_id="EMP-1", title="Sales Manager"):
    ledger.add_entity(Entity(
        id=entity_id, entity_type=EMPLOYEE,
        attributes={"Title": title, "Department": "Sales"},
    ))
    return entity_id


def _approve_and_activate(rule_id, approver_id="EMP-1"):
    """Fetches the real ApprovalRequest a create_rule() call opened for
    `rule_id`, approves it (manager-tier, matching the real
    "autonomous_ai_rule_activation" chain's single-step requirement), and
    activates the rule -- the real, full path a rule must take to become
    genuinely ACTIVE under Task #8's gating, mirroring
    test_workflow_automation.py's own _approve_and_activate helper."""

    rule = next(r for r in list_rules() if r.id == rule_id)
    approve_step(rule.attributes["approval_request_id"], approver_id, "test approval")
    set_rule_active(rule_id, True, updated_by=approver_id)
    return next(r for r in list_rules() if r.id == rule_id)


def _vehicle(entity_id="VEH-1"):
    ledger.add_entity(Entity(id=entity_id, entity_type=VEHICLE, attributes={"VIN": entity_id}))
    return entity_id


def _deal(entity_id="DEAL-1"):
    ledger.add_entity(Entity(id=entity_id, entity_type=DEAL, attributes={}))
    return entity_id


def _risk_item(key, title="Some Exception", severity="high", count=3, items=None,
                resolve=None, basis="real", note="A real note."):
    return {
        "key": key,
        "title": title,
        "severity": severity,
        "count": count,
        "items": items or [],
        "resolve": resolve or {"department": "Finance", "item_key": "deals", "hint": "Go look."},
        "basis": basis,
        "note": note,
    }


def _fake_risk_overview(items):
    return {"categories": {"critical_issues": items}}


def _rec_item(key, title="Some Rec", severity="high", triggered=True,
              finding="A real finding.", recommendation="A real recommendation.",
              resolve=None, basis="real"):
    return {
        "key": key,
        "title": title,
        "severity": severity,
        "triggered": triggered,
        "finding": finding,
        "recommendation": recommendation,
        "resolve": resolve or {"department": "Sales", "item_key": "overview", "hint": "Look here."},
        "basis": basis,
    }


def _fake_rec_overview(items, executive=None):
    return {
        "categories": {"sales": items},
        "executive_recommendations": executive or [],
    }


class TestPriorityFor:
    def test_known_severities_map_to_expected_priority(self):
        assert _priority_for("critical") == 4
        assert _priority_for("high") == 3
        assert _priority_for("medium") == 2
        assert _priority_for("low") == 1

    def test_unknown_or_none_severity_defaults_to_priority_1(self):
        assert _priority_for(None) == 1
        assert _priority_for("not_a_real_severity") == 1


class TestPromptFor:
    def test_known_key_uses_its_specific_template(self):
        item = {"key": "vehicles_missing_titles", "count": 5, "title": "Vehicles Missing Titles"}
        assert _prompt_for(item) == "Show me the 5 vehicle(s) missing a Title so I can request them."

    def test_unknown_key_uses_default_template_with_title(self):
        item = {"key": "not_a_real_key", "count": 3, "title": "Some Custom Thing"}
        assert _prompt_for(item) == "Help me with the 3 'Some Custom Thing' item(s)."

    def test_none_count_formats_as_zero(self):
        item = {"key": "not_a_real_key", "count": None, "title": "T"}
        assert _prompt_for(item) == "Help me with the 0 'T' item(s)."


class TestDoItFor:
    def test_mapped_keys_return_true(self):
        assert _do_it_for("vehicles_missing_titles") is True
        assert _do_it_for("contracts_missing_documents") is True

    def test_unmapped_key_returns_false(self):
        assert _do_it_for("recon_delays") is False
        assert _do_it_for("anything_else") is False


class TestAutomationFor:
    def test_unmapped_key_returns_tier_0(self):
        result = _automation_for("recon_delays")
        assert result["tier"] == 0
        assert result["label"] == "No Automation Path Yet"

    def test_funding_delays_maps_to_deal_stage_stalled_tier_1_with_no_active_rule(self):
        result = _automation_for("funding_delays")
        assert result["tier"] == 1
        assert result["label"] == "Automatable Today"

    def test_finance_funding_delays_maps_to_the_same_trigger_type(self):
        assert _automation_for("finance_funding_delays")["tier"] == 1

    def test_inventory_aging_action_maps_to_vehicle_aging_price_tier_1(self):
        assert _automation_for("inventory_aging_action")["tier"] == 1

    def test_real_active_rule_flips_tier_to_3_for_every_key_mapped_to_it(self):
        result = create_automation_rule_from_guidance("ADMIN", "EMP-1", "funding_delays", "Some Title")
        assert "error" not in result
        # tier-3 "already automated" detection only counts genuinely ACTIVE
        # rules (core/network_playbooks.py's _automation_score() calls
        # list_rules(active_only=True)) -- a freshly created rule starts
        # inactive/pending under Task #8's approval-chain gating, so it must
        # be explicitly approved + activated first for this check to fire.
        _approve_and_activate(result["id"])

        assert _automation_for("funding_delays")["tier"] == 3
        # finance_funding_delays maps to the same real trigger_type
        # (deal_stage_stalled) -- the same live rule covers it too.
        assert _automation_for("finance_funding_delays")["tier"] == 3
        # a different trigger type is unaffected by this unrelated rule.
        assert _automation_for("inventory_aging_action")["tier"] == 1


class TestCreateAutomationRuleFromGuidance:
    def test_unmapped_item_key_returns_an_error_and_creates_nothing(self):
        result = create_automation_rule_from_guidance("ADMIN", "EMP-1", "recon_delays", "Title")
        assert "error" in result
        assert "nothing real to automate" in result["error"]
        assert list_rules() == []

    def test_successful_creation_produces_a_real_active_rule_with_correct_fields(self):
        result = create_automation_rule_from_guidance(
            "ADMIN", "EMP-1", "funding_delays", "Funding Delays Rising"
        )
        assert "error" not in result

        matches = [r for r in list_rules() if r.attributes.get("name") == "Auto: Funding Delays Rising"]
        assert len(matches) == 1
        rule = matches[0]
        assert rule.attributes["trigger_type"] == "deal_stage_stalled"
        assert rule.attributes["action_type"] == "create_operations_task"
        assert rule.attributes["action_params"] == {
            "priority": "high", "detail_template": "Guidance: Funding Delays Rising"
        }
        assert rule.attributes["description"] == (
            "Created from a 'Help Me With This Screen' recommendation: Funding Delays Rising"
        )

    def test_inventory_aging_action_creates_a_rule_with_the_correct_trigger_type(self):
        create_automation_rule_from_guidance("ADMIN", "EMP-1", "inventory_aging_action", "Aging Units")

        matches = [r for r in list_rules() if r.attributes.get("name") == "Auto: Aging Units"]
        assert len(matches) == 1
        assert matches[0].attributes["trigger_type"] == "vehicle_aging_price"

    def test_already_automated_tier_3_item_is_rejected_and_creates_no_duplicate(self):
        first = create_automation_rule_from_guidance("ADMIN", "EMP-1", "funding_delays", "First Rule")
        assert "error" not in first
        # same reasoning as test_real_active_rule_flips_tier_to_3... above --
        # the duplicate-block only fires once the first rule is genuinely
        # active, not merely created/pending approval.
        _approve_and_activate(first["id"])
        before_count = len(list_rules())

        result = create_automation_rule_from_guidance(
            "ADMIN", "EMP-1", "finance_funding_delays", "Second Attempt"
        )

        assert "error" in result
        assert "already covers this" in result["error"]
        assert len(list_rules()) == before_count

    def test_wrong_role_is_rejected_by_the_underlying_create_rule_api_gate(self):
        result = create_automation_rule_from_guidance("SALES", "EMP-1", "funding_delays", "Title")
        assert result == {"error": "Admin/Operations role required."}
        assert list_rules() == []


class TestAlreadyRequested:
    def test_no_matching_task_returns_false(self):
        assert _already_requested("title_processing", "VEH-999") is False

    def test_real_open_task_is_detected(self):
        vid = _vehicle("VEH-1")
        request_document(VEHICLE, vid, "Title", "EMP-1")
        assert _already_requested("title_processing", vid) is True

    def test_different_entity_id_is_not_a_match(self):
        vid = _vehicle("VEH-1")
        request_document(VEHICLE, vid, "Title", "EMP-1")
        assert _already_requested("title_processing", "VEH-OTHER") is False

    def test_different_task_type_is_not_a_match(self):
        vid = _vehicle("VEH-1")
        request_document(VEHICLE, vid, "Title", "EMP-1")
        assert _already_requested("document_request", vid) is False

    def test_closed_task_is_not_counted_as_still_open(self):
        vid = _vehicle("VEH-1")
        request_document(VEHICLE, vid, "Title", "EMP-1")

        from core.operations_tasks import list_tasks as _all_tasks
        matches = [t for t in _all_tasks() if t.attributes.get("linked_entity_id") == vid]
        assert len(matches) == 1
        task_id = matches[0].id

        # list_tasks()'s own _enrich() returns a fresh Entity copy (a
        # read-time-enrichment pattern, same as core/vehicle_holds.py's
        # expires_at) -- mutating that returned object never touches the
        # real stored entity, so the status flip has to go through the
        # ledger's own real stored object instead.
        real_entity = ledger.get_entity(task_id)
        real_entity.attributes["status"] = "closed"

        assert _already_requested("title_processing", vid) is False


class TestCreateDocumentRequestsFromGuidance:
    def test_non_admin_operations_role_is_rejected(self):
        result = create_document_requests_from_guidance("SALES", "EMP-1", "vehicles_missing_titles")
        assert result == {"error": "Admin/Operations role required."}

    def test_unmapped_item_key_is_rejected(self):
        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "recon_delays")
        assert "error" in result
        assert "nothing real to do it with" in result["error"]

    def test_overview_error_is_passed_through(self, monkeypatch):
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: {"error": "denied"})
        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")
        assert result == {"error": "denied"}

    def test_all_clear_item_absent_is_rejected(self, monkeypatch):
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([]))
        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")
        assert "error" in result
        assert "Nothing currently flagged" in result["error"]

    def test_all_clear_item_present_with_zero_count_is_rejected(self, monkeypatch):
        item = _risk_item("vehicles_missing_titles", count=0, items=[])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))
        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")
        assert "error" in result

    def test_full_real_bulk_creation_flow(self, monkeypatch):
        v1 = _vehicle("VEH-1")
        v2 = _vehicle("VEH-2")
        item = _risk_item("vehicles_missing_titles", count=2, items=[{"id": v1}, {"id": v2}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert result["item_key"] == "vehicles_missing_titles"
        assert result["document_type"] == "Title"
        assert result["created_count"] == 2
        assert set(result["created"]) == {v1, v2}
        assert result["skipped_existing_count"] == 0
        assert result["errors"] == []

        assert _already_requested("title_processing", v1) is True
        assert _already_requested("title_processing", v2) is True

    def test_existing_open_request_is_skipped_not_duplicated(self, monkeypatch):
        v1 = _vehicle("VEH-1")
        request_document(VEHICLE, v1, "Title", "EMP-1")
        item = _risk_item("vehicles_missing_titles", count=1, items=[{"id": v1}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert result["created_count"] == 0
        assert result["skipped_existing_count"] == 1
        assert result["skipped_existing"] == [v1]

    def test_deal_document_type_uses_deal_jacket(self, monkeypatch):
        d1 = _deal("DEAL-1")
        item = _risk_item("contracts_missing_documents", count=1, items=[{"id": d1}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "contracts_missing_documents")

        assert result["document_type"] == "Deal Jacket"
        assert result["created_count"] == 1
        assert _already_requested("document_request", d1) is True

    def test_entity_id_missing_from_item_entry_is_skipped_silently(self, monkeypatch):
        item = _risk_item("vehicles_missing_titles", count=1, items=[{}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert result["created_count"] == 0
        assert result["skipped_existing_count"] == 0
        assert result["errors"] == []

    def test_nonexistent_entity_produces_a_real_error_entry(self, monkeypatch):
        item = _risk_item("vehicles_missing_titles", count=1, items=[{"id": "VEH-GHOST"}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        result = create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert result["created_count"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["entity_id"] == "VEH-GHOST"
        assert "error" in result["errors"][0]

    def test_save_graph_called_exactly_once_when_something_created(self, monkeypatch):
        calls = []
        monkeypatch.setattr(sg, "save_graph", lambda path: calls.append(path))
        v1 = _vehicle("VEH-1")
        item = _risk_item("vehicles_missing_titles", count=1, items=[{"id": v1}])
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))

        create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert len(calls) == 1

    def test_save_graph_not_called_when_nothing_created(self, monkeypatch):
        calls = []
        monkeypatch.setattr(sg, "save_graph", lambda path: calls.append(path))
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([]))

        create_document_requests_from_guidance("ADMIN", "EMP-1", "vehicles_missing_titles")

        assert len(calls) == 0


class TestReadinessGuidance:
    def test_no_executive_recommendations_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"executive_recommendations": []})
        assert sg._readiness_guidance("ADMIN") == []

    def test_missing_executive_recommendations_key_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {})
        assert sg._readiness_guidance("ADMIN") == []

    def test_real_field_mapping_from_executive_recommendation(self, monkeypatch):
        exec_item = {
            "key": "finance_funding_delays",
            "title": "Funding Delays Rising",
            "severity": "critical",
            "finding": "31 real deals are stalled.",
            "recommendation": "Assign more staff.",
            "basis": "real",
            "resolve": {"department": "Finance", "item_key": "deals", "hint": "Go look."},
        }
        monkeypatch.setattr(
            sg, "get_recommendations_overview",
            lambda role: {"executive_recommendations": [exec_item]},
        )

        result = sg._readiness_guidance("ADMIN")

        assert len(result) == 1
        item = result[0]
        assert item["key"] == "screen_guidance_exec_finance_funding_delays"
        assert item["title"] == "Funding Delays Rising"
        assert item["description"] == "31 real deals are stalled."
        assert item["prompt"] == "Assign more staff."
        assert item["priority"] == 4
        assert item["severity"] == "critical"
        assert item["count"] is None
        assert item["basis"] == "real"
        assert item["resolve"] == exec_item["resolve"]
        assert item["source"] == "executive_recommendation"
        # finance_funding_delays maps to deal_stage_stalled -> tier 1 (no active rule yet)
        assert item["automation"]["tier"] == 1
        assert item["do_it_available"] is False

    def test_prompt_falls_back_to_finding_when_no_recommendation_text(self, monkeypatch):
        exec_item = {
            "key": "x", "title": "T", "severity": "low",
            "finding": "The finding text.", "recommendation": None,
            "basis": "real", "resolve": None,
        }
        monkeypatch.setattr(
            sg, "get_recommendations_overview",
            lambda role: {"executive_recommendations": [exec_item]},
        )

        result = sg._readiness_guidance("ADMIN")

        assert result[0]["prompt"] == "The finding text."


class TestAdministrationGuidance:
    def test_non_admin_operations_role_returns_none(self):
        assert sg._administration_guidance("SALES") is None
        assert sg._administration_guidance("MARKETING") is None

    def test_admin_role_with_no_alerts_or_approvals_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(sg, "get_compliance_governance_summary", lambda: {"by_status": {}})
        monkeypatch.setattr(sg, "get_approval_hierarchy_summary", lambda: {"by_status": {}})
        assert sg._administration_guidance("ADMIN") == []

    def test_open_compliance_alerts_produce_a_real_item(self, monkeypatch):
        monkeypatch.setattr(sg, "get_compliance_governance_summary", lambda: {"by_status": {"open": 35}})
        monkeypatch.setattr(sg, "get_approval_hierarchy_summary", lambda: {"by_status": {}})

        result = sg._administration_guidance("ADMIN")

        assert len(result) == 1
        item = result[0]
        assert item["key"] == "screen_guidance_admin_open_compliance_alerts"
        assert item["title"] == "Open Compliance Alerts"
        assert "35" in item["description"]
        assert "35" in item["prompt"]
        assert item["count"] == 35
        assert item["severity"] == "critical"  # 25+ per _count_severity
        assert item["priority"] == 4
        assert item["basis"] == "real"
        assert item["resolve"] == {
            "department": "Administration",
            "item_key": "governance",
            "hint": "Open Compliance & Governance and resolve or override the alert.",
        }
        assert item["source"] == "administration_governance"
        assert item["do_it_available"] is False
        assert item["automation"]["tier"] == 0

    def test_pending_approvals_produce_a_real_item_resolving_to_roles_permissions(self, monkeypatch):
        monkeypatch.setattr(sg, "get_compliance_governance_summary", lambda: {"by_status": {}})
        monkeypatch.setattr(sg, "get_approval_hierarchy_summary", lambda: {"by_status": {"pending": 4}})

        result = sg._administration_guidance("OPERATIONS")

        assert len(result) == 1
        item = result[0]
        assert item["key"] == "screen_guidance_admin_pending_approvals"
        assert item["count"] == 4
        assert item["severity"] == "medium"  # 3-9 per _count_severity
        assert item["priority"] == 2
        assert item["resolve"]["item_key"] == "roles_permissions"

    def test_both_present_returns_both_items(self, monkeypatch):
        monkeypatch.setattr(sg, "get_compliance_governance_summary", lambda: {"by_status": {"open": 1}})
        monkeypatch.setattr(sg, "get_approval_hierarchy_summary", lambda: {"by_status": {"pending": 1}})

        result = sg._administration_guidance("ADMIN")

        assert len(result) == 2
        keys = {item["key"] for item in result}
        assert keys == {
            "screen_guidance_admin_open_compliance_alerts",
            "screen_guidance_admin_pending_approvals",
        }


class TestNetworkGuidance:
    def test_no_active_playbooks_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            sg, "get_playbook_library",
            lambda role: {"playbooks": [
                {"key": "pb1", "title": "T", "summary": "S", "is_currently_active": False},
            ]},
        )
        assert sg._network_guidance("ADMIN") == []

    def test_missing_playbooks_key_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(sg, "get_playbook_library", lambda role: {})
        assert sg._network_guidance("ADMIN") == []

    def test_active_playbook_produces_a_real_item(self, monkeypatch):
        pb = {
            "key": "clear_untouched_leads",
            "title": "Clear the Untouched Lead Backlog",
            "summary": "A static description.",
            "active_finding": "102 real internet leads are still untouched.",
            "is_currently_active": True,
            "automation_score": {"tier": 1, "label": "Automatable Today"},
        }
        monkeypatch.setattr(sg, "get_playbook_library", lambda role: {"playbooks": [pb]})

        result = sg._network_guidance("ADMIN")

        assert len(result) == 1
        item = result[0]
        assert item["key"] == "screen_guidance_playbook_clear_untouched_leads"
        assert item["title"] == "Clear the Untouched Lead Backlog"
        assert item["description"] == "102 real internet leads are still untouched."
        assert "Clear the Untouched Lead Backlog" in item["prompt"]
        assert "102 real internet leads are still untouched." in item["prompt"]
        assert item["priority"] == 2
        assert item["severity"] == "medium"
        assert item["count"] is None
        assert item["basis"] == "real"
        assert item["resolve"] == {
            "department": "Network",
            "item_key": "playbooks",
            "hint": "Open Playbooks and follow this guide's real steps.",
        }
        assert item["source"] == "playbook"
        assert item["automation"] == {"tier": 1, "label": "Automatable Today"}
        assert "do_it_available" not in item  # network items never carry this key

    def test_active_finding_falls_back_to_summary_when_absent(self, monkeypatch):
        pb = {
            "key": "pb2", "title": "T2", "summary": "A fallback summary.",
            "is_currently_active": True, "automation_score": {"tier": 0, "label": "No Automation Path Yet"},
        }
        monkeypatch.setattr(sg, "get_playbook_library", lambda role: {"playbooks": [pb]})

        result = sg._network_guidance("ADMIN")

        assert result[0]["description"] == "A fallback summary."

    def test_inactive_and_active_playbooks_mixed_only_active_surfaces(self, monkeypatch):
        pbs = [
            {"key": "a", "title": "A", "summary": "sa", "is_currently_active": False, "automation_score": {"tier": 0}},
            {"key": "b", "title": "B", "summary": "sb", "is_currently_active": True, "automation_score": {"tier": 0}},
        ]
        monkeypatch.setattr(sg, "get_playbook_library", lambda role: {"playbooks": pbs})

        result = sg._network_guidance("ADMIN")

        assert len(result) == 1
        assert result[0]["key"] == "screen_guidance_playbook_b"


class TestGetScreenGuidance:
    def test_unscoped_section_returns_not_yet_scoped_note(self):
        result = get_screen_guidance("ADMIN", "some_unmapped_department")
        assert result["department"] == "some_unmapped_department"
        assert result["guidance"] == []
        assert result["note"] == _NOT_YET_SCOPED_NOTE

    def test_none_section_normalizes_to_none_department(self):
        result = get_screen_guidance("ADMIN", None)
        assert result["department"] is None
        assert result["guidance"] == []
        assert result["note"] == _NOT_YET_SCOPED_NOTE

    def test_empty_string_section_normalizes_to_none_department(self):
        result = get_screen_guidance("ADMIN", "")
        assert result["department"] is None

    def test_section_is_lowercased_and_stripped(self, monkeypatch):
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"executive_recommendations": []})
        result = get_screen_guidance("ADMIN", "  READINESS  ")
        assert result["department"] == "readiness"

    def test_readiness_special_department_dispatches_correctly(self, monkeypatch):
        exec_item = {
            "key": "k1", "title": "Title1", "severity": "high",
            "finding": "f1", "recommendation": "r1", "basis": "real", "resolve": None,
        }
        monkeypatch.setattr(
            sg, "get_recommendations_overview",
            lambda role: {"executive_recommendations": [exec_item]},
        )

        result = get_screen_guidance("ADMIN", "readiness")

        assert result["department"] == "readiness"
        assert len(result["guidance"]) == 1
        assert result["guidance"][0]["key"] == "screen_guidance_exec_k1"
        assert result["note"] is None
        assert result["coaching_intensity"] == "productive"
        assert result["coaching_intensity_source"] == "default"

    def test_readiness_empty_returns_its_own_empty_note(self, monkeypatch):
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"executive_recommendations": []})
        result = get_screen_guidance("ADMIN", "readiness")
        assert result["guidance"] == []
        assert "real, current all-clear" in result["note"]

    def test_administration_role_denied_returns_error_not_note(self):
        result = get_screen_guidance("SALES", "administration")
        assert result == {
            "department": "administration",
            "guidance": [],
            "error": "Admin/Operations role required.",
        }

    def test_administration_admin_role_dispatches_correctly(self, monkeypatch):
        monkeypatch.setattr(sg, "get_compliance_governance_summary", lambda: {"by_status": {"open": 30}})
        monkeypatch.setattr(sg, "get_approval_hierarchy_summary", lambda: {"by_status": {}})

        result = get_screen_guidance("ADMIN", "administration")

        assert result["department"] == "administration"
        assert len(result["guidance"]) == 1
        assert result["note"] is None

    def test_network_special_department_dispatches_correctly(self, monkeypatch):
        pb = {"key": "pb", "title": "T", "summary": "s", "is_currently_active": True, "automation_score": {"tier": 0}}
        monkeypatch.setattr(sg, "get_playbook_library", lambda role: {"playbooks": [pb]})

        result = get_screen_guidance("ADMIN", "network")

        assert result["department"] == "network"
        assert len(result["guidance"]) == 1
        assert result["guidance"][0]["source"] == "playbook"

    def test_exception_only_department_composes_real_exception_items(self, monkeypatch):
        item1 = _risk_item("negative_gross_deals", severity="high", count=2)
        item2 = _risk_item("unfunded_contracts", severity="critical", count=30)
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item1, item2]))
        # sales also has a DEPARTMENT_RECOMMENDATION_KEYS entry -- isolate this
        # test to the exception source alone by supplying an empty rec overview
        # rather than depending on the real, unmocked recommendation engine.
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {}})

        result = get_screen_guidance("ADMIN", "sales")

        assert result["department"] == "sales"
        keys = [g["key"] for g in result["guidance"]]
        assert "screen_guidance_negative_gross_deals" in keys
        assert "screen_guidance_unfunded_contracts" in keys
        assert not any("open_compliance_issues" in k for k in keys)
        # sorted priority descending: unfunded_contracts (critical/4) before negative_gross_deals (high/3)
        assert result["guidance"][0]["key"] == "screen_guidance_unfunded_contracts"
        assert result["note"] is None

    def test_all_clear_items_are_skipped_not_surfaced(self, monkeypatch):
        item = _risk_item("negative_gross_deals", severity=None, count=0)
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {}})

        result = get_screen_guidance("ADMIN", "sales")

        assert result["guidance"] == []
        assert "real, current all-clear" in result["note"]

    def test_overview_error_short_circuits_the_whole_response(self, monkeypatch):
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: {"error": "denied for this role"})

        def _boom(role):
            raise AssertionError("get_recommendations_overview must not be called when the exception overview errors")

        monkeypatch.setattr(sg, "get_recommendations_overview", _boom)

        result = get_screen_guidance("SALES", "sales")

        assert result == {"department": "sales", "guidance": [], "error": "denied for this role"}

    def test_recommendation_only_department_marketing_composes_real_items(self, monkeypatch):
        # marketing has NO DEPARTMENT_EXCEPTION_KEYS entry at all -- proving
        # get_risk_center_overview is never even queried for it.
        def _boom(role):
            raise AssertionError("exception source must not be queried for marketing")

        monkeypatch.setattr(sg, "get_risk_center_overview", _boom)

        rec = _rec_item("marketing_channel_performance", severity="high", triggered=True)
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {"marketing": [rec]}})

        result = get_screen_guidance("MARKETING", "marketing")

        assert result["department"] == "marketing"
        assert len(result["guidance"]) == 1
        item = result["guidance"][0]
        assert item["key"] == "screen_guidance_rec_marketing_channel_performance"
        assert item["source"] == "recommendation"
        assert item["count"] is None
        assert result["note"] is None

    def test_untriggered_recommendation_is_skipped(self, monkeypatch):
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: (_ for _ in ()).throw(
            AssertionError("exception source must not be queried for marketing")
        ))
        rec = _rec_item("marketing_channel_performance", triggered=False)
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {"marketing": [rec]}})

        result = get_screen_guidance("MARKETING", "marketing")

        assert result["guidance"] == []

    def test_both_sources_merged_and_sorted_by_priority_for_finance(self, monkeypatch):
        exc = _risk_item("funding_delays", severity="medium", count=5)
        rec = _rec_item("finance_collections_risk", severity="critical", triggered=True)
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([exc]))
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {"finance": [rec]}})

        result = get_screen_guidance("FINANCE", "finance")

        assert result["department"] == "finance"
        assert len(result["guidance"]) == 2
        assert result["guidance"][0]["key"] == "screen_guidance_rec_finance_collections_risk"
        assert result["guidance"][1]["key"] == "screen_guidance_funding_delays"

    def test_operations_has_exception_source_only_no_recommendation_source(self, monkeypatch):
        exc = _risk_item("recon_delays", severity="high", count=60)
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([exc]))

        def _boom(role):
            raise AssertionError("recommendation source must not be queried for operations")

        monkeypatch.setattr(sg, "get_recommendations_overview", _boom)

        result = get_screen_guidance("OPERATIONS", "operations")

        assert len(result["guidance"]) == 1
        assert result["guidance"][0]["key"] == "screen_guidance_recon_delays"

    def test_coaching_intensity_wiring_is_actually_exercised(self, monkeypatch):
        # apply_intensity_to_tasks is a DEFERRED (in-function) import inside
        # get_screen_guidance -- only patchable via the true source module,
        # core.coaching, not via sg.apply_intensity_to_tasks (which doesn't
        # exist as a name in this module's own globals at all).
        calls = []

        def fake_apply(items, employee_id, role=None, department=None):
            calls.append((employee_id, role, department))
            return (["OVERRIDDEN"], "aggressive", "individual")

        monkeypatch.setattr("core.coaching.apply_intensity_to_tasks", fake_apply)

        item = _risk_item("negative_gross_deals", severity="high", count=2)
        monkeypatch.setattr(sg, "get_risk_center_overview", lambda role: _fake_risk_overview([item]))
        monkeypatch.setattr(sg, "get_recommendations_overview", lambda role: {"categories": {}})

        result = get_screen_guidance("SALES", "sales", employee_id="EMP-42")

        assert result["guidance"] == ["OVERRIDDEN"]
        assert result["coaching_intensity"] == "aggressive"
        assert result["coaching_intensity_source"] == "individual"
        assert calls == [("EMP-42", "SALES", "sales")]
