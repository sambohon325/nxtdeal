"""
core/network_menu.py -- real data behind the Network intelligence layer's 8-item Top
Menu (core/menu_catalog.py), session 67. The ninth and final department in this
rollout. network.pdf's own framing: unlike every other department, Network isn't
managing your dealership at all -- it's managing your dealership's relationship to
every other dealership in the network ("NADA Twenty Groups, automotive benchmarking,
peer intelligence, market forecasting, best practice sharing... but real-time"). Its
Menu Bar (Overview | Peer Groups | Benchmarks | Gap Analysis | Trends | Playbooks |
Opportunities | Reporting) maps onto: How do we rank? Who are we compared against?
What are the real numbers? Where's the money on the table? What's moving? What do top
performers do differently? What should we actually do? How did we do?

Same discipline as every prior *_menu.py: reuse an already-built function wherever
it's a genuine match, compute a small new real aggregate where the graph has the data
but nobody queried it this way yet, and use an honest `not_yet_tracked` note (never a
fabricated number) wherever network.pdf asks for something this data model doesn't
back at all. This department reuses more pre-existing, purpose-built engines than any
other -- core/network_benchmark.py (session 38, the real percentile-ranking engine
over simulated peer data) and core/network_audit.py (session 38, the real rules-based
recommendation engine) both exist purely because Network needed them, and
core/kpi_snapshots.py (session 35, real day-over-day KPI trend deltas) turns out to
be exactly what the Trends item needs too. None of the 8 functions below add their own
role gate -- every one reuses a function that already self-gates to ADMIN/OPERATIONS/
FINANCE (core/network_api.py's NETWORK_ROLES / core/department_intelligence_api.py's
DEPT_INTEL_ROLES, the same tier), so a forbidden role's response degrades to that
function's own real error message rather than a second, redundant gate.

Confirmed structural gaps up front. First, a real coverage mismatch, the same class of
finding core/readiness_menu.py's session-66 build made for core/prediction.py:
network.pdf's Overview widget mocks a "Department Rankings" list showing Sales/
Service/Inventory/Marketing, but core/network_benchmark.py's real DEPARTMENTS is
core/department_intelligence.py's 5 keys -- sales/service/parts/fi/executive. "Parts" approximates
"Inventory" loosely (parts inventory turn/margin, not the Inventory department's
vehicle inventory -- no vehicle turn-rate exists anywhere in this codebase, the same
gap core/inventory_menu.py's session-63 pricing() already found) and "fi" approximates
"Finance" loosely (F&I reserve income/APR, not the full Finance department's
floorplan/accounting); there is no Marketing benchmark at all. Every function below
reports the real 5 covered departments and says so explicitly, rather than relabeling
them to match the PDF's example wording. Second, this environment is single-tenant --
there is no real second NXTDeal dealer connected, so every peer figure here is
SIMULATED (blind-labeled Dealer B/C/D/E, core/network_benchmark.py's own
basis="simulated_peer_data"), carried forward honestly rather than presented as real
cross-dealer data. Third, no Playbook entity/curated-content model, no market/regional/
OEM trend-signal data source, and no benchmark-rank history store exist anywhere in
this codebase (confirmed via grep) -- Playbooks reuses the real recommendation feed as
the closest honest analog rather than fabricated "Top 1% Recon Workflow" content, and
Trends leans on real per-KPI day-over-day deltas rather than qualitative demand
signals that don't exist.

Enriched 2026-07-18 (first slice of Sam's "NXTDeal Intelligence Network" reframe --
an 11-item structure, a "24/7 AI 20 Group," plus a parallel NXTDeal Hub restructure;
this slice covers Overview + Opportunities): overview() and opportunities() gained a
real, honest DOLLAR-denominated opportunity layer (core/network_opportunity_value.py)
on top of the existing gap_analysis() math -- every gap is either a direct dollar
figure (already currency-shaped), a dollar figure DERIVED from a real per-unit value
already on this dealer's own KPIs (e.g. a units_sold gap x this dealer's own real
gross_profit_per_unit), or honestly reported as not_convertible_to_dollars when no
real multiplier exists (every percentage-point/ratio gap) -- never an invented
multiplier presented as fact. The old opportunity_tracker.potential_gross_opportunity
_monthly field (a mixed-unit sum across dollars/percentages/counts) is left in place,
now explicitly documented as NOT dollar-denominated, alongside the new real
dollar_opportunity/largest_opportunities/executive_summary fields. See
core/network_opportunity_value.py's own module docstring for the full formula
breakdown.
"""

from core.network_api import get_network_benchmarks_api, get_network_audit_api
from core.network_benchmark import PEER_LABELS, gap_direction, BHPH_DEPARTMENT_KEY
from core.department_intelligence_api import get_department_api
from core.department_intelligence import DEPARTMENTS as INTELLIGENCE_DEPARTMENTS
from core.network_opportunity_value import (
    get_department_dollar_opportunities,
    get_total_identified_opportunity,
    get_largest_opportunities,
    generate_executive_summary,
    get_dollar_denominated_gaps,
)
from core.network_root_cause import get_root_causes
from core.network_trends import (
    ALL_TREND_DEPARTMENTS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PROJECTION_DAYS,
    get_bhph_kpis_with_trend,
    get_department_trend_history,
    project_gap_closure,
)
from core.network_playbooks import get_playbook_library
from core.ai_management import get_call_stats

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Network
# already surfaces Department Intelligence's 5 real keys indirectly through
# benchmark_reports (via get_network_benchmarks_api -> get_department_api under the
# hood) -- there's no separate "Network" Department Intelligence key to point Reporting
# at directly, so this points back to that existing block rather than duplicating it.
_DI_GAP_NOTE = {
    "available": False,
    "note": (
        "No standalone 'Network' Department Intelligence key exists -- see "
        "benchmark_reports above, which already surfaces the real 5 Department "
        "Intelligence keys (sales/service/parts/fi/executive) per peer comparison."
    ),
}


