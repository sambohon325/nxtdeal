"""
core/delivery_fulfillment.py -- NXTDeal Home Delivery + Try Before You Buy (Digital Retail
slice DR-6, 2026-07-24). Sam's spec adds two Operations enhancements to the self-service
journey's tail:

  * Home Delivery -- delivery TYPES (store pickup / home delivery / third-party), with a real
    driver, vehicle, customer and time window, and automatic status updates. Before this, the
    only delivery primitive was a store-side calendar slot (an Appointment of type "delivery"
    via core/operations_scheduling.py) -- no mode, address, driver or status timeline.

  * Try Before You Buy -- a dealer-configurable trial (e.g. 24/48h, 100/250mi) with a real
    workflow: identity verification -> insurance verification -> deposit -> vehicle release ->
    keep/return decision, and a return workflow inspection -> reconditioning -> inventory
    reinstatement. Modeled on core/demo_drive.py's out/return + odometer lifecycle, but with
    the deposit + insurance + identity gates the spec calls for.

HONESTY POSTURE (the platform convention): there is no real SMS/email/push gateway, no real
payment gateway and no DMV/insurance API in this sandbox, so status notifications, the deposit,
and the insurance check are HONESTLY SIMULATED -- real state transitions with a clear
`simulated` marker, never a fabricated real-world side effect. The identity gate reuses the
REAL NXTDeal Verify tier (core/dealeros_verify.py) when a verification is supplied.
"""

from datetime import datetime, timezone, timedelta

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import (
    DELIVERY, TRY_BEFORE_YOU_BUY, TBYB_PROGRAM, DEAL, VEHICLE, CUSTOMER,
)
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

SIMULATION_NOTE = (
    "Status notifications, the deposit, and the insurance check are honestly simulated -- real "
    "state transitions, but no real SMS/email/push, payment, or insurance-API side effect fires "
    "in this sandbox (a real deployment routes them through NXTDeal Connect / a payment "
    "processor / an insurance verification provider)."
)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ====================================================================================
# HOME DELIVERY
# ====================================================================================

DELIVERY_MODES = ("store_pickup", "home_delivery", "third_party")

# Ordered forward flow; cancel is reachable from any non-terminal state.
DELIVERY_FLOW = ("scheduled", "preparing", "out_for_delivery", "delivered", "completed")
DELIVERY_TERMINAL = ("completed", "canceled")


def _sim_notification(customer_id, event):
    """A multi-channel status update (SMS + email + push), dispatched through the integration
    seam (core/integrations_registry.py) -- simulated today, live the moment a real
    notifications adapter is registered, with no change here."""
    from core.integrations_registry import send_notification
    return send_notification(customer_id, event)


def schedule_delivery(deal_id, mode, window_start, requested_by,
                      window_end=None, address=None, driver_id=None, notes=""):
    """Create a delivery for a deal. home_delivery / third_party require a delivery address."""
    deal = ledger.get_entity(deal_id)
    if not deal or deal.entity_type != DEAL:
        return {"error": f"'{deal_id}' is not a Deal"}
    if mode not in DELIVERY_MODES:
        return {"error": f"mode must be one of {list(DELIVERY_MODES)}"}
    if mode in ("home_delivery", "third_party") and not address:
        return {"error": f"{mode} requires a delivery address"}
    if not window_start:
        return {"error": "window_start is required"}

    delivery = Entity(
        id=id_generator.generate("DLVR"),
        entity_type=DELIVERY,
        attributes={
            "deal_id": deal_id,
            "customer_id": deal.attributes.get("customer_id"),
            "vehicle_id": deal.attributes.get("vehicle_id"),
            "mode": mode,
            "address": address,
            "window_start": window_start,
            "window_end": window_end,
            "driver_id": driver_id,
            "status": "scheduled",
            "notes": notes,
            "created_by": requested_by,
            "created_at": _iso(_now()),
            "updated_at": _iso(_now()),
            "ops_appointment_id": None,
            "status_timeline": [
                {"at": _iso(_now()), "status": "scheduled",
                 "notification": _sim_notification(deal.attributes.get("customer_id"), "delivery_scheduled")}
            ],
        },
    )
    ledger.add_entity(delivery)
    # Keep the store-side operations calendar in sync: best-effort create the delivery
    # Appointment (core/operations_scheduling.py). That helper only accepts contract/funded
    # deals, so a delivery scheduled earlier simply carries no appointment yet -- honest, not
    # an error. The Delivery entity is the richer record; the Appointment is its calendar peer.
    delivery.attributes["ops_appointment_id"] = _create_ops_appointment(
        deal_id, window_start, requested_by, driver_id, notes
    )
    save_graph(GRAPH_PATH)
    return {"delivery": _delivery_view(delivery)}


