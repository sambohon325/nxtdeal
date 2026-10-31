"""
core/pricing_desk.py -- Inventory department's "Pricing" item (Inventory
rebuild, third slice). inventory.pdf's own framing for this item: Market
Pricing, Pricing Recommendations, Age-Based Adjustments, and Competitor
Comparisons -- all four previously honest `not_yet_tracked` gaps in
core/inventory_menu.py's pricing(), since no market/competitor data feed and
no acquisition/stock-date field exist anywhere in this codebase.

Per Sam's direct instruction (2026-07-17, session 110: "when a lack of data
is a problem, lets simply make up simulated data to accommodate it"), all
four are now SIMULATED rather than left as gap notes -- deterministically
seeded off each vehicle's own real attributes (make/model/year/trim for
market data, the vehicle's own id for listing age) so the same vehicle
always reads the same simulated figure on repeat calls rather than fresh
random noise every time, the exact precedent core/acquisitions.py's
get_market_signal() established for the Acquisitions slice. Every simulated
figure carries basis="simulated_market_data" plus an explicit disclaimer
string, surfaced as-is by the frontend rather than hidden.

The one genuinely real, structural piece: a Pricing Desk recommendation is
floored at a real 3% margin over the vehicle's real Cost (never recommends
selling at a loss), and `apply_price_recommendation()` reuses
core/inventory_aging.py's new set_price() -- a bidirectional sibling to that
module's existing reduction-only reduce_price() -- so applying a
recommendation is a real Vehicle.Price mutation with a real, append-only
price_history entry, not a simulated action.
"""

import hashlib

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.workflow_tab_data import _unsold_vehicles, _safe_float
from core.inventory_aging import _vehicle_brief, set_price as _set_price_impl

SIMULATED_BASIS = "simulated_market_data"

_DISCLAIMER_MARKET = (
    "SIMULATED market data -- no real market/competitor pricing feed exists in "
    "this system yet. Deterministically generated from this vehicle's own "
    "make/model/year/trim, so the same vehicle always reads the same simulated "
    "market position rather than fresh random noise on every call."
)

_DISCLAIMER_AGE = (
    "SIMULATED listing age -- no acquisition/stock-date field exists on Vehicle "
    "in this system yet. Deterministically generated from this vehicle's own id, "
    "so the same vehicle always reads the same simulated age rather than fresh "
    "random noise on every call."
)

_COMP_DEALER_NAMES = [
    "Metro Auto Group", "Lakeside Motors", "Capital City Ford", "Sunbelt Preowned",
    "Heritage Auto Plaza", "Crossroads Motors", "Northgate Dealers",
]


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def _seeded_int(seed_str, low, high):
    """Deterministic pseudo-random int in [low, high], seeded off seed_str --
    same convention as core/acquisitions.py's _seeded_int()."""
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest, 16) % span)


