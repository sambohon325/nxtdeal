"""
core/inventory_aging.py -- Inventory Aging Management actions (session 106
follow-up #4, "keep going" autonomous continuation, fourth slice of Operations'
rebuild). Sam's spec: "price reduction / wholesale review / manager review /
marketing campaign / auction assignment actions on aging bands." Backs
Operations' own "Inventory" Top Menu item (`operations_menu.py`'s `inventory()`,
itemKey "inventory", department "Operations" -- distinct from Sales' own
"Inventory" item, which is a sales-facing locator/hold/compare tool, not a
pricing-desk action layer).

Honest scope note, same finding sessions 63/85/106 already made independently:
Vehicle has no acquisition-date/stock-date field anywhere in this codebase, so
true day-based "aging" can't be computed -- `core/workflow_tab_data.py`'s
`inventory_aging_pricing_bands()` already established price-banding as the real,
honest proxy signal, and this module attaches real actions to that same real
banding rather than fabricating a days-on-lot number.

Four of the five actions reuse existing real engines rather than building
parallel ones:
  - Price Reduction: a genuine, new capability -- directly mutates Vehicle.Price
    (nothing in this codebase could actually change a vehicle's price before
    this module) and logs an additive, append-only `price_history` attribute,
    same convention as Deal's `delivery_checklist`/`trade_in`.
  - Wholesale Review / Manager Review / Auction Assignment: create a real
    `OperationsTask` via `core/operations_tasks.py` (session 106 follow-up #3,
    shipped minutes before this module) -- reusing the exact generic task
    engine built for this, not a second parallel review-queue mechanism.
    Auction Assignment is honestly scoped: no outbound-auction/lane/run entity
    exists anywhere in this codebase (AuctionTransaction, session 59, is
    acquisition-only) -- the created task is a real coordination ticket, not a
    fabricated auction-house integration.
  - Marketing Campaign: creates a real draft `inventory_ads` Campaign
    (`core/campaigns.py`, session 31) scoped to the vehicle's own make/model,
    the one campaign type actually built to target Leads interested in specific
    inventory -- plus a `marketing_campaign_tie_in` OperationsTask so the tie
    between the vehicle and the new campaign is trackable, not just a stray
    Campaign a marketer would have no way to connect back to the vehicle that
    prompted it.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.workflow_tab_data import _unsold_vehicles, _safe_float
from core.operations_tasks import create_task
from core.campaigns import create_campaign

PRICE_BANDS = [
    ("under_15k", 0, 15000),
    ("15k_25k", 15000, 25000),
    ("25k_40k", 25000, 40000),
    ("40k_plus", 40000, float("inf")),
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _band_for(price):
    for label, low, high in PRICE_BANDS:
        if low <= price < high:
            return label
    return PRICE_BANDS[-1][0]


def _vehicle_brief(v):
    price = _safe_float(v.attributes.get("Price"))
    return {
        "vehicle_id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "price": price,
        "cost": _safe_float(v.attributes.get("Cost")) or None,
        "margin_pct": (
            round(100 * (price - _safe_float(v.attributes.get("Cost"))) / price, 1)
            if price and v.attributes.get("Cost") else None
        ),
        "price_band": _band_for(price),
        "price_history_count": len(v.attributes.get("price_history") or []),
    }


def get_vehicle_aging_brief(vehicle_id):
    """Single-vehicle aging brief -- added for the Inventory department's own
    Aging Action Center surface (Inventory rebuild wishlist item, distinct
    from Operations' full-board InventoryAgingBoard.tsx). Reuses the exact
    same `_vehicle_brief()` shape the board itself already returns, so a
    vehicle's price band/margin reads identically in both places."""

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    return {
        "vehicle": _vehicle_brief(v),
        "price_history": v.attributes.get("price_history") or [],
        "note": (
            "HEURISTIC: price banding is the real signal available today -- "
            "no acquisition/stock-date field exists to compute true days-on-lot."
        ),
    }


def get_aging_board():
    """A real per-band vehicle listing -- the same PRICE_BANDS
    `inventory_aging_pricing_bands()` already established, but with the actual
    vehicles per band (not just counts/totals) so real actions can be attached
    to real vehicles."""

    by_band = {label: [] for label, _, _ in PRICE_BANDS}

    for v in _unsold_vehicles():
        brief = _vehicle_brief(v)
        by_band[brief["price_band"]].append(brief)

    for label in by_band:
        by_band[label].sort(key=lambda b: b["price"], reverse=True)

    return {
        "unsold_count": len(_unsold_vehicles()),
        "by_price_band": by_band,
        "note": (
            "HEURISTIC: Vehicle entities have no acquisition/stock-date field in this "
            "data model, so true days-on-lot aging can't be computed -- price banding "
            "is the real signal available today."
        ),
    }


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def reduce_price(vehicle_id, new_price, updated_by, reason=""):

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    try:
        new_price = float(new_price)
    except (TypeError, ValueError):
        return {"error": "new_price must be a number"}

    if new_price <= 0:
        return {"error": "new_price must be greater than 0"}

    old_price = _safe_float(v.attributes.get("Price"))

    if new_price >= old_price and old_price > 0:
        return {"error": f"new_price ({new_price}) must be lower than the current price ({old_price}) -- this action is for price REDUCTION"}

    history = v.attributes.get("price_history") or []
    history.append({
        "old_price": old_price,
        "new_price": new_price,
        "reason": reason or "",
        "updated_by": updated_by,
        "updated_at": _now(),
    })

    v.attributes["Price"] = new_price
    v.attributes["price_history"] = history

    save_graph(GRAPH_PATH)

    return {"vehicle": _vehicle_brief(v), "history": history}


def set_price(vehicle_id, new_price, updated_by, reason=""):
    """A bidirectional sibling to reduce_price() -- added for the Inventory
    department's Pricing Desk (core/pricing_desk.py, Inventory rebuild, third
    slice). reduce_price() is deliberately reduction-only (its own error
    message says so) since it backs Operations' Aging Action Center, where
    every real action is "this unit is aging, cut the price." A Pricing
    Desk recommendation can legitimately go either direction -- an
    underpriced unit sitting below a (simulated) market read might need a
    bump, not a cut -- so this function allows either, reusing the exact
    same price_history/_vehicle_brief convention rather than a parallel
    mutation path. reduce_price() itself is untouched; existing callers
    (InventoryAgingBoard.tsx) keep their reduction-only guarantee."""

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    try:
        new_price = float(new_price)
    except (TypeError, ValueError):
        return {"error": "new_price must be a number"}

    if new_price <= 0:
        return {"error": "new_price must be greater than 0"}

    old_price = _safe_float(v.attributes.get("Price"))

    history = v.attributes.get("price_history") or []
    history.append({
        "old_price": old_price,
        "new_price": new_price,
        "reason": reason or "",
        "updated_by": updated_by,
        "updated_at": _now(),
    })

    v.attributes["Price"] = new_price
    v.attributes["price_history"] = history

    save_graph(GRAPH_PATH)

    return {"vehicle": _vehicle_brief(v), "history": history}


def request_wholesale_review(vehicle_id, requested_by, notes=""):

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    brief = _vehicle_brief(v)

    return create_task(
        task_type="transfer_to_wholesale",
        detail=f"Aging-board wholesale review requested -- {brief['year']} {brief['make']} {brief['model']}, "
               f"{brief['price_band']} band. {notes}".strip(),
        created_by=requested_by,
        priority="normal",
        owner_bucket="Inventory Manager",
        linked_entity_id=vehicle_id,
        source_entity_id=f"aging:{vehicle_id}",
    )


def request_manager_review(vehicle_id, requested_by, notes=""):

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    brief = _vehicle_brief(v)

    return create_task(
        task_type="manager_review",
        detail=f"Aging-board manager review requested -- {brief['year']} {brief['make']} {brief['model']}, "
               f"{brief['price_band']} band. {notes}".strip(),
        created_by=requested_by,
        priority="high",
        owner_bucket="Inventory Manager",
        linked_entity_id=vehicle_id,
        source_entity_id=f"aging:{vehicle_id}",
    )


def request_auction_assignment(vehicle_id, requested_by, notes=""):
    """Honestly scoped: no outbound-auction/lane/run entity exists anywhere in
    this codebase (AuctionTransaction, session 59, is acquisition-only). This
    creates a real coordination ticket for a human to actually arrange the
    auction assignment -- not a fabricated auction-house integration."""

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    brief = _vehicle_brief(v)

    return create_task(
        task_type="auction_assignment",
        detail=f"Auction assignment requested -- {brief['year']} {brief['make']} {brief['model']}, "
               f"{brief['price_band']} band. No auction-house integration exists in this system -- "
               f"this ticket tracks manual coordination only. {notes}".strip(),
        created_by=requested_by,
        priority="normal",
        owner_bucket="Inventory Manager",
        linked_entity_id=vehicle_id,
        source_entity_id=f"aging:{vehicle_id}",
    )


def create_marketing_tie_in(vehicle_id, requested_by):
    """Creates a real draft inventory_ads Campaign scoped to the vehicle's own
    make/model (the one campaign type actually built to target Leads interested
    in specific inventory, core/campaigns.py session 31), plus an OperationsTask
    so the tie between vehicle and campaign is trackable rather than a stray
    Campaign a marketer has no way to connect back to the aging unit that
    prompted it."""

    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    brief = _vehicle_brief(v)
    make = v.attributes.get("Make") or ""
    model = v.attributes.get("Model") or ""

    if not make and not model:
        return {"error": "Vehicle has no Make/Model on file -- cannot scope an inventory_ads campaign"}

    campaign = create_campaign(
        "inventory_ads",
        name=f"Aging Inventory -- {brief['year']} {make} {model}".strip(),
        channel="sms",
        created_by=requested_by,
        params={"make": make, "model": model},
    )

    task = create_task(
        task_type="marketing_campaign_tie_in",
        detail=f"Draft inventory_ads campaign {campaign.id} created for {brief['year']} {make} {model} "
               f"({brief['price_band']} band) -- awaiting Marketing activation.",
        created_by=requested_by,
        priority="low",
        owner_bucket="Inventory Manager",
        linked_entity_id=vehicle_id,
        source_entity_id=f"aging:{vehicle_id}",
    )

    return {"campaign": campaign, "task": task}
