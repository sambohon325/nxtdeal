"""
Tests for core/help_api.py's ask_help_api() -- the floating "?" help widget's "Ask AI"
tab (2026-07-13, session 34). Monkeypatches the OpenAI client the same way
test_ai_api.py stubs out ask_ai() -- fast, deterministic, no real OpenAI calls. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from core import help_api


class _FakeMessage:

    def __init__(self, content):
        self.content = content


class _FakeChoice:

    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:

    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:

    def __init__(self):
        self.last_messages = None

    def create(self, model=None, messages=None):
        self.last_messages = messages
        return _FakeResponse("stubbed help answer")


class _FakeChat:

    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:

    def __init__(self):
        self.chat = _FakeChat()


def _install_fake_client(monkeypatch):

    fake_client = _FakeClient()
    monkeypatch.setattr(help_api, "client", fake_client)

    return fake_client


def test_ask_help_returns_model_content(monkeypatch):

    _install_fake_client(monkeypatch)

    result = help_api.ask_help_api(
        "What can I do here?",
        role="SALES",
        department="Sales",
        screen_context=None
    )

    assert result == "stubbed help answer"


def test_ask_help_includes_role_and_department_in_prompt(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api(
        "What can I do here?",
        role="FINANCE",
        department="Finance",
        screen_context=None
    )

    user_message = fake_client.chat.completions.last_messages[1]["content"]

    assert "FINANCE" in user_message
    assert "Finance" in user_message
    assert "What can I do here?" in user_message


def test_ask_help_with_no_screen_context_says_nothing_open(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api(
        "What's on screen?",
        role="SALES",
        department="Sales",
        screen_context=None
    )

    user_message = fake_client.chat.completions.last_messages[1]["content"]

    assert "Nothing is currently open in the workspace panel." in user_message


def test_ask_help_describes_screen_context_when_present(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api(
        "What's on screen?",
        role="SALES",
        department="Sales",
        screen_context={
            "artifact_type": "deal_detail",
            "title": "Deal DEAL-00001 (financing)",
            "summary": "2 scenarios, financing_status=submitted"
        }
    )

    user_message = fake_client.chat.completions.last_messages[1]["content"]

    assert "deal_detail" in user_message
    assert "Deal DEAL-00001 (financing)" in user_message
    assert "financing_status=submitted" in user_message


def test_ask_help_partial_screen_context_omits_missing_fields(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api(
        "What's on screen?",
        role="SALES",
        department="Sales",
        screen_context={"artifact_type": "roster"}
    )

    user_message = fake_client.chat.completions.last_messages[1]["content"]

    assert "Artifact type currently on screen: roster" in user_message
    assert "Title:" not in user_message
    assert "Summary:" not in user_message


def test_ask_help_system_prompt_is_sent(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api(
        "How do I sell a car?",
        role="SALES",
        department="Sales",
        screen_context=None
    )

    system_message = fake_client.chat.completions.last_messages[0]

    assert system_message["role"] == "system"
    assert "in-app help assistant" in system_message["content"]


def test_ask_help_handles_missing_role_and_department(monkeypatch):

    fake_client = _install_fake_client(monkeypatch)

    help_api.ask_help_api("Help?", role=None, department=None, screen_context=None)

    user_message = fake_client.chat.completions.last_messages[1]["content"]

    assert "User's role: unknown" in user_message
    assert "Active department tab: none" in user_message
