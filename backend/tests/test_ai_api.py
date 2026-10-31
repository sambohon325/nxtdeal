"""
Tests for core/ai_api.py's ask() — specifically the dashboard-suggestion behavior added
alongside chat-triggered workspace rendering, and the dashboard ACL gate on the
workload/leaderboard/escalations fast paths (a real gap: these bypassed
can_access_dashboard entirely before this pass, meaning any role could get real
workload/leaderboard/escalation data through chat even if the matching /dashboard/*
route would have refused them). Monkeypatches ask_ai() and the three dashboard-fetch
functions so these tests are fast, deterministic, and don't make real OpenAI calls or
depend on live ledger state. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import ai_api
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, FINANCE_CONTRACT


@pytest.fixture(autouse=True)
def stub_backends(monkeypatch):

    # ask_ai() has returned a real (answer_text, resolved_entities, report_suggestion)
    # 3-tuple since session 76 (core/ai_assistant.py), and gained an optional
    # `employee_id` kwarg in the 2026-07-20 security-hardening pass (Task #5, threaded
    # through from ask()'s own new `caller_employee_id` param) -- this stub was never
    # updated to match either change (a pre-existing bug, confirmed via `git show HEAD`
    # matching the working tree exactly before this fix, unrelated to the AI-audit-trail
    # work that surfaced it). Fixed to accept the kwarg and return the real tuple shape.
    monkeypatch.setattr(
        ai_api,
        "ask_ai",
        lambda question, role=None, employee_id=None: (f"LLM answer to: {question}", [], None),
    )
    monkeypatch.setattr(ai_api, "get_workload_dashboard", lambda: [
        {"employee_id": "EMP-00001", "active_workload": 4}
    ])
    monkeypatch.setattr(ai_api, "get_leaderboard_dashboard", lambda: [
        {"employee_id": "EMP-00001", "conversion_rate": 42}
    ])
    monkeypatch.setattr(ai_api, "get_escalation_dashboard", lambda: [])


@pytest.fixture(autouse=True)
def fresh_ledger():
    """suggested_profile detection (session 21) reads the real ledger via
    core/repository.py — reset it around every test so entities from one test can't leak
    into another."""

    ledger.reset()

    yield

    ledger.reset()


def test_unmatched_question_falls_through_to_llm_with_no_suggestion():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert result == {"response": "LLM answer to: What's the weather like?"}
    assert "suggested_dashboard" not in result


def test_workload_fast_path_allowed_role():

    result = ai_api.ask("what's the current workload?", role="SALES")

    assert "EMP-00001" in result["response"]
    assert result["suggested_dashboard"] == "workload"


def test_workload_fast_path_denied_role_does_not_leak_data():
    """MARKETING isn't in DASHBOARD_ACCESS['workload'] — before this pass, the keyword
    shortcut ignored role entirely and would have returned real data anyway."""

    result = ai_api.ask("what's the current workload?", role="MARKETING")

    assert "EMP-00001" not in result["response"]
    assert "workload" in result["response"].lower()
    assert "suggested_dashboard" not in result


def test_leaderboard_fast_path_allowed_role():

    result = ai_api.ask("who's on the leaderboard?", role="OPERATIONS")

    assert "EMP-00001" in result["response"]
    assert result["suggested_dashboard"] == "leaderboard"


def test_leaderboard_fast_path_denied_role():

    result = ai_api.ask("who's on the leaderboard?", role="SERVICE")

    assert "EMP-00001" not in result["response"]
    assert "suggested_dashboard" not in result


def test_escalations_fast_path_allowed_role():

    result = ai_api.ask("are there any escalated leads?", role="ADMIN")

    assert result["suggested_dashboard"] == "escalations"


def test_llm_fallback_still_suggests_dashboard_for_known_topic():
    """'sales dashboard' matches DASHBOARD_TERMS but has no canned formatter — falls
    through to the (stubbed) LLM, but should still get suggested_dashboard attached."""

    result = ai_api.ask("show me the sales dashboard", role="SALES")

    assert result["response"] == "LLM answer to: show me the sales dashboard"
    assert result["suggested_dashboard"] == "sales"


def test_llm_fallback_respects_dashboard_acl_for_known_topic():

    result = ai_api.ask("show me the finance dashboard", role="SERVICE")

    assert "suggested_dashboard" not in result
    assert "don't have access" in result["response"]


def test_admin_can_reach_every_fast_path_and_llm_suggested_topic():

    for question, expected_key in [
        ("what's the current workload?", "workload"),
        ("who's on the leaderboard?", "leaderboard"),
        ("any escalated leads?", "escalations"),
        ("show me the executive dashboard", "executive"),
    ]:
        result = ai_api.ask(question, role="ADMIN")
        assert result["suggested_dashboard"] == expected_key


def test_entity_id_in_question_suggests_profile():
    """Profile lookup is chat-only as of session 21 — a question mentioning a real
    entity ID gets suggested_profile attached, driving the frontend's "View Profile"
    button, the same mechanic as suggested_dashboard."""

    ledger.add_entity(Entity(id="CUST-00042", entity_type=CUSTOMER, attributes={}))

    result = ai_api.ask("pull up CUST-00042", role="SALES")

    assert result["suggested_profile"] == "CUST-00042"


def test_unknown_entity_id_does_not_suggest_profile():

    result = ai_api.ask("pull up CUST-00042", role="SALES")

    assert "suggested_profile" not in result


def test_entity_id_suggestion_respects_role_access():
    """SALES isn't in FINANCE_CONTRACT's ENTITY_ACCESS — same rule /entity/{id} and
    /profile/{id} already enforce, so an ID a role can't see just doesn't get suggested,
    same as an unknown ID."""

    ledger.add_entity(Entity(id="FIN-00001", entity_type=FINANCE_CONTRACT, attributes={}))

    denied = ai_api.ask("show me FIN-00001", role="SALES")
    assert "suggested_profile" not in denied

    allowed = ai_api.ask("show me FIN-00001", role="FINANCE")
    assert allowed["suggested_profile"] == "FIN-00001"


def test_entity_id_suggestion_combines_with_llm_dashboard_suggestion():

    ledger.add_entity(Entity(id="CUST-00042", entity_type=CUSTOMER, attributes={}))

    result = ai_api.ask(
        "show me the sales dashboard and pull up CUST-00042", role="SALES"
    )

    assert result["suggested_dashboard"] == "sales"
    assert result["suggested_profile"] == "CUST-00042"


def test_entity_id_suggestion_combines_with_fast_path_dashboard():

    ledger.add_entity(Entity(id="CUST-00042", entity_type=CUSTOMER, attributes={}))

    result = ai_api.ask(
        "what's the current workload — also pull up CUST-00042", role="SALES"
    )

    assert result["suggested_dashboard"] == "workload"
    assert result["suggested_profile"] == "CUST-00042"


# --- Admin panels (roster/audit/compliance) + reset-password, session 26 ---


def test_roster_admin_panel_suggested_for_admin():

    result = ai_api.ask("show me the employee roster", role="ADMIN")

    assert result["suggested_admin_panel"] == "roster"


def test_roster_admin_panel_denied_for_non_admin():
    """Same "don't leak, don't error, just don't suggest it" shape as a denied
    suggested_dashboard — the response text says why, and nothing gets suggested."""

    result = ai_api.ask("show me the employee roster", role="SALES")

    assert "suggested_admin_panel" not in result
    assert "don't have access" in result["response"]


def test_audit_admin_panel_suggested_for_admin():

    result = ai_api.ask("what does the audit log show?", role="ADMIN")

    assert result["suggested_admin_panel"] == "audit"


def test_audit_admin_panel_denied_for_non_admin():

    result = ai_api.ask("show me the audit trail", role="OPERATIONS")

    assert "suggested_admin_panel" not in result


# The old "compliance score/layer/status" ADMIN_PANEL_TERMS key was retired session 38
# -- compliance is now a real, ADMIN+OPERATIONS-visible feature (core/compliance.py)
# with its own dedicated intent, see test_compliance_alerts_* below.
def test_compliance_alerts_suggested_for_admin():

    result = ai_api.ask("what's our compliance score?", role="ADMIN")

    assert result.get("suggested_compliance_panel") is True
    assert "suggested_admin_panel" not in result


def test_compliance_alerts_suggested_for_operations():

    result = ai_api.ask("show me compliance alerts", role="OPERATIONS")

    assert result.get("suggested_compliance_panel") is True


def test_compliance_alerts_denied_for_non_admin_ops():

    result = ai_api.ask("compliance issues", role="SALES")

    assert "suggested_compliance_panel" not in result
    assert "admin or operations" in result["response"].lower()


def test_compliance_alerts_not_suggested_for_unmatched_question():

    result = ai_api.ask("what's the weather", role="ADMIN")

    assert "suggested_compliance_panel" not in result


def test_reset_password_suggested_for_admin_with_employee_id():

    result = ai_api.ask("reset password for EMP-00003", role="ADMIN")

    assert result["suggested_reset_password"] == "EMP-00003"
    assert "confirm" in result["response"].lower()


def test_reset_password_not_suggested_without_employee_id():
    """"reset password" alone, with no EMP- id in the question, shouldn't suggest
    anything — there's nothing to confirm a reset for."""

    result = ai_api.ask("I need to reset a password", role="ADMIN")

    assert "suggested_reset_password" not in result


