"""Tests for core/ai_management.py -- the real AI feature catalog, the
per-feature kill switches backed by core/system_config.py's FEATURE_FLAGS
(layered underneath core/ai_kill_switch.py's dealer-wide/department-scoped
overrides), the in-memory call-attempt counters, the Hub-facing network
snapshot builder, and the Administration Control Center overview.

Written 2026-07-20 as part of CAF-00123 (missing_test_coverage) closure --
this module previously had zero dedicated pytest coverage despite backing a
real, security-relevant AI kill-switch surface (Task #37 of the Security
Hardening Initiative).

Follows this codebase's established multi-target monkeypatch convention for
modules with their own module-level `save_graph`/`save_audit_log` imports
(see backend/tests/test_ai_kill_switch.py / test_ai_audit.py) -- each module
that does its own `from core.X import save_Y` needs its OWN patched
attribute; patching core.audit_storage.save_audit_log directly does NOT
affect core.ai_management.save_audit_log or core.ai_kill_switch.save_audit_log,
since those are separate name bindings created at import time.
"""

import pytest

from core.dealeros import ledger
from core.entity_types import AI_ACTION_LOG
from core.audit import audit_log

import core.system_config as system_config
import core.ai_kill_switch as ai_kill_switch
import core.ai_management as ai_management

from core.ai_management import (
    AI_FEATURE_CATALOG,
    _CATALOG_BY_KEY,
    _stats_for,
    record_call_attempt,
    is_feature_enabled,
    set_feature_enabled,
    get_call_stats,
    build_ai_management_network_snapshot,
    get_ai_management_overview,
    SANDBOX_NETWORK_NOTE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def fresh_audit_log():
    audit_log.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # system_config.py's own module-level save_graph -- backs set_feature_flag()
    # and set_ai_kill_switch() (both routed through core.system_config).
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)
    # ai_management.py's own module-level save_audit_log -- backs
    # set_feature_enabled()'s real audit_log.record() call.
    monkeypatch.setattr(ai_management, "save_audit_log", lambda filepath: None)
    # ai_kill_switch.py's own module-level save_audit_log -- backs
    # _record_toggle(), called by set_dealer_wide_kill_switch()/
    # set_department_kill_switch().
    monkeypatch.setattr(ai_kill_switch, "save_audit_log", lambda filepath: None)


@pytest.fixture(autouse=True)
def reset_call_stats():
    ai_management._CALL_STATS.clear()
    yield
    ai_management._CALL_STATS.clear()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_catalog_has_twenty_one_entries(self):
        # 13 base entries + communications_hub_summary (Communications Hub's
        # real AI summary feature, core/communications_hub.py).
        assert len(AI_FEATURE_CATALOG) == 21

    def test_every_entry_has_the_required_shape(self):
        required_keys = {
            "key", "flag", "name", "module", "functions", "description",
            "has_tool_calling_access", "fallback_exists", "wired_route", "route_note",
        }
        for entry in AI_FEATURE_CATALOG:
            assert required_keys.issubset(entry.keys())
            assert isinstance(entry["key"], str) and entry["key"]
            assert isinstance(entry["flag"], str) and entry["flag"]
            assert isinstance(entry["functions"], list) and entry["functions"]

    def test_catalog_by_key_matches_catalog(self):
        assert set(_CATALOG_BY_KEY.keys()) == {entry["key"] for entry in AI_FEATURE_CATALOG}
        for entry in AI_FEATURE_CATALOG:
            assert _CATALOG_BY_KEY[entry["key"]] is entry

    def test_every_key_and_flag_is_unique(self):
        keys = [entry["key"] for entry in AI_FEATURE_CATALOG]
        flags = [entry["flag"] for entry in AI_FEATURE_CATALOG]
        assert len(keys) == len(set(keys))
        assert len(flags) == len(set(flags))

    def test_only_ai_assistant_has_tool_calling_access(self):
        with_access = [e["key"] for e in AI_FEATURE_CATALOG if e["has_tool_calling_access"]]
        assert with_access == ["ai_assistant"]

    def test_only_help_assistant_is_missing_a_wired_route(self):
        unwired = [e["key"] for e in AI_FEATURE_CATALOG if not e["wired_route"]]
        assert unwired == ["help_assistant"]

    def test_every_feature_has_a_stated_fallback(self):
        # Every real AI-backed feature in this codebase is documented as having
        # an honest fallback path -- confirmed by this module's own docstring.
        assert all(entry["fallback_exists"] for entry in AI_FEATURE_CATALOG)


