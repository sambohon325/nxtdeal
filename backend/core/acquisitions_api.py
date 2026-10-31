"""
core/acquisitions_api.py -- ACL layer for core/acquisitions.py. Viewing is
broad (the same set used across this Inventory rebuild -- every department
that touches a vehicle before it's on the lot cares about the buying
pipeline). Creating/evaluating a request (the Buyer role in Sam's spec) is
ADMIN/OPERATIONS/FINANCE -- Finance genuinely cares about acquisition cost
risk, matching the FINANCE addition core/vehicle_lifecycle_api.py made for
Cost Breakdown. The two-step approval chain is narrower and asymmetric on
purpose, matching Sam's own "Buyer -> Inventory Manager -> General Manager"
sign-off: Inventory Manager approval is ADMIN/OPERATIONS, final GM approval is
ADMIN-only (this codebase has no separate "General Manager" role -- ADMIN is
the closest real analog, same convention core/sales_overview.py's manager-tier
inference already uses elsewhere for a role this system doesn't model 1:1).
"""

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.acquisitions import (
    create_acquisition_request, get_acquisition_request, list_acquisition_requests,
    record_price_risk, record_recon_estimate, record_market_review, submit_for_approval,
    approve_by_inventory_manager, approve_by_gm, reject_request, mark_purchased,
    get_acquisitions_summary, get_market_signal, get_buy_recommendation, get_factory_allocations,
    decode_and_prefill_acquisition_vin,
    SOURCE_TYPES, DIRECT_PURCHASE_CHANNELS, ALL_STAGES,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
_EVALUATE_ROLES = (ADMIN, OPERATIONS, FINANCE)
_IM_APPROVE_ROLES = (ADMIN, OPERATIONS)
_GM_APPROVE_ROLES = (ADMIN,)


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _denied():
    return {"error": "You don't have access to Acquisitions"}


# Pillar 4 slice 4d (2026-07-23): feed the Inventory team agent the acquisition request's
# real lifecycle steps so it mines genuine multi-step buying workflows (same pattern as
# core/deals_api.py / core/repair_orders_api.py). Recorded HERE because this is where the
# actor (employee_id) is known. All steps share workflow_key=request_id, so a buyer's
# repeated steps chain into one ordered sequence the miner can recognize. Best-effort and
# fully isolated: an observation signal must NEVER break a real acquisition action -- an
# errored result is skipped and any exception swallowed.
def _record_step(employee_id, workflow_key, action_key, step_label, result):
    if _is_error(result):
        return
    if not workflow_key:
        return
    try:
        from core.bot_fleet import record_workflow_step

        record_workflow_step("inventory", employee_id, action_key, step_label=step_label, workflow_key=workflow_key)
    except Exception:
        pass


def get_catalog_api():
    return {"source_types": list(SOURCE_TYPES), "direct_purchase_channels": list(DIRECT_PURCHASE_CHANNELS), "stages": list(ALL_STAGES)}


def create_acquisition_request_api(role, employee_id, source_type, year=None, make=None, model=None,
                                    trim=None, mileage=None, vin=None, estimated_acv=None,
                                    direct_purchase_channel=None, linked_deal_id=None,
                                    linked_auction_transaction_id=None, notes=""):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = create_acquisition_request(
        source_type, employee_id, year=year, make=make, model=model, trim=trim, mileage=mileage,
        vin=vin, estimated_acv=estimated_acv, direct_purchase_channel=direct_purchase_channel,
        linked_deal_id=linked_deal_id, linked_auction_transaction_id=linked_auction_transaction_id,
        notes=notes,
    )
    _record_step(employee_id, result.get("id") if isinstance(result, dict) else None, "create_request", "Created an acquisition request", result)
    return result


def get_acquisition_request_api(role, request_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_acquisition_request(request_id)


def list_acquisition_requests_api(role, source_type=None, stage=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return list_acquisition_requests(source_type=source_type, stage=stage)


def record_price_risk_api(role, employee_id, request_id, risk_level, notes=""):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = record_price_risk(request_id, employee_id, risk_level, notes=notes)
    _record_step(employee_id, request_id, "record_price_risk", "Recorded price/risk", result)
    return result


def record_recon_estimate_api(role, employee_id, request_id, recon_estimate, notes=""):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = record_recon_estimate(request_id, employee_id, recon_estimate, notes=notes)
    _record_step(employee_id, request_id, "record_recon_estimate", "Recorded a recon estimate", result)
    return result


def record_market_review_api(role, employee_id, request_id, notes=""):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = record_market_review(request_id, employee_id, notes=notes)
    _record_step(employee_id, request_id, "record_market_review", "Recorded a market review", result)
    return result


def submit_for_approval_api(role, employee_id, request_id):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = submit_for_approval(request_id, employee_id)
    _record_step(employee_id, request_id, "submit_for_approval", "Submitted for approval", result)
    return result


def approve_by_inventory_manager_api(role, employee_id, request_id, notes=""):
    if role not in _IM_APPROVE_ROLES:
        return {"error": "You don't have access to Inventory Manager approval"}
    result = approve_by_inventory_manager(request_id, employee_id, notes=notes)
    _record_step(employee_id, request_id, "im_approve", "Inventory-manager approval", result)
    return result


def approve_by_gm_api(role, employee_id, request_id, notes=""):
    if role not in _GM_APPROVE_ROLES:
        return {"error": "You don't have access to final (GM) approval"}
    result = approve_by_gm(request_id, employee_id, notes=notes)
    _record_step(employee_id, request_id, "gm_approve", "GM final approval", result)
    return result


def reject_request_api(role, employee_id, request_id, reason):
    if role not in _IM_APPROVE_ROLES:
        return _denied()
    result = reject_request(request_id, employee_id, reason)
    _record_step(employee_id, request_id, "reject_request", "Rejected the request", result)
    return result


def mark_purchased_api(role, employee_id, request_id, vehicle_id=None):
    if role not in _EVALUATE_ROLES:
        return _denied()
    result = mark_purchased(request_id, employee_id, vehicle_id=vehicle_id)
    _record_step(employee_id, request_id, "mark_purchased", "Marked as purchased", result)
    return result


def get_acquisitions_summary_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_acquisitions_summary()


def get_buy_recommendation_api(role, make, model, year, estimated_acv=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_buy_recommendation(make, model, year, estimated_acv=estimated_acv)


def get_factory_allocations_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_factory_allocations()


def decode_and_prefill_acquisition_vin_api(role, employee_id, request_id, attempt_live=True):
    if role not in _EVALUATE_ROLES:
        return _denied()
    return decode_and_prefill_acquisition_vin(request_id, employee_id, attempt_live=attempt_live)