def test_reset_password_not_suggested_for_non_admin():

    result = ai_api.ask("reset password for EMP-00003", role="SALES")

    assert "suggested_reset_password" not in result


def test_reset_password_requires_both_keywords():
    """Just mentioning an employee ID, or just saying "reset" without "password" (or
    vice versa), shouldn't trigger a reset suggestion — avoids false positives on
    unrelated questions that happen to mention an EMP- id."""

    result = ai_api.ask("what's EMP-00003's workload?", role="ADMIN")

    assert "suggested_reset_password" not in result


def test_admin_panel_and_reset_password_can_combine():

    result = ai_api.ask(
        "show me the employee roster and reset password for EMP-00003", role="ADMIN"
    )

    assert result["suggested_admin_panel"] == "roster"
    assert result["suggested_reset_password"] == "EMP-00003"


# --- General (non-admin) panels: readiness_score / performance_rank /
# --- growth_opportunities, session 27 ---


def test_readiness_score_panel_suggested_for_any_role():
    """No ADMIN gate on general panels — /readiness is open to any logged-in role."""

    result = ai_api.ask("what's our readiness score?", role="SALES")

    assert result["suggested_panel"] == "readiness_score"


# The old "performance_rank"/"growth_opportunities" GENERAL_PANEL_TERMS placeholders
# (open to any role) were retired session 38 -- the Network page is now a real,
# ADMIN/OPERATIONS/FINANCE-gated feature (core/network_benchmark.py/
# core/network_audit.py), see test_network_benchmark_panel_* /
# test_network_audit_panel_* below.
def test_network_benchmark_panel_suggested_for_finance():

    result = ai_api.ask("how do we rank against the network?", role="FINANCE")

    assert result["suggested_network_panel"] == "benchmark"


