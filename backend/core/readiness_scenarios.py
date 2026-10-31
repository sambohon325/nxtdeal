"""
core/readiness_scenarios.py -- Readiness' "Scenarios" item (What-If Modeling),
item #6 of Sam's 10-item Enterprise Readiness & Intelligence structure (this same
reframe session). Sam's own framing: "one of NXTDeal' most powerful features" --
"Increase ad spend by $5,000 -> Projected: +74 Leads, +12 Sales, +$41,000 Gross,"
"Reduce prices $500 -> Forecast: Days Supply Reduced 18%," "Hire 2 Technicians ->
Forecast: +18% Capacity, +$34,000 Monthly Labor," "Increase portfolio by 10% ->
Expected Yield, Expected Risk, Expected Delinquencies."

The prior placeholder here (core/readiness_menu.py's old simulations()) correctly
flagged that no what-if/scenario engine existed anywhere in this codebase, and
that a real build would need "a scenario input model run through
core/prediction.py's existing blended-rate math." This module is that build --
but it is deliberately NOT an LLM-guessed or invented-multiplier engine. Every
projection here is a transparent FORMULA over REAL current-data ratios already
computed elsewhere in this codebase, with the real inputs and the real ratio
applied always returned alongside the output so a caller can audit the math,
not just trust it. Same "real rules engine, never fake AI" discipline this
whole reframe session already established for Recommendations
(core/readiness_recommendations.py) and the Executive Summary
(core/readiness_overview.py).

Per-scenario real-basis research, done before writing any formula (see each
function's own docstring for the full trace):

  - Marketing / Lead Volume: core/business_health.py's sales_health() already
    computes a real close_rate (average per-salesperson conversion %, off
    core/leaderboard_api.py) and a real gross_profit_funded_deals total. This
    module derives a real avg_gross_per_sale from those two (gross / funded
    deal count, counted the identical way core/sales_menu.py's overview()
    counts funded deals) and chains: leads -> real close rate -> sales -> real
    avg gross -> gross $. That whole chain is 100% real ratios.

    The one genuine gap: core/advertising.py's own module docstring confirms
    "No real ad spend, no real delivery -- impressions/clicks/CPC/ROAS are
    explicitly not_yet_tracked" (session 83), and core/marketing_menu.py's own
    _campaigns() confirms "Campaign has no budget/spend field in this data
    model yet." There is NO real dollars-spent-to-leads-generated ratio
    anywhere in this codebase to compute from -- inventing one would be
    exactly the fabrication this module exists to avoid. So a caller has two
    honest options, both offered here: (1) supply additional_leads directly
    (100% real chain from there), or (2) supply additional_ad_spend PLUS an
    explicit, editable assumed_cost_per_lead input (default $45, a labeled
    ASSUMPTION the caller can override, never presented as a computed fact)
    to derive additional_leads = spend / assumed_cost_per_lead first. Every
    response marks exactly which path was used and flags the assumption
    input by name when option (2) is used.

  - Inventory Pricing: core/inventory_aging.py's own module docstring already
    established that Vehicle has no acquisition-date field anywhere in this
    codebase, so true day-based aging (and any real price-elasticity/
    days-to-sell correlation) can't be computed -- confirmed via grep, no
    such correlation exists anywhere. Rather than fabricate a "days supply
    reduced by N%" figure, this module reuses the exact real, mechanical
    PRICE_BANDS logic (core/inventory_aging.py's _band_for) and the real
    3%-over-Cost margin floor (core/pricing_desk.py's own established rule)
    to compute, for every real unsold vehicle a reduction would apply to,
    whether the new price clears the real margin floor and which real price
    band it would land in. The output is a real, mechanical band-shift count
    -- not a fabricated elasticity claim.

  - Staffing: core/service_reporting.py's get_technician_scorecard() already
    computes real all-time total_revenue per technician off
    ServiceRecord.Technician (Cost - PartsCost, the same real per-technician
    attribution core/employee_value.py's _real_service_value() established).
    This module divides that real total by a real, computed number of
    elapsed months (min-to-max real ServiceRecord.ServiceDate across the
    whole department) to get a real avg-monthly-revenue-per-technician -- no
    assumed workdays/month or invented capacity-dollar constant needed
    anywhere. Capacity % is real headcount math (additional / current real
    technician count).

  - Finance Portfolio: core/loan_servicing_api.py's get_portfolio_dashboard_api()
    (real, schedule-implied total_outstanding_balance + delinquency_buckets)
    and core/loan_accounting.py's get_loan_accounting_summary() (real,
    cash-basis interest_income_recognized off actually-recorded Payments) are
    both real. This module derives a real observed yield rate (interest
    income recognized / current outstanding balance) and a real delinquency
    rate (delinquent loan count / total loan count -- itself an aggregate
    over core/loan_servicing.py's own SIMULATED per-loan delinquency-bucket
    layer, labeled as such) and scales both proportionally to a
    caller-specified portfolio_growth_pct. Both source functions are
    ADMIN/OPERATIONS/FINANCE-gated at their own layer
    (core/collections_api.py/core/loan_servicing_api.py) -- a caller outside
    that role set sees that field's own real access-denied error passed
    straight through, same degrade-gracefully convention
    core/business_health.py's finance_health() already established, not
    silently re-gated or faked here.

This module makes ZERO graph mutations -- every function here is a pure,
read-only calculation over already-real data.
"""

