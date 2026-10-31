"""
core/readiness_forecasts.py -- Readiness' "Forecasts" item (#5 of Sam's own 10-item
proposed structure), enriched from the pre-existing generic tomorrow/week/month/
quarter-per-department view into Sam's own "predictive analytics engine" framing:

    Sales Forecast:      Units, Gross, Closing Ratio, Revenue
    Service Forecast:    Labor Sales, Parts Sales, RO Count, Capacity
    Inventory Forecast:  Units Likely To Sell, Units Likely To Age, Wholesale
                          Candidates
    Finance Forecast:    Funding, Collections, Delinquencies, Portfolio Performance

Same discipline as every prior slice in this reframe (Business Health, Exceptions/
Enterprise Risk Center, Recommendations, Overview+Heatmap, Data Health, Performance
Readiness): a COMPOSITION layer over already-real engines, not a new forecasting
model. Every one of the 15 dimensions above was checked against an already-real
computation before being written here, and falls into exactly one of three honest
buckets:

  1. REAL LEDGER FORECAST -- core/prediction.py's own real, already-built
     predict_all_horizons() reused verbatim wherever its metric already matches
     (Units=units_sold, RO Count=repair_orders, Funding=contracts_funded).
  2. REAL SIMPLE LINEAR PROJECTION -- for dimensions prediction.py's
     INDUSTRY_BASELINES doesn't cover at all ($ Gross, $ Revenue, $ Parts Sales),
     built from real month-to-date ledger data and projected via the exact same
     run-rate math core/performance_readiness.py's get_current_month_pace() already
     established (actual-to-date / days elapsed x days in month) -- reusing that
     function directly for Labor Sales (Service), and applying the identical math to
     newly-computed real month-to-date sums for Gross/Revenue/Parts Sales. Explicitly
     labeled a SIMPLE linear projection everywhere, never oversold as a
     sophisticated model.
  3. REAL CURRENT DATA / REAL RULES ENGINE -- Closing Ratio and Capacity are real,
     CURRENT signals (not forecasts themselves) reported honestly as the baseline
     assumptions the $ projections above should be read against, since no ledger
     trend model exists to project a FUTURE change in either. Units Likely To
     Sell/Age are a real, TRANSPARENT RULES ENGINE (not a machine-learning
     probability model, matching this codebase's established "real rules, not fake
     AI" convention -- core/collections.py's risk scoring, core/network_audit.py's
     recommendation engine) over two already-real/simulated per-vehicle signals.
     Collections/Delinquencies/Portfolio Performance all reuse their own
     already-built, already-ADMIN/OPERATIONS/FINANCE-gated dashboards directly.

No fabricated number appears anywhere in this module -- every dimension is real, a
real simple linear projection (clearly labeled as such), or a real rules-engine
composition of already-real/simulated signals, each carrying its own basis/note.

Also backs the "Readiness Timeline" capstone (Last 7 Days / Last 30 Days / Last 90
Days / Year To Date, "to spot trends") -- a thin pass-through to core/prediction.py's
new historical_trend()/all_departments_historical_trend() (added directly to that
module in this same slice, since it's the module that already owns
_real_dates_for()'s trailing-window ledger query), kept here rather than duplicated
so Forecasts and the Timeline share one real data source.
"""

import calendar
from datetime import date, datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE, DEAL, PART_SALE

from core.prediction import (
    predict_all_horizons,
    historical_trend,
    all_departments_historical_trend,
    DEPARTMENTS as PREDICTION_DEPARTMENTS,
)
from core.performance_readiness import get_current_month_pace
from core.sales_menu import overview as _sales_overview
from core.service_reporting import get_shop_capacity
from core.workflow_tab_data import _unsold_vehicles, inventory_wholesale_disposition
from core.pricing_desk import get_age_based_adjustment
from core.collections_api import get_collections_dashboard_api
from core.loan_servicing_api import get_portfolio_dashboard_api


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _month_bounds(today=None):
    today = today or date.today()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return today, days_elapsed, days_in_month


