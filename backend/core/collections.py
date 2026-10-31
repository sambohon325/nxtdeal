"""
core/collections.py -- Finance's "Collections" item, the third slice of Sam's Retail
Automotive Lending Platform expansion (2026-07-17), right after Portfolio and
Payments. Sam's own framing: "This is usually missing from dealer software. For BHPH
and finance companies it is critical" -- a Collection Work Queue (auto-prioritized by
days late), a Collection Agent Workspace (last payment, risk score, contact history,
employer info), integrated Call/Text/Email logging, a workflow-driven Collection Path
(Friendly Reminder -> Late Notice -> Demand Notice -> Recovery Review ->
Repossession), and "AI Collection Prioritization."

Deliberately NOT a new signal-detection pass -- this module is built entirely on top
of core/loan_servicing.py's own delinquency computation (which itself already prefers
REAL payment-ledger-derived data over its SIMULATED estimate the moment real payments
exist for a loan, per core/payments.py, session 112 follow-up). Collections doesn't
re-decide whether a loan is delinquent, it triages and works whatever
get_simulated_payment_status() already says -- real or simulated, its own `basis`
field is carried through honestly rather than re-labeled.

Collection Path is a real, stored workflow state (additive `collection_stage`
attribute on the loan, same computed-default-then-real-value convention as
loan_status/ro_stage/lifecycle_status elsewhere in this codebase) -- a suggested stage
is computed live off real days-past-due (3/7/15/30/60-day thresholds, matching Sam's
own queue bucket names), but advancing it is always an explicit human action
(advance_collection_stage()), never automatic.

Risk Score and "AI Collection Prioritization" are a real, transparent RULES ENGINE
over already-real-or-disclosed inputs (days past due, broken-promise count, real
payment consistency) -- NOT a machine-learning model or LLM call, same honesty this
codebase already applies to every other "AI"-branded feature (core/bot_learning.py's
"real act/dismiss heuristic prioritization", core/network_audit.py's "real rules-based
recommendation engine"). Every score/recommendation carries its own `basis` field
(inherited from the underlying payment-status basis) so it's always traceable back to
whether it rests on real or simulated data.

Call/Text/Email logging deliberately reuses core/field_notes.py's existing "call"/
"text"/"email" categories verbatim (department="Finance", linked_entity_id=the loan's
id) -- the exact same mechanism the RO Workflow Engine's Communication Center and
Sales' Communications board already established, not a parallel contact-log store.
References has no backing data model anywhere in this codebase (same honest gap
core/loan_servicing.py's Borrower tab already states) -- not simulated here either,
same reasoning as Portfolio's own borrower.employment treatment.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import FINANCE_CONTRACT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.loan_servicing import (
    _get_loan, _customer_brief, _vehicle_brief, _linked_customer_id, _linked_vehicle_id,
    get_simulated_payment_status, get_loan_financials,
)
from core.payments import list_payments_for_loan, list_promises_to_pay
from core.field_notes import create_field_note, list_field_notes

COLLECTION_STAGES = ("friendly_reminder", "late_notice", "demand_notice", "recovery_review", "repossession_referral")

QUEUE_BUCKETS = ("3_day", "7_day", "15_day", "30_day", "60_day")

CONTACT_CHANNELS = ("call", "text", "email")

_STAGE_LABELS = {
    "friendly_reminder": "Friendly Reminder",
    "late_notice": "Late Notice",
    "demand_notice": "Demand Notice",
    "recovery_review": "Recovery Review",
    "repossession_referral": "Repossession Referral",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_loans():
    return [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT]


def _queue_bucket(days_past_due):
    if days_past_due is None or days_past_due < 3:
        return None
    if days_past_due < 7:
        return "3_day"
    if days_past_due < 15:
        return "7_day"
    if days_past_due < 30:
        return "15_day"
    if days_past_due < 60:
        return "30_day"
    return "60_day"


def suggest_collection_stage(days_past_due):
    """A real, computed suggestion -- not the stored value. Matches Sam's own
    Friendly Reminder -> Late Notice -> Demand Notice -> Recovery Review ->
    Repossession Referral ladder onto the same 3/7/15/30/60-day thresholds the Work
    Queue buckets by."""

    bucket = _queue_bucket(days_past_due)
    return {
        None: None,
        "3_day": "friendly_reminder",
        "7_day": "late_notice",
        "15_day": "demand_notice",
        "30_day": "recovery_review",
        "60_day": "repossession_referral",
    }[bucket]


def get_collection_stage(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    stored = loan.attributes.get("collection_stage")
    if stored in COLLECTION_STAGES:
        return stored

    status = get_simulated_payment_status(loan_id)
    return suggest_collection_stage(status.get("days_past_due") if isinstance(status, dict) else None)


def advance_collection_stage(loan_id, stage, by, reason=""):
    if stage not in COLLECTION_STAGES:
        return {"error": f"stage must be one of {COLLECTION_STAGES}"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    loan.attributes["collection_stage"] = stage
    history = loan.attributes.setdefault("collection_stage_history", [])
    history.append({"stage": stage, "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return loan


def _broken_promises_count(loan_id):
    promises = list_promises_to_pay(loan_id=loan_id)
    return len([p for p in promises if p.get("status") == "broken"])


def compute_risk_score(loan_id):
    """A real, transparent rules-based composite (0-100, higher = riskier) over
    already-real-or-disclosed inputs -- NOT a machine-learning model. basis is
    inherited from the underlying payment-status basis (real_payment_ledger or
    simulated_payment_status) so it's always traceable."""

    status = get_simulated_payment_status(loan_id)
    if not isinstance(status, dict) or "error" in status:
        return status

    days_past_due = status.get("days_past_due") or 0
    broken = _broken_promises_count(loan_id)
    payments = list_payments_for_loan(loan_id, include_declined=False)

    score = 0
    score += min(60, days_past_due)
    score += min(30, broken * 15)
    if not payments and days_past_due > 0:
        score += 10

    score = max(0, min(100, score))

    if score >= 60:
        tier = "high"
    elif score >= 30:
        tier = "elevated"
    else:
        tier = "low"

    return {
        "loan_id": loan_id,
        "score": score,
        "tier": tier,
        "days_past_due": days_past_due,
        "broken_promises": broken,
        "payment_count": len(payments),
        "basis": status.get("basis"),
        "note": "A real, transparent rules-based score (days past due + broken promises + "
                "payment consistency) -- not a machine-learning model or LLM call.",
    }


