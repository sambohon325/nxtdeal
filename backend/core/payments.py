"""
core/payments.py -- Finance's "Payments" item, the second slice of Sam's Retail
Automotive Lending Platform expansion (2026-07-17), right after Portfolio / Loan
Management. Sam's own framing: "Your own integrated payment platform... Accept ACH,
Debit Cards, Credit Cards, Cash, Cash App, Venmo, Apple Pay, Google Pay" plus a
Customer Payment Portal (view balance, make a payment, setup auto pay, view
statements, download contracts, request payoff), Auto Draft Management, Promise To
Pay, and Partial Payment Rules.

No real payment gateway is connected anywhere in this sandbox -- actually charging a
card or pulling an ACH draft is honestly SIMULATED (deterministically seeded per
attempt so a given payment doesn't flip outcome on repeat reads, not literal random
noise -- see _simulate_gateway_result()), same disclosure precedent as
core/campaigns.py's activate_campaign()/core/social_posts.py's publish_post(). Cash
payments skip the gateway entirely (a real employee handed real cash to another real
employee -- there's nothing to simulate) and are always approved.

The real piece: once a Payment is approved, it becomes a REAL, first-class ledger
entry -- a Payment is its own entity (not an additive dict on FinanceContract) since
many payments accrue per loan over its life, same "own lifecycle, not a dict on
something else" reasoning DamageReport/WholesaleOffer/OperationsTask/
LoanerAssignment already established in this codebase. This is what upgrades
core/loan_servicing.py's balance/delinquency computation from its own SIMULATED
estimate to a REAL one the moment real payments exist for a loan --
get_real_payment_summary() returns None when no real payments exist yet (so
loan_servicing.py's own simulation stays the honest fallback), and a real computed
summary once they do. loan_servicing.py imports this via a deferred (in-function)
import to avoid a circular top-level import between the two sibling modules -- same
technique this module's own _borrower_employment()-style helpers already use
elsewhere in this codebase for CreditApplication.

Auto Draft Management: a real, standing recurring-payment configuration
(active/paused) per loan. Actually EXECUTING a draft on schedule would need a real
background scheduler -- this codebase has exactly two of those
(core/bot_scheduler.py/core/compliance_scheduler.py), both narrow, and a third was
judged out of scope for this slice, same call session 111's appointment reminders
made. run_due_auto_drafts() is instead a real, explicit, on-demand action (a
"process today's due drafts now" button, not automatic) that still creates real
Payment ledger entries when it runs.

Promise To Pay: a real collections commitment record. kept/broken/pending status is
computed live off real payment history (not stored), same computed-status convention
as core/loan_servicing.py's own loan_status default.

Customer Payment Portal: mirrors core/approval_center.py's real public-token pattern
exactly -- a real unguessable secrets.token_urlsafe(24) link, genuinely
unauthenticated /public/* routes, and a real CUSTOMER_SENTINEL ("customer_via_
payment_portal") distinct from any employee id so it's always possible to tell who
recorded a given payment. Statements and Download Contract are honest gaps -- no
statement-generation or PDF-generation capability exists anywhere in this codebase
(core/deals.py's contract generation is explicitly "no PDF generation this pass").
"""

import hashlib
import math
import secrets
from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import PAYMENT, AUTO_DRAFT, PROMISE_TO_PAY, FINANCE_CONTRACT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.workflow_readiness import workflow_readiness
from core.loan_servicing import _get_loan, _safe_float, _today, _now as _loan_now

CUSTOMER_SENTINEL = "customer_via_payment_portal"

PAYMENT_METHODS = ("ach", "debit_card", "credit_card", "cash", "cash_app", "venmo", "apple_pay", "google_pay")
_GATEWAY_METHODS = ("ach", "debit_card", "credit_card", "cash_app", "venmo", "apple_pay", "google_pay")

SIMULATED_BASIS_GATEWAY = "simulated_payment_gateway"
_DISCLAIMER_GATEWAY = (
    "SIMULATED payment processing -- no real payment gateway (ACH/card processor) is "
    "connected in this system yet. Deterministically generated per payment attempt, "
    "not random noise on repeat reads. Cash payments skip this entirely and are "
    "always approved."
)

_REAL_LEDGER_NOTE = (
    "Real, computed from this loan's actual recorded payment history -- not "
    "simulated. days_past_due/amount_past_due are derived from real cumulative "
    "payments vs. what the real contractual schedule says should have been paid by "
    "now."
)

