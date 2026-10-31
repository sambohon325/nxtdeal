"""
core/operations_scheduling.py -- Operations' "Scheduling" item (session 106
follow-up #5, "keep going" autonomous continuation, fifth slice of the
Operations rebuild). Sam's spec: "Recon Scheduling, Delivery Scheduling with
automatic risk detection, Transport Scheduling."

All three reuse real, already-computed signals rather than building parallel
data models, then attach one real scheduling/mutation action to each:

  - Recon Scheduling: `core/workflow_tab_data.py`'s `operations_recon_queue()`
    already surfaces the real HEURISTIC population (unsold Used-condition
    units) recon applies to. `schedule_recon()` creates a real
    `OperationsTask` (task_type "recon_followup", already in the catalog)
    with a real `target_date` -- the scheduling field added to
    `core/operations_tasks.py` this same session specifically for this use.

  - Delivery Scheduling with automatic risk detection: the one genuinely new
    piece of logic in this module. `operations_menu.py`'s `scheduling()`
    already listed every contract/funded Deal as "delivery_calendar" but
    never checked whether a delivery was actually scheduled for any of
    them. `get_delivery_risk_board()` cross-references those real Deals
    against real, open (non-terminal) delivery-type Appointments
    (`core/appointments.py`, session 96) linked by customer_id/vehicle_id,
    and genuinely computes two risk categories: `no_delivery_scheduled` (no
    matching open delivery appointment exists at all) and `overdue` (one
    exists but its `scheduled_start` has already passed without being
    completed). `schedule_delivery()` creates the real Appointment that
    resolves the risk.

  - Transport Scheduling: `core/workflow_tab_data.py`'s
    `inventory_auction_acquisition()` already surfaces the real
    `transport_status` field on every `AuctionTransaction` (session 59), but
    nothing anywhere in this codebase had ever updated it -- read-only since
    the day it was seeded. `update_transport_status()` is the one genuinely
    new mutation capability this slice adds, same "one real new capability"
    shape as Inventory Aging's `reduce_price()`.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import DEAL, AUCTION_TRANSACTION
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.workflow_tab_data import operations_recon_queue, inventory_auction_acquisition
from core.operations_tasks import create_task
from core.appointments import create_appointment, list_appointments, _OPEN_STATUSES

TRANSPORT_STATUSES = ("at_auction_yard", "in_transit", "delivered")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_recon_schedule(role):

    recon = operations_recon_queue(role)

    return {
        "used_unsold_count": recon.get("used_unsold_count"),
        "by_lot": recon.get("by_lot"),
        "vehicles": recon.get("vehicles"),
        "note": recon.get("note"),
    }


def schedule_recon(vehicle_id, target_date, requested_by, notes=""):

    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if not target_date:
        return {"error": "target_date is required"}

    return create_task(
        task_type="recon_followup",
        detail=f"Recon scheduled for {target_date} -- {vehicle.attributes.get('Year')} "
               f"{vehicle.attributes.get('Make')} {vehicle.attributes.get('Model')}. {notes}".strip(),
        created_by=requested_by,
        priority="normal",
        owner_bucket="Lot Manager",
        linked_entity_id=vehicle_id,
        target_date=target_date,
    )


def _deals_needing_delivery():
    return [
        d for d in ledger.get_all().values()
        if d.entity_type == DEAL and d.attributes.get("status") in ("contract", "funded")
    ]


def _open_delivery_appointment_for(deal):

    customer_id = deal.attributes.get("customer_id")
    vehicle_id = deal.attributes.get("vehicle_id")

    if not customer_id:
        return None

    candidates = list_appointments(department="Sales", appointment_type="delivery", linked_entity_id=customer_id)

    # Prefer a match on both customer and vehicle if the appointment recorded one;
    # fall back to a customer-only match (an appointment created before the
    # vehicle was finalized on the Deal, still a real match).
    for a in candidates:
        if a.attributes.get("status") in _OPEN_STATUSES and (
            not vehicle_id or not a.attributes.get("vehicle_id") or a.attributes.get("vehicle_id") == vehicle_id
        ):
            return a

    return None


def get_delivery_risk_board(role):
    """Real automatic risk detection: cross-references every contract/funded
    Deal against real open delivery Appointments. Two honest risk categories
    -- no_delivery_scheduled and overdue -- never a fabricated 'at risk'
    label without a real underlying check."""

    now = _now_iso()

    on_track = []
    no_delivery_scheduled = []
    overdue = []

    for d in _deals_needing_delivery():
        brief = {
            "deal_id": d.id,
            "customer_id": d.attributes.get("customer_id"),
            "vehicle_id": d.attributes.get("vehicle_id"),
            "status": d.attributes.get("status"),
        }

        appt = _open_delivery_appointment_for(d)

        if not appt:
            no_delivery_scheduled.append(brief)
            continue

        brief["appointment_id"] = appt.id
        brief["scheduled_start"] = appt.attributes.get("scheduled_start")

        if appt.attributes.get("scheduled_start") and appt.attributes["scheduled_start"] < now:
            overdue.append(brief)
        else:
            on_track.append(brief)

    return {
        "total_pending_delivery": len(on_track) + len(no_delivery_scheduled) + len(overdue),
        "on_track": {"count": len(on_track), "deals": on_track},
        "no_delivery_scheduled": {"count": len(no_delivery_scheduled), "deals": no_delivery_scheduled},
        "overdue": {"count": len(overdue), "deals": overdue},
        "note": (
            "Risk is computed live against real Appointment records (department=Sales, "
            "appointment_type=delivery) -- 'no_delivery_scheduled' means no open delivery "
            "appointment exists for that Deal's customer/vehicle at all; 'overdue' means one "
            "exists but its scheduled time has already passed without being completed."
        ),
    }


def schedule_delivery(deal_id, scheduled_start, requested_by, assigned_to=None, notes=""):

    deal = ledger.get_entity(deal_id)
    if not deal or deal.entity_type != DEAL:
        return {"error": f"Deal '{deal_id}' not found"}

    if deal.attributes.get("status") not in ("contract", "funded"):
        return {"error": f"Deal is '{deal.attributes.get('status')}' -- delivery scheduling applies to contract/funded deals"}

    if not scheduled_start:
        return {"error": "scheduled_start is required"}

    return create_appointment(
        department="Sales",
        appointment_type="delivery",
        scheduled_start=scheduled_start,
        created_by=requested_by,
        assigned_to=assigned_to,
        customer_id=deal.attributes.get("customer_id"),
        vehicle_id=deal.attributes.get("vehicle_id"),
        notes=notes or f"Delivery for {deal_id}",
    )


def get_transport_schedule(role):

    return inventory_auction_acquisition(role)


def update_transport_status(transaction_id, new_status, updated_by):

    if new_status not in TRANSPORT_STATUSES:
        return {"error": f"new_status must be one of {list(TRANSPORT_STATUSES)}"}

    t = ledger.get_entity(transaction_id)
    if not t or t.entity_type != AUCTION_TRANSACTION:
        return {"error": f"AuctionTransaction '{transaction_id}' not found"}

    old_status = t.attributes.get("transport_status")
    t.attributes["transport_status"] = new_status
    t.attributes["transport_status_updated_by"] = updated_by
    t.attributes["transport_status_updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)

    return {
        "id": t.id,
        "vehicle_id": t.attributes.get("vehicle_id"),
        "old_status": old_status,
        "new_status": new_status,
    }
