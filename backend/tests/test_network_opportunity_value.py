"""
Tests for core/network_opportunity_value.py -- the real, honest dollar-
denomination layer over Network's Gap Analysis math. Added per BUILD_QUEUE.md's
standing "convert to a real pytest suite as each module gets touched" rule
(CAF-00123 missing_test_coverage work).

This module makes ZERO graph mutations (a pure, read-only calculation layer),
so no ledger fixture is needed -- every external dependency is mocked instead:
get_network_benchmarks_api()/get_network_audit_api() (core.network_api,
module-level imports, directly monkeypatchable) and get_bhph_outstanding_balance()
(core.network_benchmark, also a module-level import). The one deferred
(in-function) import -- core.performance_readiness.get_current_month_pace(),
called inside _sales_rate_unit_impact() -- must be patched via the string-
target form (monkeypatch.setattr("core.performance_readiness.get_current_month_pace",
fake)) rather than on this module's own namespace, per this codebase's
established deferred-import testing convention.

gap_direction() itself (core.network_benchmark) is NOT mocked -- it's a pure,
already-real function, and _dollar_conversion()'s correctness specifically
depends on gap_direction()'s real higher-is-better/lower-is-better semantic
(the bug this module's own docstring documents fixing), so exercising the
real function is the point.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import core.network_opportunity_value as nov
from core.network_opportunity_value import (
    _all_gaps,
    _dollar_conversion,
    _not_convertible_reason,
    _sales_rate_unit_impact,
    _bhph_exposure_impact,
    get_dollar_denominated_gaps,
    get_department_dollar_opportunities,
    get_total_identified_opportunity,
    get_largest_opportunities,
    generate_executive_summary,
    EXCLUDED_FROM_GRAND_TOTAL,
    _EXCLUDED_REASON,
    _NOT_CONVERTIBLE_NUMBER_REASON,
)


# ---------------------------------------------------------------------------
# Fake benchmark fixture -- mirrors get_network_benchmarks_api()'s real shape
# ({"departments": [{"department", "title", "percentile_rank", "this_dealer":
# {"kpis": {...}}, "peers": [{"kpis": {...}}, ...]}]}) closely enough to
# exercise _all_gaps()'s real iteration/skip logic and every real gap this
# module's dollar-conversion layer needs to see.
# ---------------------------------------------------------------------------

def _kpi(value, label=None, format_=None):
    return {"value": value, "label": label or "Label", "format": format_}


def _big_benchmark_payload():
    sales = {
        "department": "sales",
        "title": "Sales",
        "percentile_rank": 40,
        "this_dealer": {"kpis": {
            "units_sold": _kpi(90, "Units Sold", "number"),
            "gross_profit_per_unit": _kpi(4500, "Gross Profit / Unit", "currency"),
            "close_rate": _kpi(20.0, "Close Rate", "percent"),
            "show_rate": _kpi(50.0, "Show Rate", "percent"),
            "lead_response_time_minutes": _kpi(30, "Lead Response Time", "number"),
        }},
        "peers": [
            {"kpis": {
                "units_sold": _kpi(100), "gross_profit_per_unit": _kpi(4600),
                "close_rate": _kpi(25.0), "show_rate": _kpi(55.0),
                "lead_response_time_minutes": _kpi(20),
            }},
            {"kpis": {
                "units_sold": _kpi(110), "gross_profit_per_unit": _kpi(4700),
                "close_rate": _kpi(27.0), "show_rate": _kpi(60.0),
                "lead_response_time_minutes": _kpi(15),
            }},
        ],
    }

    fi = {
        "department": "fi",
        "title": "F&I",
        "percentile_rank": 60,
        "this_dealer": {"kpis": {
            "deals_financed": _kpi(40, "Deals Financed", "number"),
            "income_per_contract": _kpi(900, "Income / Contract", "currency"),
        }},
        "peers": [
            {"kpis": {"deals_financed": _kpi(50), "income_per_contract": _kpi(950)}},
            {"kpis": {"deals_financed": _kpi(48), "income_per_contract": _kpi(920)}},
        ],
    }

    service = {
        "department": "service",
        "title": "Service",
        "percentile_rank": 70,
        "this_dealer": {"kpis": {
            "ro_count": _kpi(300, "RO Count", "number"),
            "total_gross": _kpi(150000, "Total Gross", "currency"),
        }},
        "peers": [
            {"kpis": {"ro_count": _kpi(330), "total_gross": _kpi(165000)}},
            {"kpis": {"ro_count": _kpi(320), "total_gross": _kpi(160000)}},
        ],
    }

    bhph = {
        "department": "bhph",
        "title": "BHPH",
        "percentile_rank": None,
        "this_dealer": {"kpis": {
            "delinquency_rate_pct": _kpi(25.0, "Delinquency Rate", "percent"),
            "repo_rate_pct": _kpi(0.5, "Repo Rate", "percent"),
            "charge_off_rate_pct": _kpi(1.0, "Charge-Off Rate", "percent"),
        }},
        "peers": [
            {"kpis": {
                "delinquency_rate_pct": _kpi(15.0), "repo_rate_pct": _kpi(1.5),
                "charge_off_rate_pct": _kpi(0.5),
            }},
            {"kpis": {
                "delinquency_rate_pct": _kpi(17.0), "repo_rate_pct": _kpi(1.0),
                "charge_off_rate_pct": _kpi(0.5),
            }},
        ],
    }

    executive = {
        "department": "executive",
        "title": "Executive",
        "percentile_rank": 80,
        "this_dealer": {"kpis": {
            "total_gross_profit": _kpi(500000, "Total Gross Profit", "currency"),
        }},
        "peers": [
            {"kpis": {"total_gross_profit": _kpi(520000)}},
            {"kpis": {"total_gross_profit": _kpi(510000)}},
        ],
    }

    marketing = {
        "department": "marketing",
        "title": "Marketing",
        "percentile_rank": 30,
        "this_dealer": {"kpis": {
            "lead_volume": _kpi("N/A", "Lead Volume", "number"),  # non-numeric -> skipped
            "roi_pct": _kpi(12.0, "ROI", "percent"),  # peers never carry this key -> skipped
            "zero_metric": _kpi(5, "Zero Metric", "number"),  # peer_avg == 0 -> peer_gap_pct None
        }},
        "peers": [
            {"kpis": {"other_kpi": _kpi(5), "zero_metric": _kpi(0)}},
            {"kpis": {"other_kpi": _kpi(6), "zero_metric": _kpi(0)}},
        ],
    }

    return {"departments": [sales, fi, service, bhph, executive, marketing]}


def _empty_benchmark_payload():
    return {"departments": []}


def _mock_benchmarks(monkeypatch, payload):
    monkeypatch.setattr(nov, "get_network_benchmarks_api", lambda role, **kw: payload)


def _mock_audit(monkeypatch, payload):
    monkeypatch.setattr(nov, "get_network_audit_api", lambda role: payload)


# ---------------------------------------------------------------------------
# _all_gaps
# ---------------------------------------------------------------------------

class TestAllGaps:
    def test_error_from_benchmarks_api_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "Admin/Operations/Finance role required."})
        assert _all_gaps("SALES") == {"error": "Admin/Operations/Finance role required."}

    def test_non_numeric_this_value_is_skipped(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = _all_gaps("ADMIN")["gaps"]
        keys = {(g["department"], g["kpi"]) for g in gaps}
        assert ("marketing", "lead_volume") not in keys

    def test_kpi_absent_from_every_peer_is_skipped(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = _all_gaps("ADMIN")["gaps"]
        keys = {(g["department"], g["kpi"]) for g in gaps}
        assert ("marketing", "roi_pct") not in keys

    def test_zero_peer_average_yields_none_peer_gap_pct(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = _all_gaps("ADMIN")["gaps"]
        zero_metric = next(g for g in gaps if g["department"] == "marketing" and g["kpi"] == "zero_metric")
        assert zero_metric["peer_average"] == 0.0
        assert zero_metric["gap"] == -5.0
        assert zero_metric["peer_gap_pct"] is None

    def test_currency_gap_computed_correctly(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = _all_gaps("ADMIN")["gaps"]
        gpu = next(g for g in gaps if g["department"] == "sales" and g["kpi"] == "gross_profit_per_unit")
        assert gpu["this_store"] == 4500
        assert gpu["peer_average"] == 4650.0
        assert gpu["gap"] == 150.0
        assert gpu["format"] == "currency"
        assert gpu["department_title"] == "Sales"
        assert gpu["label"] == "Gross Profit / Unit"

    def test_peer_gap_pct_computed_correctly_when_peer_average_nonzero(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = _all_gaps("ADMIN")["gaps"]
        units = next(g for g in gaps if g["department"] == "sales" and g["kpi"] == "units_sold")
        # peer_avg = 105.0, gap = 15.0, peer_gap_pct = round(15/105*100, 1)
        assert units["peer_average"] == 105.0
        assert units["gap"] == 15.0
        assert units["peer_gap_pct"] == round(15.0 / 105.0 * 100, 1)


# ---------------------------------------------------------------------------
# _not_convertible_reason
# ---------------------------------------------------------------------------

class TestNotConvertibleReason:
    def test_message_names_the_kpi_and_format(self):
        reason = _not_convertible_reason("obsolete_inventory_pct", "percent")
        assert "obsolete_inventory_pct" in reason
        assert "percent" in reason

    def test_message_handles_missing_format(self):
        reason = _not_convertible_reason("some_kpi", None)
        assert "some_kpi" in reason
        assert "non-currency" in reason


# ---------------------------------------------------------------------------
# _dollar_conversion
# ---------------------------------------------------------------------------

class TestDollarConversion:
    def test_currency_opportunity_returns_direct_dollar_figure(self):
        result = _dollar_conversion("sales", "gross_profit_per_unit", "currency", 150.0, {})
        assert result["is_opportunity"] is True
        assert result["direction"] == "behind"
        assert result["dollar_impact_monthly"] == 150.0
        assert result["conversion_method"] == "direct_currency"
        assert result["real_inputs_used"] == {"gap_dollars": 150.0}
        assert result["not_convertible_reason"] is None

    def test_currency_non_opportunity_returns_zero_dollar_figure(self):
        # gap negative -- this dealer is AHEAD of peers on a higher-is-better
        # currency KPI, not an opportunity.
        result = _dollar_conversion("sales", "gross_profit_per_unit", "currency", -50.0, {})
        assert result["is_opportunity"] is False
        assert result["direction"] == "ahead"
        assert result["dollar_impact_monthly"] == 0.0
        assert result["conversion_method"] == "direct_currency"

    def test_number_direct_mapping_with_real_per_unit_value(self):
        lookup = {("sales", "gross_profit_per_unit"): 4500}
        result = _dollar_conversion("sales", "units_sold", "number", 15.0, lookup)
        assert result["is_opportunity"] is True
        assert result["dollar_impact_monthly"] == 15.0 * 4500
        assert result["conversion_method"] == "derived_per_unit_real_value"
        assert result["real_inputs_used"]["gap_units"] == 15.0
        assert result["real_inputs_used"]["per_unit_value"] == 4500.0
        assert "gross_profit_per_unit" in result["real_inputs_used"]["per_unit_value_source"]
        assert result["not_convertible_reason"] is None

    def test_number_direct_mapping_missing_per_unit_value_falls_to_not_convertible(self):
        result = _dollar_conversion("sales", "units_sold", "number", 15.0, {})
        assert result["is_opportunity"] is True
        assert result["dollar_impact_monthly"] is None
        assert result["conversion_method"] == "not_convertible_to_dollars"
        assert result["not_convertible_reason"] == _NOT_CONVERTIBLE_NUMBER_REASON

    def test_number_derived_ratio_mapping_computes_real_per_unit_value(self):
        lookup = {("service", "total_gross"): 150000, ("service", "ro_count"): 300}
        result = _dollar_conversion("service", "ro_count", "number", 25.0, lookup)
        assert result["is_opportunity"] is True
        # per_unit_value = 150000 / 300 = 500.0
        assert result["real_inputs_used"]["per_unit_value"] == 500.0
        assert result["dollar_impact_monthly"] == 25.0 * 500.0
        assert result["conversion_method"] == "derived_per_unit_real_value"

    def test_number_derived_ratio_mapping_guards_against_zero_count(self):
        lookup = {("service", "total_gross"): 150000, ("service", "ro_count"): 0}
        result = _dollar_conversion("service", "ro_count", "number", 25.0, lookup)
        assert result["dollar_impact_monthly"] is None
        assert result["conversion_method"] == "not_convertible_to_dollars"

    def test_number_with_no_mapping_at_all_is_not_convertible(self):
        # lead_response_time_minutes is lower-is-better -- gap negative means
        # this dealer is slower (worse) than peers, a real opportunity, but
        # there's no dollar-per-unit mapping for it.
        result = _dollar_conversion("sales", "lead_response_time_minutes", "number", -12.5, {})
        assert result["higher_is_better"] is False
        assert result["is_opportunity"] is True
        assert result["direction"] == "behind"
        assert result["opportunity_gap"] == 12.5
        assert result["dollar_impact_monthly"] is None
        assert result["conversion_method"] == "not_convertible_to_dollars"
        assert result["not_convertible_reason"] == _NOT_CONVERTIBLE_NUMBER_REASON

    def test_percent_format_lower_is_better_behind_is_a_real_opportunity(self):
        # bhph delinquency_rate_pct: gap = peer_avg - this_value = -9.0 means
        # this dealer's real rate is HIGHER (worse) than peers -- an
        # opportunity, even though the raw gap is negative.
        result = _dollar_conversion("bhph", "delinquency_rate_pct", "percent", -9.0, {})
        assert result["higher_is_better"] is False
        assert result["is_opportunity"] is True
        assert result["direction"] == "behind"
        assert result["opportunity_gap"] == 9.0
        assert result["dollar_impact_monthly"] is None
        assert result["conversion_method"] == "not_convertible_to_dollars"
        assert "delinquency_rate_pct" in result["not_convertible_reason"]

    def test_percent_format_lower_is_better_ahead_is_not_an_opportunity(self):
        # bhph repo_rate_pct: this dealer's real rate is LOWER (better) than
        # peers -- gap positive, but NOT an opportunity for a lower-is-better
        # KPI. This is the exact bug this module's docstring documents fixing
        # (a bare gap > 0 check would have mislabeled this as an opportunity).
        result = _dollar_conversion("bhph", "repo_rate_pct", "percent", 0.75, {})
        assert result["higher_is_better"] is False
        assert result["is_opportunity"] is False
        assert result["direction"] == "ahead"
        assert result["opportunity_gap"] == 0.0
        assert result["dollar_impact_monthly"] is None

    def test_missing_gap_value_returns_unknown_direction_and_zero_dollar(self):
        result = _dollar_conversion("sales", "gross_profit_per_unit", "currency", None, {})
        assert result["is_opportunity"] is False
        assert result["direction"] == "unknown"
        assert result["opportunity_gap"] is None
        assert result["dollar_impact_monthly"] == 0.0


# ---------------------------------------------------------------------------
# _sales_rate_unit_impact
# ---------------------------------------------------------------------------

class TestSalesRateUnitImpact:
    def test_unmapped_kpi_key_returns_none(self):
        assert _sales_rate_unit_impact("units_sold", 6.0, {}) is None

    def test_zero_opportunity_gap_pct_returns_none(self):
        assert _sales_rate_unit_impact("close_rate", 0, {}) is None

    def test_none_monthly_pace_returns_none(self, monkeypatch):
        monkeypatch.setattr("core.performance_readiness.get_current_month_pace", lambda dept: None)
        assert _sales_rate_unit_impact("close_rate", 6.0, {}) is None

    def test_missing_projected_month_total_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"department": dept},
        )
        assert _sales_rate_unit_impact("show_rate", 7.5, {}) is None

    def test_non_positive_monthly_leads_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 0},
        )
        assert _sales_rate_unit_impact("show_rate", 7.5, {}) is None

    def test_show_rate_computes_units_but_never_a_dollar_figure(self, monkeypatch):
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 373.72},
        )
        lookup = {("sales", "gross_profit_per_unit"): 4500}
        result = _sales_rate_unit_impact("show_rate", 7.5, lookup)
        assert result["unit_label"] == "appointment(s) shown"
        assert result["additional_units_monthly"] == round((7.5 / 100.0) * 373.72, 1)
        # show_rate deliberately never chains into a dollar figure, even
        # though gross_profit_per_unit is present in the lookup.
        assert result["derived_dollar_impact_monthly"] is None
        assert result["derived_dollar_impact_annualized"] is None
        assert "gross_profit_per_unit" not in result["real_inputs_used"]

    def test_close_rate_computes_a_real_derived_dollar_figure(self, monkeypatch):
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 373.72},
        )
        lookup = {("sales", "gross_profit_per_unit"): 4500}
        result = _sales_rate_unit_impact("close_rate", 6.0, lookup)
        additional_units = round((6.0 / 100.0) * 373.72, 1)
        assert result["additional_units_monthly"] == additional_units
        assert result["unit_label"] == "sale(s)"
        expected_dollar = round(additional_units * 4500, 2)
        assert result["derived_dollar_impact_monthly"] == expected_dollar
        assert result["derived_dollar_impact_annualized"] == round(expected_dollar * 12, 2)
        assert result["real_inputs_used"]["gross_profit_per_unit"] == 4500.0
        assert "monthly_lead_volume" in result["real_inputs_used"]
        assert result["real_inputs_used"]["monthly_lead_volume"] == 373.72

    def test_close_rate_without_gross_profit_per_unit_leaves_dollar_none(self, monkeypatch):
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 373.72},
        )
        result = _sales_rate_unit_impact("close_rate", 6.0, {})
        assert result["additional_units_monthly"] is not None
        assert result["derived_dollar_impact_monthly"] is None
        assert result["derived_dollar_impact_annualized"] is None


# ---------------------------------------------------------------------------
# _bhph_exposure_impact
# ---------------------------------------------------------------------------

class TestBhphExposureImpact:
    def test_unmapped_kpi_key_returns_none(self):
        assert _bhph_exposure_impact("avg_apr", 9.0, "ADMIN") is None

    def test_zero_opportunity_gap_pct_returns_none(self):
        assert _bhph_exposure_impact("delinquency_rate_pct", 0, "ADMIN") is None

    def test_none_outstanding_balance_returns_none(self, monkeypatch):
        monkeypatch.setattr(nov, "get_bhph_outstanding_balance", lambda role: None)
        assert _bhph_exposure_impact("delinquency_rate_pct", 9.0, "ADMIN") is None

    def test_zero_outstanding_balance_returns_none(self, monkeypatch):
        monkeypatch.setattr(nov, "get_bhph_outstanding_balance", lambda role: 0)
        assert _bhph_exposure_impact("repo_rate_pct", 5.0, "ADMIN") is None

    def test_real_calculation_against_a_real_outstanding_balance(self, monkeypatch):
        monkeypatch.setattr(nov, "get_bhph_outstanding_balance", lambda role: 1_000_000)
        result = _bhph_exposure_impact("delinquency_rate_pct", 9.0, "ADMIN")
        assert result["dollars_at_risk_reduction"] == round((9.0 / 100.0) * 1_000_000, 2)
        assert result["basis"] == "one_time_reduction_on_current_outstanding_balance"
        assert result["real_inputs_used"]["outstanding_portfolio_balance"] == 1_000_000
        assert result["real_inputs_used"]["opportunity_gap_percentage_points"] == 9.0
        assert "one-time" in result["note"].lower() or "ONE-TIME" in result["note"]


# ---------------------------------------------------------------------------
# get_dollar_denominated_gaps
# ---------------------------------------------------------------------------

class TestGetDollarDenominatedGaps:
    def test_error_from_benchmarks_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "denied"})
        assert get_dollar_denominated_gaps("SALES") == {"error": "denied"}

    def test_basis_notice_is_present(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_dollar_denominated_gaps("ADMIN")
        assert "basis_notice" in result
        assert "SIMULATED" in result["basis_notice"]

    def test_results_sorted_by_dollar_impact_descending(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        numeric = [g["dollar_impact_monthly"] for g in gaps if isinstance(g["dollar_impact_monthly"], (int, float))]
        assert numeric == sorted(numeric, reverse=True)

    def test_non_convertible_entries_sort_last(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        none_indices = [i for i, g in enumerate(gaps) if g["dollar_impact_monthly"] is None]
        numeric_indices = [i for i, g in enumerate(gaps) if isinstance(g["dollar_impact_monthly"], (int, float))]
        if none_indices and numeric_indices:
            assert max(numeric_indices) < min(none_indices)

    def test_close_rate_unit_impact_overrides_headline_dollar_figure(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 373.72},
        )
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        close_rate = next(g for g in gaps if g["department"] == "sales" and g["kpi"] == "close_rate")
        assert close_rate["unit_impact"] is not None
        assert close_rate["unit_impact"]["derived_dollar_impact_monthly"] is not None
        assert close_rate["conversion_method"] == "derived_rate_x_volume_x_per_unit_value"
        assert close_rate["dollar_impact_monthly"] == close_rate["unit_impact"]["derived_dollar_impact_monthly"]
        assert close_rate["annualized_dollar_impact"] == round(close_rate["dollar_impact_monthly"] * 12, 2)

    def test_show_rate_gets_unit_impact_but_no_dollar_override(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        monkeypatch.setattr(
            "core.performance_readiness.get_current_month_pace",
            lambda dept: {"projected_month_total": 373.72},
        )
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        show_rate = next(g for g in gaps if g["department"] == "sales" and g["kpi"] == "show_rate")
        assert show_rate["unit_impact"] is not None
        assert show_rate["unit_impact"]["derived_dollar_impact_monthly"] is None
        # show_rate is a percent-format KPI with no _COUNT_KPI_TO_DOLLAR_VALUE
        # mapping, so its own headline dollar_impact_monthly stays None.
        assert show_rate["dollar_impact_monthly"] is None

    def test_bhph_gets_portfolio_exposure_impact_not_unit_impact(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        monkeypatch.setattr(nov, "get_bhph_outstanding_balance", lambda role: 1_000_000)
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        delinquency = next(g for g in gaps if g["department"] == "bhph" and g["kpi"] == "delinquency_rate_pct")
        assert delinquency["unit_impact"] is None
        assert delinquency["portfolio_exposure_impact"] is not None
        assert delinquency["portfolio_exposure_impact"]["dollars_at_risk_reduction"] == round(9.0 / 100.0 * 1_000_000, 2)

    def test_bhph_ahead_kpi_gets_no_portfolio_exposure_impact(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        monkeypatch.setattr(nov, "get_bhph_outstanding_balance", lambda role: 1_000_000)
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        repo = next(g for g in gaps if g["department"] == "bhph" and g["kpi"] == "repo_rate_pct")
        assert repo["is_opportunity"] is False
        assert repo["portfolio_exposure_impact"] is None

    def test_executive_department_gaps_are_flagged_excluded(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        exec_gap = next(g for g in gaps if g["department"] == "executive")
        assert exec_gap["excluded_from_grand_total"] is True

    def test_non_executive_department_gaps_are_not_excluded(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        gaps = get_dollar_denominated_gaps("ADMIN")["gaps"]
        sales_gap = next(g for g in gaps if g["department"] == "sales" and g["kpi"] == "gross_profit_per_unit")
        assert sales_gap["excluded_from_grand_total"] is False


# ---------------------------------------------------------------------------
# get_department_dollar_opportunities
# ---------------------------------------------------------------------------

class TestGetDepartmentDollarOpportunities:
    def test_error_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "denied"})
        assert get_department_dollar_opportunities("SALES") == {"error": "denied"}

    def test_grand_total_excludes_executive_department(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_department_dollar_opportunities("ADMIN")

        exec_entry = next(d for d in result["departments"] if d["department"] == "executive")
        assert exec_entry["excluded_from_grand_total"] is True
        assert exec_entry["excluded_reason"] == _EXCLUDED_REASON
        assert exec_entry["monthly_opportunity"] > 0

        # The executive department's own real $15,000/mo gap must NOT be
        # folded into the grand total (it would double-count Sales/Service/
        # Parts/F&I gross already counted elsewhere).
        manual_total = sum(
            d["monthly_opportunity"] for d in result["departments"]
            if not d["excluded_from_grand_total"]
        )
        assert round(result["grand_total_monthly_opportunity"], 2) == round(manual_total, 2)

    def test_non_excluded_departments_have_no_excluded_reason(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_department_dollar_opportunities("ADMIN")
        sales_entry = next(d for d in result["departments"] if d["department"] == "sales")
        assert sales_entry["excluded_from_grand_total"] is False
        assert sales_entry["excluded_reason"] is None

    def test_not_convertible_gaps_are_counted_separately_from_monthly_total(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_department_dollar_opportunities("ADMIN")
        bhph_entry = next(d for d in result["departments"] if d["department"] == "bhph")
        # All 3 bhph rate KPIs are percent-format with no dollar mapping --
        # every one counts as not_convertible, none contributes to monthly_total.
        assert bhph_entry["not_convertible_gap_count"] == 3
        assert bhph_entry["convertible_gap_count"] == 0
        assert bhph_entry["monthly_opportunity"] == 0.0

    def test_annualized_is_monthly_times_twelve(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_department_dollar_opportunities("ADMIN")
        for entry in result["departments"]:
            assert entry["annualized_opportunity"] == round(entry["monthly_opportunity"] * 12, 2)

    def test_departments_sorted_by_annualized_descending(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_department_dollar_opportunities("ADMIN")
        values = [d["annualized_opportunity"] for d in result["departments"]]
        assert values == sorted(values, reverse=True)


# ---------------------------------------------------------------------------
# get_total_identified_opportunity
# ---------------------------------------------------------------------------

class TestGetTotalIdentifiedOpportunity:
    def test_error_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "denied"})
        assert get_total_identified_opportunity("SALES") == {"error": "denied"}

    def test_totals_and_excluded_departments_are_correct(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        dept_opps = get_department_dollar_opportunities("ADMIN")
        result = get_total_identified_opportunity("ADMIN")

        assert result["total_monthly_opportunity"] == dept_opps["grand_total_monthly_opportunity"]
        assert result["total_annualized_opportunity"] == dept_opps["grand_total_annualized_opportunity"]
        assert result["excluded_departments"] == ["executive"]
        assert "basis_notice" in result


# ---------------------------------------------------------------------------
# get_largest_opportunities
# ---------------------------------------------------------------------------

class TestGetLargestOpportunities:
    def test_error_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "denied"})
        assert get_largest_opportunities("SALES") == {"error": "denied"}

    def test_only_positive_convertible_opportunities_appear(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_largest_opportunities("ADMIN", limit=100)
        for g in result["largest_opportunities"]:
            assert g["is_opportunity"] is True
            assert isinstance(g["dollar_impact_monthly"], (int, float))
            assert g["dollar_impact_monthly"] > 0

    def test_bhph_rate_gaps_never_appear_since_theyre_not_dollar_convertible(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_largest_opportunities("ADMIN", limit=100)
        departments = {g["department"] for g in result["largest_opportunities"]}
        assert "bhph" not in departments

    def test_limit_is_respected(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_largest_opportunities("ADMIN", limit=2)
        assert len(result["largest_opportunities"]) <= 2

    def test_sorted_descending_by_dollar_impact(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        result = get_largest_opportunities("ADMIN", limit=100)
        values = [g["dollar_impact_monthly"] for g in result["largest_opportunities"]]
        assert values == sorted(values, reverse=True)


# ---------------------------------------------------------------------------
# generate_executive_summary (+ _build_raw_executive_summary via it)
# ---------------------------------------------------------------------------

class TestGenerateExecutiveSummary:
    def test_error_from_benchmarks_is_passed_through(self, monkeypatch):
        _mock_benchmarks(monkeypatch, {"error": "denied"})
        result = generate_executive_summary("SALES")
        assert result == {"error": "denied"}

    def test_audit_error_degrades_gracefully_to_zero_recommendations(self, monkeypatch):
        # _build_raw_executive_summary() does NOT check the audit result for
        # an "error" key the way it does for benchmarks -- it only ever reads
        # audit.get("recommendations", []), so an audit-layer denial (e.g. a
        # role outside NETWORK_ROLES) silently degrades to "no recommendations
        # currently triggered" rather than failing the whole summary. Real,
        # confirmed behavior, not a guess -- the summary itself is still
        # generated successfully off the real benchmark data.
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"error": "denied"})
        result = generate_executive_summary("ADMIN", polish=False)

        assert "error" not in result
        assert "No network-audit recommendations are currently triggered" in result["text"]
        assert result["facts"]["top_recommendations"] == []

    def test_no_departments_produces_every_fallback_sentence(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _empty_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": []})
        result = generate_executive_summary("ADMIN", polish=False)

        text = result["text"]
        assert "could not be computed" in text
        assert "No department currently has a dollar-convertible gap" in text
        assert "No network-audit recommendations are currently triggered" in text
        assert "No dollar-convertible opportunity is currently identified" in text
        assert result["basis"] == "real"
        assert result["facts"]["avg_percentile"] is None
        assert result["facts"]["total_annualized_opportunity"] in (0.0, None, 0)

    def test_full_fixture_produces_real_sentences_with_real_facts(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": [
            {"finding": "Sales close rate trails peers.", "recommendation": "Coach the desk."},
        ]})
        result = generate_executive_summary("ADMIN", polish=False)

        # avg_percentile over [40, 60, 70, 80, 30] (bhph's None excluded) = 56.0
        assert result["facts"]["avg_percentile"] == 56.0
        assert result["facts"]["top_pct"] == round(100 - 56.0, 1)
        assert "56.0th percentile" in result["text"]
        assert "Sales close rate trails peers." in result["text"]
        assert len(result["facts"]["top_gaps"]) > 0
        assert result["facts"]["total_annualized_opportunity"] is not None
        assert "$" in result["text"]

    def test_polish_false_never_calls_the_ai_polish_function(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": []})

        def _raise(*a, **kw):
            raise AssertionError("polish_network_executive_summary should not be called when polish=False")

        monkeypatch.setattr(nov, "polish_network_executive_summary", _raise)

        result = generate_executive_summary("ADMIN", polish=False)
        assert result["ai_generated"] is False
        assert result["summary"] == result["text"]

    def test_polish_true_uses_the_ai_summary_on_success(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": []})
        monkeypatch.setattr(
            nov, "polish_network_executive_summary",
            lambda text: {"summary": "A polished, AI-phrased version."},
        )

        result = generate_executive_summary("ADMIN", polish=True)
        assert result["ai_generated"] is True
        assert result["summary"] == "A polished, AI-phrased version."
        # The real, correct template text is still present under "text".
        assert "text" in result

    def test_polish_true_falls_back_to_real_template_on_ai_error(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": []})
        monkeypatch.setattr(
            nov, "polish_network_executive_summary",
            lambda text: {"error": "AI summary polish is currently disabled by your administrator.", "disabled": True},
        )

        result = generate_executive_summary("ADMIN", polish=True)
        assert result["ai_generated"] is False
        assert result["summary"] == result["text"]
        assert result["ai_polish_note"] == "AI summary polish is currently disabled by your administrator."

    def test_polish_true_falls_back_when_polish_returns_no_summary_key(self, monkeypatch):
        _mock_benchmarks(monkeypatch, _big_benchmark_payload())
        _mock_audit(monkeypatch, {"recommendations": []})
        monkeypatch.setattr(nov, "polish_network_executive_summary", lambda text: {})

        result = generate_executive_summary("ADMIN", polish=True)
        assert result["ai_generated"] is False
        assert result["summary"] == result["text"]
        assert "AI polish unavailable" in result["ai_polish_note"]
