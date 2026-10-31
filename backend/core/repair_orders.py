"""
core/repair_orders.py -- the RO Workflow Engine, the flagship build of Service's
rebuild (2026-07-17, following the exact same "keep going" kickoff pattern as
Sales' Deal Desk / session 92, Operations' Vehicle Lifecycle / session 106, and
Inventory's Master Vehicle Workspace / session 109). Sam's own framing, from a
full Service spec: "A service department lives and dies by workflow... Every
screen should help move a RO through [the] lifecycle." Sam's own diagnosis of
the pre-existing core/service_menu.py was exactly right -- every item there
(RO counts, RO lists, customer lists, shop metrics, parts metrics, warranty
metrics) is service REPORTING, not service EXECUTION.

ServiceRecord already exists as the graph's repair-order entity (ServiceNumber/
CustomerID/VIN/Description/ServiceDate/Mileage/Cost/PartsCost/LaborHours/
PayType/Status/Technician) -- this module adds the real operational layer on
top of it: a 10-stage RO lifecycle, concern tracking, an estimate/approval
flow, parts requests, a QC checklist, and a composed timeline. Same additive-
attribute-on-existing-entity convention as core/vehicle_lifecycle.py's
lifecycle_status/recon_checklist and core/deals.py's trade_in/
delivery_checklist -- no new entity type, no parallel RO model.

Historical-data honesty note, same class of finding as vehicle_lifecycle.py's
lifecycle_status default: every one of this seed graph's 434 ServiceRecords
was imported as a flat historical row with Status="Completed" -- none of them
ever moved through a real intake event stream, so none of them have a real
ro_stage. A ServiceRecord with no explicit `ro_stage` attribute is given a
computed default of "Follow-Up" (the historical record is, in reality,
already fully closed out) rather than fabricating which stage it was
"really" in along the way. The moment anyone calls advance_stage() on it (or
a fresh RO is created via create_repair_order()), that computed default is
replaced by a real, stored, audited value and the RO genuinely starts moving
through the real pipeline from then on -- exactly the same mechanic
vehicle_lifecycle.py established for Vehicle.

Warranty Status and Recall Status (Sam's "Vehicle Information" ask) are both
REAL, not simulated -- Warranty Status is an honest inference off Vehicle.
Condition (New/Certified Pre-Owned implies likely factory coverage, labeled
as an inference since no real factory-warranty-database exists anywhere in
this codebase), Recall Status reuses the exact make/model cross-reference
core/trigger_alerts.py's _scan_recall_open() already established against the
real RECALL population (no per-vehicle recall link exists on Vehicle itself,
so this is computed the same way at read time, not a fabricated one-off).

The Communication Center (Sam: "Integrated: Call / Text / Email. Attached to
RO. No separate systems.") reuses core/field_notes.py's existing generic
FieldNote mechanism verbatim -- a new "ro_communication" category,
linked_entity_id=the RO's id, department="Service" -- same reuse discipline
as vehicle_message/recovery_attempt/objection etc. before it, not a parallel
message store.
"""

import copy
import math
import uuid
from datetime import date, datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import SERVICE_RECORD, VEHICLE, CUSTOMER, RECALL
from core.relationships import Relationship
from core.relationship_types import HAS_SERVICE_RECORD, AUTHORIZED
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.field_notes import create_field_note, list_field_notes
from core.vin_decoder import check_vehicle_vin_match

RO_STAGES = [
    "Check-In", "RO Written", "Inspection", "Estimate", "Customer Approval",
    "Parts", "Repair", "Quality Control", "Delivery", "Follow-Up",
]

QC_ITEMS = ("repair_complete", "road_test", "qc_inspection", "washed")

PARTS_STATUSES = ("all_available", "awaiting_shipment", "backordered")
PART_REQUEST_STATUSES = ("requested", "in_stock", "ordered", "received", "installed")

