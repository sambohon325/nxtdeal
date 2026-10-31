"""
Tests for core/readiness_forecasts.py / core/readiness_forecasts_api.py --
Readiness' "Forecasts" item (Sales/Service/Inventory/Finance) plus the Readiness
Timeline capstone.

A pure composition layer over already-real engines (core/prediction.py's
predict_all_horizons/historical_trend, core/performance_readiness.py's
get_current_month_pace, core/service_reporting.py's get_shop_capacity, core/
workflow_tab_data.py's inventory_wholesale_disposition, core/pricing_desk.py's
get_age_based_adjustment, core/collections_api.py/core/loan_servicing_api.py's
dashboards) -- every one of those dependencies is monkeypatched directly on
core.readiness_forecasts's own namespace (they're all `from X import Y`-bound
there), matching the composition-boundary testing pattern already established for
core/business_health.py/core/enterprise_risk_center.py/core/
readiness_recommendations.py.

Two pieces are genuinely new computations with no upstream to monkeypatch away --
_month_to_date_funded_deals()/sales_forecast()'s own real Deal+Vehicle gross/revenue
sum, _month_to_date_part_sales()/service_forecast()'s own real PartSale sum, and
_unsold_vehicle_signals()'s own real Vehicle Price/Cost margin calc -- those are
tested with real ledger fixtures instead.

This module makes zero graph mutations of its own -- pure read/composition.

Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DEAL, PART_SALE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import readiness_forecasts
from core.readiness_forecasts import (
    _safe_float,
    _parse_date,
    _month_bounds,
    _linear_projection,
    _month_to_date_funded_deals,
    sales_forecast,
    _month_to_date_part_sales,
    service_forecast,
    _unsold_vehicle_signals,
    inventory_forecast,
    finance_forecast,
    get_forecasts_overview,
    get_readiness_timeline_overview,
    get_readiness_timeline_department,
)
from core import readiness_forecasts_api
from core.readiness_forecasts_api import (
    get_forecasts_overview_api,
    get_forecasts_department_api,
    get_readiness_timeline_overview_api,
    get_readiness_timeline_department_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)

TODAY = date(2026, 6, 15)  # day 15 of a 30-day month


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _vehicle(vehicle_id, price, cost, date_sold=None):
    attrs = {"Price": str(price), "Cost": str(cost)}
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))


def _deal(deal_id, vehicle_id, status, funded_at=None):
    attrs = {"vehicle_id": vehicle_id, "status": status}
    if funded_at is not None:
        attrs["funded_at"] = funded_at
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes=attrs))


def _part_sale(sale_id, sale_date, sale_price):
    ledger.add_entity(Entity(id=sale_id, entity_type=PART_SALE, attributes={
        "SaleDate": sale_date, "SalePrice": str(sale_price),
    }))


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

class TestSafeFloat:

    def test_parses_numeric(self):
        assert _safe_float("12.5") == 12.5

    def test_defaults_on_none(self):
        assert _safe_float(None) == 0.0

    def test_defaults_on_garbage(self):
        assert _safe_float("nope") == 0.0


class TestParseDate:

    def test_parses_iso_date(self):
        assert _parse_date("2026-06-15") == date(2026, 6, 15)

    def test_parses_iso_datetime_by_truncating(self):
        assert _parse_date("2026-06-15T10:30:00") == date(2026, 6, 15)

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_date("not-a-date") is None


class TestMonthBounds:

    def test_uses_provided_today(self):
        today, days_elapsed, days_in_month = _month_bounds(date(2026, 2, 10))
        assert today == date(2026, 2, 10)
        assert days_elapsed == 10
        assert days_in_month == 28  # 2026 is not a leap year

    def test_defaults_to_real_today_when_omitted(self):
        today, days_elapsed, days_in_month = _month_bounds()
        assert today == date.today()


class TestLinearProjection:

    def test_projects_forward(self):
        # $100 over 10 days elapsed in a 30-day month -> $300 projected.
        assert _linear_projection(100.0, 10, 30) == 300.0

    def test_zero_days_elapsed_returns_none(self):
        assert _linear_projection(100.0, 0, 30) is None

    def test_zero_actual_projects_to_zero(self):
        assert _linear_projection(0.0, 10, 30) == 0.0


# ---------------------------------------------------------------------------
# Sales Forecast
# ---------------------------------------------------------------------------

class TestMonthToDateFundedDeals:

    def test_includes_only_funded_deals_this_calendar_month(self):
        _vehicle("VEH-1", price=20000, cost=15000)
        _vehicle("VEH-2", price=30000, cost=20000)
        _vehicle("VEH-3", price=25000, cost=18000)
        _deal("DEAL-1", "VEH-1", status="funded", funded_at="2026-06-05")  # this month
        _deal("DEAL-2", "VEH-2", status="funded", funded_at="2026-05-20")  # different month
        _deal("DEAL-3", "VEH-3", status="contract", funded_at=None)  # not funded

        deals, vehicles_by_id = _month_to_date_funded_deals(TODAY)
        deal_ids = [d.id for d in deals]
        assert deal_ids == ["DEAL-1"]
        assert "VEH-1" in vehicles_by_id

    def test_no_matching_deals_returns_empty_list(self):
        deals, vehicles_by_id = _month_to_date_funded_deals(TODAY)
        assert deals == []


class TestSalesForecast:

    def test_units_forecast_passthrough(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {"tomorrow": {"predicted_value": 2.5}})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda role: {})
        result = sales_forecast(ADMIN)
        assert result["units"]["forecast_by_horizon"] == {"tomorrow": {"predicted_value": 2.5}}
        assert result["units"]["basis"] == "ledger_or_industry_estimate"

    def test_gross_and_revenue_computed_from_real_funded_deals(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda role: {"closing_ratio_avg": 0.42})
        monkeypatch.setattr(readiness_forecasts, "_month_bounds", lambda today=None: (TODAY, 10, 30))

        _vehicle("VEH-1", price=20000, cost=15000)
        _deal("DEAL-1", "VEH-1", status="funded", funded_at="2026-06-05")

        result = sales_forecast(ADMIN)
        assert result["gross"]["month_to_date"] == 5000.0
        assert result["gross"]["projected_month_total"] == 15000.0  # (5000/10)*30
        assert result["gross"]["basis"] == "real_linear_projection"
        assert result["revenue"]["month_to_date"] == 20000.0
        assert result["revenue"]["projected_month_total"] == 60000.0
        assert result["closing_ratio"]["value"] == 0.42
        assert result["closing_ratio"]["basis"] == "real"

    def test_closing_ratio_missing_from_overview_is_none(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda role: {})
        result = sales_forecast(ADMIN)
        assert result["closing_ratio"]["value"] is None

    def test_non_dict_overview_is_handled_gracefully(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda role: {"error": "denied"})
        result = sales_forecast(ADMIN)
        assert result["closing_ratio"]["value"] is None


# ---------------------------------------------------------------------------
# Service Forecast
# ---------------------------------------------------------------------------

class TestMonthToDatePartSales:

    def test_sums_only_this_calendar_month(self):
        _part_sale("PS-1", "2026-06-01", 100)
        _part_sale("PS-2", "2026-06-10", 50)
        _part_sale("PS-3", "2026-05-15", 999)  # different month, excluded

        total, count = _month_to_date_part_sales(TODAY)
        assert total == 150.0
        assert count == 2

    def test_no_sales_returns_zero(self):
        total, count = _month_to_date_part_sales(TODAY)
        assert total == 0.0
        assert count == 0


class TestServiceForecast:

    def _patch_common(self, monkeypatch, labor_pace):
        monkeypatch.setattr(readiness_forecasts, "get_current_month_pace", lambda dept: labor_pace)
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_shop_capacity", lambda: {"technician_count": 5, "overloaded_technician_count": 0})
        monkeypatch.setattr(readiness_forecasts, "_month_bounds", lambda today=None: (TODAY, 10, 30))

    def test_labor_sales_real_pace_is_relabeled(self, monkeypatch):
        pace = {"actual_to_date": 1000.0, "projected_month_total": 3000.0, "basis": "real"}
        self._patch_common(monkeypatch, pace)
        result = service_forecast(ADMIN)
        assert result["labor_sales"]["basis"] == "real_linear_projection"
        assert "get_current_month_pace" in result["labor_sales"]["note"]
        assert result["labor_sales"]["actual_to_date"] == 1000.0

    def test_labor_sales_none_pace_reports_not_yet_tracked(self, monkeypatch):
        self._patch_common(monkeypatch, None)
        result = service_forecast(ADMIN)
        assert result["labor_sales"]["basis"] == "not_yet_tracked"

    def test_parts_sales_computed_from_real_ledger(self, monkeypatch):
        self._patch_common(monkeypatch, None)
        _part_sale("PS-1", "2026-06-01", 100)
        _part_sale("PS-2", "2026-06-05", 200)
        result = service_forecast(ADMIN)
        assert result["parts_sales"]["month_to_date"] == 300.0
        assert result["parts_sales"]["sales_count_month_to_date"] == 2
        assert result["parts_sales"]["projected_month_total"] == 900.0  # (300/10)*30

    def test_ro_count_forecast_passthrough(self, monkeypatch):
        self._patch_common(monkeypatch, None)
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {"tomorrow": {"predicted_value": 4.0}})
        result = service_forecast(ADMIN)
        assert result["ro_count"]["forecast_by_horizon"] == {"tomorrow": {"predicted_value": 4.0}}

    def test_capacity_passthrough_with_heuristic_basis(self, monkeypatch):
        self._patch_common(monkeypatch, None)
        result = service_forecast(ADMIN)
        assert result["capacity"]["technician_count"] == 5
        assert result["capacity"]["basis"] == "heuristic"

    def test_capacity_none_is_handled_gracefully(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "get_current_month_pace", lambda dept: None)
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_shop_capacity", lambda: None)
        monkeypatch.setattr(readiness_forecasts, "_month_bounds", lambda today=None: (TODAY, 10, 30))
        result = service_forecast(ADMIN)
        assert result["capacity"]["basis"] == "heuristic"


# ---------------------------------------------------------------------------
# Inventory Forecast
# ---------------------------------------------------------------------------

class TestUnsoldVehicleSignals:

    def test_error_adjustment_is_skipped(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicles", lambda: [ledger.get_entity("VEH-1")] if ledger.get_entity("VEH-1") else [])
        _vehicle("VEH-1", price=20000, cost=15000)
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicles", lambda: [ledger.get_entity("VEH-1")])
        monkeypatch.setattr(readiness_forecasts, "get_age_based_adjustment", lambda vid: {"error": "not found"})
        signals = _unsold_vehicle_signals()
        assert signals == []

    def test_non_dict_adjustment_is_skipped(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicles", lambda: [ledger.get_entity("VEH-1")])
        monkeypatch.setattr(readiness_forecasts, "get_age_based_adjustment", lambda vid: None)
        signals = _unsold_vehicle_signals()
        assert signals == []

    def test_real_margin_computed_from_price_and_cost(self, monkeypatch):
        _vehicle("VEH-1", price=20000, cost=15000)
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicles", lambda: [ledger.get_entity("VEH-1")])
        monkeypatch.setattr(readiness_forecasts, "get_age_based_adjustment",
                             lambda vid: {"estimated_listing_age_days": 5, "age_band": "0-30 days"})
        signals = _unsold_vehicle_signals()
        assert len(signals) == 1
        assert signals[0]["vehicle_id"] == "VEH-1"
        assert signals[0]["price"] == 20000.0
        assert signals[0]["margin_pct"] == 0.25  # (20000-15000)/20000
        assert signals[0]["age_band"] == "0-30 days"

    def test_zero_price_yields_none_margin_and_none_price(self, monkeypatch):
        _vehicle("VEH-1", price=0, cost=0)
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicles", lambda: [ledger.get_entity("VEH-1")])
        monkeypatch.setattr(readiness_forecasts, "get_age_based_adjustment",
                             lambda vid: {"estimated_listing_age_days": 5, "age_band": "0-30 days"})
        signals = _unsold_vehicle_signals()
        assert signals[0]["margin_pct"] is None
        assert signals[0]["price"] is None


class TestInventoryForecast:

    def test_likely_to_sell_requires_fresh_band_and_healthy_margin(self, monkeypatch):
        signals = [
            {"vehicle_id": "V1", "age_band": "0-30 days", "margin_pct": 0.10},  # fresh + healthy -> sell
            {"vehicle_id": "V2", "age_band": "0-30 days", "margin_pct": 0.02},  # fresh but thin -> not sell
            {"vehicle_id": "V3", "age_band": "31-60 days", "margin_pct": 0.10},  # not fresh -> not sell
        ]
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicle_signals", lambda: signals)
        monkeypatch.setattr(readiness_forecasts, "inventory_wholesale_disposition", lambda role: {"count": 0, "candidates": []})
        result = inventory_forecast(ADMIN)
        assert result["units_likely_to_sell"]["count"] == 1
        assert result["units_likely_to_sell"]["vehicles"][0]["vehicle_id"] == "V1"

    def test_likely_to_age_requires_aged_band_and_thin_or_none_margin(self, monkeypatch):
        signals = [
            {"vehicle_id": "V1", "age_band": "61-90 days", "margin_pct": 0.02},  # aged + thin -> age
            {"vehicle_id": "V2", "age_band": "91+ days", "margin_pct": None},  # aged + no margin -> age
            {"vehicle_id": "V3", "age_band": "61-90 days", "margin_pct": 0.10},  # aged but healthy -> not age
            {"vehicle_id": "V4", "age_band": "31-60 days", "margin_pct": 0.02},  # not aged band -> not age
        ]
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicle_signals", lambda: signals)
        monkeypatch.setattr(readiness_forecasts, "inventory_wholesale_disposition", lambda role: {"count": 0, "candidates": []})
        result = inventory_forecast(ADMIN)
        assert result["units_likely_to_age"]["count"] == 2
        aged_ids = {v["vehicle_id"] for v in result["units_likely_to_age"]["vehicles"]}
        assert aged_ids == {"V1", "V2"}

    def test_wholesale_candidates_passthrough(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicle_signals", lambda: [])
        wholesale = {"count": 4, "candidates": []}
        monkeypatch.setattr(readiness_forecasts, "inventory_wholesale_disposition", lambda role: wholesale)
        result = inventory_forecast(ADMIN)
        assert result["wholesale_candidates"] == wholesale

    def test_vehicles_list_capped_at_50(self, monkeypatch):
        signals = [{"vehicle_id": f"V{i}", "age_band": "0-30 days", "margin_pct": 0.20} for i in range(75)]
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicle_signals", lambda: signals)
        monkeypatch.setattr(readiness_forecasts, "inventory_wholesale_disposition", lambda role: {"count": 0, "candidates": []})
        result = inventory_forecast(ADMIN)
        assert result["units_likely_to_sell"]["count"] == 75
        assert len(result["units_likely_to_sell"]["vehicles"]) == 50


# ---------------------------------------------------------------------------
# Finance Forecast
# ---------------------------------------------------------------------------

class TestFinanceForecast:

    def test_funding_forecast_passthrough(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {"tomorrow": {"predicted_value": 1.5}})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda role: {})
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda role, limit=0: {})
        result = finance_forecast(ADMIN)
        assert result["funding"]["forecast_by_horizon"] == {"tomorrow": {"predicted_value": 1.5}}

    def test_collections_passthrough(self, monkeypatch):
        collections = {"total_in_queue": 10}
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda role: collections)
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda role, limit=0: {})
        result = finance_forecast(ADMIN)
        assert result["collections"] == collections

    def test_portfolio_success_splits_into_delinquencies_and_performance(self, monkeypatch):
        portfolio = {
            "delinquency_buckets": {"current": 100}, "total_amount_past_due": 500.0,
            "basis": "simulated_payment_status", "disclaimer": "sim note",
            "total_loans": 300, "active_loans": 290, "payoffs": 10,
            "total_outstanding_balance": 900000.0,
        }
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda role: {})
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda role, limit=0: portfolio)
        result = finance_forecast(ADMIN)
        assert result["delinquencies"]["delinquency_buckets"] == {"current": 100}
        assert result["delinquencies"]["total_amount_past_due"] == 500.0
        assert result["portfolio_performance"]["total_loans"] == 300
        assert result["portfolio_performance"]["active_loans"] == 290

    def test_portfolio_error_degrades_both_fields_to_the_same_error(self, monkeypatch):
        error = {"error": "You don't have access."}
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda role: {})
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda role, limit=0: error)
        result = finance_forecast(SALES)
        assert result["delinquencies"] == error
        assert result["portfolio_performance"] == error


# ---------------------------------------------------------------------------
# get_forecasts_overview -- composition of the 4 department forecasts
# ---------------------------------------------------------------------------

class TestGetForecastsOverview:

    def _patch_all(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "sales_forecast", lambda role: {"fake": "sales"})
        monkeypatch.setattr(readiness_forecasts, "service_forecast", lambda role: {"fake": "service"})
        monkeypatch.setattr(readiness_forecasts, "inventory_forecast", lambda role: {"fake": "inventory"})
        monkeypatch.setattr(readiness_forecasts, "finance_forecast", lambda role: {"fake": "finance"})

    def test_composes_all_four_departments(self, monkeypatch):
        self._patch_all(monkeypatch)
        overview = get_forecasts_overview(ADMIN)
        assert overview["sales"] == {"fake": "sales"}
        assert overview["service"] == {"fake": "service"}
        assert overview["inventory"] == {"fake": "inventory"}
        assert overview["finance"] == {"fake": "finance"}

    def test_no_blended_forecast_is_ever_computed(self, monkeypatch):
        self._patch_all(monkeypatch)
        overview = get_forecasts_overview(ADMIN)
        assert "cross_department_blended_forecast" in overview["not_yet_tracked"]

    def test_marketing_honest_gap_note_present(self, monkeypatch):
        self._patch_all(monkeypatch)
        overview = get_forecasts_overview(ADMIN)
        assert "marketing_forecast" in overview["not_yet_tracked"]

    def test_generated_at_present(self, monkeypatch):
        self._patch_all(monkeypatch)
        overview = get_forecasts_overview(ADMIN)
        assert "generated_at" in overview


# ---------------------------------------------------------------------------
# Readiness Timeline capstone
# ---------------------------------------------------------------------------

class TestGetReadinessTimelineOverview:

    def test_composes_all_departments_trend(self, monkeypatch):
        trend = {"sales": {"trend_direction": "up"}, "service": {"trend_direction": "flat"}}
        monkeypatch.setattr(readiness_forecasts, "all_departments_historical_trend", lambda: trend)
        overview = get_readiness_timeline_overview()
        assert overview["departments"] == trend

    def test_covered_departments_is_present(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "all_departments_historical_trend", lambda: {})
        overview = get_readiness_timeline_overview()
        assert "covered_departments" in overview

    def test_uncovered_departments_note_present(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "all_departments_historical_trend", lambda: {})
        overview = get_readiness_timeline_overview()
        assert "uncovered_departments" in overview["not_yet_tracked"]

    def test_generated_at_present(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "all_departments_historical_trend", lambda: {})
        overview = get_readiness_timeline_overview()
        assert "generated_at" in overview


class TestGetReadinessTimelineDepartment:

    def test_delegates_to_historical_trend_lowercased_by_the_api_layer(self, monkeypatch):
        # get_readiness_timeline_department() itself does NOT lowercase --
        # confirm it's a direct passthrough to historical_trend().
        monkeypatch.setattr(readiness_forecasts, "historical_trend", lambda dept: {"department": dept})
        result = get_readiness_timeline_department("sales")
        assert result == {"department": "sales"}

    def test_unknown_department_returns_none(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "historical_trend", lambda dept: None)
        result = get_readiness_timeline_department("bogus")
        assert result is None


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetForecastsOverviewApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda r: {})
        monkeypatch.setattr(readiness_forecasts, "get_current_month_pace", lambda dept: None)
        monkeypatch.setattr(readiness_forecasts, "get_shop_capacity", lambda: {})
        monkeypatch.setattr(readiness_forecasts, "_unsold_vehicle_signals", lambda: [])
        monkeypatch.setattr(readiness_forecasts, "inventory_wholesale_disposition", lambda r: {})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda r: {})
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda r, limit=0: {})
        result = get_forecasts_overview_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_forecasts_overview_api("NOT_A_REAL_ROLE")
        assert result == {"error": "You don't have access to Readiness Forecasts data."}


class TestGetForecastsDepartmentApi:

    def test_unknown_role_denied(self):
        result = get_forecasts_department_api("NOT_A_REAL_ROLE", "sales")
        assert "error" in result

    def test_unknown_department_returns_error_naming_valid_choices(self):
        result = get_forecasts_department_api(ADMIN, "bogus")
        assert "error" in result
        assert "bogus" in result["error"]

    def test_dispatches_to_sales_forecast(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "_sales_overview", lambda role: {})
        result = get_forecasts_department_api(ADMIN, "SALES")  # case-insensitive
        assert "units" in result

    def test_dispatches_to_finance_forecast(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "predict_all_horizons", lambda dept: {})
        monkeypatch.setattr(readiness_forecasts, "get_collections_dashboard_api", lambda role: {})
        monkeypatch.setattr(readiness_forecasts, "get_portfolio_dashboard_api", lambda role, limit=0: {})
        result = get_forecasts_department_api(ADMIN, "finance")
        assert "funding" in result


class TestGetReadinessTimelineOverviewApi:

    def test_unknown_role_denied(self):
        result = get_readiness_timeline_overview_api("NOT_A_REAL_ROLE")
        assert "error" in result

    def test_allowed_role_returns_real_data(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "all_departments_historical_trend", lambda: {})
        result = get_readiness_timeline_overview_api(ADMIN)
        assert "departments" in result


class TestGetReadinessTimelineDepartmentApi:

    def test_unknown_role_denied(self):
        result = get_readiness_timeline_department_api("NOT_A_REAL_ROLE", "sales")
        assert "error" in result

    def test_none_result_wrapped_in_honest_error(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "historical_trend", lambda dept: None)
        result = get_readiness_timeline_department_api(ADMIN, "bogus")
        assert "error" in result
        assert "bogus" in result["error"]

    def test_real_result_passed_through(self, monkeypatch):
        monkeypatch.setattr(readiness_forecasts, "historical_trend", lambda dept: {"department": dept, "trend_direction": "up"})
        result = get_readiness_timeline_department_api(ADMIN, "sales")
        assert result["trend_direction"] == "up"
