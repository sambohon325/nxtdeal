"""
Thin API-layer functions for the DMS Deal Desk (session 33), imported directly into
api/app.py's route handlers -- same "no service layer indirection" convention every
other `*_api.py` module in this codebase follows. ACL checks live here (not in
core/deals.py), mirroring core/assets_api.py/core/campaigns_api.py/core/websites_api.py.

Role rule -- narrower than the marketing-suite workflows on purpose, since a Deal
touches real pricing and eventually a real FinanceContract: SALES can desk a deal
(create it, build/select scenarios) alongside ADMIN/OPERATIONS/FINANCE, but only
ADMIN/OPERATIONS/FINANCE can move financing forward, generate the contract, or fund it
-- F&I is gated the same way core/permissions.py's DASHBOARD_ACCESS["finance"] already
excludes SALES.
"""

from core.deals import (
    create_deal,
    get_deal,
    add_scenario,
    remove_scenario,
    select_scenario,
    choose_in_house_financing,
    submit_to_lender,
    record_lender_decision,
    accept_countered_terms,
    update_trade_appraisal,
    decode_trade_in_vin,
    approve_trade_appraisal,
    update_delivery_checklist,
    generate_contract,
    fund_deal,
    cancel_deal,
    list_deals,
    list_pending_financing,
    list_lenders,
)
from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH
from core.entities import Entity
from core.entity_types import DEAL, CUSTOMER, VEHICLE
from core.compliance import enforce_gate


_FI_ROLES = (ADMIN, OPERATIONS, FINANCE)

# Whole-board visibility -- sales.pdf's "Deal Collaboration: Salesperson Manager F&I
# all work on same record." Anyone on this list can SEE any deal on the board;
# editing/advancing a specific deal stays gated to that deal's own creator (or F&I
# roles) by each action function below, unchanged from session 33.
_BOARD_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)


def _customer_brief(customer_id):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return None

    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
        "email": customer.attributes.get("Email"),
        "phone": customer.attributes.get("Phone"),
        "credit_score": customer.attributes.get("CreditScore"),
    }


def _vehicle_brief(vehicle_id):

    vehicle = ledger.get_entity(vehicle_id)

    if not vehicle or vehicle.entity_type != VEHICLE:
        return None

    price = vehicle.attributes.get("Price")
    cost = vehicle.attributes.get("Cost")

    gross = None
    try:
        if price is not None and cost is not None:
            gross = round(float(price) - float(cost), 2)
    except (TypeError, ValueError):
        gross = None

    return {
        "id": vehicle.id,
        "description": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() or vehicle.id,
        "vin": vehicle.attributes.get("VIN"),
        "trim": vehicle.attributes.get("Trim"),
        "price": price,
        "cost": cost,
        "gross": gross,
    }


def _blocked_response(gate):
    return {
        "error": "Compliance check failed -- this can't go through until the issue(s) below are corrected.",
        "compliance_alert_id": gate["alert_id"],
        "compliance_violations": gate["violations"],
        "notice": gate["notice"],
    }


