"""Customer-scoped saved inventory foundation; no public routes enabled yet.

Uses revocable customer-account sessions with provider proof. Production exposure requires the
customer-verification/provider readiness gate; this module does not establish it.
Only references are persisted, while inventory content is resolved live.
"""
from functools import wraps
import threading

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.customer_identity import resolve_customer as _resolve_customer
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.inventory_values import inventory_number

FIELD = "SavedVehicleIDs"
MAX_SAVED = 100

# Same-process module coordination only; not a global graph transaction.
_SAVED_LOCK = threading.RLock()


def _serialized_saved(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _SAVED_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _ids(customer):
    values = customer.attributes.get(FIELD)
    if not isinstance(values, list):
        return []
    # Legacy malformed references must not break reads or become character IDs.
    return list(dict.fromkeys(value for value in values if _valid_id(value)))


def _valid_id(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and value.strip() == value


def _text(value):
    return value if isinstance(value, str) and 0 < len(value) <= 200 else None


@_serialized_saved
def get_saved_vehicles(token):
    customer_id, error = _resolve_customer(token)
    if error:
        return error
    customer = ledger.get_entity(customer_id)
    vehicles = []
    for vehicle_id in _ids(customer):
        vehicle = ledger.get_entity(vehicle_id)
        if not vehicle or vehicle.entity_type != VEHICLE or vehicle.attributes.get("DateSold"):
            vehicles.append({"id": vehicle_id, "available": False})
            continue
        a = vehicle.attributes
        year = inventory_number(a.get("Year"), maximum=9999)
        year = int(year) if year is not None and year >= 1000 and year == int(year) else None
        vehicles.append({
            "id": vehicle_id, "available": True,
            "year": year, "make": _text(a.get("Make")), "model": _text(a.get("Model")),
            "trim": _text(a.get("Trim")), "price": inventory_number(a.get("Price")),
            "mileage": inventory_number(a.get("Mileage")),
        })
    return {"vehicles": vehicles, "count": len(vehicles)}


def compare_saved_vehicles(token, vehicle_ids):
    """Read-only comparison of 2–4 of this customer's saved references.

    Reuse the public inventory projection and live availability rules. This is
    intentionally not routed until the customer identity boundary is ready.
    """
    result = get_saved_vehicles(token)
    if "error" in result:
        return result
    if (not isinstance(vehicle_ids, list) or not 2 <= len(vehicle_ids) <= 4
            or any(not _valid_id(value) for value in vehicle_ids)
            or len(set(vehicle_ids)) != len(vehicle_ids)):
        return {"error": "Choose two to four different saved vehicles"}
    available = {vehicle["id"]: vehicle for vehicle in result["vehicles"]}
    if any(value not in available for value in vehicle_ids):
        return {"error": "Choose vehicles from your saved list"}
    return {"vehicles": [available[value] for value in vehicle_ids], "count": len(vehicle_ids)}


@_serialized_saved
def set_saved_vehicle(token, vehicle_id, saved):
    customer_id, error = _resolve_customer(token)
    if error:
        return error
    if not _valid_id(vehicle_id) or not isinstance(saved, bool):
        return {"error": "A vehicle ID and saved boolean are required"}
    customer = ledger.get_entity(customer_id)
    if FIELD in customer.attributes:
        raw = customer.attributes[FIELD]
        # Reads may safely project legacy references, but edits must not silently
        # replace malformed data with that lossy projection.
        if (not isinstance(raw, list) or len(raw) > MAX_SAVED
                or any(not _valid_id(value) for value in raw)
                or len(set(raw)) != len(raw)):
            return {"error": "Saved vehicles need repair before they can be changed"}
    ids = _ids(customer)
    if saved:
        vehicle = ledger.get_entity(vehicle_id)
        if not vehicle or vehicle.entity_type != VEHICLE or vehicle.attributes.get("DateSold"):
            return {"error": "Vehicle is not available to save"}
        if vehicle_id in ids:
            return {"vehicle_id": vehicle_id, "saved": True}
        if len(ids) >= MAX_SAVED:
            return {"error": "Remove a saved vehicle before adding another"}
        ids.append(vehicle_id)
    else:
        if vehicle_id not in ids:
            return {"vehicle_id": vehicle_id, "saved": False}
        ids.remove(vehicle_id)
    had_value = FIELD in customer.attributes
    previous = customer.attributes.get(FIELD)
    customer.attributes[FIELD] = ids
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        if had_value:
            customer.attributes[FIELD] = previous
        else:
            customer.attributes.pop(FIELD, None)
        raise
    return {"vehicle_id": vehicle_id, "saved": saved}
