"""
core/network_benchmark.py -- the Network page's cross-dealer benchmarking engine
(2026-07-13, session 38). Sam: "the network is a collection of other dealers...
applying department intelligence and its kpi reports pulled from other NXTDeal
dealers (blind labeled for anonymity) so that dealers can see area and industry
trends... The entire
idea of the network is to replace the twenty groups that depend on biased history and
industry-slanted reporting."

Reality check, scoped with Sam before building (session 38): this environment is
single-tenant -- one dealer's graph, no real second NXTDeal dealer to pull KPIs from.
Sam's explicit answer: build the REAL aggregation/percentile-ranking engine now, seeded
with a handful of clearly-labeled SIMULATED blind peer-dealer snapshots
(basis="simulated_peer_data") so the feature is visibly functional today, rather than
faking a "connected to 40 dealers" claim or shipping an empty shell.

Design note on why peer targets are FIXED, illustrative anchors rather than a multiple
of this dealer's own live number: an earlier draft of this module scaled every peer's
KPI directly off this dealer's own current value (peer = this_dealer * multiplier).
That's a real bug, not just a simplification -- it makes the percentile rank a
tautology (a dealer always beats exactly the peers whose multiplier is below 1.0,
regardless of whether this dealer is actually doing well or badly, and the rank never
moves as this dealer's real performance changes). Instead, BASELINE_PRIMARY_KPI_VALUE
below is a fixed, illustrative anchor per department's primary KPI (same "reasonable
rule-of-thumb, not sourced from a specific citation" honesty bar as
core/prediction.py's INDUSTRY_BASELINES) -- each simulated peer's primary KPI is that
fixed anchor times the peer's multiplier, entirely independent of this dealer's own
number. This dealer's percentile rank against that fixed peer set genuinely moves as
its real KPI improves or declines over time, which is the whole point of a benchmark.

A NetworkPeerSnapshot is an ordinary graph entity (same no-separate-store rule as
DepartmentSnapshot/Connection/ComplianceAlert), seeded idempotently (same convention as
core/messaging.py's seed_channels()) -- once seeded, a peer's primary-KPI target never
changes (it's a fixed anchor), while every other KPI on its card is a one-time,
proportionally-scaled snapshot taken at seed time purely so the card's numbers look
internally consistent next to the real one. The moment a real second NXTDeal dealer
connects and reports its own Department Intelligence KPIs, its NetworkPeerSnapshot rows can join (or
replace) these simulated ones with zero changes to benchmark_department()'s math, the
ACL layer, or the frontend. Deliberately never persisted via save_graph() -- seeding is
idempotent, self-healing boot-time recreation from a fixed catalog (same convention
core/knowledge_base.py's seed_articles() already established), not real user data.

Enriched 2026-07-18 (Network's "NXTDeal Intelligence Network" reframe, slice 2 --
Peer Groups + Benchmarks): Sam's own instruction this same reframe, extending session
110's Inventory-rebuild "simulate when blocked" policy: "just build it out... when a
lack of data is a problem, lets simply make up simulated data to accommodate it."
Two real additions, both keeping the disclosure requirement unchanged (every simulated
figure still carries basis="simulated_peer_data" plus an explicit description, never
presented as real cross-dealer data):

  1. PEER_POOLS -- multiple distinct, deterministically-seeded (hashlib.sha256, same
     convention core/pricing_desk.py/core/acquisitions.py already established, so
     repeat views of the same peer/KPI pair are stable, not fresh noise) simulated
     peer-pool profiles a caller can select between (OEM Peers / Local Market Peers /
     NXTDeal Elite Group -- a deliberately stronger, aspirational pool / Similar
     Revenue Stores), alongside the original "default" 4-peer set (kept, unchanged
     id format, for full backward compatibility with already-persisted
     NETPEER-DealerB/C/D/E-{department} entities). Every pool reuses the exact same
     fixed-anchor-plus-proportional-scaling math (_peer_kpis()) the original module
     already established -- only the peer LABELS and MULTIPLIERS differ per pool, not
     the underlying mechanism. Existing snapshot entities are additively backfilled
     (missing keys only, never overwriting an already-frozen value) rather than
     recreated, matching core/system_config.py's own established feature-flag
     self-heal convention -- and, since seeding is never persisted anyway (see above),
     this backfill simply re-runs at every boot.

  2. A real 6th "bhph" benchmark department -- Sam's own BHPH Benchmarks ask
     (Delinquency, Repo Rate, Recovery Rate, Yield, Charge-Offs), which doesn't map
     onto core/department_intelligence.py's 5 keys (sales/service/parts/fi/executive)
     at all. Unlike the 5 department_intelligence departments, THIS dealer's own BHPH
     KPIs are 100% REAL (compute_bhph_kpis() -- delinquency/charge-off rates off
     core/loan_servicing.py's real+SIMULATED-blended delinquency buckets, repo rate
     off core/repossessions.py's real case count, recovery rate off that module's own
     real get_recovery_stats(), yield off core/loan_accounting.py's real cash-basis
     interest income over the real outstanding balance -- the exact same real ratio
     core/readiness_scenarios.py's finance_portfolio_scenario() already established).
     Only the PEER side is simulated here (a single dedicated "bhph_industry" pool,
     industry-typical BHPH benchmark RANGES, not sourced from this dealer's own
     numbers at all -- deliberately NOT run through _peer_kpis()'s proportional-
     scaling mechanism, since delinquency/repo/recovery/yield/charge-off are
     independent real-world ratios that don't move proportionally to one another the
     way one department's profit-dollar KPIs do; each BHPH peer KPI is independently
     seeded within a stated realistic range instead). yield_pct is BHPH's primary_kpi
     (higher is better, matching this engine's existing "higher wins" percentile
     convention) -- delinquency/repo/charge-off are LOWER-is-better and are shown for
     real gap comparison only, not used to rank direction.

  3. A small set of additional real Sales/Service KPIs Sam's own spec named
     explicitly that core/department_intelligence.py's 5-KPI cards don't carry --
     Sales' Show Rate/Close Rate/Lead Response Time (Sales' Gross Per Unit/PVR is
     already gross_profit_per_unit, no duplicate needed) and Service's Hours Per RO.
     Each one reuses an already-built, already-correct real computation rather than a
     new one -- core/business_health.py's sales_health() (Show Rate/Close Rate),
     core/bdc.py's get_response_time_stats() (real speed-to-lead measurement, session
     100), and core/workflow_tab_data.py's service_mpi_summary() (Hours Per RO, via
     its own real avg_labor_hours_per_visit). Injected into the "this dealer" KPI
     dict for sales/service only (_augmented_department_kpis()) -- everything else is
     untouched compute_department() output. Service's Inspection Conversion and
     Advisor Productivity have no real, already-built signal anywhere in this
     codebase to reuse (confirmed via grep) -- reported as an honest gap in
     core/network_menu.py's benchmarks() rather than guessed at.
"""

