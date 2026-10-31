"""
core/readiness_menu.py -- real data behind Readiness & Predictive Intelligence's
8-item Top Menu (core/menu_catalog.py), session 66. readiness.pdf's own framing:
unlike every other department, Readiness doesn't manage work -- it measures whether
the dealership is CAPABLE of executing the work tomorrow, next week, next month, next
quarter. "Mission Control / Digital Twin / AI Operations Center / Predictive
Intelligence Dashboard," not a DMS screen. Its Menu Bar (Overview | Data Health |
Readiness | Forecasts | Simulations | Exceptions | Recommendations | Reporting) maps
onto: Are we ready? Is our data trustworthy? Department-by-department, how ready?
What's coming? What if...? What's broken? What should we do about it? How did we do?

Same discipline as every prior *_menu.py: reuse an already-built function wherever
it's a genuine match, compute a small new real aggregate where the graph has the data
but nobody queried it this way yet, and use an honest `not_yet_tracked` note (never a
fabricated number) wherever readiness.pdf asks for something this data model doesn't
back at all. This department leans harder on already-built engines than any prior one
-- core/prediction.py (session 37, the real ledger-vs-industry-baseline confidence
engine) and core/network_audit.py (session 38, the real rules-based recommendation
engine) both already exist purely because Readiness needed them; this module is
mostly the honest, department-framed front door onto work already done, not new
computation.

Confirmed structural gap up front, the most important one in this module:
readiness.pdf's Overview widget mocks a 7-department "Readiness Scorecard"
(Operations/Sales/Marketing/Inventory/Service/Finance/Administration, all with
illustrative %s). Real core/prediction.py DEPARTMENTS is exactly 5 keys -- sales/
service/finance/marketing/parts -- each backed by one specific dated entity type
(Vehicle.DateSold/ServiceRecord.ServiceDate/FinanceContract.ContractDate/
Lead.CreatedDate/PartSale.SaleDate). Operations, Inventory, and Administration have
NO standalone prediction/readiness entry anywhere in this codebase (confirmed absent,
same finding core/administration_menu.py's session 65 reporting() already made for
Administration specifically) -- every function below reports real scores for the 5
covered departments and says so explicitly for the 3 that aren't, rather than
inventing a 6th/7th/8th number to match the PDF's mock scorecard.

No Simulations/Digital-Twin/what-if-scenario engine exists anywhere in this codebase
(confirmed via a full grep for simulation/scenario/what_if) -- an honest, fully-scoped
placeholder, same treatment core/marketing_menu.py's session-62 events() gave Events.
No prediction-vs-actual variance/accuracy-history store exists either, so Forecast
Accuracy/Variance and Readiness Trends are also honest gaps -- this module reports a
live snapshot, not a trend line, because no trend has ever been persisted.
"""

from core.prediction import (
    DEPARTMENTS as PREDICTION_DEPARTMENTS,
    HORIZONS,
    predict,
    department_readiness,
    all_departments_readiness,
)
from core.data_connections_api import list_connections_api, readiness_predictions_api
from core.network_api import get_network_audit_api
from core.business_health_api import get_business_health_overview_api
from core.enterprise_risk_center_api import get_risk_center_overview_api
from core.readiness_recommendations_api import get_recommendations_overview_api
from core.readiness_overview_api import get_enterprise_readiness_overview_api
from core.data_health_api import (
    get_integration_monitoring_api,
    get_data_completeness_api,
    get_data_accuracy_api,
    get_data_freshness_api,
)
from core.performance_readiness_api import get_performance_readiness_overview_api
from core.readiness_forecasts_api import get_forecasts_overview_api
from core.readiness_scenarios_api import get_scenario_catalog_api
from core.strategic_planning_api import get_strategic_planning_overview_api
from core.general_ledger_api import get_income_statement_api, get_balance_sheet_api
from core.bank_reconciliation_api import get_reconciliation_status_api