_OPPORTUNITY_CATEGORY_TO_BUCKET = {
    "profit_leak": "cost_reduction_opportunities",
    "automation_opportunity": "staffing_recommendations",
    "network_benchmark": "operational_improvements",
    "data_readiness": "process_improvements",
}

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def overview(role):
    """network.pdf's "Overview" item: the network intelligence command center -- "the
    dealership scoreboard." Department Rankings/Network Percentile Rank/Benchmark
    Score/Active Recommendations are all real, reused directly from
    core/network_benchmark.py's percentile engine and core/network_audit.py's
    recommendation count. Peer Comparison Snapshot is a real aggregate computed
    over the same real (simulated-peer-basis) benchmark data -- 'best_peer' honestly
    stands in for network.pdf's 'Top 10%' since only 4 simulated peers exist, no real
    percentile granularity for a literal top decile. opportunity_tracker's
    potential_gross_opportunity_monthly is a raw sum across MIXED KPI UNITS (dollars,
    percentage points, unit counts) -- NOT a real dollar total, see dollar_opportunity
    below for the honest, formula-derived dollar figure (core/
    network_opportunity_value.py) plus largest_opportunities (Sam's 'Largest
    Opportunities' list) and executive_summary (a real, rules-based templated
    narrative with an optional isolated-OpenAI phrasing polish). Peer Group Health,
    Market Trend Index, Best Practice Matches, and Forecast Variance have no backing
    data model -- see this module's other items for the closest real analogs
    (Trends, Playbooks) or an explicit gap."""

    benchmarks = get_network_benchmarks_api(role)

    if isinstance(benchmarks, dict) and "error" in benchmarks:
        return benchmarks

    audit = get_network_audit_api(role)

    department_rankings = [
        {
            "department": entry["department"],
            "title": entry["title"],
            "percentile_rank": entry["percentile_rank"],
        }
        for entry in benchmarks.get("departments", [])
    ]

    ranked = [d["percentile_rank"] for d in department_rankings if d["percentile_rank"] is not None]
    avg_percentile = round(sum(ranked) / len(ranked), 1) if ranked else None

    peer_snapshot = []
    total_opportunity = 0.0

    for entry in benchmarks.get("departments", []):

        primary_key = entry.get("primary_kpi")
        this_value = entry["this_dealer"]["kpis"].get(primary_key, {}).get("value") if primary_key else None

        peer_values = [
            p["kpis"].get(primary_key, {}).get("value")
            for p in entry.get("peers", [])
        ] if primary_key else []
        peer_values = [v for v in peer_values if isinstance(v, (int, float))]

        if not isinstance(this_value, (int, float)) or not peer_values:
            continue

        peer_avg = round(sum(peer_values) / len(peer_values), 2)
        peer_best = round(max(peer_values), 2)
        gap_vs_avg = round(peer_avg - this_value, 2)

        if gap_vs_avg > 0:
            total_opportunity += gap_vs_avg

        peer_snapshot.append({
            "department": entry["department"],
            "kpi": primary_key,
            "you": this_value,
            "average_peer": peer_avg,
            "best_peer": peer_best,
            "best_peer_note": "Stands in for 'Top 10%' -- only 4 simulated peers exist, no real percentile granularity for a literal top decile.",
        })

    active_recommendations = (
        audit.get("recommendation_count") if isinstance(audit, dict) and "recommendation_count" in audit else None
    )

    dept_opportunities = get_department_dollar_opportunities(role)
    total_opportunity_dollars = get_total_identified_opportunity(role)
    largest = get_largest_opportunities(role, limit=5)
    # Reading a dashboard must not invoke an external model. Explicit summary
    # regeneration still supports polish=True through the existing API.
    summary = generate_executive_summary(role, polish=False)

    return {
        "network_percentile_rank": {"avg_pct": avg_percentile},
        "benchmark_score": {"avg_pct": avg_percentile},
        "department_rankings": department_rankings,
        "peer_comparison_snapshot": peer_snapshot,
        "opportunity_tracker": {
            "potential_gross_opportunity_monthly": round(total_opportunity, 2) if peer_snapshot else None,
            "basis": "simulated_peer_data",
            "note": (
                "This is a raw sum of positive peer-average-minus-you gaps across "
                "MIXED KPI UNITS (dollars, percentage points, unit counts) -- NOT a "
                "real dollar total. See dollar_opportunity below for the real, "
                "honestly-converted dollar figure."
            ),
        },
        "dollar_opportunity": {
            "monthly": total_opportunity_dollars.get("total_monthly_opportunity") if isinstance(total_opportunity_dollars, dict) else None,
            "annualized": total_opportunity_dollars.get("total_annualized_opportunity") if isinstance(total_opportunity_dollars, dict) else None,
            "by_department": dept_opportunities.get("departments") if isinstance(dept_opportunities, dict) else None,
            "excluded_departments": total_opportunity_dollars.get("excluded_departments") if isinstance(total_opportunity_dollars, dict) else None,
            "basis_notice": total_opportunity_dollars.get("basis_notice") if isinstance(total_opportunity_dollars, dict) else None,
        },
        "largest_opportunities": largest.get("largest_opportunities") if isinstance(largest, dict) else None,
        "executive_summary": summary,
        "active_recommendations": {"count": active_recommendations},
        "not_yet_tracked": {
            "peer_group_health": "No peer-group-health scoring concept exists yet.",
            "market_trend_index": "No composite market-trend index exists -- see the Trends item for real per-KPI day-over-day deltas instead.",
            "best_practice_matches": "No curated playbook/best-practice content model exists yet -- see the Playbooks item.",
            "forecast_variance": "No prediction-vs-actual history is ever persisted anywhere in this codebase.",
        },
    }


