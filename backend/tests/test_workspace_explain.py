"""
Tests for core/workspace_explain.py -- the isolated, no-tool-calling AI chart
explanation helper (session 76). Run from backend/ with `pytest`.

Covers: _describe_rows()'s empty/non-empty/25-row-cap/label-column/numeric-columns
behavior; explain_chart()'s real kill-switch gate (blocked without ever calling
OpenAI), the real success path (returns the completion content, records "succeeded"),
the real fallback-on-exception path (returns a readable error message, records
"fell_back" with the exception detail, never raises into the caller), None-defaulting
of numeric_columns/rows, and that prompt_context is only included in the constructed
message when supplied.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import workspace_explain


class _FakeChoice:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _RecordingCalls:
    def __init__(self):
        self.calls = []

    def __call__(self, feature_key, outcome, detail=None):
        self.calls.append({"feature_key": feature_key, "outcome": outcome, "detail": detail})


@pytest.fixture(autouse=True)
def enabled_by_default(monkeypatch):
    # Most tests want the feature enabled; individual tests override this.
    monkeypatch.setattr(workspace_explain, "is_feature_enabled", lambda key: True)


@pytest.fixture
def recorder(monkeypatch):
    recording = _RecordingCalls()
    monkeypatch.setattr(workspace_explain, "record_call_attempt", recording)
    return recording


class TestDescribeRows:

    def test_empty_rows_returns_no_data_message(self):
        assert workspace_explain._describe_rows([], "name", ["value"]) == "No data rows were provided."

    def test_non_empty_rows_produces_header_and_lines(self):
        rows = [{"name": "Truck", "value": 10}, {"name": "Sedan", "value": 20}]
        result = workspace_explain._describe_rows(rows, "name", ["value"])

        assert "2 rows, columns: value (labeled by name)." in result
        assert "- Truck: value=10" in result
        assert "- Sedan: value=20" in result

    def test_caps_at_25_rows_and_reports_remainder(self):
        rows = [{"name": f"Row{i}", "value": i} for i in range(30)]
        result = workspace_explain._describe_rows(rows, "name", ["value"])

        assert result.count("- Row") == 25
        assert "...and 5 more rows." in result

    def test_no_label_column_produces_empty_label(self):
        rows = [{"name": "Truck", "value": 10}]
        result = workspace_explain._describe_rows(rows, None, ["value"])
        assert "- : value=10" in result

    def test_numeric_columns_filtered_to_present_keys_only(self):
        rows = [{"name": "Truck", "value": 10}]
        result = workspace_explain._describe_rows(rows, "name", ["value", "missing_col"])
        # missing_col isn't in the row so it's silently skipped, not rendered as
        # "missing_col=None".
        assert "missing_col" not in result.split("\n")[-1]
        assert "value=10" in result.split("\n")[-1]

    def test_label_column_none_or_missing_reported_as_n_a_in_header(self):
        rows = [{"name": "Truck", "value": 10}]
        result = workspace_explain._describe_rows(rows, None, ["value"])
        assert "labeled by n/a" in result


class TestExplainChartKillSwitch:

    def test_disabled_feature_returns_disabled_answer_without_calling_openai(self, monkeypatch, recorder):
        monkeypatch.setattr(workspace_explain, "is_feature_enabled", lambda key: False)
        called = {"count": 0}
        monkeypatch.setattr(
            workspace_explain.client.chat.completions, "create",
            lambda **kwargs: called.__setitem__("count", called["count"] + 1),
        )

        result = workspace_explain.explain_chart(rows=[{"a": 1}], numeric_columns=["a"])

        assert result == workspace_explain._DISABLED_ANSWER
        assert called["count"] == 0
        assert recorder.calls == [{"feature_key": "workspace_explain", "outcome": "blocked", "detail": None}]


class TestExplainChartSuccessPath:

    def test_returns_completion_content_and_records_succeeded(self, monkeypatch, recorder):
        monkeypatch.setattr(
            workspace_explain.client.chat.completions, "create",
            lambda **kwargs: _FakeResponse("This chart shows real dealership data."),
        )

        result = workspace_explain.explain_chart(
            source_label="Sales by Month", department="sales",
            rows=[{"month": "Jan", "units": 10}], label_column="month", numeric_columns=["units"],
        )

        assert result == "This chart shows real dealership data."
        assert recorder.calls == [{"feature_key": "workspace_explain", "outcome": "succeeded", "detail": None}]

    def test_none_rows_and_numeric_columns_default_to_empty_without_crashing(self, monkeypatch, recorder):
        monkeypatch.setattr(
            workspace_explain.client.chat.completions, "create",
            lambda **kwargs: _FakeResponse("ok"),
        )

        result = workspace_explain.explain_chart(rows=None, numeric_columns=None)
        assert result == "ok"

    def test_prompt_context_included_when_supplied(self, monkeypatch, recorder):
        captured = {}

        def _fake_create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return _FakeResponse("ok")

        monkeypatch.setattr(workspace_explain.client.chat.completions, "create", _fake_create)

        workspace_explain.explain_chart(rows=[{"a": 1}], numeric_columns=["a"], prompt_context="why is this low?")

        user_content = captured["messages"][1]["content"]
        assert "The user's original question/prompt was: why is this low?" in user_content

    def test_prompt_context_omitted_when_not_supplied(self, monkeypatch, recorder):
        captured = {}

        def _fake_create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return _FakeResponse("ok")

        monkeypatch.setattr(workspace_explain.client.chat.completions, "create", _fake_create)

        workspace_explain.explain_chart(rows=[{"a": 1}], numeric_columns=["a"])

        user_content = captured["messages"][1]["content"]
        assert "original question/prompt" not in user_content

    def test_source_label_falls_back_to_item_key_then_untitled(self, monkeypatch, recorder):
        captured = {}

        def _fake_create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return _FakeResponse("ok")

        monkeypatch.setattr(workspace_explain.client.chat.completions, "create", _fake_create)

        workspace_explain.explain_chart(rows=[], item_key="pricing_desk")
        assert "Chart source: pricing_desk" in captured["messages"][1]["content"]

        workspace_explain.explain_chart(rows=[])
        assert "Chart source: Untitled" in captured["messages"][1]["content"]


class TestExplainChartFallbackPath:

    def test_openai_exception_falls_back_and_records_fell_back(self, monkeypatch, recorder):
        def _raise(**kwargs):
            raise ConnectionError("no network path to OpenAI")

        monkeypatch.setattr(workspace_explain.client.chat.completions, "create", _raise)

        result = workspace_explain.explain_chart(rows=[{"a": 1}], numeric_columns=["a"])

        assert "I'm having trouble reaching the AI service right now" in result
        assert "no network path to OpenAI" in result
        assert recorder.calls[0]["outcome"] == "fell_back"
        assert "no network path to OpenAI" in recorder.calls[0]["detail"]

    def test_fallback_never_raises_into_the_caller(self, monkeypatch, recorder):
        monkeypatch.setattr(
            workspace_explain.client.chat.completions, "create",
            lambda **kwargs: (_ for _ in ()).throw(ValueError("boom")),
        )

        # Should not raise -- the whole point of the try/except.
        result = workspace_explain.explain_chart(rows=[])
        assert isinstance(result, str)
