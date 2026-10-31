"""Tests for core/success_center.py -- the NXTDeal-INTERNAL client-success /
account-management platform (dealer accounts as first-class graph entities, with
graph-native QBR / objective / initiative / recommendation linked-entity
records), plus its core/success_center_api.py ACL layer and the isolated-OpenAI-
backed generate_qbr_insights().

Follows tests/test_customer_journey.py's / tests/test_customer_journey_ai.py's
own established conventions (fresh_ledger + no_real_persistence autouse fixtures,
a _VIEW_ROLES constant, class-grouped tests, direct asserts, no per-test
docstrings) so the suite never touches real storage. This sandbox has no
outbound network access, so -- like the customer-journey AI tests -- the AI
happy-path test monkeypatches the isolated OpenAI client with a fake returning a
valid JSON completion; the disabled/malformed/unknown-dealer paths need no
network at all.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import success_center
from core import success_center_api


# Success Center is NXTDeal-internal -- only ADMIN + OPERATIONS may view/act.
_VIEW_ROLES = (ADMIN, OPERATIONS)
_DENIED_ROLES = (SALES, MARKETING, SERVICE, FINANCE, "BOGUS")

_INSIGHTS_KEYS = {"summary", "talking_points", "suggested_focus"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(success_center, "save_graph", lambda filepath: None)


def _new_dealer(name="Riverside Motors"):
    return success_center.create_dealer(name)["dealer_id"]


# ---------------------------------------------------------------------------
# Fake OpenAI client plumbing (mirrors tests/test_customer_journey_ai.py).
# ---------------------------------------------------------------------------

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

    monkeypatch.setattr(success_center.client.chat.completions, "create", _fake_create)


_VALID_MODEL_JSON = json.dumps({
    "summary": "Riverside Motors is progressing on its Q3 objectives.",
    "talking_points": [
        "Review the CRM adoption objective",
        "Confirm the GPS rollout initiative timeline",
    ],
    "suggested_focus": "Resolve the high-priority training gap.",
})


# ---------------------------------------------------------------------------
# Dealer accounts.
# ---------------------------------------------------------------------------

class TestDealers:

    def test_create_dealer_returns_a_brief_with_an_sdlr_id(self):
        brief = success_center.create_dealer("Riverside Motors", notes="key account")
        assert brief["dealer_id"].startswith("SDLR-")
        assert brief["name"] == "Riverside Motors"
        assert brief["notes"] == "key account"

    def test_create_dealer_persists_a_success_dealer_entity(self):
        dealer_id = _new_dealer()
        entity = ledger.get_entity(dealer_id)
        assert entity.entity_type == success_center.DEALER

    def test_create_dealer_rejects_an_empty_name(self):
        with pytest.raises(ValueError):
            success_center.create_dealer("   ")

    def test_list_dealers_returns_every_created_account(self):
        _new_dealer("Alpha Auto")
        _new_dealer("Beta Cars")
        names = sorted(d["name"] for d in success_center.list_dealers())
        assert names == ["Alpha Auto", "Beta Cars"]

    def test_list_dealers_is_empty_when_none_exist(self):
        assert success_center.list_dealers() == []


# ---------------------------------------------------------------------------
# QBRs.
# ---------------------------------------------------------------------------

class TestQBRs:

    def test_create_qbr_records_the_period_and_notes(self):
        dealer_id = _new_dealer()
        qbr = success_center.create_qbr(dealer_id, "Q3 2026", notes="strong quarter")
        assert qbr["period"] == "Q3 2026"
        assert qbr["notes"] == "strong quarter"
        assert qbr["dealer_id"] == dealer_id
        assert ledger.get_entity(qbr["id"]).entity_type == success_center.QBR

    def test_create_qbr_rejects_an_unknown_dealer(self):
        with pytest.raises(ValueError) as exc:
            success_center.create_qbr("SDLR-NOPE", "Q3 2026")
        assert str(exc.value) == "No dealer account found with id SDLR-NOPE."

    def test_create_qbr_rejects_an_empty_period(self):
        dealer_id = _new_dealer()
        with pytest.raises(ValueError):
            success_center.create_qbr(dealer_id, "")


# ---------------------------------------------------------------------------
# Objectives & initiatives.
# ---------------------------------------------------------------------------

class TestObjectives:

    def test_add_objective_and_it_shows_in_the_overview(self):
        dealer_id = _new_dealer()
        obj = success_center.add_objective(dealer_id, "Grow CRM adoption", target="80% of reps")
        assert obj["title"] == "Grow CRM adoption"
        assert obj["target"] == "80% of reps"
        overview = success_center.get_success_overview(dealer_id)
        assert overview["objectives_count"] == 1
        assert overview["objectives"][0]["title"] == "Grow CRM adoption"

    def test_add_objective_rejects_unknown_dealer(self):
        with pytest.raises(ValueError):
            success_center.add_objective("SDLR-NOPE", "x")

    def test_add_objective_rejects_empty_title(self):
        dealer_id = _new_dealer()
        with pytest.raises(ValueError):
            success_center.add_objective(dealer_id, "")


class TestInitiatives:

    def test_add_initiative_defaults_to_planned(self):
        dealer_id = _new_dealer()
        init = success_center.add_initiative(dealer_id, "GPS Rollout")
        assert init["status"] == "planned"

    def test_add_initiative_accepts_a_valid_status(self):
        dealer_id = _new_dealer()
        init = success_center.add_initiative(dealer_id, "Website Launch", status="in_progress")
        assert init["status"] == "in_progress"

    def test_add_initiative_rejects_an_invalid_status(self):
        dealer_id = _new_dealer()
        with pytest.raises(ValueError) as exc:
            success_center.add_initiative(dealer_id, "X", status="wishful")
        assert "Invalid initiative status" in str(exc.value)

    def test_initiatives_counted_by_status_in_overview(self):
        dealer_id = _new_dealer()
        success_center.add_initiative(dealer_id, "A", status="planned")
        success_center.add_initiative(dealer_id, "B", status="in_progress")
        success_center.add_initiative(dealer_id, "C", status="in_progress")
        overview = success_center.get_success_overview(dealer_id)
        assert overview["initiatives_by_status"]["planned"] == 1
        assert overview["initiatives_by_status"]["in_progress"] == 2
        assert overview["initiatives_by_status"]["completed"] == 0
        assert overview["initiatives_count"] == 3


# ---------------------------------------------------------------------------
# Recommendations.
# ---------------------------------------------------------------------------

class TestRecommendations:

    def test_add_recommendation_defaults_to_medium_and_open(self):
        dealer_id = _new_dealer()
        rec = success_center.add_recommendation(dealer_id, "Enable auto-drafts")
        assert rec["priority"] == "medium"
        assert rec["status"] == success_center.REC_OPEN

    def test_add_recommendation_rejects_invalid_priority(self):
        dealer_id = _new_dealer()
        with pytest.raises(ValueError) as exc:
            success_center.add_recommendation(dealer_id, "x", priority="urgent")
        assert "Invalid priority" in str(exc.value)

    def test_list_open_recommendations_returns_only_open_ones(self):
        dealer_id = _new_dealer()
        r1 = success_center.add_recommendation(dealer_id, "one", priority="high")
        success_center.add_recommendation(dealer_id, "two", priority="low")
        success_center.resolve_recommendation(dealer_id, r1["id"], resolved_by="EMP-1")
        open_recs = success_center.list_open_recommendations(dealer_id)
        assert len(open_recs) == 1
        assert open_recs[0]["text"] == "two"

    def test_resolve_recommendation_marks_it_resolved(self):
        dealer_id = _new_dealer()
        rec = success_center.add_recommendation(dealer_id, "fix it", priority="high")
        resolved = success_center.resolve_recommendation(dealer_id, rec["id"], resolved_by="EMP-9")
        assert resolved["status"] == success_center.REC_RESOLVED
        assert resolved["resolved_by"] == "EMP-9"
        assert resolved["resolved_at"] is not None

    def test_resolve_rejects_unknown_recommendation(self):
        dealer_id = _new_dealer()
        with pytest.raises(ValueError) as exc:
            success_center.resolve_recommendation(dealer_id, "SCREC-NOPE")
        assert str(exc.value) == f"No recommendation found with id SCREC-NOPE for dealer {dealer_id}."

    def test_resolve_rejects_a_rec_from_a_different_dealer(self):
        dealer_a = _new_dealer("A")
        dealer_b = _new_dealer("B")
        rec = success_center.add_recommendation(dealer_a, "for A", priority="high")
        with pytest.raises(ValueError):
            success_center.resolve_recommendation(dealer_b, rec["id"])

    def test_resolve_rejects_an_already_resolved_recommendation(self):
        dealer_id = _new_dealer()
        rec = success_center.add_recommendation(dealer_id, "once", priority="low")
        success_center.resolve_recommendation(dealer_id, rec["id"])
        with pytest.raises(ValueError) as exc:
            success_center.resolve_recommendation(dealer_id, rec["id"])
        assert "already resolved" in str(exc.value)

    def test_open_recommendations_counted_by_priority_in_overview(self):
        dealer_id = _new_dealer()
        success_center.add_recommendation(dealer_id, "h1", priority="high")
        success_center.add_recommendation(dealer_id, "h2", priority="high")
        success_center.add_recommendation(dealer_id, "m1", priority="medium")
        resolved = success_center.add_recommendation(dealer_id, "l1", priority="low")
        success_center.resolve_recommendation(dealer_id, resolved["id"])
        overview = success_center.get_success_overview(dealer_id)
        by_priority = overview["open_recommendations_by_priority"]
        assert by_priority == {"high": 2, "medium": 1, "low": 0}
        assert overview["open_recommendations_total"] == 3

    def test_list_open_recommendations_rejects_unknown_dealer(self):
        with pytest.raises(ValueError):
            success_center.list_open_recommendations("SDLR-NOPE")


# ---------------------------------------------------------------------------
# Overview.
# ---------------------------------------------------------------------------

class TestOverview:

    def test_overview_shape_for_a_fresh_dealer(self):
        dealer_id = _new_dealer("Fresh Motors")
        overview = success_center.get_success_overview(dealer_id)
        assert overview["dealer_id"] == dealer_id
        assert overview["name"] == "Fresh Motors"
        assert overview["open_recommendations_by_priority"] == {"high": 0, "medium": 0, "low": 0}
        assert overview["open_recommendations_total"] == 0
        assert overview["objectives"] == []
        assert overview["latest_qbr"] is None
        assert overview["upcoming_qbr"] is None
        assert overview["qbr_count"] == 0

    def test_overview_latest_qbr_is_the_most_recent(self):
        dealer_id = _new_dealer()
        success_center.create_qbr(dealer_id, "Q2 2026")
        success_center.create_qbr(dealer_id, "Q3 2026")
        overview = success_center.get_success_overview(dealer_id)
        assert overview["qbr_count"] == 2
        assert overview["latest_qbr"]["period"] == "Q3 2026"

    def test_overview_rejects_unknown_dealer(self):
        with pytest.raises(ValueError) as exc:
            success_center.get_success_overview("SDLR-NOPE")
        assert str(exc.value) == "No dealer account found with id SDLR-NOPE."


# ---------------------------------------------------------------------------
# QBR Insights AI.
# ---------------------------------------------------------------------------

class TestGenerateQBRInsightsHappyPath:

    def test_returns_the_parsed_structured_insights(self, monkeypatch):
        dealer_id = _new_dealer()
        success_center.add_objective(dealer_id, "Grow CRM adoption")
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        result = success_center.generate_qbr_insights(dealer_id)

        assert _INSIGHTS_KEYS.issubset(result.keys())
        assert result["ai_generated"] is True
        assert result["talking_points"] == [
            "Review the CRM adoption objective",
            "Confirm the GPS rollout initiative timeline",
        ]
        assert "disabled" not in result
        assert "fallback_reason" not in result

    def test_success_is_stored_onto_the_dealer_entity(self, monkeypatch):
        dealer_id = _new_dealer()
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        success_center.generate_qbr_insights(dealer_id)

        stored = ledger.get_entity(dealer_id).attributes["qbr_insights"]
        assert stored["ai_generated"] is True
        assert stored["summary"].startswith("Riverside Motors")

    def test_missing_model_keys_default_to_empty_never_invented(self, monkeypatch):
        dealer_id = _new_dealer()
        _install_fake_client(monkeypatch, json.dumps({"summary": "just a summary"}))

        result = success_center.generate_qbr_insights(dealer_id)

        assert result["summary"] == "just a summary"
        assert result["talking_points"] == []
        assert result["suggested_focus"] == ""
        assert result["ai_generated"] is True


class TestGenerateQBRInsightsDisabled:

    def test_returns_an_honest_disabled_fallback(self, monkeypatch):
        dealer_id = _new_dealer()
        success_center.add_recommendation(dealer_id, "training gap", priority="high")
        monkeypatch.setattr(success_center, "is_feature_enabled", lambda key: False)

        result = success_center.generate_qbr_insights(dealer_id)

        assert _INSIGHTS_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert result["disabled"] is True
        # Fallback is grounded in the real open recommendation, never invented.
        assert any("recommendation" in tp for tp in result["talking_points"])

    def test_a_disabled_result_is_not_persisted(self, monkeypatch):
        dealer_id = _new_dealer()
        monkeypatch.setattr(success_center, "is_feature_enabled", lambda key: False)

        success_center.generate_qbr_insights(dealer_id)

        assert "qbr_insights" not in ledger.get_entity(dealer_id).attributes


class TestGenerateQBRInsightsMalformedOutput:

    def test_malformed_output_falls_back_with_a_reason(self, monkeypatch):
        dealer_id = _new_dealer()
        success_center.add_initiative(dealer_id, "GPS Rollout")
        _install_fake_client(monkeypatch, "this is not valid json {oops")

        result = success_center.generate_qbr_insights(dealer_id)

        assert _INSIGHTS_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert "disabled" not in result
        assert result["fallback_reason"]

    def test_a_failed_result_is_not_persisted(self, monkeypatch):
        dealer_id = _new_dealer()
        _install_fake_client(monkeypatch, "not json")

        success_center.generate_qbr_insights(dealer_id)

        assert "qbr_insights" not in ledger.get_entity(dealer_id).attributes


class TestGenerateQBRInsightsUnknownDealer:

    def test_unknown_dealer_raises(self):
        with pytest.raises(ValueError) as exc:
            success_center.generate_qbr_insights("SDLR-404")
        assert str(exc.value) == "No dealer account found with id SDLR-404."


# ---------------------------------------------------------------------------
# ACL layer (ADMIN + OPERATIONS only).
# ---------------------------------------------------------------------------

class TestSuccessCenterApiRoleGating:

    def test_view_roles_can_list_dealers(self):
        _new_dealer()
        for role in _VIEW_ROLES:
            result = success_center_api.list_dealers_api(role)
            assert isinstance(result, list)

    def test_denied_roles_cannot_list_dealers(self):
        for role in _DENIED_ROLES:
            result = success_center_api.list_dealers_api(role)
            assert "error" in result

    def test_view_roles_can_view_overview(self):
        dealer_id = _new_dealer()
        for role in _VIEW_ROLES:
            result = success_center_api.get_success_overview_api(role, dealer_id)
            assert "error" not in result

    def test_denied_roles_cannot_view_overview(self):
        dealer_id = _new_dealer()
        for role in _DENIED_ROLES:
            result = success_center_api.get_success_overview_api(role, dealer_id)
            assert "error" in result

    def test_view_roles_can_add_records(self):
        dealer_id = _new_dealer()
        for role in _VIEW_ROLES:
            assert "error" not in success_center_api.create_qbr_api(role, dealer_id, "Q3 2026")
            assert "error" not in success_center_api.add_objective_api(role, dealer_id, "obj")
            assert "error" not in success_center_api.add_initiative_api(role, dealer_id, "init")
            assert "error" not in success_center_api.add_recommendation_api(role, dealer_id, "rec")

    def test_denied_roles_cannot_add_records(self):
        dealer_id = _new_dealer()
        for role in _DENIED_ROLES:
            assert "error" in success_center_api.create_qbr_api(role, dealer_id, "Q3 2026")
            assert "error" in success_center_api.add_recommendation_api(role, dealer_id, "rec")

    def test_view_roles_can_resolve_a_recommendation(self):
        dealer_id = _new_dealer()
        rec = success_center.add_recommendation(dealer_id, "fix", priority="high")
        result = success_center_api.resolve_recommendation_api(ADMIN, dealer_id, rec["id"], resolved_by="EMP-1")
        assert result["status"] == success_center.REC_RESOLVED

    def test_denied_role_cannot_resolve(self):
        dealer_id = _new_dealer()
        rec = success_center.add_recommendation(dealer_id, "fix", priority="high")
        result = success_center_api.resolve_recommendation_api(SALES, dealer_id, rec["id"])
        assert "error" in result

    def test_view_roles_can_generate_insights(self, monkeypatch):
        dealer_id = _new_dealer()
        monkeypatch.setattr(success_center, "is_feature_enabled", lambda key: False)
        for role in _VIEW_ROLES:
            result = success_center_api.generate_qbr_insights_api(role, dealer_id)
            assert "error" not in result
            assert result["ai_generated"] is False

    def test_denied_role_cannot_generate_insights(self):
        dealer_id = _new_dealer()
        result = success_center_api.generate_qbr_insights_api("BOGUS", dealer_id)
        assert "error" in result


class TestSuccessCenterApiErrorsSurface:

    def test_unknown_dealer_error_surfaces_through_the_api(self):
        result = success_center_api.get_success_overview_api(ADMIN, "SDLR-NOPE")
        assert result["error"] == "No dealer account found with id SDLR-NOPE."

    def test_unknown_recommendation_error_surfaces_through_the_api(self):
        dealer_id = _new_dealer()
        result = success_center_api.resolve_recommendation_api(ADMIN, dealer_id, "SCREC-NOPE")
        assert "error" in result
        assert "No recommendation found" in result["error"]

    def test_invalid_initiative_status_surfaces_through_the_api(self):
        dealer_id = _new_dealer()
        result = success_center_api.add_initiative_api(ADMIN, dealer_id, "x", status="bad")
        assert "error" in result
        assert "Invalid initiative status" in result["error"]