def peer_groups(role):
    """network.pdf's "Peer Groups" item: the digital Twenty Group manager -- "this
    determines who you're compared against." Enriched 2026-07-18 (Intelligence
    Network reframe, slice 2, Sam: "This becomes the digital version of a dealer 20
    Group") -- reuses core/network_benchmark.py's real PEER_POOLS catalog for real
    Multiple Peer Pools (OEM Peers / Local Market Peers / NXTDeal Elite Group /
    Similar Revenue Stores, alongside the original default 4-peer set), each a
    distinct, deterministically-seeded SIMULATED distribution -- this environment is
    still single-tenant, so every pool is illustrative/simulated rather than a real
    filtered dealer roster, but no longer just one fixed set. active_peer_group
    (labels/basis/note) is kept, unchanged, for backward compatibility with any
    existing caller that only reads that field."""

    benchmarks = get_network_benchmarks_api(role)

    if isinstance(benchmarks, dict) and "error" in benchmarks:
        return benchmarks

    return {
        "peer_pools": benchmarks.get("peer_pools", []),
        "active_peer_pool": benchmarks.get("peer_pool"),
        "active_peer_group": {
            "labels": PEER_LABELS,
            "basis": "simulated_peer_data",
            "note": (
                "This environment is single-tenant -- there is no real second "
                "NXTDeal dealer connected yet. These 4 blind-labeled peers "
                "(Dealer B/C/D/E) are simulated, fixed-anchor benchmarks "
                "(core/network_benchmark.py, session 38), not filterable real "
                "dealer records. See peer_pools above for the other 4 available "
                "SIMULATED pools (OEM Peers/Local Market Peers/NXTDeal Elite Group/"
                "Similar Revenue Stores) -- select one via GET /network/benchmark"
                "?peer_pool={key}."
            ),
        },
        "comparison_settings": {
            "departments_compared": [d["department"] for d in benchmarks.get("departments", [])],
        },
        "not_yet_tracked": {
            "oem_group": "No real OEM attribute exists on any peer/dealer record -- 'OEM Peers' above is a SIMULATED illustrative pool, not a real OEM-filtered roster.",
            "regional_group": "No real geography attribute exists on any peer/dealer record -- 'Local Market Peers' above is a SIMULATED illustrative pool, not a real geography-filtered roster.",
            "volume_group": "No real monthly-volume/revenue-band attribute exists on any peer/dealer record -- 'Similar Revenue Stores' above is a SIMULATED illustrative pool, not a real volume-filtered roster.",
            "custom_groups": "No custom peer-group builder exists -- the 5 pools above are a fixed catalog, not caller-defined criteria.",
            "filters": "OEM/Geography/Volume/Market Type/Dealer Size filters have no backing real attributes to filter a real dealer roster on yet -- see the 5 SIMULATED pools above as the honest, labeled stand-in.",
        },
    }


def benchmarks(role, peer_pool=None):
    """network.pdf's "Benchmarks" item: pure performance benchmarking -- "real-time
    NADA composite reporting." Reuses get_network_benchmarks_api() directly (the real
    percentile-ranking engine, unchanged) rather than a second computation. Enriched
    2026-07-18 (Intelligence Network reframe, slice 2): department coverage is now
    6, not 5 -- core/network_benchmark.py's real new "bhph" entry (Delinquency/Repo
    Rate/Recovery Rate/Yield/Charge-Offs, 100% real current-dealer data vs. a
    SIMULATED industry-range peer pool) is included automatically since
    get_network_benchmarks_api() now appends it to `departments`. Sales/Service also
    gained a few additional real KPIs this same slice (Show Rate/Close Rate/Lead
    Response Time, Hours Per RO) -- see core/network_benchmark.py's own module
    docstring point 3 for the reused-engine breakdown. peer_pool is an optional
    override (any key from core/network_benchmark.py's PEER_POOLS, default "default")
    -- callers hitting this via the generic GET /menu/data path always get the
    default pool; use GET /network/benchmark?peer_pool={key} directly to select a
    different one (same 'bespoke fetch bypasses /menu/data' precedent every other
    pool-aware or query-capable Network view in this codebase already follows)."""

    result = get_network_benchmarks_api(role, peer_pool=peer_pool) if peer_pool else get_network_benchmarks_api(role)

    if isinstance(result, dict) and "error" in result:
        return result

    return {
        "department_benchmarks": result.get("departments", []),
        "peer_pool": result.get("peer_pool"),
        "peer_pools": result.get("peer_pools", []),
        "note": (
            "Real coverage is sales/service/parts/fi/executive/bhph (5 real "
            "core/department_intelligence.py departments plus a real 6th 'bhph' "
            "entry, core/network_benchmark.py) -- network.pdf's own Inventory/"
            "Marketing/Finance benchmark views don't map 1:1: 'parts' is Parts "
            "inventory turn/margin, not the Inventory department's vehicle "
            "inventory (no vehicle turn-rate exists, same gap "
            "core/inventory_menu.py's session-63 pricing() already found); 'fi' is "
            "F&I-specific (reserve income, APR), not the full Finance department; "
            "'bhph' is real current-dealer portfolio/collections/repossession/"
            "accounting data compared against a SIMULATED industry-range peer pool "
            "(not a real second dealer -- see the 'bhph' entry's own "
            "peer_pool_description); there is no Marketing benchmark at all."
        ),
        "not_yet_tracked": {
            "marketing_roi": "No Marketing ROI benchmark KPI exists -- Marketing isn't one of core/department_intelligence.py's 5 tracked departments.",
            "sales_per_employee": "No headcount-normalized sales benchmark KPI exists yet.",
            "service_inspection_conversion": "No DVI-finding-to-repair-order conversion metric exists anywhere in this codebase to reuse -- an honest gap, not guessed at.",
            "service_advisor_productivity": "No per-advisor (distinct from per-technician) productivity metric exists anywhere in this codebase -- core/service_reporting.py's technician scorecard is per-TECHNICIAN, not per-advisor.",
        },
    }


def _gap_severity(peer_gap_pct, is_opportunity):
    """A real, transparent, threshold-based severity classification -- not a
    fabricated score. Only meaningful for a genuine opportunity (this dealer
    trailing peers); an "ahead" or "even" gap gets no severity at all."""

    if not is_opportunity or peer_gap_pct is None:
        return None

    abs_pct = abs(peer_gap_pct)

    if abs_pct >= 25:
        return "high"
    if abs_pct >= 10:
        return "medium"
    return "low"


