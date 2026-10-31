"""
core/lost_sale_recovery.py -- Lost Sale Recovery (session 105 follow-up), the eighth of
Sam's ~10 "completely missing" dealership workflows (Up System, BDC, Manager TO, Demo
Drive, Credit App, eSignature, F&I Workflow, Delivery Checklist, Lost Sale Recovery,
Orphan Owner Mining -- session 92's original spec).

Unifies TWO real, already-existing "we lost this" signals that had no recovery
mechanism sitting on top of them:
  1. Lead.PipelineState == "LOST" -- core/workflows.py's LEAD_WORKFLOW state machine
     (core/lead_workflows.py) already tracks this, but LOST is a hard terminal state
     with no valid outgoing transition -- nothing in this codebase could ever move a
     lead back out of it, and no reason was ever captured for WHY it was lost.
  2. Deal.status == "cancelled" -- core/deals.py's cancel_deal() already exists and
     works (and, as of this session's save_graph fix, actually persists), but captures
     no reason either, and nothing surfaces cancelled deals as a worklist.

Two distinct entities being lost, two distinct recovery mechanisms, one combined queue
and one combined stats view -- not a single new entity type, since both Lead and Deal
already exist and already carry the state this needs; recovery is captured as
additive attributes on each (LostReason/LostAt/LostBy/PreviousLostReasons on Lead,
cancel_reason/cancel_reason_by/cancel_reason_at on Deal), same convention as
trade_in/delivery_checklist/fi_products on Deal.

Reactivating a lost lead is a deliberate, well-reasoned BYPASS of the strict
LEAD_WORKFLOW state machine, not a hidden extra transition edge added to it: LOST has
no valid outgoing transition by design (a lead that transitions in and out of LOST
freely would make "how many leads did we actually lose this month" meaningless). This
module calls core.pipeline_state.set_pipeline_state() directly (the unvalidated
low-level setter) rather than routing through advance_lead_workflow(), logs its own
distinct "lead_reactivated" audit event mirroring advance_lead_workflow()'s own
pattern, and preserves the prior reason in a PreviousLostReasons list rather than
overwriting it -- so a lead can be lost and won back more than once, with full history
visible via both the attribute list and the audit log.

record_deal_lost_reason() deliberately does NOT modify core/deals.py's cancel_deal() --
reason capture is an optional follow-up action on an already-cancelled deal, added
entirely from this module, so DealDeskBoard.tsx's existing cancel-deal button flow
needs no changes and core/deals.py (already touched once this session for the
save_graph fix) doesn't need touching again.

save_recovery_pool_as_list() reuses core/marketing_lists.py's create_list()/
add_members() (confirmed working end-to-end after this session's save_graph fix) --
the exact same "Save as List" mechanism Marketing's CRM and Opportunities tabs already
use, so a lost-lead or cancelled-deal win-back pool becomes an ordinary, campaign-
targetable MarketingList rather than a parallel export mechanism.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, DEAL, VEHICLE
from core.pipeline_state import set_pipeline_state, get_pipeline_state
from core.lead_workflows import advance_lead_workflow
from core.field_notes import create_field_note, list_field_notes
from core.marketing_lists import create_list, add_members
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH


LOST_REASON_CODES = [
    "price", "financing_declined", "lost_to_competitor", "went_with_another_dealer",
    "changed_mind", "credit_issue", "trade_value_disagreement", "no_response",
    "vehicle_no_longer_available", "other",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _customer_brief(customer_id):

    customer = ledger.get_entity(customer_id) if customer_id else None

    if not customer or customer.entity_type != CUSTOMER:
        return None

    return {
        "id": customer.id,
        "name": f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id,
        "email": customer.attributes.get("Email"),
        "phone": customer.attributes.get("Phone"),
    }


def _vehicle_brief(vehicle_id):

    vehicle = ledger.get_entity(vehicle_id) if vehicle_id else None

    if not vehicle or vehicle.entity_type != VEHICLE:
        return None

    return {
        "id": vehicle.id,
        "description": f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} {vehicle.attributes.get('Model', '')}".strip() or vehicle.id,
        "vin": vehicle.attributes.get("VIN"),
        "price": vehicle.attributes.get("Price"),
    }


def _lead_brief(lead):
    """Leads carry their own FirstName/LastName/Email/Phone directly
    (core/lead_intake.py) -- a Lead only gains a real linked Customer once
    core/lead_conversion.py's convert_lead_to_customer() runs (ConvertedCustomerID)."""

    name = f"{lead.attributes.get('FirstName', '')} {lead.attributes.get('LastName', '')}".strip() or lead.id

    return {
        "id": lead.id,
        "name": name,
        "email": lead.attributes.get("Email"),
        "phone": lead.attributes.get("Phone"),
        "source": lead.attributes.get("Source"),
        "assigned_salesperson": lead.attributes.get("AssignedSalesperson"),
        "lost_reason": lead.attributes.get("LostReason"),
        "lost_at": lead.attributes.get("LostAt"),
        "lost_by": lead.attributes.get("LostBy"),
        "previous_lost_reasons": lead.attributes.get("PreviousLostReasons") or [],
        "converted_customer": _customer_brief(lead.attributes.get("ConvertedCustomerID")),
    }