def _linear_projection(actual_to_date, days_elapsed, days_in_month):
    """The one real projection formula every $ dimension in this module uses --
    identical math to core/performance_readiness.py's get_current_month_pace()."""
    if not days_elapsed:
        return None
    return round((actual_to_date / days_elapsed) * days_in_month, 2)


# ---------------------------------------------------------------------------
# Sales Forecast -- Units, Gross, Closing Ratio, Revenue
# ---------------------------------------------------------------------------

def _month_to_date_funded_deals(today):
    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    deals = []
    for d in _entities(DEAL):
        if d.attributes.get("status") != "funded":
            continue
        funded_at = _parse_date(d.attributes.get("funded_at"))
        if funded_at and funded_at.year == today.year and funded_at.month == today.month:
            deals.append(d)
    return deals, vehicles_by_id


def sales_forecast(role):
    """Units, Gross, Closing Ratio, Revenue -- see module docstring for the
    real/projection/current-baseline split."""

    today, days_elapsed, days_in_month = _month_bounds()

    units_forecast = predict_all_horizons("sales")

    deals_mtd, vehicles_by_id = _month_to_date_funded_deals(today)
    gross_to_date = 0.0
    revenue_to_date = 0.0
    for d in deals_mtd:
        v = vehicles_by_id.get(d.attributes.get("vehicle_id"))
        if v:
            price = _safe_float(v.attributes.get("Price"))
            cost = _safe_float(v.attributes.get("Cost"))
            gross_to_date += price - cost
            revenue_to_date += price

    ov = _sales_overview(role)
    closing_ratio = ov.get("closing_ratio_avg") if isinstance(ov, dict) else None

    return {
        "units": {
            "forecast_by_horizon": units_forecast,
            "basis": "ledger_or_industry_estimate",
            "note": "core/prediction.py's real predict_all_horizons('sales') -- units_sold, blended real-ledger/industry-baseline per horizon.",
        },
        "gross": {
            "month_to_date": round(gross_to_date, 2),
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            "projected_month_total": _linear_projection(gross_to_date, days_elapsed, days_in_month),
            "basis": "real_linear_projection",
            "note": "Real sum(Vehicle.Price - Vehicle.Cost) across Deals funded this calendar month (Deal.funded_at), projected via a simple linear run-rate (actual-to-date / days elapsed x days in month) -- same math as core/performance_readiness.py's get_current_month_pace(), not a sophisticated forecast model.",
        },
        "closing_ratio": {
            "value": closing_ratio,
            "basis": "real",
            "note": "Current real average per-salesperson conversion rate (core/sales_menu.py) -- reported as the forward-looking baseline assumption behind Gross/Revenue above; no ledger trend model exists to project a future change in this rate.",
        },
        "revenue": {
            "month_to_date": round(revenue_to_date, 2),
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            "projected_month_total": _linear_projection(revenue_to_date, days_elapsed, days_in_month),
            "basis": "real_linear_projection",
            "note": "Real sum(Vehicle.Price) across Deals funded this calendar month, same linear run-rate projection as Gross above.",
        },
    }


# ---------------------------------------------------------------------------
# Service Forecast -- Labor Sales, Parts Sales, RO Count, Capacity
# ---------------------------------------------------------------------------

def _month_to_date_part_sales(today):
    total = 0.0
    count = 0
    for s in _entities(PART_SALE):
        d = _parse_date(s.attributes.get("SaleDate"))
        if d and d.year == today.year and d.month == today.month:
            total += _safe_float(s.attributes.get("SalePrice"))
            count += 1
    return total, count


