"""
Tests for core/social_caption_wizard.py -- AI caption generation for the Social &
Reputation post builder. Same isolated, no-tool-calling OpenAI client pattern as
email_wizard.py/website_wizard.py/reputation.py's auto-respond bot, platform-aware,
grounded only in real vehicle attributes when a vehicle dict is supplied (never
invents a price/VIN/trim).

Unlike readiness_summary_wizard.py/network_summary_wizard.py (which record
"succeeded" immediately after the API call returns, before validating the parsed
shape), this module only records "succeeded" once a genuinely non-empty caption has
been extracted -- an empty/whitespace-only caption in an otherwise well-formed
response records "fell_back" directly, with no preceding "succeeded" record. That
real ordering distinction is exercised explicitly below.

No real OpenAI network calls are made -- the module-level `client` is monkeypatched
directly on social_caption_wizard itself ("patch where it's used"), and
`is_feature_enabled`/`record_call_attempt` (imported from core.ai_management into
this module's own namespace) are likewise patched here rather than exercising the
real AI-management kill-switch/stats machinery, which already has its own dedicated
coverage elsewhere.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import social_caption_wizard


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


@pytest.fixture(autouse=True)
def enabled_by_default(monkeypatch):
    monkeypatch.setattr(social_caption_wizard, "is_feature_enabled", lambda key: True)
    calls = []
    monkeypatch.setattr(
        social_caption_wizard,
        "record_call_attempt",
        lambda key, outcome, detail=None: calls.append((key, outcome, detail)),
    )
    return calls


class TestVehicleContext:

    def test_no_vehicle_returns_a_general_caption_placeholder(self):
        result = social_caption_wizard._vehicle_context(None)
        assert "no specific vehicle" in result

    def test_empty_dict_vehicle_returns_a_general_caption_placeholder(self):
        result = social_caption_wizard._vehicle_context({})
        assert "no specific vehicle" in result

    def test_vehicle_with_all_fields_includes_year_make_model_trim_and_price(self):
        vehicle = {"year": 2023, "make": "Toyota", "model": "Camry", "trim": "SE", "price": 28500}
        result = social_caption_wizard._vehicle_context(vehicle)
        assert "2023 Toyota Camry SE" in result
        assert "$28500" in result

    def test_vehicle_with_no_matching_line_fields_but_a_price_uses_the_fallback_label(self):
        vehicle = {"price": 15000}
        result = social_caption_wizard._vehicle_context(vehicle)
        assert "a vehicle in stock" in result
        assert "$15000" in result

    def test_vehicle_with_no_price_omits_the_dollar_amount(self):
        vehicle = {"year": 2022, "make": "Honda"}
        result = social_caption_wizard._vehicle_context(vehicle)
        assert "2022 Honda" in result
        assert "$" not in result


class TestGenerateCaption:

    def test_disabled_feature_returns_a_disabled_error_without_calling_openai(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(social_caption_wizard, "is_feature_enabled", lambda key: False)

        def _should_not_be_called(*args, **kwargs):
            raise AssertionError("OpenAI should not be called when the feature is disabled")

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", _should_not_be_called)

        result = social_caption_wizard.generate_caption("instagram")

        assert result["disabled"] is True
        assert "error" in result
        assert ("social_caption_wizard", "blocked", None) in enabled_by_default

    def test_successful_generation_returns_the_parsed_caption(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"caption": "Check out this ride! #dealership"}'),
        )

        result = social_caption_wizard.generate_caption("instagram", goal="promote a sale")

        assert result == {"caption": "Check out this ride! #dealership"}
        outcomes = [c[1] for c in enabled_by_default]
        assert outcomes == ["succeeded"]

    def test_known_platform_uses_its_own_real_guidance_string(self, monkeypatch, enabled_by_default):
        seen = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            return _FakeResponse('{"caption": "ok"}')

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", fake_create)

        social_caption_wizard.generate_caption("x")

        user_content = seen["messages"][1]["content"]
        assert social_caption_wizard.PLATFORM_GUIDANCE["x"] in user_content

    def test_unknown_platform_falls_back_to_a_generic_guidance_string(self, monkeypatch, enabled_by_default):
        seen = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            return _FakeResponse('{"caption": "ok"}')

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", fake_create)

        social_caption_wizard.generate_caption("bluesky")

        user_content = seen["messages"][1]["content"]
        assert "short, platform-appropriate caption" in user_content

    def test_default_goal_and_tone_are_used_when_not_supplied(self, monkeypatch, enabled_by_default):
        seen = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            return _FakeResponse('{"caption": "ok"}')

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", fake_create)

        social_caption_wizard.generate_caption("facebook")

        user_content = seen["messages"][1]["content"]
        assert "promote the dealership" in user_content
        assert "friendly and upbeat" in user_content

    def test_the_real_system_prompt_and_vehicle_context_are_sent_to_openai(
        self, monkeypatch, enabled_by_default
    ):
        seen = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            return _FakeResponse('{"caption": "ok"}')

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", fake_create)

        vehicle = {"year": 2024, "make": "Ford", "model": "F-150", "price": 42000}
        social_caption_wizard.generate_caption("linkedin", vehicle=vehicle)

        messages = seen["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == social_caption_wizard.CAPTION_SYSTEM_PROMPT
        assert "2024 Ford F-150" in messages[1]["content"]
        assert "$42000" in messages[1]["content"]
        assert seen["response_format"] == {"type": "json_object"}

    def test_empty_caption_in_the_parsed_response_records_fell_back_directly(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"caption": ""}'),
        )

        result = social_caption_wizard.generate_caption("instagram")

        assert result == {"error": "Empty caption returned"}
        # No "succeeded" record precedes the fallback here -- the empty-caption check
        # happens before any success is recorded, unlike the readiness/network
        # summary wizards' ordering.
        outcomes = [c[1] for c in enabled_by_default]
        assert outcomes == ["fell_back"]

    def test_whitespace_only_caption_is_treated_as_empty(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"caption": "   "}'),
        )

        result = social_caption_wizard.generate_caption("instagram")

        assert result == {"error": "Empty caption returned"}

    def test_missing_caption_key_is_treated_as_empty(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"not_caption": "oops"}'),
        )

        result = social_caption_wizard.generate_caption("instagram")

        assert result == {"error": "Empty caption returned"}

    def test_caption_is_stripped_of_surrounding_whitespace(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"caption": "  Clean caption text  "}'),
        )

        result = social_caption_wizard.generate_caption("instagram")

        assert result == {"caption": "Clean caption text"}

    def test_a_network_or_api_exception_falls_back_to_an_honest_error_never_raises(
        self, monkeypatch, enabled_by_default
    ):
        def _raise(**kwargs):
            raise ConnectionError("simulated -- no outbound network path in this sandbox")

        monkeypatch.setattr(social_caption_wizard.client.chat.completions, "create", _raise)

        result = social_caption_wizard.generate_caption("instagram")

        assert "error" in result
        assert "simulated" in result["error"]
        outcomes = [c[1] for c in enabled_by_default]
        assert outcomes == ["fell_back"]

    def test_malformed_json_in_the_response_falls_back_rather_than_raising(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(
            social_caption_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse("this is not valid json"),
        )

        result = social_caption_wizard.generate_caption("instagram")

        assert "error" in result
        outcomes = [c[1] for c in enabled_by_default]
        assert outcomes == ["fell_back"]


class TestFallbackCaption:

    def test_no_vehicle_uses_the_general_dealership_placeholder(self):
        result = social_caption_wizard.fallback_caption("instagram")
        assert "caption" in result
        assert "check out what's new" in result["caption"]

    def test_custom_goal_is_used_in_the_general_placeholder(self):
        result = social_caption_wizard.fallback_caption("instagram", goal="explore our BHPH options")
        assert "explore our BHPH options" in result["caption"]

    def test_vehicle_supplied_produces_a_real_vehicle_caption(self):
        vehicle = {"year": 2021, "make": "Chevrolet", "model": "Malibu", "price": 19999}
        result = social_caption_wizard.fallback_caption("instagram", vehicle=vehicle)
        assert "2021 Chevrolet Malibu" in result["caption"]
        assert "$19999" in result["caption"]

    def test_vehicle_with_no_price_omits_the_dollar_amount(self):
        vehicle = {"year": 2021, "make": "Chevrolet"}
        result = social_caption_wizard.fallback_caption("instagram", vehicle=vehicle)
        assert "$" not in result["caption"]

    def test_vehicle_with_no_line_fields_uses_the_this_vehicle_fallback_label(self):
        vehicle = {"price": 10000}
        result = social_caption_wizard.fallback_caption("instagram", vehicle=vehicle)
        assert "this vehicle" in result["caption"]

    def test_fallback_caption_makes_no_feature_flag_or_stats_calls(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            social_caption_wizard,
            "is_feature_enabled",
            lambda key: (_ for _ in ()).throw(AssertionError("should not be called")),
        )

        result = social_caption_wizard.fallback_caption("instagram")

        assert "caption" in result
        assert enabled_by_default == []
