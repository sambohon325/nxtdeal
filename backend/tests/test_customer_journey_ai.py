"""Tests for core/customer_journey.py's slice-2 AI Journey Recommendation --
the real, isolated-OpenAI-backed generate_journey_recommendation() (a next-best-
action recommendation grounded strictly in a customer's current journey stage +
history) plus its core/customer_journey_api.py ACL layer.

Follows tests/test_customer_journey.py's / tests/test_communications_hub.py's own
established conventions (fresh_ledger + no_real_persistence autouse fixtures, a
_VIEW_ROLES constant, class-grouped tests, direct asserts, no per-test
docstrings). This sandbox has no outbound network access, so -- unlike the
comms-hub summary tests, which lean on the real fallback path -- the happy-path
test here monkeypatches the isolated OpenAI client (customer_journey.client) with
a fake that returns a valid JSON completion, so the real parse-and-store path is
exercised deterministically without hitting the network. The disabled/error/
unknown-customer paths need no client at all.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import customer_journey
from core import customer_journey_api
from core import system_config
from core.system_config import set_feature_flag


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

_RECOMMENDATION_KEYS = {"recommended_action", "reason", "suggested_timing", "suggested_campaign"}


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(customer_journey, "save_graph", lambda filepath: None)
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", first="Jamie", last="Buyer"):
    customer = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    )
    ledger.add_entity(customer)
    return customer


def _add_lead(lead_id="LEAD-1", name="Jordan Prospect"):
    lead = Entity(id=lead_id, entity_type=LEAD, attributes={"Name": name})
    ledger.add_entity(lead)
    return lead


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
    """Monkeypatch customer_journey.client.chat.completions.create to return a
    canned completion whose message content is `content` (a raw string), so the
    real json.loads/parse/store path runs without any network call."""

    def _fake_create(*args, **kwargs):
        return _FakeCompletion(content)

    monkeypatch.setattr(
        customer_journey.client.chat.completions, "create", _fake_create
    )


_VALID_MODEL_JSON = json.dumps({
    "recommended_action": "Book a test-drive appointment",
    "reason": "The customer is a qualified LEAD who has shown interest; the next step is to get them in for an appointment.",
    "suggested_timing": "within 1 week",
    "suggested_campaign": "Spring Test-Drive Push",
})


class TestGenerateJourneyRecommendationHappyPath:

    def test_returns_the_parsed_structured_recommendation(self, monkeypatch):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD", note="filled a form")
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        result = customer_journey.generate_journey_recommendation("CUST-1")

        assert _RECOMMENDATION_KEYS.issubset(result.keys())
        assert result["recommended_action"] == "Book a test-drive appointment"
        assert result["suggested_timing"] == "within 1 week"
        assert result["suggested_campaign"] == "Spring Test-Drive Push"
        assert result["ai_generated"] is True
        assert "disabled" not in result
        assert "fallback_reason" not in result

    def test_a_successful_recommendation_is_stored_onto_the_customer_entity(self, monkeypatch):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        _install_fake_client(monkeypatch, _VALID_MODEL_JSON)

        customer_journey.generate_journey_recommendation("CUST-1")

        entity = ledger.get_entity("CUST-1")
        stored = entity.attributes["journey_recommendation"]
        assert stored["recommended_action"] == "Book a test-drive appointment"
        assert stored["ai_generated"] is True

    def test_missing_model_keys_default_to_empty_never_invented(self, monkeypatch):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "SALE")
        _install_fake_client(monkeypatch, json.dumps({"recommended_action": "Schedule first service"}))

        result = customer_journey.generate_journey_recommendation("CUST-1")

        assert result["recommended_action"] == "Schedule first service"
        assert result["reason"] == ""
        assert result["suggested_timing"] == ""
        assert result["suggested_campaign"] == ""
        assert result["ai_generated"] is True


class TestGenerateJourneyRecommendationDisabled:

    def test_returns_an_honest_disabled_fallback_when_the_feature_flag_is_off(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        set_feature_flag("customer_journey_recommendation_enabled", False, "EMP-TEST")

        result = customer_journey.generate_journey_recommendation("CUST-1")

        assert _RECOMMENDATION_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert result["disabled"] is True
        # The fallback is grounded in the real current stage (LEAD), never invented.
        assert result["recommended_action"] == customer_journey._NEXT_BEST_ACTION["LEAD"]
        assert "LEAD" in result["reason"]

    def test_a_disabled_recommendation_is_not_persisted_onto_the_customer(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        set_feature_flag("customer_journey_recommendation_enabled", False, "EMP-TEST")

        customer_journey.generate_journey_recommendation("CUST-1")

        entity = ledger.get_entity("CUST-1")
        assert "journey_recommendation" not in entity.attributes


class TestGenerateJourneyRecommendationMalformedOutput:

    def test_malformed_model_output_falls_back_with_a_reason(self, monkeypatch):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "APPOINTMENT")
        set_feature_flag("customer_journey_recommendation_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, "this is not valid json {oops")

        result = customer_journey.generate_journey_recommendation("CUST-1")

        assert _RECOMMENDATION_KEYS.issubset(result.keys())
        assert result["ai_generated"] is False
        assert "disabled" not in result
        assert "fallback_reason" in result
        assert result["fallback_reason"]
        # Fallback is grounded in the real APPOINTMENT stage.
        assert result["recommended_action"] == customer_journey._NEXT_BEST_ACTION["APPOINTMENT"]

    def test_a_failed_recommendation_is_not_persisted_onto_the_customer(self, monkeypatch):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "APPOINTMENT")
        set_feature_flag("customer_journey_recommendation_enabled", True, "EMP-TEST")
        _install_fake_client(monkeypatch, "not json")

        customer_journey.generate_journey_recommendation("CUST-1")

        entity = ledger.get_entity("CUST-1")
        assert "journey_recommendation" not in entity.attributes


class TestGenerateJourneyRecommendationUnknownCustomer:

    def test_unknown_customer_raises(self):
        with pytest.raises(ValueError) as exc:
            customer_journey.generate_journey_recommendation("CUST-404")
        assert str(exc.value) == "No customer found with id CUST-404."

    def test_an_id_that_is_not_a_customer_raises(self):
        _add_lead()
        with pytest.raises(ValueError) as exc:
            customer_journey.generate_journey_recommendation("LEAD-1")
        assert str(exc.value) == "No customer found with id LEAD-1."


class TestFallbackJourneyRecommendation:

    def test_builds_a_stage_grounded_recommendation_for_every_stage(self):
        for stage in customer_journey.STAGES:
            brief = {"journey_stage": stage, "name": "Test", "journey_history": []}
            result = customer_journey.fallback_journey_recommendation(brief)
            assert result["recommended_action"] == customer_journey._NEXT_BEST_ACTION[stage]
            assert stage in result["reason"]
            assert result["suggested_timing"] == "within 2 weeks"
            assert result["suggested_campaign"] == ""

    def test_handles_a_customer_with_no_recorded_stage(self):
        brief = {"journey_stage": None, "name": "Test", "journey_history": []}
        result = customer_journey.fallback_journey_recommendation(brief)
        assert result["recommended_action"]
        assert "no recorded stage" in result["reason"]


class TestGenerateJourneyRecommendationApiRoleGating:

    def _seed_disabled(self):
        _add_customer()
        customer_journey.set_journey_stage("CUST-1", "LEAD")
        set_feature_flag("customer_journey_recommendation_enabled", False, "EMP-TEST")

    def test_every_real_view_role_can_generate_a_recommendation(self):
        self._seed_disabled()
        for role in _VIEW_ROLES:
            result = customer_journey_api.generate_journey_recommendation_api(role, "CUST-1")
            assert "error" not in result
            assert result["ai_generated"] is False

    def test_an_unknown_role_is_denied_generating_a_recommendation(self):
        self._seed_disabled()
        result = customer_journey_api.generate_journey_recommendation_api("BOGUS", "CUST-1")
        assert "error" in result

    def test_an_unknown_customer_error_surfaces_through_the_api(self):
        result = customer_journey_api.generate_journey_recommendation_api(ADMIN, "CUST-NOPE")
        assert result["error"] == "No customer found with id CUST-NOPE."