from datetime import date

from core.dealeros import ledger
from core.entity_types import DEAL, SERVICE_RECORD

from core.business_health import sales_health
from core.inventory_aging import PRICE_BANDS, _band_for, _vehicle_brief
from core.workflow_tab_data import _unsold_vehicles
from core.service_reporting import get_technician_scorecard
from core.shop_control import _service_technicians
from core.loan_servicing_api import get_portfolio_dashboard_api
from core.collections_api import get_collections_dashboard_api
from core.loan_accounting import get_loan_accounting_summary

DEFAULT_ASSUMED_COST_PER_LEAD = 45.00

_DELINQUENT_BUCKETS = ("30_day", "60_day", "90_day", "repossessed", "charged_off")


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _months_elapsed(start, end):
    """Whole calendar months between two real dates, floored at 1 so a division
    against it never blows up on a same-day/short data window."""

    if not start or not end or end < start:
        return 1
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(1, months)


def _funded_deals():
    """Identical filter to core/sales_menu.py's overview() -- the real, existing
    definition of a funded Deal in this codebase, reused rather than redefined."""

    return [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]


# ---------------------------------------------------------------------------
# Scenario Catalog -- describes the 4 real scenario types + their real input
# fields, so a caller (the frontend's dynamic form builder) never has to
# hardcode field lists separately from what this module actually accepts.
# ---------------------------------------------------------------------------

