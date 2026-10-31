"""
core/inventory_overview.py -- Inventory department's "Overview" item, the
fourth Inventory slice (Inventory rebuild). inventory.pdf's own framing:
Average Days in Stock, Aged Units (30/60/90+), Inventory Turn Rate, and
Market Days Supply were all honest `not_yet_tracked` gaps in
core/inventory_menu.py's overview() -- Vehicle has no acquisition/stock-date
field anywhere in this codebase (same finding sessions 63/85/106/109 already
made), so no real day-based aging could be computed.

Per Sam's direct instruction (2026-07-17, session 110: "when a lack of data
is a problem, lets simply make up simulated data to accommodate it"), all
four are now SIMULATED -- and, critically, reuse the EXACT SAME
deterministic listing-age seed core/pricing_desk.py's
get_age_based_adjustment() already established for the Pricing slice
(`hashlib.sha256(f"{vehicle_id}|age")`), not a second, different simulated
age for the same vehicle. A vehicle's simulated age must read the same
everywhere it appears -- Pricing's age-based adjustment, this Overview
aggregate, and any future Reporting rollup -- or the simulation stops being
credible. Every simulated figure here carries basis="simulated_market_data"
plus its own disclaimer string, same convention as every other simulated
figure in this Inventory rebuild.

Frontline Ready Units is the one genuinely REAL figure closed this slice --
not simulated at all. core/vehicle_lifecycle.py's lifecycle_status (real,
with an honestly-computed default where no stage transition has ever been
recorded) already has a real "Front Line Ready" stage; this module just
counts real unsold Vehicles currently in it, something nobody had queried
this way yet.

No new routes or frontend needed -- core/report_modules.py's Overview-module
catalog engine (session 77) already turns any top-level key
core/inventory_menu.py's overview() returns into a real draggable KPI module
on the existing ReportDashboardBuilder. Enriching overview() is the whole
deliverable, same precedent session 97's Sales Reporting slice established.
"""

from core.dealeros import ledger
from core.entity_types import VEHICLE, DOCUMENT
from core.workflow_tab_data import _unsold_vehicles, _safe_float
from core.vehicle_lifecycle import LIFECYCLE_STAGES, _default_status
from core.pricing_desk import get_age_based_adjustment, get_market_pricing, SIMULATED_BASIS
from core.merchandising import get_vdp_health

_DISCLAIMER_AGING = (
    "SIMULATED -- no acquisition/stock-date field exists on Vehicle in this "
    "system yet. Built from the same deterministic per-vehicle simulated "
    "listing age core/pricing_desk.py's Age-Based Adjustment uses, so a given "
    "vehicle's simulated age reads the same in both places."
)

_DISCLAIMER_SUPPLY = (
    "SIMULATED -- averages each unsold vehicle's own simulated market-days-"
    "supply figure (see core/pricing_desk.py's Market Pricing), which is "
    "itself deterministically seeded off make/model/year/trim, not a real "
    "market/competitor inventory data feed."
)


def _lifecycle_status(v):
    return v.attributes.get("lifecycle_status") or _default_status(v)


def get_lifecycle_stage_counts():
    """Real, uncapped per-stage counts across ALL vehicles (not just unsold --
    a real command-center view should show the whole pipeline including
    Sold/Delivered). Deliberately NOT core/vehicle_lifecycle.py's
    list_by_stage(), which caps each stage's vehicle LIST at
    limit_per_stage=100 for board-rendering purposes -- that cap would
    silently undercount a stage with more than 100 real vehicles in it."""
    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE]
    counts = {s: 0 for s in LIFECYCLE_STAGES}
    for v in vehicles:
        status = _lifecycle_status(v)
        counts[status] = counts.get(status, 0) + 1
    return counts


def get_frontline_ready_count():
    """REAL, not simulated -- a genuine count of unsold Vehicles currently in
    the real 'Front Line Ready' lifecycle stage."""
    unsold = _unsold_vehicles()
    return sum(1 for v in unsold if _lifecycle_status(v) == "Front Line Ready")


def get_simulated_aging_summary():
    """Average Days in Stock + Aged Units (30/60/90+) -- both SIMULATED,
    built from the same per-vehicle simulated listing age Pricing's
    Age-Based Adjustment already computes for every unsold vehicle."""
    unsold = _unsold_vehicles()

    ages = []
    buckets = {"0-30 days": 0, "31-60 days": 0, "61-90 days": 0, "91+ days": 0}

    for v in unsold:
        adj = get_age_based_adjustment(v.id)
        if "error" in adj:
            continue
        ages.append(adj["estimated_listing_age_days"])
        buckets[adj["age_band"]] = buckets.get(adj["age_band"], 0) + 1

    avg_days = round(sum(ages) / len(ages), 1) if ages else None

    return {
        "average_days_in_stock": avg_days,
        "aged_units_by_band": buckets,
        "sample_size": len(ages),
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_AGING,
    }


def get_simulated_turn_rate(avg_days_in_stock=None):
    """Inventory Turn Rate -- SIMULATED, an annualized-turns estimate derived
    from the simulated average days in stock (365 / avg_days). If the
    average isn't supplied, computes it fresh via get_simulated_aging_summary()."""
    if avg_days_in_stock is None:
        avg_days_in_stock = get_simulated_aging_summary().get("average_days_in_stock")

    turn_rate = round(365 / avg_days_in_stock, 2) if avg_days_in_stock else None

    return {
        "annualized_turn_rate": turn_rate,
        "based_on_avg_days_in_stock": avg_days_in_stock,
        "basis": SIMULATED_BASIS,
        "disclaimer": (
            "SIMULATED -- 365 / simulated average days in stock. No real "
            "acquisition-date field exists to compute a true turn rate from "
            "actual holding periods yet."
        ),
    }


