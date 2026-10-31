"""
Tests for core/governance.py / core/governance_api.py -- Administration's
"Compliance & Governance" screen. This module is a pure composition layer
over three already-real engines (core/compliance.py's cited-federal-rules
alert engine, core/permissions_registry.py's tier-gated ApprovalRequest
hierarchy, core/audit_center.py's EVENT_CATEGORIES-based audit-log slicing)
-- it makes zero ledger mutations of its own. Every test below drives the
real underlying engines directly (create_alert/resolve_alert/override_alert,
create_approval_request/approve_step/reject_step, set_override) and then
asserts governance.py's own aggregation/blending math against that real
data.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.audit import audit_log
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD

from core import compliance
from core import permissions_registry
from core import governance
from core import governance_api
from core.compliance_rules import NOT_LEGAL_ADVICE_NOTICE
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_state():
    ledger.reset()
    audit_log.reset()
    yield
    ledger.reset()
    audit_log.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(compliance, "save_graph", lambda filepath: None)
    monkeypatch.setattr(compliance, "save_audit_log", lambda filepath: None)
    monkeypatch.setattr(permissions_registry, "save_graph", lambda filepath: None)
    monkeypatch.setattr(permissions_registry, "save_audit_log", lambda filepath: None)


def _employee(employee_id, title):
    e = Entity(id=employee_id, entity_type=EMPLOYEE, attributes={"Title": title})
    ledger.add_entity(e)
    return e


def _lead(lead_id="LEAD-1"):
    e = Entity(id=lead_id, entity_type=LEAD, attributes={})
    ledger.add_entity(e)
    return e


def _reg_z_violation():
    return {
        "rule_id": "reg_z_disclosure",
        "law": "Truth in Lending Act / Regulation Z",
        "citation": "12 CFR 1026.18",
        "category": "lending",
        "severity": "high",
        "description": "Missing a real disclosure.",
    }


class TestGetComplianceGovernanceSummary:

    def test_an_empty_ledger_returns_real_honest_zeroed_aggregates(self):
        result = governance.get_compliance_governance_summary()

        assert result["total_alerts"] == 0
        assert result["by_status"] == {}
        assert result["resolution_rate"] is None
        assert result["avg_resolution_hours"] is None
        assert result["by_law"] == {}
        assert result["notice"] == NOT_LEGAL_ADVICE_NOTICE

    def test_computes_a_real_by_status_breakdown_and_resolution_rate(self):
        entity = _lead("LEAD-1")
        alert_open = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])
        alert_to_resolve = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])
        alert_to_override = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        compliance.resolve_alert(alert_to_resolve.id, "EMP-1", notes="fixed it")
        compliance.override_alert(alert_to_override.id, "EMP-2", "documented exception")

        result = governance.get_compliance_governance_summary()

        assert result["total_alerts"] == 3
        assert result["by_status"] == {"open": 1, "resolved": 1, "overridden": 1}
        # closed = resolved + overridden = 2, total = 3.
        assert result["resolution_rate"] == pytest.approx(2 / 3, rel=1e-3)

    def test_avg_resolution_hours_is_a_real_non_negative_float_once_something_is_closed(self):
        entity = _lead("LEAD-1")
        alert = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])
        compliance.resolve_alert(alert.id, "EMP-1")

        result = governance.get_compliance_governance_summary()

        assert result["avg_resolution_hours"] is not None
        assert result["avg_resolution_hours"] >= 0.0

    def test_avg_resolution_hours_stays_none_when_nothing_is_closed_yet(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        result = governance.get_compliance_governance_summary()

        assert result["avg_resolution_hours"] is None

    def test_by_law_maps_a_known_rule_id_to_its_real_law_name(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        result = governance.get_compliance_governance_summary()

        assert result["by_law"] == {"Truth in Lending Act / Regulation Z": 1}

    def test_by_law_falls_back_to_the_raw_rule_id_for_an_unknown_but_present_rule_id(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [{"rule_id": "made_up_rule", "description": "x"}])

        result = governance.get_compliance_governance_summary()

        assert result["by_law"] == {"made_up_rule": 1}

    def test_by_law_falls_back_to_unknown_rule_when_rule_id_is_falsy(self):
        # core.compliance.create_alert() itself requires every violation dict to
        # have a real "rule_id" key (it indexes with v["rule_id"], not .get()) --
        # so the only way a violation can reach the ledger with no real rule_id is
        # a present-but-falsy value, not a fully missing key.
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [{"rule_id": None, "description": "no real rule"}])

        result = governance.get_compliance_governance_summary()

        assert result["by_law"] == {"Unknown rule": 1}


class TestGetApprovalHierarchySummary:

    def test_an_empty_ledger_returns_real_honest_zeroed_aggregates(self):
        result = governance.get_approval_hierarchy_summary()

        assert result["total_requests"] == 0
        assert result["by_status"] == {}
        assert result["by_chain"] == {}
        assert result["throughput_rate"] is None
        assert result["avg_turnaround_hours"] is None
        assert result["pending_requests"] == []
        # Real, always-present chain catalog regardless of whether any
        # request has ever been created against it. Security-hardening
        # Task #8 ("AI execution-tier framework") added a 5th real chain,
        # "autonomous_ai_rule_activation" -- core/workflow_automation.py's
        # create_rule() now opens a real request against it on every rule
        # creation, gating activation on a real manager-tier approval.
        assert len(result["chains"]) == 5
        assert {c["key"] for c in result["chains"]} == {
            "permission_change_request", "role_change_request",
            "policy_exception", "expense_request",
            "autonomous_ai_rule_activation",
        }

    def test_a_single_step_chain_fully_approves_on_one_real_manager_tier_approval(self):
        _employee("EMP-STAFF", "Sales Associate")
        _employee("EMP-MGR", "Sales Manager")

        created = permissions_registry.create_approval_request(
            "permission_change_request", "EMP-STAFF", "Please grant me deals.fund"
        )
        assert created["status"] == "pending"

        # A staff-tier approver can't clear a manager-tier step.
        denied = permissions_registry.approve_step(created["id"], "EMP-STAFF")
        assert "error" in denied

        approved = permissions_registry.approve_step(created["id"], "EMP-MGR", note="looks fine")
        assert approved["status"] == "approved"
        assert approved["current_step_index"] == 1

        summary = governance.get_approval_hierarchy_summary()

        assert summary["total_requests"] == 1
        assert summary["by_status"] == {"approved": 1}
        assert summary["by_chain"] == {"permission_change_request": 1}
        assert summary["throughput_rate"] == pytest.approx(1.0)
        assert summary["avg_turnaround_hours"] is not None
        assert summary["avg_turnaround_hours"] >= 0.0
        assert summary["pending_requests"] == []

    def test_a_two_step_chain_stays_pending_after_only_the_manager_step_clears(self):
        _employee("EMP-MGR", "Sales Manager")

        created = permissions_registry.create_approval_request(
            "role_change_request", "EMP-MGR", "Promote me to Finance"
        )

        step_one = permissions_registry.approve_step(created["id"], "EMP-MGR")
        assert step_one["status"] == "pending"
        assert step_one["current_step_index"] == 1

        summary = governance.get_approval_hierarchy_summary()

        assert summary["by_status"] == {"pending": 1}
        assert summary["throughput_rate"] == pytest.approx(0.0)
        # A pending request never contributes a real turnaround-hours sample.
        assert summary["avg_turnaround_hours"] is None
        assert len(summary["pending_requests"]) == 1
        assert summary["pending_requests"][0]["id"] == created["id"]

    def test_a_two_step_chain_fully_approves_once_an_executive_clears_the_second_step(self):
        _employee("EMP-MGR", "Sales Manager")
        _employee("EMP-EXEC", "General Manager")

        created = permissions_registry.create_approval_request(
            "role_change_request", "EMP-MGR", "Promote me to Finance"
        )
        permissions_registry.approve_step(created["id"], "EMP-MGR")

        # A manager-tier approver can't clear the executive-tier second step.
        denied = permissions_registry.approve_step(created["id"], "EMP-MGR")
        assert "error" in denied

        final = permissions_registry.approve_step(created["id"], "EMP-EXEC")
        assert final["status"] == "approved"

        summary = governance.get_approval_hierarchy_summary()
        assert summary["by_status"] == {"approved": 1}
        assert summary["throughput_rate"] == pytest.approx(1.0)

    def test_a_rejected_request_counts_as_decided_and_not_pending(self):
        _employee("EMP-MGR", "Sales Manager")

        created = permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "New office chairs"
        )
        rejected = permissions_registry.reject_step(created["id"], "EMP-MGR", "budget freeze")
        assert rejected["status"] == "rejected"

        summary = governance.get_approval_hierarchy_summary()

        assert summary["by_status"] == {"rejected": 1}
        assert summary["throughput_rate"] == pytest.approx(1.0)
        assert summary["avg_turnaround_hours"] is not None

    def test_by_chain_breaks_down_real_counts_across_multiple_chains(self):
        _employee("EMP-MGR", "Sales Manager")

        permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )
        permissions_registry.create_approval_request(
            "policy_exception", "EMP-MGR", "Exception request"
        )
        permissions_registry.create_approval_request(
            "policy_exception", "EMP-MGR", "Another exception"
        )

        summary = governance.get_approval_hierarchy_summary()

        assert summary["by_chain"] == {"expense_request": 1, "policy_exception": 2}
        assert summary["total_requests"] == 3


class TestGetGovernanceActionLog:

    def test_an_empty_log_returns_real_honest_zeroes(self):
        result = governance.get_governance_action_log()

        assert result == {"total_matches": 0, "returned": 0, "events": []}

    def test_merges_compliance_and_approval_events_by_default(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        _employee("EMP-MGR", "Sales Manager")
        permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )

        result = governance.get_governance_action_log()

        assert result["total_matches"] == 2
        event_types = {e["event_type"] for e in result["events"]}
        assert event_types == {"compliance_alert_created", "approval_request_created"}
        for e in result["events"]:
            assert e["category"] in ("Compliance", "Approvals")

    def test_narrows_to_a_single_real_category_when_given(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        _employee("EMP-MGR", "Sales Manager")
        permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )

        result = governance.get_governance_action_log(category="Compliance")

        assert result["total_matches"] == 1
        assert result["events"][0]["event_type"] == "compliance_alert_created"
        assert result["events"][0]["category"] == "Compliance"

    def test_permissions_category_events_are_captured_too(self):
        _employee("EMP-1", "Sales Associate")
        permissions_registry.set_override("EMP-1", "deals.fund", True, "EMP-ADMIN")

        result = governance.get_governance_action_log(category="Permissions")

        assert result["total_matches"] == 1
        assert result["events"][0]["event_type"] == "permission_override_set"

    def test_an_event_type_outside_the_three_governance_categories_is_never_included(self):
        # A plain, unrelated audit event (e.g. a real login) has category
        # "Other" under core/audit_center.py's own EVENT_CATEGORIES map --
        # it should never leak into the governance action log.
        audit_log.record(event_type="login_success", summary="EMP-1 logged in", actor="EMP-1")

        result = governance.get_governance_action_log()

        assert result["total_matches"] == 0

    def test_results_are_sorted_most_recent_first(self):
        entity = _lead("LEAD-1")
        first = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])
        second = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        result = governance.get_governance_action_log()

        entity_ids = [e["entity_id"] for e in result["events"]]
        # Both alerts are on the same entity -- assert on real ordering by
        # checking the second-created alert's own audit summary comes first.
        assert second.id in result["events"][0]["summary"]
        assert first.id in result["events"][1]["summary"]

    def test_limit_truncates_but_total_matches_still_reflects_the_real_full_count(self):
        entity = _lead("LEAD-1")
        for _ in range(5):
            compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        result = governance.get_governance_action_log(limit=2)

        assert result["total_matches"] == 5
        assert result["returned"] == 2
        assert len(result["events"]) == 2

    def test_rejects_an_unknown_category(self):
        result = governance_api.get_governance_action_log_api(ADMIN, category="Bogus")

        assert "error" in result


class TestGetGovernanceHealth:

    def test_blends_two_real_rates_when_both_are_present(self):
        entity = _lead("LEAD-1")
        alert = compliance.create_alert("deal_fund", entity, [_reg_z_violation()])
        compliance.resolve_alert(alert.id, "EMP-1")

        _employee("EMP-MGR", "Sales Manager")
        req = permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )
        permissions_registry.approve_step(req["id"], "EMP-MGR")

        result = governance.get_governance_health()

        assert result["compliance_resolution_rate"] == pytest.approx(1.0)
        assert result["approval_throughput_rate"] == pytest.approx(1.0)
        assert result["blended_health_score"] == pytest.approx(1.0)
        assert result["basis"] == "real_blend_of_compliance_resolution_rate_and_approval_throughput_rate"
        assert result["open_compliance_alerts"] == 0
        assert result["pending_approval_requests"] == 0

    def test_drops_a_missing_input_honestly_instead_of_treating_it_as_zero(self):
        # No compliance alerts have ever been created -> resolution_rate is
        # None -> the blend should be computed off approval throughput alone,
        # not silently averaged against a fabricated 0%.
        _employee("EMP-MGR", "Sales Manager")
        req = permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )
        permissions_registry.approve_step(req["id"], "EMP-MGR")

        result = governance.get_governance_health()

        assert result["compliance_resolution_rate"] is None
        assert result["approval_throughput_rate"] == pytest.approx(1.0)
        assert result["blended_health_score"] == pytest.approx(1.0)

    def test_is_none_when_neither_real_source_has_any_data_at_all(self):
        result = governance.get_governance_health()

        assert result["blended_health_score"] is None
        assert result["compliance_resolution_rate"] is None
        assert result["approval_throughput_rate"] is None

    def test_accepts_precomputed_summaries_to_avoid_a_redundant_recomputation(self):
        compliance_summary = {"resolution_rate": 0.5}
        approval_summary = {"throughput_rate": 0.9}

        result = governance.get_governance_health(compliance_summary, approval_summary)

        assert result["blended_health_score"] == pytest.approx(0.7)


class TestGetGovernanceOverview:

    def test_composes_every_real_section_plus_the_honest_not_yet_tracked_notes(self):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        _employee("EMP-MGR", "Sales Manager")
        permissions_registry.create_approval_request(
            "expense_request", "EMP-MGR", "Chairs"
        )

        result = governance.get_governance_overview()

        assert result["compliance_summary"]["total_alerts"] == 1
        assert result["approval_hierarchy"]["total_requests"] == 1
        assert result["governance_health"]["open_compliance_alerts"] == 1
        assert result["governance_action_log"]["total_matches"] == 2
        assert set(result["not_yet_tracked"].keys()) == {
            "policy_management", "workflow_templates", "department_standards",
        }

    def test_action_log_inside_the_overview_is_capped_at_30(self):
        entity = _lead("LEAD-1")
        for _ in range(35):
            compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        result = governance.get_governance_overview()

        assert result["governance_action_log"]["total_matches"] == 35
        assert result["governance_action_log"]["returned"] == 30


class TestGovernanceApiAcl:

    @pytest.mark.parametrize("role", [SALES, FINANCE, MARKETING, SERVICE])
    def test_every_function_rejects_a_non_admin_ops_role(self, role):
        assert governance_api.get_governance_overview_api(role) == {
            "error": "Admin/Operations role required."
        }
        assert governance_api.get_compliance_governance_summary_api(role) == {
            "error": "Admin/Operations role required."
        }
        assert governance_api.get_approval_hierarchy_summary_api(role) == {
            "error": "Admin/Operations role required."
        }
        assert governance_api.get_governance_health_api(role) == {
            "error": "Admin/Operations role required."
        }
        assert governance_api.get_governance_action_log_api(role) == {
            "error": "Admin/Operations role required."
        }

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_an_allowed_role_gets_the_real_underlying_result(self, role):
        entity = _lead("LEAD-1")
        compliance.create_alert("deal_fund", entity, [_reg_z_violation()])

        overview = governance_api.get_governance_overview_api(role)
        assert overview["compliance_summary"]["total_alerts"] == 1

        summary = governance_api.get_compliance_governance_summary_api(role)
        assert summary["total_alerts"] == 1

        hierarchy = governance_api.get_approval_hierarchy_summary_api(role)
        assert hierarchy["total_requests"] == 0

        health = governance_api.get_governance_health_api(role)
        assert health["open_compliance_alerts"] == 1

        log = governance_api.get_governance_action_log_api(role)
        assert log["total_matches"] == 1

    def test_action_log_api_rejects_an_unknown_category_before_an_allowed_role_check_passes(self):
        result = governance_api.get_governance_action_log_api(ADMIN, category="NotReal")

        assert "error" in result