# ---------------------------------------------------------------------------
# _stats_for
# ---------------------------------------------------------------------------


class TestStatsFor:
    def test_default_shape(self):
        stats = _stats_for("ai_assistant")
        assert stats == {
            "attempted": 0,
            "succeeded": 0,
            "fell_back": 0,
            "blocked": 0,
            "last_outcome": None,
            "last_at": None,
        }

    def test_same_key_returns_the_same_stored_dict(self):
        first = _stats_for("ai_assistant")
        first["attempted"] = 7
        second = _stats_for("ai_assistant")
        assert second is first
        assert second["attempted"] == 7

    def test_works_for_a_key_not_in_the_real_catalog(self):
        # _stats_for() itself doesn't validate against AI_FEATURE_CATALOG --
        # that check lives one layer up, in is_feature_enabled()/set_feature_enabled().
        stats = _stats_for("not_a_real_feature")
        assert stats["attempted"] == 0

    def test_different_keys_get_independent_dicts(self):
        a = _stats_for("ai_assistant")
        b = _stats_for("email_sms_wizard")
        a["attempted"] = 5
        assert b["attempted"] == 0


# ---------------------------------------------------------------------------
# record_call_attempt
# ---------------------------------------------------------------------------


class TestRecordCallAttempt:
    def test_increments_attempted_on_every_call(self):
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("ai_assistant", "fell_back")
        stats = get_call_stats("ai_assistant")
        assert stats["attempted"] == 2

    @pytest.mark.parametrize("outcome", ["succeeded", "fell_back", "blocked"])
    def test_increments_the_matching_outcome_counter(self, outcome):
        record_call_attempt("email_sms_wizard", outcome)
        stats = get_call_stats("email_sms_wizard")
        assert stats[outcome] == 1
        other_outcomes = {"succeeded", "fell_back", "blocked"} - {outcome}
        for other in other_outcomes:
            assert stats[other] == 0

    def test_unrecognized_outcome_still_increments_attempted_only(self):
        record_call_attempt("ai_assistant", "something_unexpected")
        stats = get_call_stats("ai_assistant")
        assert stats["attempted"] == 1
        assert stats["succeeded"] == 0
        assert stats["fell_back"] == 0
        assert stats["blocked"] == 0
        assert stats["last_outcome"] == "something_unexpected"

    def test_records_last_outcome_and_last_detail(self):
        record_call_attempt("ai_assistant", "fell_back", detail="APIConnectionError")
        stats = _stats_for("ai_assistant")
        assert stats["last_outcome"] == "fell_back"
        assert stats["last_detail"] == "APIConnectionError"
        assert stats["last_at"] is not None

    def test_returns_the_live_stats_dict(self):
        result = record_call_attempt("ai_assistant", "succeeded")
        assert result is _stats_for("ai_assistant")
        assert result["attempted"] == 1

    def test_creates_a_real_ai_action_log_ledger_entity(self):
        before = len(ledger.entities)
        record_call_attempt(
            "ai_assistant",
            "succeeded",
            actor="EMP-00001",
            prompt_summary="how many leads today",
            output_summary="there are 12 open leads",
            detail="ok",
        )
        after = len(ledger.entities)
        assert after == before + 1

        new_entities = [
            e for e in ledger.entities.values()
            if e.entity_type == AI_ACTION_LOG
        ]
        assert len(new_entities) == 1
        entity = new_entities[0]
        assert entity.attributes["feature_key"] == "ai_assistant"
        assert entity.attributes["outcome"] == "succeeded"
        assert entity.attributes["actor"] == "EMP-00001"
        assert entity.attributes["prompt_summary"] == "how many leads today"
        assert entity.attributes["output_summary"] == "there are 12 open leads"

    def test_multiple_calls_each_create_their_own_ai_action_log_entity(self):
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("ai_assistant", "fell_back")
        record_call_attempt("email_sms_wizard", "blocked")
        action_logs = [e for e in ledger.entities.values() if e.entity_type == AI_ACTION_LOG]
        assert len(action_logs) == 3

    def test_defaults_actor_and_summaries_to_none(self):
        record_call_attempt("ai_assistant", "succeeded")
        action_logs = [e for e in ledger.entities.values() if e.entity_type == AI_ACTION_LOG]
        entity = action_logs[0]
        assert entity.attributes["actor"] is None
        assert entity.attributes["prompt_summary"] is None
        assert entity.attributes["output_summary"] is None

    def test_does_not_call_save_graph_on_its_own(self, monkeypatch):
        # log_action() itself never calls save_graph() (see core/ai_audit.py's
        # own docstring) -- confirm no *unstubbed* save attempt happens by
        # asserting the real (unstubbed-in-this-test) save_graph is never hit.
        calls = []
        monkeypatch.setattr(system_config, "save_graph", lambda filepath: calls.append(filepath))
        record_call_attempt("ai_assistant", "succeeded")
        assert calls == []