COMM_CHANNELS = ("call", "text", "email")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sub_id(prefix):
    """Ids for records embedded inside a ServiceRecord's own attributes
    (concerns, parts_requests) -- deliberately NOT core/id_generator.py's
    shared counter, which only survives for the lifetime of one running
    process and is never recovered from these embedded lists (unlike real
    graph-entity ids, which id_generator._recover_id_counters() rescans on
    boot). A random suffix avoids that whole collision class rather than
    inheriting it the way vehicle_lifecycle.py's vendor_assignments ids did."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _get_ro(ro_id):
    r = ledger.get_entity(ro_id)
    if not r or r.entity_type != SERVICE_RECORD:
        return None
    return r


def _default_stage(ro):
    if ro.attributes.get("Status") == "Completed":
        return "Follow-Up"
    return "Check-In"


def _stage_of(ro):
    return ro.attributes.get("ro_stage") or _default_stage(ro)


def _hours_since_checkin(ro):
    """Shared by core/service_overview.py's jobs_behind_schedule and
    core/shop_control.py's stalled-RO/approval-delay checks -- one real
    "how long has this RO been open" computation, not three. Deliberately
    uses a real datetime.now() call rather than this module's own _now()
    (which returns an isoformat STRING, for timestamping -- not usable in a
    subtraction)."""
    history = ro.attributes.get("ro_stage_history") or []
    if not history:
        return None
    try:
        checked_in_at = datetime.fromisoformat(history[0]["at"])
    except (ValueError, TypeError, KeyError):
        return None
    return round((datetime.now(timezone.utc) - checked_in_at).total_seconds() / 3600.0, 1)


def _linked_record_source(ro, relationship_type, entity_type):
    # Live check-in writes these exact links; optional import keys may be absent
    # or duplicated. Never substitute a different record for an ambiguous link.
    sources = {r.source_id for r in ledger.get_entity_relationships(ro.id)
               if r.target_id == ro.id and r.relationship_type == relationship_type}
    if len(sources) == 1:
        entity = ledger.get_entity(next(iter(sources)))
        if entity and entity.entity_type == entity_type:
            return entity, True
    return None, bool(sources)


def _customer_for_record(ro):
    linked, has_link = _linked_record_source(ro, AUTHORIZED, CUSTOMER)
    if has_link:
        return linked
    cust_key = ro.attributes.get("CustomerID")
    if not cust_key:
        return None
    for c in ledger.get_all().values():
        if c.entity_type == CUSTOMER and c.attributes.get("CustomerID") == cust_key:
            return c
    return None


def _vehicle_for_record(ro):
    linked, has_link = _linked_record_source(ro, HAS_SERVICE_RECORD, VEHICLE)
    if has_link:
        return linked
    vin = ro.attributes.get("VIN")
    if not vin:
        return None
    for v in ledger.get_all().values():
        if v.entity_type == VEHICLE and v.attributes.get("VIN") == vin:
            return v
    return None


def _warranty_status(vehicle):
    """Honest inference, not a real factory-warranty-database check (none
    exists anywhere in this codebase, same finding sessions 62/85 already
    made) -- Condition New/Certified Pre-Owned implies likely coverage."""
    if not vehicle:
        return {"status": "unknown", "note": "No vehicle on file for this RO."}
    condition = (vehicle.attributes.get("Condition") or "").strip()
    if condition in ("New", "Certified Pre-Owned"):
        return {
            "status": "likely_covered",
            "condition": condition,
            "note": "INFERRED from Vehicle.Condition -- no real factory-warranty database exists in this system to confirm actual coverage/remaining term.",
        }
    return {
        "status": "likely_not_covered",
        "condition": condition or None,
        "note": "INFERRED from Vehicle.Condition -- used vehicles are assumed out of factory coverage absent a real warranty-database check.",
    }


def _recall_status(vehicle):
    """REAL -- same make/model cross-reference core/trigger_alerts.py's
    _scan_recall_open() already established against the real RECALL
    population (no per-vehicle recall link exists on Vehicle itself)."""
    if not vehicle:
        return {"open_recalls": [], "count": 0}

    vehicle_make = str(vehicle.attributes.get("Make", "")).strip().lower()
    vehicle_model = str(vehicle.attributes.get("Model", "")).strip().lower()

    matches = []
    for r in ledger.get_all().values():
        if r.entity_type != RECALL or not r.attributes.get("open"):
            continue
        if (
            str(r.attributes.get("make", "")).strip().lower() == vehicle_make
            and str(r.attributes.get("model", "")).strip().lower() == vehicle_model
        ):
            matches.append({
                "id": r.id,
                "recall_number": r.attributes.get("recall_number"),
                "description": r.attributes.get("description"),
                "campaign_type": r.attributes.get("campaign_type"),
            })

    return {"open_recalls": matches, "count": len(matches)}


def create_repair_order(vehicle_id, customer_id, description, created_by, pay_type="Customer Pay", preferred_contact_method=None):
    """Writes a genuinely NEW, live ServiceRecord -- Check-In is the real
    entry point of the live workflow (all 434 seeded records are historical
    imports, already Completed; this is how a real day-to-day RO gets born
    going forward). Reuses imports/service_import.py's exact relationship
    convention (Customer --AUTHORIZED--> ServiceRecord, Vehicle
    --HAS_SERVICE_RECORD--> ServiceRecord) so a live RO looks identical on
    the graph to a historically-imported one."""

    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        return {"error": f"Customer '{customer_id}' not found"}

    if not description or not description.strip():
        return {"error": "description (the customer's stated concern) is required"}

    ro_id = id_generator.generate("SRV")

    ro = Entity(
        id=ro_id,
        entity_type=SERVICE_RECORD,
        attributes={
            "ServiceNumber": ro_id,
            "CustomerID": customer.attributes.get("CustomerID"),
            "VIN": vehicle.attributes.get("VIN"),
            "Description": description.strip(),
            "ServiceDate": _now()[:10],
            "Mileage": vehicle.attributes.get("Mileage"),
            "Cost": 0,
            "PartsCost": 0,
            "LaborHours": 0,
            "PayType": pay_type,
            "Status": "Open",
            "Technician": None,
            "ro_stage": "Check-In",
            "ro_stage_history": [{"stage": "Check-In", "at": _now(), "by": created_by}],
            "concerns": [{
                "id": _sub_id("CONC"),
                "description": description.strip(),
                "occurs_at": "",
                "created_by": created_by,
                "created_at": _now(),
                "status": "open",
            }],
            "preferred_contact_method": preferred_contact_method or None,
            "parts_requests": [],
            "parts_status": None,
            "estimate": None,
            "qc_checklist": {},
        },
    )

    ledger.add_entity(ro)

    ledger.add_relationship(Relationship(source_id=customer.id, target_id=ro_id, relationship_type=AUTHORIZED))
    ledger.add_relationship(Relationship(source_id=vehicle.id, target_id=ro_id, relationship_type=HAS_SERVICE_RECORD))

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def _delivery_blockers(ro):
    """Normal completed-repair delivery only; no inference of payment or safety."""
    blockers = []
    concerns = ro.attributes.get("concerns") or []
    if any(c.get("status") not in ("resolved", "declined", "deferred") for c in concerns):
        blockers.append("Record an outcome for every open concern")
    if any(c.get("status") in ("declined", "deferred") for c in concerns):
        blockers.append("Declined or deferred work needs a separate return review; normal completed-repair delivery is unavailable")
    estimate = ro.attributes.get("estimate")
    if estimate and estimate.get("approved") is not True:
        blockers.append("Record customer approval for the estimate before completed-repair delivery")
    if any(r.get("status") != "installed" for r in (ro.attributes.get("parts_requests") or [])):
        blockers.append("Review outstanding parts requests before delivery")
    if not _qc_ready_for_pickup(ro.attributes.get("qc_checklist") or {}):
        blockers.append("Complete the quality-control checklist")
    return blockers


def _return_review_snapshot(ro):
    return copy.deepcopy({key: ro.attributes.get(key) for key in
        ("concerns", "parts_requests", "estimate", "qc_checklist", "parts_status")})


def record_return_review(ro_id, recorded_by, transport, notes, acknowledged):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    if transport not in ("tow", "customer_pickup", "other"):
        return {"error": "Choose a return transport plan"}
    if acknowledged is not True:
        return {"error": "Confirm that unfinished work and the return plan were reviewed"}
    if not isinstance(notes, str) or not notes.strip():
        return {"error": "Record the unfinished work, customer discussion and return plan"}
    concerns = ro.attributes.get("concerns") or []
    if not any(c.get("status") in ("declined", "deferred") for c in concerns):
        return {"error": "This review is for declined or deferred work"}
    if any(c.get("status") not in ("resolved", "declined", "deferred") for c in concerns):
        return {"error": "Record an outcome for every open concern before the return review"}
    review = {"transport": transport, "notes": notes.strip(), "acknowledged": True,
              "recorded_by": recorded_by, "recorded_at": _now(),
              "snapshot": _return_review_snapshot(ro)}
    ro.attributes.setdefault("return_reviews", []).append(review)
    save_graph(GRAPH_PATH)
    return get_ro_workspace(ro_id)


def record_return_handover(ro_id, recorded_by, recipient, settlement_reference, confirmed):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    if ro.attributes.get("return_handover"):
        return {"error": "Return handover is already recorded; review the existing record"}
    reviews = ro.attributes.get("return_reviews") or []
    if not reviews or reviews[-1].get("snapshot") != _return_review_snapshot(ro):
        return {"error": "Save a current return review before recording handover"}
    if confirmed is not True:
        return {"error": "Confirm actual handover and the recorded transport arrangement"}
    if not isinstance(recipient, str) or not recipient.strip():
        return {"error": "Record who received the vehicle"}
    if not isinstance(settlement_reference, str) or not settlement_reference.strip():
        return {"error": "Record the external settlement or no-charge authorization reference"}
    review = reviews[-1]
    ro.attributes["return_handover"] = {
        "recipient": recipient.strip(), "settlement_reference": settlement_reference.strip(),
        "settlement_basis": "staff_recorded_external_check", "transport": review["transport"],
        "review_recorded_at": review["recorded_at"], "recorded_by": recorded_by,
        "recorded_at": _now(), "snapshot": _return_review_snapshot(ro),
    }
    # Physical custody return is distinct from completing the repair order.
    save_graph(GRAPH_PATH)
    return get_ro_workspace(ro_id)


def plan_return_followup(ro_id, recorded_by, due_date, next_action):
    ro = _get_ro(ro_id)
    if not ro or not ro.attributes.get("return_handover"):
        return {"error": "Record the vehicle return before planning returned-work follow-up"}
    try:
        parsed = date.fromisoformat(due_date)
        if parsed.isoformat() != due_date:
            raise ValueError()
    except (TypeError, ValueError):
        return {"error": "Use a valid YYYY-MM-DD follow-up date"}
    if not isinstance(next_action, str) or not next_action.strip():
        return {"error": "Describe the next action"}
    plan = {"status": "planned", "owner_id": recorded_by, "due_date": due_date, "next_action": next_action.strip(), "updated_at": _now()}
    ro.attributes["return_followup"] = plan
    ro.attributes.setdefault("return_followup_history", []).append(copy.deepcopy(plan))
    save_graph(GRAPH_PATH)
    return get_ro_workspace(ro_id)


def complete_return_followup(ro_id, recorded_by, outcome, expected_updated_at):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": "Repair order not found"}
    plan = ro.attributes.get("return_followup")
    if not plan or not ro.attributes.get("return_handover"):
        return {"error": "Save a returned-work follow-up plan first"}
    if plan.get("updated_at") != expected_updated_at:
        return {"error": "The follow-up plan changed; reload and review it before recording an outcome"}
    if plan.get("status") == "completed":
        return {"error": "This follow-up already has a recorded outcome"}
    if not isinstance(outcome, str) or not outcome.strip():
        return {"error": "Describe the follow-up outcome"}
    plan = copy.deepcopy(plan)
    plan.update({"status": "completed", "outcome": outcome.strip(), "completed_by": recorded_by, "completed_at": _now(), "updated_at": _now()})
    ro.attributes["return_followup"] = plan
    ro.attributes.setdefault("return_followup_history", []).append(copy.deepcopy(plan))
    save_graph(GRAPH_PATH)
    return get_ro_workspace(ro_id)


def advance_stage(ro_id, new_stage, updated_by):

    if new_stage not in RO_STAGES:
        return {"error": f"new_stage must be one of {RO_STAGES}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if new_stage in ("Delivery", "Follow-Up"):
        blockers = _delivery_blockers(ro)
        if new_stage == "Follow-Up" and ro.attributes.get("ro_stage") not in ("Delivery", "Follow-Up"):
            blockers.append("Move through Delivery before Follow-Up")
        if blockers:
            return {"error": "Delivery review required: " + "; ".join(blockers), "blockers": blockers}

    ro.attributes["ro_stage"] = new_stage
    ro.attributes.setdefault("ro_stage_history", []).append(
        {"stage": new_stage, "at": _now(), "by": updated_by}
    )

    if new_stage == "Follow-Up" and ro.attributes.get("Status") != "Completed":
        ro.attributes["Status"] = "Completed"
        ro.attributes["loyalty_finalized_at"] = _now()

    save_graph(GRAPH_PATH)

    if new_stage == "Follow-Up":
        from core.loyalty_workflows import enqueue
        enqueue(ro_id, updated_by)

    return get_ro_workspace(ro_id)


def add_concern(ro_id, description, created_by, occurs_at=""):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if not description or not description.strip():
        return {"error": "description is required"}

    concerns = ro.attributes.get("concerns") or []
    concerns.append({
        "id": _sub_id("CONC"),
        "description": description.strip(),
        "occurs_at": occurs_at or "",
        "created_by": created_by,
        "created_at": _now(),
        "status": "open",
    })
    ro.attributes["concerns"] = concerns

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def resolve_concern(ro_id, concern_id, resolved_by, resolution_notes="", outcome="resolved"):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if outcome not in ("resolved", "declined", "deferred"):
        return {"error": "outcome must be resolved, declined or deferred"}
    if not isinstance(resolution_notes, str) or not resolution_notes.strip():
        return {"error": "Describe the repair or customer decision before saving the outcome"}

    concerns = ro.attributes.get("concerns") or []
    found = False
    for c in concerns:
        if c.get("id") == concern_id:
            c.setdefault("outcome_history", []).append({"outcome": outcome, "notes": resolution_notes.strip(), "by": resolved_by, "at": _now()})
            c["status"] = outcome
            c["resolution_notes"] = resolution_notes.strip()
            c["resolved_by"] = resolved_by
            c["resolved_at"] = _now()
            found = True
            break

    if not found:
        return {"error": f"Concern '{concern_id}' not found on this RO"}

    ro.attributes["concerns"] = concerns
    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def send_estimate(ro_id, amount, sent_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be a number"}

    if not math.isfinite(amount) or amount < 0:
        return {"error": "amount must be a finite, non-negative number"}

    ro.attributes["estimate"] = {
        "amount": amount,
        "sent_by": sent_by,
        "sent_at": _now(),
        "approved": None,
        "approved_by": None,
        "approved_at": None,
        "decline_reason": None,
    }

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def record_customer_approval(ro_id, approved, recorded_by, decline_reason=""):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    estimate = ro.attributes.get("estimate")
    if not estimate:
        return {"error": "No estimate has been sent on this RO yet"}

    estimate["approved"] = bool(approved)
    estimate["approved_by"] = recorded_by
    estimate["approved_at"] = _now()
    estimate["decline_reason"] = (decline_reason or "") if not approved else None

    ro.attributes["estimate"] = estimate
    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def assign_technician(ro_id, technician_id, assigned_by):
    """The real capability behind Shop Control's Technician Dispatch Board --
    nothing in this codebase could previously assign/reassign a technician to
    a live RO (ServiceRecord.Technician was only ever set once, at CSV-import
    time, for historical records). A None/empty technician_id un-assigns
    (moves the RO back to the dispatch board's Unassigned column)."""

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if technician_id:
        tech = ledger.get_entity(technician_id)
        if not tech:
            return {"error": f"Technician '{technician_id}' not found"}

    ro.attributes["Technician"] = technician_id or None
    ro.attributes.setdefault("technician_assignment_history", []).append(
        {"technician_id": technician_id or None, "at": _now(), "by": assigned_by}
    )

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def update_parts_status(ro_id, status, updated_by, notes=""):

    if status not in PARTS_STATUSES:
        return {"error": f"status must be one of {list(PARTS_STATUSES)}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    ro.attributes["parts_status"] = {
        "status": status,
        "notes": notes or "",
        "updated_by": updated_by,
        "updated_at": _now(),
    }

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def request_part(ro_id, description, requested_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if not description or not description.strip():
        return {"error": "description is required"}

    requests = ro.attributes.get("parts_requests") or []
    requests.append({
        "id": _sub_id("PREQ"),
        "description": description.strip(),
        "status": "requested",
        "requested_by": requested_by,
        "requested_at": _now(),
        "updated_by": None,
        "updated_at": None,
    })
    ro.attributes["parts_requests"] = requests

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def update_part_request_status(ro_id, request_id, status, updated_by):

    if status not in PART_REQUEST_STATUSES:
        return {"error": f"status must be one of {list(PART_REQUEST_STATUSES)}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    requests = ro.attributes.get("parts_requests") or []
    found = False
    for r in requests:
        if r.get("id") == request_id:
            if status == "installed" and r.get("status") not in ("in_stock", "received", "installed"):
                return {"error": "Record this part as in stock or received before marking it installed"}
            r["status"] = status
            r["updated_by"] = updated_by
            r["updated_at"] = _now()
            found = True
            break

    if not found:
        return {"error": f"Part request '{request_id}' not found on this RO"}

    ro.attributes["parts_requests"] = requests
    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def update_qc_item(ro_id, item, complete, updated_by):
    """Quality Control Process, Sam's own spec: 'Repair Complete -> Road Test
    -> QC Inspection -> Washed -> Ready For Pickup.' The first 4 are real
    checkboxes; Ready For Pickup is deliberately NOT a 5th manual checkbox --
    it's computed (all 4 complete) so the RO can't be marked ready by
    skipping the actual checklist."""

    if item not in QC_ITEMS:
        return {"error": f"item must be one of {list(QC_ITEMS)}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    checklist = dict(ro.attributes.get("qc_checklist") or {})
    checklist[item] = {
        "complete": bool(complete),
        "updated_by": updated_by,
        "updated_at": _now(),
    }
    ro.attributes["qc_checklist"] = checklist

    save_graph(GRAPH_PATH)

    return get_ro_workspace(ro_id)


def log_ro_communication(ro_id, channel, body, created_by):

    if channel not in COMM_CHANNELS:
        return {"error": f"channel must be one of {list(COMM_CHANNELS)}"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if not body or not body.strip():
        return {"error": "body is required"}

    create_field_note("Service", "ro_communication", f"[{channel}] {body.strip()}", created_by, linked_entity_id=ro_id)

    return get_ro_workspace(ro_id)


def _workflow_checklist(ro):
    current = _stage_of(ro)
    current_idx = RO_STAGES.index(current) if current in RO_STAGES else 0

    checklist = []
    for i, stage in enumerate(RO_STAGES):
        if i < current_idx:
            status = "complete"
        elif i == current_idx:
            status = "current"
        else:
            status = "pending"
        checklist.append({"stage": stage, "status": status})
    return checklist


def _qc_ready_for_pickup(checklist):
    return all((checklist.get(item) or {}).get("complete") for item in QC_ITEMS)


def get_ro_timeline(ro_id, limit=100):
    """Composed activity feed -- same "merge real history already tracked,
    don't build a second parallel event log" discipline as
    vehicle_lifecycle.py's get_vehicle_activity_feed(): stage transitions,
    concern captures, estimate/approval, parts requests, QC completions, and
    the Communication Center's logged calls/texts/emails, all in one
    chronological feed."""

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    events = []

    for h in ro.attributes.get("ro_stage_history") or []:
        events.append({"type": "stage_change", "label": f"Moved to {h.get('stage')}", "at": h.get("at"), "by": h.get("by"), "notes": None})

    for c in ro.attributes.get("concerns") or []:
        events.append({"type": "concern_added", "label": f"Concern logged: {c.get('description')}", "at": c.get("created_at"), "by": c.get("created_by"), "notes": c.get("occurs_at") or None})
        if c.get("status") in ("resolved", "declined", "deferred"):
            events.append({"type": "concern_resolved", "label": f"Concern {c.get('status')}: {c.get('description')}", "at": c.get("resolved_at"), "by": c.get("resolved_by"), "notes": c.get("resolution_notes")})

    estimate = ro.attributes.get("estimate")
    if estimate:
        events.append({"type": "estimate_sent", "label": f"Estimate sent -- ${estimate.get('amount')}", "at": estimate.get("sent_at"), "by": estimate.get("sent_by"), "notes": None})
        if estimate.get("approved") is True:
            events.append({"type": "estimate_approved", "label": "Customer approved estimate", "at": estimate.get("approved_at"), "by": estimate.get("approved_by"), "notes": None})
        elif estimate.get("approved") is False:
            events.append({"type": "estimate_declined", "label": "Customer declined estimate", "at": estimate.get("approved_at"), "by": estimate.get("approved_by"), "notes": estimate.get("decline_reason")})

    for r in ro.attributes.get("parts_requests") or []:
        events.append({"type": "part_requested", "label": f"Part requested: {r.get('description')}", "at": r.get("requested_at"), "by": r.get("requested_by"), "notes": None})
        if r.get("updated_at"):
            events.append({"type": "part_status", "label": f"Part status -> {r.get('status')}: {r.get('description')}", "at": r.get("updated_at"), "by": r.get("updated_by"), "notes": None})

    for item, entry in (ro.attributes.get("qc_checklist") or {}).items():
        events.append({"type": "qc_item", "label": f"QC -- {item.replace('_', ' ')}: {'complete' if entry.get('complete') else 'incomplete'}", "at": entry.get("updated_at"), "by": entry.get("updated_by"), "notes": None})

    for h in ro.attributes.get("technician_assignment_history") or []:
        label = f"Assigned to technician {h.get('technician_id')}" if h.get("technician_id") else "Unassigned from technician"
        events.append({"type": "technician_assigned", "label": label, "at": h.get("at"), "by": h.get("by"), "notes": None})

    for note in list_field_notes(department="Service", limit=200, linked_entity_id=ro_id):
        if note.attributes.get("category") == "ro_communication":
            events.append({"type": "communication", "label": note.attributes.get("body"), "at": note.attributes.get("created_at"), "by": note.attributes.get("created_by"), "notes": None})

    events.sort(key=lambda e: e.get("at") or "")

    return {"events": events[-limit:]}


def get_ro_workspace(ro_id):
    """The full RO operating environment Sam asked for: Customer Information,
    Vehicle Information (VIN/mileage/warranty/recall status), Concern
    Tracking, RO Workflow Status, Timeline, and (via the Communication
    Center's own log_ro_communication/get_ro_timeline) the integrated
    call/text/email log."""

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    customer = _customer_for_record(ro)
    vehicle = _vehicle_for_record(ro)

    # Phase 2 of NXTDeal VIN Intelligence: a real, in-process cross-check
    # (no HTTP round-trip, no new route needed) confirming this RO's own
    # vehicle actually matches its VIN's decoded manufacturer/year -- a real
    # identity-integrity signal for a Service Advisor, on top of the honest
    # warranty/recall inferences below.
    vin_match, _vin_match_error = check_vehicle_vin_match(vehicle.id) if vehicle else (None, None)

    stage = _stage_of(ro)
    qc_checklist = ro.attributes.get("qc_checklist") or {}

    return {
        "id": ro.id,
        "service_number": ro.attributes.get("ServiceNumber"),
        "description": ro.attributes.get("Description"),
        "service_date": ro.attributes.get("ServiceDate"),
        "pay_type": ro.attributes.get("PayType"),
        "status": ro.attributes.get("Status"),
        "cost": ro.attributes.get("Cost"),
        "parts_cost": ro.attributes.get("PartsCost"),
        "labor_hours": ro.attributes.get("LaborHours"),
        "technician": ro.attributes.get("Technician"),
        "ro_stage": stage,
        "ro_stage_is_default": ro.attributes.get("ro_stage") is None,
        "workflow_checklist": _workflow_checklist(ro),
        "customer": {
            "id": customer.id if customer else None,
            "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
            "phone": customer.attributes.get("Phone") if customer else None,
            "email": customer.attributes.get("Email") if customer else None,
            "preferred_contact_method": ro.attributes.get("preferred_contact_method"),
        },
        "vehicle": {
            "id": vehicle.id if vehicle else None,
            "vin": ro.attributes.get("VIN"),
            "year": vehicle.attributes.get("Year") if vehicle else None,
            "make": vehicle.attributes.get("Make") if vehicle else None,
            "model": vehicle.attributes.get("Model") if vehicle else None,
            "mileage": ro.attributes.get("Mileage"),
            "warranty_status": _warranty_status(vehicle),
            "recall_status": _recall_status(vehicle),
            "vin_match": vin_match,
        },
        "concerns": ro.attributes.get("concerns") or [],
        "estimate": ro.attributes.get("estimate"),
        "parts_status": ro.attributes.get("parts_status"),
        "parts_requests": ro.attributes.get("parts_requests") or [],
        "qc_checklist": qc_checklist,
        "qc_ready_for_pickup": _qc_ready_for_pickup(qc_checklist),
        "delivery_blockers": _delivery_blockers(ro),
        "return_followup": ro.attributes.get("return_followup"),
        "return_handover": ({k: v for k, v in ro.attributes["return_handover"].items() if k != "snapshot"} | {
            "work_changed_since": ro.attributes["return_handover"].get("snapshot") != _return_review_snapshot(ro)
        }) if ro.attributes.get("return_handover") else None,
        "return_review": ({k: v for k, v in ro.attributes["return_reviews"][-1].items() if k != "snapshot"} | {
            "current": ro.attributes["return_reviews"][-1].get("snapshot") == _return_review_snapshot(ro)
        }) if ro.attributes.get("return_reviews") else None,
        "timeline": get_ro_timeline(ro_id),
    }


def _ro_brief(ro):
    return {
        "id": ro.id,
        "return_followup": ro.attributes.get("return_followup"),
        "vehicle_returned_at": (ro.attributes.get("return_handover") or {}).get("recorded_at"),
        "service_number": ro.attributes.get("ServiceNumber"),
        "vin": ro.attributes.get("VIN"),
        "customer_id": ro.attributes.get("CustomerID"),
        "description": ro.attributes.get("Description"),
        "pay_type": ro.attributes.get("PayType"),
        "ro_stage": _stage_of(ro),
        "technician": ro.attributes.get("Technician"),
        "service_date": ro.attributes.get("ServiceDate"),
    }


def get_stage_counts():
    """Real, UNCAPPED per-stage counts across every ServiceRecord -- deliberately
    separate from get_ro_board()'s per-stage vehicle LIST, which caps each stage
    at limit_per_stage (100 by default) for board-rendering purposes. That cap
    would silently undercount a stage (Follow-Up, in particular, holds all 434
    historical records) if reused for a count -- same distinction
    core/inventory_overview.py's get_lifecycle_stage_counts() draws against
    core/vehicle_lifecycle.py's own capped list_by_stage()."""

    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    counts = {s: 0 for s in RO_STAGES}
    for r in records:
        stage = _stage_of(r)
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def get_ro_board(limit_per_stage=100):
    """The RO Workflow's Kanban board -- every ServiceRecord grouped by its
    (stored or computed-default) ro_stage. Same "no filtering by
    open/closed, the caller decides what to render" convention as
    vehicle_lifecycle.py's list_by_stage()."""

    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]

    board = {s: [] for s in RO_STAGES}
    for r in records:
        stage = _stage_of(r)
        board.setdefault(stage, []).append(_ro_brief(r))

    for stage in board:
        board[stage] = board[stage][:limit_per_stage]

    return board


def get_catalog():
    return {
        "stages": RO_STAGES,
        "qc_items": list(QC_ITEMS),
        "parts_statuses": list(PARTS_STATUSES),
        "part_request_statuses": list(PART_REQUEST_STATUSES),
        "comm_channels": list(COMM_CHANNELS),
    }
