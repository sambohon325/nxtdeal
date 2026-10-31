"""
Tests for core/ai_audit.py -- the comprehensive, durable AI action audit
trail (security-hardening pass, 2026-07-20, Task #5), plus core/ai_audit_api.py's
ADMIN/OPERATIONS-only ACL layer.

AiActionLog entities live on the real graph ledger (a first-class, own-lifecycle
entity type -- see core/entity_types.py's own comment), so this file follows
test_workforce.py's own pattern: a fresh_ledger fixture resetting core.dealeros.ledger
between tests, plus a no_real_persistence fixture stubbing out the real disk write
flush_ai_audit_log() makes (core/ai_audit.py deliberately does a deferred, in-function
`from core.storage import save_graph` rather than a module-level import -- see that
module's own docstring on the batched-save discipline this follows -- so the stub here
patches core.storage.save_graph directly rather than an ai_audit-module attribute).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import AI_ACTION_LOG
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import ai_audit
from core.ai_audit import (
    log_action,
    flush_ai_audit_log,
    list_ai_actions,
    get_ai_audit_dashboard,
)
from core.ai_audit_api import (
    get_ai_audit_dashboard_api,
    list_ai_actions_api,
    flush_ai_audit_log_api,
)
from core.ai_management import record_call_attempt, _stats_for


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    import core.storage as storage_mod

    monkeypatch.setattr(storage_mod, "save_graph", lambda filepath: None)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
ADMIN_ROLES = (ADMIN, OPERATIONS)
NON_ADMIN_ROLES = (SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# log_action()
# ---------------------------------------------------------------------------


class TestLogAction:

    def test_creates_a_real_entity_on_the_ledger(self):
        action_id = log_action("ai_assistant", "succeeded")

        entity = ledger.get_entity(action_id)
        assert entity is not None
        assert entity.entity_type == AI_ACTION_LOG
        assert entity.attributes["feature_key"] == "ai_assistant"
        assert entity.attributes["outcome"] == "succeeded"

    def test_ids_are_unique_and_sequential(self):
        first = log_action("ai_assistant", "succeeded")
        second = log_action("ai_assistant", "succeeded")

        assert first != second
        assert first.startswith("AIACT-")
        assert second.startswith("AIACT-")

    def test_defaults_are_honestly_none_not_guessed(self):
        action_id = log_action("website_wizard", "succeeded")

        entity = ledger.get_entity(action_id)
        assert entity.attributes["actor"] is None
        assert entity.attributes["prompt_summary"] is None
        assert entity.attributes["output_summary"] is None
        assert entity.attributes["detail"] is None

    def test_records_actor_prompt_output_detail(self):
        action_id = log_action(
            "ai_assistant",
            "succeeded",
            actor="EMP-00001",
            prompt_summary="What is my pipeline coverage?",
            output_summary="Your pipeline coverage is real and detailed.",
            detail="some detail",
        )

        entity = ledger.get_entity(action_id)
        assert entity.attributes["actor"] == "EMP-00001"
        assert entity.attributes["prompt_summary"] == "What is my pipeline coverage?"
        assert entity.attributes["output_summary"] == "Your pipeline coverage is real and detailed."
        assert entity.attributes["detail"] == "some detail"

    def test_created_at_is_a_real_timestamp(self):
        action_id = log_action("ai_assistant", "succeeded")

        entity = ledger.get_entity(action_id)
        assert entity.attributes["created_at"]
        assert "T" in entity.attributes["created_at"]

    def test_never_calls_save_graph_directly(self, monkeypatch):
        # log_action() itself must never persist -- that's the whole batched-save
        # point of this module. Assert directly against core.storage.save_graph
        # rather than the autouse no_real_persistence stub, so a regression here
        # would fail loudly even if that fixture's own stub silently absorbed it.
        calls = []
        import core.storage as storage_mod
        monkeypatch.setattr(storage_mod, "save_graph", lambda filepath: calls.append(filepath))

        log_action("ai_assistant", "succeeded")
        log_action("ai_assistant", "blocked")

        assert calls == []


class TestPromptOutputTruncation:

    def test_short_text_is_not_truncated(self):
        action_id = log_action("ai_assistant", "succeeded", prompt_summary="short")

        entity = ledger.get_entity(action_id)
        assert entity.attributes["prompt_summary"] == "short"

    def test_long_text_is_truncated_with_a_marker(self):
        long_text = "x" * 1000
        action_id = log_action("ai_assistant", "succeeded", prompt_summary=long_text)

        entity = ledger.get_entity(action_id)
        summary = entity.attributes["prompt_summary"]
        assert len(summary) < len(long_text)
        assert summary.startswith("x" * 500)
        assert "truncated" in summary
        assert "1000 chars total" in summary

    def test_exactly_at_the_limit_is_not_truncated(self):
        exact_text = "y" * ai_audit._MAX_SUMMARY_CHARS
        action_id = log_action("ai_assistant", "succeeded", prompt_summary=exact_text)

        entity = ledger.get_entity(action_id)
        assert entity.attributes["prompt_summary"] == exact_text

    def test_empty_string_becomes_none(self):
        action_id = log_action("ai_assistant", "succeeded", prompt_summary="")

        entity = ledger.get_entity(action_id)
        assert entity.attributes["prompt_summary"] is None


# ---------------------------------------------------------------------------
# flush_ai_audit_log()
# ---------------------------------------------------------------------------


class TestFlushAiAuditLog:

    def test_calls_save_graph_exactly_once(self, monkeypatch):
        calls = []
        import core.storage as storage_mod
        monkeypatch.setattr(storage_mod, "save_graph", lambda filepath: calls.append(filepath))

        result = flush_ai_audit_log()

        assert len(calls) == 1
        assert result["flushed"] is True
        assert result["flushed_at"]


# ---------------------------------------------------------------------------
# list_ai_actions()
# ---------------------------------------------------------------------------


class TestListAiActions:

    def test_empty_ledger_returns_empty_list(self):
        assert list_ai_actions() == []

    def test_most_recent_first(self):
        first = log_action("ai_assistant", "succeeded")
        second = log_action("ai_assistant", "succeeded")
        third = log_action("ai_assistant", "succeeded")

        actions = list_ai_actions()

        assert [a["id"] for a in actions] == [third, second, first]

    def test_filters_by_feature_key(self):
        log_action("ai_assistant", "succeeded")
        log_action("help_assistant", "succeeded")

        actions = list_ai_actions(feature_key="help_assistant")

        assert len(actions) == 1
        assert actions[0]["feature_key"] == "help_assistant"

    def test_filters_by_actor(self):
        log_action("ai_assistant", "succeeded", actor="EMP-00001")
        log_action("ai_assistant", "succeeded", actor="EMP-00002")

        actions = list_ai_actions(actor="EMP-00002")

        assert len(actions) == 1
        assert actions[0]["actor"] == "EMP-00002"

    def test_filters_by_outcome(self):
        log_action("ai_assistant", "succeeded")
        log_action("ai_assistant", "blocked")

        actions = list_ai_actions(outcome="blocked")

        assert len(actions) == 1
        assert actions[0]["outcome"] == "blocked"

    def test_combined_filters(self):
        log_action("ai_assistant", "succeeded", actor="EMP-00001")
        log_action("ai_assistant", "blocked", actor="EMP-00001")
        log_action("ai_assistant", "blocked", actor="EMP-00002")

        actions = list_ai_actions(feature_key="ai_assistant", actor="EMP-00001", outcome="blocked")

        assert len(actions) == 1

    def test_limit_caps_results(self):
        for _ in range(5):
            log_action("ai_assistant", "succeeded")

        actions = list_ai_actions(limit=2)

        assert len(actions) == 2

    def test_limit_none_returns_everything(self):
        for _ in range(5):
            log_action("ai_assistant", "succeeded")

        actions = list_ai_actions(limit=None)

        assert len(actions) == 5


# ---------------------------------------------------------------------------
# get_ai_audit_dashboard()
# ---------------------------------------------------------------------------


class TestGetAiAuditDashboard:

    def test_empty_ledger(self):
        dash = get_ai_audit_dashboard()

        assert dash["total_actions"] == 0
        assert dash["by_feature"] == {}
        assert dash["by_outcome"] == {}
        assert dash["distinct_actors_with_recorded_activity"] == 0
        assert dash["recent"] == []

    def test_by_feature_and_by_outcome_breakdown(self):
        log_action("ai_assistant", "succeeded")
        log_action("ai_assistant", "blocked")
        log_action("help_assistant", "succeeded")

        dash = get_ai_audit_dashboard()

        assert dash["total_actions"] == 3
        assert dash["by_feature"] == {"ai_assistant": 2, "help_assistant": 1}
        assert dash["by_outcome"] == {"succeeded": 2, "blocked": 1}

    def test_distinct_actors_only_counts_real_actors(self):
        log_action("ai_assistant", "succeeded", actor="EMP-00001")
        log_action("ai_assistant", "succeeded", actor="EMP-00001")
        log_action("ai_assistant", "succeeded", actor="EMP-00002")
        log_action("website_wizard", "succeeded")  # actor=None -- shouldn't count

        dash = get_ai_audit_dashboard()

        assert dash["distinct_actors_with_recorded_activity"] == 2

    def test_recent_is_capped_at_25(self):
        for _ in range(30):
            log_action("ai_assistant", "succeeded")

        dash = get_ai_audit_dashboard()

        assert len(dash["recent"]) == 25

    def test_recent_is_most_recent_first(self):
        log_action("ai_assistant", "succeeded", prompt_summary="first")
        log_action("ai_assistant", "succeeded", prompt_summary="second")

        dash = get_ai_audit_dashboard()

        assert dash["recent"][0]["prompt_summary"] == "second"


# ---------------------------------------------------------------------------
# record_call_attempt() -- core/ai_management.py's real production call path,
# confirming it correctly threads through into a real AiActionLog entity
# (this is the exact end-to-end chain ai_assistant.py's ask_ai() exercises).
# ---------------------------------------------------------------------------


class TestRecordCallAttemptWritesRealAiActionLog:

    def test_writes_a_real_entity_matching_the_in_memory_counters(self):
        stats = record_call_attempt(
            "ai_assistant", "succeeded",
            actor="EMP-00003", prompt_summary="q", output_summary="a",
        )

        assert stats["attempted"] == 1
        assert stats["succeeded"] == 1

        actions = list_ai_actions(feature_key="ai_assistant", actor="EMP-00003")
        assert len(actions) == 1
        assert actions[0]["outcome"] == "succeeded"
        assert actions[0]["prompt_summary"] == "q"
        assert actions[0]["output_summary"] == "a"

    def test_backward_compatible_with_no_new_kwargs(self):
        # every pre-existing call site across 13 modules calls this with just
        # (feature_key, outcome[, detail]) -- confirm that still works and still
        # writes a real (actor=None) AiActionLog entry.
        stats = record_call_attempt("website_wizard", "fell_back", detail="network error")

        assert stats["fell_back"] == 1

        actions = list_ai_actions(feature_key="website_wizard")
        assert len(actions) == 1
        assert actions[0]["actor"] is None
        assert actions[0]["detail"] == "network error"

    def test_does_not_call_save_graph(self, monkeypatch):
        calls = []
        import core.storage as storage_mod
        monkeypatch.setattr(storage_mod, "save_graph", lambda filepath: calls.append(filepath))

        record_call_attempt("ai_assistant", "succeeded")

        assert calls == []


# ---------------------------------------------------------------------------
# core/ai_audit_api.py -- ACL layer (ADMIN/OPERATIONS-only)
# ---------------------------------------------------------------------------


class TestAiAuditApiAcl:

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_dashboard(self, role):
        result = get_ai_audit_dashboard_api(role)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_actions(self, role):
        result = list_ai_actions_api(role)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_denied_flush(self, role):
        result = flush_ai_audit_log_api(role)
        assert result == {"error": "Admin/Operations role required."}

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_dashboard(self, role):
        result = get_ai_audit_dashboard_api(role)
        assert "error" not in result
        assert "total_actions" in result

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_actions(self, role):
        log_action("ai_assistant", "succeeded")

        result = list_ai_actions_api(role)

        assert "error" not in result
        assert len(result["actions"]) == 1

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_allowed_flush(self, role, monkeypatch):
        import core.storage as storage_mod
        monkeypatch.setattr(storage_mod, "save_graph", lambda filepath: None)

        result = flush_ai_audit_log_api(role)

        assert result["flushed"] is True

    def test_actions_api_passes_through_filters(self):
        log_action("ai_assistant", "succeeded", actor="EMP-00001")
        log_action("ai_assistant", "blocked", actor="EMP-00002")

        result = list_ai_actions_api(ADMIN, actor="EMP-00002")

        assert len(result["actions"]) == 1
        assert result["actions"][0]["actor"] == "EMP-00002"
