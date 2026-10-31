"""Tests for core/network_menu.py -- the Network department's 8-item Top Menu
dispatcher (overview/peer_groups/benchmarks/gap_analysis/trends/forecasts/
playbooks/ai_advisors/opportunities/reporting).

This module makes no graph mutations and adds no role gate of its own -- every
function is a pure composition over other already-real engines, reused via
module-level `from X import Y` bindings (all directly monkeypatchable on the
`core.network_menu` module alias) except `ai_advisors()`'s one deferred import
(`from core.network_advisors import list_advisors`, done inside the function
body to avoid a real circular import -- must be patched via the STRING-TARGET
form, `monkeypatch.setattr("core.network_advisors.list_advisors", fake)`, not
via the module alias).

Two functions call SIBLING functions defined in this very module rather than
an external engine: `forecasts()` calls `gap_analysis(role)`, and `reporting()`
calls `benchmarks(role)`/`gap_analysis(role)`/`opportunities(role)`/
`trends(role)`/`forecasts(role)`/`playbooks(role)`. Both are tested as pure
composition/dispatch logic by monkeypatching those SAME-MODULE functions
directly on the module alias (e.g. `monkeypatch.setattr(nm, "gap_analysis",
fake)`) -- Python resolves a bare-name call like `gap_analysis(role)` via the
module's own global namespace at call time, so patching the module attribute
correctly intercepts it. Each of those underlying functions is separately
covered by its own dedicated test class exercising its real logic against
mocked lower-level engines.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.network_menu as nm


# ---------------------------------------------------------------------------
# _gap_severity -- pure function, no mocking needed
# ---------------------------------------------------------------------------


class TestGapSeverity:

    def test_not_an_opportunity_returns_none(self):
        assert nm._gap_severity(30.0, False) is None

    def test_none_peer_gap_pct_returns_none(self):
        assert nm._gap_severity(None, True) is None

    def test_high_at_boundary(self):
        assert nm._gap_severity(25.0, True) == "high"

    def test_high_above_boundary(self):
        assert nm._gap_severity(40.0, True) == "high"

    def test_negative_pct_uses_absolute_value(self):
        assert nm._gap_severity(-30.0, True) == "high"

    def test_medium_at_boundary(self):
        assert nm._gap_severity(10.0, True) == "medium"

    def test_medium_between_boundaries(self):
        assert nm._gap_severity(15.0, True) == "medium"

    def test_low_below_medium_boundary(self):
        assert nm._gap_severity(5.0, True) == "low"

    def test_low_zero(self):
        assert nm._gap_severity(0.0, True) == "low"


# ---------------------------------------------------------------------------
# _enrich_gap
# ---------------------------------------------------------------------------


class TestEnrichGap:

    def test_dollar_entry_present_populates_revenue_impact(self, monkeypatch):
        monkeypatch.setattr(
            nm, "get_root_causes",
            lambda department, kpi, label=None: {"causes": [{"finding": "slow response"}], "note": None},
        )
        g = {"department": "sales", "kpi": "close_rate", "label": "Close Rate"}
        dollar_lookup = {
            ("sales", "close_rate"): {
                "dollar_impact_monthly": 5000.0,
                "annualized_dollar_impact": 60000.0,
                "conversion_method": "derived_per_unit_real_value",
                "real_inputs_used": {"gross_profit_per_unit": 4500.0},
                "not_convertible_reason": None,
                "unit_impact": {"additional_units_monthly": 1.5},
                "portfolio_exposure_impact": None,
            }
        }

        nm._enrich_gap(g, dollar_lookup)

        assert g["revenue_impact"]["dollar_impact_monthly"] == 5000.0
        assert g["revenue_impact"]["annualized_dollar_impact"] == 60000.0
        assert g["revenue_impact"]["conversion_method"] == "derived_per_unit_real_value"
        assert g["revenue_impact"]["unit_impact"] == {"additional_units_monthly": 1.5}
        assert g["root_causes"] == [{"finding": "slow response"}]
        assert g["root_cause_note"] is None

    def test_no_dollar_entry_leaves_revenue_impact_none(self, monkeypatch):
        monkeypatch.setattr(
            nm, "get_root_causes",
            lambda department, kpi, label=None: {"causes": [], "note": "No diagnostic mapped."},
        )
        g = {"department": "service", "kpi": "hours_per_ro", "label": "Hours Per RO"}

        nm._enrich_gap(g, {})

        assert g["revenue_impact"] is None
        assert g["root_causes"] == []
        assert g["root_cause_note"] == "No diagnostic mapped."

    def test_root_causes_always_fetched_regardless_of_dollar_lookup(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nm, "get_root_causes",
            lambda department, kpi, label=None: calls.append((department, kpi, label)) or {"causes": [], "note": None},
        )
        g = {"department": "finance", "kpi": "delinquency_rate_pct", "label": "Delinquency Rate"}

        nm._enrich_gap(g, {})

        assert calls == [("finance", "delinquency_rate_pct", "Delinquency Rate")]


# ---------------------------------------------------------------------------
# overview()
# ---------------------------------------------------------------------------


def _dept_entry(department, title="Title", percentile_rank=50.0, primary_kpi=None,
                 this_value=None, peer_values=None, kpi_key=None):
    kpi_key = kpi_key or primary_kpi
    entry = {
        "department": department,
        "title": title,
        "percentile_rank": percentile_rank,
        "primary_kpi": primary_kpi,
    }
    kpis = {}
    if kpi_key is not None and this_value is not None:
        kpis[kpi_key] = {"value": this_value, "label": kpi_key, "format": "currency"}
    entry["this_dealer"] = {"kpis": kpis}
    peers = []
    if kpi_key is not None and peer_values is not None:
        for v in peer_values:
            peers.append({"kpis": {kpi_key: {"value": v}}})
    entry["peers"] = peers
    return entry


class TestOverview:

    def test_error_passthrough_short_circuits_before_audit(self, monkeypatch):
        audit_called = []
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"error": "denied"})
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: audit_called.append(role) or {})

        result = nm.overview("SALES")

        assert result == {"error": "denied"}
        assert audit_called == []

    def test_empty_departments(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendation_count": 0})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {
            "total_monthly_opportunity": 0.0, "total_annualized_opportunity": 0.0,
            "excluded_departments": [], "basis_notice": "note",
        })
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=5: {"largest_opportunities": []})
        def template_summary(role, polish=True):
            assert polish is False, "Passive dashboard reads must not invoke a model"
            return {"summary": "n/a"}
        monkeypatch.setattr(nm, "generate_executive_summary", template_summary)

        result = nm.overview("ADMIN")

        assert result["department_rankings"] == []
        assert result["peer_comparison_snapshot"] == []
        assert result["opportunity_tracker"]["potential_gross_opportunity_monthly"] is None
        assert result["network_percentile_rank"]["avg_pct"] is None

    def test_full_path_computes_snapshot_and_totals(self, monkeypatch):
        departments = [
            _dept_entry("sales", title="Sales", percentile_rank=40.0, primary_kpi="gross_profit",
                        this_value=3000.0, peer_values=[4000.0, 5000.0]),
            _dept_entry("service", title="Service", percentile_rank=80.0, primary_kpi="ro_count",
                        this_value=500.0, peer_values=[300.0, 200.0]),
        ]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendation_count": 7})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": [{"department": "sales"}]})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {
            "total_monthly_opportunity": 12000.0, "total_annualized_opportunity": 144000.0,
            "excluded_departments": ["executive"], "basis_notice": "note",
        })
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=5: {"largest_opportunities": [{"kpi": "gross_profit"}]})
        monkeypatch.setattr(nm, "generate_executive_summary", lambda role, polish=True: {"summary": "text", "basis": "real_rules"})

        result = nm.overview("ADMIN")

        assert len(result["department_rankings"]) == 2
        assert result["department_rankings"][0] == {"department": "sales", "title": "Sales", "percentile_rank": 40.0}
        assert result["network_percentile_rank"]["avg_pct"] == 60.0

        snapshot = result["peer_comparison_snapshot"]
        assert len(snapshot) == 2
        sales_snap = next(s for s in snapshot if s["department"] == "sales")
        assert sales_snap["you"] == 3000.0
        assert sales_snap["average_peer"] == 4500.0
        assert sales_snap["best_peer"] == 5000.0

        # sales: peer_avg(4500) - this(3000) = 1500 (opportunity, positive)
        # service: peer_avg(250) - this(500) = -250 (this dealer ahead, negative, not counted)
        assert result["opportunity_tracker"]["potential_gross_opportunity_monthly"] == 1500.0

        assert result["dollar_opportunity"]["monthly"] == 12000.0
        assert result["dollar_opportunity"]["annualized"] == 144000.0
        assert result["largest_opportunities"] == [{"kpi": "gross_profit"}]
        assert result["executive_summary"] == {"summary": "text", "basis": "real_rules"}
        assert result["active_recommendations"]["count"] == 7

    def test_department_without_primary_kpi_skipped_from_snapshot_but_kept_in_rankings(self, monkeypatch):
        departments = [_dept_entry("marketing", title="Marketing", percentile_rank=None, primary_kpi=None)]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {})
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=5: {})
        monkeypatch.setattr(nm, "generate_executive_summary", lambda role, polish=True: {})

        result = nm.overview("ADMIN")

        assert len(result["department_rankings"]) == 1
        assert result["department_rankings"][0]["department"] == "marketing"
        assert result["peer_comparison_snapshot"] == []

    def test_audit_error_dict_degrades_active_recommendations_to_none(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"error": "denied"})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {})
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=5: {})
        monkeypatch.setattr(nm, "generate_executive_summary", lambda role, polish=True: {})

        result = nm.overview("SALES")

        assert result["active_recommendations"]["count"] is None


# ---------------------------------------------------------------------------
# peer_groups()
# ---------------------------------------------------------------------------


class TestPeerGroups:

    def test_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"error": "denied"})

        assert nm.peer_groups("SALES") == {"error": "denied"}

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {
            "peer_pools": [{"key": "default"}, {"key": "elite_group"}],
            "peer_pool": "default",
            "departments": [{"department": "sales"}, {"department": "service"}],
        })

        result = nm.peer_groups("ADMIN")

        assert result["peer_pools"] == [{"key": "default"}, {"key": "elite_group"}]
        assert result["active_peer_pool"] == "default"
        assert result["active_peer_group"]["labels"] == nm.PEER_LABELS
        assert result["active_peer_group"]["basis"] == "simulated_peer_data"
        assert result["comparison_settings"]["departments_compared"] == ["sales", "service"]
        assert "not_yet_tracked" in result


# ---------------------------------------------------------------------------
# benchmarks()
# ---------------------------------------------------------------------------


class TestBenchmarksFn:

    def test_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role, **kw: {"error": "denied"})

        assert nm.benchmarks("SALES") == {"error": "denied"}

    def test_no_peer_pool_calls_without_kwarg(self, monkeypatch):
        calls = []

        def fake(role, peer_pool=None):
            calls.append((role, peer_pool))
            return {"departments": [], "peer_pool": "default", "peer_pools": []}

        monkeypatch.setattr(nm, "get_network_benchmarks_api", fake)

        nm.benchmarks("ADMIN")

        # called via `get_network_benchmarks_api(role)` (no peer_pool kwarg) when peer_pool is falsy
        assert calls == [("ADMIN", None)]

    def test_peer_pool_override_passed_through(self, monkeypatch):
        calls = []

        def fake(role, peer_pool=None):
            calls.append((role, peer_pool))
            return {"departments": [], "peer_pool": peer_pool, "peer_pools": []}

        monkeypatch.setattr(nm, "get_network_benchmarks_api", fake)

        result = nm.benchmarks("ADMIN", peer_pool="elite_group")

        assert calls == [("ADMIN", "elite_group")]
        assert result["peer_pool"] == "elite_group"

    def test_full_path_shape(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {
            "departments": [{"department": "sales", "percentile_rank": 60.0}],
            "peer_pool": "default",
            "peer_pools": [{"key": "default"}],
        })

        result = nm.benchmarks("ADMIN")

        assert result["department_benchmarks"] == [{"department": "sales", "percentile_rank": 60.0}]
        assert result["peer_pool"] == "default"
        assert result["peer_pools"] == [{"key": "default"}]
        assert "note" in result
        assert "not_yet_tracked" in result


# ---------------------------------------------------------------------------
# gap_analysis()
# ---------------------------------------------------------------------------


def _direction(higher_is_better, direction, is_opportunity, opportunity_gap):
    return {
        "higher_is_better": higher_is_better,
        "direction": direction,
        "is_opportunity": is_opportunity,
        "opportunity_gap": opportunity_gap,
    }


class TestGapAnalysis:

    def test_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"error": "denied"})

        assert nm.gap_analysis("SALES") == {"error": "denied"}

    def test_empty_departments_skips_dollar_lookup(self, monkeypatch):
        dollar_called = []
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_dollar_denominated_gaps", lambda role: dollar_called.append(role) or {"gaps": []})

        result = nm.gap_analysis("ADMIN")

        assert result["largest_gaps"] == []
        assert result["largest_opportunity_gaps"] == []
        assert result["all_gaps"] == []
        assert dollar_called == []

    def test_non_numeric_this_value_skipped(self, monkeypatch):
        departments = [{
            "department": "sales",
            "this_dealer": {"kpis": {"note": {"value": "n/a"}}},
            "peers": [{"kpis": {"note": {"value": 5.0}}}],
        }]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})

        result = nm.gap_analysis("ADMIN")

        assert result["all_gaps"] == []

    def test_kpi_with_no_peer_values_skipped(self, monkeypatch):
        departments = [{
            "department": "sales",
            "this_dealer": {"kpis": {"units_sold": {"value": 20.0}}},
            "peers": [{"kpis": {}}],
        }]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})

        result = nm.gap_analysis("ADMIN")

        assert result["all_gaps"] == []

    def test_peer_avg_zero_gives_none_peer_gap_pct(self, monkeypatch):
        departments = [{
            "department": "sales",
            "this_dealer": {"kpis": {"metric": {"value": 5.0, "label": "Metric", "format": "count"}}},
            "peers": [{"kpis": {"metric": {"value": 0.0}}}],
        }]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})
        monkeypatch.setattr(nm, "gap_direction", lambda department, kpi, gap: _direction(True, "even", False, None))

        result = nm.gap_analysis("ADMIN")

        assert result["all_gaps"][0]["peer_gap_pct"] is None

    def test_full_path_sorting_severity_and_opportunity_filtering(self, monkeypatch):
        # sales.gross_profit: this=3000, peers=[4000,5000] -> peer_avg=4500, gap=1500 -> opportunity
        # sales.close_rate:  this=30,   peers=[20,10]      -> peer_avg=15,   gap=-15  -> ahead (not an opportunity)
        departments = [{
            "department": "sales",
            "this_dealer": {"kpis": {
                "gross_profit": {"value": 3000.0, "label": "Gross Profit", "format": "currency"},
                "close_rate": {"value": 30.0, "label": "Close Rate", "format": "percent"},
            }},
            "peers": [
                {"kpis": {"gross_profit": {"value": 4000.0}, "close_rate": {"value": 20.0}}},
                {"kpis": {"gross_profit": {"value": 5000.0}, "close_rate": {"value": 10.0}}},
            ],
        }]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})

        def fake_gap_direction(department, kpi, gap):
            if kpi == "gross_profit":
                return _direction(True, "behind", True, 1500.0)
            return _direction(True, "ahead", False, None)

        monkeypatch.setattr(nm, "gap_direction", fake_gap_direction)
        monkeypatch.setattr(nm, "get_dollar_denominated_gaps", lambda role: {"gaps": []})
        monkeypatch.setattr(nm, "get_root_causes", lambda department, kpi, label=None: {"causes": [], "note": None})

        result = nm.gap_analysis("ADMIN")

        assert len(result["all_gaps"]) == 2
        # |1500| > |-15|, so gross_profit sorts first in largest_gaps
        assert result["largest_gaps"][0]["kpi"] == "gross_profit"
        assert result["largest_gaps"][1]["kpi"] == "close_rate"

        assert len(result["largest_opportunity_gaps"]) == 1
        assert result["largest_opportunity_gaps"][0]["kpi"] == "gross_profit"

        gross_profit_gap = next(g for g in result["all_gaps"] if g["kpi"] == "gross_profit")
        assert gross_profit_gap["is_opportunity"] is True
        assert gross_profit_gap["severity"] == "high"
        # 1500 gets enriched (it's an opportunity in largest_gaps/largest_opportunity_gaps)
        assert gross_profit_gap["root_causes"] == []

        close_rate_gap = next(g for g in result["all_gaps"] if g["kpi"] == "close_rate")
        assert close_rate_gap["is_opportunity"] is False
        assert close_rate_gap["severity"] is None
        # not an opportunity -> never enriched, stays at its initialized None
        assert close_rate_gap["root_causes"] is None

    def test_caps_largest_gaps_at_ten(self, monkeypatch):
        kpis = {f"kpi_{i}": {"value": float(i), "label": f"KPI {i}", "format": "count"} for i in range(15)}
        peers = [{"kpis": {f"kpi_{i}": {"value": float(i + 100)} for i in range(15)}}]
        departments = [{"department": "sales", "this_dealer": {"kpis": kpis}, "peers": peers}]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})
        monkeypatch.setattr(nm, "gap_direction", lambda department, kpi, gap: _direction(True, "behind", True, abs(gap)))
        monkeypatch.setattr(nm, "get_dollar_denominated_gaps", lambda role: {"gaps": []})
        monkeypatch.setattr(nm, "get_root_causes", lambda department, kpi, label=None: {"causes": [], "note": None})

        result = nm.gap_analysis("ADMIN")

        assert len(result["all_gaps"]) == 15
        assert len(result["largest_gaps"]) == 10
        assert len(result["largest_opportunity_gaps"]) == 10

    def test_dollar_denominated_gaps_error_dict_yields_empty_lookup_but_still_enriches_root_causes(self, monkeypatch):
        departments = [{
            "department": "sales",
            "this_dealer": {"kpis": {"gross_profit": {"value": 3000.0, "label": "Gross Profit", "format": "currency"}}},
            "peers": [{"kpis": {"gross_profit": {"value": 5000.0}}}],
        }]
        monkeypatch.setattr(nm, "get_network_benchmarks_api", lambda role: {"departments": departments})
        monkeypatch.setattr(nm, "gap_direction", lambda department, kpi, gap: _direction(True, "behind", True, gap))
        monkeypatch.setattr(nm, "get_dollar_denominated_gaps", lambda role: {"error": "denied"})
        root_cause_calls = []
        monkeypatch.setattr(
            nm, "get_root_causes",
            lambda department, kpi, label=None: root_cause_calls.append((department, kpi)) or {"causes": [], "note": None},
        )

        result = nm.gap_analysis("ADMIN")

        assert result["all_gaps"][0]["revenue_impact"] is None
        assert root_cause_calls == [("sales", "gross_profit")]


# ---------------------------------------------------------------------------
# trends()
# ---------------------------------------------------------------------------


class TestTrends:

    def test_error_without_kpis_key_short_circuits(self, monkeypatch):
        monkeypatch.setattr(nm, "INTELLIGENCE_DEPARTMENTS", ["sales", "service"])
        history_called = []

        def fake_get_department_api(role, department):
            if department == "sales":
                return {"error": "denied"}
            return {"kpis": []}

        monkeypatch.setattr(nm, "get_department_api", fake_get_department_api)
        monkeypatch.setattr(nm, "get_department_trend_history", lambda dept, days: history_called.append(dept) or {})
        monkeypatch.setattr(nm, "get_bhph_kpis_with_trend", lambda role: None)

        result = nm.trends("SALES")

        assert result == {"error": "denied"}
        # short-circuits before ever reaching the trend-history call for "sales"
        assert history_called == []

    def test_error_with_kpis_key_is_not_fatal(self, monkeypatch):
        monkeypatch.setattr(nm, "INTELLIGENCE_DEPARTMENTS", ["sales"])
        monkeypatch.setattr(nm, "get_department_api", lambda role, department: {"error": "partial", "kpis": []})
        monkeypatch.setattr(nm, "get_department_trend_history", lambda dept, days: {"days_with_data": 0, "days_requested": days, "kpis": {}})
        monkeypatch.setattr(nm, "get_bhph_kpis_with_trend", lambda role: None)

        result = nm.trends("SALES")

        assert "error" not in result
        assert result["department_trends"]["sales"] == []

    def test_full_path_extracts_kpi_fields_and_history(self, monkeypatch):
        monkeypatch.setattr(nm, "INTELLIGENCE_DEPARTMENTS", ["sales", "service"])

        def fake_get_department_api(role, department):
            return {"kpis": [
                {"key": f"{department}_kpi", "label": "Label", "value": 10.0,
                 "delta_pct": 5.0, "has_history": True, "compared_to": "yesterday"},
            ]}

        history_calls = []

        def fake_history(department, days):
            history_calls.append((department, days))
            return {"days_with_data": 3, "days_requested": days, "kpis": {"a": []}}

        monkeypatch.setattr(nm, "get_department_api", fake_get_department_api)
        monkeypatch.setattr(nm, "get_department_trend_history", fake_history)
        monkeypatch.setattr(nm, "get_bhph_kpis_with_trend", lambda role: None)

        result = nm.trends("ADMIN", history_days=30)

        assert result["department_trends"]["sales"] == [{
            "key": "sales_kpi", "label": "Label", "value": 10.0,
            "delta_pct": 5.0, "has_history": True, "compared_to": "yesterday",
        }]
        assert history_calls == [("sales", 30), ("service", 30)]
        assert result["department_history"]["sales"]["days_with_data"] == 3
        assert result["history_days_requested"] == 30
        assert nm.BHPH_DEPARTMENT_KEY not in result["department_trends"]

    def test_bhph_included_when_present(self, monkeypatch):
        monkeypatch.setattr(nm, "INTELLIGENCE_DEPARTMENTS", [])
        monkeypatch.setattr(nm, "get_bhph_kpis_with_trend", lambda role: {"kpis": [
            {"key": "yield_pct", "label": "Yield", "value": 0.88, "delta_pct": None, "has_history": False, "compared_to": None},
        ]})
        history_calls = []
        monkeypatch.setattr(nm, "get_department_trend_history", lambda dept, days: history_calls.append((dept, days)) or {"days_with_data": 1, "days_requested": days, "kpis": {}})

        result = nm.trends("ADMIN")

        assert nm.BHPH_DEPARTMENT_KEY in result["department_trends"]
        assert result["department_trends"][nm.BHPH_DEPARTMENT_KEY][0]["key"] == "yield_pct"
        assert (nm.BHPH_DEPARTMENT_KEY, nm.DEFAULT_HISTORY_DAYS) in history_calls


# ---------------------------------------------------------------------------
# forecasts()
# ---------------------------------------------------------------------------


class TestForecasts:

    def test_error_passthrough_from_gap_analysis(self, monkeypatch):
        monkeypatch.setattr(nm, "gap_analysis", lambda role: {"error": "denied"})

        assert nm.forecasts("SALES") == {"error": "denied"}

    def test_empty_all_gaps(self, monkeypatch):
        monkeypatch.setattr(nm, "gap_analysis", lambda role: {"all_gaps": []})

        result = nm.forecasts("ADMIN")

        assert result["projectable_kpi_count"] == 0
        assert result["not_projectable_kpi_count"] == 0
        assert result["closing_gaps"] == []
        assert result["widening_gaps"] == []
        assert result["all_projections"] == []

    def test_full_path_projectable_and_not_projectable_split(self, monkeypatch):
        gaps = {"all_gaps": [
            {"department": "sales", "kpi": "gross_profit", "peer_average": 5000.0,
             "higher_is_better": True, "label": "Gross Profit", "format": "currency"},
            {"department": "service", "kpi": "ro_count", "peer_average": 400.0,
             "higher_is_better": True, "label": "RO Count", "format": "count"},
            {"department": "finance", "kpi": "delinquency_rate_pct", "peer_average": 15.0,
             "higher_is_better": False, "label": "Delinquency Rate", "format": "percent"},
        ]}
        monkeypatch.setattr(nm, "gap_analysis", lambda role: gaps)

        calls = []

        def fake_project(department, kpi, peer_average, higher_is_better, days_history=None, project_days=None):
            calls.append((department, kpi, peer_average, higher_is_better, days_history, project_days))
            if kpi == "gross_profit":
                return {"projectable": True, "gap_trend": "closing", "current_gap": 800.0}
            if kpi == "ro_count":
                return {"projectable": True, "gap_trend": "widening", "current_gap": 50.0}
            return {"projectable": False, "reason": "not enough history"}

        monkeypatch.setattr(nm, "project_gap_closure", fake_project)

        result = nm.forecasts("ADMIN", project_days=60, history_days=45)

        assert result["projectable_kpi_count"] == 2
        assert result["not_projectable_kpi_count"] == 1
        assert len(result["closing_gaps"]) == 1
        assert result["closing_gaps"][0]["label"] == "Gross Profit"
        assert result["closing_gaps"][0]["format"] == "currency"
        assert len(result["widening_gaps"]) == 1
        assert result["widening_gaps"][0]["label"] == "RO Count"
        assert len(result["all_projections"]) == 3

        # verify project_gap_closure called with the right positional args + kwargs
        assert ("sales", "gross_profit", 5000.0, True, 45, 60) in calls
        assert ("finance", "delinquency_rate_pct", 15.0, False, 45, 60) in calls

    def test_closing_and_widening_sorted_by_current_gap_descending(self, monkeypatch):
        gaps = {"all_gaps": [
            {"department": "sales", "kpi": "a", "peer_average": 1.0, "higher_is_better": True, "label": "A", "format": "count"},
            {"department": "sales", "kpi": "b", "peer_average": 1.0, "higher_is_better": True, "label": "B", "format": "count"},
        ]}
        monkeypatch.setattr(nm, "gap_analysis", lambda role: gaps)

        def fake_project(department, kpi, peer_average, higher_is_better, days_history=None, project_days=None):
            if kpi == "a":
                return {"projectable": True, "gap_trend": "closing", "current_gap": 10.0}
            return {"projectable": True, "gap_trend": "closing", "current_gap": 90.0}

        monkeypatch.setattr(nm, "project_gap_closure", fake_project)

        result = nm.forecasts("ADMIN")

        assert [p["label"] for p in result["closing_gaps"]] == ["B", "A"]


# ---------------------------------------------------------------------------
# playbooks()
# ---------------------------------------------------------------------------


class TestPlaybooks:

    def test_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"error": "denied"})

        assert nm.playbooks("SALES") == {"error": "denied"}

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendations": [{"key": "rec1"}]})
        monkeypatch.setattr(nm, "get_playbook_library", lambda role: {
            "playbooks": [{"key": "slow_lead_response", "is_currently_active": True}],
            "playbook_count": 13,
            "currently_active_count": 7,
            "note": "library note",
        })

        result = nm.playbooks("ADMIN")

        assert result["library"] == [{"key": "slow_lead_response", "is_currently_active": True}]
        assert result["playbook_count"] == 13
        assert result["currently_active_count"] == 7
        assert result["library_note"] == "library note"
        assert result["related_recommendations"] == [{"key": "rec1"}]


# ---------------------------------------------------------------------------
# ai_advisors() -- deferred import, needs the string-target monkeypatch form
# ---------------------------------------------------------------------------


class TestAiAdvisors:

    def test_full_path(self, monkeypatch):
        calls = []

        def fake_list_advisors():
            calls.append(True)
            return [{"department": "sales"}, {"department": "service"}]

        monkeypatch.setattr("core.network_advisors.list_advisors", fake_list_advisors)

        result = nm.ai_advisors("ADMIN")

        assert result["advisors"] == [{"department": "sales"}, {"department": "service"}]
        assert "note" in result
        assert calls == [True]


# ---------------------------------------------------------------------------
# opportunities()
# ---------------------------------------------------------------------------


class TestOpportunities:

    def test_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"error": "denied"})

        assert nm.opportunities("SALES") == {"error": "denied"}

    def test_bucketing_and_unmapped_category_dropped(self, monkeypatch):
        recommendations = [
            {"category": "profit_leak", "severity": "high"},
            {"category": "automation_opportunity", "severity": "medium"},
            {"category": "network_benchmark", "severity": "low"},
            {"category": "data_readiness", "severity": "low"},
            {"category": "revenue_opportunities", "severity": "high"},  # not a real mapped category key
            {"category": "totally_unknown", "severity": "high"},
        ]
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {
            "recommendations": recommendations, "recommendation_count": 6,
        })
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {
            "total_monthly_opportunity": 0.0, "total_annualized_opportunity": 0.0,
            "excluded_departments": [], "basis_notice": "note",
        })
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=10: {"largest_opportunities": []})

        result = nm.opportunities("ADMIN")

        assert result["revenue_opportunities"] == []
        assert len(result["cost_reduction_opportunities"]) == 1
        assert len(result["staffing_recommendations"]) == 1
        assert len(result["operational_improvements"]) == 1
        assert len(result["process_improvements"]) == 1
        assert result["recommendation_count"] == 6

    def test_recommendation_count_defaults_to_zero(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendations": []})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {})
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=10: {})

        result = nm.opportunities("ADMIN")

        assert result["recommendation_count"] == 0

    def test_largest_opportunities_called_with_limit_ten(self, monkeypatch):
        calls = []
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendations": []})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": []})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {})
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=10: calls.append(limit) or {"largest_opportunities": []})

        nm.opportunities("ADMIN")

        assert calls == [10]

    def test_dollar_opportunities_block_shape(self, monkeypatch):
        monkeypatch.setattr(nm, "get_network_audit_api", lambda role: {"recommendations": []})
        monkeypatch.setattr(nm, "get_department_dollar_opportunities", lambda role: {"departments": [{"department": "sales"}]})
        monkeypatch.setattr(nm, "get_total_identified_opportunity", lambda role: {
            "total_monthly_opportunity": 5000.0, "total_annualized_opportunity": 60000.0,
            "excluded_departments": ["executive"], "basis_notice": "note text",
        })
        monkeypatch.setattr(nm, "get_largest_opportunities", lambda role, limit=10: {"largest_opportunities": [{"kpi": "x"}]})

        result = nm.opportunities("ADMIN")

        assert result["dollar_opportunities"]["by_department"] == [{"department": "sales"}]
        assert result["dollar_opportunities"]["grand_total_monthly"] == 5000.0
        assert result["dollar_opportunities"]["grand_total_annualized"] == 60000.0
        assert result["dollar_opportunities"]["excluded_departments"] == ["executive"]
        assert result["dollar_opportunities"]["largest_opportunities"] == [{"kpi": "x"}]
        assert result["dollar_opportunities"]["basis_notice"] == "note text"


# ---------------------------------------------------------------------------
# reporting() -- composition over the module's own sibling functions
# ---------------------------------------------------------------------------


class TestReporting:

    def _patch_all(self, monkeypatch, bench=None, gaps=None, opps=None, trend=None, forecast=None, playbook_lib=None, call_stats=None):
        monkeypatch.setattr(nm, "benchmarks", lambda role: bench if bench is not None else {})
        monkeypatch.setattr(nm, "gap_analysis", lambda role: gaps if gaps is not None else {})
        monkeypatch.setattr(nm, "opportunities", lambda role: opps if opps is not None else {})
        monkeypatch.setattr(nm, "trends", lambda role: trend if trend is not None else {})
        monkeypatch.setattr(nm, "forecasts", lambda role: forecast if forecast is not None else {})
        monkeypatch.setattr(nm, "playbooks", lambda role: playbook_lib if playbook_lib is not None else {})
        monkeypatch.setattr(nm, "get_call_stats", lambda key: dict(call_stats) if call_stats is not None else {"attempted": 0})

    def test_full_happy_path(self, monkeypatch):
        self._patch_all(
            monkeypatch,
            bench={"department_benchmarks": [
                {"department": "sales", "percentile_rank": 40.0},
                {"department": "service", "percentile_rank": 80.0},
            ]},
            gaps={"all_gaps": [
                {"department": "sales", "kpi": "gross_profit", "is_opportunity": True, "opportunity_gap": 1500.0},
                {"department": "service", "kpi": "ro_count", "is_opportunity": False, "opportunity_gap": None},
                {"department": "finance", "kpi": "yield_pct", "is_opportunity": True, "opportunity_gap": "not-a-number"},
            ]},
            opps={
                "revenue_opportunities": [],
                "cost_reduction_opportunities": [{"key": "a", "severity": "low"}],
                "operational_improvements": [{"key": "b", "severity": "high"}],
                "staffing_recommendations": [{"key": "c", "severity": "medium"}],
                "process_improvements": [{"key": "d", "severity": None}],
            },
            trend={
                "department_trends": {"sales": []},
                "history_days_requested": 90,
                "department_history": {
                    "sales": {"days_with_data": 5, "days_requested": 90, "kpis": {"a": [], "b": []}},
                },
            },
            forecast={
                "basis_notice": "note",
                "project_days": 30,
                "history_days_considered": 90,
                "projectable_kpi_count": 2,
                "not_projectable_kpi_count": 1,
                "closing_gaps": [{"label": "A"}, {"label": "B"}],
                "widening_gaps": [{"label": "C"}],
            },
            playbook_lib={
                "playbook_count": 13,
                "currently_active_count": 7,
                "library": [
                    {"automation_score": {"tier": 0}},
                    {"automation_score": {"tier": 1}},
                    {"automation_score": {"tier": 1}},
                    {"automation_score": {"tier": 3}},
                    {},
                ],
            },
            call_stats={"attempted": 10, "succeeded": 2, "fell_back": 8, "blocked": 0},
        )

        result = nm.reporting("ADMIN")

        assert result["benchmark_reports"]["department_rankings"] == [
            {"department": "sales", "percentile_rank": 40.0},
            {"department": "service", "percentile_rank": 80.0},
        ]
        assert result["benchmark_reports"]["percentile_performance_avg"] == 60.0

        # only "sales" gross_profit (1500.0, is_opportunity) counts; the string opportunity_gap is skipped
        assert result["executive_reports"]["total_opportunity_monthly"] == 1500.0
        assert result["executive_reports"]["network_standing_avg_percentile"] == 60.0

        priorities = result["executive_reports"]["strategic_priorities"]
        assert [p["key"] for p in priorities] == ["b", "c", "a", "d"]  # high, medium, low, then unranked(default 3)

        assert result["growth_forecast_report"]["closing_gap_count"] == 2
        assert result["growth_forecast_report"]["widening_gap_count"] == 1
        assert result["growth_forecast_report"]["top_closing_gaps"] == [{"label": "A"}, {"label": "B"}]

        assert result["historical_trend_report"]["coverage_by_department"] == [
            {"department": "sales", "days_with_data": 5, "days_requested": 90, "kpi_count": 2},
        ]

        assert result["playbook_adoption_report"]["playbook_count"] == 13
        assert result["playbook_adoption_report"]["currently_active_count"] == 7
        assert result["playbook_adoption_report"]["automation_tier_breakdown"] == {
            "tier_0_no_automation_path": 1,
            "tier_1_automatable_not_configured": 2,
            "tier_2_reserved": 0,
            "tier_3_already_automated": 1,
        }

        assert result["ai_advisor_usage_report"]["attempted"] == 10
        assert "note" in result["ai_advisor_usage_report"]

        assert result["department_intelligence"] == nm._DI_GAP_NOTE
        assert "not_yet_tracked" in result

    def test_degrades_gracefully_when_bench_missing_key(self, monkeypatch):
        self._patch_all(monkeypatch, bench={"error": "denied"}, gaps={}, opps={}, trend={}, forecast={}, playbook_lib={})

        result = nm.reporting("SALES")

        assert result["benchmark_reports"]["department_rankings"] is None
        assert result["benchmark_reports"]["percentile_performance_avg"] is None

    def test_degrades_gracefully_when_gaps_missing_all_gaps_key(self, monkeypatch):
        self._patch_all(monkeypatch, bench={}, gaps={"error": "denied"}, opps={}, trend={}, forecast={}, playbook_lib={})

        result = nm.reporting("SALES")

        assert result["executive_reports"]["total_opportunity_monthly"] is None

    def test_opps_error_dict_still_yields_empty_list_not_none(self, monkeypatch):
        # opportunities() always returns SOME dict (even on error passthrough) --
        # isinstance(opps, dict) is True regardless, so strategic_priorities
        # becomes [] rather than staying None like the other conditional sections.
        self._patch_all(monkeypatch, bench={}, gaps={}, opps={"error": "denied"}, trend={}, forecast={}, playbook_lib={})

        result = nm.reporting("SALES")

        assert result["executive_reports"]["strategic_priorities"] == []

    def test_degrades_gracefully_when_trend_missing_department_history(self, monkeypatch):
        self._patch_all(monkeypatch, bench={}, gaps={}, opps={}, trend={"error": "denied"}, forecast={}, playbook_lib={})

        result = nm.reporting("SALES")

        assert result["historical_trend_report"] is None
        assert result["competitive_reports"]["trend_direction"] is None

    def test_degrades_gracefully_when_forecast_missing_closing_gaps(self, monkeypatch):
        self._patch_all(monkeypatch, bench={}, gaps={}, opps={}, trend={}, forecast={"error": "denied"}, playbook_lib={})

        result = nm.reporting("SALES")

        assert result["growth_forecast_report"] is None

    def test_degrades_gracefully_when_playbook_lib_missing_library(self, monkeypatch):
        self._patch_all(monkeypatch, bench={}, gaps={}, opps={}, trend={}, forecast={}, playbook_lib={"error": "denied"})

        result = nm.reporting("SALES")

        assert result["playbook_adoption_report"] is None