# The 3 Top-Menu departments readiness.pdf's mock scorecard shows that core/
# prediction.py has no standalone entry for -- confirmed absent, not silently
# dropped.
_UNCOVERED_DEPARTMENTS = ["operations", "inventory", "administration"]

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Department
# Intelligence's real KPI engine (core/department_intelligence.py) only has 5 keys --
# sales/service/parts/fi/executive -- not one per menu department, so this is an honest
# gap for Readiness itself (which is about confidence in OTHER departments' data, not
# its own KPI dashboard) rather than a stretch mapping onto an unrelated key.
_DI_GAP_NOTE = {
    "available": False,
    "note": (
        "No 1:1 Department Intelligence key exists for Readiness -- the 5 real keys "
        "are sales/service/parts/fi/executive (see core/department_intelligence.py). "
        "Readiness measures confidence in other departments' data, not its own KPI set."
    ),
}


def _connections(role):
    """Unwraps list_connections_api's {"connections": [...]} shape into a plain list,
    or returns None if the caller's role was forbidden -- the exact bug class
    core/administration_menu.py's session-65 smoke test caught and fixed (that module
    iterated the raw dict directly, silently walking its one string key), applied here
    correctly from the start."""

    result = list_connections_api(role)

    if isinstance(result, dict) and "connections" in result:
        return result["connections"]

    return None


def _all_readiness():
    return [r for r in all_departments_readiness() if r]


def overview(role):
    """readiness.pdf's "Overview" item, REBUILT (2026-07-19, this same reframe
    session) from the old thin data-confidence stub into the real Enterprise
    Readiness Dashboard Sam described -- and, confirmed the same real feature
    before building it, ALSO the answer to his separately-named "Readiness
    Heatmap" capstone ("show every department % with drill-down capability").
    Composes core/readiness_overview.py's 3 real pieces, built ONCE (same
    discipline this whole reframe session already established for Exceptions/
    Enterprise Risk Center and Recommendations):

      1. A Department Readiness Heatmap -- core/prediction.py's real 5-
         department confidence scores (sales/service/finance/marketing/
         parts), color-coded, with Operations/Inventory/Administration
         reported as an explicit, honestly-labeled gap (no standalone
         core/prediction.py entry exists for any of the 3 -- confirmed
         absent, never relabeled onto one of the 5 real covered keys).
      2. Today's Risks -- core/enterprise_risk_center.py's real risk feed
         reused verbatim, plus a small real top-N ranking.
      3. An Executive Summary -- a real, rules-based templated narrative
         (never a fabricated LLM-generated fact) composing (1) + (2) +
         core/readiness_recommendations.py's real executive recommendations,
         with an OPTIONAL isolated-OpenAI phrasing polish
         (core/readiness_summary_wizard.py) that can never add a fact not
         already in the real template.

    See core/readiness_overview.py's own module docstring for the full
    reasoning."""

    return get_enterprise_readiness_overview_api(role)


def business_health(role):
    """readiness.pdf reframe (Sam: "is the dealership ready to achieve its goals,
    where are the risks" -- an executive layer above every production department,
    not a data-confidence screen). Real KPIs pulled from each department's own
    already-real modules (core/business_health.py) -- Lead Volume/Show Rate/Close
    Rate/Gross Profit/Pipeline Coverage (Sales), RO Volume/Technician Utilization/
    Customer Retention/Shop Capacity (Service), Funding Time/Contract Accuracy/
    Collections/Portfolio Quality (Finance), Lead Volume/ROI/Website Traffic/
    Campaign Performance (Marketing), Turn Rate/Aging/Recon Time/Days Supply
    (Inventory). Every figure carries its own real/heuristic/simulated basis label
    rather than being flattened into one number -- see core/business_health.py's
    module docstring for the full reasoning, including why no single blended
    "overall health score" is computed."""

    return get_business_health_overview_api(role)


