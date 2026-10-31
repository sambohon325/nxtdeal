"""
core/warranty_desk.py -- Service's "Warranty" item, the sixth slice of
Service's rebuild (following RO Workflow Engine, Overview, Shop Control,
Customers, and Parts, session 111). Sam's spec: Warranty Eligibility Check,
Submission Workflow, a Rejected Claims Queue, and Recall Management.

core/service_menu.py's existing `warranty()` (session 61) is real claim
LISTING (every ServiceRecord with PayType == "Warranty", off
core/workflow_tab_data.py's service_warranty_claims) and open-recall
reporting -- but nothing tracked a claim's actual submission/decision/
payment status, and nothing tracked which specific vehicles had actually
had a given open recall's repair completed. This module closes both real
gaps.

Submission Workflow is the same additive-attribute-on-ServiceRecord
convention as core/repair_orders.py's `estimate`/`delivery_checklist` --
`warranty_claim` is a dict living on the ServiceRecord itself, only
meaningful for records with PayType == "Warranty" (submitting a claim on a
non-warranty RO is rejected). A ServiceRecord with PayType == "Warranty" but
no `warranty_claim` dict yet gets a computed "draft" default (same
computed-default-for-historical-data convention as repair_orders.py's
ro_stage) -- the real 55 historical warranty ServiceRecords from the
original CSV import predate this workflow entirely and were never actually
"submitted" through any system, so "draft" is the honest starting point, not
a fabricated submitted/approved history.

Warranty Eligibility Check reuses core/repair_orders.py's real
`_warranty_status()` Condition-based inference verbatim, plus one genuine
additional real signal: if an open recall exists for this vehicle's exact
make/model, the recall-specific repair is ALWAYS warranty-eligible
regardless of Condition (federal recall law covers this regardless of
vehicle age) -- a real rule, not a fabricated one.

Recall Management is a genuinely new internal capability: nothing in this
codebase previously tracked which specific customer-owned vehicles had
actually had a given open recall's repair completed (core/trigger_alerts.py's
`_scan_recall_open()` only flags the match, it doesn't track completion).
`mark_recall_completed()` records this as an additive `completed_recalls`
list on the Vehicle entity itself (same additive-attribute convention used
throughout this codebase), and `get_recall_management_queue()` reuses
trigger_alerts.py's own real customer-vehicle-ownership cross-reference
logic to split each open recall's real affected population into "needs
repair" vs. "completed" -- not a second recall-matching engine.
"""

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD, VEHICLE, CUSTOMER, RECALL
from core.repair_orders import _get_ro, _now, _customer_for_record, _warranty_status
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

WARRANTY_CLAIM_STATUSES = ("draft", "submitted", "approved", "rejected", "paid")


def _default_claim():
    return {
        "status": "draft",
        "oem_claim_number": None,
        "submitted_by": None,
        "submitted_at": None,
        "decided_by": None,
        "decided_at": None,
        "rejection_reason": None,
        "paid_amount": None,
        "paid_at": None,
        "paid_by": None,
    }


def _claim_of(ro):
    return ro.attributes.get("warranty_claim") or _default_claim()


def _all_warranty_records():
    return [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD and e.attributes.get("PayType") == "Warranty"]


def _ro_brief(ro):
    customer = _customer_for_record(ro)
    return {
        "ro_id": ro.id,
        "service_number": ro.attributes.get("ServiceNumber"),
        "ro_description": ro.attributes.get("Description"),
        "vin": ro.attributes.get("VIN"),
        "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
    }


def get_warranty_claim(ro_id):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    if ro.attributes.get("PayType") != "Warranty":
        return {"error": f"'{ro_id}' is not a Warranty pay-type record"}

    return {**_ro_brief(ro), **_claim_of(ro)}


