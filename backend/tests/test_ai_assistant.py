"""
Test coverage for core/ai_assistant.py -- the main, tool-calling AI Assistant
(ask_ai(), backing POST /ai/chat).

Most of this module's logic is genuinely network-dependent (a real OpenAI
chat-completion round trip with tool calling). This sandbox has no outbound
network access to the real OpenAI API (confirmed directly here, consistent
with every other AI-wizard test file in this suite) -- so ask_ai() with the
kill switch enabled genuinely hits the real try/except network-failure path
and returns the honest "having trouble reaching" fallback answer, never
raising into the caller. That's real, verified sandbox behavior, not a mock.

These tests cover the two fully-real, non-network code paths (the disabled
kill-switch early-return, and the enabled-but-unreachable exception fallback,
including its record_call_attempt() side effects) plus the one pure,
fully-testable helper function, _collect_resolved_entities().

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger

import core.ai_assistant as aa
import core.ai_management as am
from core.system_config import set_feature_flag


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    am._CALL_STATS.clear()
    yield
    ledger.reset()
    am._CALL_STATS.clear()


class TestAskAiDisabled:

    def test_disabled_returns_disabled_answer_with_empty_entities_and_no_report(self):
        set_feature_flag("ai_assistant_enabled", False, "EMP-TEST")
        answer, entities, report = aa.ask_ai("What's my inventory?", role="ADMIN")
        assert answer == aa._DISABLED_ANSWER
        assert entities == []
        assert report is None

    def test_disabled_records_blocked_call_attempt(self):
        set_feature_flag("ai_assistant_enabled", False, "EMP-TEST")
        aa.ask_ai("test question", role="ADMIN")
        stats = am.get_call_stats("ai_assistant")
        assert stats["attempted"] == 1
        assert stats["blocked"] == 1
        assert stats["succeeded"] == 0
        assert stats["fell_back"] == 0
        assert stats["last_outcome"] == "blocked"

    def test_disabled_message_mentions_administrator(self):
        set_feature_flag("ai_assistant_enabled", False, "EMP-TEST")
        answer, _, _ = aa.ask_ai("test", role="SALES")
        assert "disabled by your administrator" in answer


class TestAskAiEnabledButUnreachable:

    def test_enabled_falls_back_to_unreachable_answer(self):
        set_feature_flag("ai_assistant_enabled", True, "EMP-TEST")
        answer, entities, report = aa.ask_ai("What's my inventory?", role="ADMIN")
        assert answer.startswith(aa._UNREACHABLE_ANSWER_PREFIX)
        assert entities == []
        assert report is None

    def test_enabled_fallback_records_fell_back_call_attempt(self):
        set_feature_flag("ai_assistant_enabled", True, "EMP-TEST")
        aa.ask_ai("test question", role="ADMIN")
        stats = am.get_call_stats("ai_assistant")
        assert stats["attempted"] == 1
        assert stats["fell_back"] == 1
        assert stats["blocked"] == 0
        assert stats["succeeded"] == 0
        assert stats["last_outcome"] == "fell_back"
        assert stats["last_detail"]  # the real connection-error string is recorded

    def test_default_flag_state_is_enabled_on_a_fresh_ledger(self):
        # No SystemConfig entity exists yet -- is_feature_enabled() fails open,
        # so the call should reach the (unreachable, in this sandbox) OpenAI
        # client rather than short-circuiting to the disabled message.
        answer, entities, report = aa.ask_ai("test", role="ADMIN")
        assert answer != aa._DISABLED_ANSWER
        assert answer.startswith(aa._UNREACHABLE_ANSWER_PREFIX)
        assert entities == []
        assert report is None

    def test_default_flag_state_records_fell_back_not_blocked(self):
        aa.ask_ai("test", role="ADMIN")
        stats = am.get_call_stats("ai_assistant")
        assert stats["fell_back"] == 1
        assert stats["blocked"] == 0

    def test_unreachable_answer_suggests_using_dashboards(self):
        set_feature_flag("ai_assistant_enabled", True, "EMP-TEST")
        answer, _, _ = aa.ask_ai("test", role="ADMIN")
        assert "dashboards" in answer

    def test_multiple_calls_accumulate_stats(self):
        set_feature_flag("ai_assistant_enabled", False, "EMP-TEST")
        aa.ask_ai("q1", role="ADMIN")
        aa.ask_ai("q2", role="ADMIN")
        set_feature_flag("ai_assistant_enabled", True, "EMP-TEST")
        aa.ask_ai("q3", role="ADMIN")
        stats = am.get_call_stats("ai_assistant")
        assert stats["attempted"] == 3
        assert stats["blocked"] == 2
        assert stats["fell_back"] == 1


class TestCollectResolvedEntitiesSingleDict:

    def test_single_dict_result_is_appended(self):
        seen_ids = set()
        resolved = []
        tool_result = {"id": "VEH-00001", "entity_type": "Vehicle", "Make": "Ford"}
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == [tool_result]
        assert seen_ids == {"VEH-00001"}

    def test_single_dict_missing_id_is_ignored(self):
        seen_ids = set()
        resolved = []
        tool_result = {"entity_type": "Vehicle", "Make": "Ford"}
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == []
        assert seen_ids == set()

    def test_single_dict_missing_entity_type_is_ignored(self):
        seen_ids = set()
        resolved = []
        tool_result = {"id": "VEH-00001", "Make": "Ford"}
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == []

    def test_single_dict_non_string_id_is_ignored(self):
        seen_ids = set()
        resolved = []
        tool_result = {"id": 12345, "entity_type": "Vehicle"}
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == []


class TestCollectResolvedEntitiesListOfDicts:

    def test_list_of_dicts_all_appended(self):
        seen_ids = set()
        resolved = []
        tool_result = [
            {"id": "VEH-00001", "entity_type": "Vehicle"},
            {"id": "VEH-00002", "entity_type": "Vehicle"},
        ]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert len(resolved) == 2
        assert seen_ids == {"VEH-00001", "VEH-00002"}

    def test_list_with_invalid_entries_mixed_in_only_valid_ones_kept(self):
        seen_ids = set()
        resolved = []
        tool_result = [
            {"id": "VEH-00001", "entity_type": "Vehicle"},
            {"entity_type": "Vehicle"},  # missing id
            {"id": "VEH-00002"},  # missing entity_type
            "not a dict",
            {"id": "VEH-00003", "entity_type": "Vehicle"},
        ]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert seen_ids == {"VEH-00001", "VEH-00003"}
        assert len(resolved) == 2

    def test_list_capped_at_20_items(self):
        seen_ids = set()
        resolved = []
        tool_result = [
            {"id": f"VEH-{i:05d}", "entity_type": "Vehicle"} for i in range(30)
        ]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert len(resolved) == 20
        assert seen_ids == {f"VEH-{i:05d}" for i in range(20)}

    def test_empty_list_is_a_no_op(self):
        seen_ids = set()
        resolved = []
        aa._collect_resolved_entities([], seen_ids, resolved)
        assert resolved == []
        assert seen_ids == set()


class TestCollectResolvedEntitiesRelationshipShape:

    def test_relationship_shaped_list_extracts_nested_entity(self):
        seen_ids = set()
        resolved = []
        tool_result = [
            {"relationship_type": "OWNS", "entity": {"id": "VEH-00001", "entity_type": "Vehicle"}},
            {"relationship_type": "AUTHORIZED", "entity": {"id": "SRV-00001", "entity_type": "ServiceRecord"}},
        ]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert len(resolved) == 2
        assert resolved[0] == {"id": "VEH-00001", "entity_type": "Vehicle"}
        assert seen_ids == {"VEH-00001", "SRV-00001"}

    def test_relationship_entry_missing_entity_key_is_ignored(self):
        seen_ids = set()
        resolved = []
        tool_result = [{"relationship_type": "OWNS"}]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == []

    def test_relationship_entry_with_invalid_nested_entity_is_ignored(self):
        seen_ids = set()
        resolved = []
        tool_result = [{"relationship_type": "OWNS", "entity": {"entity_type": "Vehicle"}}]
        aa._collect_resolved_entities(tool_result, seen_ids, resolved)
        assert resolved == []


class TestCollectResolvedEntitiesDedup:

    def test_repeat_id_is_not_added_twice(self):
        seen_ids = set()
        resolved = []
        first = {"id": "VEH-00001", "entity_type": "Vehicle", "Make": "Ford"}
        second = {"id": "VEH-00001", "entity_type": "Vehicle", "Make": "Chevy"}
        aa._collect_resolved_entities(first, seen_ids, resolved)
        aa._collect_resolved_entities(second, seen_ids, resolved)
        assert len(resolved) == 1
        assert resolved[0]["Make"] == "Ford"  # first-seen wins

    def test_dedup_works_across_calls_sharing_seen_ids(self):
        seen_ids = set()
        resolved = []
        tool_result_1 = [{"id": "VEH-00001", "entity_type": "Vehicle"}]
        tool_result_2 = [
            {"id": "VEH-00001", "entity_type": "Vehicle"},
            {"id": "VEH-00002", "entity_type": "Vehicle"},
        ]
        aa._collect_resolved_entities(tool_result_1, seen_ids, resolved)
        aa._collect_resolved_entities(tool_result_2, seen_ids, resolved)
        assert len(resolved) == 2
        assert seen_ids == {"VEH-00001", "VEH-00002"}


class TestCollectResolvedEntitiesUnrecognizedShapes:

    def test_plain_string_tool_result_is_ignored(self):
        seen_ids = set()
        resolved = []
        aa._collect_resolved_entities("just a string answer", seen_ids, resolved)
        assert resolved == []
        assert seen_ids == set()

    def test_none_tool_result_is_ignored(self):
        seen_ids = set()
        resolved = []
        aa._collect_resolved_entities(None, seen_ids, resolved)
        assert resolved == []

    def test_int_tool_result_is_ignored(self):
        seen_ids = set()
        resolved = []
        aa._collect_resolved_entities(42, seen_ids, resolved)
        assert resolved == []