def data_health(role):
    """readiness.pdf's "Data Health" item: the foundation layer -- "this is where
    trust in the AI begins." GREATLY EXPANDED (2026-07-19, this same reframe
    session -- Sam: "This is what the current screen appears focused on. I'd keep
    it but greatly expand it."). Connected Systems/API Status/Sync Health/Data
    Integrity reuse the real Connection records (core/data_connections.py, session
    37) -- status/last_synced_at/error_message are genuine fields, not fabricated.
    Historical Coverage reuses core/prediction.py's own real completeness/volume/
    recency factors per department (the exact signal readiness.pdf's "96% Complete"
    example describes) rather than inventing a second coverage metric. Missing Data
    is explicit about the 3 departments core/prediction.py doesn't cover at all.

    Four new sections (core/data_health.py) close Sam's expansion ask: Integration
    Monitoring (the same Connection records, regrouped -- with an honest note on
    the gap between Sam's 5 named categories and this codebase's real
    department/connection_type fields), Data Completeness (a genuinely new real
    field-presence scan -- Missing VIN/Customer/RO/Contract Data), Data Accuracy
    (real duplicate-customer/duplicate-vehicle detection built fresh this slice,
    core/workflow_tab_data.py's inventory_lot_audit() reused verbatim for
    Inventory Mismatches, and an honest, EXPLAINED gap for Pricing Discrepancies
    -- confirmed via imports/generate_seed_data.py that FinanceContract.SalePrice
    is deliberately Vehicle.Price +/- random negotiated variance, not a data-entry
    error, so no fabricated discrepancy count is computed), and Data Freshness
    (real per-connection Last Sync, a new real Records-Updated-in-24h scan across
    every entity type this codebase actually stamps with a real timestamp, and
    Pending Changes reusing the same real cross-department approval queue
    core/administration_menu.py's _approval_queue() already established). See
    core/data_health.py's own module docstring for the full reasoning."""

    connections = _connections(role)

    if connections is None:
        return list_connections_api(role)

    by_status = {}
    for c in connections:
        status = c.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    connected_systems = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "connection_type": c.get("connection_type"),
            "department": c.get("department"),
            "status": c.get("status"),
            "last_synced_at": c.get("last_synced_at"),
            "last_test_at": c.get("last_test_at"),
            "error_message": c.get("error_message"),
        }
        for c in connections
    ]

    historical_coverage = {}
    for department in PREDICTION_DEPARTMENTS:
        p = predict(department, "quarter")
        if p:
            historical_coverage[department] = {
                "completeness_pct": round(p["factors"]["completeness"] * 100, 1),
                "sample_size": p["sample_size"],
                "basis": p["basis"],
            }

    return {
        "connected_systems": {"count": len(connections), "systems": connected_systems},
        "api_status": by_status,
        "sync_health": {
            "error_count": by_status.get("error", 0),
            "connected_count": by_status.get("connected", 0),
            "pending_count": by_status.get("pending", 0),
        },
        "data_integrity": {
            "connections_with_errors": [c for c in connected_systems if c["status"] == "error"],
        },
        "historical_coverage": historical_coverage,
        "integration_monitoring": get_integration_monitoring_api(role),
        "data_completeness": get_data_completeness_api(role),
        "data_accuracy": get_data_accuracy_api(role),
        "data_freshness": get_data_freshness_api(role),
        "not_yet_tracked": {
            "missing_data": f"core/prediction.py has no standalone entry for {', '.join(_UNCOVERED_DEPARTMENTS)} -- no dated-entity source is wired for those departments' confidence scoring yet.",
        },
    }