def _deal_brief(deal):

    return {
        "id": deal.id,
        "status": deal.attributes.get("status"),
        "cancelled_at": deal.attributes.get("updated_at"),
        "cancel_reason": deal.attributes.get("cancel_reason"),
        "cancel_reason_by": deal.attributes.get("cancel_reason_by"),
        "cancel_reason_at": deal.attributes.get("cancel_reason_at"),
        "customer": _customer_brief(deal.attributes.get("customer_id")),
        "vehicle": _vehicle_brief(deal.attributes.get("vehicle_id")),
    }


def get_lost_leads(limit=50):
    """Every Lead currently sitting in the terminal LOST pipeline state, most recently
    lost first -- the real 'lost_opportunities' detail sales_menu.py's prospects() has
    only ever reported as a bare count."""

    leads = [l for l in _entities(LEAD) if l.attributes.get("PipelineState") == "LOST"]
    leads.sort(key=lambda l: l.attributes.get("LostAt") or l.attributes.get("PipelineStateSince") or "", reverse=True)

    return [_lead_brief(l) for l in leads[:limit]]


def get_cancelled_deals(limit=50):
    """Every cancelled Deal, most recently cancelled first."""

    deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "cancelled"]
    deals.sort(key=lambda d: d.attributes.get("updated_at") or "", reverse=True)

    return [_deal_brief(d) for d in deals[:limit]]


def mark_lead_lost(lead_id, reason, lost_by):
    """Real transition into LOST via the validated state machine (advance_lead_workflow
    already handles the graph write, save_graph, and its own 'workflow_transition'
    audit event) -- this function's own job is only the reason-capture additive
    attributes on top of that real transition."""

    if reason not in LOST_REASON_CODES:
        return {"error": f"Unknown reason code. Must be one of: {LOST_REASON_CODES}"}

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {"error": "Lead not found"}

    try:
        advance_lead_workflow(lead_id, "LOST")
    except ValueError as exc:
        return {"error": str(exc)}

    lead.attributes["LostReason"] = reason
    lead.attributes["LostAt"] = _now()
    lead.attributes["LostBy"] = lost_by
    save_graph(GRAPH_PATH)

    return _lead_brief(lead)


def record_deal_lost_reason(deal_id, reason, recorded_by):
    """Additive reason capture on an already-cancelled Deal. Deliberately does NOT call
    into core/deals.py's cancel_deal() -- this only annotates a deal that's already
    cancelled, so the existing cancel flow (DealDeskBoard.tsx's Cancel button) needs no
    changes, and a reason can be recorded any time after the fact."""

    deal = ledger.get_entity(deal_id)

    if not deal or deal.entity_type != DEAL:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "cancelled":
        return {"error": f"Deal is '{deal.attributes.get('status')}' -- a lost-sale reason can only be recorded on a cancelled deal"}

    deal.attributes["cancel_reason"] = reason
    deal.attributes["cancel_reason_by"] = recorded_by
    deal.attributes["cancel_reason_at"] = _now()
    save_graph(GRAPH_PATH)

    return _deal_brief(deal)


def reactivate_lost_lead(lead_id, reactivated_by, note=None):
    """Bypasses LEAD_WORKFLOW's strict state machine on purpose -- LOST has no valid
    outgoing transition (see this module's docstring). Moves the lead directly back to
    CONTACTED via the low-level, unvalidated pipeline_state setter, preserves the prior
    reason in a running PreviousLostReasons list rather than discarding it, and logs its
    own 'lead_reactivated' audit event (mirroring advance_lead_workflow's own
    event/summary/details shape) so this bypass is just as visible in the audit trail as
    a normal transition would have been."""

    lead = ledger.get_entity(lead_id)

    if not lead or lead.entity_type != LEAD:
        return {"error": "Lead not found"}

    if get_pipeline_state(lead_id) != "LOST":
        return {"error": "Lead is not currently in the LOST state"}

    prior_reason = lead.attributes.get("LostReason")

    if prior_reason:
        history = list(lead.attributes.get("PreviousLostReasons") or [])
        history.append({
            "reason": prior_reason,
            "lost_at": lead.attributes.get("LostAt"),
            "lost_by": lead.attributes.get("LostBy"),
            "reactivated_at": _now(),
            "reactivated_by": reactivated_by,
        })
        lead.attributes["PreviousLostReasons"] = history

    set_pipeline_state(lead_id, "CONTACTED")

    lead.attributes["LostReason"] = None
    lead.attributes["LostAt"] = None
    lead.attributes["LostBy"] = None
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="lead_reactivated",
        summary=f"Lead {lead_id} reactivated LOST -> CONTACTED by {reactivated_by}",
        entity_id=lead_id,
        actor=reactivated_by,
        details={"from": "LOST", "to": "CONTACTED", "prior_reason": prior_reason, "note": note},
    )
    save_audit_log(AUDIT_PATH)

    if note:
        create_field_note(
            department="Sales",
            category="recovery_attempt",
            body=note,
            created_by=reactivated_by,
            linked_entity_id=lead_id,
        )

    return _lead_brief(lead)