def test_network_benchmark_panel_denied_for_sales():

    result = ai_api.ask("how do we rank against the network?", role="SALES")

    assert "suggested_network_panel" not in result
    assert "admin, operations, or finance" in result["response"].lower()


def test_network_audit_panel_suggested_for_operations():

    result = ai_api.ask("what are our growth opportunities?", role="OPERATIONS")

    assert result["suggested_network_panel"] == "audit"


def test_network_audit_panel_denied_for_marketing():

    result = ai_api.ask("what are our growth opportunities?", role="MARKETING")

    assert "suggested_network_panel" not in result


def test_general_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_panel" not in result


def test_general_panel_combines_with_admin_panel_for_admin():

    result = ai_api.ask(
        "show me the employee roster and our readiness score", role="ADMIN"
    )

    assert result["suggested_admin_panel"] == "roster"
    assert result["suggested_panel"] == "readiness_score"


# --- Marketing asset design/approval workflow, session 30 ---


def test_asset_templates_suggested_for_any_role():

    result = ai_api.ask("show me asset templates", role="SALES")

    assert result["suggested_asset_panel"] == "templates"


def test_asset_templates_suggested_via_create_flyer_phrasing():

    result = ai_api.ask("design a flyer for this car", role="SALES")

    assert result["suggested_asset_panel"] == "templates"