def get_market_pricing(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    seed = f"{v.attributes.get('Make')}|{v.attributes.get('Model')}|{v.attributes.get('Year')}|{v.attributes.get('Trim') or ''}"
    price = _safe_float(v.attributes.get("Price"))

    variance_pct = _seeded_int(seed + "|variance", -8, 8) / 100.0
    market_avg_price = round(price * (1 + variance_pct), 2) if price else None

    if price and market_avg_price:
        if price < market_avg_price * 0.97:
            position = "below_market"
        elif price > market_avg_price * 1.03:
            position = "above_market"
        else:
            position = "at_market"
    else:
        position = None

    return {
        "vehicle_id": vehicle_id,
        "current_price": price or None,
        "market_avg_price": market_avg_price,
        "price_position": position,
        "market_days_supply": _seeded_int(seed + "|supply", 15, 120),
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_MARKET,
    }


def get_competitor_comparisons(vehicle_id, count=4):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    seed_base = f"{v.attributes.get('Make')}|{v.attributes.get('Model')}|{v.attributes.get('Year')}"
    price = _safe_float(v.attributes.get("Price"))
    mileage = _safe_float(v.attributes.get("Mileage"))

    comps = []
    for i in range(count):
        seed = f"{seed_base}|comp{i}"
        dealer = _COMP_DEALER_NAMES[_seeded_int(seed + "|dealer", 0, len(_COMP_DEALER_NAMES) - 1)]
        price_delta_pct = _seeded_int(seed + "|price", -10, 12) / 100.0
        comp_price = round((price or 25000) * (1 + price_delta_pct), 2)
        mileage_delta = _seeded_int(seed + "|mileage", -8000, 12000)
        comp_mileage = max(0, int((mileage or 30000) + mileage_delta))
        distance = _seeded_int(seed + "|distance", 3, 85)
        comps.append({
            "dealer_name": dealer,
            "price": comp_price,
            "mileage": comp_mileage,
            "distance_miles": distance,
        })

    comps.sort(key=lambda c: c["price"])

    return {
        "vehicle_id": vehicle_id,
        "comparisons": comps,
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_MARKET,
    }


def get_age_based_adjustment(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    estimated_days = _seeded_int(f"{vehicle_id}|age", 1, 130)

    if estimated_days <= 30:
        band, adj_pct = "0-30 days", 0.0
    elif estimated_days <= 60:
        band, adj_pct = "31-60 days", -0.02
    elif estimated_days <= 90:
        band, adj_pct = "61-90 days", -0.05
    else:
        band, adj_pct = "91+ days", -0.08

    price = _safe_float(v.attributes.get("Price"))
    suggested_price = round(price * (1 + adj_pct), 2) if price else None

    return {
        "vehicle_id": vehicle_id,
        "estimated_listing_age_days": estimated_days,
        "age_band": band,
        "suggested_adjustment_pct": adj_pct,
        "current_price": price or None,
        "suggested_price": suggested_price,
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_AGE,
    }


def get_pricing_recommendation(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    market = get_market_pricing(vehicle_id)
    age = get_age_based_adjustment(vehicle_id)

    price = _safe_float(v.attributes.get("Price"))
    cost = _safe_float(v.attributes.get("Cost"))
    margin_floor = round(cost * 1.03, 2) if cost else None  # never recommend below a real 3% margin

    candidates = [c for c in [market.get("market_avg_price"), age.get("suggested_price")] if c]
    recommended_price = round(sum(candidates) / len(candidates), 2) if candidates else None

    floor_applied = False
    if recommended_price and margin_floor and recommended_price < margin_floor:
        recommended_price = margin_floor
        floor_applied = True

    return {
        "vehicle_id": vehicle_id,
        "current_price": price or None,
        "recommended_price": recommended_price,
        "margin_floor": margin_floor,
        "margin_floor_applied": floor_applied,
        "basis": SIMULATED_BASIS,
        "disclaimer": (
            "Recommendation blends SIMULATED market pricing and a SIMULATED "
            "age-based adjustment, floored at a real 3% margin over this "
            "vehicle's real Cost so it never recommends selling at a loss."
        ),
    }


def get_pricing_view(vehicle_id):
    """Composed detail view for the Pricing Desk's per-vehicle panel: real
    vehicle brief plus all three simulated signals and the blended
    recommendation, one call for the frontend."""
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    return {
        "vehicle": _vehicle_brief(v),
        "market_pricing": get_market_pricing(vehicle_id),
        "competitor_comparisons": get_competitor_comparisons(vehicle_id),
        "age_based_adjustment": get_age_based_adjustment(vehicle_id),
        "recommendation": get_pricing_recommendation(vehicle_id),
    }


def get_pricing_queue(limit=25):
    """The real, actionable worklist: unsold inventory ranked by worst real
    margin_pct first (zero-price units sort to the very top since a missing
    price is the most urgent pricing gap), each with a real recommendation
    attached. Same real population core/inventory_menu.py's pricing() item
    already flags as its 'pricing_queue' -- this is that same queue, now
    with a real action attached to each row instead of just a list."""
    unsold = _unsold_vehicles()

    def _sort_key(v):
        price = _safe_float(v.attributes.get("Price"))
        cost = _safe_float(v.attributes.get("Cost"))
        if not price:
            return -1.0  # zero-price units are the most urgent
        if not cost:
            return 0.5
        return (price - cost) / price

    ranked = sorted(unsold, key=_sort_key)[:limit]
    results = []
    for v in ranked:
        results.append({**_vehicle_brief(v), "recommendation": get_pricing_recommendation(v.id)})

    return {"count": len(results), "vehicles": results}


def apply_price_recommendation(vehicle_id, employee_id, new_price, reason=""):
    return _set_price_impl(vehicle_id, new_price, employee_id, reason=reason or "Applied Pricing Desk recommendation")