def _enrich_gap(g, dollar_lookup):
    """Attaches real root_causes (core/network_root_cause.py) and real
    revenue_impact (core/network_opportunity_value.py's own dollar-conversion
    formulas, reused verbatim -- not a second formula engine) to one gap
    entry. Only called for the enriched subset (see gap_analysis())."""

    dollar_entry = dollar_lookup.get((g["department"], g["kpi"]))

    if dollar_entry:
        g["revenue_impact"] = {
            "dollar_impact_monthly": dollar_entry.get("dollar_impact_monthly"),
            "annualized_dollar_impact": dollar_entry.get("annualized_dollar_impact"),
            "conversion_method": dollar_entry.get("conversion_method"),
            "real_inputs_used": dollar_entry.get("real_inputs_used"),
            "not_convertible_reason": dollar_entry.get("not_convertible_reason"),
            "unit_impact": dollar_entry.get("unit_impact"),
            "portfolio_exposure_impact": dollar_entry.get("portfolio_exposure_impact"),
        }
    else:
        g["revenue_impact"] = None

    rc = get_root_causes(g["department"], g["kpi"], g.get("label"))
    g["root_causes"] = rc["causes"]
    g["root_cause_note"] = rc["note"]


def gap_analysis(role):
    """network.pdf's "Gap Analysis" item: the profit leakage center -- "this may
    become the most valuable screen in the entire platform." A genuinely new real
    aggregate: for every numeric KPI on every real benchmarked department, computes
    peer_average minus this dealer's value (the exact "Peer Average: 3.6 / Your
    Store: 2.8 / Gap: 0.8" shape network.pdf's own example describes), ranked by the
    size of the gap so the largest opportunities surface first. Real math, but over
    SIMULATED peer data -- same basis_notice core/network_benchmark.py's own
    benchmark_department() already carries.

    Enriched 2026-07-18 (root-cause/revenue-impact slice, slice 3):

      1. FIXED, not just flagged: direction/severity now respect each KPI's real
         higher-is-better/lower-is-better semantic via core/network_benchmark.py's
         shared gap_direction() -- the bhph department's 3 lower-is-better rate KPIs
         (delinquency_rate_pct/repo_rate_pct/charge_off_rate_pct) are no longer
         mislabeled as an opportunity when this dealer is actually ahead of peers on
         them. Every gap now carries higher_is_better/direction ("ahead"/"behind"/
         "even")/is_opportunity/opportunity_gap (the real, always-non-negative
         magnitude of how far behind, when is_opportunity) alongside the original
         `gap` (still the raw signed peer_average - this_store value, unchanged, for
         backward compatibility with any existing caller).

      2. Root Cause Analysis -- real, threshold-based diagnostic checks over
         already-built engines elsewhere in this codebase (core/network_root_cause.py),
         e.g. "Likely Causes: Slow Lead Response (avg 73 min speed-to-lead), Low SMS
         Utilization (12% of appointments)." Never a fabricated plausible-sounding
         sentence -- a KPI with no real diagnostic mapped gets an honest note instead.

      3. Revenue Impact -- real dollar-conversion figures, reusing core/
         network_opportunity_value.py's exact formulas (not a second engine):
         direct-currency/derived-per-unit-value gaps get their existing real dollar
         figure; Sales' close_rate/show_rate percentage-point gaps additionally get a
         real "N more sale(s)/appointment(s) shown per month" unit figure chained
         through this dealer's own real monthly lead volume (matching Sam's own "18
         more sales/month, $84,000 additional gross/month" framing); the bhph
         department's 3 lower-is-better rate gaps get a real one-time dollars-at-risk
         reduction figure chained through this dealer's own real outstanding portfolio
         balance.

      Root causes + revenue impact are attached to the UNION of the top 10 gaps by
      |gap| (largest_gaps, unchanged ranking) and the top 10 REAL opportunities by
      opportunity_gap magnitude (largest_opportunity_gaps, new) -- capped there to keep
      the payload reasonable, since a real opportunity worth enriching could rank
      outside the top 10 by raw |gap| if this dealer is meaningfully ahead of peers on
      several other KPIs."""

    result = get_network_benchmarks_api(role)

    if isinstance(result, dict) and "error" in result:
        return result

    gaps = []

    for entry in result.get("departments", []):

        department = entry["department"]
        this_kpis = entry["this_dealer"]["kpis"]
        peers = entry.get("peers", [])

        for kpi_key, kpi_data in this_kpis.items():

            this_value = kpi_data.get("value")

            if not isinstance(this_value, (int, float)):
                continue

            peer_values = [
                p["kpis"].get(kpi_key, {}).get("value")
                for p in peers
            ]
            peer_values = [v for v in peer_values if isinstance(v, (int, float))]

            if not peer_values:
                continue

            peer_avg = round(sum(peer_values) / len(peer_values), 2)
            gap = round(peer_avg - this_value, 2)
            direction = gap_direction(department, kpi_key, gap)
            peer_gap_pct = round(gap / peer_avg * 100, 1) if peer_avg else None

            gaps.append({
                "department": department,
                "kpi": kpi_key,
                "label": kpi_data.get("label", kpi_key),
                "this_store": this_value,
                "peer_average": peer_avg,
                "gap": gap,
                "peer_gap_pct": peer_gap_pct,
                "format": kpi_data.get("format"),
                "higher_is_better": direction["higher_is_better"],
                "direction": direction["direction"],
                "is_opportunity": direction["is_opportunity"],
                "opportunity_gap": direction["opportunity_gap"],
                "severity": _gap_severity(peer_gap_pct, direction["is_opportunity"]),
                "root_causes": None,
                "root_cause_note": None,
                "revenue_impact": None,
            })

    gaps.sort(key=lambda g: abs(g["gap"]), reverse=True)

    largest_gaps = gaps[:10]
    largest_opportunity_gaps = sorted(
        [g for g in gaps if g["is_opportunity"]],
        key=lambda g: g["opportunity_gap"] or 0,
        reverse=True,
    )[:10]

    enrich_targets = list(largest_gaps)
    seen_ids = {id(g) for g in enrich_targets}
    for g in largest_opportunity_gaps:
        if id(g) not in seen_ids:
            enrich_targets.append(g)
            seen_ids.add(id(g))

    if enrich_targets:
        dollar_gaps = get_dollar_denominated_gaps(role)
        dollar_lookup = (
            {(d["department"], d["kpi"]): d for d in dollar_gaps.get("gaps", [])}
            if isinstance(dollar_gaps, dict) and "error" not in dollar_gaps
            else {}
        )
        for g in enrich_targets:
            if g["is_opportunity"]:
                _enrich_gap(g, dollar_lookup)

    return {
        "largest_gaps": largest_gaps,
        "largest_opportunity_gaps": largest_opportunity_gaps,
        "all_gaps": gaps,
        "basis_notice": (
            "Gap values are computed against SIMULATED peer benchmarks "
            "(blind-labeled Dealer B/C/D/E by default -- see peer_pool on each "
            "underlying benchmark entry for which pool was used, "
            "core/network_benchmark.py). Real once a second NXTDeal dealer "
            "connects and reports its own Department Intelligence KPIs the same "
            "way. FIXED 2026-07-18 (root-cause/revenue-impact slice): direction/"
            "severity/opportunity_gap now respect each KPI's real higher-is-better/"
            "lower-is-better semantic (core/network_benchmark.py's gap_direction()) "
            "-- the bhph department's 3 lower-is-better rate KPIs "
            "(delinquency_rate_pct/repo_rate_pct/charge_off_rate_pct) are no longer "
            "mislabeled as an opportunity when this dealer is already ahead of peers "
            "on them. The raw `gap` field (peer_average - this_store) is unchanged "
            "for backward compatibility -- use `is_opportunity`/`direction`/"
            "`opportunity_gap` for a correct read."
        ),
        "not_yet_tracked": {
            "retention_gaps": "No customer retention/repeat-business benchmark KPI exists yet.",
            "conversion_gaps": "No lead-to-sale conversion-rate benchmark KPI exists yet.",
            "staffing_gaps": "No headcount-normalized (e.g. sales-per-employee) benchmark KPI exists yet.",
        },
    }