import hashlib
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import NETWORK_PEER_SNAPSHOT
from core.department_intelligence import (
    compute_department,
    DEPARTMENTS as INTELLIGENCE_DEPARTMENTS,
    kpi as di_kpi,
)
from core.bdc import get_response_time_stats
from core.loan_servicing_api import get_portfolio_dashboard_api
from core.loan_accounting import get_loan_accounting_summary
from core.repossessions import list_cases, get_recovery_stats


SIMULATED_BASIS = "simulated_peer_data"

BHPH_DEPARTMENT_KEY = "bhph"

# ---------------------------------------------------------------------------
# Peer pools -- "default" is the original fixed 4-peer set (session 38), kept with
# its original id format for backward compatibility with already-persisted
# NETPEER-DealerB/C/D/E-{department} entities. The other 4 are new (2026-07-18,
# Peer Groups slice) -- see module docstring point 1.
# ---------------------------------------------------------------------------

DEFAULT_PEER_POOL = "default"

PEER_POOLS = {
    "default": {
        "label": "Standard Peer Group",
        "description": (
            "The original blind-labeled 4-peer benchmark set (Dealer B/C/D/E) -- a "
            "general-purpose comparison group, not filtered by any real dealer "
            "attribute (this environment has no real OEM/region/size data on any "
            "peer record to filter by)."
        ),
        "profiles": {"Dealer B": 1.15, "Dealer C": 0.90, "Dealer D": 1.02, "Dealer E": 0.75},
    },
    "oem_peers": {
        "label": "OEM Peers",
        "description": (
            "SIMULATED same-OEM franchise dealers -- illustrative of what a real "
            "OEM-filtered peer group would look like once real dealer OEM "
            "attribution exists in this network (see core/network_menu.py's "
            "peer_groups() not_yet_tracked note -- no OEM attribute exists on any "
            "real peer/dealer record today)."
        ),
        "profiles": {"OEM Peer 1": 1.08, "OEM Peer 2": 0.94, "OEM Peer 3": 1.18},
    },
    "local_market": {
        "label": "Local Market Peers",
        "description": (
            "SIMULATED dealers competing in the same regional market -- "
            "illustrative of a real geography-filtered peer group (no geography "
            "attribute exists on any real peer/dealer record today)."
        ),
        "profiles": {"Local Peer 1": 0.87, "Local Peer 2": 1.05, "Local Peer 3": 0.98},
    },
    "elite_group": {
        "label": "NXTDeal Elite Group",
        "description": (
            "SIMULATED TOP-DECILE performers -- deliberately, meaningfully stronger "
            "than the default peer set, for aspirational benchmarking ('what would "
            "it take to be elite'), not a typical-peer comparison."
        ),
        "profiles": {
            "Elite Peer 1": 1.42, "Elite Peer 2": 1.55,
            "Elite Peer 3": 1.35, "Elite Peer 4": 1.48,
        },
    },
    "similar_revenue": {
        "label": "Similar Revenue Stores",
        "description": (
            "SIMULATED dealers sized to a comparable revenue band -- illustrative "
            "of a real volume/size-filtered peer group (no monthly-volume/revenue-"
            "band attribute exists on any real peer/dealer record today)."
        ),
        "profiles": {"Revenue Peer 1": 0.96, "Revenue Peer 2": 1.04, "Revenue Peer 3": 0.91},
    },
}

