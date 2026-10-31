"""
core/repair_orders_api.py -- ACL layer for core/repair_orders.py, the RO
Workflow Engine. Viewing an RO/the board is broad (ADMIN/OPERATIONS/SALES/
SERVICE/FINANCE -- Sales cares about a customer's delivery promise, Finance
cares about warranty/cost visibility), same breadth as Vehicle Lifecycle's
view set. Mutating (advancing stage, concerns, estimate/approval, parts,
QC, communication log) is ADMIN/OPERATIONS/SERVICE only -- this is a Service
department's own operational workflow, matching the same narrower mutate
set most department-specific workflow engines use (Vehicle Lifecycle,
Inventory Aging, Lot Control).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE
from core.repair_orders import (
    create_repair_order, advance_stage, add_concern, resolve_concern,
    send_estimate, record_customer_approval, update_parts_status,
    request_part, update_part_request_status, update_qc_item,
    log_ro_communication, get_ro_workspace, get_ro_board, get_catalog,
    get_stage_counts, assign_technician, record_return_review, record_return_handover, plan_return_followup, complete_return_followup,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, SERVICE, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, SERVICE)


def _denied():
    return {"error": "You don't have access to the RO Workflow Engine"}


# Pillar 4 slice 4d (2026-07-23): feed the Service team agent the RO's real lifecycle
# steps so it mines genuine multi-step service workflows (same pattern as the deal feed
# in core/deals_api.py). Recorded HERE because this is where the actor (employee_id) is
# known. All steps share workflow_key=ro_id, so a service advisor's repeated steps chain
# into one ordered sequence the miner can recognize. Best-effort and fully isolated: an
# observation signal must NEVER break a real RO action -- an errored result is skipped and
# any exception swallowed.
def _record_step(employee_id, workflow_key, action_key, step_label, result):
    if isinstance(result, dict) and result.get("error"):
        return
    if not workflow_key:
        return
    try:
        from core.bot_fleet import record_workflow_step

        record_workflow_step("service", employee_id, action_key, step_label=step_label, workflow_key=workflow_key)
    except Exception:
        pass


def get_catalog_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_catalog()


def get_ro_board_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_ro_board()


def get_stage_counts_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_stage_counts()


def get_ro_workspace_api(role, ro_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_ro_workspace(ro_id)


def create_repair_order_api(role, employee_id, vehicle_id, customer_id, description, pay_type="Customer Pay", preferred_contact_method=None):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = create_repair_order(vehicle_id, customer_id, description, employee_id, pay_type=pay_type, preferred_contact_method=preferred_contact_method)
    _record_step(employee_id, result.get("id") if isinstance(result, dict) else None, "create_ro", "Created a repair order", result)
    return result


def advance_stage_api(role, employee_id, ro_id, new_stage):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = advance_stage(ro_id, new_stage, employee_id)
    _record_step(employee_id, ro_id, "advance_stage", f"Advanced the RO to {new_stage}", result)
    return result


def add_concern_api(role, employee_id, ro_id, description, occurs_at=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = add_concern(ro_id, description, employee_id, occurs_at=occurs_at)
    _record_step(employee_id, ro_id, "add_concern", "Added a customer concern", result)
    return result


def resolve_concern_api(role, employee_id, ro_id, concern_id, resolution_notes="", outcome="resolved"):
    if role not in _MUTATE_ROLES:
        return _denied()
    return resolve_concern(ro_id, concern_id, employee_id, resolution_notes=resolution_notes, outcome=outcome)


def send_estimate_api(role, employee_id, ro_id, amount):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = send_estimate(ro_id, amount, employee_id)
    _record_step(employee_id, ro_id, "send_estimate", "Sent the estimate", result)
    return result


def record_customer_approval_api(role, employee_id, ro_id, approved, decline_reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = record_customer_approval(ro_id, approved, employee_id, decline_reason=decline_reason)
    _record_step(employee_id, ro_id, "customer_approval", "Recorded the customer's approval decision", result)
    return result


def update_parts_status_api(role, employee_id, ro_id, status, notes=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_parts_status(ro_id, status, employee_id, notes=notes)


def request_part_api(role, employee_id, ro_id, description):
    if role not in _MUTATE_ROLES:
        return _denied()
    return request_part(ro_id, description, employee_id)


def update_part_request_status_api(role, employee_id, ro_id, request_id, status):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_part_request_status(ro_id, request_id, status, employee_id)


def update_qc_item_api(role, employee_id, ro_id, item, complete):
    if role not in _MUTATE_ROLES:
        return _denied()
    return update_qc_item(ro_id, item, complete, employee_id)


def log_ro_communication_api(role, employee_id, ro_id, channel, body):
    if role not in _MUTATE_ROLES:
        return _denied()
    return log_ro_communication(ro_id, channel, body, employee_id)


def assign_technician_api(role, employee_id, ro_id, technician_id):
    if role not in _MUTATE_ROLES:
        return _denied()
    return assign_technician(ro_id, technician_id, employee_id)


def record_return_review_api(role, employee_id, ro_id, transport, notes, acknowledged):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_return_review(ro_id, employee_id, transport, notes, acknowledged)


def record_return_handover_api(role, employee_id, ro_id, recipient, settlement_reference, confirmed):
    if role not in _MUTATE_ROLES:
        return _denied()
    return record_return_handover(ro_id, employee_id, recipient, settlement_reference, confirmed)


def plan_return_followup_api(role, employee_id, ro_id, due_date, next_action):
    if role not in _MUTATE_ROLES:
        return _denied()
    return plan_return_followup(ro_id, employee_id, due_date, next_action)


def complete_return_followup_api(role, employee_id, ro_id, outcome, expected_updated_at):
    if role not in _MUTATE_ROLES:
        return _denied()
    return complete_return_followup(ro_id, employee_id, outcome, expected_updated_at)
