"""
Seeds a handful of real, in-flight repair orders spanning several real RO
Workflow Engine stages -- every one of this seed graph's 434 imported
ServiceRecords is a flat historical row already Status="Completed" (see
core/repair_orders.py's module docstring), so without this, the new RO
Workflow Engine's Kanban board would show nothing outside "Follow-Up" until
a person manually created a live RO through the UI.

Same discipline as imports/seed_operational.py: calls the real
core.repair_orders functions directly (create_repair_order/advance_stage/
add_concern/send_estimate/record_customer_approval/update_parts_status),
not a flat Entity(attributes=dict(row)) import, so every real invariant
those functions enforce (stage validation, the QC-gated ready-for-pickup
computation, etc.) runs for real -- exactly as if an advisor had clicked
through the RO Workspace. Called from run_seed_import.py, after vehicles/
customers are already loaded (looks them up by graph id directly since,
unlike the flat CSV importers, this doesn't need business-key resolution).
"""

from core.dealeros import ledger
from core.entity_types import VEHICLE, CUSTOMER
from core.repair_orders import (
    create_repair_order, advance_stage, add_concern, send_estimate,
    record_customer_approval, update_parts_status,
)

SERVICE_ADVISOR = "EMP-00029"


def _vehicle_customer_pairs(n):
    """Picks n distinct (vehicle_id, customer_id) pairs from the seed graph --
    doesn't matter whether the vehicle/customer are actually linked to each
    other in reality, this is demo scaffolding for the Kanban board, not a
    claim about real ownership history."""
    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE]
    customers = [e for e in ledger.get_all().values() if e.entity_type == CUSTOMER]
    pairs = []
    for i in range(n):
        pairs.append((vehicles[i + 1].id, customers[i + 1].id))
    return pairs


def run():

    pairs = _vehicle_customer_pairs(4)
    created = 0

    # 1. Fresh Check-In -- no advance, straight off create_repair_order().
    vid, cid = pairs[0]
    create_repair_order(vid, cid, "Customer reports a burning smell after highway driving", SERVICE_ADVISOR, pay_type="Customer Pay")
    created += 1

    # 2. Inspection, with an extra concern logged.
    vid, cid = pairs[1]
    ro = create_repair_order(vid, cid, "Squeaking brakes", SERVICE_ADVISOR, pay_type="Customer Pay")
    advance_stage(ro["id"], "RO Written", SERVICE_ADVISOR)
    advance_stage(ro["id"], "Inspection", SERVICE_ADVISOR)
    add_concern(ro["id"], "Also requesting a multi-point inspection while it's in", SERVICE_ADVISOR)
    created += 1

    # 3. Waiting Approval -- estimate sent, not yet approved.
    vid, cid = pairs[2]
    ro = create_repair_order(vid, cid, "40,000 mile scheduled maintenance", SERVICE_ADVISOR, pay_type="Customer Pay")
    advance_stage(ro["id"], "RO Written", SERVICE_ADVISOR)
    advance_stage(ro["id"], "Inspection", SERVICE_ADVISOR)
    advance_stage(ro["id"], "Estimate", SERVICE_ADVISOR)
    send_estimate(ro["id"], 425.00, SERVICE_ADVISOR)
    advance_stage(ro["id"], "Customer Approval", SERVICE_ADVISOR)
    created += 1

    # 4. Waiting Parts -- approved, backordered part.
    vid, cid = pairs[3]
    ro = create_repair_order(vid, cid, "Transmission concern -- hesitates on upshift", SERVICE_ADVISOR, pay_type="Warranty")
    advance_stage(ro["id"], "RO Written", SERVICE_ADVISOR)
    advance_stage(ro["id"], "Inspection", SERVICE_ADVISOR)
    advance_stage(ro["id"], "Estimate", SERVICE_ADVISOR)
    send_estimate(ro["id"], 1850.00, SERVICE_ADVISOR)
    advance_stage(ro["id"], "Customer Approval", SERVICE_ADVISOR)
    record_customer_approval(ro["id"], True, SERVICE_ADVISOR)
    advance_stage(ro["id"], "Parts", SERVICE_ADVISOR)
    update_parts_status(ro["id"], "backordered", SERVICE_ADVISOR, notes="Transmission solenoid on backorder from OEM")
    created += 1

    return created