def _serialize_deal(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def _serialize_deal_enriched(entity):
    """Same shape as _serialize_deal, plus live-resolved customer/vehicle briefs --
    what the Pipeline board's cards and the Deal Worksheet actually need to render
    without a separate round-trip per deal. No parallel copy stored on the Deal
    itself -- resolved fresh from the graph every call, same rule as
    core/social_posts.py's resolve_linked_vehicles()."""

    data = _serialize_deal(entity)
    data["customer"] = _customer_brief(entity.attributes.get("customer_id"))
    data["vehicle"] = _vehicle_brief(entity.attributes.get("vehicle_id"))

    return data


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _can_do_financing(role):
    return role in _FI_ROLES


# Pillar 4 slice 4c (2026-07-23): feed the team agents the deal's real lifecycle steps
# so they mine genuine multi-step workflows (create_deal alone -- recorded in
# core/deals.py -- is a 1-step sequence, below MIN_WORKFLOW_OCCURRENCES). Recorded HERE
# at the API layer because this is where the actor (employee_id) is known; the core
# lifecycle fns (add_scenario/select_scenario/fund_deal/...) don't carry it. All steps
# share workflow_key=deal_id, so per (actor, deal) they chain into one ordered sequence
# and the miner recognizes a sequence a rep/desk actually repeats across deals. Desking
# steps go to the SALES agent, F&I/funding steps to the FINANCE agent -- the same team
# split _FI_ROLES already encodes. Best-effort and fully isolated: an observation signal
# must NEVER break a real deal action, so any failure here is swallowed.
def _record_step(section, employee_id, deal_id, action_key, step_label):
    try:
        from core.bot_fleet import record_workflow_step

        record_workflow_step(
            section, employee_id, action_key, step_label=step_label, workflow_key=deal_id
        )
    except Exception:
        pass


def list_lenders_api():

    return [
        {"id": lender.id, "name": lender.attributes.get("Name", lender.id)}
        for lender in list_lenders()
    ]


def create_deal_api(role, employee_id, customer_id, vehicle_id, trade_in=None):
    """Desking a new deal -- same _BOARD_VIEW_ROLES gate (ADMIN/OPERATIONS/SALES/
    FINANCE) this module's own docstring already states ("SALES can desk a deal
    (create it, build/select scenarios) alongside ADMIN/OPERATIONS/FINANCE"), matching
    add_scenario_api/remove_scenario_api/select_scenario_api's own role check exactly.
    Found genuinely missing (2026-07-19) by the Code Auditor's missing_acl_gate rule --
    this was the one function in the whole Deal Desk module with no role gate at all,
    meaning any authenticated employee of any role (e.g. MARKETING) could previously
    create a Deal."""

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "Only Sales/Operations/Finance/Admin can desk a new deal"}

    result = create_deal(customer_id, vehicle_id, employee_id, trade_in)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def add_scenario_api(role, employee_id, deal_id, label, sale_price, down_payment, term_months):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can edit this deal"}

    result = add_scenario(deal_id, label, sale_price, down_payment, term_months)

    if _is_error(result):
        return result

    _record_step("sales", employee_id, deal_id, "add_scenario", "Added a pricing scenario")

    return _serialize_deal_enriched(result)