def get_priority_recommendation(loan_id):
    """Sam's "AI Collection Prioritization" -- a real rules-based recommendation, same
    honesty as compute_risk_score(). Two headline outcomes, matching Sam's own
    examples verbatim: "High Probability To Pay -- Contact Today" and "Recovery Risk
    -- Escalate", plus a middle "Standard Follow-Up" for everything else."""

    risk = compute_risk_score(loan_id)
    if not isinstance(risk, dict) or "error" in risk:
        return risk

    promises = list_promises_to_pay(loan_id=loan_id)
    has_kept_promise = any(p.get("status") == "kept" for p in promises)

    if risk["tier"] == "high" or risk["broken_promises"] >= 2:
        recommendation = "recovery_risk"
        label = "Recovery Risk -- Escalate"
    elif risk["tier"] == "low" and (has_kept_promise or risk["days_past_due"] <= 7):
        recommendation = "high_probability_to_pay"
        label = "High Probability To Pay -- Contact Today"
    else:
        recommendation = "standard_follow_up"
        label = "Standard Follow-Up"

    return {
        "loan_id": loan_id,
        "recommendation": recommendation,
        "label": label,
        "risk_score": risk["score"],
        "risk_tier": risk["tier"],
        "basis": risk["basis"],
        "note": risk["note"],
    }


