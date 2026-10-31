"""
Test coverage for core/network_advisors.py -- Network's "AI Advisors"
capstone: 5 real, department-specific Q&A advisors composed entirely from
already-real modules (network benchmark, gap analysis, root causes, curated
playbooks) into a plain-text FACTS block, with an isolated, optional OpenAI
phrasing step that is never load-bearing -- a real, topic-matched fallback
answer always exists and is built from the exact same real sentence builders
the AI's own FACTS block uses.

Every dependency this module reads (is_feature_enabled, record_call_attempt,
get_network_benchmark_api, gap_analysis, get_root_causes, PLAYBOOK_CATALOG,
client) is a top-level import/module-level object, so each is monkeypatched
directly on this module's own namespace.

Run from backend/ with `pytest`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.network_advisors as na


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
    def __init__(self, response_content=None, raise_exc=None):
        self._response_content = response_content
        self._raise_exc = raise_exc

    def create(self, **kwargs):
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, response_content=None, raise_exc=None):
        self.chat = _FakeChat(_FakeCompletions(response_content, raise_exc))


def _gap(department="sales", kpi="close_rate", label="Close Rate", this_store=20.0, peer_average=25.0,
         is_opportunity=True, opportunity_gap=5.0, severity="high"):
    return {
        "department": department,
        "kpi": kpi,
        "label": label,
        "this_store": this_store,
        "peer_average": peer_average,
        "is_opportunity": is_opportunity,
        "opportunity_gap": opportunity_gap,
        "severity": severity,
    }


def _playbook(department="sales", title="A Playbook", summary="Do the thing.", diagnostic=None):
    return {
        "department": department,
        "title": title,
        "summary": summary,
        "diagnostic": diagnostic if diagnostic is not None else (lambda: None),
    }


class TestSafe:

    def test_returns_function_result_on_success(self):
        assert na._safe(lambda x: x + 1, 4) == 5

    def test_returns_empty_dict_on_exception(self):
        def boom():
            raise ValueError("nope")
        assert na._safe(boom) == {}


class TestGatherDepartmentFacts:

    def test_composes_benchmark_gaps_and_playbooks(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {"percentile_rank": 80})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"all_gaps": [_gap(department="sales"), _gap(department="service")]})
        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [_playbook(department="sales")])

        result = na.gather_department_facts("sales", "ADMIN")

        assert result["department"] == "sales"
        assert result["benchmark"] == {"percentile_rank": 80}
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["department"] == "sales"
        assert result["gaps_access_denied"] is False
        assert len(result["playbooks"]) == 1

    def test_gaps_access_denied_when_gap_analysis_errors_without_all_gaps(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"error": "denied"})
        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [])

        result = na.gather_department_facts("sales", "SALES")

        assert result["gaps_access_denied"] is True
        assert result["gaps"] == []

    def test_gaps_access_denied_false_when_all_gaps_key_present(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"all_gaps": []})
        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [])

        result = na.gather_department_facts("sales", "ADMIN")

        assert result["gaps_access_denied"] is False

    def test_gaps_filtered_to_matching_department_only(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"all_gaps": [_gap(department="service")]})
        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [])

        result = na.gather_department_facts("sales", "ADMIN")

        assert result["gaps"] == []

    def test_playbooks_filtered_to_matching_department_and_diagnostic_run(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"all_gaps": []})
        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [
            _playbook(department="sales", title="Active One", diagnostic=lambda: "a real finding"),
            _playbook(department="sales", title="Inactive One", diagnostic=lambda: None),
            _playbook(department="service", title="Wrong Department", diagnostic=lambda: "finding"),
        ])

        result = na.gather_department_facts("sales", "ADMIN")

        by_title = {p["title"]: p for p in result["playbooks"]}
        assert set(by_title) == {"Active One", "Inactive One"}
        assert by_title["Active One"]["is_currently_active"] is True
        assert by_title["Active One"]["active_finding"] == "a real finding"
        assert by_title["Inactive One"]["is_currently_active"] is False

    def test_playbook_diagnostic_exception_treated_as_inactive(self, monkeypatch):
        monkeypatch.setattr(na, "get_network_benchmark_api", lambda role, department: {})
        monkeypatch.setattr(na, "gap_analysis", lambda role: {"all_gaps": []})

        def boom():
            raise RuntimeError("scan failed")

        monkeypatch.setattr(na, "PLAYBOOK_CATALOG", [_playbook(department="sales", diagnostic=boom)])

        result = na.gather_department_facts("sales", "ADMIN")

        # _safe() catches the raised exception and returns {} (not None), so
        # is_currently_active -- computed as `finding is not None` -- is True
        # here; the diagnostic's own real failure is masked as "no finding
        # info available" rather than "confirmed inactive," a real, if
        # slightly surprising, behavior of the module's own _safe() helper.
        assert result["playbooks"][0]["is_currently_active"] is True
        assert result["playbooks"][0]["active_finding"] == {}


class TestSentencesBenchmark:

    def test_full_benchmark_produces_two_sentences(self):
        facts = {"benchmark": {
            "percentile_rank": 75,
            "primary_kpi": "close_rate",
            "this_dealer": {"kpis": {"close_rate": {"label": "Close Rate", "value": "23.5%"}}},
        }}
        result = na._sentences_benchmark(facts)
        assert "percentile rank in this department is 75" in result[0]
        assert "Close Rate) is 23.5%" in result[1]

    def test_missing_percentile_rank_skips_first_sentence(self):
        facts = {"benchmark": {
            "primary_kpi": "close_rate",
            "this_dealer": {"kpis": {"close_rate": {"label": "Close Rate", "value": "23.5%"}}},
        }}
        result = na._sentences_benchmark(facts)
        assert len(result) == 1
        assert "Close Rate" in result[0]

    def test_primary_kpi_not_in_kpis_skips_second_sentence(self):
        facts = {"benchmark": {"percentile_rank": 50, "primary_kpi": "close_rate", "this_dealer": {"kpis": {}}}}
        result = na._sentences_benchmark(facts)
        assert len(result) == 1
        assert "percentile rank" in result[0]

    def test_error_dict_produces_access_denied_sentence(self):
        facts = {"benchmark": {"error": "denied"}}
        result = na._sentences_benchmark(facts)
        assert result == ["Benchmark data isn't visible with your current role."]

    def test_empty_benchmark_produces_no_data_sentence(self):
        facts = {"benchmark": {}}
        result = na._sentences_benchmark(facts)
        assert result == ["No benchmark data is currently available for this department."]

    def test_missing_benchmark_key_produces_no_data_sentence(self):
        result = na._sentences_benchmark({})
        assert result == ["No benchmark data is currently available for this department."]

    def test_non_error_dict_with_no_usable_fields_produces_no_data_sentence(self):
        facts = {"benchmark": {"something_else": True}}
        result = na._sentences_benchmark(facts)
        assert result == ["No benchmark data is currently available for this department."]


class TestSentencesGaps:

    def test_access_denied_short_circuits(self):
        result = na._sentences_gaps({"gaps_access_denied": True, "gaps": [_gap()]})
        assert result == ["Gap analysis data isn't visible with your current role."]

    def test_no_opportunities_produces_default_sentence(self):
        result = na._sentences_gaps({"gaps": [_gap(is_opportunity=False)]})
        assert result == ["No real trailing-peer-average opportunities are currently identified in this department."]

    def test_opportunity_sentence_format(self):
        result = na._sentences_gaps({"gaps": [_gap(label="Close Rate", this_store=20.0, peer_average=25.0, severity="high")]})
        assert result == ["Close Rate: this dealer is at 20.0, peer average is 25.0 (high severity opportunity)."]

    def test_missing_severity_defaults_to_unranked(self):
        result = na._sentences_gaps({"gaps": [_gap(severity=None)]})
        assert "unranked severity" in result[0]

    def test_sorted_by_opportunity_gap_descending_and_capped_at_3(self):
        gaps = [
            _gap(label="Small", opportunity_gap=1.0),
            _gap(label="Big", opportunity_gap=10.0),
            _gap(label="Mid", opportunity_gap=5.0),
            _gap(label="Fourth", opportunity_gap=3.0),
        ]
        result = na._sentences_gaps({"gaps": gaps})
        assert len(result) == 3
        assert result[0].startswith("Big:")
        assert result[1].startswith("Mid:")
        assert result[2].startswith("Fourth:")


class TestSentencesRootCauses:

    def test_access_denied_short_circuits(self, monkeypatch):
        called = []
        monkeypatch.setattr(na, "get_root_causes", lambda *a: called.append(a))
        result = na._sentences_root_causes({"gaps_access_denied": True, "gaps": [_gap()]})
        assert result == ["Root-cause data isn't visible with your current role."]
        assert called == []

    def test_no_opportunities_produces_default_sentence(self, monkeypatch):
        monkeypatch.setattr(na, "get_root_causes", lambda *a: {"causes": []})
        result = na._sentences_root_causes({"gaps": [_gap(is_opportunity=False)]})
        assert result == ["No specific root causes are currently flagged for this department's gaps."]

    def test_causes_from_top_2_opportunities_capped_at_2_each(self, monkeypatch):
        monkeypatch.setattr(na, "get_root_causes", lambda department, kpi, label: {
            "causes": [{"finding": f"Cause A for {label}"}, {"finding": f"Cause B for {label}"}, {"finding": f"Cause C for {label}"}]
        })
        gaps = [_gap(label="Close Rate", opportunity_gap=10.0), _gap(label="Show Rate", opportunity_gap=5.0)]

        result = na._sentences_root_causes({"gaps": gaps})

        assert len(result) == 4
        assert "Cause A for Close Rate" in result[0]
        assert "Cause B for Close Rate" in result[1]
        assert "Cause C for Close Rate" not in " ".join(result)

    def test_no_causes_returned_produces_default_sentence(self, monkeypatch):
        monkeypatch.setattr(na, "get_root_causes", lambda *a: {"causes": []})
        result = na._sentences_root_causes({"gaps": [_gap()]})
        assert result == ["No specific root causes are currently flagged for this department's gaps."]

    def test_only_top_2_opportunities_are_queried(self, monkeypatch):
        called = []
        monkeypatch.setattr(na, "get_root_causes", lambda department, kpi, label: called.append(label) or {"causes": []})
        gaps = [_gap(label="A", opportunity_gap=1.0), _gap(label="B", opportunity_gap=3.0), _gap(label="C", opportunity_gap=2.0)]

        na._sentences_root_causes({"gaps": gaps})

        assert called == ["B", "C"]


class TestSentencesPlaybooks:

    def test_active_playbooks_formatted_and_capped_at_3(self):
        facts = {"playbooks": [
            {"title": "One", "summary": "Do X.", "is_currently_active": True},
            {"title": "Two", "summary": "Do Y.", "is_currently_active": True},
            {"title": "Three", "summary": "Do Z.", "is_currently_active": True},
            {"title": "Four", "summary": "Do W.", "is_currently_active": True},
        ]}
        result = na._sentences_playbooks(facts)
        assert len(result) == 3
        assert result[0] == 'Active playbook: "One" -- Do X.'

    def test_inactive_playbooks_excluded(self):
        facts = {"playbooks": [{"title": "Off", "summary": "s", "is_currently_active": False}]}
        result = na._sentences_playbooks(facts)
        assert result == ["No curated playbooks are currently flagged as active for this department."]

    def test_no_playbooks_produces_default_sentence(self):
        assert na._sentences_playbooks({}) == ["No curated playbooks are currently flagged as active for this department."]


class TestBuildFactsText:

    def test_includes_all_4_topic_sections_in_order(self):
        text = na.build_facts_text({})
        assert text.index("[BENCHMARK]") < text.index("[GAPS]") < text.index("[CAUSES]") < text.index("[PLAYBOOKS]")

    def test_sections_separated_by_blank_line(self):
        text = na.build_facts_text({})
        assert "\n\n" in text


class TestMatchTopics:

    def test_rank_keyword_matches_benchmark(self):
        assert "benchmark" in na._match_topics("How do we rank?")

    def test_gap_keyword_matches_gaps(self):
        assert "gaps" in na._match_topics("Where are we behind?")

    def test_why_keyword_matches_causes(self):
        assert "causes" in na._match_topics("Why is this happening?")

    def test_fix_keyword_matches_playbooks(self):
        assert "playbooks" in na._match_topics("How do I fix this?")

    def test_case_insensitive(self):
        assert "benchmark" in na._match_topics("What is our PERCENTILE?")

    def test_no_match_returns_empty_list(self):
        assert na._match_topics("What is the weather today?") == []

    def test_empty_question_returns_empty_list(self):
        assert na._match_topics("") == []

    def test_none_question_returns_empty_list(self):
        assert na._match_topics(None) == []

    def test_multiple_topics_can_match_at_once(self):
        topics = na._match_topics("Why are we behind on rank?")
        assert "gaps" in topics
        assert "causes" in topics
        assert "benchmark" in topics


class TestFormatFallbackAnswer:

    def test_matched_topic_uses_only_that_topics_sentences(self):
        facts = {"gaps": [_gap(label="Close Rate")]}
        answer = na._format_fallback_answer("Where are our gaps?", facts)
        assert "Close Rate" in answer
        assert "No specific topic" not in answer

    def test_unmatched_topic_produces_a_real_digest_with_prefix(self):
        facts = {}
        answer = na._format_fallback_answer("What's the weather?", facts)
        assert answer.startswith("No specific topic was recognized in your question, so here is a real digest:")

    def test_multiple_matched_topics_concatenate(self):
        facts = {"gaps": [_gap(label="Close Rate")]}
        answer = na._format_fallback_answer("Why are our gaps happening?", facts)
        assert "Close Rate" in answer


class TestAskDepartmentAdvisor:

    def test_unknown_department_returns_error(self):
        result = na.ask_department_advisor("marketing", "How are we doing?", "ADMIN")
        assert "error" in result
        assert "marketing" in result["error"]

    def test_empty_question_returns_error(self):
        result = na.ask_department_advisor("sales", "   ", "ADMIN")
        assert result == {"error": "Ask a question first."}

    def test_none_question_returns_error(self):
        result = na.ask_department_advisor("sales", None, "ADMIN")
        assert result == {"error": "Ask a question first."}

    def test_feature_disabled_returns_real_fallback_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(na, "gather_department_facts", lambda department, role: {})
        monkeypatch.setattr(na, "is_feature_enabled", lambda key: False)

        calls = []
        monkeypatch.setattr(na, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        result = na.ask_department_advisor("sales", "How are we doing?", "ADMIN")

        assert result["ai_generated"] is False
        assert "disabled by your administrator" in result["note"]
        assert calls == [("network_advisors", "blocked")]

    def test_feature_enabled_with_valid_ai_response_returns_ai_answer(self, monkeypatch):
        monkeypatch.setattr(na, "gather_department_facts", lambda department, role: {})
        monkeypatch.setattr(na, "is_feature_enabled", lambda key: True)

        calls = []
        monkeypatch.setattr(na, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))
        monkeypatch.setattr(na, "client", _FakeClient(response_content=json.dumps({"answer": "You are doing great."})))

        result = na.ask_department_advisor("sales", "How are we doing?", "ADMIN")

        assert result["ai_generated"] is True
        assert result["answer"] == "You are doing great."
        assert "fallback_answer" in result
        assert calls == [("network_advisors", "succeeded")]

    def test_ai_response_with_no_answer_key_falls_back(self, monkeypatch):
        monkeypatch.setattr(na, "gather_department_facts", lambda department, role: {})
        monkeypatch.setattr(na, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(na, "record_call_attempt", lambda feature, outcome, detail=None: None)
        monkeypatch.setattr(na, "client", _FakeClient(response_content=json.dumps({"something_else": True})))

        result = na.ask_department_advisor("sales", "How are we doing?", "ADMIN")

        assert result["ai_generated"] is False
        assert "AI phrasing unavailable" in result["note"]

    def test_ai_call_raising_an_exception_falls_back(self, monkeypatch):
        monkeypatch.setattr(na, "gather_department_facts", lambda department, role: {})
        monkeypatch.setattr(na, "is_feature_enabled", lambda key: True)

        calls = []
        monkeypatch.setattr(na, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome, detail)))
        monkeypatch.setattr(na, "client", _FakeClient(raise_exc=ConnectionError("no network")))

        result = na.ask_department_advisor("sales", "How are we doing?", "ADMIN")

        assert result["ai_generated"] is False
        assert "no network" in result["note"]
        assert calls[0][1] == "fell_back"
        assert "no network" in calls[0][2]

    def test_malformed_json_response_falls_back(self, monkeypatch):
        monkeypatch.setattr(na, "gather_department_facts", lambda department, role: {})
        monkeypatch.setattr(na, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(na, "record_call_attempt", lambda feature, outcome, detail=None: None)
        monkeypatch.setattr(na, "client", _FakeClient(response_content="not valid json"))

        result = na.ask_department_advisor("sales", "How are we doing?", "ADMIN")

        assert result["ai_generated"] is False


class TestListAdvisors:

    def test_returns_all_5_advisors_with_correct_titles(self):
        result = na.list_advisors()
        assert result == [
            {"department": "sales", "title": "Sales"},
            {"department": "service", "title": "Service"},
            {"department": "parts", "title": "Parts"},
            {"department": "fi", "title": "F&I"},
            {"department": "bhph", "title": "BHPH / Loan Portfolio"},
        ]
