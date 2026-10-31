"""
My Garage — verify-token-scoped customer data (App Suite roadmap Phase 4 + 7 data, 2026-08-03).

The My Garage customer app is no-login: a customer proves who they are through the same
tiered NXTDeal Verify flow the start-your-deal-online journey uses (an OTP to their email
or phone = Verified Human). This module turns that verified session into the customer's OWN
data — vehicles + equity, service history, and their message thread — so the app can show
real PII safely behind the verification gate.

Security posture (mirrors core/customer_accounts.py's match-and-verify):
  * Only a Verified-Human-or-above session may see any data (the OTP has proven the caller
    controls that email/phone).
  * The verified contact is matched to a real Customer via customer_accounts._find_matching_
    customer (email-first, exact). Matching a *verified* contact is defensible precisely
    because the OTP already proved ownership of it.
  * The match is linked back onto the session (link_subject) so subsequent calls are direct,
    and a returning customer with an existing link skips matching entirely.
  * A verified session with no matching Customer on file returns an honest "no account found
    yet" — never another customer's data, never fabricated records.
"""

from datetime import datetime, timezone

from core import dealeros_verify as verify
from core.customer_accounts import _find_matching_customer
from core.entity_types import CUSTOMER, VEHICLE
from core.dealeros import ledger
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _now():
    return datetime.now(timezone.utc).isoformat()


def _resolve_customer(token):
    """(customer_id, None) for a verified session that resolves to a real Customer, else
    (None, error_dict). error_dict['reason'] is 'token' / 'unverified' / 'no_match'."""
    entity = verify._find_by_token(token)
    if not entity:
        return None, {"error": "Invalid or unknown verification token", "reason": "token"}

    a = entity.attributes
    tier = verify.get_verification(entity.id)["tier"]
    if verify.TIER_RANK.get(tier, 0) < verify.TIER_RANK[verify.TIER_VERIFIED_HUMAN]:
        return None, {"error": "Verify your email or phone to view your account.", "reason": "unverified"}

    # 1) Honor an existing confirmed link.
    linked = a.get("linked_entity_id")
    if linked:
        e = ledger.get_entity(linked)
        if e and e.entity_type == CUSTOMER:
            return linked, None

    # 2) Match the verified contact to a Customer (owners only — a Lead has no garage).
    match = _find_matching_customer(a.get("email"), a.get("phone"))
    if match and match.entity_type == CUSTOMER:
        verify.link_subject(entity.id, match.id)
        return match.id, None

    return None, {
        "error": "We couldn't find an account matching your verified contact yet.",
        "reason": "no_match",
    }


def _customer_public(customer_id):
    c = ledger.get_entity(customer_id)
    if not c:
        return None
    a = c.attributes
    return {
        "id": c.id,
        "name": f"{a.get('FirstName', '')} {a.get('LastName', '')}".strip() or a.get("name") or c.id,
    }


def get_my_vehicles(token):
    """The verified customer's owned vehicles, their equity position, and a service-history
    summary — the My Garage home."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err

    from core import service_customers, equity_center

    c360 = service_customers.get_customer_360(customer_id)
    vehicles = (c360.get("vehicles_owned") or {}).get("vehicles", []) if isinstance(c360, dict) else []
    service = (c360.get("service_history") or {}) if isinstance(c360, dict) else {}

    try:
        equity = equity_center.get_equity_position(customer_id)
    except ValueError:
        equity = {"equity_amount": None, "status": "unknown"}

    return {
        "customer": _customer_public(customer_id),
        "vehicles": vehicles,
        "vehicle_count": len(vehicles),
        "equity": {
            "equity_amount": equity.get("equity_amount"),
            "status": equity.get("status"),
            "estimated_value": equity.get("estimated_value"),
            "estimated_payoff": equity.get("estimated_payoff"),
            "lease_maturing_soon": equity.get("lease_maturing_soon"),
            "is_estimated": True,
            "disclaimer": equity.get("disclaimer"),
        },
        "service_summary": {
            "count": service.get("count", 0),
            "recent": (service.get("records") or [])[:5],
        },
    }


def get_my_service_history(token):
    """The verified customer's full service history."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err
    from core import service_customers
    c360 = service_customers.get_customer_360(customer_id)
    service = (c360.get("service_history") or {}) if isinstance(c360, dict) else {}
    declined = (c360.get("declined_services") or {}) if isinstance(c360, dict) else {}
    return {
        "customer": _customer_public(customer_id),
        "count": service.get("count", 0),
        "records": service.get("records", []),
        "declined_services": declined.get("records", []) if isinstance(declined, dict) else [],
    }