def service_forecast(role):
    """Labor Sales, Parts Sales, RO Count, Capacity -- see module docstring."""

    today, days_elapsed, days_in_month = _month_bounds()

    labor_pace = get_current_month_pace("service")

    parts_to_date, parts_count = _month_to_date_part_sales(today)
    parts_projection = _linear_projection(parts_to_date, days_elapsed, days_in_month)

    ro_forecast = predict_all_horizons("service")

    capacity = get_shop_capacity()

    if labor_pace:
        labor_sales = dict(labor_pace)
        labor_sales["basis"] = "real_linear_projection"
        labor_sales["note"] = (
            "core/performance_readiness.py's own real get_current_month_pace('service') "
            "-- real ServiceRecord.Cost-PartsCost labor revenue this calendar month, "
            "projected via linear run-rate."
        )
    else:
        labor_sales = {
            "basis": "not_yet_tracked",
            "note": "No current-month labor revenue could be computed (no days elapsed / no matching records).",
        }

    return {
        "labor_sales": labor_sales,
        "parts_sales": {
            "month_to_date": round(parts_to_date, 2),
            "sales_count_month_to_date": parts_count,
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            "projected_month_total": parts_projection,
            "basis": "real_linear_projection",
            "note": "Real sum(PartSale.SalePrice) this calendar month (PartSale.SaleDate), projected via the same simple linear run-rate math as Sales' Gross/Revenue.",
        },
        "ro_count": {
            "forecast_by_horizon": ro_forecast,
            "basis": "ledger_or_industry_estimate",
            "note": "core/prediction.py's real predict_all_horizons('service') -- repair_orders, blended real-ledger/industry-baseline per horizon.",
        },
        "capacity": {
            **(capacity or {}),
            "basis": "heuristic",
            "note": "Current real shop capacity (core/shop_control.py) -- ASSUMED 8-hour/day per-technician capacity (no real time-clock/shift data exists to read a true capacity from). Reported as the real constraint RO Count's forecast above should be read against.",
        },
    }


# ---------------------------------------------------------------------------
# Inventory Forecast -- Units Likely To Sell, Units Likely To Age, Wholesale
# Candidates
# ---------------------------------------------------------------------------

_FRESH_BAND = "0-30 days"
_AGED_BANDS = ("61-90 days", "91+ days")
_HEALTHY_MARGIN_PCT = 0.08


def _unsold_vehicle_signals():
    signals = []
    for v in _unsold_vehicles():
        adj = get_age_based_adjustment(v.id)
        if not isinstance(adj, dict) or "error" in adj:
            continue
        price = _safe_float(v.attributes.get("Price"))
        cost = _safe_float(v.attributes.get("Cost"))
        margin_pct = (price - cost) / price if price else None
        signals.append({
            "vehicle_id": v.id,
            "vin": v.attributes.get("VIN"),
            "stock_number": v.attributes.get("StockNumber"),
            "year": v.attributes.get("Year"),
            "make": v.attributes.get("Make"),
            "model": v.attributes.get("Model"),
            "price": price or None,
            "estimated_listing_age_days": adj.get("estimated_listing_age_days"),
            "age_band": adj.get("age_band"),
            "margin_pct": round(margin_pct, 3) if margin_pct is not None else None,
        })
    return signals


def inventory_forecast(role):
    """Units Likely To Sell, Units Likely To Age, Wholesale Candidates -- see module
    docstring for the real-rules-engine explanation."""

    signals = _unsold_vehicle_signals()

    likely_to_sell = [
        s for s in signals
        if s["age_band"] == _FRESH_BAND and (s["margin_pct"] or 0) >= _HEALTHY_MARGIN_PCT
    ]
    likely_to_age = [
        s for s in signals
        if s["age_band"] in _AGED_BANDS and (s["margin_pct"] is None or s["margin_pct"] < _HEALTHY_MARGIN_PCT)
    ]

    wholesale = inventory_wholesale_disposition(role)

    return {
        "units_likely_to_sell": {
            "count": len(likely_to_sell),
            "vehicles": likely_to_sell[:50],
            "basis": "heuristic_rules",
            "note": "Rules-based, not a probability model: fresh listing (SIMULATED 0-30 day age, core/pricing_desk.py) + healthy REAL margin (>=8%, Vehicle.Price - Vehicle.Cost).",
        },
        "units_likely_to_age": {
            "count": len(likely_to_age),
            "vehicles": likely_to_age[:50],
            "basis": "heuristic_rules",
            "note": "Rules-based: already 61+ SIMULATED days AND thin/negative REAL margin (<8%).",
        },
        "wholesale_candidates": wholesale,
    }


