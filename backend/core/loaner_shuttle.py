"""
core/loaner_shuttle.py -- Loaner & Shuttle Management, the third of Sam's
"FEATURES COMPLETELY MISSING" Service list (after Digital Vehicle Inspection
and the Customer-Facing Approval Center). Nothing in this codebase tracked
either capability before this module: a customer whose car is in for
service getting a loaner vehicle, or getting a ride to/from the dealership.

Three distinct real-world objects, not additive attributes bolted onto an
existing entity:

- LoanerVehicle -- a dealership-owned fleet asset, entirely separate from
  sale inventory. The existing Vehicle entity type is NXTDeal's for-sale
  stock (Price/Cost/DateSold); a loaner has none of that, it has an
  availability/maintenance lifecycle instead. Kept as its own entity type
  rather than overloading Vehicle, matching this codebase's "one entity
  type per real-world object" discipline (same reasoning AdCampaign is kept
  distinct from Campaign).

- LoanerAssignment -- a first-class, timed checkout/checkin event, not a
  dict on LoanerVehicle, since the same vehicle has many assignments over
  its life and each one needs its own odometer-out/in, fuel-out/in, and
  return-status lifecycle -- same "own lifecycle, not a dict on something
  else" reasoning DamageReport/WholesaleOffer/OperationsTask already
  established.

- ShuttleRequest -- a separate real-world event (a ride), with its own
  requested -> assigned -> en_route -> completed/cancelled lifecycle,
  independent of whether a loaner was also involved.

Both LoanerAssignment and ShuttleRequest optionally tie to a specific RO
(`ro_id`) via a plain attribute id, same convention as FieldNote/LeadTask/
Appointment/ManagerTO/DemoDrive -- not a foreign key, no parallel store --
so the RO Workspace can show "this customer's transportation" for the visit
that's actually in progress, while the underlying records also stand alone
for a customer with no RO at all (a loaner handed out ahead of a scheduled
appointment, a shuttle ride unrelated to any repair order).

get_ro_transportation_summary() is the one composed view built specifically
to back a new "Loaner & Shuttle" tab in RepairOrderWorkspaceBoard.tsx's RO
Workspace modal, same "tightly integrate into the RO" precedent DVI's
create_concerns_from_inspection() established.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import LOANER_VEHICLE, LOANER_ASSIGNMENT, SHUTTLE_REQUEST, CUSTOMER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.repair_orders import _get_ro

LOANER_STATUSES = ("available", "out", "maintenance", "out_of_service")

SHUTTLE_STATUSES = ("requested", "assigned", "en_route", "completed", "cancelled")
SHUTTLE_DIRECTIONS = ("to_dealership", "from_dealership")

_SHUTTLE_TRANSITIONS = {
    "requested": ("assigned", "en_route", "cancelled"),
    "assigned": ("en_route", "cancelled"),
    "en_route": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_customer(customer_id):
    c = ledger.get_entity(customer_id)
    if not c or c.entity_type != CUSTOMER:
        return None
    return c


def _customer_brief(customer_id):
    c = _get_customer(customer_id)
    if not c:
        return {"customer_id": customer_id, "name": None}
    return {
        "customer_id": customer_id,
        "name": f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')}".strip() or None,
    }


def _get_loaner(loaner_id):
    e = ledger.get_entity(loaner_id)
    if not e or e.entity_type != LOANER_VEHICLE:
        return None
    return e


def _get_assignment(assignment_id):
    e = ledger.get_entity(assignment_id)
    if not e or e.entity_type != LOANER_ASSIGNMENT:
        return None
    return e


def _get_shuttle(request_id):
    e = ledger.get_entity(request_id)
    if not e or e.entity_type != SHUTTLE_REQUEST:
        return None
    return e


def _loaner_brief(v):
    return {
        "loaner_id": v.id,
        "make": v.attributes.get("make"),
        "model": v.attributes.get("model"),
        "year": v.attributes.get("year"),
        "vin": v.attributes.get("vin"),
        "mileage": v.attributes.get("mileage"),
        "status": v.attributes.get("status"),
    }


def _assignment_status(a):
    if a.attributes.get("checked_in_at"):
        return "returned"
    expected = a.attributes.get("expected_return_at")
    if expected:
        try:
            dt = datetime.fromisoformat(expected)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > dt:
                return "overdue"
        except ValueError:
            pass
    return "out"


def _assignment_brief(a):
    return {
        "id": a.id,
        **a.attributes,
        "status": _assignment_status(a),
        "customer": _customer_brief(a.attributes.get("customer_id")),
    }


def _shuttle_brief(s):
    return {
        "id": s.id,
        **s.attributes,
        "customer": _customer_brief(s.attributes.get("customer_id")),
    }


# --- Loaner Fleet ---

def add_loaner_vehicle(make, model, year, vin, mileage, added_by, notes=""):
    loaner_id = id_generator.generate("LOAN")
    entity = Entity(
        id=loaner_id,
        entity_type=LOANER_VEHICLE,
        attributes={
            "make": make,
            "model": model,
            "year": year,
            "vin": vin,
            "mileage": mileage,
            "status": "available",
            "notes": notes or "",
            "added_by": added_by,
            "added_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _loaner_brief(entity)


def update_loaner_status(loaner_id, status, updated_by, notes=""):
    v = _get_loaner(loaner_id)
    if not v:
        return {"error": f"Loaner vehicle '{loaner_id}' not found"}
    if status not in LOANER_STATUSES:
        return {"error": f"status must be one of {LOANER_STATUSES}"}
    if status == "out":
        return {"error": "A loaner can only move to 'out' via checkout_loaner()"}
    if v.attributes.get("status") == "out":
        return {"error": "This loaner is currently checked out -- check it in before changing its status"}

    v.attributes["status"] = status
    if notes:
        v.attributes["notes"] = (v.attributes.get("notes") or "") + f" | {notes}"
    v.attributes["status_updated_by"] = updated_by
    v.attributes["status_updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return _loaner_brief(v)


def get_loaner_vehicle(loaner_id):
    v = _get_loaner(loaner_id)
    if not v:
        return {"error": f"Loaner vehicle '{loaner_id}' not found"}
    return {**_loaner_brief(v), "assignment_history": get_assignments_for_loaner(loaner_id)}


def list_loaner_fleet(status=None):
    fleet = [e for e in ledger.get_all().values() if e.entity_type == LOANER_VEHICLE]
    if status:
        fleet = [v for v in fleet if v.attributes.get("status") == status]
    fleet.sort(key=lambda v: v.attributes.get("added_at") or "", reverse=True)
    return {"count": len(fleet), "fleet": [_loaner_brief(v) for v in fleet]}


# --- Loaner Assignments ---

def checkout_loaner(loaner_vehicle_id, customer_id, checked_out_by, odometer_out, fuel_out="Full",
                     ro_id=None, expected_return_at=None, agreement_signed=False, notes=""):
    v = _get_loaner(loaner_vehicle_id)
    if not v:
        return {"error": f"Loaner vehicle '{loaner_vehicle_id}' not found"}
    if v.attributes.get("status") != "available":
        return {"error": f"Loaner vehicle '{loaner_vehicle_id}' is not available (status: {v.attributes.get('status')})"}

    customer = _get_customer(customer_id)
    if not customer:
        return {"error": f"Customer '{customer_id}' not found"}

    if ro_id and not _get_ro(ro_id):
        return {"error": f"Repair order '{ro_id}' not found"}

    try:
        odometer_out = int(odometer_out)
    except (TypeError, ValueError):
        return {"error": "odometer_out must be a number"}

    assignment_id = id_generator.generate("LNAS")
    entity = Entity(
        id=assignment_id,
        entity_type=LOANER_ASSIGNMENT,
        attributes={
            "loaner_vehicle_id": loaner_vehicle_id,
            "customer_id": customer_id,
            "ro_id": ro_id,
            "checked_out_by": checked_out_by,
            "checked_out_at": _now(),
            "odometer_out": odometer_out,
            "fuel_out": fuel_out,
            "expected_return_at": expected_return_at,
            "agreement_signed": bool(agreement_signed),
            "notes": notes or "",
            "checked_in_by": None,
            "checked_in_at": None,
            "odometer_in": None,
            "fuel_in": None,
            "miles_driven": None,
        },
    )
    ledger.add_entity(entity)

    v.attributes["status"] = "out"

    save_graph(GRAPH_PATH)
    return _assignment_brief(entity)


def checkin_loaner(assignment_id, checked_in_by, odometer_in, fuel_in="Full", send_to_maintenance=False, notes=""):
    a = _get_assignment(assignment_id)
    if not a:
        return {"error": f"Loaner assignment '{assignment_id}' not found"}
    if a.attributes.get("checked_in_at"):
        return {"error": f"Loaner assignment '{assignment_id}' has already been checked in"}

    try:
        odometer_in = int(odometer_in)
    except (TypeError, ValueError):
        return {"error": "odometer_in must be a number"}

    odometer_out = a.attributes.get("odometer_out") or 0
    if odometer_in < odometer_out:
        return {"error": f"odometer_in ({odometer_in}) cannot be less than odometer_out ({odometer_out})"}

    a.attributes["checked_in_by"] = checked_in_by
    a.attributes["checked_in_at"] = _now()
    a.attributes["odometer_in"] = odometer_in
    a.attributes["fuel_in"] = fuel_in
    a.attributes["miles_driven"] = odometer_in - odometer_out
    if notes:
        a.attributes["notes"] = (a.attributes.get("notes") or "") + f" | Return: {notes}"

    v = _get_loaner(a.attributes.get("loaner_vehicle_id"))
    if v:
        v.attributes["status"] = "maintenance" if send_to_maintenance else "available"
        v.attributes["mileage"] = odometer_in

    save_graph(GRAPH_PATH)
    return _assignment_brief(a)


def get_assignment(assignment_id):
    a = _get_assignment(assignment_id)
    if not a:
        return {"error": f"Loaner assignment '{assignment_id}' not found"}
    return _assignment_brief(a)


def get_assignments_for_loaner(loaner_vehicle_id):
    assignments = [
        e for e in ledger.get_all().values()
        if e.entity_type == LOANER_ASSIGNMENT and e.attributes.get("loaner_vehicle_id") == loaner_vehicle_id
    ]
    assignments.sort(key=lambda a: a.attributes.get("checked_out_at") or "", reverse=True)
    return [_assignment_brief(a) for a in assignments]


def get_assignments_for_ro(ro_id):
    assignments = [
        e for e in ledger.get_all().values()
        if e.entity_type == LOANER_ASSIGNMENT and e.attributes.get("ro_id") == ro_id
    ]
    assignments.sort(key=lambda a: a.attributes.get("checked_out_at") or "", reverse=True)
    return [_assignment_brief(a) for a in assignments]


def get_assignments_for_customer(customer_id):
    assignments = [
        e for e in ledger.get_all().values()
        if e.entity_type == LOANER_ASSIGNMENT and e.attributes.get("customer_id") == customer_id
    ]
    assignments.sort(key=lambda a: a.attributes.get("checked_out_at") or "", reverse=True)
    return [_assignment_brief(a) for a in assignments]


def get_loaner_board():
    fleet = [e for e in ledger.get_all().values() if e.entity_type == LOANER_VEHICLE]
    by_status = {s: 0 for s in LOANER_STATUSES}
    for v in fleet:
        s = v.attributes.get("status")
        if s in by_status:
            by_status[s] += 1

    active = [
        e for e in ledger.get_all().values()
        if e.entity_type == LOANER_ASSIGNMENT and not e.attributes.get("checked_in_at")
    ]
    active.sort(key=lambda a: a.attributes.get("checked_out_at") or "")
    overdue_count = sum(1 for a in active if _assignment_status(a) == "overdue")

    return {
        "total_fleet": len(fleet),
        "by_status": by_status,
        "active_assignments": [_assignment_brief(a) for a in active],
        "overdue_count": overdue_count,
    }


# --- Shuttle Requests ---

def request_shuttle(customer_id, direction, pickup_location, dropoff_location, requested_time,
                     requested_by, ro_id=None, notes=""):
    customer = _get_customer(customer_id)
    if not customer:
        return {"error": f"Customer '{customer_id}' not found"}
    if direction not in SHUTTLE_DIRECTIONS:
        return {"error": f"direction must be one of {SHUTTLE_DIRECTIONS}"}
    if ro_id and not _get_ro(ro_id):
        return {"error": f"Repair order '{ro_id}' not found"}

    request_id = id_generator.generate("SHTL")
    entity = Entity(
        id=request_id,
        entity_type=SHUTTLE_REQUEST,
        attributes={
            "customer_id": customer_id,
            "ro_id": ro_id,
            "direction": direction,
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
            "requested_time": requested_time,
            "requested_by": requested_by,
            "created_at": _now(),
            "status": "requested",
            "driver_id": None,
            "completed_at": None,
            "cancelled_reason": None,
            "notes": notes or "",
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _shuttle_brief(entity)


def assign_shuttle_driver(request_id, driver_id, updated_by):
    s = _get_shuttle(request_id)
    if not s:
        return {"error": f"Shuttle request '{request_id}' not found"}
    if s.attributes.get("status") in ("completed", "cancelled"):
        return {"error": f"Shuttle request '{request_id}' is already {s.attributes.get('status')}"}

    s.attributes["driver_id"] = driver_id
    if s.attributes.get("status") == "requested":
        s.attributes["status"] = "assigned"
    s.attributes["updated_by"] = updated_by
    s.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return _shuttle_brief(s)


def update_shuttle_status(request_id, status, updated_by, notes=""):
    s = _get_shuttle(request_id)
    if not s:
        return {"error": f"Shuttle request '{request_id}' not found"}
    if status not in SHUTTLE_STATUSES:
        return {"error": f"status must be one of {SHUTTLE_STATUSES}"}

    current = s.attributes.get("status")
    allowed = _SHUTTLE_TRANSITIONS.get(current, ())
    if status not in allowed:
        return {"error": f"Cannot move a '{current}' shuttle request to '{status}'"}

    s.attributes["status"] = status
    s.attributes["updated_by"] = updated_by
    s.attributes["updated_at"] = _now()
    if status == "completed":
        s.attributes["completed_at"] = _now()
    if status == "cancelled":
        s.attributes["cancelled_reason"] = notes or s.attributes.get("cancelled_reason")
    elif notes:
        s.attributes["notes"] = (s.attributes.get("notes") or "") + f" | {notes}"

    save_graph(GRAPH_PATH)
    return _shuttle_brief(s)


def get_shuttle_request(request_id):
    s = _get_shuttle(request_id)
    if not s:
        return {"error": f"Shuttle request '{request_id}' not found"}
    return _shuttle_brief(s)


def list_shuttle_requests(status=None):
    requests = [e for e in ledger.get_all().values() if e.entity_type == SHUTTLE_REQUEST]
    if status:
        requests = [r for r in requests if r.attributes.get("status") == status]
    requests.sort(key=lambda r: r.attributes.get("requested_time") or r.attributes.get("created_at") or "")
    return {"count": len(requests), "requests": [_shuttle_brief(r) for r in requests]}


def get_shuttle_requests_for_ro(ro_id):
    requests = [
        e for e in ledger.get_all().values()
        if e.entity_type == SHUTTLE_REQUEST and e.attributes.get("ro_id") == ro_id
    ]
    requests.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)
    return [_shuttle_brief(r) for r in requests]


def get_shuttle_queue():
    requests = [e for e in ledger.get_all().values() if e.entity_type == SHUTTLE_REQUEST]
    by_status = {s: 0 for s in SHUTTLE_STATUSES}
    for r in requests:
        s = r.attributes.get("status")
        if s in by_status:
            by_status[s] += 1

    pending = [r for r in requests if r.attributes.get("status") in ("requested", "assigned", "en_route")]
    pending.sort(key=lambda r: r.attributes.get("requested_time") or r.attributes.get("created_at") or "")

    return {
        "total": len(requests),
        "by_status": by_status,
        "pending": [_shuttle_brief(r) for r in pending],
    }


# --- Composed RO-scoped view ---

def get_ro_transportation_summary(ro_id):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    assignments = get_assignments_for_ro(ro_id)
    active_assignment = next((a for a in assignments if a["status"] in ("out", "overdue")), None)

    return {
        "ro_id": ro_id,
        "active_loaner_assignment": active_assignment,
        "assignment_history": assignments,
        "shuttle_requests": get_shuttle_requests_for_ro(ro_id),
    }