# Backward-compat aliases -- unchanged names, same values as before this slice.
_PEER_PROFILES = PEER_POOLS[DEFAULT_PEER_POOL]["profiles"]
PEER_LABELS = list(_PEER_PROFILES.keys())

# The one KPI per department used to rank this dealer against its peer set -- each
# department's real headline profit/volume number, same key
# core/department_intelligence.py already computes.
PRIMARY_KPI_BY_DEPARTMENT = {
    "sales": "total_gross_profit",
    "service": "total_gross",
    "parts": "net_profit",
    "fi": "reserve_income",
    "executive": "total_gross_profit",
}

# Fixed, illustrative monthly-scale anchors for each department's primary KPI --
# reasonable rule-of-thumb figures for a mid-size independent dealership, NOT sourced
# from a specific study (same honesty bar as core/prediction.py's INDUSTRY_BASELINES).
# These exist purely so a simulated peer's target is independent of this dealer's own
# number -- see the module docstring's "Design note" above.
BASELINE_PRIMARY_KPI_VALUE = {
    "sales": 150000.0,
    "service": 80000.0,
    "parts": 20000.0,
    "fi": 60000.0,
    "executive": 300000.0,
}

DEPARTMENTS = list(INTELLIGENCE_DEPARTMENTS)

# ---------------------------------------------------------------------------
# Gap direction (2026-07-18, Gap Analysis root-cause/revenue-impact slice --
# the fix core/network_menu.py's gap_analysis() had explicitly flagged, not
# fixed, as a KNOWN LIMITATION at the end of its own basis_notice: every gap
# here is computed as peer_average - this_dealer's value, and treating a
# POSITIVE gap as "peer beats you, an opportunity to close" is correct for
# every HIGHER-is-better KPI (gross profit, close rate, units sold, etc.) but
# is backwards for a LOWER-is-better one (a lower delinquency/repo/charge-off
# rate is GOOD -- a positive gap there means this dealer's rate is already
# BELOW the peer average, i.e. ahead, not behind).
#
# LOWER_IS_BETTER_KPIS is deliberately a small, explicit (department, kpi_key)
# set, not a blanket "every percent-format KPI defaults to lower-is-better"
# rule -- most percent KPIs in this codebase (close_rate, show_rate,
# customer_pay_pct, every Executive contribution_pct) are genuinely
# higher-is-better or have no clear direction at all (contribution_pct is a
# proportion, not a performance direction). Checked against every real KPI
# format core/department_intelligence.py/this module define before writing
# this: bhph's 3 rate KPIs are the ones Sam's own reframe explicitly flagged,
# parts.obsolete_inventory_pct is unambiguously bad-when-high (unsold aging
# inventory), and sales.lead_response_time_minutes (a "number"-format KPI,
# not "percent" -- confirmed via _augmented_department_kpis() above) is
# unambiguously bad-when-high (slower speed-to-lead is worse). Every other
# KPI keeps this engine's original higher-is-better default, not guessed at.
# ---------------------------------------------------------------------------

LOWER_IS_BETTER_KPIS = {
    ("bhph", "delinquency_rate_pct"),
    ("bhph", "repo_rate_pct"),
    ("bhph", "charge_off_rate_pct"),
    ("parts", "obsolete_inventory_pct"),
    ("sales", "lead_response_time_minutes"),
}


def is_lower_better(department, kpi_key):
    return (department, kpi_key) in LOWER_IS_BETTER_KPIS