def get_collection_queue(bucket=None):
    """The real, auto-prioritized Work Queue -- every loan with days_past_due >= 3
    (per core/loan_servicing.py's own real-or-simulated delinquency computation),
    grouped into Sam's own 3/7/15/30/60-day buckets, sorted worst-first."""

    loans = _all_loans()
    rows = []

    for loan in loans:
        status = get_simulated_payment_status(loan.id)
        if not isinstance(status, dict):
            continue
        days_past_due = status.get("days_past_due") or 0
        queue_bucket = _queue_bucket(days_past_due)
        if queue_bucket is None:
            continue
        if bucket and queue_bucket != bucket:
            continue

        customer = _customer_brief(_linked_customer_id(loan))
        recommendation = get_priority_recommendation(loan.id)

        rows.append({
            "loan_id": loan.id,
            "finance_number": loan.attributes.get("FinanceNumber"),
            "customer_name": customer.get("name") if customer else None,
            "days_past_due": days_past_due,
            "amount_past_due": status.get("amount_past_due"),
            "queue_bucket": queue_bucket,
            "collection_stage": get_collection_stage(loan.id),
            "priority": recommendation.get("recommendation") if isinstance(recommendation, dict) else None,
            "priority_label": recommendation.get("label") if isinstance(recommendation, dict) else None,
            "basis": status.get("basis"),
        })

    rows.sort(key=lambda r: r["days_past_due"], reverse=True)

    counts = {b: 0 for b in QUEUE_BUCKETS}
    for r in rows:
        counts[r["queue_bucket"]] += 1

    return {
        "total_in_queue": len(rows),
        "bucket_counts": counts,
        "loans": rows,
    }


def log_contact(loan_id, channel, notes, by):
    if channel not in CONTACT_CHANNELS:
        return {"error": f"channel must be one of {CONTACT_CHANNELS}"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    return create_field_note("Finance", channel, notes, by, linked_entity_id=loan_id)


def get_contact_history(loan_id, limit=50):
    return list_field_notes(department="Finance", limit=limit, linked_entity_id=loan_id)


def get_agent_workspace(loan_id):
    """The real, composed Collection Agent Workspace -- last payment, risk score,
    contact history, references, employer info, all in one view for whoever's
    working this loan."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    from core.loan_servicing import _borrower_employment

    customer_id = _linked_customer_id(loan)
    vehicle_id = _linked_vehicle_id(loan)

    payments = list_payments_for_loan(loan_id, include_declined=False)
    last_payment = payments[-1] if payments else None

    status = get_simulated_payment_status(loan_id)
    risk = compute_risk_score(loan_id)
    recommendation = get_priority_recommendation(loan_id)
    promises = list_promises_to_pay(loan_id=loan_id)
    contact_history = get_contact_history(loan_id)

    return {
        "loan_id": loan_id,
        "finance_number": loan.attributes.get("FinanceNumber"),
        "customer": _customer_brief(customer_id),
        "vehicle": _vehicle_brief(vehicle_id),
        "employment": _borrower_employment(customer_id),
        "references": {
            "on_file": False,
            "note": "No personal-reference data model exists anywhere in this codebase yet -- an honest gap, not simulated.",
        },
        "last_payment": {
            "amount": last_payment.attributes.get("amount"),
            "method": last_payment.attributes.get("method"),
            "payment_date": last_payment.attributes.get("payment_date"),
        } if last_payment else None,
        "payment_status": status,
        "risk_score": risk,
        "priority_recommendation": recommendation,
        "promises_to_pay": promises,
        "collection_stage": get_collection_stage(loan_id),
        "collection_stage_history": loan.attributes.get("collection_stage_history") or [],
        "contact_history": [
            {"id": n.id, "category": n.attributes.get("category"), "body": n.attributes.get("body"), "created_by": n.attributes.get("created_by"), "created_at": n.attributes.get("created_at")}
            for n in contact_history
        ],
    }


def get_collections_dashboard():
    queue = get_collection_queue()
    stage_counts = {s: 0 for s in COLLECTION_STAGES}
    for row in queue["loans"]:
        stage = row.get("collection_stage")
        if stage in stage_counts:
            stage_counts[stage] += 1

    high_priority = len([r for r in queue["loans"] if r["priority"] == "recovery_risk"])
    contact_today = len([r for r in queue["loans"] if r["priority"] == "high_probability_to_pay"])

    return {
        "total_in_queue": queue["total_in_queue"],
        "bucket_counts": queue["bucket_counts"],
        "stage_counts": stage_counts,
        "recovery_risk_count": high_priority,
        "contact_today_count": contact_today,
    }
