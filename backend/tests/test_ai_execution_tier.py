"""
Tests for core/ai_execution_tier.py and core/ai_execution_tier_api.py --
security-hardening pass, Task #8 "AI execution-tier framework
(Informational/Assisted/Autonomous)". Closes a real, confirmed
zero-coverage gap flagged by the Code Auditor's own CAF-00123 finding --
prior to this file, `ai_execution_tier` was only ever mentioned in a single
comment inside tests/test_workflow_automation.py, never actually exercised.

Both modules under test are pure, dependency-light, no-mutation composition/
ACL layers (confirmed via reading their own module docstrings: "Nothing here
makes an OpenAI call, mutates the graph, or has any side effect at all") --
no ledger/storage isolation concerns apply here the way they do for most of
this codebase's other test files, so no fixture is needed beyond the
standard sys.path bootstrap every test file in this suite uses.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import ai_execution_tier
from core.ai_execution_tier import (
    TIER_INFORMATIONAL,
    TIER_ASSISTED,
    TIER_AUTONOMOUS,
    EXECUTION_TIERS,
    TIER_DESCRIPTIONS,
    FEATURE_EXECUTION_TIERS,
    get_execution_tier,
    requires_approval_chain,
    list_execution_tier_catalog,
    get_execution_tier_summary,
)
from core import ai_execution_tier_api
from core.ai_management import AI_FEATURE_CATALOG
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:

    def test_three_tiers_defined(self):
        assert EXECUTION_TIERS == (TIER_INFORMATIONAL, TIER_ASSISTED, TIER_AUTONOMOUS)

    def test_tier_values_are_the_expected_literal_strings(self):
        assert TIER_INFORMATIONAL == "informational"
        assert TIER_ASSISTED == "assisted"
        assert TIER_AUTONOMOUS == "autonomous"

    def test_every_tier_has_a_real_description(self):
        for tier in EXECUTION_TIERS:
            assert tier in TIER_DESCRIPTIONS
            assert isinstance(TIER_DESCRIPTIONS[tier], str)
            assert len(TIER_DESCRIPTIONS[tier]) > 10

    def test_autonomous_description_mentions_approval_chain(self):
        assert "Approval Chain" in TIER_DESCRIPTIONS[TIER_AUTONOMOUS]


# ---------------------------------------------------------------------------
# get_execution_tier() -- the fail-safe lookup
# ---------------------------------------------------------------------------


class TestGetExecutionTier:

    def test_every_real_ai_feature_catalog_key_has_an_explicit_classification(self):
        # This is the load-bearing honesty check for the whole module: every
        # one of core.ai_management's 13 real AI features must have been
        # individually reasoned about, not silently defaulted.
        for entry in AI_FEATURE_CATALOG:
            key = entry["key"]
            assert key in FEATURE_EXECUTION_TIERS, (
                f"AI_FEATURE_CATALOG key {key!r} has no explicit execution-tier "
                f"classification -- it would silently fall through to the "
                f"fail-safe Autonomous default."
            )

    def test_known_informational_feature_resolves_correctly(self):
        result = get_execution_tier("ai_assistant")

        assert result["tier"] == TIER_INFORMATIONAL
        assert "read-only" in result["rationale"].lower()

    def test_known_assisted_feature_resolves_correctly(self):
        result = get_execution_tier("email_sms_wizard")

        assert result["tier"] == TIER_ASSISTED
        assert "draft" in result["rationale"].lower()

    def test_known_autonomous_feature_resolves_correctly(self):
        result = get_execution_tier("reputation_autorespond")

        assert result["tier"] == TIER_AUTONOMOUS

    def test_non_catalog_autonomous_surface_workflow_automation_resolves(self):
        result = get_execution_tier("workflow_automation_rule_engine")

        assert result["tier"] == TIER_AUTONOMOUS
        assert "Approval Chain" in result["rationale"]

    def test_non_catalog_autonomous_surface_bot_auto_touch_resolves(self):
        result = get_execution_tier("bot_auto_touch_overdue_leads")

        assert result["tier"] == TIER_AUTONOMOUS

    def test_unknown_feature_key_fails_safe_to_autonomous(self):
        result = get_execution_tier("some_feature_that_does_not_exist")

        assert result["tier"] == TIER_AUTONOMOUS
        assert "no real classification" in result["rationale"].lower()

    def test_unknown_feature_key_never_silently_resolves_to_a_weaker_tier(self):
        # The whole point of a fail-safe default is that an unrecognized
        # surface is treated as maximally dangerous, never assumed safe.
        for bogus_key in ("", "typo_key", "DROP TABLE features", None):
            result = get_execution_tier(bogus_key)
            assert result["tier"] == TIER_AUTONOMOUS

    def test_returned_dict_is_a_copy_not_a_live_reference_into_the_catalog(self):
        result = get_execution_tier("ai_assistant")
        result["tier"] = "mutated"

        # Mutating the returned dict must never corrupt the real, shared
        # module-level FEATURE_EXECUTION_TIERS catalog for subsequent callers.
        second_result = get_execution_tier("ai_assistant")
        assert second_result["tier"] == TIER_INFORMATIONAL

    def test_returned_shape_has_exactly_tier_and_rationale_keys(self):
        result = get_execution_tier("ai_assistant")

        assert set(result.keys()) == {"tier", "rationale"}


# ---------------------------------------------------------------------------
# requires_approval_chain()
# ---------------------------------------------------------------------------


class TestRequiresApprovalChain:

    def test_autonomous_requires_approval_chain(self):
        assert requires_approval_chain(TIER_AUTONOMOUS) is True

    def test_informational_does_not_require_approval_chain(self):
        assert requires_approval_chain(TIER_INFORMATIONAL) is False

    def test_assisted_does_not_require_approval_chain(self):
        assert requires_approval_chain(TIER_ASSISTED) is False

    def test_an_unrecognized_tier_string_does_not_require_approval_chain(self):
        # requires_approval_chain() is a pure string-equality check against
        # the literal Autonomous constant -- it does not itself fail-safe
        # for a garbage tier value (that responsibility belongs entirely to
        # get_execution_tier()'s own fail-safe default, not this function).
        assert requires_approval_chain("not_a_real_tier") is False

    def test_composes_correctly_with_get_execution_tier_for_every_real_feature(self):
        for entry in AI_FEATURE_CATALOG:
            tier_info = get_execution_tier(entry["key"])
            expected = tier_info["tier"] == TIER_AUTONOMOUS
            assert requires_approval_chain(tier_info["tier"]) == expected


# ---------------------------------------------------------------------------
# list_execution_tier_catalog()
# ---------------------------------------------------------------------------


class TestListExecutionTierCatalog:

    def test_returns_all_13_catalog_features_plus_2_non_catalog_surfaces(self):
        catalog = list_execution_tier_catalog()

        assert len(catalog) == len(AI_FEATURE_CATALOG) + 2

    def test_every_entry_carries_a_real_execution_tier_and_rationale(self):
        catalog = list_execution_tier_catalog()

        for entry in catalog:
            assert "execution_tier" in entry
            assert entry["execution_tier"] in EXECUTION_TIERS
            assert "execution_tier_rationale" in entry
            assert isinstance(entry["execution_tier_rationale"], str)
            assert len(entry["execution_tier_rationale"]) > 0

    def test_every_real_ai_feature_catalog_entrys_own_fields_are_preserved(self):
        catalog = list_execution_tier_catalog()
        by_key = {e["key"]: e for e in catalog}

        for original in AI_FEATURE_CATALOG:
            merged = by_key[original["key"]]
            for field, value in original.items():
                assert merged[field] == value

    def test_non_catalog_surfaces_are_present_by_key(self):
        catalog = list_execution_tier_catalog()
        keys = {e["key"] for e in catalog}

        assert "workflow_automation_rule_engine" in keys
        assert "bot_auto_touch_overdue_leads" in keys

    def test_workflow_automation_entry_has_its_own_real_fields(self):
        catalog = list_execution_tier_catalog()
        entry = next(e for e in catalog if e["key"] == "workflow_automation_rule_engine")

        assert entry["module"] == "core/workflow_automation.py"
        assert "evaluate_rules" in entry["functions"]
        assert entry["wired_route"] is True
        assert entry["execution_tier"] == TIER_AUTONOMOUS

    def test_bot_auto_touch_entry_has_its_own_real_fields(self):
        catalog = list_execution_tier_catalog()
        entry = next(e for e in catalog if e["key"] == "bot_auto_touch_overdue_leads")

        assert entry["module"] == "core/bot_actions.py"
        assert entry["wired_route"] is True
        assert entry["execution_tier"] == TIER_AUTONOMOUS

    def test_calling_it_twice_produces_independently_mutable_results(self):
        first = list_execution_tier_catalog()
        first[0]["execution_tier"] = "corrupted"

        second = list_execution_tier_catalog()

        assert second[0]["execution_tier"] != "corrupted"

    def test_no_duplicate_keys_in_the_merged_catalog(self):
        catalog = list_execution_tier_catalog()
        keys = [e["key"] for e in catalog]

        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# get_execution_tier_summary()
# ---------------------------------------------------------------------------


class TestGetExecutionTierSummary:

    def test_total_matches_the_full_catalog_length(self):
        summary = get_execution_tier_summary()
        catalog = list_execution_tier_catalog()

        assert summary["total"] == len(catalog)

    def test_by_tier_counts_sum_to_the_total(self):
        summary = get_execution_tier_summary()

        assert sum(summary["by_tier"].values()) == summary["total"]

    def test_by_tier_has_an_entry_for_every_real_tier(self):
        summary = get_execution_tier_summary()

        for tier in EXECUTION_TIERS:
            assert tier in summary["by_tier"]

    def test_autonomous_requiring_approval_matches_the_autonomous_count(self):
        summary = get_execution_tier_summary()

        assert summary["autonomous_requiring_approval"] == summary["by_tier"][TIER_AUTONOMOUS]

    def test_autonomous_count_is_at_least_the_two_named_flagship_surfaces(self):
        # reputation_autorespond, website_ai_receptionist,
        # workflow_automation_rule_engine, and bot_auto_touch_overdue_leads
        # are all real, individually-documented Autonomous entries -- the
        # count should never silently drop below what this module's own
        # docstring claims exists.
        summary = get_execution_tier_summary()

        assert summary["by_tier"][TIER_AUTONOMOUS] >= 4

    def test_summary_is_recomputed_fresh_not_cached_stale(self):
        first = get_execution_tier_summary()
        second = get_execution_tier_summary()

        assert first == second
        # Independently mutable -- not the same dict object / not sharing
        # nested mutable state across calls.
        first["total"] = -999
        third = get_execution_tier_summary()
        assert third["total"] != -999


# ---------------------------------------------------------------------------
# core/ai_execution_tier_api.py -- ACL layer
# ---------------------------------------------------------------------------


_ALLOWED_ROLES = (ADMIN, OPERATIONS)
_DENIED_ROLES = (SALES, MARKETING, SERVICE, FINANCE, "BOGUS_ROLE", None)


class TestGetExecutionTierOverviewApi:

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_allowed_roles_get_the_real_overview(self, role):
        result = ai_execution_tier_api.get_execution_tier_overview_api(role)

        assert "error" not in result
        assert result["tiers"] == list(EXECUTION_TIERS)
        assert result["tier_descriptions"] == TIER_DESCRIPTIONS
        assert "summary" in result
        assert "catalog" in result
        assert len(result["catalog"]) == len(AI_FEATURE_CATALOG) + 2

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_denied_roles_get_a_real_error_not_partial_data(self, role):
        result = ai_execution_tier_api.get_execution_tier_overview_api(role)

        assert result == {"error": "Admin/Operations role required."}
        assert "catalog" not in result
        assert "summary" not in result


class TestGetExecutionTierForFeatureApi:

    @pytest.mark.parametrize("role", _ALLOWED_ROLES)
    def test_allowed_roles_get_the_real_classification(self, role):
        result = ai_execution_tier_api.get_execution_tier_for_feature_api(
            role, "reputation_autorespond"
        )

        assert result["feature_key"] == "reputation_autorespond"
        assert result["tier"] == TIER_AUTONOMOUS
        assert "rationale" in result

    @pytest.mark.parametrize("role", _DENIED_ROLES)
    def test_denied_roles_get_a_real_error(self, role):
        result = ai_execution_tier_api.get_execution_tier_for_feature_api(
            role, "reputation_autorespond"
        )

        assert result == {"error": "Admin/Operations role required."}

    def test_an_allowed_role_looking_up_an_unknown_feature_still_fails_safe(self):
        result = ai_execution_tier_api.get_execution_tier_for_feature_api(
            ADMIN, "totally_made_up_feature"
        )

        assert result["tier"] == TIER_AUTONOMOUS
        assert result["feature_key"] == "totally_made_up_feature"