def submit_warranty_claim(ro_id, submitted_by, oem_claim_number=None):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    if ro.attributes.get("PayType") != "Warranty":
        return {"error": "Only Warranty pay-type records can have a warranty claim submitted"}

    claim = _claim_of(ro)
    if claim["status"] not in ("draft", "rejected"):
        return {"error": f"Cannot submit a claim already in '{claim['status']}' status"}

    claim["status"] = "submitted"
    claim["oem_claim_number"] = oem_claim_number or claim.get("oem_claim_number")
    claim["submitted_by"] = submitted_by
    claim["submitted_at"] = _now()
    claim["decided_by"] = None
    claim["decided_at"] = None
    claim["rejection_reason"] = None

    ro.attributes["warranty_claim"] = claim
    save_graph(GRAPH_PATH)

    return {**_ro_brief(ro), **claim}


def record_warranty_decision(ro_id, approved, decided_by, rejection_reason=""):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    claim = _claim_of(ro)
    if claim["status"] != "submitted":
        return {"error": f"Cannot record a decision on a claim in '{claim['status']}' status -- it must be 'submitted' first"}

    if not approved and not (rejection_reason or "").strip():
        return {"error": "rejection_reason is required when declining a warranty claim"}

    claim["status"] = "approved" if approved else "rejected"
    claim["decided_by"] = decided_by
    claim["decided_at"] = _now()
    claim["rejection_reason"] = (rejection_reason or "").strip() if not approved else None

    ro.attributes["warranty_claim"] = claim
    save_graph(GRAPH_PATH)

    return {**_ro_brief(ro), **claim}