def gap_direction(department, kpi_key, gap):
    """The one shared, correct interpretation of a peer_average - this_dealer
    gap, respecting each KPI's real higher-is-better/lower-is-better
    semantic -- used by both core/network_menu.py's gap_analysis() and
    core/network_opportunity_value.py's _dollar_conversion() so the two
    systems never disagree about which gaps are real opportunities.

    Returns:
      higher_is_better: bool -- this KPI's real semantic.
      is_opportunity: bool -- True only when this dealer is genuinely
        trailing peers on this KPI (worth closing).
      direction: "ahead" | "behind" | "even" | "unknown".
      opportunity_gap: the REAL, always-non-negative magnitude of how far
        behind this dealer is when is_opportunity is True (0.0 otherwise,
        None when gap is missing) -- this is what a revenue-impact formula
        should multiply against, never the raw signed `gap` value (which is
        negative for a lower-is-better opportunity).
    """

    lower_better = is_lower_better(department, kpi_key)
    higher_is_better = not lower_better

    if not isinstance(gap, (int, float)):
        return {
            "higher_is_better": higher_is_better,
            "is_opportunity": False,
            "direction": "unknown",
            "opportunity_gap": None,
        }

    if gap == 0:
        return {
            "higher_is_better": higher_is_better,
            "is_opportunity": False,
            "direction": "even",
            "opportunity_gap": 0.0,
        }

    if lower_better:
        # gap = peer_avg - this_value. gap > 0 means this_value < peer_avg --
        # this dealer's rate is LOWER than peers, which is GOOD for a
        # lower-is-better KPI -> ahead. gap < 0 means this dealer's rate is
        # HIGHER than peers -> behind (a real opportunity to reduce it).
        is_opportunity = gap < 0
        direction = "behind" if gap < 0 else "ahead"
        opportunity_gap = round(-gap, 2) if gap < 0 else 0.0
    else:
        is_opportunity = gap > 0
        direction = "behind" if gap > 0 else "ahead"
        opportunity_gap = round(gap, 2) if gap > 0 else 0.0

    return {
        "higher_is_better": higher_is_better,
        "is_opportunity": is_opportunity,
        "direction": direction,
        "opportunity_gap": opportunity_gap,
    }


def get_bhph_outstanding_balance(role="ADMIN"):
    """This dealer's real total outstanding loan-portfolio balance
    (core/loan_servicing_api.py) -- the real denominator Gap Analysis's
    revenue-impact layer uses to turn a BHPH lower-is-better rate gap
    (delinquency/repo/charge-off) into a real one-time dollars-at-risk
    figure. Returns None if the caller's role can't reach Portfolio data."""

    portfolio = get_portfolio_dashboard_api(role, limit=0)

    if isinstance(portfolio, dict) and "error" in portfolio:
        return None

    return portfolio.get("total_outstanding_balance")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seeded_int(seed_str, low, high):
    """Same deterministic-seeding convention as core/pricing_desk.py/
    core/acquisitions.py's own _seeded_int() -- a given seed string always maps to
    the same value, not fresh random noise per call."""

    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return low + (value % (high - low + 1))


# ---------------------------------------------------------------------------
# Real additional Sales/Service KPIs (module docstring point 3) -- injected into
# compute_department()'s own real KPI dict for sales/service only, everything else
# untouched.
# ---------------------------------------------------------------------------

def _augmented_department_kpis(department, role="ADMIN"):
    """core/business_health.py and core/workflow_tab_data.py are both imported
    HERE, deferred inside the function body rather than at module top-level --
    core/business_health.py imports core/sales_menu.py, which imports
    core/workflow_tab_data.py, which imports core/network_api.py, which imports
    core/network_benchmark.py (this module) -- a real circular import at module
    load time if either were imported at the top of this file. Same deferred-
    import convention core/loan_servicing.py's get_loan_financials() already
    established for its own core/payments.py import."""

    base = compute_department(department)

    if not base:
        return None

    kpis = dict(base["kpis"])

    if department == "sales":

        from core.business_health import sales_health

        health = sales_health(role)

        show_rate = health.get("show_rate", {}).get("value") if isinstance(health, dict) else None
        close_rate = health.get("close_rate", {}).get("value") if isinstance(health, dict) else None

        if isinstance(show_rate, (int, float)):
            kpis["show_rate"] = di_kpi(
                "show_rate", "Show Rate", round(show_rate * 100, 1), "percent"
            )

        if isinstance(close_rate, (int, float)):
            kpis["close_rate"] = di_kpi(
                "close_rate", "Close Rate", round(close_rate, 1), "percent"
            )

        response = get_response_time_stats()
        avg_minutes = response.get("average_minutes") if isinstance(response, dict) else None

        if isinstance(avg_minutes, (int, float)):
            kpis["lead_response_time_minutes"] = di_kpi(
                "lead_response_time_minutes", "Lead Response Time", avg_minutes,
                "number", suffix=" min"
            )

    elif department == "service":

        from core.workflow_tab_data import service_mpi_summary

        mpi = service_mpi_summary(role)
        hours_per_ro = mpi.get("avg_labor_hours_per_visit") if isinstance(mpi, dict) else None

        if isinstance(hours_per_ro, (int, float)):
            kpis["hours_per_ro"] = di_kpi(
                "hours_per_ro", "Hours / RO", hours_per_ro, "number", suffix=" hrs"
            )

    return {**base, "kpis": kpis}