def get_simulated_market_days_supply():
    """Market Days Supply -- SIMULATED, the average of each unsold vehicle's
    own simulated market-days-supply figure (Pricing's Market Pricing)."""
    unsold = _unsold_vehicles()

    supplies = []
    for v in unsold:
        mp = get_market_pricing(v.id)
        if "error" in mp:
            continue
        supplies.append(mp["market_days_supply"])

    avg_supply = round(sum(supplies) / len(supplies), 1) if supplies else None

    return {
        "market_days_supply": avg_supply,
        "sample_size": len(supplies),
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_SUPPLY,
    }


def get_readiness_score():
    """Inventory Readiness Score -- the first of the Inventory rebuild's two
    remaining wishlist items (session 110 continued). A single 0-100
    composite grade for "how ready is this inventory," deliberately blending
    REAL signals this module and its siblings already compute for real
    (margin, merchandising completeness, title-on-file) with the two
    SIMULATED signals this arc already established (aging band, market
    position) -- reusing every per-vehicle engine verbatim rather than a
    seventh independent computation. Weighted 70% real / 30% simulated (the
    same "real floor, simulated ceiling isn't the majority of the number"
    principle core/merchandising.py's VDP Health Score established at
    65/35), so a genuinely well-run lot (real pricing/photos/titles in
    order) scores well even before any simulated market data is considered."""

    unsold = _unsold_vehicles()
    n = len(unsold)

    if n == 0:
        return {
            "score": None, "grade": None, "sample_size": 0, "components": {},
            "basis": "mixed", "disclaimer": "No unsold inventory to score.",
        }

    title_docs_by_vehicle = {
        doc.attributes.get("EntityID")
        for doc in ledger.get_all().values()
        if doc.entity_type == DOCUMENT
        and doc.attributes.get("EntityType") == VEHICLE
        and doc.attributes.get("DocumentType") == "Title"
    }

    margin_ok = merch_ok = title_ok = aging_ok = market_ok = 0

    for v in unsold:
        price = _safe_float(v.attributes.get("Price"))
        cost = _safe_float(v.attributes.get("Cost"))
        if price and cost and price > cost:
            margin_ok += 1

        vdp = get_vdp_health(v.id)
        if isinstance(vdp, dict) and "error" not in vdp and vdp.get("has_photos") and vdp.get("has_description"):
            merch_ok += 1

        if v.id in title_docs_by_vehicle:
            title_ok += 1

        adj = get_age_based_adjustment(v.id)
        if isinstance(adj, dict) and "error" not in adj and adj.get("age_band") != "91+ days":
            aging_ok += 1

        mp = get_market_pricing(v.id)
        if isinstance(mp, dict) and "error" not in mp and mp.get("price_position") in ("at_market", "below_market"):
            market_ok += 1

    def pct(x):
        return round(100 * x / n, 1)

    margin_pct, merch_pct, title_pct = pct(margin_ok), pct(merch_ok), pct(title_ok)
    aging_pct, market_pct = pct(aging_ok), pct(market_ok)

    WEIGHTS = {
        "margin_health": 25, "merchandising_health": 25, "title_health": 20,
        "aging_health": 15, "market_position_health": 15,
    }

    score = round(
        margin_pct * WEIGHTS["margin_health"] / 100
        + merch_pct * WEIGHTS["merchandising_health"] / 100
        + title_pct * WEIGHTS["title_health"] / 100
        + aging_pct * WEIGHTS["aging_health"] / 100
        + market_pct * WEIGHTS["market_position_health"] / 100,
        1,
    )

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "sample_size": n,
        "components": {
            "margin_health": {
                "pct": margin_pct, "weight": WEIGHTS["margin_health"], "basis": "real",
                "description": "Share of unsold units priced above real Cost.",
            },
            "merchandising_health": {
                "pct": merch_pct, "weight": WEIGHTS["merchandising_health"], "basis": "real",
                "description": "Share of unsold units with a real photo AND a real description on file.",
            },
            "title_health": {
                "pct": title_pct, "weight": WEIGHTS["title_health"], "basis": "real",
                "description": "Share of unsold units with a real Title document on file.",
            },
            "aging_health": {
                "pct": aging_pct, "weight": WEIGHTS["aging_health"], "basis": SIMULATED_BASIS,
                "description": "Share of unsold units NOT in the simulated 91+ day aging band.",
            },
            "market_position_health": {
                "pct": market_pct, "weight": WEIGHTS["market_position_health"], "basis": SIMULATED_BASIS,
                "description": "Share of unsold units priced at or below their simulated market comp.",
            },
        },
        "basis": "mixed",
        "disclaimer": (
            "A weighted composite -- 70% real signals (margin/merchandising/title "
            "on file), 30% simulated signals (aging band + market position, see "
            "Pricing Desk). Not a single ground-truth number -- a real+simulated "
            "blend for at-a-glance inventory health."
        ),
    }


def get_inventory_overview_enrichment():
    """One composed call for core/inventory_menu.py's overview() -- real
    lifecycle-stage counts + frontline-ready count, plus the three simulated
    aggregates, computed once and shared (the turn rate reuses the aging
    summary's own average rather than recomputing it)."""
    aging = get_simulated_aging_summary()
    turn_rate = get_simulated_turn_rate(avg_days_in_stock=aging.get("average_days_in_stock"))
    supply = get_simulated_market_days_supply()

    return {
        "lifecycle_stage_counts": get_lifecycle_stage_counts(),
        "frontline_ready_units": get_frontline_ready_count(),
        "aging_summary": aging,
        "turn_rate": turn_rate,
        "market_days_supply": supply,
        "readiness_score": get_readiness_score(),
    }