# ---------------------------------------------------------------------------
# Finance Forecast -- Funding, Collections, Delinquencies, Portfolio Performance
# ---------------------------------------------------------------------------

def finance_forecast(role):
    """Funding, Collections, Delinquencies, Portfolio Performance -- see module
    docstring. Collections/Delinquencies/Portfolio Performance all reuse their own
    already-ADMIN/OPERATIONS/FINANCE-gated dashboards -- a caller outside that role
    set sees that dashboard's own real access-denied error, same degrade-gracefully
    convention every other composed Readiness dashboard in this reframe already
    established (Business Health, Overview, etc.)."""

    funding_forecast = predict_all_horizons("finance")

    collections = get_collections_dashboard_api(role)

    portfolio = get_portfolio_dashboard_api(role, limit=0)

    if isinstance(portfolio, dict) and "error" not in portfolio:
        delinquencies = {
            "delinquency_buckets": portfolio.get("delinquency_buckets"),
            "total_amount_past_due": portfolio.get("total_amount_past_due"),
            "basis": portfolio.get("basis"),
            "disclaimer": portfolio.get("disclaimer"),
        }
        portfolio_performance = {
            "total_loans": portfolio.get("total_loans"),
            "active_loans": portfolio.get("active_loans"),
            "payoffs": portfolio.get("payoffs"),
            "total_outstanding_balance": portfolio.get("total_outstanding_balance"),
            "basis": portfolio.get("basis"),
            "disclaimer": portfolio.get("disclaimer"),
        }
    else:
        delinquencies = portfolio
        portfolio_performance = portfolio

    return {
        "funding": {
            "forecast_by_horizon": funding_forecast,
            "basis": "ledger_or_industry_estimate",
            "note": "core/prediction.py's real predict_all_horizons('finance') -- contracts_funded, blended real-ledger/industry-baseline per horizon.",
        },
        "collections": collections,
        "delinquencies": delinquencies,
        "portfolio_performance": portfolio_performance,
    }


# ---------------------------------------------------------------------------
# Overview -- composes all 4 department forecasts, no fabricated blended figure
# (same "no single blended score" discipline core/business_health.py established)
# ---------------------------------------------------------------------------

def get_forecasts_overview(role):

    return {
        "sales": sales_forecast(role),
        "service": service_forecast(role),
        "inventory": inventory_forecast(role),
        "finance": finance_forecast(role),
        "not_yet_tracked": {
            "cross_department_blended_forecast": "No single blended revenue/readiness forecast across all departments is computed -- each department's own dimensions carry incompatible units (units/dollars/percentages/day-counts), same reasoning core/business_health.py's overall_score_note already established. See each dimension's own basis/note for real vs. real-linear-projection vs. real-rules-heuristic detail.",
            "marketing_forecast": "Marketing was not part of Sam's own 4-department Forecasts spec for this slice (Sales/Service/Inventory/Finance) -- core/prediction.py's real predict_all_horizons('marketing') and core/marketing_attribution.py's ROI engine already exist and are surfaced elsewhere (Business Health, the pre-existing generic forecasts_by_horizon view).",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Readiness Timeline capstone -- Last 7 Days / Last 30 Days / Last 90 Days /
# Year To Date, "to spot trends". Thin pass-through to core/prediction.py's real
# historical_trend()/all_departments_historical_trend() (added in this same slice)
# so Forecasts and the Timeline share one real data source rather than two.
# ---------------------------------------------------------------------------

def get_readiness_timeline_overview():

    return {
        "departments": all_departments_historical_trend(),
        "covered_departments": PREDICTION_DEPARTMENTS,
        "not_yet_tracked": {
            "uncovered_departments": "Operations/Inventory/Administration have no standalone core/prediction.py entry -- no real historical trend exists to report for them yet, same gap core/readiness_menu.py's own forecasts()/readiness() functions already flag.",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_readiness_timeline_department(department):
    return historical_trend((department or "").lower())