def _peer_kpis(real_kpis, department, peer_label, multiplier):
    """Builds one peer's full KPI dict: the primary KPI is the FIXED baseline anchor
    times this peer's multiplier (independent of this dealer's number, see module
    docstring); every other KPI is this dealer's real value scaled by the ratio between
    that fixed primary target and this dealer's own real primary value, so the rest of
    the peer's card looks proportionally consistent rather than being a second
    unrelated random number. Falls back to the plain multiplier if this dealer's real
    primary value is zero/missing (nothing sensible to ratio against)."""

    primary_key = PRIMARY_KPI_BY_DEPARTMENT.get(department)
    peer_primary_target = round(BASELINE_PRIMARY_KPI_VALUE.get(department, 0.0) * multiplier, 2)

    this_primary_value = real_kpis.get(primary_key, {}).get("value") if primary_key else None

    if isinstance(this_primary_value, (int, float)) and this_primary_value:
        scale_factor = peer_primary_target / this_primary_value
    else:
        scale_factor = multiplier

    scaled = {}

    for key, entry in real_kpis.items():

        value = entry.get("value")

        if key == primary_key:
            scaled_value = peer_primary_target
        elif isinstance(value, (int, float)):
            scaled_value = round(value * scale_factor, 2)
        else:
            scaled_value = value

        scaled[key] = {**entry, "value": scaled_value}

    return scaled


def _peer_snapshot_id(peer_label, department, pool_key=DEFAULT_PEER_POOL):

    if pool_key == DEFAULT_PEER_POOL:
        # Original id format, unchanged -- full backward compatibility with
        # already-persisted NETPEER-DealerB/C/D/E-{department} entities.
        return f"NETPEER-{peer_label.replace(' ', '')}-{department}"

    return f"NETPEER-{pool_key}-{peer_label.replace(' ', '')}-{department}"


def _seed_peer_snapshots_for_department(department, real_kpis):
    """The actual per-department seed/backfill work, factored out so
    benchmark_department() can seed just the ONE department it needs (reusing the
    real KPI dict it already computed) rather than re-running
    _augmented_department_kpis() a second time for every department on every single
    benchmark_department() call -- a real perf fix, since sales_health()/
    service_mpi_summary() aren't free. seed_peer_snapshots() (the full boot-time
    sweep) is just a thin loop over this per-department worker."""

    for pool_key, pool in PEER_POOLS.items():

        for peer_label, multiplier in pool["profiles"].items():

            snapshot_id = _peer_snapshot_id(peer_label, department, pool_key)
            existing = ledger.get_entity(snapshot_id)
            computed_kpis = _peer_kpis(real_kpis, department, peer_label, multiplier)

            if existing:
                stored_kpis = existing.attributes.setdefault("kpis", {})
                for key, value in computed_kpis.items():
                    if key not in stored_kpis:
                        stored_kpis[key] = value
                existing.attributes.setdefault("pool", pool_key)
                existing.attributes.setdefault("pool_label", pool["label"])
                continue

            ledger.add_entity(Entity(
                id=snapshot_id,
                entity_type=NETWORK_PEER_SNAPSHOT,
                attributes={
                    "peer_label": peer_label,
                    "department": department,
                    "pool": pool_key,
                    "pool_label": pool["label"],
                    "kpis": computed_kpis,
                    "basis": SIMULATED_BASIS,
                    "created_at": _now(),
                },
            ))


def seed_peer_snapshots():
    """Idempotent, same convention as core/messaging.py's seed_channels() -- creates
    the simulated peer NetworkPeerSnapshot entities once per (pool, peer, department)
    if they don't already exist. Safe to call on every process start; never overwrites
    an already-frozen KPI value already loaded from storage/graph.json -- a snapshot
    that already exists is only ADDITIVELY backfilled with any KPI keys it doesn't yet
    carry (e.g. this slice's new show_rate/close_rate/lead_response_time_minutes/
    hours_per_ro), same self-heal convention core/system_config.py's feature_flags
    backfill already established. Called from api/app.py at startup (a real, one-time
    boot cost -- see _seed_peer_snapshots_for_department() for why a per-request call
    doesn't pay this same cost)."""

    for department in DEPARTMENTS:

        real = _augmented_department_kpis(department)

        if not real:
            continue

        _seed_peer_snapshots_for_department(department, real["kpis"])