def trends(role, history_days=DEFAULT_HISTORY_DAYS):
    """network.pdf's "Trends" item: the market intelligence center -- "this lets
    dealers react before competitors do." Reuses core/kpi_snapshots.py's real
    day-over-day KPI trend-delta mechanism (session 35, via
    core/department_intelligence_api.py's get_department_api) across all 5 real
    department-intelligence departments -- genuine delta_pct/has_history/compared_to
    per KPI, not fabricated 'Used Truck Demand +11%' narrative. has_history=false is
    expected, not a bug, the first time a department's dashboard has ever been opened
    (or is reopened same-day, since a snapshot is recorded once per department per
    calendar day). Regional/OEM/consumer-demand-signal trend data has no backing
    source anywhere in this codebase.

    Enriched 2026-07-18 (Intelligence Network reframe, slice 4): (1) the real bhph
    portfolio department is now included alongside the original 5 -- it never had
    ANY trend coverage before this slice (core/network_benchmark.py's
    compute_bhph_kpis() had no with_trend() call anywhere, confirmed via grep), now
    real day-over-day deltas via core/network_trends.py's get_bhph_kpis_with_trend().
    (2) a real `history` block per department (core/network_trends.py's
    get_department_trend_history(), `history_days` calendar days, default 90) --
    every real DepartmentSnapshot actually recorded within the window, in date order,
    with an honest `days_with_data` vs. `days_requested` count so sparse real history
    (this backend has no real overnight batch job -- see core/kpi_snapshots.py's own
    docstring) is never silently presented as a full window of data."""

    department_trends = {}
    department_history = {}

    for department in INTELLIGENCE_DEPARTMENTS:

        result = get_department_api(role, department)

        if isinstance(result, dict) and "error" in result and "kpis" not in result:
            return result

        kpis = result.get("kpis", [])

        department_trends[department] = [
            {
                "key": k.get("key"),
                "label": k.get("label"),
                "value": k.get("value"),
                "delta_pct": k.get("delta_pct"),
                "has_history": k.get("has_history"),
                "compared_to": k.get("compared_to"),
            }
            for k in kpis
        ]

        department_history[department] = get_department_trend_history(department, days=history_days)

    bhph_result = get_bhph_kpis_with_trend(role)

    if bhph_result is not None:
        department_trends[BHPH_DEPARTMENT_KEY] = [
            {
                "key": k.get("key"),
                "label": k.get("label"),
                "value": k.get("value"),
                "delta_pct": k.get("delta_pct"),
                "has_history": k.get("has_history"),
                "compared_to": k.get("compared_to"),
            }
            for k in bhph_result.get("kpis", [])
        ]
        department_history[BHPH_DEPARTMENT_KEY] = get_department_trend_history(BHPH_DEPARTMENT_KEY, days=history_days)

    return {
        "department_trends": department_trends,
        "history_days_requested": history_days,
        "department_history": department_history,
        "note": (
            "Real day-over-day KPI deltas (core/kpi_snapshots.py, session 35) -- "
            "each department's dashboard is snapshotted the first time it's opened "
            "each day, and delta_pct compares against the most recent prior "
            "snapshot. has_history=false is expected, not a bug, the first time a "
            "department is ever opened or reopened same-day. FIXED 2026-07-18: the "
            "real 'bhph' portfolio department (added slice 2) never had ANY trend "
            "coverage before this slice -- it's now included alongside the "
            "original 5. `department_history` is a real 90-day-or-however-many-"
            "days-were-actually-recorded snapshot series, not a fabricated full "
            "window -- check each department's `days_with_data` for the real "
            "coverage."
        ),
        "not_yet_tracked": {
            "regional_trends": "No geography-tagged trend data exists anywhere in this codebase.",
            "oem_trends": "No OEM-tagged trend data exists anywhere in this codebase.",
            "consumer_demand_signals": "No consumer-demand-signal data source exists anywhere in this codebase.",
        },
    }