def _create_ops_appointment(deal_id, window_start, requested_by, driver_id, notes):
    from core.operations_scheduling import schedule_delivery as ops_schedule_delivery
    result = ops_schedule_delivery(deal_id, window_start, requested_by,
                                   assigned_to=driver_id, notes=notes or f"Delivery for {deal_id}")
    if isinstance(result, dict) and result.get("error"):
        return None
    return getattr(result, "id", None)


def _sync_ops_appointment(delivery, appt_status, by):
    """Push a Delivery status change onto its paired ops Appointment (best-effort; ignores an
    already-closed appointment)."""
    appt_id = delivery.attributes.get("ops_appointment_id")
    if not appt_id:
        return
    from core.appointments import update_status
    update_status(appt_id, appt_status, by)


def assign_driver(delivery_id, driver_id, by):
    delivery = _get(delivery_id, DELIVERY)
    if not delivery:
        return {"error": f"No delivery {delivery_id}"}
    delivery.attributes["driver_id"] = driver_id
    delivery.attributes["updated_at"] = _iso(_now())
    save_graph(GRAPH_PATH)
    return {"delivery": _delivery_view(delivery)}


def update_delivery_status(delivery_id, new_status, by):
    """Advance a delivery. Forward-only along DELIVERY_FLOW (no skipping/going back), or cancel
    from any non-terminal state. Each transition emits a simulated customer notification."""
    delivery = _get(delivery_id, DELIVERY)
    if not delivery:
        return {"error": f"No delivery {delivery_id}"}
    a = delivery.attributes
    current = a["status"]
    if current in DELIVERY_TERMINAL:
        return {"error": f"Delivery is already {current}"}
    if new_status == "canceled":
        pass
    elif new_status in DELIVERY_FLOW:
        if DELIVERY_FLOW.index(new_status) != DELIVERY_FLOW.index(current) + 1:
            return {"error": f"Cannot move from {current} to {new_status} -- deliveries advance "
                             f"one step at a time along {list(DELIVERY_FLOW)}"}
    else:
        return {"error": f"Unknown status '{new_status}'"}

    a["status"] = new_status
    a["updated_at"] = _iso(_now())
    a["status_timeline"].append(
        {"at": _iso(_now()), "status": new_status,
         "notification": _sim_notification(a.get("customer_id"), f"delivery_{new_status}")}
    )
    # Mirror onto the ops calendar: delivered/completed -> appointment completed; canceled ->
    # appointment cancelled. Intermediate steps leave the appointment as-is.
    if new_status in ("delivered", "completed"):
        _sync_ops_appointment(delivery, "completed", by)
    elif new_status == "canceled":
        _sync_ops_appointment(delivery, "cancelled", by)
    if new_status in ("delivered", "completed"):
        a.setdefault("loyalty_finalized_at", _iso(_now()))
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="delivery_status_changed",
        summary=f"Delivery {delivery_id} -> {new_status}",
        entity_id=delivery_id, actor=by, details={"status": new_status},
    )
    if new_status in ("delivered", "completed"):
        from core.loyalty_workflows import enqueue
        enqueue(delivery_id, by)
    return {"delivery": _delivery_view(delivery)}


def cancel_delivery(delivery_id, by, reason=None):
    return update_delivery_status(delivery_id, "canceled", by)


def _delivery_view(delivery):
    a = delivery.attributes
    return {
        "id": delivery.id, "deal_id": a.get("deal_id"), "customer_id": a.get("customer_id"),
        "vehicle_id": a.get("vehicle_id"), "mode": a.get("mode"), "address": a.get("address"),
        "window_start": a.get("window_start"), "window_end": a.get("window_end"),
        "driver_id": a.get("driver_id"), "status": a.get("status"), "notes": a.get("notes"),
        "status_timeline": a.get("status_timeline") or [],
        "ops_appointment_id": a.get("ops_appointment_id"),
        "created_by": a.get("created_by"),
        "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
    }


