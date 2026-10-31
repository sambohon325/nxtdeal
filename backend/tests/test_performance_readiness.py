"""
Test coverage for core/performance_readiness.py -- Readiness' "Performance
Readiness" item: real Goal vs. Pace vs. Readiness % per department.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.performance_readiness as pr
from core.system_config import set_department_goal, clear_department_goal


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


TODAY = date(2026, 7, 20)  # day 20 of a 31-day month


def _vehicle(vid, **attrs):
    ledger.add_entity(Entity(id=vid, entity_type="Vehicle", attributes=attrs))


def _service_record(sid, **attrs):
    ledger.add_entity(Entity(id=sid, entity_type="ServiceRecord", attributes=attrs))


def _lead(lid, **attrs):
    ledger.add_entity(Entity(id=lid, entity_type="Lead", attributes=attrs))


class TestCurrentMonthActual:

    def test_sales_counts_only_current_month_sold_vehicles(self):
        _vehicle("VEH-1", DateSold="2026-07-01")
        _vehicle("VEH-2", DateSold="2026-07-20")
        _vehicle("VEH-3", DateSold="2026-06-30")  # prior month, excluded
        _vehicle("VEH-4")  # no DateSold, excluded
        assert pr._current_month_actual("sales", TODAY) == 2.0

    def test_service_sums_cost_minus_parts_cost_current_month(self):
        _service_record("SRV-1", ServiceDate="2026-07-05", Cost="500", PartsCost="100")
        _service_record("SRV-2", ServiceDate="2026-07-10", Cost="300", PartsCost="50")
        _service_record("SRV-3", ServiceDate="2026-06-01", Cost="999", PartsCost="0")  # excluded
        assert pr._current_month_actual("service", TODAY) == 650.0

    def test_marketing_counts_current_month_leads(self):
        _lead("LEAD-1", CreatedDate="2026-07-01")
        _lead("LEAD-2", CreatedDate="2026-07-19")
        _lead("LEAD-3", CreatedDate="2026-08-01")  # future month, excluded
        assert pr._current_month_actual("marketing", TODAY) == 2.0

    def test_unknown_department_returns_none(self):
        assert pr._current_month_actual("finance", TODAY) is None

    def test_empty_ledger_returns_zero_not_none(self):
        assert pr._current_month_actual("sales", TODAY) == 0.0


class TestGetCurrentMonthPace:

    def test_unknown_department_returns_none(self):
        assert pr.get_current_month_pace("finance", today=TODAY) is None

    def test_linear_run_rate_math(self):
        _vehicle("VEH-1", DateSold="2026-07-01")
        pace = pr.get_current_month_pace("sales", today=TODAY)
        assert pace["actual_to_date"] == 1.0
        assert pace["days_elapsed"] == 20
        assert pace["days_in_month"] == 31
        assert pace["projected_month_total"] == round((1.0 / 20) * 31, 2)
        assert pace["basis"] == "real"

    def test_zero_actual_still_returns_a_real_pace_dict(self):
        pace = pr.get_current_month_pace("sales", today=TODAY)
        assert pace["actual_to_date"] == 0.0
        assert pace["projected_month_total"] == 0.0


class TestGetLedgerForecast:

    def test_service_is_always_excluded(self):
        assert pr.get_ledger_forecast("service") is None

    def test_unknown_department_returns_none(self):
        assert pr.get_ledger_forecast("xyz") is None

    def test_sales_returns_a_real_forecast_dict(self):
        forecast = pr.get_ledger_forecast("sales")
        assert forecast is not None
        assert set(forecast.keys()) == {
            "department", "metric", "unit", "predicted_value", "confidence_pct", "basis", "note",
        }
        assert forecast["department"] == "sales"

    def test_marketing_returns_a_real_forecast_dict(self):
        forecast = pr.get_ledger_forecast("marketing")
        assert forecast is not None
        assert forecast["department"] == "marketing"

    def test_a_department_outside_goal_metric_catalog_is_not_restricted_here(self):
        # get_ledger_forecast() isn't scoped to GOAL_METRIC_CATALOG's 3 keys --
        # it accepts any of core.prediction's own DEPARTMENTS (except service).
        assert pr.get_ledger_forecast("finance") is not None


class TestGetDepartmentPerformanceReadiness:

    def test_unknown_department_returns_error(self):
        result = pr.get_department_performance_readiness("finance", today=TODAY)
        assert "error" in result
        assert "finance" in result["error"]

    def test_empty_department_returns_error(self):
        result = pr.get_department_performance_readiness("", today=TODAY)
        assert "error" in result

    def test_department_lookup_is_case_insensitive(self):
        result = pr.get_department_performance_readiness("SALES", today=TODAY)
        assert result["department"] == "sales"

    def test_no_goal_set_reports_honestly_not_a_fabricated_100(self):
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["goal_set"] is False
        assert result["goal"] is None
        assert result["readiness_pct"] is None
        assert result["readiness_source"] is None
        assert "No goal set" in result["status"]

    def test_goal_set_computes_readiness_from_current_month_pace(self):
        _vehicle("VEH-1", DateSold="2026-07-01")
        set_department_goal("sales", 10, "EMP-TEST")
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["goal_set"] is True
        assert result["goal"] == 10.0
        assert result["readiness_source"] == "current_month_pace"
        expected_pace = round((1.0 / 20) * 31, 2)
        assert result["readiness_pct"] == round((expected_pace / 10) * 100, 1)

    def test_readiness_exactly_100_is_at_above_goal(self):
        _vehicle("VEH-1", DateSold="2026-07-01")
        pace = pr.get_current_month_pace("sales", today=TODAY)["projected_month_total"]
        set_department_goal("sales", pace, "EMP-TEST")
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["readiness_pct"] == 100.0
        assert result["status"] == "At/Above Goal"

    def test_readiness_above_100_is_at_above_goal(self):
        _vehicle("VEH-1", DateSold="2026-07-01")
        set_department_goal("sales", 1.0, "EMP-TEST")
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["readiness_pct"] > 100.0
        assert result["status"] == "At/Above Goal"

    def test_readiness_below_100_is_below_goal(self):
        _lead("LEAD-1", CreatedDate="2026-07-01")
        set_department_goal("marketing", 1000, "EMP-TEST")
        result = pr.get_department_performance_readiness("marketing", today=TODAY)
        assert result["readiness_pct"] < 100.0
        assert result["status"] == "Below Goal"

    def test_clearing_a_goal_reverts_to_unset_state(self):
        set_department_goal("sales", 10, "EMP-TEST")
        clear_department_goal("sales", "EMP-TEST")
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["goal_set"] is False
        assert result["readiness_pct"] is None

    def test_response_includes_pace_and_forecast_sub_dicts(self):
        set_department_goal("sales", 10, "EMP-TEST")
        result = pr.get_department_performance_readiness("sales", today=TODAY)
        assert result["current_month_pace"] is not None
        assert result["ledger_forecast"] is not None

    def test_service_forecast_is_none_even_when_goal_is_set(self):
        set_department_goal("service", 100, "EMP-TEST")
        result = pr.get_department_performance_readiness("service", today=TODAY)
        assert result["ledger_forecast"] is None
        assert result["current_month_pace"] is not None
        assert result["readiness_source"] == "current_month_pace"

    def test_label_and_unit_come_from_the_real_catalog(self):
        result = pr.get_department_performance_readiness("service", today=TODAY)
        assert result["label"] == "Monthly Service Labor Goal"
        assert result["unit"] == "$"


class TestGetPerformanceReadinessOverview:

    def test_overview_covers_exactly_the_three_tracked_departments(self):
        overview = pr.get_performance_readiness_overview(today=TODAY)
        depts = [d["department"] for d in overview["departments"]]
        assert depts == ["sales", "service", "marketing"]
        assert overview["tracked_departments"] == ["sales", "service", "marketing"]

    def test_overview_names_the_honest_finance_and_inventory_gaps(self):
        overview = pr.get_performance_readiness_overview(today=TODAY)
        assert set(overview["not_yet_tracked"].keys()) == {"finance_goal", "inventory_goal"}

    def test_overview_reflects_real_goal_state_per_department(self):
        set_department_goal("sales", 5, "EMP-TEST")
        overview = pr.get_performance_readiness_overview(today=TODAY)
        by_dept = {d["department"]: d for d in overview["departments"]}
        assert by_dept["sales"]["goal_set"] is True
        assert by_dept["service"]["goal_set"] is False
        assert by_dept["marketing"]["goal_set"] is False
