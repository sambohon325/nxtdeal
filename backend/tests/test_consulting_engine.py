"""Tests for core/consulting_engine.py -- the AI Consulting Engine, the
strategic centerpiece that composes NXTDeal's own already-real analysis into a
four-part (Analysis / Root Cause / Opportunity / Action Plan) consultation --
plus its core/consulting_engine_api.py ACL layer.

Follows tests/test_customer_journey_ai.py's own established conventions
(fresh_ledger + no_real_persistence autouse fixtures, a _VIEW_ROLES constant,
class-grouped tests, direct asserts). This sandbox has no outbound network
access, so the AI happy-path test monkeypatches the isolated OpenAI client
(consulting_engine.client) with a fake returning valid four-part JSON, exercising
the real parse path deterministically; the disabled/malformed paths need no
client and lean on the real deterministic fallback.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger

from core import consulting_engine
from core import consulting_engine_api
from core import system_config
from core.system_config import set_feature_flag


_VIEW_ROLES = ("ADMIN", "OPERATIONS")

_SECTION_KEYS = {"analysis", "root_cause", "opportunity", "action_plan"}
_FULL_KEYS = _SECTION_KEYS | {"question", "department", "confidence_note", "sources", "ai_generated"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(consulting_engine, "save_graph", lambda filepath: None)
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _install_fake_client(monkeypatch, content):
    def _fake_create(*args, **kwargs):
        return _FakeCompletion(content)

    monkeypatch.setattr(
        consulting_engine.client.chat.completions, "create", _fake_create
    )


_VALID_MODEL_JSON = json.dumps({
    "analysis": "Service repair-order volume is trending below the peer average.",
    "root_cause": "Technician utilization and customer retention are the primary drivers.",
    "opportunity": "Closing the gap is worth an estimated six-figure annual opportunity.",
    "action_plan": [
        "Audit the recon checklist completion rate",
        "Launch a lapsed-customer service re-engagement campaign",
        "Rebalance technician workload to reduce overload",
    ],
    "confidence_note": "Grounded in this store's own real service KPIs.",
})


class TestRunConsultationHappyPath:

    def test_returns_the_parsed_structured_consultation(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        result = consulting_engine.run_consultation("Why are service sales down?", "ADMIN")

        assert _FULL_KEYS.issubset(result.keys())
        assert result["ai_generated"] is True
        assert result["analysis"] == "Service repair-order volume is trending below the peer average."
        assert result["root_cause"].startswith("Technician utilization")
        assert result["opportunity"].startswith("Closing the gap")
        assert isinstance(result["action_plan"], list)
        assert len(result["action_plan"]) == 3
        assert result["action_plan"][0] == "Audit the recon checklist completion rate"
        assert result["confidence_note"] == "Grounded in this store's own real service KPIs."
        assert result["sources"]

    def test_a_department_scoped_consultation_carries_the_department(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        result = consulting_engine.run_consultation(
            "Where are we behind?", "ADMIN", department="sales"
        )

        assert result["department"] == "sales"
        assert result["ai_generated"] is True

    def test_action_plan_items_are_coerced_to_strings(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, json.dumps({
            "analysis": "a", "root_cause": "b", "opportunity": "c",
            "action_plan": [1, "two", 3.0],
            "confidence_note": "n",
        }))

        result = consulting_engine.run_consultation("Any question?", "ADMIN")

        assert result["action_plan"] == ["1", "two", "3.0"]


class TestRunConsultationFeatureDisabled:

    def test_disabled_returns_a_real_four_part_fallback(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")

        result = consulting_engine.run_consultation("Why are service sales down?", "ADMIN")

        assert _FULL_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        # All four sections are present and non-empty even on an empty graph.
        assert isinstance(result["analysis"], str) and result["analysis"].strip()
        assert isinstance(result["root_cause"], str) and result["root_cause"].strip()
        assert isinstance(result["opportunity"], str) and result["opportunity"].strip()
        assert isinstance(result["action_plan"], list) and result["action_plan"]
        assert "disabled" in result["note"].lower()

    def test_disabled_fallback_is_grounded_in_the_same_real_facts(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")

        question = "Why is inventory readiness declining?"
        result = consulting_engine.run_consultation(question, "ADMIN")

        # The fallback analysis is exactly ai_business_analyst's own real,
        # topic-matched answer over the same gathered facts -- not invented here.
        facts = consulting_engine._gather("ADMIN", None)
        expected_analysis = consulting_engine._section_analysis(question, facts)
        assert result["analysis"] == expected_analysis


class TestRunConsultationMalformedOutput:

    def test_malformed_json_falls_back(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, "this is not valid json {oops")

        result = consulting_engine.run_consultation("Why are service sales down?", "ADMIN")

        assert result["ai_generated"] is False
        assert _SECTION_KEYS.issubset(result.keys())
        assert "unavailable" in result["note"].lower()

    def test_missing_section_falls_back(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        # Valid JSON, but no action_plan array -> not a usable consultation.
        _install_fake_client(monkeypatch, json.dumps({
            "analysis": "a", "root_cause": "b", "opportunity": "c",
        }))

        result = consulting_engine.run_consultation("Why are service sales down?", "ADMIN")

        assert result["ai_generated"] is False
        assert isinstance(result["action_plan"], list) and result["action_plan"]

    def test_empty_action_plan_array_falls_back(self, monkeypatch):
        set_feature_flag("ai_consulting_engine_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, json.dumps({
            "analysis": "a", "root_cause": "b", "opportunity": "c",
            "action_plan": [], "confidence_note": "n",
        }))

        result = consulting_engine.run_consultation("Why are service sales down?", "ADMIN")

        assert result["ai_generated"] is False


class TestRunConsultationValidation:

    def test_empty_question_is_rejected(self):
        result = consulting_engine.run_consultation("   ", "ADMIN")
        assert result["error"] == "Ask a business question first."

    def test_unknown_department_is_rejected(self):
        result = consulting_engine.run_consultation("A question?", "ADMIN", department="bogus")
        assert "Unknown department" in result["error"]


class TestSparseDataGraceful:

    def test_every_section_is_non_empty_on_a_completely_empty_graph(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")

        for department in (None, "sales", "service", "fi", "bhph", "parts"):
            result = consulting_engine.run_consultation("What should we do?", "ADMIN", department=department)
            assert result["analysis"].strip()
            assert result["root_cause"].strip()
            assert result["opportunity"].strip()
            assert result["action_plan"]


class TestGetConsultingOverview:

    def test_overview_shape(self):
        overview = consulting_engine.get_consulting_overview("ADMIN")

        assert set(overview.keys()) == {
            "starter_questions", "departments_available", "data_sources",
            "recent_consultations", "note",
        }
        assert overview["starter_questions"]
        assert overview["departments_available"] == list(consulting_engine.ADVISOR_DEPARTMENTS)
        assert "readiness_recommendations_present" in overview["data_sources"]
        assert "network_opportunity_present" in overview["data_sources"]
        assert isinstance(overview["recent_consultations"], list)

    def test_overview_lists_recent_consultations(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")
        consulting_engine.run_consultation("Q1?", "ADMIN")
        consulting_engine.run_consultation("Q2?", "ADMIN")

        overview = consulting_engine.get_consulting_overview("ADMIN")
        questions = [c["question"] for c in overview["recent_consultations"]]
        assert "Q1?" in questions
        assert "Q2?" in questions


class TestApiRoleGating:

    def test_every_view_role_can_run_a_consultation(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")
        for role in _VIEW_ROLES:
            result = consulting_engine_api.run_consultation_api(role, "Why are sales down?")
            assert "error" not in result
            assert result["ai_generated"] is False

    def test_a_non_executive_role_is_denied(self):
        set_feature_flag("ai_consulting_engine_enabled", False, "EMP-TEST")
        for role in ("SALES", "MARKETING", "SERVICE", "FINANCE", "BOGUS"):
            result = consulting_engine_api.run_consultation_api(role, "Why are sales down?")
            assert "error" in result

    def test_overview_api_role_gating(self):
        assert "error" not in consulting_engine_api.get_consulting_overview_api("ADMIN")
        assert "error" in consulting_engine_api.get_consulting_overview_api("SALES")

    def test_api_surfaces_a_validation_error(self):
        result = consulting_engine_api.run_consultation_api("ADMIN", "  ")
        assert result["error"] == "Ask a business question first."

    def test_api_surfaces_an_unknown_department_error(self):
        result = consulting_engine_api.run_consultation_api("ADMIN", "A question?", department="nope")
        assert "Unknown department" in result["error"]