def readiness(role):
    """readiness.pdf's "Readiness" item, RENAMED + EXPANDED (2026-07-19, this same
    reframe session) into "Performance Readiness" -- item #4 of Sam's own 10-item
    proposed structure. Sam's own words: "This is where scores become useful." Goal
    Tracking against real pace (e.g. Monthly Sales Goal 120 Units vs. Current Pace
    134 Units, Readiness 112%; Service Goal $250,000 Labor vs. Projected $262,000,
    Readiness 105%; Marketing Goal 900 Leads vs. Forecast 1,120 Leads, Readiness
    124%).

    Deliberate scope decision, made explicitly rather than by accident: this
    feature needs a real GOAL to compare pace against, and no goal/quota/target-
    setting mechanism existed anywhere in this codebase before this slice (core/
    business_health.py's own Pipeline Coverage note had already flagged this exact
    gap: "No sales quota/target concept exists anywhere"). Chose to BUILD a real
    goal-setting mechanism now rather than leave the whole feature gapped -- a
    simple, real, ADMIN/OPERATIONS-editable flat monthly numeric target per
    department (core/system_config.py's new department_goals dict,
    GOAL_TRACKED_DEPARTMENTS = sales/service/marketing, matching Sam's own 3
    worked examples exactly). This is a genuine, small, working stopgap --
    deliberately narrow enough that it won't collide with the separately-scoped,
    richer "Strategic Planning" item (objectives/initiatives/budgets, Sam's #9),
    which may supersede or extend it later, not compete with it now. See core/
    performance_readiness.py's own module docstring for the full reasoning,
    including why Service's ledger_forecast is honestly omitted (a real unit
    mismatch -- core/prediction.py's Service metric is repair_orders, a count,
    not $ labor revenue) rather than shown as a mismatched cross-check.

    The pre-existing confidence-score content (current/target confidence %,
    variance, risk factors against the 90% go-live threshold, computed by core/
    prediction.py's department_readiness()) is a genuinely DIFFERENT concept --
    data trustworthiness, not business performance vs. a goal -- and is kept here
    too, under `data_confidence_scores` (renamed from the old top-level
    `department_readiness` key so it isn't confused with the new `goal_tracking`
    section sitting alongside it). Only reports the 5 departments core/
    prediction.py actually covers for that half -- Operations/Inventory/
    Administration stay an explicit gap, never a fabricated score."""

    scores = []

    for department in PREDICTION_DEPARTMENTS:

        r = department_readiness(department)

        if not r:
            continue

        scores.append({
            "department": department,
            "current_score_pct": r["confidence_pct"],
            "target_score_pct": r["threshold"],
            "variance_pct": round(r["confidence_pct"] - r["threshold"], 1),
            "status": "At/Above Target" if r["ready"] else "Below Target",
            "risk_factors": [] if r["ready"] else [
                f"Confidence basis is '{r['basis']}' -- not enough real ledger history yet to clear the {r['threshold']}% go-live threshold."
            ],
        })

    return {
        "goal_tracking": get_performance_readiness_overview_api(role),
        "data_confidence_scores": scores,
        "not_yet_tracked": {
            "uncovered_departments": f"{', '.join(d.title() for d in _UNCOVERED_DEPARTMENTS)} have no standalone core/prediction.py entry -- no confidence score exists to report for them yet, rather than a fabricated one.",
            "finance_inventory_goals": "No Finance/Inventory goal metric is tracked yet -- see core/performance_readiness.py's own not_yet_tracked note.",
        },
    }


def forecasts(role):
    """readiness.pdf's "Forecasts" item, ENRICHED (2026-07-19, Readiness reframe)
    from a generic tomorrow/week/month/quarter-per-department view into Sam's own
    "predictive analytics engine" framing: real Sales (Units/Gross/Closing Ratio/
    Revenue), Service (Labor Sales/Parts Sales/RO Count/Capacity), Inventory (Units
    Likely To Sell/Age, Wholesale Candidates), and Finance (Funding/Collections/
    Delinquencies/Portfolio Performance) forecasts -- see core/readiness_forecasts.py's
    own module docstring for the full real/real-linear-projection/real-rules-engine
    breakdown per dimension. The prior generic horizon-first view is kept alongside,
    unchanged, as `forecasts_by_horizon` -- still a real, useful cross-department
    tomorrow/week/month/quarter comparison, just no longer the whole picture."""

    data = readiness_predictions_api()

    by_horizon = {horizon: [] for horizon in HORIZONS}

    for entry in data.get("departments", []):
        for p in entry.get("predictions", []):
            by_horizon.setdefault(p["horizon"], []).append({
                "department": p["department"],
                "metric": p["metric"],
                "predicted_value": p["predicted_value"],
                "unit": p["unit"],
                "confidence_pct": p["confidence_pct"],
                "basis": p["basis"],
            })

    department_forecasts = get_forecasts_overview_api(role)

    return {
        "forecasts_by_horizon": by_horizon,
        "department_forecasts": department_forecasts,
        "not_yet_tracked": {
            "marketing_forecast": "Marketing wasn't part of Sam's own 4-department Forecasts spec for this slice -- see department_forecasts.not_yet_tracked for the full note; the generic forecasts_by_horizon view above still covers Marketing's real units_sold-style leads_generated forecast.",
        },
    }


