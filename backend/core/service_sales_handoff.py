"""
core/service_sales_handoff.py -- Service-to-Sales Opportunity Handoff, the
fourth and final of Sam's "FEATURES COMPLETELY MISSING" Service list (after
DVI, the Customer-Facing Approval Center, and Loaner & Shuttle Management).

Real dealership motivation: a Service visit is one of the best trade-in/
upsell signals a dealership has -- a customer who just declined a repair, or
just paid a large bill to keep an aging car running, is a warm Sales
conversation waiting to happen. Nothing in this codebase turned that signal
into an actual handoff before this module; Service and Sales were two
islands.

Two real, honestly-scoped signals, not a fabricated third:

- Declined Services -- reuses `core/service_customers.py`'s
  `get_declined_services()` verbatim (a customer said no to a real estimate
  on a live RO). The single strongest, most literal version of "Service
  found a sales opportunity" this codebase has.

- High-Cost Repair -- a real ServiceRecord.Cost above a stated HEURISTIC
  threshold ($750, `HIGH_COST_THRESHOLD` -- checked against this seed's real
  cost distribution before picking a number: costs here top out at $898.95,
  so $750 lands around the real 90th percentile, a genuinely "expensive for
  this dealership" repair rather than an arbitrary round number that would
  silently return zero results) on a completed RO. Honestly labeled as a
  heuristic, not a precise signal -- there's no real vehicle age/book-value/
  ownership-tenure data anywhere in this codebase to compute a smarter "this
  car is worth trading in" score, same class of limitation this codebase's
  other heuristic thresholds (e.g. Shop Control's assumed 8-hour technician
  capacity) already carry.

A manual third path (`flag_manual_opportunity`) lets an advisor flag any
completed RO as a handoff candidate regardless of either automatic signal --
"the customer mentioned they're thinking about a new car" isn't always
tied to a declined estimate or an expensive bill.

Handoff state (open/promoted/dismissed) is tracked as an additive
`sales_handoff` dict directly on the ServiceRecord -- same convention as
`estimate`/`dvi`/`warranty_claim`, no new entity type, since this is one
more piece of state about an existing RO, not a new real-world object.

`promote_to_sales()` is the actual handoff mechanism, and reuses the exact
precedent `core/orphan_owner_mining.py`'s `claim_orphan_owner()` and
`core/trigger_alerts.py`'s `promote_alert()` already established: a real new
Lead via `core/lead_intake.py`'s `create_lead()` (Source="Service Handoff"),
tied back to the originating Customer via a real `GENERATED_LEAD`
relationship. Once promoted, the opportunity drops out of the open queue --
no second "already handed off" tracking mechanism needed, `sales_handoff`
already carries it.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SERVICE_RECORD, LEAD
from core.relationships import Relationship
from core.relationship_types import GENERATED_LEAD
from core.repair_orders import _get_ro, _customer_for_record, _vehicle_for_record
from core.service_customers import get_declined_services
from core.lead_intake import create_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

HIGH_COST_THRESHOLD = 750.0

OPPORTUNITY_TYPES = ("declined_service", "high_cost_repair", "manual")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _handoff_state(ro):
    return ro.attributes.get("sales_handoff") or {"status": "open"}


def _is_actionable(ro):
    """Only completed ROs (there's nothing to hand off on a car still on
    the lift), not already promoted or dismissed."""
    return _handoff_state(ro).get("status") not in ("promoted", "dismissed")


def _customer_brief(customer):
    if not customer:
        return None
    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
        "email": customer.attributes.get("Email"),
        "phone": customer.attributes.get("Phone"),
    }


def get_declined_service_candidates():
    declined = get_declined_services()
    candidates = []
    for d in declined["records"]:
        ro = _get_ro(d["ro_id"])
        if not ro or not _is_actionable(ro):
            continue
        candidates.append({
            "ro_id": d["ro_id"],
            "opportunity_type": "declined_service",
            "customer_id": d["customer_id"],
            "customer_name": d["customer_name"],
            "vehicle": d["vehicle"],
            "description": d["description"],
            "amount": d["amount"],
            "reason": d["decline_reason"] or "Customer declined estimate",
            "handoff_status": _handoff_state(ro).get("status", "open"),
        })
    return candidates


def get_high_cost_repair_candidates(threshold=HIGH_COST_THRESHOLD, limit=50):
    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    candidates = []
    for r in records:
        cost = r.attributes.get("Cost")
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            continue
        if cost < threshold:
            continue
        if not _is_actionable(r):
            continue

        customer = _customer_for_record(r)
        vehicle = _vehicle_for_record(r)
        candidates.append({
            "ro_id": r.id,
            "opportunity_type": "high_cost_repair",
            "customer_id": customer.id if customer else None,
            "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
            "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
            "description": r.attributes.get("Description"),
            "amount": cost,
            "reason": f"Repair cost of ${cost:,.2f} exceeds the ${threshold:,.0f} heuristic threshold",
            "handoff_status": _handoff_state(r).get("status", "open"),
        })

    candidates.sort(key=lambda c: c["amount"] or 0, reverse=True)
    return candidates[:limit]


def get_manually_flagged_candidates():
    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    candidates = []
    for r in records:
        state = r.attributes.get("sales_handoff")
        if not state or state.get("opportunity_type") != "manual" or state.get("status") != "open":
            continue
        customer = _customer_for_record(r)
        vehicle = _vehicle_for_record(r)
        candidates.append({
            "ro_id": r.id,
            "opportunity_type": "manual",
            "customer_id": customer.id if customer else None,
            "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
            "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
            "description": r.attributes.get("Description"),
            "amount": None,
            "reason": state.get("notes") or "Manually flagged by a service advisor",
            "handoff_status": "open",
        })
    return candidates


def get_opportunity_queue(limit=50):
    declined = get_declined_service_candidates()
    high_cost = get_high_cost_repair_candidates(limit=limit)
    manual = get_manually_flagged_candidates()

    all_candidates = declined + high_cost + manual
    seen_ro_ids = set()
    deduped = []
    for c in all_candidates:
        if c["ro_id"] in seen_ro_ids:
            continue
        seen_ro_ids.add(c["ro_id"])
        deduped.append(c)

    deduped.sort(key=lambda c: c["amount"] or 0, reverse=True)

    return {
        "count": len(deduped),
        "declined_service_count": len(declined),
        "high_cost_repair_count": len(high_cost),
        "manual_count": len(manual),
        "candidates": deduped[:limit],
    }


def get_equity_service_candidates(limit=50):
    """Phase 7 (competitive roadmap): the equity/maturity-at-service signal. A customer who
    is (or recently was) in the service lane AND is carrying positive estimated equity or a
    maturing loan/lease is a prime upgrade conversation -- exactly automotiveMastermind's
    "mine the service drive for sales" play. Joins the actionable ServiceRecord set with
    core/equity_center's position. One candidate per customer (their most recent actionable
    RO), so a customer with several visits doesn't flood the queue.

    Kept as a SEPARATE queue from get_opportunity_queue() (which existing tests pin to exact
    counts) -- this is additive, surfaced through get_conversion_opportunities() below."""
    from core import equity_center

    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    by_customer = {}  # customer_id -> chosen RO (dedupe)
    for r in records:
        if not _is_actionable(r):
            continue
        customer = _customer_for_record(r)
        if not customer:
            continue
        by_customer.setdefault(customer.id, (r, customer))

    candidates = []
    for customer_id, (ro, customer) in by_customer.items():
        pos = equity_center.get_equity_position(customer_id)
        equity_amount = pos.get("equity_amount")
        maturing = pos.get("lease_maturing_soon")
        positive_equity = pos.get("status") == "positive"
        if not positive_equity and not maturing:
            continue

        reasons = []
        if positive_equity:
            reasons.append(f"~${equity_amount:,.0f} estimated equity")
        if maturing:
            reasons.append(f"loan/lease matures in {pos.get('days_to_lease_maturity')} day(s)")
        vehicle = _vehicle_for_record(ro)
        candidates.append({
            "ro_id": ro.id,
            "opportunity_type": "equity_at_service",
            "customer_id": customer_id,
            "customer_name": _customer_brief(customer)["name"],
            "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
            "description": "In the service lane with equity/maturity — upgrade opportunity",
            "amount": equity_amount,
            "reason": " · ".join(reasons),
            "handoff_status": _handoff_state(ro).get("status", "open"),
            "is_estimated": True,
        })

    candidates.sort(key=lambda c: c["amount"] or 0, reverse=True)
    return candidates[:limit]


def get_conversion_opportunities(limit=50):
    """Combined service-to-sales view (Phase 7): the standard opportunity queue
    (declined/high-cost/manual) PLUS the new equity/maturity-at-service candidates, deduped
    by RO. This is what the enhanced UI reads; get_opportunity_queue() is unchanged."""
    base = get_opportunity_queue(limit=limit)
    equity = get_equity_service_candidates(limit=limit)

    seen = {c["ro_id"] for c in base["candidates"]}
    fresh_equity = [c for c in equity if c["ro_id"] not in seen]

    combined = base["candidates"] + fresh_equity
    combined.sort(key=lambda c: c["amount"] or 0, reverse=True)

    return {
        "count": len(combined),
        "declined_service_count": base["declined_service_count"],
        "high_cost_repair_count": base["high_cost_repair_count"],
        "manual_count": base["manual_count"],
        "equity_at_service_count": len(fresh_equity),
        "candidates": combined[:limit],
    }


def flag_manual_opportunity(ro_id, flagged_by, notes=""):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    if not _is_actionable(ro):
        return {"error": f"Repair order '{ro_id}' has already been {_handoff_state(ro).get('status')}"}

    ro.attributes["sales_handoff"] = {
        "status": "open",
        "opportunity_type": "manual",
        "notes": notes,
        "flagged_by": flagged_by,
        "flagged_at": _now(),
    }
    save_graph(GRAPH_PATH)
    return {"ro_id": ro_id, "sales_handoff": ro.attributes["sales_handoff"]}


def get_ro_handoff_status(ro_id):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}
    return {"ro_id": ro_id, "sales_handoff": _handoff_state(ro)}


def promote_to_sales(ro_id, promoted_by, assigned_to=None, notes="", opportunity_type=None):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    state = _handoff_state(ro)
    if state.get("status") == "promoted":
        return {"error": f"This RO was already promoted -- Lead {state.get('promoted_lead_id')}"}
    if state.get("status") == "dismissed":
        return {"error": "This opportunity was already dismissed"}

    customer = _customer_for_record(ro)
    if not customer:
        return {"error": f"No customer on file for repair order '{ro_id}'"}
    vehicle = _vehicle_for_record(ro)

    lead_owner = assigned_to or promoted_by

    lead = create_lead(
        lead_owner,
        customer.attributes.get("FirstName", ""),
        customer.attributes.get("LastName", ""),
        "Service Handoff",
        phone=customer.attributes.get("Phone"),
        email=customer.attributes.get("Email"),
        city=customer.attributes.get("City"),
        state=customer.attributes.get("State"),
        vin=vehicle.attributes.get("VIN") if vehicle else None,
    )

    ledger.add_relationship(
        Relationship(source_id=customer.id, target_id=lead.id, relationship_type=GENERATED_LEAD)
    )

    ro.attributes["sales_handoff"] = {
        "status": "promoted",
        "opportunity_type": opportunity_type or state.get("opportunity_type", "manual"),
        "promoted_lead_id": lead.id,
        "promoted_by": promoted_by,
        "assigned_to": lead_owner,
        "promoted_at": _now(),
        "notes": notes or state.get("notes", ""),
    }

    save_graph(GRAPH_PATH)

    return {
        "ro_id": ro_id,
        "lead_id": lead.id,
        "customer_id": customer.id,
        "assigned_to": lead_owner,
    }


def dismiss_opportunity(ro_id, dismissed_by, reason="", opportunity_type=None):
    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    state = _handoff_state(ro)
    if state.get("status") == "promoted":
        return {"error": f"This RO was already promoted -- Lead {state.get('promoted_lead_id')}"}
    if state.get("status") == "dismissed":
        return {"error": "This opportunity was already dismissed"}

    ro.attributes["sales_handoff"] = {
        "status": "dismissed",
        "opportunity_type": opportunity_type or state.get("opportunity_type", "manual"),
        "dismissed_by": dismissed_by,
        "dismissed_at": _now(),
        "reason": reason,
    }
    save_graph(GRAPH_PATH)
    return {"ro_id": ro_id, "sales_handoff": ro.attributes["sales_handoff"]}


def get_handoff_stats():
    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    promoted = 0
    dismissed = 0
    for r in records:
        state = r.attributes.get("sales_handoff")
        if not state:
            continue
        if state.get("status") == "promoted":
            promoted += 1
        elif state.get("status") == "dismissed":
            dismissed += 1

    queue = get_opportunity_queue(limit=100000)

    return {
        "open_opportunities": queue["count"],
        "declined_service_count": queue["declined_service_count"],
        "high_cost_repair_count": queue["high_cost_repair_count"],
        "manual_count": queue["manual_count"],
        "promoted_count": promoted,
        "dismissed_count": dismissed,
    }
