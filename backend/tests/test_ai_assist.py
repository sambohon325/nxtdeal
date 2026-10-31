"""Tests for core/ai_assist.py -- the generic inline AI text-assist
(generate/rewrite/shorten/expand/retone/grammar) plus its
core/ai_assist_api.py ACL layer.

Follows tests/test_customer_journey_ai.py's own established conventions
(fresh_ledger + no_real_persistence autouse fixtures, a _VIEW_ROLES constant,
class-grouped tests, direct asserts, no per-test docstrings, a monkeypatched
fake OpenAI client for the happy path). This sandbox has no outbound network
access, so the AI-path tests monkeypatch the isolated client
(ai_assist.client) with a fake returning valid JSON, while the disabled-
feature tests exercise the real deterministic fallback path.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, FINANCE, MARKETING, OPERATIONS, SALES, SERVICE

from core import ai_assist
from core import ai_assist_api
from core import system_config
from core.system_config import set_feature_flag, update_brand_settings


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # ai_assist itself never saves; get_brand_settings() goes through
    # system_config._get_or_create() which does.
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


def _install_fake_client(monkeypatch, result_text="TRANSFORMED", capture=None):
    """Monkeypatch ai_assist.client.chat.completions.create to return a canned
    completion whose JSON `result` is `result_text`. If `capture` is a list,
    the messages passed to the model are appended to it so tests can assert on
    the injected brand context."""

    def _fake_create(*args, **kwargs):
        if capture is not None:
            capture.append(kwargs.get("messages"))
        return _FakeCompletion(json.dumps({"result": result_text}))

    monkeypatch.setattr(ai_assist.client.chat.completions, "create", _fake_create)


# ---------------------------------------------------------------------------
# AI path (mocked OpenAI) -- each action returns non-empty transformed text.
# ---------------------------------------------------------------------------

class TestAssistAiPath:

    @pytest.mark.parametrize("action", ["rewrite", "shorten", "expand", "retone", "grammar"])
    def test_transform_actions_return_the_model_result(self, monkeypatch, action):
        _install_fake_client(monkeypatch, result_text="A clean on-brand sentence.")
        result = ai_assist.assist_text("some raw input text", action)

        assert result["ai_generated"] is True
        assert result["action"] == action
        assert result["result"] == "A clean on-brand sentence."
        assert "note" not in result

    def test_generate_uses_context_and_returns_model_result(self, monkeypatch):
        _install_fake_client(monkeypatch, result_text="Your Service Is Due -- Book Today")
        result = ai_assist.assist_text(
            "", "generate", context="email subject line for a service reminder"
        )

        assert result["ai_generated"] is True
        assert result["action"] == "generate"
        assert result["result"] == "Your Service Is Due -- Book Today"

    def test_an_empty_model_result_falls_back_deterministically(self, monkeypatch):
        _install_fake_client(monkeypatch, result_text="")
        result = ai_assist.assist_text("fix   this  text", "grammar")

        # Empty model output is treated as a failure -> real rule-based fallback.
        assert result["ai_generated"] is False
        assert result["result"]
        assert "note" in result


# ---------------------------------------------------------------------------
# Brand tone / style injection.
# ---------------------------------------------------------------------------

class TestBrandInjection:

    def test_brand_tone_and_voice_are_injected_into_the_prompt(self, monkeypatch):
        update_brand_settings(
            {
                "brand_tone": "High Energy",
                "brand_voice": "Upbeat, family-owned, no pressure.",
                "style_guidelines": "Never use ALL CAPS.",
            },
            "EMP-TEST",
        )
        capture = []
        _install_fake_client(monkeypatch, result_text="ok", capture=capture)

        ai_assist.assist_text("draft text", "rewrite")

        user_content = capture[0][1]["content"]
        assert "High Energy" in user_content
        assert "Upbeat, family-owned, no pressure." in user_content
        assert "Never use ALL CAPS." in user_content

    def test_default_tone_comes_from_brand_settings_when_none_passed(self, monkeypatch):
        update_brand_settings({"brand_tone": "Direct"}, "EMP-TEST")
        capture = []
        _install_fake_client(monkeypatch, result_text="ok", capture=capture)

        ai_assist.assist_text("draft text", "rewrite")

        user_content = capture[0][1]["content"]
        assert "Direct" in user_content

    def test_explicit_tone_overrides_the_brand_default(self, monkeypatch):
        update_brand_settings({"brand_tone": "Professional"}, "EMP-TEST")
        capture = []
        _install_fake_client(monkeypatch, result_text="ok", capture=capture)

        ai_assist.assist_text("draft text", "retone", tone="Friendly")

        user_content = capture[0][1]["content"]
        assert "Friendly" in user_content


# ---------------------------------------------------------------------------
# Deterministic fallback (feature disabled) -- real, non-blank transforms.
# ---------------------------------------------------------------------------

class TestDeterministicFallback:

    def _disable(self):
        set_feature_flag("ai_assist_enabled", False, "EMP-TEST")

    def test_grammar_fallback_cleans_whitespace_and_capitalization(self):
        self._disable()
        result = ai_assist.assist_text("hello   world .this is  wrong", "grammar")

        assert result["ai_generated"] is False
        assert result["note"]
        assert result["result"].startswith("Hello world")
        assert "   " not in result["result"]

    def test_shorten_fallback_trims_to_the_first_sentence(self):
        self._disable()
        text = "First sentence here. Second sentence here. Third one too."
        result = ai_assist.assist_text(text, "shorten")

        assert result["ai_generated"] is False
        assert result["result"] == "First sentence here."

    def test_expand_fallback_appends_a_sentence_and_gets_longer(self):
        self._disable()
        text = "We have great deals"
        result = ai_assist.assist_text(text, "expand")

        assert result["ai_generated"] is False
        assert len(result["result"]) > len(text)
        assert result["result"].startswith("We have great deals")

    def test_retone_fallback_returns_nonblank_marked_text(self):
        self._disable()
        result = ai_assist.assist_text("some existing copy", "retone", tone="Friendly")

        assert result["ai_generated"] is False
        assert result["result"]
        assert "Friendly" in result["note"]

    def test_rewrite_fallback_returns_cleaned_nonblank_text(self):
        self._disable()
        result = ai_assist.assist_text("rewrite    me please", "rewrite")

        assert result["ai_generated"] is False
        assert result["result"] == "rewrite me please"

    def test_generate_fallback_with_no_draft_returns_a_marked_placeholder(self):
        self._disable()
        result = ai_assist.assist_text(
            "", "generate", context="email subject line for a service reminder"
        )

        assert result["ai_generated"] is False
        assert result["result"]
        assert "service reminder" in result["result"]

    def test_generate_fallback_with_a_draft_echoes_the_draft(self):
        self._disable()
        result = ai_assist.assist_text("My existing draft", "generate", context="a subject line")

        assert result["ai_generated"] is False
        assert "My existing draft" in result["result"]

    def test_no_fallback_ever_returns_a_blank_result(self):
        self._disable()
        for action in ("rewrite", "shorten", "expand", "retone", "grammar"):
            result = ai_assist.assist_text("Some real input text here. And more.", action)
            assert result["result"].strip(), action


# ---------------------------------------------------------------------------
# Guards -- empty text, invalid action.
# ---------------------------------------------------------------------------

class TestGuards:

    def test_empty_text_is_rejected_for_transform_actions(self):
        for action in ("rewrite", "shorten", "expand", "retone", "grammar"):
            result = ai_assist.assist_text("   ", action)
            assert "error" in result
            assert result["ai_generated"] is False

    def test_generate_allows_empty_text(self):
        set_feature_flag("ai_assist_enabled", False, "EMP-TEST")
        result = ai_assist.assist_text("", "generate", context="a subject line")
        assert "error" not in result

    def test_invalid_action_is_rejected(self):
        result = ai_assist.assist_text("hi", "translate")
        assert "error" in result
        assert "translate" in result["error"]


# ---------------------------------------------------------------------------
# API ACL layer.
# ---------------------------------------------------------------------------

class TestAssistApiRoleGating:

    def _disable(self):
        set_feature_flag("ai_assist_enabled", False, "EMP-TEST")

    def test_every_real_role_can_use_inline_assist(self):
        self._disable()
        for role in _VIEW_ROLES:
            result = ai_assist_api.assist_text_api(role, "Fix this text.", "grammar")
            assert "error" not in result
            assert result["result"]

    def test_an_unknown_role_is_denied(self):
        self._disable()
        result = ai_assist_api.assist_text_api("BOGUS", "Fix this text.", "grammar")
        assert "error" in result

    def test_api_passes_tone_and_context_through(self, monkeypatch):
        capture = []
        _install_fake_client(monkeypatch, result_text="ok", capture=capture)

        ai_assist_api.assist_text_api(
            ADMIN, "", "generate", tone="High Energy", context="a headline"
        )

        user_content = capture[0][1]["content"]
        assert "High Energy" in user_content
        assert "a headline" in user_content