def simulations(role):
    """readiness.pdf's "Simulations" item: the Digital Twin -- "one of NXTDeal's
    strongest differentiators." REBUILT (2026-07-19, this same reframe session)
    from the old honest-placeholder stub into Sam's own real What-If Modeling ask
    -- a real, transparent, formula-based scenario engine (core/
    readiness_scenarios.py) covering Marketing/Lead Volume, Inventory Pricing,
    Staffing, and Finance Portfolio scenarios, each projecting off this
    dealership's OWN real current-data ratios (real close rate, real avg gross
    per sale, real per-technician revenue, real observed portfolio yield/
    delinquency rate) rather than an invented multiplier -- see
    core/readiness_scenarios.py's own module docstring for the full per-scenario
    real-basis trace. This menu view surfaces the real scenario catalog (the 4
    real scenario types + their real input fields) so a caller knows what's
    available; running an actual what-if projection with real numbers happens
    via the dedicated /readiness-scenarios/* POST routes (a scenario needs a
    caller-supplied input parameter, e.g. "how many additional leads" -- not
    something a GET-only menu view can compute)."""

    catalog = get_scenario_catalog_api(role)

    return {
        "scenario_catalog": catalog,
        "note": (
            "Run an actual what-if projection via POST /readiness-scenarios/"
            "{marketing-lead-volume|inventory-pricing|staffing|finance-portfolio} "
            "with the real input fields listed in scenario_catalog above -- every "
            "projection returns the real current-data ratios it used alongside "
            "the projected output, so the math is fully auditable."
        ),
    }


def exceptions(role):
    """readiness.pdf's "Exceptions" item: the operational anomaly center --
    "everything bad surfaces here." Enriched (2026-07-18, this same reframe session)
    from a thin data-sync/readiness-drop/compliance stub into the real, full
    Enterprise Risk Center Sam separately named as a capstone feature -- confirmed
    to be the same real feature before building (Sam himself said this item "could
    become an active risk center"), so core/enterprise_risk_center.py was built ONCE
    and is composed here, not duplicated. Covers Sam's full spec: Critical Issues
    (Vehicles Missing Titles, Contracts Missing Documents, Inventory Not Located,
    Data Sync Failures), Financial Exceptions (Unfunded Contracts, Funding Delays,
    Negative Gross Deals), and Operational Exceptions (Recon Delays, Service Delays,
    Open Compliance Issues) -- every exception type carries a real, computed
    Low/Medium/High/Critical severity (see core/enterprise_risk_center.py's own
    docstring for the transparent severity rules) and a `resolve` reference back to
    the real Top Menu item/department where the underlying action already lives.

    readiness_drops (any department below the go-live threshold, reused from
    department_readiness() directly) is kept alongside the new risk center output
    rather than folded into it -- it's a genuinely different kind of exception
    (data-confidence, not an operational/financial/critical issue) that predates
    this reframe and still belongs on this screen. Forecast Variances still has no
    backing data model -- no prediction-vs-actual history is ever persisted, so
    there's no stored prior forecast to compare against (unchanged honest gap)."""

    readiness_drops = [r for r in _all_readiness() if not r["ready"]]

    risk_center = get_risk_center_overview_api(role)

    return {
        "risk_center": risk_center,
        "readiness_drops": {"count": len(readiness_drops), "departments": readiness_drops},
        "not_yet_tracked": {
            "forecast_variances": "No prediction-vs-actual history is ever persisted -- there's no stored prior forecast to compare against.",
        },
    }