_DECLINE_REASONS = [
    "Insufficient funds",
    "Card declined by issuer",
    "ACH return -- account closed",
    "Payment method expired",
]

AUTO_DRAFT_STATUSES = ("active", "paused")
PROMISE_STATUSES = ("pending", "kept", "broken")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today_iso():
    return _today().isoformat()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _seeded_int(seed_str, low, high):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest, 16) % span)


def _monthly_rate(loan):
    apr = _safe_float(loan.attributes.get("APR"))
    return (apr / 100.0) / 12.0


# ---------------------------------------------------------------------------
# Payment ledger
# ---------------------------------------------------------------------------

def _all_payments():
    return [e for e in ledger.get_all().values() if e.entity_type == PAYMENT]


def list_payments_for_loan(loan_id, include_declined=True):
    payments = [p for p in _all_payments() if p.attributes.get("loan_id") == loan_id]
    if not include_declined:
        payments = [p for p in payments if p.attributes.get("status") == "approved"]
    payments.sort(key=lambda p: p.attributes.get("payment_date") or "")
    return payments


def _approved_payments_for_loan(loan_id):
    return [p for p in list_payments_for_loan(loan_id) if p.attributes.get("status") == "approved"]


def _current_real_balance_before_payment(loan):
    original = _safe_float(loan.attributes.get("AmountFinanced"))
    approved = _approved_payments_for_loan(loan.id)
    principal_paid = sum(_safe_float(p.attributes.get("principal_portion")) for p in approved)
    return max(0.0, round(original - principal_paid, 2))


def _simulate_gateway_result(payment_id, method, amount):
    """Deterministic simulated gateway approval/decline -- cash always approves (no
    gateway involved). Everything else has a real-feeling ~94% approval rate, seeded
    off the payment's own id so it never flips on repeat reads."""

    if method == "cash":
        return {"approved": True, "decline_reason": None}

    roll = _seeded_int(f"{payment_id}|gateway", 1, 100)
    if roll <= 94:
        return {"approved": True, "decline_reason": None}

    reason = _DECLINE_REASONS[_seeded_int(f"{payment_id}|reason", 0, len(_DECLINE_REASONS) - 1)]
    return {"approved": False, "decline_reason": reason}