def forecasts(role, project_days=DEFAULT_PROJECTION_DAYS, history_days=DEFAULT_HISTORY_DAYS):
    """A new Network Top Menu item (added 2026-07-18, Intelligence Network reframe,
    slice 4). This dealer's own real trend, projected forward -- a real linear
    projection (core/network_trends.py's project_gap_closure(), ordinary least
    squares over actual recorded DepartmentSnapshot history) compared against the
    (static, SIMULATED) peer average from gap_analysis() to estimate whether a real
    gap is closing, widening, or holding.

    Deliberately NOT a "competitive forecast" in the sense of predicting where
    PEERS will be -- core/network_benchmark.py's peer averages are a fixed
    simulated snapshot with no time series of their own, so there is nothing real
    to project on that side. This only ever answers "is this dealer's own real
    trajectory moving toward or away from where peers currently sit," and only for
    KPIs with at least 2 real recorded snapshot days -- every other KPI is reported
    honestly as not-yet-projectable rather than guessed at."""

    gaps_result = gap_analysis(role)

    if isinstance(gaps_result, dict) and "error" in gaps_result:
        return gaps_result

    projections = []

    for g in gaps_result.get("all_gaps", []):

        projection = project_gap_closure(
            g["department"],
            g["kpi"],
            g["peer_average"],
            g["higher_is_better"],
            days_history=history_days,
            project_days=project_days,
        )
        projection["label"] = g["label"]
        projection["format"] = g["format"]

        projections.append(projection)

    projectable = [p for p in projections if p["projectable"]]
    not_projectable_count = len(projections) - len(projectable)

    closing = [p for p in projectable if p.get("gap_trend") == "closing"]
    widening = [p for p in projectable if p.get("gap_trend") == "widening"]

    return {
        "project_days": project_days,
        "history_days_considered": history_days,
        "projectable_kpi_count": len(projectable),
        "not_projectable_kpi_count": not_projectable_count,
        "closing_gaps": sorted(closing, key=lambda p: p.get("current_gap", 0), reverse=True),
        "widening_gaps": sorted(widening, key=lambda p: p.get("current_gap", 0), reverse=True),
        "all_projections": projections,
        "basis_notice": (
            "Every projection here is a REAL linear (ordinary-least-squares) fit over this "
            "dealer's own actual recorded DepartmentSnapshot history (core/kpi_snapshots.py) "
            "-- never a fabricated slope. Most KPIs will show `projectable: false` on a "
            "freshly-deployed dealer, since this backend has no real overnight batch job and "
            "a snapshot is only recorded the first time a department's dashboard is opened "
            "each day -- real history accumulates day by day, not guessed at to fill a "
            "90-day window. The peer_average side of every comparison is a FIXED simulated "
            "snapshot, not a real time series, so 'closing'/'widening' describes this "
            "dealer's own movement toward or away from a static target, not a real "
            "competitive race against a moving peer."
        ),
        "not_yet_tracked": {
            "peer_trend_projection": "Peer averages are a fixed simulated snapshot with no time series of their own -- no real peer-side trend exists anywhere to project.",
            "regional_oem_forecast": "No regional/OEM/demand-signal forecast data exists anywhere in this codebase.",
        },
    }


def playbooks(role):
    """network.pdf's "Playbooks" item: the best-practice sharing center -- "this is
    where the network starts teaching dealers."

    Enriched 2026-07-18 (Intelligence Network reframe, slice 5): a real curated
    library (core/network_playbooks.py) replaces the old honest-but-thin analog of
    just reusing the recommendation feed. Every playbook references a real NXTDeal
    screen/workflow that already exists in this codebase, is tied to one of
    core/network_root_cause.py's real diagnostic functions (re-run live here, so
    `is_currently_active` is a real checked fact about THIS dealer's current data,
    not a static description), and carries a real Automation Score against
    core/workflow_automation.py's actual rule engine -- 0 (no automation path
    exists), 1 (a matching trigger type exists but no live rule is configured), or
    3 (a matching trigger type exists AND a live rule is already active). The old
    `related_recommendations` field (the recommendation feed reused as an honest
    analog) is kept alongside it, unchanged, for backward compatibility. No Playbook
    entity or dealer-submittable content-authoring model exists anywhere in this
    codebase (confirmed via grep) -- this catalog is a fixed, hand-written set, not
    crowd-sourced, since this environment is single-tenant (no real peer dealer to
    crowd-source 'Top 1%' content from)."""

    audit = get_network_audit_api(role)

    if isinstance(audit, dict) and "error" in audit:
        return audit

    library = get_playbook_library(role)

    return {
        "library": library["playbooks"],
        "playbook_count": library["playbook_count"],
        "currently_active_count": library["currently_active_count"],
        "library_note": library["note"],
        "related_recommendations": audit.get("recommendations", []),
        "note": (
            "A real curated playbook library now exists (`library` above) -- see "
            "`library_note` for its own scope/honesty notes. The pre-existing "
            "cross-department recommendation feed (core/network_audit.py, session "
            "38) is kept alongside it, unchanged, under `related_recommendations`."
        ),
        "not_yet_tracked": {
            "dealer_submittable_playbooks": "This catalog is a fixed, hand-written set -- no dealer-submittable/crowd-sourced content-authoring model exists yet (this environment is single-tenant).",
            "average_turn_time_benchmarks": "No workflow-timing benchmark data (e.g. recon turn time) exists anywhere in this codebase.",
            "playbook_simulation": "No 'simulate impact before deploying locally' capability exists -- see the Simulations gap already flagged in core/readiness_menu.py.",
        },
    }


def ai_advisors(role):
    """Intelligence Network reframe, slice 6 -- the "AI Advisors" Top Menu item.
    The generic GET /menu/data view for this item just returns the real 5-advisor
    catalog (core/network_advisors.py's list_advisors()); the actual Q&A
    interaction (a question needs a POST) is served by the dedicated
    POST /network-advisors/ask route, not this GET dispatch -- same "bespoke
    board bypasses /menu/data for its own extra views" precedent every other
    Network slice this reframe has established.

    Deferred import (not a top-of-file import) deliberately -- core/
    network_advisors.py itself imports gap_analysis from THIS module, so a
    module-level import here would be a real circular import."""

    from core.network_advisors import list_advisors as _list_advisors

    return {
        "advisors": _list_advisors(),
        "note": (
            "5 real, department-specific Q&A advisors. Ask a question via "
            "POST /network-advisors/ask -- each advisor's answer is composed "
            "strictly from this dealer's own real benchmark comparison, gap "
            "analysis, and curated playbook data (all built earlier in this "
            "same Intelligence Network reframe); AI phrasing is optional "
            "polish over an always-real, topic-matched fallback, never "
            "load-bearing."
        ),
    }