def record_warranty_payment(ro_id, paid_amount, paid_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    claim = _claim_of(ro)
    if claim["status"] != "approved":
        return {"error": f"Cannot record payment on a claim in '{claim['status']}' status -- it must be 'approved' first"}

    try:
        amount = float(paid_amount)
    except (TypeError, ValueError):
        return {"error": "paid_amount must be a number"}
    if amount <= 0:
        return {"error": "paid_amount must be positive"}

    claim["status"] = "paid"
    claim["paid_amount"] = amount
    claim["paid_at"] = _now()
    claim["paid_by"] = paid_by

    ro.attributes["warranty_claim"] = claim
    save_graph(GRAPH_PATH)

    return {**_ro_brief(ro), **claim}


def get_claims_queue(status=None):
    """Real cross-RO warranty claim listing, optionally filtered by claim
    status (draft/submitted/approved/rejected/paid). This is the real
    Submission Workflow work queue, as opposed to service_menu.py's existing
    flat claim-listing (which doesn't carry claim status at all)."""

    entries = []
    for ro in _all_warranty_records():
        claim = _claim_of(ro)
        if status and claim["status"] != status:
            continue
        entries.append({**_ro_brief(ro), **claim, "cost": ro.attributes.get("Cost")})

    entries.sort(key=lambda e: e.get("submitted_at") or "", reverse=True)

    by_status = {}
    for ro in _all_warranty_records():
        s = _claim_of(ro)["status"]
        by_status[s] = by_status.get(s, 0) + 1

    return {"count": len(entries), "by_status": by_status, "claims": entries}


def get_rejected_claims_queue():
    """Sam's own named item -- the real rejected subset, with the real
    rejection reason surfaced so someone can decide whether to resubmit."""
    return get_claims_queue(status="rejected")


def get_warranty_eligibility(vehicle_id):
    """Reuses core/repair_orders.py's real _warranty_status() Condition-based
    inference verbatim, plus one genuine additional real signal: an open
    recall matching this vehicle's exact make/model always makes THAT
    specific repair warranty-eligible, regardless of Condition."""

    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    base = _warranty_status(vehicle)

    vehicle_make = str(vehicle.attributes.get("Make", "")).strip().lower()
    vehicle_model = str(vehicle.attributes.get("Model", "")).strip().lower()

    matching_recalls = [
        {"id": r.id, "recall_number": r.attributes.get("recall_number"), "description": r.attributes.get("description")}
        for r in ledger.get_all().values()
        if r.entity_type == RECALL and r.attributes.get("open")
        and str(r.attributes.get("make", "")).strip().lower() == vehicle_make
        and str(r.attributes.get("model", "")).strip().lower() == vehicle_model
    ]

    return {
        "vehicle_id": vehicle.id,
        "vin": vehicle.attributes.get("VIN"),
        "general_warranty": base,
        "recall_eligible_repairs": matching_recalls,
        "note": "General warranty eligibility is inferred from Vehicle.Condition -- no real factory-warranty database exists in this system. Recall-eligible repairs are real: any open recall matching this vehicle's exact make/model is always covered regardless of Condition.",
    }


def mark_recall_completed(vehicle_id, recall_id, ro_id, completed_by):

    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    recall = ledger.get_entity(recall_id)
    if not recall or recall.entity_type != RECALL:
        return {"error": f"Recall '{recall_id}' not found"}

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    linked = any(r.source_id == vehicle_id and r.target_id == ro_id
                 and r.relationship_type == "HAS_SERVICE_RECORD"
                 for r in ledger.get_relationships())
    if not linked:
        return {"error": "Repair order does not belong to this vehicle"}

    completed = vehicle.attributes.get("completed_recalls") or []
    if any(c.get("recall_id") == recall_id for c in completed):
        return {"error": f"Recall '{recall_id}' is already marked completed for this vehicle"}

    completed.append({
        "recall_id": recall_id,
        "recall_number": recall.attributes.get("recall_number"),
        "ro_id": ro_id,
        "completed_by": completed_by,
        "completed_at": _now(),
    })
    vehicle.attributes["completed_recalls"] = completed
    save_graph(GRAPH_PATH)

    return {"vehicle_id": vehicle.id, "completed_recalls": completed}


def get_recall_management_queue():
    """Reuses core/trigger_alerts.py's real customer-vehicle-ownership
    cross-reference logic (make/model matching against every real open
    recall) rather than a second recall-matching engine, then splits each
    recall's real affected population into needs_repair vs. completed off
    the real completed_recalls tracking this module adds."""

    open_recalls = [r for r in ledger.get_all().values() if r.entity_type == RECALL and r.attributes.get("open")]

    campaigns = []
    total_needs_repair = 0
    total_completed = 0

    for recall in open_recalls:
        recall_make = str(recall.attributes.get("make", "")).strip().lower()
        recall_model = str(recall.attributes.get("model", "")).strip().lower()

        needs_repair = []
        completed = []
        seen_vehicle_ids = set()  # dedupe -- some customers have duplicate OWNS
        # relationships to the same vehicle (a real, pre-existing data-quality quirk
        # confirmed live in this seed graph, same finding as core/service_customers.py's
        # _vehicles_owned() -- without this, the same vehicle can appear twice in
        # needs_repair/completed for one recall).

        for customer in ledger.get_all().values():
            if customer.entity_type != CUSTOMER:
                continue
            owned = [
                ledger.get_entity(r.target_id)
                for r in ledger.get_relationships()
                if r.source_id == customer.id and r.relationship_type == "OWNS"
            ]
            for vehicle in owned:
                if not vehicle or vehicle.entity_type != VEHICLE:
                    continue
                if vehicle.id in seen_vehicle_ids:
                    continue
                if str(vehicle.attributes.get("Make", "")).strip().lower() != recall_make:
                    continue
                if str(vehicle.attributes.get("Model", "")).strip().lower() != recall_model:
                    continue

                seen_vehicle_ids.add(vehicle.id)
                already_done = any(c.get("recall_id") == recall.id for c in (vehicle.attributes.get("completed_recalls") or []))
                brief = {
                    "vehicle_id": vehicle.id,
                    "vin": vehicle.attributes.get("VIN"),
                    "customer_id": customer.id,
                    "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip(),
                }
                (completed if already_done else needs_repair).append(brief)

        total_needs_repair += len(needs_repair)
        total_completed += len(completed)

        campaigns.append({
            "recall_id": recall.id,
            "recall_number": recall.attributes.get("recall_number"),
            "make": recall.attributes.get("make"),
            "model": recall.attributes.get("model"),
            "description": recall.attributes.get("description"),
            "needs_repair": needs_repair,
            "completed": completed,
        })

    return {
        "campaign_count": len(campaigns),
        "total_needs_repair": total_needs_repair,
        "total_completed": total_completed,
        "campaigns": campaigns,
    }
