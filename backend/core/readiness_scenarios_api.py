"""
ACL layer for Readiness' "Scenarios" item (core/readiness_scenarios.py).
Viewing/running a scenario is deliberately broad -- every real role (ADMIN,
OPERATIONS, SALES, MARKETING, SERVICE, FINANCE) -- matching the same
"everyone can see tomorrow, a week, a month, a quarter" precedent every other
module in this Readiness reframe already established: this is a planning tool
over already-real, non-sensitive-in-aggregate data, not a raw record dump.
The one scenario that touches genuinely sensitive data (Finance Portfolio)
stays gated at its OWN, narrower layer (core/loan_servicing_api.py/
core/collections_api.py, both ADMIN/OPERATIONS/FINANCE) and degrades
gracefully for any other role -- not re-gated a second time here.
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.readiness_scenarios import (
    get_scenario_catalog,
    marketing_lead_volume_scenario,
    inventory_pricing_scenario,
    staffing_scenario,
    finance_portfolio_scenario,
)

_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _denied():
    return {"error": "You don't have access to Readiness Scenarios."}


def get_scenario_catalog_api(role):
    if role not in _ALL_ROLES:
        return _denied()
    return get_scenario_catalog()


def run_marketing_lead_volume_scenario_api(role, additional_leads=None, additional_ad_spend=None, assumed_cost_per_lead=None):
    if role not in _ALL_ROLES:
        return _denied()
    return marketing_lead_volume_scenario(
        role,
        additional_leads=additional_leads,
        additional_ad_spend=additional_ad_spend,
        assumed_cost_per_lead=assumed_cost_per_lead,
    )


def run_inventory_pricing_scenario_api(role, price_reduction_amount, price_band=None):
    if role not in _ALL_ROLES:
        return _denied()
    return inventory_pricing_scenario(role, price_reduction_amount, price_band=price_band)


def run_staffing_scenario_api(role, additional_technicians):
    if role not in _ALL_ROLES:
        return _denied()
    return staffing_scenario(role, additional_technicians)


def run_finance_portfolio_scenario_api(role, portfolio_growth_pct):
    if role not in _ALL_ROLES:
        return _denied()
    return finance_portfolio_scenario(role, portfolio_growth_pct)