def get_delivery(delivery_id):
    d = _get(delivery_id, DELIVERY)
    return _delivery_view(d) if d else None


def list_deliveries(status=None, mode=None, deal_id=None, limit=100):
    rows = []
    for e in ledger.get_all().values():
        if e.entity_type != DELIVERY:
            continue
        a = e.attributes
        if status and a.get("status") != status:
            continue
        if mode and a.get("mode") != mode:
            continue
        if deal_id and a.get("deal_id") != deal_id:
            continue
        rows.append(_delivery_view(e))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"deliveries": rows[:limit], "count": min(len(rows), limit), "total": len(rows)}


def delivery_board():
    by_status = {}
    by_mode = {m: 0 for m in DELIVERY_MODES}
    unassigned_home = 0
    total = 0
    for e in ledger.get_all().values():
        if e.entity_type != DELIVERY:
            continue
        a = e.attributes
        total += 1
        by_status[a.get("status")] = by_status.get(a.get("status"), 0) + 1
        if a.get("mode") in by_mode:
            by_mode[a["mode"]] += 1
        if a.get("mode") in ("home_delivery", "third_party") and not a.get("driver_id") \
                and a.get("status") not in DELIVERY_TERMINAL:
            unassigned_home += 1
    return {"total": total, "by_status": by_status, "by_mode": by_mode,
            "home_deliveries_without_driver": unassigned_home,
            "modes": list(DELIVERY_MODES), "disclaimer": SIMULATION_NOTE}


# ====================================================================================
# TRY BEFORE YOU BUY
# ====================================================================================

_DEFAULT_PROGRAM = {
    "max_hours": 48,
    "max_miles": 250,
    "deposit_amount": 500.0,
    "require_identity_verified": True,
    "require_insurance": True,
}
_PROGRAM_KEYS = tuple(_DEFAULT_PROGRAM.keys())

# Linear lifecycle. `kept` is terminal; the return path continues to reinstated.
TBYB_FLOW = ("created", "insurance_verified", "deposit_collected", "out",
             "returned", "inspected", "reconditioned", "reinstated")
TBYB_TERMINAL = ("kept", "reinstated", "canceled")


def _find_program():
    for e in ledger.get_all().values():
        if e.entity_type == TBYB_PROGRAM:
            return e
    return None


def get_or_create_program():
    existing = _find_program()
    if existing:
        return existing
    prog = Entity(
        id=id_generator.generate("TBYP"),
        entity_type=TBYB_PROGRAM,
        attributes={**_DEFAULT_PROGRAM, "updated_by": None, "updated_at": _iso(_now())},
    )
    ledger.add_entity(prog)
    save_graph(GRAPH_PATH)
    return prog


def get_tbyb_program():
    a = get_or_create_program().attributes
    return {k: a.get(k) for k in _PROGRAM_KEYS}


def set_tbyb_program(patch, admin_id):
    if not isinstance(patch, dict):
        return {"error": "patch must be an object"}
    prog = get_or_create_program()
    clean = {}
    for k, v in patch.items():
        if k not in _PROGRAM_KEYS:
            return {"error": f"Unknown program setting '{k}' -- valid: {list(_PROGRAM_KEYS)}"}
        if k in ("require_identity_verified", "require_insurance"):
            clean[k] = bool(v)
        elif k in ("max_hours",):
            iv = _to_int(v)
            if iv is None or iv <= 0:
                return {"error": "max_hours must be a positive integer"}
            clean[k] = iv
        elif k == "max_miles":
            iv = _to_int(v)
            if iv is None or iv < 0:
                return {"error": "max_miles must be a non-negative integer"}
            clean[k] = iv
        else:  # deposit_amount
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return {"error": "deposit_amount must be a number"}
            if fv < 0:
                return {"error": "deposit_amount must be >= 0"}
            clean[k] = fv
    prog.attributes.update(clean)
    prog.attributes["updated_by"] = admin_id
    prog.attributes["updated_at"] = _iso(_now())
    save_graph(GRAPH_PATH)
    return {"program": get_tbyb_program()}


def _get(entity_id, entity_type):
    e = ledger.get_entity(entity_id)
    return e if e and e.entity_type == entity_type else None