def record_payment(loan_id, amount, method, recorded_by, payment_date=None, notes=""):
    """The real payment-recording engine -- used by staff recording a payment taken
    over the phone/in person, by Auto Draft's on-demand run, and by the public
    Customer Payment Portal (with recorded_by=CUSTOMER_SENTINEL)."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    if method not in PAYMENT_METHODS:
        return {"error": f"method must be one of {PAYMENT_METHODS}"}

    amount = _safe_float(amount)
    if not math.isfinite(amount) or amount <= 0:
        return {"error": "amount must be a finite number greater than 0"}

    from core.pci_dss_guard import assert_no_card_data, CardDataDetectedError
    try:
        assert_no_card_data({"notes": notes}, context="record_payment notes")
    except CardDataDetectedError as exc:
        return {
            "error": "payment blocked: cardholder data detected in notes",
            "findings": [{"type": f["type"], "confidence": f["confidence"]} for f in exc.findings],
        }

    from core.workflow_readiness import simulation_block
    # Public customers cannot self-report cash receipt to reduce their debt.
    # Auto-drafts likewise cannot turn a 'cash' method into a receipt.
    if method != "cash" or recorded_by == CUSTOMER_SENTINEL or str(recorded_by).startswith("auto_draft:"):
        blocked = simulation_block("electronic_payments")
        if blocked:
            return blocked

    payment_id = id_generator.generate("PMT")

    gateway_result = _simulate_gateway_result(payment_id, method, amount)

    balance_before = _current_real_balance_before_payment(loan)
    principal_portion = 0.0
    interest_portion = 0.0
    overpayment_credit = 0.0
    if gateway_result["approved"]:
        rate = _monthly_rate(loan)
        interest_due = round(balance_before * rate, 2)
        # Interest is capped at what's actually due and principal at the remaining balance; anything
        # beyond payoff is an unapplied CREDIT, never re-booked as interest income (which previously
        # inflated interest_income and swallowed the customer's overpayment).
        interest_portion = round(min(amount, interest_due), 2)
        principal_portion = round(min(amount - interest_portion, balance_before), 2)
        overpayment_credit = round(max(0.0, amount - interest_portion - principal_portion), 2)

    payment = Entity(
        id=payment_id,
        entity_type=PAYMENT,
        attributes={
            "loan_id": loan_id,
            "amount": amount,
            "method": method,
            "status": "approved" if gateway_result["approved"] else "declined",
            "decline_reason": gateway_result["decline_reason"],
            "principal_portion": principal_portion,
            "interest_portion": interest_portion,
            "overpayment_credit": overpayment_credit,
            "balance_before": balance_before,
            "balance_after": max(0.0, round(balance_before - principal_portion, 2)) if gateway_result["approved"] else balance_before,
            "recorded_by": recorded_by,
            "payment_date": payment_date or _today_iso(),
            "notes": notes,
            "created_at": _now(),
            "basis": "staff_recorded_cash" if method == "cash" else SIMULATED_BASIS_GATEWAY,
            "disclaimer": "Cash receipt recorded by staff; not processor settlement." if method == "cash" else _DISCLAIMER_GATEWAY,
        },
    )

    ledger.add_entity(payment)
    save_graph(GRAPH_PATH)

    return payment


def _deferred_months(loan):
    """How many monthly installments have been formally deferred/extended and so are NOT yet
    expected. A deferral counts its `months`; an extension moves one installment's due date out,
    counted as one month. Without this, granting relief did nothing — the borrower kept accruing
    days-past-due and could be referred to repossession despite the accommodation."""
    total = 0
    for adj in (loan.attributes.get("payment_adjustments") or []):
        kind = adj.get("type")
        if kind == "deferral":
            try:
                total += int(adj.get("months") or 0)
            except (TypeError, ValueError):
                pass
        elif kind == "extension":
            total += 1
    return max(0, total)


def get_real_payment_summary(loan_id):
    """Returns None if no real approved payments exist yet for this loan (the caller
    -- core/loan_servicing.py -- should fall back to its own SIMULATED estimate in
    that case). Returns a real, computed summary once they do: real balance, real
    delinquency bucket/days-past-due derived from actual cumulative payments vs. what
    should have been paid by now on the real contractual schedule."""

    loan = _get_loan(loan_id)
    if not loan:
        return None

    approved = _approved_payments_for_loan(loan_id)
    if not approved:
        return None

    original = _safe_float(loan.attributes.get("AmountFinanced"))
    monthly_payment = _safe_float(loan.attributes.get("MonthlyPayment"))
    contract_date = _parse_date(loan.attributes.get("ContractDate"))

    total_paid = round(sum(_safe_float(p.attributes.get("amount")) for p in approved), 2)
    total_principal_paid = round(sum(_safe_float(p.attributes.get("principal_portion")) for p in approved), 2)
    total_interest_paid = round(sum(_safe_float(p.attributes.get("interest_portion")) for p in approved), 2)
    real_balance = max(0.0, round(original - total_principal_paid, 2))
    last_payment_date = approved[-1].attributes.get("payment_date")

    from core.loan_servicing import _months_elapsed as _months_elapsed_ls

    stored_status = loan.attributes.get("loan_status")
    if stored_status in ("repossessed", "charged_off"):
        return {
            "loan_id": loan_id,
            "total_paid": total_paid,
            "total_principal_paid": total_principal_paid,
            "total_interest_paid": total_interest_paid,
            "real_balance": real_balance,
            "last_payment_date": last_payment_date,
            "payment_count": len(approved),
            "bucket": stored_status,
            "days_past_due": 0,
            "amount_past_due": 0.0,
            "basis": "real_payment_ledger",
            "disclaimer": _REAL_LEDGER_NOTE,
        }

    elapsed = _months_elapsed_ls(contract_date, _today()) if contract_date else 0
    # Honor granted deferrals/extensions — those installments aren't expected yet.
    effective_elapsed = max(0, elapsed - _deferred_months(loan))
    expected_cumulative = round(effective_elapsed * monthly_payment, 2)
    shortfall = round(expected_cumulative - total_paid, 2)

    if shortfall <= 0 or monthly_payment <= 0:
        days_past_due = 0
    else:
        days_past_due = max(1, round((shortfall / monthly_payment) * 30))

    if days_past_due == 0:
        bucket = "current"
    elif days_past_due < 30:
        bucket = "30_day"
    elif days_past_due < 60:
        bucket = "60_day"
    else:
        bucket = "90_day"

    return {
        "loan_id": loan_id,
        "total_paid": total_paid,
        "total_principal_paid": total_principal_paid,
        "total_interest_paid": total_interest_paid,
        "real_balance": real_balance,
        "last_payment_date": last_payment_date,
        "payment_count": len(approved),
        "expected_cumulative": expected_cumulative,
        "shortfall": max(0.0, shortfall),
        "bucket": bucket,
        "days_past_due": days_past_due,
        "amount_past_due": max(0.0, shortfall),
        "basis": "real_payment_ledger",
        "disclaimer": _REAL_LEDGER_NOTE,
    }


# ---------------------------------------------------------------------------
# Auto Draft Management
# ---------------------------------------------------------------------------

def _all_auto_drafts():
    return [e for e in ledger.get_all().values() if e.entity_type == AUTO_DRAFT]


def create_auto_draft(loan_id, amount, method, day_of_month, created_by):
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("automatic_payments")
    if blocked:
        return blocked
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    if method not in PAYMENT_METHODS:
        return {"error": f"method must be one of {PAYMENT_METHODS}"}

    amount = _safe_float(amount)
    if amount <= 0:
        return {"error": "amount must be greater than 0"}

    try:
        day_of_month = int(day_of_month)
    except (TypeError, ValueError):
        return {"error": "day_of_month must be an integer"}
    if not (1 <= day_of_month <= 28):
        return {"error": "day_of_month must be between 1 and 28 (to avoid short-month edge cases)"}

    draft_id = id_generator.generate("DRFT")
    draft = Entity(
        id=draft_id,
        entity_type=AUTO_DRAFT,
        attributes={
            "loan_id": loan_id,
            "amount": amount,
            "method": method,
            "day_of_month": day_of_month,
            "status": "active",
            "created_by": created_by,
            "created_at": _now(),
            "last_run_at": None,
            "last_run_month": None,
            "run_history": [],
        },
    )
    ledger.add_entity(draft)
    save_graph(GRAPH_PATH)
    return draft


def _get_auto_draft(draft_id):
    e = ledger.get_entity(draft_id)
    if not e or e.entity_type != AUTO_DRAFT:
        return None
    return e


def set_auto_draft_status(draft_id, status, by):
    if status not in AUTO_DRAFT_STATUSES:
        return {"error": f"status must be one of {AUTO_DRAFT_STATUSES}"}
    draft = _get_auto_draft(draft_id)
    if not draft:
        return {"error": f"Auto draft '{draft_id}' not found"}
    if status == "active":
        from core.workflow_readiness import simulation_block
        blocked = simulation_block("automatic_payments")
        if blocked:
            return blocked
    draft.attributes["status"] = status
    draft.attributes["status_changed_by"] = by
    draft.attributes["status_changed_at"] = _now()
    save_graph(GRAPH_PATH)
    return draft


def list_auto_drafts(loan_id=None, status=None):
    drafts = _all_auto_drafts()
    if loan_id:
        drafts = [d for d in drafts if d.attributes.get("loan_id") == loan_id]
    if status:
        drafts = [d for d in drafts if d.attributes.get("status") == status]
    return drafts


def run_due_auto_drafts(run_by):
    """Real, explicit, on-demand action -- NOT an automatic background job (see
    module docstring). Processes every active AutoDraft whose day_of_month matches
    today and hasn't already run this calendar month, via the real record_payment()
    engine -- each run creates a real Payment ledger entry, approved or declined per
    the same simulated gateway every manually-recorded payment goes through."""

    from core.workflow_readiness import simulation_block
    blocked = simulation_block("automatic_payments")
    if blocked:
        return blocked

    today = _today()
    this_month_key = f"{today.year:04d}-{today.month:02d}"
    processed = []

    for draft in list_auto_drafts(status="active"):
        if _safe_float(draft.attributes.get("day_of_month")) != today.day:
            continue
        if draft.attributes.get("last_run_month") == this_month_key:
            continue

        payment = record_payment(
            draft.attributes["loan_id"],
            draft.attributes["amount"],
            draft.attributes["method"],
            recorded_by=f"auto_draft:{run_by}",
            notes="Processed via Auto Draft",
        )

        outcome = {
            "payment_id": payment.id if hasattr(payment, "id") else None,
            "status": payment.attributes.get("status") if hasattr(payment, "attributes") else "error",
            "run_at": _now(),
        }
        draft.attributes.setdefault("run_history", []).append(outcome)
        draft.attributes["last_run_at"] = _now()
        draft.attributes["last_run_month"] = this_month_key
        processed.append({"draft_id": draft.id, **outcome})

    if processed:
        save_graph(GRAPH_PATH)

    return {"processed_count": len(processed), "results": processed}


# ---------------------------------------------------------------------------
# Promise To Pay
# ---------------------------------------------------------------------------

def _all_promises():
    return [e for e in ledger.get_all().values() if e.entity_type == PROMISE_TO_PAY]


def create_promise_to_pay(loan_id, promise_date, amount, reason, created_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    if not _parse_date(promise_date):
        return {"error": "promise_date must be a valid ISO date"}

    amount = _safe_float(amount)
    if amount <= 0:
        return {"error": "amount must be greater than 0"}

    ptp_id = id_generator.generate("PTP")
    ptp = Entity(
        id=ptp_id,
        entity_type=PROMISE_TO_PAY,
        attributes={
            "loan_id": loan_id,
            "promise_date": promise_date,
            "amount": amount,
            "reason": reason,
            "created_by": created_by,
            "created_at": _now(),
        },
    )
    ledger.add_entity(ptp)
    save_graph(GRAPH_PATH)
    return ptp


def _get_promise(ptp_id):
    e = ledger.get_entity(ptp_id)
    if not e or e.entity_type != PROMISE_TO_PAY:
        return None
    return e


def get_promise_status(ptp_id):
    """kept/broken/pending is computed live, not stored -- kept the moment enough
    real payments have landed since the promise was made to cover its amount, broken
    once the promise_date has passed without that, pending otherwise."""

    ptp = _get_promise(ptp_id)
    if not ptp:
        return {"error": f"Promise to pay '{ptp_id}' not found"}

    loan_id = ptp.attributes["loan_id"]
    created_at = ptp.attributes["created_at"]
    promise_date = _parse_date(ptp.attributes["promise_date"])
    amount = _safe_float(ptp.attributes["amount"])

    approved = _approved_payments_for_loan(loan_id)
    paid_since = round(sum(
        _safe_float(p.attributes.get("amount"))
        for p in approved
        if (p.attributes.get("payment_date") or "") >= created_at[:10]
    ), 2)

    if paid_since >= amount:
        status = "kept"
    elif promise_date and promise_date < _today():
        status = "broken"
    else:
        status = "pending"

    return {
        "id": ptp.id,
        "loan_id": loan_id,
        "promise_date": ptp.attributes["promise_date"],
        "amount": amount,
        "reason": ptp.attributes.get("reason"),
        "created_by": ptp.attributes.get("created_by"),
        "created_at": created_at,
        "paid_since_promise": paid_since,
        "status": status,
    }


def list_promises_to_pay(loan_id=None, status=None):
    promises = _all_promises()
    if loan_id:
        promises = [p for p in promises if p.attributes.get("loan_id") == loan_id]
    results = [get_promise_status(p.id) for p in promises]
    if status:
        results = [r for r in results if r.get("status") == status]
    results.sort(key=lambda r: r.get("promise_date") or "", reverse=True)
    return results


# ---------------------------------------------------------------------------
# Extension / Deferral -- Partial Payment Rules' two workflow accommodations
# ---------------------------------------------------------------------------

def record_extension(loan_id, new_next_due_date, reason, recorded_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}
    if not _parse_date(new_next_due_date):
        return {"error": "new_next_due_date must be a valid ISO date"}

    entry = {
        "type": "extension",
        "new_next_due_date": new_next_due_date,
        "reason": reason,
        "recorded_by": recorded_by,
        "recorded_at": _now(),
    }
    loan.attributes.setdefault("payment_adjustments", []).append(entry)
    save_graph(GRAPH_PATH)
    return {"loan_id": loan_id, "adjustment": entry}


def record_deferral(loan_id, months, reason, recorded_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}
    try:
        months = int(months)
    except (TypeError, ValueError):
        return {"error": "months must be an integer"}
    if months <= 0:
        return {"error": "months must be greater than 0"}

    entry = {
        "type": "deferral",
        "months": months,
        "reason": reason,
        "recorded_by": recorded_by,
        "recorded_at": _now(),
    }
    loan.attributes.setdefault("payment_adjustments", []).append(entry)
    save_graph(GRAPH_PATH)
    return {"loan_id": loan_id, "adjustment": entry}


def list_payment_adjustments(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}
    return loan.attributes.get("payment_adjustments") or []


# ---------------------------------------------------------------------------
# Payoff requests -- part of the Customer Payment Portal
# ---------------------------------------------------------------------------

def request_payoff(loan_id, requested_by, notes=""):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    entry = {
        "id": f"payoff-{secrets.token_hex(4)}",
        "requested_by": requested_by,
        "requested_at": _now(),
        "notes": notes,
        "status": "requested",
    }
    loan.attributes.setdefault("payoff_requests", []).append(entry)
    save_graph(GRAPH_PATH)
    return {"loan_id": loan_id, "request": entry}


def fulfill_payoff_request(loan_id, request_id, fulfilled_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    requests = loan.attributes.get("payoff_requests") or []
    for r in requests:
        if r["id"] == request_id:
            if r["status"] == "fulfilled":
                return {"error": "This payoff request has already been fulfilled"}
            r["status"] = "fulfilled"
            r["fulfilled_by"] = fulfilled_by
            r["fulfilled_at"] = _now()
            save_graph(GRAPH_PATH)
            return {"loan_id": loan_id, "request": r}

    return {"error": f"Payoff request '{request_id}' not found on loan '{loan_id}'"}


def list_payoff_requests(loan_id=None, status=None):
    if loan_id:
        loans = [_get_loan(loan_id)] if _get_loan(loan_id) else []
    else:
        from core.loan_servicing import _all_loans as _all_loans_ls
        loans = _all_loans_ls()

    results = []
    for loan in loans:
        for r in (loan.attributes.get("payoff_requests") or []):
            if not status or r.get("status") == status:
                results.append({"loan_id": loan.id, **r})
    results.sort(key=lambda r: r.get("requested_at") or "", reverse=True)
    return results


# ---------------------------------------------------------------------------
# Customer Payment Portal -- real public unauthenticated link, same pattern as
# core/approval_center.py
# ---------------------------------------------------------------------------

def generate_payment_portal_link(loan_id, created_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    token = secrets.token_urlsafe(24)
    loan.attributes["payment_portal_link"] = {
        "token": token,
        "created_by": created_by,
        "created_at": _now(),
        "revoked": False,
    }
    save_graph(GRAPH_PATH)
    return {"loan_id": loan_id, "token": token, "path": f"/pay/{token}"}


def get_payment_portal_link_status(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    link = loan.attributes.get("payment_portal_link")
    if not link:
        return {"loan_id": loan_id, "exists": False}
    return {"loan_id": loan_id, "exists": True, **link, "path": f"/pay/{link['token']}"}


def revoke_payment_portal_link(loan_id, revoked_by):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    link = loan.attributes.get("payment_portal_link")
    if not link:
        return {"error": "No payment portal link exists for this loan"}
    if link.get("revoked"):
        return {"error": "This payment portal link is already revoked"}

    link["revoked"] = True
    link["revoked_by"] = revoked_by
    link["revoked_at"] = _now()
    loan.attributes["payment_portal_link"] = link
    save_graph(GRAPH_PATH)
    return {"loan_id": loan_id, "revoked": True}


def _find_loan_by_token(token):
    for e in ledger.get_all().values():
        if e.entity_type == FINANCE_CONTRACT:
            link = e.attributes.get("payment_portal_link")
            if link and link.get("token") == token:
                return e
    return None


def get_public_portal_view(token):
    """PUBLIC, unauthenticated -- a real customer viewing their own loan balance/
    payment history/auto-draft status via a real shareable link."""

    loan = _find_loan_by_token(token)
    if not loan:
        return {"error": "This payment link is invalid or has expired."}

    link = loan.attributes["payment_portal_link"]
    if link.get("revoked"):
        return {"error": "This payment link has been revoked. Please contact the dealership.", "revoked": True}

    from core.loan_servicing import get_loan_financials, get_simulated_payment_status, _customer_brief, _vehicle_brief, _linked_customer_id, _linked_vehicle_id

    real_summary = get_real_payment_summary(loan.id)
    if real_summary:
        balance = real_summary["real_balance"]
        balance_basis = "real_payment_ledger"
    else:
        financials = get_loan_financials(loan.id)
        balance = financials.get("schedule_implied_balance")
        balance_basis = "schedule_implied_estimate"

    customer = _customer_brief(_linked_customer_id(loan))
    vehicle = _vehicle_brief(_linked_vehicle_id(loan))
    recent_payments = list_payments_for_loan(loan.id, include_declined=False)[-10:]
    active_drafts = list_auto_drafts(loan_id=loan.id, status="active")

    return {
        "revoked": link.get("revoked", False),
        "payment_readiness": workflow_readiness()["electronic_payments"],
        "finance_number": loan.attributes.get("FinanceNumber"),
        "customer_name": customer.get("name") if customer else None,
        "vehicle": f"{vehicle['year']} {vehicle['make']} {vehicle['model']}".strip() if vehicle else None,
        "balance": balance,
        "balance_basis": balance_basis,
        "monthly_payment": _safe_float(loan.attributes.get("MonthlyPayment")),
        "recent_payments": [
            {
                "amount": p.attributes.get("amount"),
                "method": p.attributes.get("method"),
                "payment_date": p.attributes.get("payment_date"),
                "status": p.attributes.get("status"),
            }
            for p in recent_payments
        ],
        "active_auto_drafts": [
            {"id": d.id, "amount": d.attributes.get("amount"), "method": d.attributes.get("method"), "day_of_month": d.attributes.get("day_of_month")}
            for d in active_drafts
        ],
        "not_yet_tracked": {
            "statements": "No statement-generation capability exists in this system yet.",
            "contract_download": "No PDF-generation capability exists in this system yet -- core/deals.py's own contract generation is explicitly on-screen only.",
        },
    }


def submit_public_payment(token, amount, method):
    """PUBLIC, unauthenticated -- the real customer-initiated payment. Recorded with
    recorded_by=CUSTOMER_SENTINEL, an honest, distinct marker from any employee id or
    the auto_draft: prefix."""

    loan = _find_loan_by_token(token)
    if not loan:
        return {"error": "This payment link is invalid or has expired."}

    link = loan.attributes["payment_portal_link"]
    if link.get("revoked"):
        return {"error": "This payment link has been revoked. Please contact the dealership."}

    result = record_payment(loan.id, amount, method, recorded_by=CUSTOMER_SENTINEL)
    if isinstance(result, dict) and "error" in result:
        return result

    return get_public_portal_view(token)


def submit_public_payoff_request(token, notes=""):
    """PUBLIC, unauthenticated -- a real customer-initiated payoff request."""

    loan = _find_loan_by_token(token)
    if not loan:
        return {"error": "This payment link is invalid or has expired."}

    link = loan.attributes["payment_portal_link"]
    if link.get("revoked"):
        return {"error": "This payment link has been revoked. Please contact the dealership."}

    return request_payoff(loan.id, CUSTOMER_SENTINEL, notes=notes)


def get_payments_dashboard():
    """Sam's own Payments module -- real totals across the whole real ledger."""

    payments = _all_payments()
    approved = [p for p in payments if p.attributes.get("status") == "approved"]
    declined = [p for p in payments if p.attributes.get("status") == "declined"]

    by_method = {}
    for p in approved:
        m = p.attributes.get("method")
        by_method[m] = by_method.get(m, 0) + 1

    active_drafts = list_auto_drafts(status="active")
    paused_drafts = list_auto_drafts(status="paused")

    pending_promises = list_promises_to_pay(status="pending")
    kept_promises = list_promises_to_pay(status="kept")
    broken_promises = list_promises_to_pay(status="broken")

    pending_payoffs = list_payoff_requests(status="requested")

    return {
        "total_payments": len(payments),
        "approved_payments": len(approved),
        "declined_payments": len(declined),
        "total_collected": round(sum(_safe_float(p.attributes.get("amount")) for p in approved), 2),
        "by_method": by_method,
        "active_auto_drafts": len(active_drafts),
        "paused_auto_drafts": len(paused_drafts),
        "promises_to_pay": {
            "pending": len(pending_promises),
            "kept": len(kept_promises),
            "broken": len(broken_promises),
        },
        "pending_payoff_requests": len(pending_payoffs),
        "basis": SIMULATED_BASIS_GATEWAY,
        "disclaimer": _DISCLAIMER_GATEWAY,
    }
