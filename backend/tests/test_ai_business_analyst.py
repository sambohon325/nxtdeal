"""Tests for core/ai_business_analyst.py -- Readiness' AI Business Analyst.

The AI-phrasing path always falls back in this sandbox (no outbound OpenAI
network access, confirmed by this codebase's own repeated findings), so the
real focus here is the deterministic topic-matching fallback formatter --
that's the code path an executive actually sees in this environment, and it
does all the real work (every number traces to an already-real/heuristic/
simulated-labeled figure, this module only composes and phrases)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.ai_business_analyst as aba


# ---------------------------------------------------------------------------
# _match_topics()
# ---------------------------------------------------------------------------


class TestMatchTopics:

    def test_matches_inventory_keyword(self):
        assert "inventory" in aba._match_topics("Why is inventory readiness declining?")

    def test_matches_multiple_topics(self):
        topics = aba._match_topics("How are sales and finance collections doing?")
        assert "sales" in topics
        assert "finance" in topics

    def test_case_insensitive(self):
        assert "risk" in aba._match_topics("WHAT EXCEPTIONS ARE OPEN")

    def test_no_match_returns_empty(self):
        assert aba._match_topics("what's the weather like") == []

    def test_empty_question_returns_empty(self):
        assert aba._match_topics("") == []
        assert aba._match_topics(None) == []


# ---------------------------------------------------------------------------
# Per-topic sentence builders
# ---------------------------------------------------------------------------


class TestSentencesInventory:

    def test_builds_real_sentences_from_facts(self):
        facts = {
            "business_health": {
                "inventory": {
                    "aging": {
                        "aged_units_by_band": {"91+ days": 17},
                        "average_days_in_stock": 42,
                        "sample_size": 150,
                    },
                    "turn_rate": {"annualized_turn_rate": 5.5},
                    "recon_time": {
                        "avg_checklist_completion_pct": 62.5,
                        "used_unsold_count": 40,
                        "vehicles_fully_recon_complete": 10,
                        "vehicles_with_zero_recon_progress": 5,
                    },
                    "days_supply": {"market_days_supply": 60},
                }
            }
        }

        out = aba._sentences_inventory(facts)

        combined = " ".join(out)
        assert "17 unit(s) exceed 90 days" in combined
        assert "42 days across 150" in combined
        assert "5.5x" in combined
        assert "62.5%" in combined
        assert "60 days" in combined

    def test_missing_data_reports_honest_gap(self):
        out = aba._sentences_inventory({})

        assert out == ["No inventory health data is currently available."]


class TestSentencesSales:

    def test_builds_real_sentences(self):
        facts = {
            "business_health": {
                "sales": {
                    "lead_volume": {"value": 500},
                    "show_rate": {"value": 0.75, "appointments_shown": 300, "appointments_scheduled": 400},
                    "close_rate": {"value": 23.7},
                    "gross_profit": {"value": 192000.5},
                    "pipeline_coverage": {"active_pipeline_count": 88},
                }
            }
        }

        out = aba._sentences_sales(facts)
        combined = " ".join(out)

        assert "500" in combined
        assert "75.0%" in combined
        assert "300 of 400" in combined
        assert "23.7%" in combined
        assert "$192,000.50" in combined
        assert "88" in combined

    def test_missing_data_reports_honest_gap(self):
        assert aba._sentences_sales({}) == ["No sales health data is currently available."]


class TestSentencesService:

    def test_builds_real_sentences(self):
        facts = {
            "business_health": {
                "service": {
                    "ro_volume": {"total": 439, "open": 5},
                    "technician_utilization": {
                        "avg_utilization_pct_today": 88.0,
                        "overloaded_technician_count": 2,
                        "technician_count": 5,
                    },
                    "customer_retention": {"avg_visits_per_year": 1.4, "lost_customers": 17},
                }
            }
        }

        out = aba._sentences_service(facts)
        combined = " ".join(out)

        assert "439" in combined
        assert "5 currently open" in combined
        assert "88.0%" in combined
        assert "2 of 5" in combined
        assert "1.4" in combined
        assert "17" in combined

    def test_missing_data_reports_honest_gap(self):
        assert aba._sentences_service({}) == ["No service health data is currently available."]


class TestSentencesFinance:

    def test_builds_real_sentences_with_accessible_sub_data(self):
        facts = {
            "business_health": {
                "finance": {
                    "funding_time": {"avg_days_in_transit": 3.2, "contracts_in_transit": 8},
                    "collections": {"total_in_queue": 65, "recovery_risk_count": 12},
                    "portfolio_quality": {
                        "total_loans": 315,
                        "total_outstanding_balance": 10384640.39,
                        "total_amount_past_due": 71331.36,
                    },
                    "contract_accuracy": {"not_yet_tracked": True},
                }
            }
        }

        out = aba._sentences_finance(facts)
        combined = " ".join(out)

        assert "3.2 days across 8" in combined
        assert "65 loan(s)" in combined
        assert "12 flagged" in combined
        assert "315 total loan(s)" in combined
        assert "$10,384,640.39" in combined
        assert "no backing data model" in combined

    def test_denied_sub_data_reports_access_error(self):
        facts = {
            "business_health": {
                "finance": {
                    "collections": {"error": "Access denied."},
                    "portfolio_quality": {"error": "Access denied."},
                }
            }
        }

        out = aba._sentences_finance(facts)
        combined = " ".join(out)

        assert "Collections data isn't visible with your current role." in combined
        assert "Portfolio quality data isn't visible with your current role." in combined

    def test_missing_data_reports_honest_gap(self):
        assert aba._sentences_finance({}) == ["No finance health data is currently available."]


class TestSentencesMarketing:

    def test_builds_real_sentences(self):
        facts = {
            "business_health": {
                "marketing": {
                    "lead_volume": {"value": 1005},
                    "roi": {"channel_mix": {"total_revenue": 167396.67, "total_leads": 1005}},
                    "website_traffic": {"total_page_views": 400, "site_count": 2, "bot_views": 50},
                }
            }
        }

        out = aba._sentences_marketing(facts)
        combined = " ".join(out)

        assert "1005" in combined
        assert "$167,396.67" in combined
        assert "not proven multi-touch attribution" in combined
        assert "400 page view(s)" in combined
        assert "2 site(s)" in combined

    def test_denied_roi_reports_access_error(self):
        facts = {"business_health": {"marketing": {"roi": {"error": "Access denied."}}}}

        out = aba._sentences_marketing(facts)

        assert "Marketing ROI data isn't visible with your current role." in out

    def test_missing_data_reports_honest_gap(self):
        assert aba._sentences_marketing({}) == ["No marketing health data is currently available."]


class TestSentencesRisk:

    def test_builds_real_sentences_and_ranks_top_three(self):
        facts = {
            "risk_center": {
                "kpi": {
                    "total_exception_types_active": 7,
                    "total_exception_types": 10,
                    "total_affected_entities": 200,
                    "by_severity": {"critical": 3, "high": 4},
                },
                "categories": {
                    "critical_issues": [
                        {"title": "Vehicles Missing Titles", "count": 129, "severity": "critical"},
                        {"title": "Recon Delays", "count": 60, "severity": "critical"},
                    ],
                    "financial_exceptions": [
                        {"title": "Funding Delays", "count": 31, "severity": "high"},
                        {"title": "Unfunded Contracts", "count": 4, "severity": "medium"},
                    ],
                },
            }
        }

        out = aba._sentences_risk(facts)
        combined = " ".join(out)

        assert "7 of 10 exception types" in combined
        assert "200 entities" in combined
        assert "3 critical" in combined
        # top 3 by count: 129, 60, 31 -- the 4-count item should not appear
        assert "Vehicles Missing Titles: 129" in combined
        assert "Recon Delays: 60" in combined
        assert "Funding Delays: 31" in combined
        assert "Unfunded Contracts: 4" not in combined

    def test_no_active_risk_reports_honest_all_clear(self):
        assert aba._sentences_risk({}) == [
            "No active risks are currently open across Critical, Financial, or Operational categories."
        ]


class TestSentencesRecommendations:

    def test_builds_real_sentences_limited_to_three(self):
        facts = {
            "recommendations": {
                "kpi": {"triggered_count": 9, "total_rules": 12},
                "executive_recommendations": [
                    {"title": "A", "recommendation": "Do A."},
                    {"title": "B", "recommendation": "Do B."},
                    {"title": "C", "recommendation": "Do C."},
                    {"title": "D", "recommendation": "Do D."},
                ],
            }
        }

        out = aba._sentences_recommendations(facts)
        combined = " ".join(out)

        assert "9 of 12 recommendation rules" in combined
        assert "Do A." in combined
        assert "Do C." in combined
        assert "Do D." not in combined

    def test_none_triggered_reports_honest_gap(self):
        assert aba._sentences_recommendations({}) == [
            "No high- or critical-severity recommendations are currently triggered."
        ]


class TestSentencesForecast:

    def test_builds_real_sentences(self):
        facts = {
            "forecasts": {
                "sales": {"gross": {"projected_month_total": 100000.0, "month_to_date": 60000.0}},
                "finance": {"funding": {"note": "Projected off real ledger contracts_funded."}},
                "inventory": {"units_likely_to_sell": {"value": 35}},
            }
        }

        out = aba._sentences_forecast(facts)
        combined = " ".join(out)

        assert "$100,000.00" in combined
        assert "$60,000.00" in combined
        assert "Finance forecast (funding)" in combined
        assert "units likely to sell: 35" in combined

    def test_denied_finance_forecast_skips_gracefully(self):
        facts = {"forecasts": {"finance": {"error": "Access denied."}}}

        out = aba._sentences_forecast(facts)

        # no finance sentence added, and no crash -- falls through to honest gap
        assert out == ["No forward-looking forecast data is currently available for this topic."]

    def test_missing_data_reports_honest_gap(self):
        assert aba._sentences_forecast({}) == [
            "No forward-looking forecast data is currently available for this topic."
        ]


# ---------------------------------------------------------------------------
# _digest()
# ---------------------------------------------------------------------------


class TestDigest:

    def test_combines_first_sentence_of_four_sections(self):
        facts = {
            "business_health": {
                "inventory": {"aging": {"aged_units_by_band": {"91+ days": 5}}},
                "sales": {"lead_volume": {"value": 100}},
            },
            "risk_center": {"kpi": {"total_exception_types_active": 2, "total_exception_types": 10}},
            "recommendations": {"kpi": {"triggered_count": 1, "total_rules": 12}},
        }

        out = aba._digest(facts)

        assert len(out) == 4
        assert "5 unit(s)" in out[0]
        assert "100" in out[1]
        assert "2 of 10" in out[2]
        assert "1 of 12" in out[3]


# ---------------------------------------------------------------------------
# _format_fallback_answer()
# ---------------------------------------------------------------------------


class TestFormatFallbackAnswer:

    def test_matched_topic_uses_topic_builder_with_no_prefix(self):
        facts = {"business_health": {"sales": {"lead_volume": {"value": 100}}}}

        answer = aba._format_fallback_answer("How are sales doing?", facts)

        assert answer.startswith("Total lead volume")
        assert "No specific topic" not in answer

    def test_unmatched_topic_uses_digest_with_prefix(self):
        answer = aba._format_fallback_answer("what's for lunch", {})

        assert answer.startswith("No specific topic was recognized")

    def test_multiple_matched_topics_concatenate(self):
        facts = {
            "business_health": {
                "sales": {"lead_volume": {"value": 100}},
                "finance": {"funding_time": {"avg_days_in_transit": 3.0, "contracts_in_transit": 4}},
            }
        }

        answer = aba._format_fallback_answer("sales and finance funding?", facts)

        assert "lead volume on file is 100" in answer
        assert "funding time" in answer.lower()


# ---------------------------------------------------------------------------
# build_facts_text()
# ---------------------------------------------------------------------------


class TestBuildFactsText:

    def test_includes_every_topic_section(self):
        text = aba.build_facts_text({})

        for topic in aba._TOPIC_BUILDERS:
            assert f"[{topic.upper()}]" in text


# ---------------------------------------------------------------------------
# ask_business_analyst() -- public entrypoint
# ---------------------------------------------------------------------------


def _stub_gather(monkeypatch, sales_lead_volume=100):
    monkeypatch.setattr(aba, "get_business_health_overview", lambda role: {
        "sales": {"lead_volume": {"value": sales_lead_volume}}
    })
    monkeypatch.setattr(aba, "get_risk_center_overview", lambda role: {})
    monkeypatch.setattr(aba, "get_recommendations_overview", lambda role: {})
    monkeypatch.setattr(aba, "get_forecasts_overview", lambda role: {})


class TestAskBusinessAnalyst:

    def test_empty_question_returns_error(self):
        result = aba.ask_business_analyst("", "ADMIN")

        assert result == {"error": "Ask a question first."}

    def test_whitespace_only_question_returns_error(self):
        result = aba.ask_business_analyst("   ", "ADMIN")

        assert "error" in result

    def test_gather_facts_composes_all_four_sources(self, monkeypatch):
        calls = []
        monkeypatch.setattr(aba, "get_business_health_overview", lambda role: calls.append("bh") or {})
        monkeypatch.setattr(aba, "get_risk_center_overview", lambda role: calls.append("rc") or {})
        monkeypatch.setattr(aba, "get_recommendations_overview", lambda role: calls.append("rec") or {})
        monkeypatch.setattr(aba, "get_forecasts_overview", lambda role: calls.append("fc") or {})

        facts = aba.gather_facts("ADMIN")

        assert set(calls) == {"bh", "rc", "rec", "fc"}
        assert set(facts.keys()) == {"business_health", "risk_center", "recommendations", "forecasts"}

    def test_gather_facts_degrades_gracefully_on_raise(self, monkeypatch):
        def _boom(role):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(aba, "get_business_health_overview", _boom)
        monkeypatch.setattr(aba, "get_risk_center_overview", lambda role: {})
        monkeypatch.setattr(aba, "get_recommendations_overview", lambda role: {})
        monkeypatch.setattr(aba, "get_forecasts_overview", lambda role: {})

        facts = aba.gather_facts("ADMIN")

        assert facts["business_health"] == {}

    def test_feature_disabled_returns_honest_fallback(self, monkeypatch):
        _stub_gather(monkeypatch)
        monkeypatch.setattr(aba, "is_feature_enabled", lambda key: False)

        result = aba.ask_business_analyst("How are sales doing?", "ADMIN")

        assert result["ai_generated"] is False
        assert "disabled by your administrator" in result["note"]
        assert "Total lead volume on file is 100" in result["answer"]

    def test_ai_call_falls_back_when_openai_unreachable(self, monkeypatch):
        # This sandbox has no outbound OpenAI network access -- the real call
        # site is exercised for real and is expected to raise, landing in the
        # except branch. Feature flag forced on to reach that call site.
        _stub_gather(monkeypatch)
        monkeypatch.setattr(aba, "is_feature_enabled", lambda key: True)

        result = aba.ask_business_analyst("How are sales doing?", "ADMIN")

        assert result["ai_generated"] is False
        assert "AI phrasing unavailable" in result["note"]
        assert "Total lead volume on file is 100" in result["answer"]

    def test_question_is_echoed_back(self, monkeypatch):
        _stub_gather(monkeypatch)
        monkeypatch.setattr(aba, "is_feature_enabled", lambda key: False)

        result = aba.ask_business_analyst("What about sales?", "ADMIN")

        assert result["question"] == "What about sales?"
