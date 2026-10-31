"""
core/parts_desk.py -- Service's "Parts" item, the fifth slice of Service's
rebuild (following RO Workflow Engine, Overview, Shop Control, and Customers,
session 111). Sam's spec: a Parts Request Queue, RO Parts Status (already
real -- every RO's own `parts_requests` list, core/repair_orders.py), Special
Order Tracking, and Inventory Recommendations.

core/service_menu.py's existing `parts()` (session 61) is real DEPARTMENT
inventory reporting (SKU count, on-hand value, category breakdown, part-sale
revenue) -- but nothing aggregated the RO-scoped `parts_requests` embedded on
individual ServiceRecords (core/repair_orders.py, this session) into a real
cross-RO work queue, and Special Order Tracking / reorder recommendations
were both honest `not_yet_tracked` gaps. This module closes both.

Parts Request Queue: every live RO's `parts_requests` entries, flattened
across the whole department with the RO/customer/vehicle context attached --
the real queue a parts counter actually works from, instead of having to
open one RO workspace at a time.

Special Order Tracking is a genuinely new internal capability (not an
external-data gap -- nothing previously tracked which part requests were
special-ordered from a vendor, or when they're expected): `mark_special_order()`
extends an existing part-request dict (same additive-field convention as
`Deal.trade_in`/`delivery_checklist`) with `vendor`/`eta`/`is_special_order`,
built on top of `core/repair_orders.py`'s existing `update_part_request_status`
mechanism rather than a parallel one.

Inventory Recommendations is REAL, not simulated -- no fabrication needed.
Part has no min/max/reorder-point field (confirmed, still an honest gap for
that literal field), but a genuine recommendation is computable from real
data already in this graph: real PartSale volume per PartNumber (velocity)
against real Part.QuantityOnHand. A part with real recent sales and zero/low
stock is a real, derived reorder signal, not a guess.
"""

from datetime import date

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD, PART, PART_SALE
from core.repair_orders import _get_ro, _now, _customer_for_record, _vehicle_for_record, _stage_of
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

LOW_STOCK_DAYS_OF_SUPPLY = 14


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _all_live_ros():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD and e.attributes.get("parts_requests")]


def _ro_brief(ro):
    """NOTE: deliberately does NOT use the key "description" -- every part
    request dict already has its own real "description" field (what part is
    needed), and a naive {**req, **brief} merge with a colliding key would
    silently clobber it with the RO's own Description (what the RO is about).
    Found and fixed live during this module's own smoke test."""
    customer = _customer_for_record(ro)
    vehicle = _vehicle_for_record(ro)
    return {
        "ro_id": ro.id,
        "service_number": ro.attributes.get("ServiceNumber"),
        "ro_description": ro.attributes.get("Description"),
        "ro_stage": _stage_of(ro),
        "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
        "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
    }


def get_parts_request_queue(status=None):
    """The real department-wide Parts Request Queue -- every live RO's
    parts_requests, flattened with RO/customer/vehicle context attached,
    optionally filtered by status."""

    entries = []
    for ro in _all_live_ros():
        brief = _ro_brief(ro)
        for req in ro.attributes.get("parts_requests") or []:
            if status and req.get("status") != status:
                continue
            entries.append({**req, **brief})

    entries.sort(key=lambda e: e.get("requested_at") or "", reverse=True)

    by_status = {}
    for ro in _all_live_ros():
        for req in ro.attributes.get("parts_requests") or []:
            by_status[req.get("status", "unknown")] = by_status.get(req.get("status", "unknown"), 0) + 1

    return {"count": len(entries), "by_status": by_status, "requests": entries}