def _peer_snapshots_for(department, pool_key=DEFAULT_PEER_POOL):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == NETWORK_PEER_SNAPSHOT
        and e.attributes.get("department") == department
        and e.attributes.get("pool", DEFAULT_PEER_POOL) == pool_key
    ]


def get_peer_pool_catalog():
    """The real pool catalog a caller can pick from -- backs Peer Groups' pool
    selector."""

    return [
        {
            "key": key,
            "label": pool["label"],
            "description": pool["description"],
            "peer_count": len(pool["profiles"]),
            "basis": SIMULATED_BASIS,
        }
        for key, pool in PEER_POOLS.items()
    ]


def _percentile_rank(this_value, peer_values):
    """% of the peer set this dealer performs at or above -- 100 means top of the
    group, 0 means bottom. With N peers, beating k of them scores k/N*100."""

    if not peer_values:
        return None

    beaten = sum(1 for v in peer_values if this_value >= v)

    return round(beaten / len(peer_values) * 100, 1)


def benchmark_department(department, role="ADMIN", peer_pool=DEFAULT_PEER_POOL):
    """This dealer's real, CURRENT KPIs for `department`, alongside every simulated (or,
    once real dealers connect, real) peer snapshot from the selected peer_pool, plus a
    percentile rank on the department's primary KPI computed against the peers' fixed
    baseline targets -- genuinely responsive to this dealer's real performance, not a
    tautology. Returns None for an unknown department. `department="bhph"` delegates to
    benchmark_bhph() -- a real 6th department, not one of
    core/department_intelligence.py's 5 keys, see module docstring point 2."""

    if department == BHPH_DEPARTMENT_KEY:
        return benchmark_bhph(role)

    if peer_pool not in PEER_POOLS:
        peer_pool = DEFAULT_PEER_POOL

    this_dealer = _augmented_department_kpis(department, role)

    if not this_dealer:
        return None

    _seed_peer_snapshots_for_department(department, this_dealer["kpis"])

    peers = _peer_snapshots_for(department, peer_pool)
    primary_key = PRIMARY_KPI_BY_DEPARTMENT.get(department)

    this_value = this_dealer["kpis"].get(primary_key, {}).get("value", 0) if primary_key else 0

    peer_values = [
        p.attributes["kpis"].get(primary_key, {}).get("value", 0)
        for p in peers
        if primary_key
    ]

    return {
        "department": department,
        "title": this_dealer["title"],
        "primary_kpi": primary_key,
        "peer_pool": peer_pool,
        "peer_pool_label": PEER_POOLS[peer_pool]["label"],
        "peer_pool_description": PEER_POOLS[peer_pool]["description"],
        "this_dealer": {
            "label": "Your Dealership",
            "kpis": this_dealer["kpis"],
        },
        "peers": [
            {
                "label": p.attributes["peer_label"],
                "kpis": p.attributes["kpis"],
                "basis": p.attributes["basis"],
            }
            for p in sorted(peers, key=lambda p: p.attributes["peer_label"])
        ],
        "percentile_rank": _percentile_rank(this_value, peer_values),
        "basis_notice": (
            f"Peer figures shown here are SIMULATED ({PEER_POOLS[peer_pool]['label']}) "
            "-- this environment has no real second NXTDeal dealer connected yet. Real "
            "peer benchmarking activates automatically the moment another dealer joins "
            "the network and reports its own Department Intelligence KPIs the same way."
        ),
    }


def all_departments_benchmark(role="ADMIN", peer_pool=DEFAULT_PEER_POOL):
    result = [benchmark_department(d, role=role, peer_pool=peer_pool) for d in DEPARTMENTS]
    result.append(benchmark_bhph(role))
    return result


# ---------------------------------------------------------------------------
# BHPH Benchmarks (module docstring point 2) -- a real 6th department, not one of
# core/department_intelligence.py's 5 keys. This dealer's own KPIs are 100% real;
# only the peer side is SIMULATED, via its own dedicated industry-range pool rather
# than the proportional-scaling mechanism above (see docstring for why).
# ---------------------------------------------------------------------------

BHPH_PEER_POOL_KEY = "bhph_industry"
BHPH_PEER_POOL_LABEL = "BHPH Industry Peers"
BHPH_PEER_POOL_DESCRIPTION = (
    "SIMULATED industry-typical BHPH/finance-company benchmark RANGES "
    "(delinquency/repo/recovery/yield/charge-off) -- a reasonable, clearly-labeled "
    "illustrative distribution, not sourced from a specific study and not a real "
    "peer dealer (same honesty bar as core/prediction.py's INDUSTRY_BASELINES)."
)
BHPH_PEER_LABELS = ["BHPH Peer 1", "BHPH Peer 2", "BHPH Peer 3", "BHPH Peer 4"]