def remove_scenario_api(role, employee_id, deal_id, scenario_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can edit this deal"}

    result = remove_scenario(deal_id, scenario_id)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def select_scenario_api(role, employee_id, deal_id, scenario_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can edit this deal"}

    result = select_scenario(deal_id, scenario_id)

    if _is_error(result):
        return result

    _record_step("sales", employee_id, deal_id, "select_scenario", "Selected a scenario")

    return _serialize_deal_enriched(result)


def choose_in_house_financing_api(role, employee_id, deal_id):

    if not _can_do_financing(role):
        return {"error": "You don't have access to move financing forward on this deal"}

    result = choose_in_house_financing(deal_id)

    if _is_error(result):
        return result

    _record_step("finance", employee_id, deal_id, "choose_financing", "Chose in-house financing")

    return _serialize_deal_enriched(result)


def submit_to_lender_api(role, employee_id, deal_id, lender_id):

    if not _can_do_financing(role):
        return {"error": "You don't have access to submit this deal to a lender"}

    result = submit_to_lender(deal_id, lender_id)

    if _is_error(result):
        return result

    _record_step("finance", employee_id, deal_id, "submit_to_lender", "Submitted to a lender")

    return _serialize_deal_enriched(result)


def record_lender_decision_api(role, employee_id, deal_id, decision, countered_terms=None, notes=None):

    if not _can_do_financing(role):
        return {"error": "You don't have access to record a lender decision"}

    if decision == "declined":

        # Compliance check (ECOA/Reg B, session 38) runs against the PENDING decision --
        # a lightweight, unpersisted Entity built from the current deal plus what this
        # decline would set -- so a declined financing decision never gets recorded at
        # all without a documented reason, rather than recording it and flagging it
        # after the fact.
        deal = get_deal(deal_id)

        if not deal:
            return {"error": "Deal not found"}

        pending_attributes = dict(deal.attributes)
        pending_attributes["financing_status"] = "declined"
        pending_attributes["financing_notes"] = notes

        gate = enforce_gate("deal_decline", Entity(id=deal_id, entity_type=DEAL, attributes=pending_attributes))

        if gate["blocked"]:
            return _blocked_response(gate)

    result = record_lender_decision(deal_id, decision, countered_terms, notes)

    if _is_error(result):
        return result

    audit_log.record(
        event_type="deal_financing_decision",
        summary=f"Deal {deal_id} financing {decision} by {employee_id}",
        entity_id=deal_id,
        actor=employee_id,
        details={"decision": decision},
    )
    save_audit_log(AUDIT_PATH)

    _record_step("finance", employee_id, deal_id, "lender_decision", f"Recorded lender decision: {decision}")

    return _serialize_deal_enriched(result)


def accept_countered_terms_api(role, employee_id, deal_id):

    if not _can_do_financing(role):
        return {"error": "You don't have access to accept countered terms on this deal"}

    result = accept_countered_terms(deal_id)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def generate_contract_api(role, employee_id, deal_id):

    if not _can_do_financing(role):
        return {"error": "You don't have access to generate this deal's contract"}

    result = generate_contract(deal_id)

    if _is_error(result):
        return result

    _record_step("finance", employee_id, deal_id, "generate_contract", "Generated the contract")

    return _serialize_deal_enriched(result)


def fund_deal_api(role, employee_id, deal_id):

    if not _can_do_financing(role):
        return {"error": "You don't have access to fund this deal"}

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    # Release readiness precedes deal-specific checks; a rules override cannot
    # authorize execution of the current estimate worksheet.
    from core.contracting_readiness import execution_block
    blocked = execution_block("deal_fund")
    if blocked:
        return blocked

    # Compliance agent (session 38) -- runs on every real sale before funding.
    # Reg Z (contract disclosure) + Red Flags Rule (customer identity completeness).
    # Sam: "If it fails a compliance review it needs to be flagged, stopped, and not
    # allowed to go through until the corrections are made."
    gate = enforce_gate("deal_fund", deal)

    if gate["blocked"]:
        return _blocked_response(gate)

    result = fund_deal(deal_id)

    if _is_error(result):
        return result

    audit_log.record(
        event_type="deal_funded",
        summary=f"Deal {deal_id} funded by {employee_id}",
        entity_id=deal_id,
        actor=employee_id,
        details={"finance_contract_id": result.attributes.get("finance_contract_id")},
    )
    save_audit_log(AUDIT_PATH)

    _record_step("finance", employee_id, deal_id, "fund_deal", "Funded the deal")

    return _serialize_deal_enriched(result)


def cancel_deal_api(role, employee_id, deal_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can cancel this deal"}

    result = cancel_deal(deal_id)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def get_deal_api(role, employee_id, deal_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    # Board-wide read access (see _BOARD_VIEW_ROLES above) -- viewing a deal is not
    # the same permission as acting on it, which every action function above still
    # gates to that deal's own creator or an F&I role.
    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to this deal"}

    return _serialize_deal_enriched(deal)


def list_my_deals_api(employee_id):

    return [_serialize_deal_enriched(d) for d in list_deals(created_by=employee_id)]


def list_all_deals_api(role, status=None):
    """The Pipeline board's real data source -- sales.pdf's "Deal Collaboration"
    (salesperson/manager/F&I "all work on same record") means the board itself has
    to show every deal, not just the viewer's own. Editing a specific deal stays
    gated per-deal by the action functions above -- this only controls whether the
    board's read is visible at all."""

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to the deal pipeline board"}

    return [_serialize_deal_enriched(d) for d in list_deals(status=status)]


def list_pending_financing_api(role):

    if not _can_do_financing(role):
        return {"error": "You don't have access to the financing decision queue"}

    return [_serialize_deal_enriched(d) for d in list_pending_financing()]


def update_trade_appraisal_api(role, employee_id, deal_id, patch):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can edit this deal's trade appraisal"}

    result = update_trade_appraisal(deal_id, employee_id, patch or {})

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def decode_trade_in_vin_api(role, deal_id, attempt_live=True):
    """NXTDeal VIN Intelligence, Phase 2: read-only, non-mutating decision
    support, so this uses the broader board-view role set (same access as
    just viewing the deal itself), not the narrower creator-or-F&I edit gate
    update_trade_appraisal_api above enforces -- nothing is written back to
    the deal, and anyone who can already see the deal can already see
    everything this returns."""

    if role not in _BOARD_VIEW_ROLES:
        return {"error": "You don't have access to view this deal's trade-in VIN decode."}

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    return decode_trade_in_vin(deal_id, attempt_live=attempt_live)


def approve_trade_appraisal_api(role, employee_id, deal_id):
    """Manager-level approval only -- deliberately narrower than the creator-or-F&I
    edit rule above, since the whole point is a second set of eyes distinct from
    whoever entered the numbers."""

    if not _can_do_financing(role):
        return {"error": "Only F&I/admin can approve a trade appraisal"}

    result = approve_trade_appraisal(deal_id, employee_id)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)


def update_delivery_checklist_api(role, employee_id, deal_id, section, patch):
    """Same creator-or-F&I edit gate as update_trade_appraisal_api -- the sales rep
    handling the delivery, or F&I/admin, not the whole board-view roster."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("created_by") != employee_id and role not in _FI_ROLES:
        return {"error": "Only the deal's creator (or F&I/admin) can edit this deal's delivery checklist"}

    result = update_delivery_checklist(deal_id, section, patch or {}, employee_id)

    if _is_error(result):
        return result

    return _serialize_deal_enriched(result)