def recommendations(role):
    """readiness.pdf's "Recommendations" item: the action engine -- "not just
    reporting, actual guidance." Enriched (2026-07-19, this same reframe
    session) from a thin network_audit()-only pass-through into Sam's own
    fuller ask -- "This is where AI becomes truly valuable": Executive/Sales/
    Service/Finance/Inventory/Marketing recommendations, each a real,
    transparent rule firing off a real condition over real data (core/
    readiness_recommendations.py's 12-rule engine, same standing "rules
    engine over real data, never a fabricated LLM narrative" convention
    core/network_audit.py established session 38). core/network_audit.py's
    own real recommendation feed (network percentile gaps/obsolete parts/
    automation coverage/low readiness confidence) is kept alongside as
    `network_audit_recommendations` -- a genuinely different, complementary
    signal set (cross-dealer/employee-value-based, ADMIN/OPERATIONS/FINANCE-
    gated) rather than folded into or replaced by the new department-level
    engine, which is open to every real role."""

    department = get_recommendations_overview_api(role)

    audit = get_network_audit_api(role)
    network_audit_recommendations = audit.get("recommendations", []) if isinstance(audit, dict) and "error" not in audit else []
    network_audit_note = audit.get("error") if isinstance(audit, dict) and "error" in audit else None

    return {
        "categories": department.get("categories"),
        "executive_recommendations": department.get("executive_recommendations"),
        "kpi": department.get("kpi"),
        "overall_recommendation_score": department.get("overall_recommendation_score"),
        "overall_recommendation_score_note": department.get("overall_recommendation_score_note"),
        "network_audit_recommendations": network_audit_recommendations,
        "network_audit_note": network_audit_note,
        "generated_at": department.get("generated_at"),
    }


def strategic_planning(role):
    """readiness.pdf reframe's "Strategic Planning" item, #9 of Sam's 10-item
    proposed structure -- Sam's own words: "A completely new area." Real
    Quarterly Planning (Objectives, Goals, Budgets), Department Planning
    (Sales Goal, Inventory Target, Service Growth, Marketing Budget), and
    Initiative Tracking (New Website Launch, New Service Center, New BHPH
    Program, GPS Rollout -- "Monitor performance"). See core/
    strategic_planning.py's own module docstring for the full design,
    including exactly how this relates to core/system_config.py's pre-
    existing department_goals mechanism (Performance Readiness, item #4) --
    that stopgap stays the one real source Performance Readiness reads;
    this module can explicitly, one-way PUSH a quarterly objective's target
    down into it via sync_objective_to_monthly_goal(), never silently.
    Status is computed LIVE, never a manually-set field divorced from real
    progress -- real for Sales/Service/Marketing objectives (core/
    performance_readiness.py's exact real signal sources, generalized from
    a calendar month to a calendar quarter), an honest manual self-report
    for every other department. Initiative progress is real where a real
    graph signal exists (a linked Website's own publish status, a real
    InstalledDevice count against a target) and manual otherwise (e.g. "New
    Service Center," "New BHPH Program" -- no backing entity for either)."""

    return get_strategic_planning_overview_api(role)


