"""
core/wholesale_desk.py -- Inventory department's "Wholesale" item (Inventory
rebuild, seventh slice). inventory.pdf's own framing: the disposition
center. Wholesale Candidates, the Auction Queue, and Title Status all
already existed (core/workflow_tab_data.py's inventory_wholesale_disposition,
session 63) -- this module is the real ACTION layer on top: Open Offers,
Sold Wholesale Units, and Fund Collection.

Same "internal tracking gap, not external data gap" call
core/lot_control.py and core/merchandising.py already made -- there's no
reason to simulate an offer or a settlement record when the real thing is
just as easy to build. Built as REAL features here.

A WholesaleOffer is a first-class entity (core/entity_types.py), not another
additive-attribute dict on Vehicle, since multiple competing offers can
exist per vehicle over time (accept one, reject or counter the rest), each
with its own status lifecycle -- same reasoning DamageReport/OperationsTask
used for the same distinction.

mark_wholesale_sold() is the real capability that closes "Sold Wholesale
Units": nothing in this codebase previously distinguished a wholesale
disposition from a retail sale -- Vehicle.DateSold alone doesn't say which.
This sets a real `disposition_channel="wholesale"` attribute alongside
DateSold, so a genuinely new real query (get_sold_wholesale_units()) can
tell the two apart. Fund Collection (record_funds_collected()) is a real,
append-only settlement record attached to that same wholesale sale.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import VEHICLE, WHOLESALE_OFFER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_tab_data import _safe_float

OFFER_STATUSES = ("pending", "accepted", "rejected", "countered", "withdrawn")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def _vehicle_brief(v):
    price = _safe_float(v.attributes.get("Price"))
    cost = _safe_float(v.attributes.get("Cost"))
    return {
        "vehicle_id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "price": price or None,
        "cost": cost or None,
    }


def _get_offer(offer_id):
    e = ledger.get_entity(offer_id)
    if not e or e.entity_type != WHOLESALE_OFFER:
        return None
    return e


# --- Open Offers (REAL) ---

def submit_offer(vehicle_id, buyer_name, offer_amount, submitted_by, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    try:
        offer_amount = float(offer_amount)
    except (TypeError, ValueError):
        return {"error": "offer_amount must be a number"}
    if offer_amount <= 0:
        return {"error": "offer_amount must be greater than 0"}

    offer_id = id_generator.generate("WOFR")
    entity = Entity(
        id=offer_id,
        entity_type=WHOLESALE_OFFER,
        attributes={
            "vehicle_id": vehicle_id,
            "buyer_name": buyer_name,
            "offer_amount": offer_amount,
            "status": "pending",
            "notes": notes,
            "submitted_by": submitted_by,
            "submitted_at": _now(),
            "decided_by": None,
            "decided_at": None,
            "counter_amount": None,
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return {"id": entity.id, **entity.attributes}


def accept_offer(offer_id, decided_by):
    offer = _get_offer(offer_id)
    if not offer:
        return {"error": f"Offer '{offer_id}' not found"}
    if offer.attributes.get("status") not in ("pending", "countered"):
        return {"error": f"Offer '{offer_id}' is not pending (status: {offer.attributes.get('status')})"}

    offer.attributes["status"] = "accepted"
    offer.attributes["decided_by"] = decided_by
    offer.attributes["decided_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": offer.id, **offer.attributes}


def reject_offer(offer_id, decided_by, notes=""):
    offer = _get_offer(offer_id)
    if not offer:
        return {"error": f"Offer '{offer_id}' not found"}
    if offer.attributes.get("status") != "pending":
        return {"error": f"Offer '{offer_id}' is not pending (status: {offer.attributes.get('status')})"}

    offer.attributes["status"] = "rejected"
    offer.attributes["decided_by"] = decided_by
    offer.attributes["decided_at"] = _now()
    if notes:
        offer.attributes["notes"] = (offer.attributes.get("notes") or "") + f" | Rejected: {notes}"
    save_graph(GRAPH_PATH)
    return {"id": offer.id, **offer.attributes}


def counter_offer(offer_id, counter_amount, decided_by):
    offer = _get_offer(offer_id)
    if not offer:
        return {"error": f"Offer '{offer_id}' not found"}
    if offer.attributes.get("status") != "pending":
        return {"error": f"Offer '{offer_id}' is not pending (status: {offer.attributes.get('status')})"}

    try:
        counter_amount = float(counter_amount)
    except (TypeError, ValueError):
        return {"error": "counter_amount must be a number"}
    if counter_amount <= 0:
        return {"error": "counter_amount must be greater than zero"}

    offer.attributes["status"] = "countered"
    offer.attributes["counter_amount"] = counter_amount
    offer.attributes["decided_by"] = decided_by
    offer.attributes["decided_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": offer.id, **offer.attributes}


def withdraw_offer(offer_id, updated_by):
    offer = _get_offer(offer_id)
    if not offer:
        return {"error": f"Offer '{offer_id}' not found"}
    if offer.attributes.get("status") not in ("pending", "countered"):
        return {"error": f"Offer '{offer_id}' cannot be withdrawn (status: {offer.attributes.get('status')})"}

    offer.attributes["status"] = "withdrawn"
    offer.attributes["decided_by"] = updated_by
    offer.attributes["decided_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"id": offer.id, **offer.attributes}


def list_offers(vehicle_id=None, status=None):
    offers = [e for e in ledger.get_all().values() if e.entity_type == WHOLESALE_OFFER]
    if vehicle_id:
        offers = [o for o in offers if o.attributes.get("vehicle_id") == vehicle_id]
    if status:
        offers = [o for o in offers if o.attributes.get("status") == status]
    offers.sort(key=lambda o: o.attributes.get("submitted_at") or "", reverse=True)
    return {"count": len(offers), "offers": [{"id": o.id, **o.attributes} for o in offers]}


# --- Sold Wholesale Units (REAL) ---

def mark_wholesale_sold(vehicle_id, buyer_name, sale_price, sold_by, offer_id=None, notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}
    if v.attributes.get("DateSold"):
        return {"error": f"Vehicle '{vehicle_id}' is already marked sold"}

    try:
        sale_price = float(sale_price)
    except (TypeError, ValueError):
        return {"error": "sale_price must be a number"}
    if sale_price <= 0:
        return {"error": "sale_price must be greater than zero"}

    # If an offer id is given it MUST belong to this vehicle — otherwise selling VEH-A while passing
    # VEH-B's offer id would accept VEH-B's offer and corrupt the offers ledger. Validate before any
    # mutation so a bad id doesn't half-commit the sale.
    offer = None
    if offer_id:
        offer = _get_offer(offer_id)
        if not offer or offer.attributes.get("vehicle_id") != vehicle_id:
            return {"error": "That offer isn't for this vehicle"}

    now = _now()
    v.attributes["DateSold"] = now
    v.attributes["disposition_channel"] = "wholesale"
    v.attributes["wholesale_sale"] = {
        "buyer_name": buyer_name,
        "sale_price": sale_price,
        "sold_by": sold_by,
        "sold_at": now,
        "offer_id": offer_id,
        "notes": notes,
        "funds_collected": None,
    }

    if offer is not None and offer.attributes.get("status") == "pending":
        offer.attributes["status"] = "accepted"
        offer.attributes["decided_by"] = sold_by
        offer.attributes["decided_at"] = now

    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "wholesale_sale": v.attributes["wholesale_sale"]}


def get_sold_wholesale_units(limit=50):
    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE and e.attributes.get("disposition_channel") == "wholesale"]
    vehicles.sort(key=lambda v: (v.attributes.get("wholesale_sale") or {}).get("sold_at") or "", reverse=True)
    results = []
    for v in vehicles[:limit]:
        results.append({**_vehicle_brief(v), "wholesale_sale": v.attributes.get("wholesale_sale")})
    return {"count": len(vehicles), "vehicles": results}


# --- Fund Collection (REAL) ---

def record_funds_collected(vehicle_id, amount, collected_by, method="", notes=""):
    v = _get_vehicle(vehicle_id)
    if not v:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    sale = v.attributes.get("wholesale_sale")
    if not sale:
        return {"error": f"Vehicle '{vehicle_id}' has no wholesale sale on file"}
    if sale.get("funds_collected"):
        return {"error": f"Funds for '{vehicle_id}' are already marked collected"}

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be a number"}
    if amount <= 0:
        return {"error": "amount must be greater than zero"}

    sale["funds_collected"] = {
        "amount": amount, "method": method, "notes": notes,
        "collected_by": collected_by, "collected_at": _now(),
    }
    v.attributes["wholesale_sale"] = sale
    save_graph(GRAPH_PATH)
    return {"vehicle_id": vehicle_id, "wholesale_sale": sale}


def get_fund_collection_status():
    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE and e.attributes.get("disposition_channel") == "wholesale"]

    awaiting = []
    collected = []
    for v in vehicles:
        sale = v.attributes.get("wholesale_sale") or {}
        entry = {**_vehicle_brief(v), "wholesale_sale": sale}
        if sale.get("funds_collected"):
            collected.append(entry)
        else:
            awaiting.append(entry)

    total_awaiting = sum(_safe_float((v["wholesale_sale"] or {}).get("sale_price")) for v in awaiting)
    total_collected = sum(_safe_float((v["wholesale_sale"] or {}).get("funds_collected", {}).get("amount")) for v in collected)

    return {
        "awaiting_collection": {"count": len(awaiting), "total_amount": round(total_awaiting, 2), "vehicles": awaiting},
        "collected": {"count": len(collected), "total_amount": round(total_collected, 2), "vehicles": collected},
    }


# --- Composed queue ---

def get_wholesale_desk_summary():
    actionable = []
    for offer in list_offers()["offers"]:
        vehicle = _get_vehicle(offer["vehicle_id"])
        if offer["status"] in ("pending", "countered", "accepted") and vehicle and not vehicle.attributes.get("DateSold"):
            actionable.append(offer)
    offers = {"count": len(actionable), "offers": actionable}
    sold = get_sold_wholesale_units()
    funds = get_fund_collection_status()

    return {
        "open_offers": offers,
        "sold_wholesale_units": sold,
        "fund_collection": funds,
    }