def test_my_assets_suggested_for_any_role():

    result = ai_api.ask("show me my assets", role="SERVICE")

    assert result["suggested_asset_panel"] == "my_assets"


def test_pending_approvals_suggested_for_marketing():

    result = ai_api.ask("what's in the asset approval queue?", role="MARKETING")

    assert result["suggested_asset_panel"] == "pending_approvals"


def test_pending_approvals_suggested_for_admin():

    result = ai_api.ask("show me pending approvals", role="ADMIN")

    assert result["suggested_asset_panel"] == "pending_approvals"


def test_pending_approvals_denied_for_sales():

    result = ai_api.ask("show me pending approvals", role="SALES")

    assert "suggested_asset_panel" not in result
    assert "don't have access" in result["response"]


def test_asset_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_asset_panel" not in result


# --- Campaign & customer-lifecycle engine intents (session 31) ---


def test_campaign_types_suggested_for_any_role():

    result = ai_api.ask("I want to run a retention campaign", role="SALES")

    assert result["suggested_campaign_panel"] == "types"


def test_campaign_types_suggested_via_launch_phrasing():

    result = ai_api.ask("let's launch a campaign for this inventory", role="SERVICE")

    assert result["suggested_campaign_panel"] == "types"


def test_my_campaigns_suggested_for_any_role():

    result = ai_api.ask("show me my campaigns", role="SERVICE")

    assert result["suggested_campaign_panel"] == "my_campaigns"


def test_pending_campaigns_suggested_for_marketing():

    result = ai_api.ask("what's in the campaign activation queue?", role="MARKETING")

    assert result["suggested_campaign_panel"] == "pending_campaigns"


def test_pending_campaigns_suggested_for_admin():

    result = ai_api.ask("show me pending campaigns", role="ADMIN")

    assert result["suggested_campaign_panel"] == "pending_campaigns"


def test_pending_campaigns_denied_for_sales():

    result = ai_api.ask("show me pending campaigns", role="SALES")

    assert "suggested_campaign_panel" not in result
    assert "don't have access" in result["response"]


def test_campaign_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_campaign_panel" not in result


# --- Website/inventory builder intents (session 32) ---


def test_website_sections_suggested_for_any_role():

    result = ai_api.ask("I want to build a website for our dealership", role="SALES")

    assert result["suggested_website_panel"] == "sections"


def test_website_sections_suggested_via_add_section_phrasing():

    result = ai_api.ask("let's add a section to the homepage", role="SERVICE")

    assert result["suggested_website_panel"] == "sections"


def test_my_sites_suggested_for_any_role():

    result = ai_api.ask("show me my websites", role="SERVICE")

    assert result["suggested_website_panel"] == "my_sites"


def test_pending_sites_suggested_for_marketing():

    result = ai_api.ask("what's in the site approval queue?", role="MARKETING")

    assert result["suggested_website_panel"] == "pending_sites"


def test_pending_sites_suggested_for_admin():

    result = ai_api.ask("show me pending websites", role="ADMIN")

    assert result["suggested_website_panel"] == "pending_sites"


def test_pending_sites_denied_for_sales():

    result = ai_api.ask("show me pending websites", role="SALES")

    assert "suggested_website_panel" not in result
    assert "don't have access" in result["response"]


