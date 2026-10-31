"""
Tests for core/readiness_scenarios.py / core/readiness_scenarios_api.py --
Readiness' "Scenarios" item (What-If Modeling): Marketing/Lead Volume, Inventory
Pricing, Staffing, and Finance Portfolio.

Every projection is a transparent formula over real current-data ratios already
computed elsewhere in this codebase, so the already-real upstream engines
(core/business_health.py's sales_health(), core/service_reporting.py's
get_technician_scorecard(), core/shop_control.py's _service_technicians(),
core/loan_servicing_api.py/core/collections_api.py/core/loan_accounting.py's
dashboards) are monkeypatched directly on core.readiness_scenarios's own
namespace, matching the composition-boundary testing pattern already established
elsewhere in this Readiness test suite. Inventory Pricing's own mechanical
band-shift math is genuinely new computation in this module, so it's tested
against real Vehicle ledger fixtures instead.

This module makes zero graph mutations -- pure read-only calculation.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DEAL, SERVICE_RECORD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import readiness_scenarios
from core.readiness_scenarios import (
    get_scenario_catalog,
    marketing_lead_volume_scenario,
    inventory_pricing_scenario,
    staffing_scenario,
    finance_portfolio_scenario,
    DEFAULT_ASSUMED_COST_PER_LEAD,
)
from core import readiness_scenarios_api
from core.readiness_scenarios_api import (
    get_scenario_catalog_api,
    run_marketing_lead_volume_scenario_api,
    run_inventory_pricing_scenario_api,
    run_staffing_scenario_api,
    run_finance_portfolio_scenario_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _vehicle(vehicle_id, price, cost=None, date_sold=None):
    attrs = {"Price": str(price)}
    if cost is not None:
        attrs["Cost"] = str(cost)
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))


def _deal(deal_id, status="funded"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={"status": status}))


def _service_record(record_id, service_date, technician_id="EMP-1", cost=100, parts_cost=0):
    ledger.add_entity(Entity(id=record_id, entity_type=SERVICE_RECORD, attributes={
        "ServiceDate": service_date, "Technician": technician_id,
        "Cost": str(cost), "PartsCost": str(parts_cost),
    }))


# ---------------------------------------------------------------------------
# Scenario Catalog
# ---------------------------------------------------------------------------

class TestGetScenarioCatalog:

    def test_returns_all_four_real_scenario_types(self):
        catalog = get_scenario_catalog()
        keys = [s["key"] for s in catalog["scenario_types"]]
        assert keys == ["marketing_lead_volume", "inventory_pricing", "staffing", "finance_portfolio"]

    def test_marketing_scenario_has_three_inputs(self):
        catalog = get_scenario_catalog()
        marketing = next(s for s in catalog["scenario_types"] if s["key"] == "marketing_lead_volume")
        input_keys = [i["key"] for i in marketing["inputs"]]
        assert input_keys == ["additional_leads", "additional_ad_spend", "assumed_cost_per_lead"]

    def test_finance_portfolio_scenario_requires_growth_pct(self):
        catalog = get_scenario_catalog()
        finance = next(s for s in catalog["scenario_types"] if s["key"] == "finance_portfolio")
        assert finance["inputs"][0]["key"] == "portfolio_growth_pct"
        assert finance["inputs"][0]["required"] is True


# ---------------------------------------------------------------------------
# Marketing / Lead Volume
# ---------------------------------------------------------------------------

class TestMarketingLeadVolumeScenario:

    def test_direct_lead_volume_path(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 100000.0},
        })
        _deal("DEAL-1")
        _deal("DEAL-2")

        result = marketing_lead_volume_scenario(ADMIN, additional_leads=50)

        assert result["input_path"] == "direct_lead_volume"
        assert result["assumption_used"] is None
        assert result["real_ratios_used"]["avg_gross_per_sale"] == 50000.0  # 100000 / 2
        assert result["projection"]["projected_additional_sales"] == 10.0  # 50 * 0.20
        assert result["projection"]["projected_additional_gross_profit"] == 500000.0  # 10 * 50000

    def test_assumed_spend_to_lead_path_uses_default_rate(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 0.0},
        })
        result = marketing_lead_volume_scenario(ADMIN, additional_leads=None, additional_ad_spend=4500.0)

        assert result["input_path"] == "assumed_spend_to_lead"
        assert result["assumption_used"]["assumed_cost_per_lead"] == DEFAULT_ASSUMED_COST_PER_LEAD
        assert result["inputs"]["additional_leads"] == 100.0  # 4500 / 45

    def test_assumed_spend_to_lead_path_uses_custom_rate(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 0.0},
        })
        result = marketing_lead_volume_scenario(ADMIN, additional_ad_spend=1000.0, assumed_cost_per_lead=50.0)

        assert result["assumption_used"]["assumed_cost_per_lead"] == 50.0
        assert result["inputs"]["additional_leads"] == 20.0  # 1000 / 50

    def test_zero_assumed_cost_per_lead_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 0.0},
        })
        result = marketing_lead_volume_scenario(ADMIN, additional_ad_spend=450.0, assumed_cost_per_lead=0)
        assert result["assumption_used"]["assumed_cost_per_lead"] == DEFAULT_ASSUMED_COST_PER_LEAD

    def test_no_spend_or_leads_produces_zero_leads(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 0.0},
        })
        result = marketing_lead_volume_scenario(ADMIN)
        assert result["inputs"]["additional_leads"] == 0.0

    def test_missing_close_rate_leaves_projection_none(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": None}, "gross_profit": {"value": 100000.0},
        })
        _deal("DEAL-1")
        result = marketing_lead_volume_scenario(ADMIN, additional_leads=50)
        assert result["projection"]["projected_additional_sales"] is None
        assert result["projection"]["projected_additional_gross_profit"] is None

    def test_zero_funded_deals_leaves_avg_gross_per_sale_none(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 100000.0},
        })
        result = marketing_lead_volume_scenario(ADMIN, additional_leads=50)
        assert result["real_ratios_used"]["avg_gross_per_sale"] is None
        assert result["projection"]["projected_additional_gross_profit"] is None
        # Sales are still projectable off the real close rate alone.
        assert result["projection"]["projected_additional_sales"] == 10.0

    def test_non_funded_deals_are_excluded_from_funded_count(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda role: {
            "close_rate": {"value": 20.0}, "gross_profit": {"value": 40000.0},
        })
        _deal("DEAL-1", status="funded")
        _deal("DEAL-2", status="contract")  # not funded, excluded
        result = marketing_lead_volume_scenario(ADMIN, additional_leads=10)
        assert result["real_ratios_used"]["funded_deals_count"] == 1
        assert result["real_ratios_used"]["avg_gross_per_sale"] == 40000.0


# ---------------------------------------------------------------------------
# Inventory Pricing
# ---------------------------------------------------------------------------

class TestInventoryPricingScenario:

    def test_band_shift_when_reduction_pushes_into_a_lower_band(self):
        # price 25100 (25k_40k band), cost 20000, reduction 200
        # -> new_price 24900 (15k_25k band), margin_floor 20600 (feasible)
        _vehicle("VEH-1", price=25100, cost=20000)
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=200)
        assert result["projection"]["vehicles_would_shift_band"] == 1
        assert result["projection"]["band_distribution_before"]["25k_40k"] == 1
        assert result["projection"]["band_distribution_after"]["15k_25k"] == 1

    def test_blocked_by_margin_floor(self):
        # price 20000, cost 19500, reduction 1000 -> new_price 19000
        # margin_floor = 19500 * 1.03 = 20085 -- not feasible
        _vehicle("VEH-1", price=20000, cost=19500)
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=1000)
        assert result["projection"]["vehicles_blocked_by_margin_floor"] == 1
        assert result["projection"]["vehicles_would_shift_band"] == 0
        # Blocked vehicles stay in their original band in the "after" distribution.
        assert result["projection"]["band_distribution_after"]["15k_25k"] == 1

    def test_feasible_but_no_band_shift(self):
        # price 30000, cost 20000, reduction 500 -> new_price 29500, still 25k_40k
        _vehicle("VEH-1", price=30000, cost=20000)
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=500)
        assert result["projection"]["vehicles_would_shift_band"] == 0
        assert result["projection"]["vehicles_blocked_by_margin_floor"] == 0
        assert result["projection"]["total_margin_dollars_given_up"] == 500.0

    def test_unknown_cost_vehicle_is_not_feasible_and_counted_separately(self):
        _vehicle("VEH-1", price=20000, cost=None)  # no real Cost on file
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=500)
        assert result["projection"]["vehicles_unknown_cost"] == 1
        assert result["projection"]["vehicles_blocked_by_margin_floor"] == 0
        assert result["projection"]["vehicles_would_shift_band"] == 0

    def test_sold_vehicles_are_excluded(self):
        _vehicle("VEH-1", price=20000, cost=15000, date_sold="2026-01-01")
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=500)
        assert result["projection"]["vehicles_evaluated"] == 0

    def test_price_band_filter_narrows_evaluation(self):
        _vehicle("VEH-1", price=10000, cost=8000)   # under_15k
        _vehicle("VEH-2", price=30000, cost=20000)  # 25k_40k
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=100, price_band="under_15k")
        assert result["projection"]["vehicles_evaluated"] == 1

    def test_all_price_band_evaluates_everything(self):
        _vehicle("VEH-1", price=10000, cost=8000)
        _vehicle("VEH-2", price=30000, cost=20000)
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=100, price_band="all")
        assert result["projection"]["vehicles_evaluated"] == 2

    def test_multiple_vehicles_aggregate_total_margin_given_up(self):
        _vehicle("VEH-1", price=20000, cost=10000)
        _vehicle("VEH-2", price=22000, cost=10000)
        result = inventory_pricing_scenario(ADMIN, price_reduction_amount=300)
        assert result["projection"]["total_margin_dollars_given_up"] == 600.0


# ---------------------------------------------------------------------------
# Staffing
# ---------------------------------------------------------------------------

class TestStaffingScenario:

    def _fake_technician(self, tech_id):
        class _T:
            id = tech_id
        return _T()

    def test_capacity_increase_and_labor_projection(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "_service_technicians", lambda: [self._fake_technician("EMP-1"), self._fake_technician("EMP-2")])
        monkeypatch.setattr(readiness_scenarios, "get_technician_scorecard", lambda: {
            "technicians": [{"technician_id": "EMP-1", "total_revenue": 60000.0}, {"technician_id": "EMP-2", "total_revenue": 60000.0}],
        })
        _service_record("SR-1", "2026-01-15")
        _service_record("SR-2", "2026-06-15")  # 5 real elapsed months (Jan->Jun)

        result = staffing_scenario(ADMIN, additional_technicians=1)

        assert result["real_ratios_used"]["current_technician_count"] == 2
        assert result["real_ratios_used"]["total_revenue_all_time"] == 120000.0
        assert result["real_ratios_used"]["months_of_data"] == 5
        assert result["real_ratios_used"]["avg_revenue_per_technician_all_time"] == 60000.0
        assert result["real_ratios_used"]["avg_monthly_revenue_per_technician"] == 12000.0  # 60000 / 5
        assert result["projection"]["capacity_increase_pct"] == 50.0  # 1 / 2 * 100
        assert result["projection"]["projected_monthly_labor_increase"] == 12000.0  # 1 * 12000

    def test_no_service_records_defaults_to_one_month(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "_service_technicians", lambda: [self._fake_technician("EMP-1")])
        monkeypatch.setattr(readiness_scenarios, "get_technician_scorecard", lambda: {
            "technicians": [{"technician_id": "EMP-1", "total_revenue": 6000.0}],
        })
        result = staffing_scenario(ADMIN, additional_technicians=1)
        assert result["real_ratios_used"]["months_of_data"] == 1
        assert result["real_ratios_used"]["avg_monthly_revenue_per_technician"] == 6000.0

    def test_zero_current_technicians_leaves_projections_none(self, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "_service_technicians", lambda: [])
        monkeypatch.setattr(readiness_scenarios, "get_technician_scorecard", lambda: {"technicians": []})
        result = staffing_scenario(ADMIN, additional_technicians=2)
        assert result["real_ratios_used"]["current_technician_count"] == 0
        assert result["real_ratios_used"]["avg_revenue_per_technician_all_time"] is None
        assert result["projection"]["capacity_increase_pct"] is None
        assert result["projection"]["projected_monthly_labor_increase"] is None


# ---------------------------------------------------------------------------
# Finance Portfolio
# ---------------------------------------------------------------------------

class TestFinancePortfolioScenario:

    def _patch(self, monkeypatch, portfolio, collections=None, accounting=None):
        monkeypatch.setattr(readiness_scenarios, "get_portfolio_dashboard_api", lambda role, limit=0: portfolio)
        monkeypatch.setattr(readiness_scenarios, "get_collections_dashboard_api", lambda role: collections or {})
        monkeypatch.setattr(readiness_scenarios, "get_loan_accounting_summary", lambda: accounting or {})

    def test_portfolio_access_denied_returns_early(self, monkeypatch):
        self._patch(monkeypatch, {"error": "You don't have access."})
        result = finance_portfolio_scenario(SALES, portfolio_growth_pct=10)
        assert result["error"] == "You don't have access."
        assert "note" in result

    def test_real_projection_math(self, monkeypatch):
        portfolio = {
            "total_outstanding_balance": 1000000.0, "total_loans": 200,
            "delinquency_buckets": {"current": 150, "30_day": 20, "60_day": 15, "90_day": 10, "repossessed": 3, "charged_off": 2},
        }
        accounting = {"interest_income_recognized": 5000.0}
        self._patch(monkeypatch, portfolio, collections={"queue_count": 10}, accounting=accounting)

        result = finance_portfolio_scenario(ADMIN, portfolio_growth_pct=10)

        delinquent_count = 20 + 15 + 10 + 3 + 2  # 50
        assert result["real_ratios_used"]["current_delinquency_rate_pct"] == 25.0  # 50/200*100
        assert result["real_ratios_used"]["observed_yield_pct"] == 0.5  # 5000/1000000*100
        assert result["projection"]["projected_additional_outstanding_balance"] == 100000.0  # 1000000 * 0.10
        assert result["projection"]["projected_additional_interest_income"] == 500.0  # 5000 * 0.10
        assert result["projection"]["projected_additional_loans"] == 20.0  # 200 * 0.10
        assert result["projection"]["projected_additional_delinquent_loans"] == 5.0  # 20 * 0.25
        assert result["collections_context"] == {"queue_count": 10}

    def test_collections_error_is_passed_through_narrowly(self, monkeypatch):
        portfolio = {"total_outstanding_balance": 1000.0, "total_loans": 10, "delinquency_buckets": {}}
        self._patch(monkeypatch, portfolio, collections={"error": "denied"}, accounting={})
        result = finance_portfolio_scenario(ADMIN, portfolio_growth_pct=5)
        assert result["collections_context"] == {"error": "denied"}

    def test_zero_outstanding_balance_leaves_yield_and_interest_projection_none(self, monkeypatch):
        portfolio = {"total_outstanding_balance": 0.0, "total_loans": 0, "delinquency_buckets": {}}
        self._patch(monkeypatch, portfolio, accounting={"interest_income_recognized": 0.0})
        result = finance_portfolio_scenario(ADMIN, portfolio_growth_pct=10)
        assert result["real_ratios_used"]["observed_yield_pct"] is None
        assert result["projection"]["projected_additional_interest_income"] is None

    def test_zero_total_loans_leaves_delinquency_rate_and_projection_none(self, monkeypatch):
        portfolio = {"total_outstanding_balance": 5000.0, "total_loans": 0, "delinquency_buckets": {}}
        self._patch(monkeypatch, portfolio, accounting={"interest_income_recognized": 0.0})
        result = finance_portfolio_scenario(ADMIN, portfolio_growth_pct=10)
        assert result["real_ratios_used"]["current_delinquency_rate_pct"] is None
        assert result["projection"]["projected_additional_delinquent_loans"] is None


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetScenarioCatalogApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = get_scenario_catalog_api(role)
        assert "scenario_types" in result

    def test_unknown_role_denied(self):
        result = get_scenario_catalog_api("NOT_A_REAL_ROLE")
        assert result == {"error": "You don't have access to Readiness Scenarios."}


class TestRunMarketingLeadVolumeScenarioApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "sales_health", lambda r: {"close_rate": {"value": 10.0}, "gross_profit": {"value": 0.0}})
        result = run_marketing_lead_volume_scenario_api(role, additional_leads=10)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = run_marketing_lead_volume_scenario_api("NOT_A_REAL_ROLE", additional_leads=10)
        assert "error" in result


class TestRunInventoryPricingScenarioApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role):
        result = run_inventory_pricing_scenario_api(role, price_reduction_amount=500)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = run_inventory_pricing_scenario_api("NOT_A_REAL_ROLE", price_reduction_amount=500)
        assert "error" in result


class TestRunStaffingScenarioApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "_service_technicians", lambda: [])
        monkeypatch.setattr(readiness_scenarios, "get_technician_scorecard", lambda: {"technicians": []})
        result = run_staffing_scenario_api(role, additional_technicians=1)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = run_staffing_scenario_api("NOT_A_REAL_ROLE", additional_technicians=1)
        assert "error" in result


class TestRunFinancePortfolioScenarioApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_allowed(self, role, monkeypatch):
        monkeypatch.setattr(readiness_scenarios, "get_portfolio_dashboard_api", lambda r, limit=0: {"total_outstanding_balance": 0.0, "total_loans": 0, "delinquency_buckets": {}})
        monkeypatch.setattr(readiness_scenarios, "get_collections_dashboard_api", lambda r: {})
        monkeypatch.setattr(readiness_scenarios, "get_loan_accounting_summary", lambda: {})
        result = run_finance_portfolio_scenario_api(role, portfolio_growth_pct=10)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = run_finance_portfolio_scenario_api("NOT_A_REAL_ROLE", portfolio_growth_pct=10)
        assert "error" in result
