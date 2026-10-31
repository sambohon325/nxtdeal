"""
core/business_health.py -- the first slice of Readiness' reframe from "Enterprise
Readiness" (data confidence -- is there enough historical ledger data to trust a
forecast) into "Enterprise Readiness & Intelligence" (is the DEALERSHIP ready to
achieve its goals -- an executive layer above Sales/Service/Inventory/Finance/
Marketing/Operations/Administration). Sam's own complaint about the pre-existing
Readiness module: data confidence is "a data-science concept, not useful to a
dealer principal/GM/CFO." Business Health is the first of Sam's proposed 10-item
structure (Overview, Business Health, Data Health, Performance Readiness, Forecasts,
Scenarios, Exceptions, Recommendations, Strategic Planning, Reporting) -- his own
words picking it first: "This would be new. Probably the most important area."

Sam's own target KPI set per department (Sales: Lead Volume/Show Rate/Close Rate/
Gross Profit/Pipeline Coverage; Service: RO Volume/Technician Utilization/Customer
Retention/Shop Capacity; Finance: Funding Time/Contract Accuracy/Collections/
Portfolio Quality; Marketing: Lead Volume/ROI/Website Traffic/Campaign Performance;
Inventory: Turn Rate/Aging/Recon Time/Days Supply) is used as the TARGET shape, not
a license to fabricate -- every single one of the ~19 KPIs below was checked against
an already-real, already-correct computation elsewhere in this ~110-prior-session
codebase before being written here. This module is a COMPOSITION layer, not a new
computation engine: it imports and re-shapes real functions from
core/sales_menu.py, core/service_menu.py, core/service_reporting.py,
core/finance_menu.py (+ core/collections_api.py/core/loan_servicing_api.py),
core/marketing_menu.py (+ core/marketing_attribution_api.py, core/websites.py),
core/inventory_overview.py, and core/operations_menu.py rather than recomputing
anything a department module already gets right.

Honesty discipline carried through from every source module rather than flattened
away: a HEURISTIC proxy (Finance's Funding Time, off Deal.updated_at since Deal has
no distinct submitted-to-lender timestamp) stays labeled HEURISTIC here, a SIMULATED
figure (Inventory's Turn Rate/Aging/Days Supply, per session 110's "simulate a real
gap, label it" policy) stays labeled SIMULATED with its own basis/disclaimer intact,
and a genuine gap with NO backing data model anywhere (Contract Accuracy -- confirmed
absent via a full grep before writing this module, no contract-vs-terms validation
concept exists in this codebase) is reported as an honest not_yet_tracked note, never
a fabricated plausible-sounding number.

Reuses each source module's own ACL where one already exists (get_collections_
dashboard_api/get_portfolio_dashboard_api are ADMIN/OPERATIONS/FINANCE-gated at their
own layer, get_marketing_roi_dashboard_api is ADMIN/OPERATIONS/MARKETING-gated) --
Business Health's own top-level ACL (core/business_health_api.py) is deliberately
broad (every real role), so a caller without access to one specific sub-signal sees
that one field degrade to its own module's real error, exactly matching the
"compose already-gated functions, let them degrade gracefully" convention
core/readiness_menu.py/core/sales_overview.py/core/operations_overview.py already
established, rather than a second, redundant gate here.

No single blended "overall health score" is computed. Considered and deliberately
declined: normalizing dollars (Gross Profit), percentages (Show Rate/Utilization),
and day-counts (Funding Time/Turn Rate) onto one comparable 0-100 scale would need an
arbitrary weighting scheme with no real methodology behind it -- the same reasoning
core/network_menu.py's Gap Analysis and core/inventory_overview.py's own Readiness
Score docstring wrestle with explicitly (that one DOES blend, but only 5 genuinely
comparable 0-100%-shaped sub-scores with a stated 70/30 real/simulated weighting --
this module's 19 KPIs span far more incompatible units, so a fabricated blend here
would be a worse offender, not a smaller one). get_business_health_overview() instead
composes the 5 real department sections side by side, which is what an executive
actually scanning "where are the risks" needs -- a single number would hide, not
surface, exactly the department-level detail Sam's own framing asks for.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD, DEAL

from core.sales_menu import overview as sales_overview
from core.appointments import list_appointments as _list_appointments

from core.service_menu import overview as service_overview
from core.service_reporting import get_shop_capacity, get_customer_retention_reporting

from core.finance_menu import _submitted_deal_aging
from core.collections_api import get_collections_dashboard_api
from core.loan_servicing_api import get_portfolio_dashboard_api

from core.marketing_menu import _campaigns as _marketing_campaigns
from core.marketing_attribution_api import get_marketing_roi_dashboard_api
from core.websites import list_websites, get_website_analytics

from core.inventory_overview import (
    get_simulated_aging_summary,
    get_simulated_turn_rate,
    get_simulated_market_days_supply,
)
from core.operations_menu import _recon_reporting


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Sales Health
# ---------------------------------------------------------------------------

def sales_health(role):
    """Lead Volume, Show Rate, Close Rate, Gross Profit, Pipeline Coverage --
    reuses core/sales_menu.py's overview() for Close Rate (its real
    closing_ratio_avg, the same per-salesperson leaderboard average
    core/leaderboard_api.py computes) and Gross Profit (its real
    gross_profit_funded_deals, sum(Vehicle.Price - Vehicle.Cost) across funded
    Deals). Show Rate is computed fresh here (no aggregate department-wide show
    rate existed anywhere -- only a per-salesperson figure inside
    core/sales_menu.py's _salesperson_scorecards()) off the real Appointment
    entity (session 96). Pipeline Coverage's real half is the active pipeline
    count already computed in overview(); the traditional "pipeline value /
    quota" ratio is an honest gap -- no quota/sales-target concept exists
    anywhere in this codebase (confirmed via grep before writing this
    function)."""

    ov = sales_overview(role)

    lead_volume = len(_entities(LEAD))

    sales_appointments = _list_appointments(department="Sales")
    shown = [a for a in sales_appointments if a.attributes.get("status") in ("arrived", "completed")]
    show_rate = round(len(shown) / len(sales_appointments), 3) if sales_appointments else None

    return {
        "lead_volume": {"value": lead_volume, "basis": "real"},
        "show_rate": {
            "value": show_rate,
            "appointments_scheduled": len(sales_appointments),
            "appointments_shown": len(shown),
            "basis": "real",
        },
        "close_rate": {
            "value": ov.get("closing_ratio_avg"),
            "basis": "real",
            "note": "Average per-salesperson conversion rate (core/leaderboard_api.py).",
        },
        "gross_profit": {
            "value": ov.get("gross_profit_funded_deals"),
            "basis": "real",
            "note": "sum(Vehicle.Price - Vehicle.Cost) across funded Deals.",
        },
        "pipeline_coverage": {
            "active_pipeline_count": ov.get("active_opportunities"),
            "basis": "real",
            "not_yet_tracked": {
                "coverage_ratio": "No sales quota/target concept exists anywhere in this codebase to divide pipeline value against -- the active pipeline count above is the real signal available today.",
            },
        },
    }


# ---------------------------------------------------------------------------
# Service Health
# ---------------------------------------------------------------------------

def service_health(role):
    """RO Volume, Technician Utilization, Customer Retention, Shop Capacity --
    reuses core/service_menu.py's overview() for RO Volume,
    core/service_reporting.py's get_shop_capacity() for both Technician
    Utilization (its own real avg_utilization_pct_today, an ASSUMED
    8-hour/day capacity per technician, labeled HEURISTIC at the source) and
    Shop Capacity itself (reused as one dict, not recomputed twice), and
    core/service_reporting.py's get_customer_retention_reporting() for
    Customer Retention."""

    ov = service_overview(role)
    capacity = get_shop_capacity()
    retention = get_customer_retention_reporting()

    return {
        "ro_volume": {
            "total": ov.get("repair_orders_total"),
            "open": ov.get("repair_orders_open"),
            "by_status": ov.get("repair_orders_by_status"),
            "basis": "real",
        },
        "technician_utilization": {
            "avg_utilization_pct_today": capacity.get("avg_utilization_pct_today"),
            "overloaded_technician_count": capacity.get("overloaded_technician_count"),
            "technician_count": capacity.get("technician_count"),
            "basis": "heuristic",
            "note": "ASSUMED 8-hour/day capacity per technician -- no real time-clock/shift data exists to read a true capacity from (core/shop_control.py).",
        },
        "customer_retention": {
            "customers_with_service_history": retention.get("customers_with_service_history"),
            "avg_visits_per_year": retention.get("avg_visits_per_year"),
            "lost_customers": retention.get("lost_customers"),
            "basis": "real",
        },
        "shop_capacity": {
            **capacity,
            "basis": "real",
            "note": "open_ro_count/technician_count/unassigned_ro_count are real; avg_utilization_pct_today is HEURISTIC (see technician_utilization above).",
        },
    }


# ---------------------------------------------------------------------------
# Finance Health
# ---------------------------------------------------------------------------

def finance_health(role):
    """Funding Time, Contract Accuracy, Collections, Portfolio Quality.
    Funding Time is HEURISTIC (Deal has no distinct submitted-to-lender
    timestamp -- days-since-updated_at on a still-submitted deal is the real,
    if imperfect, proxy core/finance_menu.py's own overview() already uses).
    Contract Accuracy is an honest gap -- no contract-vs-terms validation
    concept exists anywhere in this codebase (confirmed via grep before
    writing this function). Collections and Portfolio Quality both reuse
    their own already-built ADMIN/OPERATIONS/FINANCE-gated _api wrappers
    (core/collections_api.py/core/loan_servicing_api.py) rather than a
    second computation or a second ACL layer -- a caller outside that role
    set sees that field's own real "you don't have access" error, same
    degrade-gracefully convention every other composed dashboard in this
    codebase already follows."""

    submitted = [d for d in _entities(DEAL) if d.attributes.get("financing_status") == "submitted"]
    aging_days = _submitted_deal_aging(submitted)
    funding_time_avg = round(sum(aging_days) / len(aging_days), 1) if aging_days else None

    collections = get_collections_dashboard_api(role)
    portfolio = get_portfolio_dashboard_api(role, limit=0)

    return {
        "funding_time": {
            "avg_days_in_transit": funding_time_avg,
            "contracts_in_transit": len(submitted),
            "basis": "heuristic",
            "note": "Deal has no distinct submitted-to-lender timestamp -- days since last update on a still-submitted deal is the real proxy this data model has (core/finance_menu.py's _submitted_deal_aging).",
        },
        "contract_accuracy": {
            "not_yet_tracked": {
                "contract_accuracy": "No contract-vs-terms validation concept exists anywhere in this codebase -- confirmed absent, not guessed.",
            },
        },
        "collections": collections,
        "portfolio_quality": portfolio,
    }


# ---------------------------------------------------------------------------
# Marketing Health
# ---------------------------------------------------------------------------

def marketing_health(role):
    """Lead Volume, ROI, Website Traffic, Campaign Performance. Lead Volume is
    the same real Lead population Sales' own lead_volume counts (Marketing
    generates the leads Sales works). ROI reuses core/marketing_attribution.py's
    real (session 113) channel/campaign/PURL revenue correlation, ADMIN/
    OPERATIONS/MARKETING-gated at its own _api layer -- honestly labeled
    "real_but_not_proven_causal" at the source (no Campaign<->Lead/Deal
    touchpoint relationship exists anywhere in this codebase, so this is real
    first-touch correlation, not proven multi-touch attribution) and carried
    through unchanged here, not oversold. Website Traffic sums
    core/websites.py's real WebsiteAnalyticsEvent-backed get_website_analytics()
    across every real Website this dealer has -- genuinely real page-view/
    bot-vs-human data, honestly scoped (per that module's own note) to
    internal/preview traffic only, since this sandbox has no live public
    domain serving real customer traffic. Campaign Performance reuses
    core/marketing_menu.py's own _campaigns() composition."""

    lead_volume = len(_entities(LEAD))

    roi = get_marketing_roi_dashboard_api(role)

    sites = list_websites()
    total_views = 0
    human_views = 0
    bot_views = 0
    sites_with_traffic = 0
    for site in sites:
        analytics = get_website_analytics(site.id)
        if isinstance(analytics, dict) and "total_views" in analytics:
            if analytics["total_views"]:
                sites_with_traffic += 1
            total_views += analytics["total_views"]
            bot = analytics.get("bot_traffic") or {}
            human_views += bot.get("human_views", 0)
            bot_views += bot.get("bot_views", 0)

    website_traffic = {
        "total_page_views": total_views,
        "human_views": human_views,
        "bot_views": bot_views,
        "site_count": len(sites),
        "sites_with_recorded_traffic": sites_with_traffic,
        "basis": "real",
        "note": "Real WebsiteAnalyticsEvent counts (core/websites.py) -- this sandbox has no live public domain serving real customer traffic, so volume reflects internal/preview/personal-site traffic only, not real public site visitors.",
    }

    campaign_performance = _marketing_campaigns(role)

    return {
        "lead_volume": {"value": lead_volume, "basis": "real", "note": "Same real Lead population Sales Health's lead_volume counts."},
        "roi": roi,
        "website_traffic": website_traffic,
        "campaign_performance": campaign_performance,
    }


# ---------------------------------------------------------------------------
# Inventory Health
# ---------------------------------------------------------------------------

def inventory_health(role):
    """Turn Rate, Aging, Recon Time, Days Supply. Turn Rate/Aging/Days Supply
    all reuse core/inventory_overview.py's real (session 110, session-110
    "simulate a real gap, label it" policy) SIMULATED figures verbatim --
    every unsold vehicle's own deterministic simulated listing age, since
    Vehicle has no real acquisition-date field anywhere in this codebase
    (confirmed absent by sessions 63/85/106/109 independently). Recon Time
    reuses core/operations_menu.py's own real _recon_reporting() -- a real
    checklist-completion-rate signal, honestly NOT a true cycle-time-per-item
    duration, since no per-item recon start timestamp exists in this data
    model (said explicitly at the source, carried through here unchanged)."""

    aging = get_simulated_aging_summary()
    turn_rate = get_simulated_turn_rate(avg_days_in_stock=aging.get("average_days_in_stock"))
    days_supply = get_simulated_market_days_supply()
    recon = _recon_reporting()

    return {
        "turn_rate": turn_rate,
        "aging": aging,
        "recon_time": {
            "avg_checklist_completion_pct": recon.get("avg_checklist_completion_pct"),
            "vehicles_fully_recon_complete": recon.get("vehicles_fully_recon_complete"),
            "vehicles_with_zero_recon_progress": recon.get("vehicles_with_zero_recon_progress"),
            "used_unsold_count": recon.get("used_unsold_count"),
            "basis": "real",
            "note": recon.get("note"),
        },
        "days_supply": days_supply,
    }


# ---------------------------------------------------------------------------
# Overview -- composes all 5, no fabricated blended score (see module docstring)
# ---------------------------------------------------------------------------

def get_business_health_overview(role):

    return {
        "sales": sales_health(role),
        "service": service_health(role),
        "finance": finance_health(role),
        "marketing": marketing_health(role),
        "inventory": inventory_health(role),
        "overall_score": None,
        "overall_score_note": (
            "No single blended health score is computed -- these 19 KPIs span "
            "incompatible units (dollars, percentages, day-counts) with no real "
            "methodology to weight them into one number. See each department "
            "section below for real/heuristic/simulated-labeled detail instead."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