def start_tbyb(vehicle_id, customer_id, requested_by, deal_id=None, verification_id=None):
    """Open a Try-Before-You-Buy. If the program requires identity verification, a NXTDeal
    Verify session at Identity Verified (or above) must be supplied."""
    vehicle = _get(vehicle_id, VEHICLE)
    if not vehicle:
        return {"error": f"'{vehicle_id}' is not a Vehicle"}
    customer = _get(customer_id, CUSTOMER)
    if not customer:
        return {"error": f"'{customer_id}' is not a Customer"}
    program = get_tbyb_program()
    if program["require_identity_verified"]:
        from core.dealeros_verify import get_verification, TIER_RANK, TIER_IDENTITY_VERIFIED
        v = get_verification(verification_id) if verification_id else None
        if not v or TIER_RANK.get(v["tier"], 0) < TIER_RANK[TIER_IDENTITY_VERIFIED]:
            return {"error": "Try Before You Buy requires an Identity Verified customer"}

    tbyb = Entity(
        id=id_generator.generate("TBYB"),
        entity_type=TRY_BEFORE_YOU_BUY,
        attributes={
            "vehicle_id": vehicle_id, "customer_id": customer_id, "deal_id": deal_id,
            "verification_id": verification_id, "status": "created",
            "program": program,
            "insurance": None, "deposit": None, "release": None, "decision": None,
            "return": None, "inspection": None, "recondition": None, "reinstated_at": None,
            "created_by": requested_by, "created_at": _iso(_now()), "updated_at": _iso(_now()),
            "history": [{"at": _iso(_now()), "event": "created"}],
        },
    )
    ledger.add_entity(tbyb)
    save_graph(GRAPH_PATH)
    return {"tbyb": _tbyb_view(tbyb)}


def _advance(tbyb, from_status, to_status, event, patch):
    a = tbyb.attributes
    if a["status"] != from_status:
        return {"error": f"Must be '{from_status}' to {event} (currently '{a['status']}')"}
    a.update(patch)
    a["status"] = to_status
    a["updated_at"] = _iso(_now())
    a["history"].append({"at": _iso(_now()), "event": event})
    save_graph(GRAPH_PATH)
    return {"tbyb": _tbyb_view(tbyb)}


def verify_insurance(tbyb_id, policy_ref, by):
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    if tbyb.attributes["status"] != "created":
        return {"error": "Trial must be created before insurance verification."}
    if not policy_ref:
        return {"error": "An insurance policy reference is required"}
    from core.integrations_registry import verify_insurance_policy
    check = verify_insurance_policy(policy_ref)
    if not isinstance(check, dict) or check.get("error") or check.get("verified") is not True:
        return check if isinstance(check, dict) and check.get("error") else {"error": "Insurance coverage could not be confirmed."}
    return _advance(tbyb, "created", "insurance_verified", "insurance_verified",
                    {"insurance": {"policy_ref": policy_ref, "verified_at": _iso(_now()),
                                   "simulated": check.get("simulated", True),
                                   "provider": check.get("provider")}})


def collect_deposit(tbyb_id, by, amount=None):
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    if tbyb.attributes["status"] != "insurance_verified":
        return {"error": "Trial insurance must be verified before deposit collection."}
    amt = amount if amount is not None else tbyb.attributes["program"]["deposit_amount"]
    from core.integrations_registry import charge_deposit
    charge = charge_deposit(amt, reference=tbyb_id)
    if not isinstance(charge, dict) or charge.get("error") or charge.get("status") != "collected":
        return charge if isinstance(charge, dict) and charge.get("error") else {"error": "Deposit collection could not be confirmed."}
    return _advance(tbyb, "insurance_verified", "deposit_collected", "deposit_collected",
                    {"deposit": {"amount": float(amt), "collected_at": _iso(_now()),
                                 "refunded": False, "simulated": charge.get("simulated", True),
                                 "provider": charge.get("provider")}})


def release_vehicle(tbyb_id, odometer_out, by):
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("trial_vehicle_release")
    if blocked:
        return blocked
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    a = tbyb.attributes
    if a["status"] != "deposit_collected":
        return {"error": f"Must be 'deposit_collected' to release (currently '{a['status']}')"}
    due = _now() + timedelta(hours=int(a["program"]["max_hours"]))
    res = _advance(tbyb, "deposit_collected", "out", "released",
                   {"release": {"odometer_out": _to_int(odometer_out), "released_at": _iso(_now()),
                                "due_back": _iso(due)}})
    # mark the vehicle out on trial (real inventory signal; reinstated on keep/return path)
    vehicle = ledger.get_entity(a["vehicle_id"])
    if vehicle:
        vehicle.attributes["on_trial"] = True
        save_graph(GRAPH_PATH)
    return res


