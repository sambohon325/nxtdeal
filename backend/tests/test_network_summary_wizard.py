"""
Tests for core/network_summary_wizard.py -- the OPTIONAL, isolated OpenAI polish
step for Network's Overview/Opportunities Executive Summary
(core/network_opportunity_value.py). Same isolation pattern as
readiness_summary_wizard.py/email_wizard.py/website_wizard.py/
social_caption_wizard.py: never generates facts, only asked to smooth phrasing on
an already-correct real summary, with an honest fallback to that same unmodified
original text whenever the feature is disabled or OpenAI can't be reached.

No real OpenAI network calls are made in this suite -- the module-level `client` is
monkeypatched directly (patched on network_summary_wizard itself, "patch where it's
used"), and `is_feature_enabled`/`record_call_attempt` (both imported from
core.ai_management into this module's own namespace) are likewise patched here
rather than exercising the real AI-management kill-switch/stats machinery, which
already has its own dedicated coverage elsewhere.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import network_summary_wizard


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
    monkeypatch.setattr(network_summary_wizard, "is_feature_enabled", lambda key: True)
    calls = []
    monkeypatch.setattr(
        network_summary_wizard,
        "record_call_attempt",
        lambda key, outcome, detail=None: calls.append((key, outcome, detail)),
    )
    return calls


class TestPolishNetworkExecutiveSummary:

    def test_empty_input_returns_an_error_with_no_feature_check(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            network_summary_wizard,
            "is_feature_enabled",
            lambda key: (_ for _ in ()).throw(AssertionError("should not be called")),
        )

        result = network_summary_wizard.polish_network_executive_summary("")

        assert result == {"error": "No summary text to polish."}

    def test_none_input_returns_an_error(self):
        result = network_summary_wizard.polish_network_executive_summary(None)
        assert result == {"error": "No summary text to polish."}

    def test_disabled_feature_returns_a_disabled_error_without_calling_openai(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(network_summary_wizard, "is_feature_enabled", lambda key: False)

        def _should_not_be_called(*args, **kwargs):
            raise AssertionError("OpenAI should not be called when the feature is disabled")

        monkeypatch.setattr(
            network_summary_wizard.client.chat.completions, "create", _should_not_be_called
        )

        result = network_summary_wizard.polish_network_executive_summary("Real summary text.")

        assert result["disabled"] is True
        assert "error" in result
        assert ("network_executive_summary", "blocked", None) in enabled_by_default

    def test_successful_polish_returns_the_parsed_summary(self, monkeypatch, enabled_by_default):
        monkeypatch.setattr(
            network_summary_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"summary": "A polished, real-fact-only summary."}'),
        )

        result = network_summary_wizard.polish_network_executive_summary("Raw templated summary text.")

        assert result == {"summary": "A polished, real-fact-only summary."}
        assert ("network_executive_summary", "succeeded", None) in enabled_by_default

    def test_the_real_system_prompt_and_raw_text_are_sent_to_openai(self, monkeypatch, enabled_by_default):
        seen = {}

        def fake_create(**kwargs):
            seen.update(kwargs)
            return _FakeResponse('{"summary": "ok"}')

        monkeypatch.setattr(network_summary_wizard.client.chat.completions, "create", fake_create)

        network_summary_wizard.polish_network_executive_summary(
            "Your dealership ranks in the 62nd percentile."
        )

        messages = seen["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == network_summary_wizard.POLISH_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Your dealership ranks in the 62nd percentile."
        assert seen["response_format"] == {"type": "json_object"}

    def test_missing_summary_key_in_the_parsed_response_returns_an_error(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(
            network_summary_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"not_summary": "oops"}'),
        )

        result = network_summary_wizard.polish_network_executive_summary("Raw text.")

        assert result == {"error": "AI polish returned no summary text."}
        assert ("network_executive_summary", "succeeded", None) in enabled_by_default

    def test_empty_string_summary_in_the_parsed_response_returns_an_error(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(
            network_summary_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse('{"summary": ""}'),
        )

        result = network_summary_wizard.polish_network_executive_summary("Raw text.")

        assert result == {"error": "AI polish returned no summary text."}

    def test_a_network_or_api_exception_falls_back_to_an_honest_error_never_raises(
        self, monkeypatch, enabled_by_default
    ):
        def _raise(**kwargs):
            raise ConnectionError("simulated -- no outbound network path in this sandbox")

        monkeypatch.setattr(network_summary_wizard.client.chat.completions, "create", _raise)

        result = network_summary_wizard.polish_network_executive_summary("Raw text.")

        assert "error" in result
        assert "simulated" in result["error"]
        outcomes = [call[1] for call in enabled_by_default]
        assert outcomes == ["fell_back"]

    def test_malformed_json_in_the_response_falls_back_rather_than_raising(
        self, monkeypatch, enabled_by_default
    ):
        monkeypatch.setattr(
            network_summary_wizard.client.chat.completions,
            "create",
            lambda **kwargs: _FakeResponse("this is not valid json"),
        )

        result = network_summary_wizard.polish_network_executive_summary("Raw text.")

        assert "error" in result
        outcomes = [call[1] for call in enabled_by_default]
        assert outcomes == ["succeeded", "fell_back"]
