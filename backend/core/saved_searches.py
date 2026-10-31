"""Customer-owned vehicle search criteria, unrouted until identity is ready.

Saving criteria is not consent to messaging and does not enable notifications.
No matching history, price snapshots, delivery or availability is fabricated.
"""
from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from uuid import uuid4
from functools import wraps
import threading

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.customer_identity import resolve_customer as _resolve_customer
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.inventory_values import inventory_number

FIELD = "SavedVehicleSearches"
MAX_SEARCHES = 10
TEXT_FIELDS = ("make", "model", "body_style")
PRICE_FIELDS = ("min_price", "max_price")

# Shared graph persistence is synchronous. Coordinate this module's reads/edits
# in one process so failed-write rollback cannot erase another search edit.
_SEARCH_LOCK = threading.RLock()


def _serialized_search(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _SEARCH_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _criteria(value):
    if not isinstance(value, dict) or not value or set(value) - set(TEXT_FIELDS + PRICE_FIELDS):
        raise ValueError("Provide supported vehicle search criteria")
    clean = {}
    for key, item in value.items():
        if key in TEXT_FIELDS:
            if not isinstance(item, str) or not item.strip() or len(item) > 80:
                raise ValueError("Search text must contain 1 to 80 characters")
            clean[key] = item.strip()
        else:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not 0 <= item <= 100000000 or not isfinite(item):
                raise ValueError("Search prices must be finite nonnegative numbers")
            clean[key] = item
    if clean.get("min_price", 0) > clean.get("max_price", 100000000):
        raise ValueError("Minimum price must not exceed maximum price")
    return clean


def _timestamp(value):
    # Dates without offsets cannot establish an instant; do not assume a timezone.
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Saved search timestamps need repair")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Saved search timestamps need repair") from None
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Saved search timestamps need repair")
    return instant


def _records(customer):
    rows = customer.attributes.get(FIELD, [])
    if not isinstance(rows, list) or len(rows) > MAX_SEARCHES:
        raise ValueError("Saved searches need repair before they can be changed")
    result = []
    seen = set()
    observed_at = datetime.now(timezone.utc)
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not 0 < len(row["id"]) <= 128 or row["id"] in seen
                or any(not isinstance(row.get(key), str) for key in ("created_at", "updated_at"))):
            raise ValueError("Saved searches need repair before they can be changed")
        created_at = _timestamp(row["created_at"])
        updated_at = _timestamp(row["updated_at"])
        if updated_at < created_at or updated_at > observed_at:
            raise ValueError("Saved search timestamps need repair")
        seen.add(row["id"])
        result.append({"id": row["id"], "criteria": _criteria(row.get("criteria")),
                       "created_at": row["created_at"], "updated_at": row["updated_at"]})
    return result


@_serialized_search
def _load(token):
    customer_id, error = _resolve_customer(token)
    if error:
        return None, None, error
    customer = ledger.get_entity(customer_id)
    try:
        return customer, _records(customer), None
    except ValueError as exc:
        return None, None, {"error": str(exc)}


def get_saved_searches(token):
    _, rows, error = _load(token)
    return error or {"searches": rows, "count": len(rows), "delivery_enabled": False}


def _persist(customer, rows):
    present = FIELD in customer.attributes
    previous = customer.attributes.get(FIELD)
    # _load validates stored rows before writes. Public projections intentionally
    # omit metadata, but that omission must not erase it from surviving records.
    stored_by_id = {row["id"]: row for row in (previous or [])}
    customer.attributes[FIELD] = [
        {**deepcopy(stored_by_id.get(row["id"], {})), **deepcopy(row)} for row in rows
    ]
    try:
        save_graph(GRAPH_PATH)
    except Exception:
        if present:
            customer.attributes[FIELD] = previous
        else:
            customer.attributes.pop(FIELD, None)
        raise


@_serialized_search
def save_search(token, criteria, search_id=None):
    customer, rows, error = _load(token)
    if error:
        return error
    try:
        clean = _criteria(criteria)
    except ValueError as exc:
        return {"error": str(exc)}
    existing = next((row for row in rows if row["id"] == search_id), None)
    if search_id is not None and existing is None:
        return {"error": "Saved search not found"}
    if existing is None and len(rows) >= MAX_SEARCHES:
        return {"error": "Remove a saved search before adding another"}
    now = datetime.now(timezone.utc).isoformat()
    if existing is not None and _timestamp(now) < _timestamp(existing["updated_at"]):
        return {"error": "Current time precedes the saved search update; retry after clock reconciliation"}
    if existing is None:
        existing = {"id": str(uuid4()), "created_at": now}
        rows.append(existing)
    existing.update(criteria=clean, updated_at=now)
    _persist(customer, rows)
    return {"search": deepcopy(existing), "delivery_enabled": False}


@_serialized_search
def remove_search(token, search_id):
    customer, rows, error = _load(token)
    if error:
        return error
    remaining = [row for row in rows if row["id"] != search_id]
    if len(remaining) == len(rows):
        return {"error": "Saved search not found"}
    _persist(customer, remaining)
    return {"removed": True}


def preview_search_matches(token, search_id, *, offset=0, limit=100):
    """Current matching inventory references, not alerts or historical arrivals.

    Body style is not a canonical Vehicle field yet; never guess it from model.
    Price-constrained searches exclude unknown/malformed prices.
    """
    _, rows, error = _load(token)
    if error:
        return error
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        return {"error": "Use a nonnegative integer offset and a limit from 1 to 100"}
    search = next((row for row in rows if row["id"] == search_id), None)
    if search is None:
        return {"error": "Saved search not found"}
    criteria = search["criteria"]
    if "body_style" in criteria:
        return {"error": "Body style matching is not available in current inventory",
                "reason": "unsupported_inventory_field"}
    matches = []
    for vehicle in ledger.get_all().values():
        if vehicle.entity_type != VEHICLE or vehicle.attributes.get("DateSold"):
            continue
        attrs = vehicle.attributes
        if any(not isinstance(attrs.get(key.title()), str)
               or attrs[key.title()].strip().casefold() != criteria[key].casefold()
               for key in ("make", "model") if key in criteria):
            continue
        if any(key in criteria for key in PRICE_FIELDS):
            price = inventory_number(attrs.get("Price"))
            if (price is None or price < criteria.get("min_price", 0)
                    or price > criteria.get("max_price", 100000000)):
                continue
        matches.append(vehicle.id)
    matches.sort()
    # Live pages, not a frozen inventory snapshot. Inventory may change between reads.
    page = matches[offset:offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(matches) else None
    return {"vehicle_ids": page, "total_count": len(matches),
            "truncated": next_offset is not None, "next_offset": next_offset,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "delivery_enabled": False}
