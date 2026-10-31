"""
Test coverage for core/readiness_overview.py -- the Enterprise Readiness
Dashboard: a Department Readiness Heatmap (core/prediction.py's real
all_departments_readiness()), Today's Risks (core/enterprise_risk_center.py's
real get_risk_center_overview() reused verbatim + a small real top-N
ranking), and a real, rules-based Executive Summary template with an
optional isolated-AI polish step that is never load-bearing.

Every external composition point (all_departments_readiness,
get_risk_center_overview, get_recommendations_overview,
polish_executive_summary) is a top-level import into this module's own
namespace, so each is monkeypatched there directly -- this file tests this
module's own composition/ranking/templating logic, not any of those four
functions' own real behavior (each already has, or will get, its own test
file).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.readiness_overview as ro


def _readiness_row(department, confidence_pct, threshold=90.0, ready=None, basis="ledger"):
    if ready is None:
        ready = confidence_pct >= threshold
    return {
        "department": department,
        "confidence_pct": confidence_pct,
        "threshold": threshold,
        "ready": ready,
        "basis": basis,
    }


def _risk_item(key, title, category, severity, count, resolve=None):
    return {
        "key": key,
        "title": title,
        "category": category,
        "severity": severity,
        "count": count,
        "resolve": resolve,
    }


def _fake_risk_center(categories=None, kpi=None):
    def fn(role):
        return {"categories": categories or {}, "kpi": kpi or {}}
    return fn


def _fake_recommendations(exec_recs=None):
    def fn(role):
        return {"executive_recommendations": exec_recs or []}
    return fn


def _exec_rec(title, recommendation, severity="high"):
    return {"title": title, "recommendation": recommendation, "severity": severity}


class TestStatusColor:

    def test_none_is_gray(self):
        assert ro._status_color(None) == "gray"

    def test_at_or_above_green_threshold_is_green(self):
        assert ro._status_color(ro._GREEN_THRESHOLD) == "green"
        assert ro._status_color(ro._GREEN_THRESHOLD + 5) == "green"

    def test_just_below_green_threshold_is_yellow(self):
        assert ro._status_color(ro._GREEN_THRESHOLD - 0.1) == "yellow"

    def test_at_yellow_threshold_is_yellow(self):
        assert ro._status_color(ro._YELLOW_THRESHOLD) == "yellow"

    def test_below_yellow_threshold_is_red(self):
        assert ro._status_color(ro._YELLOW_THRESHOLD - 0.1) == "red"


class TestGetDepartmentHeatmap:

    def test_filters_out_falsy_entries(self, monkeypatch):
        monkeypatch.setattr(ro, "all_departments_readiness", lambda: [
            _readiness_row("sales", 95.0),
            None,
            _readiness_row("service", 70.0),
        ])

        result = ro.get_department_heatmap()

        assert [c["department"] for c in result["covered"]] == ["sales", "service"]
        assert result["covered_count"] == 2

    def test_status_colors_reflect_thresholds(self, monkeypatch):
        monkeypatch.setattr(ro, "all_departments_readiness", lambda: [
            _readiness_row("sales", 95.0),
            _readiness_row("service", 70.0),
            _readiness_row("finance", 30.0),
        ])

        result = ro.get_department_heatmap()
        by_dept = {c["department"]: c for c in result["covered"]}

        assert by_dept["sales"]["status_color"] == "green"
        assert by_dept["service"]["status_color"] == "yellow"
        assert by_dept["finance"]["status_color"] == "red"

    def test_avg_confidence_is_rounded_average(self, monkeypatch):
        monkeypatch.setattr(ro, "all_departments_readiness", lambda: [
            _readiness_row("sales", 90.0),
            _readiness_row("service", 80.0),
            _readiness_row("finance", 70.0),
        ])

        result = ro.get_department_heatmap()

        assert result["avg_confidence_pct"] == 80.0

    def test_avg_confidence_none_when_no_covered_departments(self, monkeypatch):
        monkeypatch.setattr(ro, "all_departments_readiness", lambda: [])

        result = ro.get_department_heatmap()

        assert result["avg_confidence_pct"] is None

    def test_uncovered_departments_are_explicit(self, monkeypatch):
        monkeypatch.setattr(ro, "all_departments_readiness", lambda: [])

        result = ro.get_department_heatmap()

        assert result["uncovered"] == ["operations", "inventory", "administration"]
        assert "Operations" in result["uncovered_note"]


class TestGetTodaysRisks:

    def test_flattens_and_filters_to_active_items_only(self, monkeypatch):
        monkeypatch.setattr(ro, "get_risk_center_overview", _fake_risk_center(categories={
            "critical": [_risk_item("k1", "T1", "critical", "high", 5), _risk_item("k2", "T2", "critical", "high", 0)],
            "financial": [_risk_item("k3", "T3", "financial", "medium", 2)],
        }))

        result = ro.get_todays_risks("ADMIN")

        keys = {r["key"] for r in result["top_risks"]}
        assert "k2" not in keys
        assert keys == {"k1", "k3"}

    def test_sorted_by_severity_then_count_descending(self, monkeypatch):
        monkeypatch.setattr(ro, "get_risk_center_overview", _fake_risk_center(categories={
            "a": [
                _risk_item("low-big", "Low Big", "a", "low", 50),
                _risk_item("critical-small", "Critical Small", "a", "critical", 1),
                _risk_item("high-mid", "High Mid", "a", "high", 10),
            ],
        }))

        result = ro.get_todays_risks("ADMIN")

        assert [r["key"] for r in result["top_risks"]] == ["critical-small", "high-mid", "low-big"]

    def test_limit_is_respected(self, monkeypatch):
        monkeypatch.setattr(ro, "get_risk_center_overview", _fake_risk_center(categories={
            "a": [_risk_item(f"k{i}", f"T{i}", "a", "high", i + 1) for i in range(10)],
        }))

        result = ro.get_todays_risks("ADMIN", limit=3)

        assert len(result["top_risks"]) == 3

    def test_preserves_full_risk_center_and_kpi(self, monkeypatch):
        monkeypatch.setattr(ro, "get_risk_center_overview", _fake_risk_center(categories={"a": []}, kpi={"total": 5}))

        result = ro.get_todays_risks("ADMIN")

        assert result["kpi"] == {"total": 5}
        assert result["risk_center"]["categories"] == {"a": []}

    def test_handles_missing_categories_key_gracefully(self, monkeypatch):
        def fn(role):
            return {"kpi": {}}
        monkeypatch.setattr(ro, "get_risk_center_overview", fn)

        result = ro.get_todays_risks("ADMIN")

        assert result["top_risks"] == []


class TestBuildRawSummary:

    def test_strong_label_at_or_above_green_threshold(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 95.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "strong" in result["text"]
        assert result["facts"]["confidence_label"] == "strong"

    def test_moderate_label_between_thresholds(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 75.0, "covered_count": 2, "covered": [{"department": "sales"}, {"department": "service"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "moderate" in result["text"]

    def test_at_risk_label_below_yellow_threshold(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 30.0, "covered_count": 1, "covered": [{"department": "finance"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "at risk" in result["text"]

    def test_singular_department_wording(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "1 covered department (Sales)" in result["text"]
        assert "departments" not in result["text"]

    def test_overall_none_produces_not_assessed_sentence(self, monkeypatch):
        heatmap = {"avg_confidence_pct": None, "covered_count": 0, "covered": []}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "could not be assessed" in result["text"]
        assert result["facts"]["confidence_label"].startswith("unknown")

    def test_risk_titles_included_capped_at_3(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": [
            {"title": "Risk A", "count": 5},
            {"title": "Risk B", "count": 3},
            {"title": "Risk C", "count": 2},
            {"title": "Risk D", "count": 1},
        ]}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "Risk A (5)" in result["text"]
        assert "Risk D" not in result["text"]

    def test_no_risks_produces_all_clear_sentence(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "No active risks are currently open" in result["text"]

    def test_recommendation_texts_included_capped_at_3(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        recs = [_exec_rec("T1", "Do X."), _exec_rec("T2", "Do Y."), _exec_rec("T3", "Do Z."), _exec_rec("T4", "Do W.")]
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations(recs))

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "Do X." in result["text"]
        assert "Do W." not in result["text"]
        assert len(result["facts"]["top_recommendations"]) == 3

    def test_recommendation_without_text_is_skipped(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        recs = [{"title": "T1", "recommendation": None, "severity": "high"}]
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations(recs))

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "No high- or critical-severity recommendations are currently triggered." in result["text"]

    def test_no_recommendations_produces_none_triggered_sentence(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert "No high- or critical-severity recommendations are currently triggered." in result["text"]

    def test_basis_is_always_real(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        result = ro._build_raw_summary("ADMIN", heatmap, risks)

        assert result["basis"] == "real"


class TestGenerateExecutiveSummary:

    def test_polish_false_skips_the_ai_call_entirely(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"top_risks": []})
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())

        called = []
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: called.append(text))

        result = ro.generate_executive_summary("ADMIN", polish=False)

        assert called == []
        assert result["ai_generated"] is False
        assert result["summary"] == result["text"]

    def test_polish_true_with_a_valid_response_uses_the_polished_text(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"top_risks": []})
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: {"summary": "A polished version."})

        result = ro.generate_executive_summary("ADMIN")

        assert result["ai_generated"] is True
        assert result["summary"] == "A polished version."

    def test_polish_true_with_an_error_falls_back_to_the_real_template(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"top_risks": []})
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: {"error": "no network"})

        result = ro.generate_executive_summary("ADMIN")

        assert result["ai_generated"] is False
        assert result["ai_polish_note"] == "no network"
        assert result["summary"] == result["text"]

    def test_polish_true_with_a_non_dict_response_falls_back_gracefully(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"top_risks": []})
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: None)

        result = ro.generate_executive_summary("ADMIN")

        assert result["ai_generated"] is False
        assert "AI polish unavailable" in result["ai_polish_note"]

    def test_polish_true_with_a_dict_missing_summary_falls_back_gracefully(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"avg_confidence_pct": 90.0, "covered_count": 1, "covered": [{"department": "sales"}]})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"top_risks": []})
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: {"something_else": True})

        result = ro.generate_executive_summary("ADMIN")

        assert result["ai_generated"] is False
        assert "AI polish unavailable" in result["ai_polish_note"]

    def test_uses_provided_heatmap_and_risks_when_given(self, monkeypatch):
        heatmap = {"avg_confidence_pct": 50.0, "covered_count": 1, "covered": [{"department": "finance"}]}
        risks = {"top_risks": []}
        monkeypatch.setattr(ro, "get_recommendations_overview", _fake_recommendations())
        monkeypatch.setattr(ro, "polish_executive_summary", lambda text: {"summary": "polished"})

        called_heatmap = []
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: called_heatmap.append(True) or {})

        ro.generate_executive_summary("ADMIN", heatmap=heatmap, risks=risks)

        assert called_heatmap == []


class TestGetEnterpriseReadinessOverview:

    def test_composes_all_sections(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {"heatmap": True})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {"risks": True})
        monkeypatch.setattr(
            ro,
            "generate_executive_summary",
            lambda role, heatmap=None, risks=None, polish=True: {"summary": "x", "polish_flag": polish},
        )

        result = ro.get_enterprise_readiness_overview("ADMIN")

        assert result["heatmap"] == {"heatmap": True}
        assert result["todays_risks"] == {"risks": True}
        assert result["executive_summary"]["summary"] == "x"
        assert "not_yet_tracked" in result
        assert "generated_at" in result

    def test_polish_summary_flag_is_passed_through(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {})

        captured = {}

        def fake_summary(role, heatmap=None, risks=None, polish=True):
            captured["polish"] = polish
            return {}
        monkeypatch.setattr(ro, "generate_executive_summary", fake_summary)

        ro.get_enterprise_readiness_overview("ADMIN", polish_summary=False)

        assert captured["polish"] is False

    def test_not_yet_tracked_notes_present(self, monkeypatch):
        monkeypatch.setattr(ro, "get_department_heatmap", lambda: {})
        monkeypatch.setattr(ro, "get_todays_risks", lambda role, limit=5: {})
        monkeypatch.setattr(ro, "generate_executive_summary", lambda role, heatmap=None, risks=None, polish=True: {})

        result = ro.get_enterprise_readiness_overview("ADMIN")

        assert "forecast_accuracy" in result["not_yet_tracked"]
        assert "system_stability" in result["not_yet_tracked"]