def get_scenario_catalog():

    return {
        "scenario_types": [
            {
                "key": "marketing_lead_volume",
                "label": "Marketing / Lead Volume",
                "description": "Project sales and gross profit from an increase in lead volume, using this dealership's own real close rate and average gross per sale.",
                "inputs": [
                    {"key": "additional_leads", "label": "Additional Leads", "type": "int", "required": False},
                    {"key": "additional_ad_spend", "label": "Additional Ad Spend ($)", "type": "float", "required": False},
                    {"key": "assumed_cost_per_lead", "label": "Assumed Cost Per Lead ($, editable assumption)", "type": "float", "required": False, "default": DEFAULT_ASSUMED_COST_PER_LEAD},
                ],
                "note": "Supply either additional_leads directly (100% real chain) or additional_ad_spend (derives leads via the editable assumed_cost_per_lead -- no real spend-to-lead ratio exists anywhere in this codebase, see module docstring).",
            },
            {
                "key": "inventory_pricing",
                "label": "Inventory Pricing",
                "description": "Project how many unsold vehicles would shift into a more competitive price band from a price reduction, mechanically, against the real 3%-over-cost margin floor.",
                "inputs": [
                    {"key": "price_reduction_amount", "label": "Price Reduction ($)", "type": "float", "required": True},
                    {"key": "price_band", "label": "Price Band (optional filter)", "type": "string", "required": False, "options": [b[0] for b in PRICE_BANDS] + ["all"]},
                ],
            },
            {
                "key": "staffing",
                "label": "Staffing",
                "description": "Project added shop capacity and monthly labor revenue from hiring additional technicians, using this dealership's own real historical revenue-per-technician rate.",
                "inputs": [
                    {"key": "additional_technicians", "label": "Additional Technicians", "type": "int", "required": True},
                ],
            },
            {
                "key": "finance_portfolio",
                "label": "Finance Portfolio",
                "description": "Project expected yield, delinquencies, and outstanding balance from growing the loan portfolio, using this dealership's own real observed yield and delinquency rates.",
                "inputs": [
                    {"key": "portfolio_growth_pct", "label": "Portfolio Growth (%)", "type": "float", "required": True},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Marketing / Lead Volume
# ---------------------------------------------------------------------------

def marketing_lead_volume_scenario(role, additional_leads=None, additional_ad_spend=None, assumed_cost_per_lead=None):

    health = sales_health(role)

    close_rate_pct = health.get("close_rate", {}).get("value")
    gross_profit_total = health.get("gross_profit", {}).get("value") or 0.0
    funded_count = len(_funded_deals())

    avg_gross_per_sale = round(gross_profit_total / funded_count, 2) if funded_count else None

    assumption_used = None

    if additional_leads is None:
        input_path = "assumed_spend_to_lead"
        rate = assumed_cost_per_lead if assumed_cost_per_lead else DEFAULT_ASSUMED_COST_PER_LEAD
        spend = additional_ad_spend or 0.0
        additional_leads = round(spend / rate, 1) if rate else 0
        assumption_used = {
            "assumed_cost_per_lead": rate,
            "note": "No real dollars-spent-to-leads-generated ratio exists anywhere in this codebase (core/advertising.py's own launches carry no real spend/impression/click data, core/campaigns.py has no budget field) -- this is an editable ASSUMPTION input, not a computed fact.",
        }
    else:
        input_path = "direct_lead_volume"

    projected_sales = None
    projected_gross = None
    if close_rate_pct is not None:
        projected_sales = round(additional_leads * (close_rate_pct / 100), 1)
    if projected_sales is not None and avg_gross_per_sale is not None:
        projected_gross = round(projected_sales * avg_gross_per_sale, 2)

    return {
        "scenario_type": "marketing_lead_volume",
        "input_path": input_path,
        "inputs": {
            "additional_leads": additional_leads,
            "additional_ad_spend": additional_ad_spend,
        },
        "assumption_used": assumption_used,
        "real_ratios_used": {
            "close_rate_pct": close_rate_pct,
            "close_rate_basis": "real -- average per-salesperson conversion rate, core/leaderboard_api.py, via core/business_health.py's sales_health().",
            "funded_deals_count": funded_count,
            "gross_profit_funded_deals_total": gross_profit_total,
            "avg_gross_per_sale": avg_gross_per_sale,
            "avg_gross_per_sale_basis": "real -- gross_profit_funded_deals / funded deal count, both real (core/sales_menu.py's overview()).",
        },
        "projection": {
            "additional_leads": additional_leads,
            "projected_additional_sales": projected_sales,
            "projected_additional_gross_profit": projected_gross,
            "formula": "projected_additional_sales = additional_leads * (real close_rate_pct / 100); projected_additional_gross_profit = projected_additional_sales * real avg_gross_per_sale.",
        },
    }


# ---------------------------------------------------------------------------
# Inventory Pricing
# ---------------------------------------------------------------------------

def inventory_pricing_scenario(role, price_reduction_amount, price_band=None):

    vehicles = [_vehicle_brief(v) for v in _unsold_vehicles()]

    if price_band and price_band != "all":
        vehicles = [v for v in vehicles if v["price_band"] == price_band]

    before_bands = {label: 0 for label, _, _ in PRICE_BANDS}
    after_bands = {label: 0 for label, _, _ in PRICE_BANDS}

    would_shift = 0
    blocked_by_margin_floor = 0
    unknown_cost = 0
    total_reduction_given = 0.0

    for v in vehicles:
        before_bands[v["price_band"]] += 1

        price = v["price"] or 0.0
        cost = v["cost"]
        new_price = price - price_reduction_amount

        if cost is None:
            unknown_cost += 1
            after_bands[v["price_band"]] += 1
            continue

        margin_floor = round(cost * 1.03, 2)
        feasible = new_price >= margin_floor

        if not feasible:
            blocked_by_margin_floor += 1
            after_bands[v["price_band"]] += 1
            continue

        new_band = _band_for(new_price)
        after_bands[new_band] += 1
        total_reduction_given += price_reduction_amount

        if new_band != v["price_band"]:
            would_shift += 1

    return {
        "scenario_type": "inventory_pricing",
        "inputs": {
            "price_reduction_amount": price_reduction_amount,
            "price_band": price_band or "all",
        },
        "real_ratios_used": {
            "vehicles_evaluated": len(vehicles),
            "margin_floor_basis": "real -- 3% over each vehicle's real Cost (core/pricing_desk.py's established margin-floor rule).",
            "price_band_basis": "real, mechanical -- core/inventory_aging.py's PRICE_BANDS/_band_for(), same bands the Aging Action Center already uses.",
        },
        "not_yet_tracked": {
            "days_supply_reduction": "Vehicle has no acquisition-date field anywhere in this codebase, so no real day-based aging or price-elasticity/days-to-sell correlation exists to compute a 'days supply reduced by N%' figure from -- the real, mechanical band-shift count below is the honest analog.",
        },
        "projection": {
            "vehicles_evaluated": len(vehicles),
            "vehicles_would_shift_band": would_shift,
            "vehicles_blocked_by_margin_floor": blocked_by_margin_floor,
            "vehicles_unknown_cost": unknown_cost,
            "total_margin_dollars_given_up": round(total_reduction_given, 2),
            "band_distribution_before": before_bands,
            "band_distribution_after": after_bands,
            "formula": "For each real unsold vehicle: new_price = price - reduction; feasible if new_price >= real Cost * 1.03; if feasible, new price band recomputed via the real PRICE_BANDS thresholds.",
        },
    }


# ---------------------------------------------------------------------------
# Staffing
# ---------------------------------------------------------------------------

def staffing_scenario(role, additional_technicians):

    technicians = _service_technicians()
    current_count = len(technicians)

    scorecard = get_technician_scorecard()
    total_revenue_all_time = sum(t["total_revenue"] for t in scorecard["technicians"])

    records = _entities(SERVICE_RECORD)
    dates = [d for d in (_parse_date(r.attributes.get("ServiceDate")) for r in records) if d]
    months_of_data = _months_elapsed(min(dates), max(dates)) if dates else 1

    avg_revenue_per_tech_all_time = round(total_revenue_all_time / current_count, 2) if current_count else None
    avg_monthly_revenue_per_tech = round(avg_revenue_per_tech_all_time / months_of_data, 2) if avg_revenue_per_tech_all_time is not None else None

    capacity_increase_pct = round((additional_technicians / current_count) * 100, 1) if current_count else None
    projected_monthly_labor_increase = round(additional_technicians * avg_monthly_revenue_per_tech, 2) if avg_monthly_revenue_per_tech is not None else None

    return {
        "scenario_type": "staffing",
        "inputs": {
            "additional_technicians": additional_technicians,
        },
        "real_ratios_used": {
            "current_technician_count": current_count,
            "current_technician_count_basis": "real -- Service-department Employees with 'Technician' in Title (core/shop_control.py's _service_technicians()).",
            "total_revenue_all_time": round(total_revenue_all_time, 2),
            "total_revenue_basis": "real -- sum(Cost - PartsCost) across every ServiceRecord per technician, all time (core/service_reporting.py's get_technician_scorecard()).",
            "months_of_data": months_of_data,
            "months_of_data_basis": "real -- whole calendar months between the earliest and latest real ServiceRecord.ServiceDate in this dealership's data.",
            "avg_revenue_per_technician_all_time": avg_revenue_per_tech_all_time,
            "avg_monthly_revenue_per_technician": avg_monthly_revenue_per_tech,
        },
        "projection": {
            "capacity_increase_pct": capacity_increase_pct,
            "projected_monthly_labor_increase": projected_monthly_labor_increase,
            "formula": "capacity_increase_pct = additional_technicians / real current_technician_count * 100; projected_monthly_labor_increase = additional_technicians * (real total_revenue_all_time / real current_technician_count / real months_of_data).",
        },
    }


# ---------------------------------------------------------------------------
# Finance Portfolio
# ---------------------------------------------------------------------------

def finance_portfolio_scenario(role, portfolio_growth_pct):

    portfolio = get_portfolio_dashboard_api(role, limit=0)
    collections = get_collections_dashboard_api(role)
    accounting = get_loan_accounting_summary()

    if isinstance(portfolio, dict) and "error" in portfolio:
        return {
            "scenario_type": "finance_portfolio",
            "inputs": {"portfolio_growth_pct": portfolio_growth_pct},
            "error": portfolio["error"],
            "note": "Portfolio data is ADMIN/OPERATIONS/FINANCE-gated at its own layer (core/loan_servicing_api.py) -- not re-gated here, passed straight through.",
        }

    total_outstanding = portfolio.get("total_outstanding_balance") or 0.0
    total_loans = portfolio.get("total_loans") or 0
    buckets = portfolio.get("delinquency_buckets") or {}
    delinquent_count = sum(buckets.get(b, 0) for b in _DELINQUENT_BUCKETS)
    delinquency_rate_pct = round(delinquent_count / total_loans * 100, 2) if total_loans else None

    interest_income = accounting.get("interest_income_recognized") or 0.0
    observed_yield_pct = round(interest_income / total_outstanding * 100, 3) if total_outstanding else None

    growth_factor = (portfolio_growth_pct or 0.0) / 100

    projected_additional_outstanding = round(total_outstanding * growth_factor, 2)
    projected_additional_interest_income = round(interest_income * growth_factor, 2) if observed_yield_pct is not None else None
    projected_additional_loans = round(total_loans * growth_factor, 1)
    projected_additional_delinquent_loans = (
        round(projected_additional_loans * (delinquency_rate_pct / 100), 1)
        if delinquency_rate_pct is not None else None
    )

    return {
        "scenario_type": "finance_portfolio",
        "inputs": {
            "portfolio_growth_pct": portfolio_growth_pct,
        },
        "real_ratios_used": {
            "current_total_outstanding_balance": total_outstanding,
            "current_total_outstanding_basis": "real -- schedule-implied balance across active loans (core/loan_servicing.py's get_portfolio_dashboard()).",
            "current_total_loans": total_loans,
            "current_delinquency_rate_pct": delinquency_rate_pct,
            "current_delinquency_rate_basis": "aggregated from SIMULATED per-loan delinquency-bucket status -- see core/loan_servicing.py's own module docstring (no real payment ledger exists for every loan yet; loans with real recorded Payments already use real ledger-derived status).",
            "interest_income_recognized": interest_income,
            "interest_income_basis": "real -- cash-basis, computed entirely from actually-recorded, approved Payment records (core/loan_accounting.py's get_loan_accounting_summary()).",
            "observed_yield_pct": observed_yield_pct,
            "observed_yield_basis": "real -- interest income recognized as a % of the current real outstanding balance (not annualized).",
        },
        "collections_context": collections if not (isinstance(collections, dict) and "error" in collections) else {"error": collections.get("error")},
        "projection": {
            "projected_additional_outstanding_balance": projected_additional_outstanding,
            "projected_additional_interest_income": projected_additional_interest_income,
            "projected_additional_loans": projected_additional_loans,
            "projected_additional_delinquent_loans": projected_additional_delinquent_loans,
            "formula": "Every projected figure = real current value * (portfolio_growth_pct / 100) -- a proportional scaling of this dealership's own real observed ratios, not a new model.",
        },
    }
