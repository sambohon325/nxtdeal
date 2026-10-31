"""
Tests for the agentic-bot FLEET (core/bot_fleet.py + core/bot_fleet_api.py) — Pillar 4
slice 1, 2026-07-23. Run from backend/ with `pytest`.

Covers: the nine team agents materialize inactive; section normalization; admin
activate/deactivate; auto mode gated by the same default-deny bot.coverage.auto_mode
capability as Bot Coverage; workflow-step recording persists as graph entities; and the
honest frequent-sequence derivation (a workflow is only "recognized" once it has actually
recurred, sequences never chain across different actors/runs, sub-sequences are dominated
by their maximal parent).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import TEAM_AGENT, TEAM_WORKFLOW_EVENT
from core.permissions import ADMIN, SALES

from core import bot_fleet
from core import bot_fleet_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture
def grant_auto(monkeypatch):
    """Grant the default-deny bot.coverage.auto_mode capability dealer-wide, the same way
    tests/test_bot.py does — so auto-mode activation tests exercise fleet behavior, not the
    permission layer (which has its own tests)."""
    import core.bot_permissions as bot_permissions_mod

    monkeypatch.setattr(bot_permissions_mod, "save_graph", lambda filepath: None)
    monkeypatch.setattr(bot_permissions_mod, "save_audit_log", lambda filepath: None)

    from core.bot_permissions import grant_capability

    grant_capability("bot.coverage.auto_mode", "dealer_wide", True, "EMP-TEST-SETUP")
    yield


# ---- fleet listing + normalization --------------------------------------------------

def test_fleet_materializes_nine_agents_all_inactive_by_default():
    fleet = bot_fleet.list_fleet()

    assert len(fleet) == 9
    assert {a["section"] for a in fleet} == set(bot_fleet.FLEET_SECTIONS)
    assert all(a["status"] == "inactive" and a["mode"] == "draft" for a in fleet)
    assert all(a["workflow_step_count"] == 0 for a in fleet)

    # Materialized as real TeamAgent graph entities (single ledger — no side store).
    agents = [e for e in ledger.get_all().values() if e.entity_type == TEAM_AGENT]
    assert len(agents) == 9


def test_get_or_create_agent_is_idempotent():
    a1 = bot_fleet.get_or_create_agent("Sales")
    a2 = bot_fleet.get_or_create_agent("sales")  # different casing, same agent
    assert a1.id == a2.id
    assert len([e for e in ledger.get_all().values() if e.entity_type == TEAM_AGENT]) == 1


def test_normalize_section_case_insensitive_and_rejects_unknown():
    assert bot_fleet.normalize_section("  ServICE ") == "service"
    assert bot_fleet.normalize_section("Network") == "network"
    assert bot_fleet.normalize_section("accounting") is None
    assert bot_fleet.normalize_section("") is None
    assert bot_fleet.normalize_section(None) is None


# ---- activation ---------------------------------------------------------------------

def test_activate_draft_then_deactivate():
    result = bot_fleet.activate_agent("Sales", "draft", "EMP-ADMIN")
    assert "error" not in result
    assert result["agent"]["status"] == "active"
    assert result["agent"]["mode"] == "draft"
    assert result["agent"]["activated_by"] == "EMP-ADMIN"

    off = bot_fleet.deactivate_agent("sales", "EMP-ADMIN")
    assert off["agent"]["status"] == "inactive"
    assert off["agent"]["mode"] == "draft"
    assert off["agent"]["deactivated_by"] == "EMP-ADMIN"


def test_activate_unknown_section_and_bad_mode_error():
    assert "error" in bot_fleet.activate_agent("accounting", "draft", "EMP-ADMIN")
    assert "error" in bot_fleet.activate_agent("sales", "sideways", "EMP-ADMIN")


def test_auto_mode_denied_without_capability():
    result = bot_fleet.activate_agent("Sales", "auto", "EMP-ADMIN")
    assert "error" in result
    assert "auto" in result["error"].lower()
    # Denied activation must not have flipped the agent on.
    agent = bot_fleet.get_or_create_agent("sales")
    assert agent.attributes["status"] == "inactive"


def test_auto_mode_allowed_with_capability(grant_auto):
    result = bot_fleet.activate_agent("Sales", "auto", "EMP-ADMIN")
    assert "error" not in result
    assert result["agent"]["status"] == "active"
    assert result["agent"]["mode"] == "auto"


# ---- workflow recording + derivation ------------------------------------------------

def test_record_workflow_step_persists_as_entity_and_counts():
    out = bot_fleet.record_workflow_step("Sales", "EMP-1", "open_lead", step_label="Open lead")
    assert "error" not in out
    events = [e for e in ledger.get_all().values() if e.entity_type == TEAM_WORKFLOW_EVENT]
    assert len(events) == 1
    assert events[0].attributes["section"] == "sales"
    assert events[0].attributes["actor"] == "EMP-1"
    assert events[0].attributes["action_key"] == "open_lead"

    wf = bot_fleet.get_team_workflows("sales")
    assert wf["available"] is True
    assert wf["step_count"] == 1
    assert wf["recognized_workflows"] == []  # a single step is not a recurring workflow


def test_record_requires_action_key_and_valid_section():
    assert "error" in bot_fleet.record_workflow_step("sales", "EMP-1", "")
    assert "error" in bot_fleet.record_workflow_step("accounting", "EMP-1", "open_lead")


def test_workflow_recognized_only_after_it_recurs():
    # Employee 1 runs open_lead -> log_call -> advance once.
    for action in ("open_lead", "log_call", "advance"):
        bot_fleet.record_workflow_step("sales", "EMP-1", action, workflow_key="run-a")

    once = bot_fleet.get_team_workflows("sales")
    assert once["recognized_workflows"] == []  # seen only once -> not yet a pattern

    # Employee 2 runs the same sequence -> now it has recurred across the team.
    for action in ("open_lead", "log_call", "advance"):
        bot_fleet.record_workflow_step("sales", "EMP-2", action, workflow_key="run-b")

    twice = bot_fleet.get_team_workflows("sales")
    steps = [w["steps"] for w in twice["recognized_workflows"]]
    assert ["open_lead", "log_call", "advance"] in steps
    top = twice["recognized_workflows"][0]
    assert top["occurrences"] >= 2
    # The maximal 3-step workflow dominates its 2-step sub-sequences.
    assert ["open_lead", "log_call"] not in steps


def test_sequences_do_not_chain_across_different_actors():
    # Two different employees each do a single, different step. No 2-step sequence exists,
    # so nothing should be mis-recognized as a shared workflow.
    bot_fleet.record_workflow_step("service", "EMP-1", "open_ro")
    bot_fleet.record_workflow_step("service", "EMP-2", "close_ro")

    wf = bot_fleet.get_team_workflows("service")
    assert wf["recognized_workflows"] == []
    assert set(wf["distinct_actors"]) == {"EMP-1", "EMP-2"}


def test_get_team_workflows_unknown_section_is_unavailable_not_an_error():
    wf = bot_fleet.get_team_workflows("accounting")
    assert wf["available"] is False


# ---- api gate -----------------------------------------------------------------------

def test_activate_api_requires_admin():
    denied = bot_fleet_api.activate_agent_api(SALES, "EMP-9", "sales", "draft")
    assert "error" in denied

    allowed = bot_fleet_api.activate_agent_api(ADMIN, "EMP-ADMIN", "sales", "draft")
    assert "error" not in allowed
    assert allowed["agent"]["status"] == "active"


def test_deactivate_api_requires_admin():
    assert "error" in bot_fleet_api.deactivate_agent_api(SALES, "EMP-9", "sales")


def test_fleet_and_workflow_views_open_to_any_role():
    # Viewing is not admin-gated — any authenticated role gets the read.
    fleet = bot_fleet_api.get_fleet_api(SALES)
    assert "fleet" in fleet and "summary" in fleet
    assert fleet["summary"]["total_agents"] == 9

    wf = bot_fleet_api.get_team_workflows_api(SALES, "sales")
    assert wf["available"] is True


def test_record_api_records_for_the_calling_employee():
    out = bot_fleet_api.record_workflow_step_api("EMP-7", "marketing", "send_campaign")
    assert "error" not in out
    events = [e for e in ledger.get_all().values() if e.entity_type == TEAM_WORKFLOW_EVENT]
    assert len(events) == 1
    assert events[0].attributes["actor"] == "EMP-7"
    assert events[0].attributes["section"] == "marketing"


# ---- slice 4e: agentic AUTO-EXECUTION of a recognized workflow -----------------------

def _seed_recognized_sales_workflow(steps=("open_lead", "log_call")):
    """Record the same step sequence twice (same actor, two runs) so it clears
    MIN_WORKFLOW_OCCURRENCES and becomes a recognized workflow for the Sales agent."""
    for run in ("run-a", "run-b"):
        for action in steps:
            bot_fleet.record_workflow_step("sales", "EMP-1", action, workflow_key=run)


@pytest.fixture
def grant_fleet_exec(grant_auto):
    """On top of grant_auto (bot.coverage.auto_mode), also grant bot.fleet.auto_execute
    dealer-wide, so run tests exercise the execute path rather than the permission layer."""
    from core.bot_permissions import grant_capability

    grant_capability("bot.fleet.auto_execute", "dealer_wide", True, "EMP-TEST-SETUP")
    yield


def test_run_requires_an_active_agent():
    _seed_recognized_sales_workflow()
    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")
    assert "error" in out and "not active" in out["error"]


def test_run_requires_a_recognized_workflow():
    bot_fleet.activate_agent("sales", "draft", "EMP-ADMIN")
    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")
    assert "error" in out and "nothing to run" in out["error"]


def test_run_drafts_every_step_when_no_safe_actions_registered(grant_fleet_exec):
    # Fully armed (active + auto + both capabilities + kill switch on), but the shipped
    # FLEET_SAFE_ACTIONS is EMPTY -> nothing executes. This is the safety boundary.
    _seed_recognized_sales_workflow()
    bot_fleet.activate_agent("sales", "auto", "EMP-ADMIN")

    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")

    assert out["mode"] == "auto"
    assert out["executed_count"] == 0
    assert out["drafted_count"] == len(out["workflow"])
    assert all(s["status"] == "drafted" for s in out["steps"])

    from core.entity_types import TEAM_AGENT_RUN
    runs = [e for e in ledger.get_all().values() if e.entity_type == TEAM_AGENT_RUN]
    assert len(runs) == 1


def test_run_executes_only_whitelisted_safe_steps(grant_fleet_exec, monkeypatch):
    calls = []

    def _safe(section, actor, action_key, run_by):
        calls.append((section, action_key))
        return {"ok": True}

    monkeypatch.setattr(bot_fleet, "FLEET_SAFE_ACTIONS", {"open_lead": _safe})

    _seed_recognized_sales_workflow(("open_lead", "log_call"))
    bot_fleet.activate_agent("sales", "auto", "EMP-ADMIN")

    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")

    assert out["mode"] == "auto"
    assert out["executed_count"] == 1  # only open_lead is whitelisted
    assert out["drafted_count"] == len(out["workflow"]) - 1
    executed = [s["action_key"] for s in out["steps"] if s["status"] == "executed"]
    assert executed == ["open_lead"]
    assert calls == [("sales", "open_lead")]


def test_draft_mode_never_executes_even_with_a_safe_action(monkeypatch):
    def _safe(section, actor, action_key, run_by):
        raise AssertionError("a draft-mode agent must never execute")

    monkeypatch.setattr(bot_fleet, "FLEET_SAFE_ACTIONS", {"open_lead": _safe})

    _seed_recognized_sales_workflow()
    bot_fleet.activate_agent("sales", "draft", "EMP-ADMIN")

    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")
    assert out["mode"] == "draft"
    assert out["executed_count"] == 0


def test_auto_mode_without_fleet_capability_does_not_execute(grant_auto, monkeypatch):
    # grant_auto grants bot.coverage.auto_mode (so auto ACTIVATION succeeds) but NOT
    # bot.fleet.auto_execute -> the per-run execute gate is false -> everything drafts.
    def _safe(section, actor, action_key, run_by):
        raise AssertionError("must not execute without bot.fleet.auto_execute")

    monkeypatch.setattr(bot_fleet, "FLEET_SAFE_ACTIONS", {"open_lead": _safe})

    _seed_recognized_sales_workflow()
    bot_fleet.activate_agent("sales", "auto", "EMP-ADMIN")

    out = bot_fleet.run_recognized_workflow("sales", "EMP-ADMIN")
    assert out["mode"] == "draft"
    assert out["executed_count"] == 0


def test_run_api_is_admin_only(grant_fleet_exec):
    _seed_recognized_sales_workflow()
    bot_fleet.activate_agent("sales", "auto", "EMP-ADMIN")

    denied = bot_fleet_api.run_recognized_workflow_api(SALES, "EMP-9", "sales")
    assert "error" in denied

    allowed = bot_fleet_api.run_recognized_workflow_api(ADMIN, "EMP-ADMIN", "sales")
    assert "error" not in allowed
    assert allowed["section"] == "sales"
