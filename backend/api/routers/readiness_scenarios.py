"""Scenarios (What-If Modeling) router -- Readiness' "Simulations" Top Menu
item, REBUILT (core/readiness_scenarios.py / _api.py) from an honest
placeholder into Sam's own real ask: a transparent, formula-based what-if
engine over this dealership's own real current-data ratios (real close
rate, real avg gross per sale, real per-technician revenue, real observed
portfolio yield/delinquency rate) -- never an invented multiplier.
Deliberately open to every real role (ADMIN, OPERATIONS, SALES, MARKETING,
SERVICE, FINANCE), same "everyone can see tomorrow, a week, a month, a
quarter" precedent as every other module in this Readiness reframe -- the
one scenario touching genuinely sensitive data (Finance Portfolio) stays
gated at its OWN, narrower layer (core/loan_servicing_api.py/
core/collections_api.py) and degrades gracefully, not re-gated here.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/readiness-scenarios/catalog" registered
before nothing dynamic exists in this block (every scenario is its own fixed
POST path, no path-param routes here).
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.readiness_scenarios_api import (
    get_scenario_catalog_api,
    run_marketing_lead_volume_scenario_api,
    run_inventory_pricing_scenario_api,
    run_staffing_scenario_api,
    run_finance_portfolio_scenario_api,
)


router = APIRouter()


class MarketingLeadVolumeScenarioRequest(BaseModel):

    additional_leads: float | None = None
    additional_ad_spend: float | None = None
    assumed_cost_per_lead: float | None = None


class InventoryPricingScenarioRequest(BaseModel):

    price_reduction_amount: float
    price_band: str | None = None


class StaffingScenarioRequest(BaseModel):

    additional_technicians: int


class FinancePortfolioScenarioRequest(BaseModel):

    portfolio_growth_pct: float


@router.get("/readiness-scenarios/catalog")
def readiness_scenarios_catalog_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_scenario_catalog_api(payload["role"])


@router.post("/readiness-scenarios/marketing-lead-volume")
def readiness_scenarios_marketing_lead_volume_route(request: MarketingLeadVolumeScenarioRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_marketing_lead_volume_scenario_api(
        payload["role"],
        additional_leads=request.additional_leads,
        additional_ad_spend=request.additional_ad_spend,
        assumed_cost_per_lead=request.assumed_cost_per_lead,
    )


@router.post("/readiness-scenarios/inventory-pricing")
def readiness_scenarios_inventory_pricing_route(request: InventoryPricingScenarioRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_inventory_pricing_scenario_api(
        payload["role"],
        request.price_reduction_amount,
        price_band=request.price_band,
    )


@router.post("/readiness-scenarios/staffing")
def readiness_scenarios_staffing_route(request: StaffingScenarioRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_staffing_scenario_api(payload["role"], request.additional_technicians)


@router.post("/readiness-scenarios/finance-portfolio")
def readiness_scenarios_finance_portfolio_route(request: FinancePortfolioScenarioRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_finance_portfolio_scenario_api(payload["role"], request.portfolio_growth_pct)