def consulting_engine(role):
    """AI Consulting Engine (2026-07-23) -- the Network Top Menu item for the
    strategic centerpiece. The generic GET /menu/data view for this item returns
    the real engine overview (starter questions + which data feeds currently have
    data + recent consultations, core/consulting_engine.py's get_consulting_
    overview()); the actual four-part consultation (a question needs a POST) is
    served by the dedicated POST /consulting-engine/ask route, not this GET
    dispatch -- same "bespoke board bypasses /menu/data for its own POST view"
    precedent ai_advisors() above and every other Network slice already set.

    Deferred import (not a top-of-file import) deliberately -- core/
    consulting_engine.py itself imports FROM this module's chain (network_advisors
    -> network_menu), so a module-level import here would be a real circular
    import, exactly like ai_advisors() above."""

    from core.consulting_engine import get_consulting_overview as _get_consulting_overview

    return _get_consulting_overview(role)


def opportunities(role):
    """network.pdf's "Opportunities" item: action-oriented intelligence -- "unlike
    reports, this page focuses only on actions." Groups the same real, severity-
    ranked recommendation feed core/network_audit.py computes (session 38) into
    network.pdf's 5 named buckets by real category. 'revenue_opportunities' has no
    distinct backing category yet -- none of run_audit()'s 4 rule categories are
    tagged specifically as revenue-generating vs. cost/efficiency -- shown as an
    honest empty bucket rather than re-labeling an unrelated recommendation to fill
    it. Enriched (Intelligence Network reframe, slice 1) with real, dollar-
    denominated department totals + a grand total (Sam's "Total Identified
    Opportunity") + the same largest_opportunities list Overview shows -- see
    core/network_opportunity_value.py for the full real/derived/not-convertible
    formula breakdown."""

    audit = get_network_audit_api(role)

    if isinstance(audit, dict) and "error" in audit:
        return audit

    recommendation_list = audit.get("recommendations", [])

    buckets = {
        "revenue_opportunities": [],
        "cost_reduction_opportunities": [],
        "operational_improvements": [],
        "staffing_recommendations": [],
        "process_improvements": [],
    }

    for r in recommendation_list:
        bucket_key = _OPPORTUNITY_CATEGORY_TO_BUCKET.get(r["category"])
        if bucket_key:
            buckets[bucket_key].append(r)

    dept_opportunities = get_department_dollar_opportunities(role)
    total_opportunity_dollars = get_total_identified_opportunity(role)
    largest = get_largest_opportunities(role, limit=10)

    return {
        **buckets,
        "note": (
            "Grouped from the same real, severity-ranked recommendation feed "
            "core/network_audit.py computes (session 38) -- 'revenue_opportunities' "
            "has no distinct backing category yet, shown here as an honest empty "
            "bucket rather than re-labeling an unrelated recommendation."
        ),
        "recommendation_count": audit.get("recommendation_count", 0),
        "dollar_opportunities": {
            "by_department": dept_opportunities.get("departments") if isinstance(dept_opportunities, dict) else None,
            "grand_total_monthly": total_opportunity_dollars.get("total_monthly_opportunity") if isinstance(total_opportunity_dollars, dict) else None,
            "grand_total_annualized": total_opportunity_dollars.get("total_annualized_opportunity") if isinstance(total_opportunity_dollars, dict) else None,
            "excluded_departments": total_opportunity_dollars.get("excluded_departments") if isinstance(total_opportunity_dollars, dict) else None,
            "largest_opportunities": largest.get("largest_opportunities") if isinstance(largest, dict) else None,
            "basis_notice": total_opportunity_dollars.get("basis_notice") if isinstance(total_opportunity_dollars, dict) else None,
        },
    }