def log_recovery_attempt(entity_id, entity_type, note, logged_by):
    """A logged outreach attempt against a lost lead or cancelled deal -- merged into
    the same Activity Timeline as every other FieldNote category, via the
    'recovery_attempt' category added to core/field_notes.py's CATEGORIES this
    session."""

    entity = ledger.get_entity(entity_id)

    if not entity or entity.entity_type not in (LEAD, DEAL):
        return {"error": "Entity must be a real Lead or Deal id"}

    department = "Sales"

    field_note = create_field_note(
        department=department,
        category="recovery_attempt",
        body=note,
        created_by=logged_by,
        linked_entity_id=entity_id,
    )

    return {
        "id": field_note.id,
        "entity_id": entity_id,
        "entity_type": entity.entity_type,
        "body": note,
        "created_by": logged_by,
        "created_at": field_note.attributes.get("created_at"),
    }


def list_recovery_attempts(entity_id):
    notes = list_field_notes(linked_entity_id=entity_id)
    return [
        {
            "id": n.id,
            "body": n.attributes.get("body"),
            "created_by": n.attributes.get("created_by"),
            "created_at": n.attributes.get("created_at"),
        }
        for n in notes
        if n.attributes.get("category") == "recovery_attempt"
    ]


def save_recovery_pool_as_list(name, created_by, source, description=""):
    """Reuses core/marketing_lists.py's real create_list()/add_members() -- the exact
    'Save as List' mechanism Marketing's CRM/Opportunities tabs already use, so a
    lost-lead or cancelled-deal win-back pool becomes an ordinary, campaign-targetable
    MarketingList rather than a parallel export mechanism. Deals aren't a valid
    MarketingList member type (core/marketing_lists.py's add_members() only accepts
    Customer/Lead ids) -- for the cancelled_deals source, this resolves each deal's
    linked Customer instead, since that's who a win-back campaign would actually
    target."""

    if source not in ("lost_leads", "cancelled_deals"):
        return {"error": "source must be 'lost_leads' or 'cancelled_deals'"}

    if source == "lost_leads":
        member_ids = [l.id for l in _entities(LEAD) if l.attributes.get("PipelineState") == "LOST"]
    else:
        deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "cancelled"]
        member_ids = list({d.attributes.get("customer_id") for d in deals if d.attributes.get("customer_id")})

    entity = create_list(name, created_by, description=description or f"Auto-saved from Lost Sale Recovery ({source})")
    result = add_members(entity.id, member_ids)

    return {
        "list_id": entity.id,
        "source": source,
        "requested": len(member_ids),
        "added": len(result["added"]) if result else 0,
    }


def get_lost_sale_stats():
    """Real aggregates -- total lost leads, total cancelled deals, a lost-by-reason
    breakdown (honest 'not_recorded' bucket for leads/deals lost before this feature
    existed or whose reason was never captured), and a recovery rate computed only over
    leads that have ever actually been through the LOST state at least once (had
    LostAt or PreviousLostReasons set) -- not a rate over every lead ever created."""

    leads = _entities(LEAD)
    deals = _entities(DEAL)

    lost_leads = [l for l in leads if l.attributes.get("PipelineState") == "LOST"]
    cancelled_deals = [d for d in deals if d.attributes.get("status") == "cancelled"]

    ever_lost = [
        l for l in leads
        if l.attributes.get("PipelineState") == "LOST" or l.attributes.get("PreviousLostReasons")
    ]
    reactivated = [l for l in ever_lost if l.attributes.get("PreviousLostReasons")]

    reason_counts = {}
    for l in lost_leads:
        reason = l.attributes.get("LostReason") or "not_recorded"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    deal_reason_counts = {}
    for d in cancelled_deals:
        reason = d.attributes.get("cancel_reason") or "not_recorded"
        deal_reason_counts[reason] = deal_reason_counts.get(reason, 0) + 1

    recovery_rate = round(100 * len(reactivated) / len(ever_lost), 1) if ever_lost else None

    return {
        "total_lost_leads": len(lost_leads),
        "total_cancelled_deals": len(cancelled_deals),
        "lost_lead_reasons": reason_counts,
        "cancelled_deal_reasons": deal_reason_counts,
        "recovery_rate_pct": recovery_rate,
        "leads_ever_lost": len(ever_lost),
        "leads_reactivated": len(reactivated),
    }
