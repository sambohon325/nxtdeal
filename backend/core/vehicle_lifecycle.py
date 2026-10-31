"""
core/vehicle_lifecycle.py -- Vehicle Lifecycle Management, the flagship build of
Operations' rebuild (session 106 follow-up). Sam's own framing, from a full
Operations spec: "Sales should manage the customer lifecycle. Operations should
manage the vehicle lifecycle... This should be one of the largest operational
modules." Vehicle already exists as the graph's core inventory entity (VIN/Year/
Make/Model/Trim/Color/Mileage/Condition/Price/Cost/StockNumber/Lot/DateSold) --
this adds the real operational layer on top of it: a lifecycle status pipeline, a
recon checklist, and vendor coordination. Same additive-attribute-on-existing-
entity convention as core/deals.py's trade_in/delivery_checklist (session
101/102) -- no new entity type, no parallel inventory copy.

Honest scope note on Acquisition Data: Vehicle has no acquisition-date/purchase-
source/buyer field anywhere in this codebase (confirmed absent, same finding
sessions 63/85 already independently made -- "no acquisition/stock-date field
exists"). The only real acquisition detail that exists at all is
core/entity_types.py's AuctionTransaction (session 59), and only for the ~25
units actually acquired at auction -- get_vehicle_lifecycle() surfaces that real
data where it exists and an honest not_yet_tracked note everywhere else, rather
than fabricate a buy date/source/buyer for the other ~475 units.

Lifecycle status default: this seed graph has no historical stage-transition
data (every vehicle was seeded as a flat row, not built up through a real intake
event stream), so a vehicle with no explicit `lifecycle_status` attribute is
given a computed default -- "Sold" if `DateSold` is set, otherwise "Front Line
Ready" (unsold seed inventory is, in reality, already listed/searchable
inventory today, not mid-recon -- defaulting it to an early pipeline stage would
be a fabricated claim about history this graph doesn't have). The moment anyone
calls update_lifecycle_status(), that computed default is replaced by a real,
stored, audited value and the vehicle genuinely starts moving through the real
pipeline from then on.

Internal messaging between departments about a specific vehicle (Sam's example:
"Sales Manager: Need this vehicle by Friday. / Recon Manager: Waiting for bumper
shipment.") deliberately reuses core/field_notes.py's existing generic
FieldNote mechanism (linked_entity_id=vehicle_id, a new "vehicle_message"
category) rather than a parallel messaging store -- see core/field_notes_api.py,
already open to any authenticated role, no new module needed for it.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entity_types import VEHICLE, AUCTION_TRANSACTION, DOCUMENT, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

LIFECYCLE_STAGES = [
    "Acquired", "In Transit", "Received", "Inspection", "Recon",
    "Photo", "Merchandising", "Front Line Ready", "Sold", "Delivered",
]

RECON_ITEMS = ("inspection", "oil_change", "tires", "body_work", "photos")

VENDOR_TYPES = ("body_shop", "detail", "paint", "glass", "other")
VENDOR_STATUSES = ("assigned", "in_progress", "complete")

# Inventory department's Master Vehicle Workspace (Sam's Inventory spec, follow-up
# to the Operations rebuild this module was originally built for): Cost Breakdown,
# Ownership, and Activity Feed. Same additive-attribute-on-Vehicle convention as
# lifecycle_status/recon_checklist/vendor_assignments above -- no new entity type,
# no parallel record.
COST_FIELDS = ("acquisition_cost", "transport_cost", "recon_cost", "floorplan_interest", "marketing_cost")

OWNERSHIP_ROLES = ("buyer", "inventory_manager", "recon_manager", "sales_manager")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def _default_status(vehicle):
    if vehicle.attributes.get("DateSold"):
        return "Sold"
    return "Front Line Ready"


def _auction_data(vehicle_id):
    for e in ledger.get_all().values():
        if e.entity_type == AUCTION_TRANSACTION and e.attributes.get("vehicle_id") == vehicle_id:
            return {
                "auction_house": e.attributes.get("auction_house"),
                "bid_amount": e.attributes.get("bid_amount"),
                "purchase_date": e.attributes.get("purchase_date"),
                "carrier": e.attributes.get("carrier"),
                "transport_status": e.attributes.get("transport_status"),
            }
    return None


def get_vehicle_lifecycle(vehicle_id):

    vehicle = _get_vehicle(vehicle_id)

    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    stored_status = vehicle.attributes.get("lifecycle_status")
    status = stored_status or _default_status(vehicle)

    checklist = dict(vehicle.attributes.get("recon_checklist") or {})
    full_checklist = {item: checklist.get(item) or {"complete": False, "notes": "", "updated_by": None, "updated_at": None} for item in RECON_ITEMS}

    vendor_assignments = list(vehicle.attributes.get("vendor_assignments") or [])

    auction = _auction_data(vehicle_id)

    acquisition = {
        "cost": vehicle.attributes.get("Cost"),
        "lot": vehicle.attributes.get("Lot"),
        "condition": vehicle.attributes.get("Condition"),
        "auction_data": auction,
    }
    if not auction:
        acquisition["not_yet_tracked"] = (
            "No acquisition-date/purchase-source/buyer field exists on this Vehicle "
            "-- only auction-acquired units (AuctionTransaction) carry real acquisition "
            "detail beyond Cost."
        )

    return {
        "vehicle_id": vehicle.id,
        "vin": vehicle.attributes.get("VIN"),
        "stock_number": vehicle.attributes.get("StockNumber"),
        "year": vehicle.attributes.get("Year"),
        "make": vehicle.attributes.get("Make"),
        "model": vehicle.attributes.get("Model"),
        "trim": vehicle.attributes.get("Trim"),
        "color": vehicle.attributes.get("Color"),
        "mileage": vehicle.attributes.get("Mileage"),
        "price": vehicle.attributes.get("Price"),
        "date_sold": vehicle.attributes.get("DateSold"),
        "lifecycle_status": status,
        "lifecycle_status_is_default": stored_status is None,
        "status_history": vehicle.attributes.get("lifecycle_status_history") or [],
        "recon_checklist": full_checklist,
        "vendor_assignments": vendor_assignments,
        "acquisition": acquisition,
        "vin_decode": vehicle.attributes.get("vin_decode"),
    }


def update_lifecycle_status(vehicle_id, new_status, updated_by):

    if new_status not in LIFECYCLE_STAGES:
        return {"error": f"new_status must be one of {LIFECYCLE_STAGES}"}

    vehicle = _get_vehicle(vehicle_id)

    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    vehicle.attributes["lifecycle_status"] = new_status
    vehicle.attributes.setdefault("lifecycle_status_history", []).append(
        {"status": new_status, "at": _now(), "by": updated_by}
    )

    # NXTDeal VIN Intelligence, Phase 3 -- the real "auto-populate" moment
    # Sam's original Phase 1 spec asked for: the instant a vehicle is marked
    # physically Received, best-effort auto-decode its VIN and backfill any
    # blank Year/Make/Model/Trim fields, rather than requiring someone to
    # remember to click Decode later on a separate screen. Deferred import
    # (core/vin_decoder.py has no dependency on this module, but this
    # codebase's own established convention -- core/loan_servicing.py's
    # get_loan_financials() -- is a deferred import at every cross-module
    # reuse point). Best-effort and non-blocking: a decode failure (bad VIN
    # format, live fetch blocked) never prevents the real lifecycle status
    # update itself from landing, and this only ever fires once, the first
    # time a vehicle reaches Received with no decode already on file.
    if new_status == "Received" and not vehicle.attributes.get("vin_decode"):
        try:
            from core.vin_decoder import apply_decode_to_vehicle
            apply_decode_to_vehicle(vehicle_id, updated_by, attempt_live=True, _skip_save=True)
        except Exception:
            pass

    save_graph(GRAPH_PATH)

    return get_vehicle_lifecycle(vehicle_id)


def update_recon_item(vehicle_id, item, complete, updated_by, notes=""):

    if item not in RECON_ITEMS:
        return {"error": f"item must be one of {list(RECON_ITEMS)}"}

    vehicle = _get_vehicle(vehicle_id)

    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    checklist = dict(vehicle.attributes.get("recon_checklist") or {})
    checklist[item] = {
        "complete": bool(complete),
        "notes": notes or "",
        "updated_by": updated_by,
        "updated_at": _now(),
    }
    vehicle.attributes["recon_checklist"] = checklist

    save_graph(GRAPH_PATH)

    return get_vehicle_lifecycle(vehicle_id)


def assign_vendor(vehicle_id, vendor_type, vendor_name, assigned_by, notes=""):
    """No real Vendor entity roster exists in this codebase (confirmed absent,
    same finding session 65's Administration menu already made -- VENDOR is a
    defined entity type with zero real records) -- vendor_name is an honest
    free-text field, not a fabricated linked Vendor record."""

    if vendor_type not in VENDOR_TYPES:
        return {"error": f"vendor_type must be one of {list(VENDOR_TYPES)}"}

    if not vendor_name or not vendor_name.strip():
        return {"error": "vendor_name is required"}

    vehicle = _get_vehicle(vehicle_id)

    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    assignment = {
        "id": id_generator.generate("VEND"),
        "vendor_type": vendor_type,
        "vendor_name": vendor_name.strip(),
        "status": "assigned",
        "notes": notes or "",
        "assigned_by": assigned_by,
        "assigned_at": _now(),
        "updated_by": None,
        "updated_at": None,
        "completed_at": None,
    }

    assignments = list(vehicle.attributes.get("vendor_assignments") or [])
    assignments.append(assignment)
    vehicle.attributes["vendor_assignments"] = assignments

    save_graph(GRAPH_PATH)

    return get_vehicle_lifecycle(vehicle_id)


def update_vendor_status(vehicle_id, assignment_id, new_status, updated_by):

    if new_status not in VENDOR_STATUSES:
        return {"error": f"new_status must be one of {list(VENDOR_STATUSES)}"}

    vehicle = _get_vehicle(vehicle_id)

    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    assignments = list(vehicle.attributes.get("vendor_assignments") or [])
    found = False

    for a in assignments:
        if a.get("id") == assignment_id:
            a["status"] = new_status
            a["updated_by"] = updated_by
            a["updated_at"] = _now()
            if new_status == "complete":
                a["completed_at"] = _now()
            found = True
            break

    if not found:
        return {"error": "Vendor assignment not found"}

    vehicle.attributes["vendor_assignments"] = assignments

    save_graph(GRAPH_PATH)

    return get_vehicle_lifecycle(vehicle_id)


def list_by_stage(stage=None, limit_per_stage=100):
    """The Vehicle Lifecycle board's real data source -- every Vehicle grouped by its
    (stored or computed-default) lifecycle_status. No filtering by sold/unsold here --
    a real board should show the whole pipeline including Sold/Delivered, the caller
    decides what to render."""

    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE]

    result = {s: [] for s in LIFECYCLE_STAGES}

    for v in vehicles:
        status = v.attributes.get("lifecycle_status") or _default_status(v)

        if stage and status != stage:
            continue

        result.setdefault(status, []).append({
            "vehicle_id": v.id,
            "vin": v.attributes.get("VIN"),
            "stock_number": v.attributes.get("StockNumber"),
            "year": v.attributes.get("Year"),
            "make": v.attributes.get("Make"),
            "model": v.attributes.get("Model"),
            "price": v.attributes.get("Price"),
        })

    for s in result:
        result[s] = result[s][:limit_per_stage]

    if stage:
        return {stage: result.get(stage, [])}

    return result


def get_cost_breakdown(vehicle_id):
    """Sam's Inventory spec: 'Cost Breakdown -- Acquisition Cost, Transport Cost,
    Recon Cost, Floorplan Interest, Marketing Cost, Total Investment. Critical for
    managers.' Vehicle only ever had one flat Cost field -- acquisition_cost
    defaults to that real value until someone explicitly overrides it (e.g. the
    real AuctionTransaction bid_amount for the ~25 auction-acquired units), the
    other four default to 0 (honestly zero, not fabricated) until a real dollar
    amount is recorded against this specific unit. total_investment is always
    computed live, never stored, so it can never drift from its components."""

    vehicle = _get_vehicle(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    stored = dict(vehicle.attributes.get("cost_breakdown") or {})

    breakdown = {}
    for field in COST_FIELDS:
        if field in stored and stored[field] is not None:
            breakdown[field] = stored[field]
        elif field == "acquisition_cost":
            breakdown[field] = vehicle.attributes.get("Cost") or 0
        else:
            breakdown[field] = 0

    try:
        total = sum(float(breakdown[f] or 0) for f in COST_FIELDS)
    except (TypeError, ValueError):
        total = None

    return {
        "vehicle_id": vehicle_id,
        "breakdown": breakdown,
        "total_investment": round(total, 2) if total is not None else None,
        "acquisition_cost_is_default": "acquisition_cost" not in stored,
        "updated_by": stored.get("_updated_by"),
        "updated_at": stored.get("_updated_at"),
    }


def update_cost_breakdown(vehicle_id, updated_by, **fields):

    vehicle = _get_vehicle(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    unknown = [f for f in fields if f not in COST_FIELDS]
    if unknown:
        return {"error": f"Unknown cost field(s) {unknown} -- must be one of {list(COST_FIELDS)}"}

    stored = dict(vehicle.attributes.get("cost_breakdown") or {})

    for field, value in fields.items():
        if value is None:
            continue
        try:
            stored[field] = float(value)
        except (TypeError, ValueError):
            return {"error": f"{field} must be a number"}

    stored["_updated_by"] = updated_by
    stored["_updated_at"] = _now()
    vehicle.attributes["cost_breakdown"] = stored

    save_graph(GRAPH_PATH)

    return get_cost_breakdown(vehicle_id)


def get_ownership(vehicle_id):
    """Sam's Inventory spec: 'Ownership -- Assign: Buyer, Inventory Manager, Recon
    Manager, Sales Manager. Who owns problems?' Stores employee IDs per role;
    new assignments require Employee entities. Existing records remain readable."""

    vehicle = _get_vehicle(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    stored = dict(vehicle.attributes.get("ownership") or {})

    return {
        "vehicle_id": vehicle_id,
        "assignments": {role: stored.get(role) for role in OWNERSHIP_ROLES},
        "updated_by": stored.get("_updated_by"),
        "updated_at": stored.get("_updated_at"),
    }


def assign_ownership(vehicle_id, updated_by, **roles):

    vehicle = _get_vehicle(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    unknown = [r for r in roles if r not in OWNERSHIP_ROLES]
    if unknown:
        return {"error": f"Unknown ownership role(s) {unknown} -- must be one of {list(OWNERSHIP_ROLES)}"}

    normalized = {}
    for role, employee_id in roles.items():
        if employee_id is None:
            continue
        if not isinstance(employee_id, str):
            return {"error": f"Enter an employee ID for {role}, or clear the assignment."}
        employee_id = employee_id.strip()
        if employee_id:
            employee = ledger.get_entity(employee_id)
            if not employee or employee.entity_type != EMPLOYEE:
                return {"error": f"Employee '{employee_id}' not found. Check the employee ID before saving."}
        normalized[role] = employee_id

    stored = dict(vehicle.attributes.get("ownership") or {})

    for role, employee_id in normalized.items():
        if employee_id is None:
            continue
        stored[role] = employee_id or None

    stored["_updated_by"] = updated_by
    stored["_updated_at"] = _now()
    vehicle.attributes["ownership"] = stored

    save_graph(GRAPH_PATH)

    return get_ownership(vehicle_id)


def get_vehicle_activity_feed(vehicle_id, limit=100):
    """Sam's Inventory spec: 'Activity Feed -- Vehicle Purchased, Transport
    Received, Inspection Completed, Recon Approved, Price Changed. Full audit
    trail.' Composed from real history already tracked across this codebase
    rather than a new parallel event log: lifecycle status changes (this
    module), recon checklist updates (this module), vendor work (this module),
    price changes (core/inventory_aging.py's price_history), and document
    approvals (core/document_workflows.py) -- every event type Sam's example
    list names already has a real source somewhere in this graph."""

    vehicle = _get_vehicle(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    events = []

    for h in vehicle.attributes.get("lifecycle_status_history") or []:
        events.append({
            "type": "lifecycle_status",
            "label": f"Status changed to {h.get('status')}",
            "at": h.get("at"),
            "by": h.get("by"),
            "notes": None,
        })

    checklist = vehicle.attributes.get("recon_checklist") or {}
    for item, entry in checklist.items():
        if entry and entry.get("updated_at"):
            events.append({
                "type": "recon_item",
                "label": f"Recon item '{item}' marked {'complete' if entry.get('complete') else 'incomplete'}",
                "at": entry.get("updated_at"),
                "by": entry.get("updated_by"),
                "notes": entry.get("notes") or None,
            })

    for v in vehicle.attributes.get("vendor_assignments") or []:
        events.append({
            "type": "vendor_assigned",
            "label": f"{v.get('vendor_type')} work assigned to {v.get('vendor_name')}",
            "at": v.get("assigned_at"),
            "by": v.get("assigned_by"),
            "notes": v.get("notes") or None,
        })
        if v.get("completed_at"):
            events.append({
                "type": "vendor_completed",
                "label": f"{v.get('vendor_type')} work completed by {v.get('vendor_name')}",
                "at": v.get("completed_at"),
                "by": v.get("updated_by"),
                "notes": None,
            })

    for p in vehicle.attributes.get("price_history") or []:
        events.append({
            "type": "price_change",
            "label": f"Price changed from ${p.get('old_price')} to ${p.get('new_price')}",
            "at": p.get("updated_at"),
            "by": p.get("updated_by"),
            "notes": p.get("reason") or None,
        })

    for d in ledger.get_all().values():
        if d.entity_type == DOCUMENT and d.attributes.get("EntityID") == vehicle_id:
            events.append({
                "type": "document_uploaded",
                "label": f"{d.attributes.get('DocumentType')} document uploaded",
                "at": d.attributes.get("CreatedAt"),
                "by": d.attributes.get("UploadedBy"),
                "notes": None,
            })
            status = d.attributes.get("approval_status")
            if status in ("approved", "rejected"):
                events.append({
                    "type": f"document_{status}",
                    "label": f"{d.attributes.get('DocumentType')} document {status}",
                    "at": d.attributes.get("approved_at") or d.attributes.get("rejected_at"),
                    "by": d.attributes.get("approved_by"),
                    "notes": None,
                })

    cost = vehicle.attributes.get("cost_breakdown") or {}
    if cost.get("_updated_at"):
        events.append({
            "type": "cost_breakdown_updated",
            "label": "Cost breakdown updated",
            "at": cost.get("_updated_at"),
            "by": cost.get("_updated_by"),
            "notes": None,
        })

    ownership = vehicle.attributes.get("ownership") or {}
    if ownership.get("_updated_at"):
        events.append({
            "type": "ownership_updated",
            "label": "Ownership assignments updated",
            "at": ownership.get("_updated_at"),
            "by": ownership.get("_updated_by"),
            "notes": None,
        })

    events = [e for e in events if e.get("at")]
    events.sort(key=lambda e: e["at"], reverse=True)

    return {"vehicle_id": vehicle_id, "count": len(events), "events": events[:limit]}


def get_vehicle_workspace(vehicle_id):
    """Sam's Inventory spec's 'Vehicle Detail Workspace': the single composed
    payload the master Inventory screen needs -- identity + lifecycle tracker +
    recon checklist + vendor coordination (all from get_vehicle_lifecycle()) plus
    Cost Breakdown, Ownership, and the Activity Feed. One call, not four, for the
    frontend's main vehicle detail view."""

    lifecycle = get_vehicle_lifecycle(vehicle_id)
    if "error" in lifecycle:
        return lifecycle

    return {
        **lifecycle,
        "cost_breakdown": get_cost_breakdown(vehicle_id),
        "ownership": get_ownership(vehicle_id),
        "activity_feed": get_vehicle_activity_feed(vehicle_id, limit=50),
    }
