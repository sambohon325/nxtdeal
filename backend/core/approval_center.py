"""
core/approval_center.py -- the Customer-Facing Approval Center, one of
Sam's "FEATURES COMPLETELY MISSING" list items, and the natural next piece
after the RO Workflow Engine's Estimate/Approval flow (`core/repair_orders.py`)
and Digital Vehicle Inspection (`core/vehicle_inspection.py`): right now a
customer's estimate approval/decline is always RECORDED BY STAFF on the
customer's behalf (over the phone, in person) -- `record_customer_approval()`'s
`recorded_by` has only ever been an employee id. This module closes that
real gap: a genuine, real customer-initiated approval, over a real
shareable link, with no staff member acting as an intermediary.

Real mechanism, not a mockup: `generate_approval_link()` creates a real
unguessable token (`secrets.token_urlsafe(24)`, same class of real random
secret `core/network_pseudonym.py`'s pseudonym generation already
established for this codebase -- NOT a sequential graph-entity id, which
would be guessable and let one customer view another's estimate). The
token is stored as an additive `approval_link` dict directly on the
ServiceRecord (same additive-attribute convention as `estimate`/`dvi`),
requiring a real estimate to already be on file before a link can be
generated at all -- there's nothing to approve otherwise.

The public-facing read (`get_public_approval_view`) and write
(`record_public_approval_decision`) are genuinely unauthenticated -- same
`/public/*` convention this codebase already uses for website visitors
(`core/websites.py`'s `get_website_rendered()`) and website chat sessions
(`core/website_chat.py`). A customer approving/declining through this link
is recorded with `recorded_by="customer_via_approval_link"` -- an honest,
distinct sentinel value from any real employee id, so it's always possible
to tell, looking at the RO's own estimate record, whether staff recorded
the decision on the customer's behalf or the customer did it themselves
through this real mechanism.

Scope note: this does NOT surface every DVI item's raw technician notes to
the customer -- only flagged (yellow/red) findings' descriptions, matching
what a customer actually needs to make an approval decision, not an
internal working document. A revoked or already-decided link still renders
(read-only), so a customer who already acted (or staff who revoked the
link) sees an honest, accurate state rather than a dead page.
"""

import secrets

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD
from core.repair_orders import _get_ro, _now, _customer_for_record, _vehicle_for_record, record_customer_approval
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CUSTOMER_SENTINEL = "customer_via_approval_link"


def _find_ro_by_token(token):
    for e in ledger.get_all().values():
        if e.entity_type == SERVICE_RECORD:
            link = e.attributes.get("approval_link")
            if link and link.get("token") == token:
                return e
    return None


def generate_approval_link(ro_id, created_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    if not ro.attributes.get("estimate"):
        return {"error": "Cannot generate an approval link before an estimate has been sent on this RO"}

    token = secrets.token_urlsafe(24)
    ro.attributes["approval_link"] = {
        "token": token,
        "created_by": created_by,
        "created_at": _now(),
        "revoked": False,
    }
    save_graph(GRAPH_PATH)

    return {"ro_id": ro_id, "token": token, "path": f"/approve/{token}"}


def get_approval_link_status(ro_id):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    link = ro.attributes.get("approval_link")
    if not link:
        return {"ro_id": ro_id, "exists": False}

    return {"ro_id": ro_id, "exists": True, **link, "path": f"/approve/{link['token']}"}


def revoke_approval_link(ro_id, revoked_by):

    ro = _get_ro(ro_id)
    if not ro:
        return {"error": f"Repair order '{ro_id}' not found"}

    link = ro.attributes.get("approval_link")
    if not link:
        return {"error": "No approval link exists for this RO"}
    if link.get("revoked"):
        return {"error": "This approval link is already revoked"}

    link["revoked"] = True
    link["revoked_by"] = revoked_by
    link["revoked_at"] = _now()
    ro.attributes["approval_link"] = link
    save_graph(GRAPH_PATH)

    return {"ro_id": ro_id, "revoked": True}


def get_public_approval_view(token):
    """PUBLIC, unauthenticated -- a real customer viewing their own RO's
    estimate/concerns/flagged DVI findings via a real shareable link, same
    /public/* convention as core/websites.py's website visitor render."""

    ro = _find_ro_by_token(token)
    if not ro:
        return {"error": "This approval link is invalid or has expired."}

    link = ro.attributes["approval_link"]
    customer = _customer_for_record(ro)
    vehicle = _vehicle_for_record(ro)
    estimate = ro.attributes.get("estimate") or {}
    concerns = [c for c in (ro.attributes.get("concerns") or []) if c.get("status") == "open"]

    dvi = ro.attributes.get("dvi") or {}
    flagged_findings = [
        {"category": entry["category"], "item": entry["item"], "status": entry["status"], "notes": entry.get("notes") or ""}
        for entry in (dvi.get("items") or {}).values()
        if entry["status"] in ("yellow", "red")
    ]

    return {
        "revoked": link.get("revoked", False),
        "service_number": ro.attributes.get("ServiceNumber"),
        "description": ro.attributes.get("Description"),
        "customer_name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() if customer else None,
        "vehicle": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() if vehicle else None,
        "open_concerns": [{"description": c["description"]} for c in concerns],
        "flagged_inspection_findings": flagged_findings,
        "estimate": {
            "amount": estimate.get("amount"),
            "sent_at": estimate.get("sent_at"),
            "approved": estimate.get("approved"),
            "decided_at": estimate.get("approved_at"),
            "decline_reason": estimate.get("decline_reason"),
            "decided_by_customer": estimate.get("approved_by") == CUSTOMER_SENTINEL,
        },
    }


def record_public_approval_decision(token, approved, decline_reason=""):
    """PUBLIC, unauthenticated -- the real customer-initiated write. Records
    with recorded_by=CUSTOMER_SENTINEL, an honest, distinct marker from any
    real employee id."""

    ro = _find_ro_by_token(token)
    if not ro:
        return {"error": "This approval link is invalid or has expired."}

    link = ro.attributes["approval_link"]
    if link.get("revoked"):
        return {"error": "This approval link has been revoked. Please contact the dealership."}

    estimate = ro.attributes.get("estimate")
    if estimate and estimate.get("approved") is not None:
        return {"error": "A decision has already been recorded for this estimate."}

    if not approved and not (decline_reason or "").strip():
        return {"error": "A reason is required when declining."}

    result = record_customer_approval(ro.id, approved, CUSTOMER_SENTINEL, decline_reason=decline_reason)
    if "error" in result:
        return result

    return get_public_approval_view(token)