def get_my_messages(token):
    """The verified customer's conversation thread with the dealership (calls/texts/
    appointments unified) — the Phase 4 one-thread-across-channels view, customer side."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err
    from core import customer_comms
    convo = customer_comms.get_conversation(customer_id)
    if isinstance(convo, dict) and convo.get("error"):
        return {"customer": _customer_public(customer_id), "timeline": []}
    return {
        "customer": _customer_public(customer_id),
        "timeline": convo.get("timeline", []) if isinstance(convo, dict) else [],
    }


# ---------------------------------------------------------------------------
# Approvals + Status (the last two My Garage customer screens, 2026-08-03).
# Both key off the verified customer and scope strictly to the customer's own repair
# orders (their AUTHORIZED edges via service_customers._service_records_for). Every
# mutation re-checks the target RO belongs to the resolved customer before touching it.
# ---------------------------------------------------------------------------

def _my_ros(customer_id):
    from core import service_customers
    return service_customers._service_records_for(customer_id)


def _owns_ro(customer_id, ro_id):
    return any(r.id == ro_id for r in _my_ros(customer_id))


def _ro_vehicle_label(ro):
    vin = ro.attributes.get("VIN")
    if vin:
        for v in ledger.get_all().values():
            if v.entity_type == VEHICLE and v.attributes.get("VIN") == vin:
                label = f"{v.attributes.get('Year', '')} {v.attributes.get('Make', '')} {v.attributes.get('Model', '')}".strip()
                if label:
                    return label
    return vin or "Your vehicle"


def get_my_approvals(token):
    """Repair orders on the customer's account that need their attention: an estimate
    awaiting approval, or an approved estimate not yet paid."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err

    items = []
    for ro in _my_ros(customer_id):
        est = ro.attributes.get("estimate")
        if not est:
            continue
        approved = est.get("approved")
        paid = bool((ro.attributes.get("payment") or {}).get("paid"))
        if approved is None or (approved is True and not paid):
            open_concerns = [c for c in (ro.attributes.get("concerns") or []) if c.get("status") == "open"]
            items.append({
                "ro_id": ro.id,
                "service_number": ro.attributes.get("ServiceNumber", ro.id),
                "description": ro.attributes.get("Description"),
                "vehicle": _ro_vehicle_label(ro),
                "estimate_amount": est.get("amount"),
                "estimate_status": "pending" if approved is None else "approved",
                "paid": paid,
                "concerns": [{"description": c.get("description")} for c in open_concerns],
            })

    return {"customer": _customer_public(customer_id), "approvals": items, "count": len(items)}


def respond_to_approval(token, ro_id, approved, decline_reason=""):
    """Customer approves or declines the estimate on one of THEIR repair orders."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err
    if not _owns_ro(customer_id, ro_id):
        return {"error": "That repair order isn't on your account."}

    from core import repair_orders
    result = repair_orders.record_customer_approval(ro_id, bool(approved), "customer_via_garage", decline_reason=decline_reason or "")
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "ro_id": ro_id, "approved": bool(approved)}


def pay_my_ro(token, ro_id, method="card"):
    """Pay an approved estimate on one of the customer's repair orders. RO pay has no loan,
    so it routes through the payments seam (integrations_registry.charge_deposit) — honestly
    simulated until a payments provider is connected — and stamps a payment record on the RO."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err
    if not _owns_ro(customer_id, ro_id):
        return {"error": "That repair order isn't on your account."}

    ro = ledger.get_entity(ro_id)
    est = ro.attributes.get("estimate") or {}
    if est.get("approved") is not True:
        return {"error": "This estimate hasn't been approved yet."}
    if (ro.attributes.get("payment") or {}).get("paid"):
        return {"error": "This repair order is already paid."}

    amount = est.get("amount")
    from core import integrations_registry
    dispatch = integrations_registry.charge_deposit(amount, reference=ro_id)
    # A returned adapter payload is not itself proof of collection. Pending,
    # declined and malformed responses must leave the repair order unpaid.
    if (not isinstance(dispatch, dict) or dispatch.get("error")
            or dispatch.get("ok") is False
            or dispatch.get("status") != "collected"
            or not isinstance(dispatch.get("simulated"), bool)):
        return {"error": "Payment could not be confirmed. Check with the service desk before retrying."}
    ro.attributes["payment"] = {
        "paid": True,
        "amount": amount,
        "method": method,
        "provider": dispatch.get("provider"),
        "simulated": bool(dispatch.get("simulated")),
        "reference": dispatch.get("reference"),
        "paid_at": _now(),
        "paid_via": "garage",
    }
    save_graph(GRAPH_PATH)
    return {
        "ok": True,
        "ro_id": ro_id,
        "amount": amount,
        "mode": "live" if not dispatch.get("simulated") else "simulated",
    }


def get_my_status(token):
    """Live status of the customer's active repair orders — where each vehicle is in the
    service process (stage + progress), the technician, and a recent timeline."""
    customer_id, err = _resolve_customer(token)
    if err:
        return err

    from core import repair_orders
    active = []
    for ro in _my_ros(customer_id):
        stage = repair_orders._stage_of(ro)
        if ro.attributes.get("Status") == "Completed" and stage == "Follow-Up":
            continue  # delivered / done — not "active"
        ws = repair_orders.get_ro_workspace(ro.id)
        if isinstance(ws, dict) and ws.get("error"):
            continue
        active.append({
            "ro_id": ro.id,
            "service_number": ro.attributes.get("ServiceNumber", ro.id),
            "description": ro.attributes.get("Description"),
            "vehicle": _ro_vehicle_label(ro),
            "stage": ws.get("ro_stage"),
            "workflow_checklist": ws.get("workflow_checklist", []),
            "technician": ws.get("technician"),
            "timeline": ((ws.get("timeline") or {}).get("events") or [])[:8],
        })

    return {"customer": _customer_public(customer_id), "active_ros": active, "count": len(active)}