_BHPH_KPI_RANGES = {
    "yield_pct": (14.0, 24.0),
    "delinquency_rate_pct": (12.0, 28.0),
    "repo_rate_pct": (1.5, 6.0),
    "recovery_rate_pct": (55.0, 82.0),
    "charge_off_rate_pct": (2.0, 7.0),
}

_BHPH_KPI_LABELS = {
    "yield_pct": "Portfolio Yield",
    "delinquency_rate_pct": "Delinquency Rate",
    "repo_rate_pct": "Repo Rate",
    "recovery_rate_pct": "Recovery Rate",
    "charge_off_rate_pct": "Charge-Off Rate",
}

_BHPH_DELINQUENT_BUCKETS = ("30_day", "60_day", "90_day", "repossessed", "charged_off")


def compute_bhph_kpis(role="ADMIN"):
    """This dealer's real BHPH portfolio KPIs -- delinquency/charge-off rates off
    core/loan_servicing.py's own real-once-real-payments-exist/SIMULATED-otherwise
    delinquency buckets (same blended basis core/finance_menu.py's Portfolio
    dashboard already surfaces), repo rate off core/repossessions.py's real case
    count, recovery rate off that module's own real get_recovery_stats(), and yield
    off core/loan_accounting.py's real cash-basis interest income over the real
    outstanding balance -- the exact real ratio core/readiness_scenarios.py's
    finance_portfolio_scenario() already established. Returns None if the caller's
    role can't reach the underlying Portfolio dashboard (ADMIN/OPERATIONS/FINANCE)."""

    portfolio = get_portfolio_dashboard_api(role, limit=0)

    if isinstance(portfolio, dict) and "error" in portfolio:
        return None

    total_loans = portfolio.get("total_loans") or 0
    buckets = portfolio.get("delinquency_buckets") or {}

    delinquent_count = sum(buckets.get(b, 0) for b in _BHPH_DELINQUENT_BUCKETS)
    delinquency_rate_pct = round(delinquent_count / total_loans * 100, 2) if total_loans else 0.0
    charge_off_rate_pct = round(buckets.get("charged_off", 0) / total_loans * 100, 2) if total_loans else 0.0

    accounting = get_loan_accounting_summary()
    outstanding = portfolio.get("total_outstanding_balance") or 0.0
    interest_income = accounting.get("interest_income_recognized") or 0.0
    yield_pct = round(interest_income / outstanding * 100, 3) if outstanding else 0.0

    case_summary = list_cases()
    total_cases = case_summary.get("count", 0) if isinstance(case_summary, dict) else 0
    repo_rate_pct = round(total_cases / total_loans * 100, 2) if total_loans else 0.0

    recovery = get_recovery_stats()
    recovery_rate_pct = recovery.get("recovery_rate_pct")
    disposed_case_count = recovery.get("disposed_case_count", 0)

    kpis = {
        "yield_pct": di_kpi("yield_pct", "Portfolio Yield", yield_pct, "percent"),
        "delinquency_rate_pct": di_kpi(
            "delinquency_rate_pct", "Delinquency Rate", delinquency_rate_pct, "percent"
        ),
        "repo_rate_pct": di_kpi("repo_rate_pct", "Repo Rate", repo_rate_pct, "percent"),
        "recovery_rate_pct": di_kpi(
            "recovery_rate_pct", "Recovery Rate",
            recovery_rate_pct if recovery_rate_pct is not None else 0.0, "percent"
        ),
        "charge_off_rate_pct": di_kpi(
            "charge_off_rate_pct", "Charge-Off Rate", charge_off_rate_pct, "percent"
        ),
    }

    return {
        "department": BHPH_DEPARTMENT_KEY,
        "title": "BHPH / Loan Portfolio",
        "subtitle": "Real portfolio delinquency, repossession, recovery, and yield performance.",
        "capabilities": [
            {"title": "Delinquency Visibility", "description": "Real 30/60/90-day delinquency rate across the active loan portfolio."},
            {"title": "Repossession Rate", "description": "Real share of the portfolio that has ever generated a repossession case."},
            {"title": "Recovery Performance", "description": "Real sale-proceeds-vs-amount-owed recovery rate across every disposed unit."},
            {"title": "Portfolio Yield", "description": "Real cash-basis interest income recognized as a % of the real outstanding balance."},
        ],
        "kpis": kpis,
        "raw": {
            "total_loans": total_loans,
            "total_cases": total_cases,
            "disposed_case_count": disposed_case_count,
            "recovery_rate_pct_is_null_reason": (
                "No case has been disposed yet in this seed" if recovery_rate_pct is None else None
            ),
        },
    }