def reporting(role):
    """network.pdf's "Reporting" item: formal network reporting. Benchmark Reports
    reuses benchmarks()'s department rankings. Opportunity Reports reuses
    opportunities()'s real buckets. Competitive Reports' Relative Positioning reuses
    the same percentile average; Trend Direction reuses trends()'s real per-KPI
    deltas. Executive Reports' Network Standing/Total Opportunity are real averages/
    sums; Strategic Priorities is the same recommendation feed sorted by severity.
    Market Reports and Market Movement have no backing data model -- no regional/
    OEM/demand-indicator data exists anywhere in this codebase.

    Enriched 2026-07-18 (Intelligence Network reframe, slice 7 -- Reporting), on
    top of what slices 4-6 built earlier in this same reframe, closing two of the
    four gaps this function used to flag as honest `not_yet_tracked` notes rather
    than leaving them stale:
      - `growth_forecast_report` -- was flagged "no cross-department growth-
        forecasting model exists yet." Slice 4's forecasts() now provides exactly
        that for THIS dealer's own real trend (a real linear projection compared
        against the static peer average) -- reused directly, not recomputed, with
        the same honest "not a true competitive forecast" caveat carried through.
      - `historical_trend_report` -- was flagged "no benchmark-rank history is
        stored over time." Still true for RANK history specifically (no percentile
        score has ever been snapshotted), but slice 4's real day-over-day
        DepartmentSnapshot KPI history (trends()'s department_history) is a real,
        if still sparse, historical record now -- surfaced honestly with its own
        real days_with_data count, not conflated with a claim of deep rank history.
      - `playbook_adoption_report` -- new, off slice 5's real curated library:
        real active-playbook count and a real automation-tier breakdown (0/1/3),
        the honest "how much of the network's best-practice guidance is actually
        live for this dealer today" signal.
      - `ai_advisor_usage_report` -- new, off slice 6's real (in-memory, resets on
        restart, same core/ws_manager.py-class limitation core/ai_management.py's
        own docstring already documents) call-attempt counters -- attempted/
        succeeded/fell_back/blocked, an honest usage signal for the 5 AI Advisors,
        never a fabricated adoption metric."""

    bench = benchmarks(role)
    gaps = gap_analysis(role)
    opps = opportunities(role)
    trend = trends(role)
    forecast = forecasts(role)
    playbook_lib = playbooks(role)

    department_rankings = None
    if isinstance(bench, dict) and "department_benchmarks" in bench:
        department_rankings = [
            {"department": d["department"], "percentile_rank": d["percentile_rank"]}
            for d in bench["department_benchmarks"]
        ]

    ranks = [d["percentile_rank"] for d in (department_rankings or []) if d["percentile_rank"] is not None]
    avg_percentile = round(sum(ranks) / len(ranks), 1) if ranks else None

    total_opportunity = None
    if isinstance(gaps, dict) and "all_gaps" in gaps:
        # FIXED 2026-07-18 (root-cause/revenue-impact slice): was summing raw
        # `gap` values with `gap > 0`, which mislabeled the bhph department's 3
        # lower-is-better rate KPIs (delinquency/repo/charge-off) as an
        # opportunity whenever this dealer was actually AHEAD of peers on them.
        # Now sums the real, direction-aware `opportunity_gap` (always the
        # non-negative magnitude of a genuine trailing gap) via `is_opportunity`.
        opportunity_gaps = [
            g["opportunity_gap"] for g in gaps["all_gaps"]
            if g.get("is_opportunity") and isinstance(g.get("opportunity_gap"), (int, float))
        ]
        total_opportunity = round(sum(opportunity_gaps), 2) if opportunity_gaps else 0.0

    strategic_priorities = None
    if isinstance(opps, dict):
        all_opps = []
        for key in (
            "revenue_opportunities", "cost_reduction_opportunities",
            "operational_improvements", "staffing_recommendations", "process_improvements",
        ):
            all_opps.extend(opps.get(key, []))
        all_opps.sort(key=lambda r: _SEVERITY_ORDER.get(r.get("severity"), 3))
        strategic_priorities = all_opps[:10]

    growth_forecast_report = None
    if isinstance(forecast, dict) and "closing_gaps" in forecast:
        growth_forecast_report = {
            "basis_notice": forecast.get("basis_notice"),
            "project_days": forecast.get("project_days"),
            "history_days_considered": forecast.get("history_days_considered"),
            "projectable_kpi_count": forecast.get("projectable_kpi_count"),
            "not_projectable_kpi_count": forecast.get("not_projectable_kpi_count"),
            "closing_gap_count": len(forecast.get("closing_gaps") or []),
            "widening_gap_count": len(forecast.get("widening_gaps") or []),
            "top_closing_gaps": (forecast.get("closing_gaps") or [])[:3],
            "top_widening_gaps": (forecast.get("widening_gaps") or [])[:3],
        }

    historical_trend_report = None
    if isinstance(trend, dict) and "department_history" in trend:
        dept_history = trend.get("department_history") or {}
        historical_trend_report = {
            "history_days_requested": trend.get("history_days_requested"),
            "coverage_by_department": [
                {
                    "department": dept,
                    "days_with_data": (hist or {}).get("days_with_data"),
                    "days_requested": (hist or {}).get("days_requested"),
                    "kpi_count": len((hist or {}).get("kpis") or {}),
                }
                for dept, hist in dept_history.items()
            ],
            "note": (
                "Real day-over-day KPI VALUE history now exists (core/network_trends.py) -- "
                "still NOT the same thing as benchmark-RANK history over time (no percentile "
                "score has ever been snapshotted). Coverage is honestly sparse (see "
                "days_with_data per department above) until this environment has real daily "
                "use over more calendar days -- a snapshot is only recorded the first time "
                "someone opens a department's dashboard each day (core/kpi_snapshots.py)."
            ),
        }

    playbook_adoption_report = None
    if isinstance(playbook_lib, dict) and "library" in playbook_lib:
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for entry in playbook_lib.get("library") or []:
            tier = ((entry or {}).get("automation_score") or {}).get("tier")
            if tier in tier_counts:
                tier_counts[tier] += 1
        playbook_adoption_report = {
            "playbook_count": playbook_lib.get("playbook_count"),
            "currently_active_count": playbook_lib.get("currently_active_count"),
            "automation_tier_breakdown": {
                "tier_0_no_automation_path": tier_counts[0],
                "tier_1_automatable_not_configured": tier_counts[1],
                "tier_2_reserved": tier_counts[2],
                "tier_3_already_automated": tier_counts[3],
            },
        }

    ai_advisor_usage_report = get_call_stats("network_advisors")
    ai_advisor_usage_report["note"] = (
        "In-memory call-attempt counters for the 5 AI Advisors -- resets on every server "
        "restart, same documented limitation as core/ws_manager.py's ConnectionManager "
        "(core/ai_management.py). A high 'fell_back' count in this sandbox is expected "
        "(no outbound OpenAI network access here), not a bug."
    )

    return {
        "benchmark_reports": {
            "department_rankings": department_rankings,
            "percentile_performance_avg": avg_percentile,
        },
        "opportunity_reports": {
            "revenue_potential": opps.get("revenue_opportunities") if isinstance(opps, dict) else None,
            "cost_reduction_potential": opps.get("cost_reduction_opportunities") if isinstance(opps, dict) else None,
            "operational_improvements": opps.get("operational_improvements") if isinstance(opps, dict) else None,
        },
        "competitive_reports": {
            "relative_positioning_avg_percentile": avg_percentile,
            "trend_direction": trend.get("department_trends") if isinstance(trend, dict) else None,
        },
        "executive_reports": {
            "network_standing_avg_percentile": avg_percentile,
            "total_opportunity_monthly": total_opportunity,
            "strategic_priorities": strategic_priorities,
        },
        "growth_forecast_report": growth_forecast_report,
        "historical_trend_report": historical_trend_report,
        "playbook_adoption_report": playbook_adoption_report,
        "ai_advisor_usage_report": ai_advisor_usage_report,
        "department_intelligence": _DI_GAP_NOTE,
        "not_yet_tracked": {
            "market_reports": "No regional/OEM/demand-indicator data exists anywhere in this codebase.",
            "market_movement": "No market-movement tracking exists yet.",
        },
    }