# ---------------------------------------------------------------------------
# is_feature_enabled -- default state, per-feature flag, and the layered
# dealer-wide / department kill switches from core/ai_kill_switch.py.
# ---------------------------------------------------------------------------


class TestIsFeatureEnabled:
    def test_unknown_feature_key_fails_open(self):
        assert is_feature_enabled("not_a_real_feature") is True

    def test_defaults_to_true_before_any_toggle(self):
        assert is_feature_enabled("ai_assistant") is True

    def test_reflects_a_disabled_flag(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is False

    def test_reflects_a_re_enabled_flag(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        set_feature_enabled("ai_assistant", True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is True

    def test_disabling_one_feature_does_not_affect_a_sibling(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        assert is_feature_enabled("email_sms_wizard") is True

    def test_dealer_wide_kill_switch_disables_every_mapped_and_unmapped_feature(self):
        ai_kill_switch.set_dealer_wide_kill_switch(True, "EMP-00001", reason="incident")
        for entry in AI_FEATURE_CATALOG:
            assert is_feature_enabled(entry["key"]) is False

    def test_dealer_wide_kill_switch_overrides_a_feature_that_is_otherwise_enabled(self):
        # The per-feature flag itself never got touched -- the dealer-wide
        # switch is a wider veto layered on top.
        ai_kill_switch.set_dealer_wide_kill_switch(True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is False
        ai_kill_switch.set_dealer_wide_kill_switch(False, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is True

    def test_department_kill_switch_disables_only_features_owned_by_that_department(self):
        # ai_assistant is mapped to Sales; email_sms_wizard is mapped to Marketing.
        ai_kill_switch.set_department_kill_switch("Sales", True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is False
        assert is_feature_enabled("email_sms_wizard") is True

    def test_a_different_departments_kill_switch_does_not_affect_this_feature(self):
        ai_kill_switch.set_department_kill_switch("Finance", True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is True

    def test_unmapped_cross_department_features_are_immune_to_any_department_switch(self):
        for department in ai_kill_switch.REAL_DEPARTMENTS:
            ai_kill_switch.set_department_kill_switch(department, True, "EMP-00001")
        assert is_feature_enabled("help_assistant") is True
        assert is_feature_enabled("workspace_explain") is True

    def test_deactivating_a_department_kill_switch_restores_the_feature(self):
        ai_kill_switch.set_department_kill_switch("Sales", True, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is False
        ai_kill_switch.set_department_kill_switch("Sales", False, "EMP-00001")
        assert is_feature_enabled("ai_assistant") is True

    def test_department_switch_still_gated_by_the_narrower_per_feature_flag(self):
        # Even with no kill switch active at all, a feature explicitly
        # disabled at the flag level stays disabled.
        set_feature_enabled("email_sms_wizard", False, "EMP-00001")
        ai_kill_switch.set_department_kill_switch("Sales", True, "EMP-00001")
        assert is_feature_enabled("email_sms_wizard") is False


# ---------------------------------------------------------------------------
# set_feature_enabled
# ---------------------------------------------------------------------------


class TestSetFeatureEnabled:
    def test_unknown_feature_key_returns_an_error(self):
        result = set_feature_enabled("not_a_real_feature", False, "EMP-00001")
        assert "error" in result
        assert "not_a_real_feature" in result["error"]

    def test_unknown_feature_key_does_not_write_an_audit_event(self):
        set_feature_enabled("not_a_real_feature", False, "EMP-00001")
        assert audit_log.get_by_type("ai_feature_toggled") == []

    def test_successful_disable_returns_the_expected_shape(self):
        result = set_feature_enabled("ai_assistant", False, "EMP-00001")
        assert result == {
            "feature_key": "ai_assistant",
            "name": "AI Assistant (Workspace Chat)",
            "flag": "ai_assistant_enabled",
            "enabled": False,
        }

    def test_round_trips_through_is_feature_enabled(self):
        set_feature_enabled("ai_business_analyst", False, "EMP-00001")
        assert is_feature_enabled("ai_business_analyst") is False
        set_feature_enabled("ai_business_analyst", True, "EMP-00001")
        assert is_feature_enabled("ai_business_analyst") is True

    def test_writes_a_real_audit_log_event(self):
        set_feature_enabled("network_advisors", False, "EMP-00042", )
        events = audit_log.get_by_type("ai_feature_toggled")
        assert len(events) == 1
        event = events[0]
        assert event.actor == "EMP-00042"
        assert "Disabled" in event.summary
        assert "Network AI Advisors" in event.summary
        assert event.details["feature_key"] == "network_advisors"
        assert event.details["flag"] == "network_advisors_enabled"
        assert event.details["enabled"] is False

    def test_enabling_records_enabled_in_the_summary(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        set_feature_enabled("ai_assistant", True, "EMP-00001")
        events = audit_log.get_by_type("ai_feature_toggled")
        assert len(events) == 2
        assert "Enabled" in events[-1].summary

    def test_persists_across_a_fresh_read_of_system_config(self):
        set_feature_enabled("advertising_ai", False, "EMP-00001")
        config = system_config.get_system_config()
        assert config["feature_flags"]["ai_advertising_enabled"] is False

    def test_coerces_truthy_and_falsy_enabled_values_to_real_booleans(self):
        result = set_feature_enabled("ai_assistant", 1, "EMP-00001")
        assert result["enabled"] is True
        result = set_feature_enabled("ai_assistant", 0, "EMP-00001")
        assert result["enabled"] is False


# ---------------------------------------------------------------------------
# get_call_stats
# ---------------------------------------------------------------------------


class TestGetCallStats:
    def test_single_feature_returns_a_copy_not_the_live_dict(self):
        record_call_attempt("ai_assistant", "succeeded")
        snapshot = get_call_stats("ai_assistant")
        snapshot["attempted"] = 999
        assert _stats_for("ai_assistant")["attempted"] == 1

    def test_single_feature_with_no_activity_returns_default_shape(self):
        stats = get_call_stats("ai_assistant")
        assert stats["attempted"] == 0

    def test_all_features_returns_an_entry_for_every_catalog_key(self):
        all_stats = get_call_stats()
        assert set(all_stats.keys()) == set(_CATALOG_BY_KEY.keys())

    def test_all_features_reflects_real_recorded_activity(self):
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("email_sms_wizard", "fell_back")
        all_stats = get_call_stats()
        assert all_stats["ai_assistant"]["attempted"] == 1
        assert all_stats["email_sms_wizard"]["fell_back"] == 1
        assert all_stats["advertising_ai"]["attempted"] == 0


# ---------------------------------------------------------------------------
# build_ai_management_network_snapshot -- the Hub-facing, per-dealer,
# coarse/aggregate feature snapshot.
# ---------------------------------------------------------------------------


class TestBuildAiManagementNetworkSnapshot:
    def test_returns_one_entry_per_catalog_feature(self):
        snapshot = build_ai_management_network_snapshot()
        assert len(snapshot["features"]) == len(AI_FEATURE_CATALOG)
        assert {f["key"] for f in snapshot["features"]} == {e["key"] for e in AI_FEATURE_CATALOG}

    def test_each_feature_entry_only_carries_the_coarse_allowed_fields(self):
        snapshot = build_ai_management_network_snapshot()
        for feature in snapshot["features"]:
            assert set(feature.keys()) == {
                "key", "name", "enabled", "attempted", "succeeded", "fell_back", "blocked",
            }

    def test_deliberately_omits_last_detail_last_outcome_last_at(self):
        record_call_attempt("ai_assistant", "fell_back", detail="a secret-ish exception string")
        snapshot = build_ai_management_network_snapshot()
        entry = next(f for f in snapshot["features"] if f["key"] == "ai_assistant")
        assert "last_detail" not in entry
        assert "last_outcome" not in entry
        assert "last_at" not in entry

    def test_reflects_real_call_stats(self):
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("ai_assistant", "blocked")
        snapshot = build_ai_management_network_snapshot()
        entry = next(f for f in snapshot["features"] if f["key"] == "ai_assistant")
        assert entry["attempted"] == 3
        assert entry["succeeded"] == 2
        assert entry["blocked"] == 1
        assert entry["fell_back"] == 0

    def test_reflects_a_disabled_feature_flag(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        snapshot = build_ai_management_network_snapshot()
        entry = next(f for f in snapshot["features"] if f["key"] == "ai_assistant")
        assert entry["enabled"] is False

    def test_includes_submitted_at_and_a_real_note(self):
        snapshot = build_ai_management_network_snapshot()
        assert snapshot["submitted_at"]
        assert isinstance(snapshot["note"], str) and len(snapshot["note"]) > 0

    def test_snapshot_has_no_side_effects_on_call_stats(self):
        record_call_attempt("ai_assistant", "succeeded")
        build_ai_management_network_snapshot()
        build_ai_management_network_snapshot()
        assert get_call_stats("ai_assistant")["attempted"] == 1


# ---------------------------------------------------------------------------
# get_ai_management_overview -- the Administration Control Center's own
# AI Management screen payload.
# ---------------------------------------------------------------------------


class TestGetAiManagementOverview:
    def test_summary_total_features_matches_catalog_length(self):
        overview = get_ai_management_overview()
        assert overview["summary"]["total_features"] == len(AI_FEATURE_CATALOG)

    def test_enabled_and_disabled_counts_sum_to_total_when_all_default_enabled(self):
        overview = get_ai_management_overview()
        summary = overview["summary"]
        assert summary["enabled_count"] == len(AI_FEATURE_CATALOG)
        assert summary["disabled_count"] == 0

    def test_disabling_features_moves_them_from_enabled_to_disabled_count(self):
        set_feature_enabled("ai_assistant", False, "EMP-00001")
        set_feature_enabled("email_sms_wizard", False, "EMP-00001")
        overview = get_ai_management_overview()
        summary = overview["summary"]
        assert summary["enabled_count"] == len(AI_FEATURE_CATALOG) - 2
        assert summary["disabled_count"] == 2

    def test_features_with_recorded_activity_counts_only_features_with_attempts(self):
        record_call_attempt("ai_assistant", "succeeded")
        record_call_attempt("email_sms_wizard", "fell_back")
        overview = get_ai_management_overview()
        assert overview["summary"]["features_with_recorded_activity"] == 2

    def test_features_with_recorded_activity_is_zero_with_no_calls_yet(self):
        overview = get_ai_management_overview()
        assert overview["summary"]["features_with_recorded_activity"] == 0

    def test_features_missing_a_real_route_equals_one(self):
        # Only help_assistant is flagged as unwired in this catalog (see
        # this module's own docstring -- a real, deliberately-surfaced gap).
        overview = get_ai_management_overview()
        assert overview["summary"]["features_missing_a_real_route"] == 1

    def test_sandbox_network_note_is_present_and_matches_the_module_constant(self):
        overview = get_ai_management_overview()
        assert overview["sandbox_network_note"] == SANDBOX_NETWORK_NOTE

    def test_feature_entries_include_the_full_catalog_shape_plus_enabled_and_stats(self):
        overview = get_ai_management_overview()
        entry = next(f for f in overview["features"] if f["key"] == "ai_assistant")
        # every original catalog field survives...
        for k, v in _CATALOG_BY_KEY["ai_assistant"].items():
            assert entry[k] == v
        # ...plus the two computed fields.
        assert entry["enabled"] is True
        assert entry["stats"]["attempted"] == 0

    def test_feature_entry_stats_reflect_real_recorded_activity(self):
        record_call_attempt("ai_assistant", "succeeded")
        overview = get_ai_management_overview()
        entry = next(f for f in overview["features"] if f["key"] == "ai_assistant")
        assert entry["stats"]["attempted"] == 1
        assert entry["stats"]["succeeded"] == 1

    def test_accepts_an_optional_role_argument_without_using_it_for_gating(self):
        # get_ai_management_overview() itself does no ACL filtering -- that's
        # core/ai_management_api.py's job (this module intentionally accepts
        # `role=None` and ignores it, per its own signature).
        overview_no_role = get_ai_management_overview()
        overview_with_role = get_ai_management_overview(role="SALES")
        assert overview_no_role["summary"] == overview_with_role["summary"]