def mark_special_order(ro_id, request_id, vendor, eta, updated_by):
    """Extends an existing part request with vendor/ETA tracking -- a real
    internal capability that didn't exist before this module (only a bare
    status enum, no vendor/timing metadata). Also sets status to 'ordered'
    if it isn't already further along, since marking something a special
    order implies it has genuinely been placed with a vendor."""

    if not vendor or not vendor.strip():
        return {"error": "vendor is required"}
    if not eta or not eta.strip():
        return {"error": "eta is required"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    requests = ro.attributes.get("parts_requests") or []
    found = False
    for r in requests:
        if r.get("id") == request_id:
            r["is_special_order"] = True
            r["vendor"] = vendor.strip()
            r["eta"] = eta.strip()
            if r.get("status") in (None, "requested"):
                r["status"] = "ordered"
            r["updated_by"] = updated_by
            r["updated_at"] = _now()
            found = True
            break

    if not found:
        return {"error": f"Part request '{request_id}' not found on this RO"}

    ro.attributes["parts_requests"] = requests
    save_graph(GRAPH_PATH)

    return next(r for r in requests if r.get("id") == request_id)


def get_special_orders():
    """Real cross-RO list of every part request that's actually been marked
    a special order (via mark_special_order above), with a real overdue
    computation off its real ETA date."""

    today = date.today()
    entries = []

    for ro in _all_live_ros():
        brief = _ro_brief(ro)
        for req in ro.attributes.get("parts_requests") or []:
            if not req.get("is_special_order"):
                continue
            days_until_eta = None
            overdue = False
            eta = req.get("eta")
            if eta:
                try:
                    days_until_eta = (date.fromisoformat(eta) - today).days
                    overdue = days_until_eta < 0 and req.get("status") != "received" and req.get("status") != "installed"
                except ValueError:
                    days_until_eta = None
            entries.append({**req, **brief, "days_until_eta": days_until_eta, "overdue": overdue})

    entries.sort(key=lambda e: (not e["overdue"], e.get("days_until_eta") if e.get("days_until_eta") is not None else 9999))

    return {"count": len(entries), "overdue_count": sum(1 for e in entries if e["overdue"]), "special_orders": entries}


def get_inventory_recommendations(limit=50):
    """Real reorder recommendations off real PartSale velocity vs. real
    Part.QuantityOnHand -- no min/max/reorder-point field exists on Part
    (still an honest gap, noted below), but a genuine signal is computable
    from data already in this graph: total real units sold per PartNumber
    over the real span since that part's earliest sale, compared against
    real on-hand quantity. Flagged 'reorder_needed' if on-hand would run out
    within LOW_STOCK_DAYS_OF_SUPPLY days at the part's own real sales
    velocity (0 on-hand with any real sales history is always flagged)."""

    parts = [e for e in ledger.get_all().values() if e.entity_type == PART]
    sales = [e for e in ledger.get_all().values() if e.entity_type == PART_SALE]

    sales_by_part_number = {}
    for s in sales:
        pn = s.attributes.get("PartNumber")
        if not pn:
            continue
        group = sales_by_part_number.setdefault(pn, {"total_units": 0, "dates": []})
        group["total_units"] += _safe_int(s.attributes.get("QuantitySold"))
        d = s.attributes.get("SaleDate")
        if d:
            group["dates"].append(d)

    today = date.today()
    recommendations = []

    for p in parts:
        pn = p.attributes.get("PartNumber")
        on_hand = _safe_int(p.attributes.get("QuantityOnHand"))
        sale_group = sales_by_part_number.get(pn)

        if not sale_group or sale_group["total_units"] == 0:
            continue  # no real sales history -- no real velocity to recommend against

        earliest_sale = min(sale_group["dates"]) if sale_group["dates"] else None
        try:
            span_days = max((today - date.fromisoformat(earliest_sale)).days, 1) if earliest_sale else None
        except ValueError:
            span_days = None

        if not span_days:
            continue

        velocity_per_day = round(sale_group["total_units"] / span_days, 4)
        days_of_supply = round(on_hand / velocity_per_day, 1) if velocity_per_day > 0 else None

        if on_hand == 0 or (days_of_supply is not None and days_of_supply <= LOW_STOCK_DAYS_OF_SUPPLY):
            recommendations.append({
                "part_id": p.id,
                "part_number": pn,
                "description": p.attributes.get("Description"),
                "category": p.attributes.get("Category"),
                "quantity_on_hand": on_hand,
                "total_units_sold": sale_group["total_units"],
                "velocity_per_day": velocity_per_day,
                "days_of_supply": days_of_supply,
                "recommendation": "Reorder now -- out of stock with real sales history" if on_hand == 0 else f"Reorder soon -- ~{days_of_supply} days of supply left at current sales velocity",
            })

    recommendations.sort(key=lambda r: (r["days_of_supply"] if r["days_of_supply"] is not None else -1))

    return {
        "count": len(recommendations),
        "recommendations": recommendations[:limit],
        "not_yet_tracked": {
            "reorder_points": "No per-part min/max/reorder-point field exists on Part yet -- these recommendations are computed live from real PartSale velocity vs. real QuantityOnHand, not a stored threshold.",
        },
    }