def record_decision(tbyb_id, decision, by, odometer_in=None):
    """decision 'keep' -> terminal 'kept' (vehicle off trial). 'return' -> 'returned', then
    the return workflow (inspect -> recondition -> reinstate)."""
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    a = tbyb.attributes
    if a["status"] != "out":
        return {"error": f"Vehicle must be 'out' to record a decision (currently '{a['status']}')"}
    decision = str(decision or "").strip().lower()
    if decision not in ("keep", "return"):
        return {"error": "decision must be 'keep' or 'return'"}

    odo_in = _to_int(odometer_in)
    odo_out = (a.get("release") or {}).get("odometer_out")
    miles = (odo_in - odo_out) if (odo_in is not None and odo_out is not None) else None
    a["decision"] = decision
    if decision == "keep":
        a["return"] = {"odometer_in": odo_in, "returned_at": _iso(_now()), "miles_driven": miles}
        vehicle = ledger.get_entity(a["vehicle_id"])
        if vehicle:
            vehicle.attributes["on_trial"] = False
            save_graph(GRAPH_PATH)
        return _advance(tbyb, "out", "kept", "kept", {})
    return _advance(tbyb, "out", "returned", "returned",
                    {"return": {"odometer_in": odo_in, "returned_at": _iso(_now()),
                                "miles_driven": miles}})


def inspect_return(tbyb_id, findings, by):
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    return _advance(tbyb, "returned", "inspected", "inspected",
                    {"inspection": {"findings": findings or "", "at": _iso(_now())}})


def recondition(tbyb_id, notes, by):
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    return _advance(tbyb, "inspected", "reconditioned", "reconditioned",
                    {"recondition": {"notes": notes or "", "at": _iso(_now())}})


def reinstate_inventory(tbyb_id, by):
    tbyb = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    if not tbyb:
        return {"error": f"No TBYB {tbyb_id}"}
    res = _advance(tbyb, "reconditioned", "reinstated", "reinstated",
                   {"reinstated_at": _iso(_now())})
    vehicle = ledger.get_entity(tbyb.attributes["vehicle_id"])
    if vehicle:
        vehicle.attributes["on_trial"] = False
        save_graph(GRAPH_PATH)
    return res


def _tbyb_view(tbyb):
    a = tbyb.attributes
    return {
        "id": tbyb.id, "vehicle_id": a.get("vehicle_id"), "customer_id": a.get("customer_id"),
        "deal_id": a.get("deal_id"), "status": a.get("status"), "program": a.get("program"),
        "insurance": a.get("insurance"), "deposit": a.get("deposit"), "release": a.get("release"),
        "decision": a.get("decision"), "return": a.get("return"), "inspection": a.get("inspection"),
        "recondition": a.get("recondition"), "reinstated_at": a.get("reinstated_at"),
        "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
        "history": a.get("history") or [],
    }


def get_tbyb(tbyb_id):
    t = _get(tbyb_id, TRY_BEFORE_YOU_BUY)
    return _tbyb_view(t) if t else None


def list_tbyb(status=None, limit=100):
    rows = []
    for e in ledger.get_all().values():
        if e.entity_type != TRY_BEFORE_YOU_BUY:
            continue
        if status and e.attributes.get("status") != status:
            continue
        rows.append(_tbyb_view(e))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"trials": rows[:limit], "count": min(len(rows), limit), "total": len(rows)}


def tbyb_summary():
    by_status = {}
    total = 0
    out_now = 0
    for e in ledger.get_all().values():
        if e.entity_type != TRY_BEFORE_YOU_BUY:
            continue
        total += 1
        st = e.attributes.get("status")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "out":
            out_now += 1
    return {"total": total, "by_status": by_status, "currently_out": out_now,
            "program": get_tbyb_program(), "disclaimer": SIMULATION_NOTE}


def fulfillment_dashboard():
    return {"delivery": delivery_board(), "try_before_you_buy": tbyb_summary()}
