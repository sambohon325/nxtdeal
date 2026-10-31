"""
core/vehicle_holds.py -- the real Reservation/Hold mechanism for Sales' Inventory item
(session 99 follow-up).

Closes a real gap: nothing in this codebase previously prevented, or even surfaced,
two salespeople desking separate Deals against the same unsold Vehicle at once -- a
Vehicle only becomes genuinely unavailable once a Deal actually funds (DateSold gets
set on it, see core/deals.py's fund_deal()). A VehicleHold is a short-lived, ordinary
graph entity -- who placed it, which vehicle, an optional linked Customer/Lead, an
expiration -- not a change to Vehicle itself, so a hold never blocks the underlying
Deal Desk workflow, it's purely an honesty/visibility layer ("someone's already
working this car") on top of it.

Expiry is computed on read (now vs. expires_at), not a background scheduler --
matches this codebase's established "compute live" convention (core/trigger_alerts.py,
core/compliance.py's run_full_scan(), etc.) rather than adding a second async
scheduler alongside core/bot_scheduler.py/core/compliance_scheduler.py.
"""

from datetime import datetime, timezone, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import VEHICLE_HOLD, VEHICLE, CUSTOMER, LEAD
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

DEFAULT_DURATION_HOURS = 24
MAX_DURATION_HOURS = 168  # 7 days -- a hold is meant to be short-lived, not a parking spot


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _is_expired(hold):
    expires_at = hold.attributes.get("expires_at")
    if not expires_at:
        return False
    try:
        dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _now() > dt


def _effective_status(hold):
    if hold.attributes.get("status") == "released":
        return "released"
    if _is_expired(hold):
        return "expired"
    return "active"


def place_hold(vehicle_id, employee_id, customer_id=None, lead_id=None, notes="", duration_hours=None):

    vehicle = ledger.get_entity(vehicle_id)

    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if vehicle.attributes.get("DateSold"):
        return {"error": f"Vehicle '{vehicle_id}' is already sold"}

    existing = get_active_hold(vehicle_id)
    if existing and existing.attributes.get("held_by") != employee_id:
        return {"error": f"Vehicle already on hold by {existing.attributes.get('held_by')} until {existing.attributes.get('expires_at')}"}

    if customer_id:
        customer = ledger.get_entity(customer_id)
        if not customer or customer.entity_type != CUSTOMER:
            return {"error": f"Customer '{customer_id}' not found"}

    if lead_id:
        lead = ledger.get_entity(lead_id)
        if not lead or lead.entity_type != LEAD:
            return {"error": f"Lead '{lead_id}' not found"}

    hours = duration_hours or DEFAULT_DURATION_HOURS
    hours = max(1, min(hours, MAX_DURATION_HOURS))

    hold_id = id_generator.generate("HOLD")
    now = _now()

    entity = Entity(
        id=hold_id,
        entity_type=VEHICLE_HOLD,
        attributes={
            "vehicle_id": vehicle_id,
            "held_by": employee_id,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "notes": notes or "",
            "status": "active",
            "placed_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=hours)).isoformat(),
            "released_at": None,
            "released_by": None,
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def release_hold(hold_id, released_by):

    hold = ledger.get_entity(hold_id)

    if not hold or hold.entity_type != VEHICLE_HOLD:
        return {"error": "Hold not found"}

    if _effective_status(hold) != "active":
        return {"error": f"Hold is already '{_effective_status(hold)}'"}

    hold.attributes["status"] = "released"
    hold.attributes["released_at"] = _now_iso()
    hold.attributes["released_by"] = released_by

    save_graph(GRAPH_PATH)

    return hold


def get_active_hold(vehicle_id):
    """The one real active (not expired, not released) hold on a vehicle, if any --
    the signal used to block a second concurrent hold and to badge inventory
    browsing/search results."""

    holds = [
        e for e in ledger.get_all().values()
        if e.entity_type == VEHICLE_HOLD and e.attributes.get("vehicle_id") == vehicle_id
    ]

    for h in holds:
        if _effective_status(h) == "active":
            return h

    return None


def list_active_holds():

    holds = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE_HOLD]

    return [h for h in holds if _effective_status(h) == "active"]


def list_my_holds(employee_id, include_inactive=False):

    holds = [
        e for e in ledger.get_all().values()
        if e.entity_type == VEHICLE_HOLD and e.attributes.get("held_by") == employee_id
    ]

    if not include_inactive:
        holds = [h for h in holds if _effective_status(h) == "active"]

    holds.sort(key=lambda h: h.attributes.get("placed_at") or "", reverse=True)

    return holds