def test_website_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_website_panel" not in result


# --- DMS Deal Desk intents (session 33) ---


def test_deal_desk_suggested_for_sales():

    result = ai_api.ask("I want to sell a car", role="SALES")

    assert result["suggested_deal_panel"] == "start_deal"


def test_deal_desk_suggested_for_finance():

    result = ai_api.ask("let's start a deal", role="FINANCE")

    assert result["suggested_deal_panel"] == "start_deal"


def test_deal_desk_denied_for_marketing():

    result = ai_api.ask("I want to sell a car", role="MARKETING")

    assert "suggested_deal_panel" not in result
    assert "don't have access" in result["response"]


def test_my_deals_suggested_for_sales():

    result = ai_api.ask("show me my deals", role="SALES")

    assert result["suggested_deal_panel"] == "my_deals"


def test_pending_financing_suggested_for_finance():

    result = ai_api.ask("what's in the financing queue?", role="FINANCE")

    assert result["suggested_deal_panel"] == "pending_financing"


def test_pending_financing_denied_for_sales():

    result = ai_api.ask("show me pending financing", role="SALES")

    assert "suggested_deal_panel" not in result
    assert "don't have access" in result["response"]


def test_deal_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_deal_panel" not in result


# --- Department Intelligence intents (session 35, renamed session 68 -- dropping the
# "Bumper BI" branding) ---


def test_intelligence_sales_department_matched_for_finance():

    result = ai_api.ask("show me department intelligence sales", role="FINANCE")

    assert result["suggested_intelligence_panel"] == "sales"


def test_intelligence_generic_term_matches_executive():

    result = ai_api.ask("show me department intelligence", role="ADMIN")

    assert result["suggested_intelligence_panel"] == "executive"


def test_intelligence_profit_leaks_matches_executive_for_operations():

    result = ai_api.ask("where are our profit leaks", role="OPERATIONS")

    assert result["suggested_intelligence_panel"] == "executive"


def test_intelligence_parts_matched_for_admin():

    result = ai_api.ask("department intelligence parts", role="ADMIN")

    assert result["suggested_intelligence_panel"] == "parts"


def test_intelligence_denied_for_sales():

    result = ai_api.ask("show me department intelligence", role="SALES")

    assert "suggested_intelligence_panel" not in result
    assert "don't have access" in result["response"]


def test_intelligence_denied_for_marketing():

    result = ai_api.ask("department intelligence service", role="MARKETING")

    assert "suggested_intelligence_panel" not in result
    assert "don't have access" in result["response"]


def test_intelligence_panel_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="ADMIN")

    assert "suggested_intelligence_panel" not in result


# ---------------------------------------------------------------------------
# Agentic bot layer (session 36) -- "my tasks" is open to any role (the task list is
# already personalized server-side to the caller), "bot coverage" is ADMIN-only, same
# gating shape as roster/audit/compliance.
# ---------------------------------------------------------------------------

def test_bot_tasks_intent_matched_for_any_role():

    result = ai_api.ask("show my tasks", role="SALES")

    assert result["suggested_bot_panel"] == "my_tasks"


def test_bot_tasks_intent_phrase_variant():

    result = ai_api.ask("what should I be doing today?", role="SERVICE")

    assert result["suggested_bot_panel"] == "my_tasks"


def test_bot_tasks_not_suggested_for_unmatched_question():

    result = ai_api.ask("What's the weather like?", role="SALES")

    assert "suggested_bot_panel" not in result


def test_bot_coverage_admin_panel_matched_for_admin():

    result = ai_api.ask("show bot coverage", role="ADMIN")

    assert result["suggested_admin_panel"] == "bot_coverage"


def test_bot_coverage_admin_panel_denied_for_non_admin():

    result = ai_api.ask("show bot coverage", role="SALES")

    assert "suggested_admin_panel" not in result
    assert "don't have access" in result["response"]