def _bhph_peer_kpis(peer_label):
    """Deliberately NOT run through _peer_kpis()'s proportional-scaling mechanism --
    delinquency/repo/recovery/yield/charge-off are independent real-world ratios that
    don't move proportionally to one another the way one department's profit-dollar
    KPIs do. Each is independently, deterministically seeded within a stated
    industry-typical range instead."""

    values = {}

    for key, (low, high) in _BHPH_KPI_RANGES.items():

        seed = f"{BHPH_PEER_POOL_KEY}|{peer_label}|{key}"
        fraction = _seeded_int(seed, 0, 1000) / 1000.0
        value = round(low + (high - low) * fraction, 2)

        values[key] = di_kpi(key, _BHPH_KPI_LABELS[key], value, "percent")

    return values


def _seed_bhph_peer_snapshots():

    for peer_label in BHPH_PEER_LABELS:

        snapshot_id = f"NETPEER-{BHPH_PEER_POOL_KEY}-{peer_label.replace(' ', '')}-{BHPH_DEPARTMENT_KEY}"
        existing = ledger.get_entity(snapshot_id)
        computed_kpis = _bhph_peer_kpis(peer_label)

        if existing:
            stored_kpis = existing.attributes.setdefault("kpis", {})
            for key, value in computed_kpis.items():
                if key not in stored_kpis:
                    stored_kpis[key] = value
            continue

        ledger.add_entity(Entity(
            id=snapshot_id,
            entity_type=NETWORK_PEER_SNAPSHOT,
            attributes={
                "peer_label": peer_label,
                "department": BHPH_DEPARTMENT_KEY,
                "pool": BHPH_PEER_POOL_KEY,
                "pool_label": BHPH_PEER_POOL_LABEL,
                "kpis": computed_kpis,
                "basis": SIMULATED_BASIS,
                "created_at": _now(),
            },
        ))


def benchmark_bhph(role="ADMIN"):
    """The BHPH Benchmarks entry -- see module docstring point 2. Returns a real
    error dict (not None) when the caller's role can't reach Portfolio data, matching
    the shape every other benchmark_department() caller already expects to handle."""

    this_dealer = compute_bhph_kpis(role)

    if not this_dealer:
        return {
            "department": BHPH_DEPARTMENT_KEY,
            "error": (
                "BHPH portfolio data is not accessible with the current role -- "
                "Admin, Operations, or Finance required (core/loan_servicing_api.py)."
            ),
        }

    _seed_bhph_peer_snapshots()

    peers = _peer_snapshots_for(BHPH_DEPARTMENT_KEY, BHPH_PEER_POOL_KEY)
    primary_key = "yield_pct"

    this_value = this_dealer["kpis"].get(primary_key, {}).get("value", 0)
    peer_values = [p.attributes["kpis"].get(primary_key, {}).get("value", 0) for p in peers]

    return {
        "department": BHPH_DEPARTMENT_KEY,
        "title": this_dealer["title"],
        "primary_kpi": primary_key,
        "primary_kpi_note": (
            "Higher Portfolio Yield is better, matching this engine's 'higher wins' "
            "percentile convention. Delinquency Rate/Repo Rate/Charge-Off Rate are "
            "LOWER-is-better and are NOT used for ranking direction -- shown for real "
            "gap comparison only."
        ),
        "peer_pool": BHPH_PEER_POOL_KEY,
        "peer_pool_label": BHPH_PEER_POOL_LABEL,
        "peer_pool_description": BHPH_PEER_POOL_DESCRIPTION,
        "this_dealer": {
            "label": "Your Dealership",
            "kpis": this_dealer["kpis"],
        },
        "peers": [
            {
                "label": p.attributes["peer_label"],
                "kpis": p.attributes["kpis"],
                "basis": p.attributes["basis"],
            }
            for p in sorted(peers, key=lambda p: p.attributes["peer_label"])
        ],
        "percentile_rank": _percentile_rank(this_value, peer_values),
        "basis_notice": (
            "Your dealership's BHPH KPIs are REAL, computed from actual portfolio "
            "data (core/loan_servicing.py/core/collections.py/core/repossessions.py/"
            "core/loan_accounting.py). Peer figures are SIMULATED industry-typical "
            "ranges (basis=simulated_peer_data), not a real second dealer -- see "
            "peer_pool_description."
        ),
        "raw_counts": this_dealer.get("raw"),
    }