def reporting(role):
    """readiness.pdf's "Reporting" item: formal predictive reporting. Data Quality
    Reports reuses data_health()'s connection/coverage summary. Readiness Reports
    reuses readiness()'s department scores plus a real Target Achievement count.
    Forecast Reports' Future Outlook reuses forecasts(); Accuracy/Variance have no
    backing history (same gap flagged everywhere else in this module). Risk Reports'
    Operational Deficits reuses the same not-ready department list exceptions()
    surfaces; Bottlenecks/Critical Dependencies have no backing entity. Executive
    Reports' Business Readiness/Forecast Confidence are real overall averages;
    Strategic Outlook/Growth Capacity have no backing model.

    ENRICHED (2026-07-19, this same reframe session -- the FINAL slice, closing
    out Readiness' full 10-item structure) with Sam's own executive-reporting
    spec, backend-only, same "core/report_modules.py already auto-discovers any
    new top-level key" precedent every prior department's Reporting slice
    established (Sales session 97, Inventory/Service/Finance sessions,
    Administration's own Reporting enrichment earlier this session) -- zero new
    routes needed, confirmed live before shipping.

    Dealer Principal Dashboard: Revenue/Net Profit/Cash Position reused
    directly from core/general_ledger.py's real income statement/balance sheet
    and core/bank_reconciliation.py's real book balance (both ADMIN/OPERATIONS/
    FINANCE-gated at their own layer -- degrades to that module's own real
    access-denied error for other roles, same convention core/business_health.py's
    finance_health() already established for Collections/Portfolio Quality),
    plus the same overall Readiness Score used elsewhere on this screen. No
    separate "Gross" line is reported distinct from Net Profit -- the general
    ledger's income statement carries one blended Revenue total (vehicle sales
    + loan interest income), not a segmented gross-margin figure; the real
    per-account breakdown is included instead of a fabricated one. No true
    Statement of Cash Flows (operating/investing/financing activity) is
    computed anywhere in this codebase -- Cash Position is a real point-in-time
    balance, not a period-over-period flow, and this is stated explicitly.

    Group Dashboard (multi-store comparison): an honest not_applicable note.
    This codebase is single-tenant per dealer (see CLAUDE.md's "NXTDeal Hub /
    Multi-Tenant Architecture" section) -- Store Rankings/Growth/Profitability/
    Risk-Level comparisons across multiple stores would need the Hub's real,
    separate cross-tenant anonymized aggregation mechanism
    (hub/core/network_collector.py / network_analytics.py), which has its own
    honest sample-size limitations. No fake "other store" data is fabricated
    here to fill this in.

    Board/Investor Report: real Forecasts (department_forecasts, reused
    verbatim from forecasts()), real top Exceptions (the Enterprise Risk
    Center's own categorized items, ranked by count), real top Recommendations
    (the Recommendations engine's own executive_recommendations, High/Critical
    severity), and a real Growth Opportunities section -- the same
    recommendation-engine's own Medium/Low severity TRIGGERED items (a real
    finding that isn't yet an urgent risk, i.e. a genuine improvement
    opportunity), the honest analog for "Growth Opportunities" since no
    dedicated growth-opportunity signal exists anywhere in this codebase
    (confirmed via grep before writing this -- core/network_audit.py's own
    recommendation feed has no "opportunity"-flavored signal_type either, only
    "risk").

    Also fixes a real, previously-silent bug found while building this: this
    function's own `scores` lookup read `ready.get("department_readiness", [])`,
    but readiness()'s own top-level key was renamed to `data_confidence_scores`
    when Performance Readiness shipped earlier this same reframe session --
    meaning readiness_reports.department_scores/target_achievement had been
    silently empty (always `[]` / always `{0, 0}`) ever since that rename,
    with nothing catching it since no route/frontend change exercised this
    specific field along the way. Fixed to read the real current key."""

    health = data_health(role)
    ready = readiness(role)
    forecast = forecasts(role)
    recs = recommendations(role)
    risk = exceptions(role)

    scores = ready.get("data_confidence_scores", [])

    target_achievement = {
        "at_or_above_target": len([s for s in scores if s["status"] == "At/Above Target"]),
        "below_target": len([s for s in scores if s["status"] == "Below Target"]),
    }

    overall = _all_readiness()
    overall_score = (
        round(sum(r["confidence_pct"] for r in overall) / len(overall), 1)
        if overall else None
    )

    # -- Dealer Principal Dashboard: Revenue / Net Profit / Cash Position ----
    income_statement = get_income_statement_api(role)
    balance_sheet = get_balance_sheet_api(role)
    reconciliation = get_reconciliation_status_api(role)

    revenue = None
    net_profit = None
    if isinstance(income_statement, dict) and "error" not in income_statement:
        revenue = income_statement.get("revenue", {}).get("total")
        net_profit = income_statement.get("net_income")

    cash_position = None
    if isinstance(reconciliation, dict) and "error" not in reconciliation:
        cash_position = reconciliation.get("book_balance")
    elif isinstance(balance_sheet, dict) and "error" not in balance_sheet:
        for line in balance_sheet.get("assets", {}).get("lines", []):
            if line.get("account") == "Cash":
                cash_position = line.get("balance")
                break

    dealer_principal_dashboard = {
        "revenue": revenue,
        "net_profit": net_profit,
        "cash_position": cash_position,
        "readiness_score_pct": overall_score,
        "basis": (
            "Revenue/Net Profit reused directly from core/general_ledger.py's real "
            "income statement (ADMIN/OPERATIONS/FINANCE-gated -- degrades to that "
            "module's own real access-denied error for other roles); Cash Position "
            "from core/bank_reconciliation.py's real book balance; Readiness Score "
            "is the same plain average of the 5 core/prediction.py-covered "
            "departments used elsewhere on this screen."
        ),
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "not_yet_tracked": {
            "gross_isolated_from_net": "core/general_ledger.py's income statement reports one blended Revenue total (vehicle sales + loan interest income) rather than a separate Gross line distinct from Net Profit -- see income_statement.revenue.lines/expenses.lines above for the real per-account breakdown instead.",
            "true_cash_flow_statement": "No Statement of Cash Flows (operating/investing/financing activity) is computed anywhere in this codebase -- cash_position above is a real point-in-time balance (core/bank_reconciliation.py), not a period-over-period flow.",
        },
    }

    # -- Group Dashboard: honest single-tenant scope note --------------------
    group_dashboard = {
        "not_applicable": (
            "This NXTDeal instance is single-tenant -- one dealer, one graph "
            "(see CLAUDE.md's 'NXTDeal Hub / Multi-Tenant Architecture' "
            "section). Store Rankings/Growth/Profitability/Risk-Level "
            "comparisons across multiple stores would need the NXTDeal Hub's "
            "real cross-tenant anonymized aggregation mechanism "
            "(hub/core/network_collector.py / hub/core/network_analytics.py) -- "
            "a genuinely separate, already-documented system with its own "
            "honest sample-size limitations, not something to fabricate here "
            "with fake 'other store' data."
        ),
    }

    # -- Board/Investor Report -------------------------------------------------
    top_exceptions = []
    if isinstance(risk, dict):
        for bucket in (risk.get("risk_center") or {}).get("categories", {}).values():
            top_exceptions.extend([i for i in (bucket or []) if i.get("count")])
    top_exceptions.sort(key=lambda i: i.get("count") or 0, reverse=True)

    top_recommendations = (recs.get("executive_recommendations") or [])[:5] if isinstance(recs, dict) else []

    growth_opportunities = []
    if isinstance(recs, dict):
        for bucket in (recs.get("categories") or {}).values():
            for item in (bucket or []):
                if item.get("triggered") and item.get("severity") in ("medium", "low"):
                    growth_opportunities.append(item)
    growth_opportunities.sort(key=lambda i: 0 if i.get("severity") == "medium" else 1)

    board_investor_report = {
        "forecasts": forecast.get("department_forecasts"),
        "top_exceptions": top_exceptions[:5],
        "top_recommendations": top_recommendations,
        "growth_opportunities": {
            "items": growth_opportunities[:10],
            "count": len(growth_opportunities),
            "basis": "real",
            "note": (
                "Real triggered recommendation-engine rules at Medium/Low "
                "severity -- genuine improvement areas that aren't urgent risks "
                "(High/Critical severity items are top_recommendations/"
                "top_exceptions above instead). The honest analog for 'Growth "
                "Opportunities,' since no dedicated growth-opportunity signal "
                "exists anywhere in this codebase (confirmed via grep -- "
                "core/network_audit.py's own recommendation feed has no "
                "'opportunity'-flavored signal_type either)."
            ),
        },
        "overall_readiness_pct": overall_score,
    }

    return {
        "dealer_principal_dashboard": dealer_principal_dashboard,
        "group_dashboard": group_dashboard,
        "board_investor_report": board_investor_report,
        "data_quality_reports": {
            "connected_systems_count": health.get("connected_systems", {}).get("count") if isinstance(health, dict) else None,
            "historical_coverage": health.get("historical_coverage") if isinstance(health, dict) else None,
        },
        "readiness_reports": {
            "department_scores": scores,
            "target_achievement": target_achievement,
        },
        "forecast_reports": {
            "future_outlook": forecast.get("forecasts_by_horizon"),
        },
        "risk_reports": {
            "operational_deficits": [r for r in overall if not r["ready"]],
        },
        "executive_reports": {
            "business_readiness_pct": overall_score,
            "forecast_confidence_pct": overall_score,
        },
        "department_intelligence": _DI_GAP_NOTE,
        "not_yet_tracked": {
            "readiness_trends": "No readiness-history/trend storage exists -- every score is a live snapshot, not a tracked-over-time series.",
            "forecast_accuracy": "No prediction-vs-actual history is ever persisted.",
            "forecast_variance": "Same gap as forecast_accuracy -- no prior forecast is stored to compare against.",
            "bottlenecks": "No dedicated cross-department bottleneck entity exists yet.",
            "critical_dependencies": "No dependency-mapping data model exists yet.",
            "strategic_outlook": "No qualitative strategic-planning model exists yet.",
            "growth_capacity": "No capacity-modeling data model exists yet.",
        },
    }
