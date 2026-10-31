"""
core/loan_servicing.py -- Finance's Portfolio / Loan Management, the first slice of
Sam's "Retail Automotive Lending Platform" expansion (2026-07-17). Sam's own framing:
Finance shouldn't stop at Funded/Delivered -- for BHPH and finance-company operation,
Funded is the START of a loan's real life (Lead -> Deal -> Credit -> Approval ->
Contract -> Funding -> Loan Servicing -> Collections -> Repossession -> Recovery ->
Payoff). Portfolio is the piece Sam called out explicitly as "the heart of BHPH and
finance company operations" -- the master Loan record everything else (Payments,
Collections, GPS & Device Management, Starter Interrupt, Repossessions -- all
separately scoped future slices from this same message) will attach to.

Deliberately NOT a new entity type -- a FinanceContract already IS the loan (same
"reuse, don't duplicate" discipline this whole codebase follows: core/deals.py's
fund_deal() already creates a real FinanceContract for every funded Deal, and
imports/finance_import.py has created 315 more from historical CSV data). This module
adds real loan-servicing behavior on top of that existing entity:

  - a real amortization engine (standard fixed-rate monthly schedule off
    AmountFinanced/APR/TermMonths) computing a schedule-implied current balance,
    terms remaining, and a full month-by-month payment schedule for every one of the
    real FinanceContract entities in this graph -- 100% real math over real contract
    terms already on file, no fabrication needed for this part. It assumes on-schedule
    payments (there is no real payment ledger yet -- that's the next slice, Payments),
    stated plainly wherever the balance is surfaced.

  - loan_status as a stored, additive attribute (active/paid_off/repossessed/
    charged_off) on the FinanceContract's own attributes -- computed on first read
    (paid_off once the amortization schedule fully elapses) and settable by future
    modules (Repossessions/Payments), same computed-default-then-real-value convention
    as vehicle_lifecycle.py's lifecycle_status / repair_orders.py's ro_stage.

  - a Loan Timeline composing what's real today (Originated + Funded, both equal to
    ContractDate in this data model since desking-to-funding is same-day here) plus
    honest, clearly-labeled empty slots for Payment History / Collection Activity /
    Repossession Events -- these fill in for real once the Payments / Collections /
    Repossessions slices ship, not fabricated here.

  - SIMULATED payment/delinquency status per loan (current / 30-day / 60-day / 90-day /
    repossessed / charged_off, plus a paid-through date and an amount-past-due),
    per Sam's explicit standing instruction from this same session's kickoff message,
    following the precedent set session 110 on Inventory's Acquisitions/Pricing slices:
    "when a lack of data is a problem, lets simply make up simulated data to
    accommodate it." No real payment ledger exists anywhere in this codebase yet, so
    there is no real way to know whether any of these loans are actually current or
    delinquent. Deterministically seeded via hashlib.sha256 off the loan's own id (same
    convention as core/pricing_desk.py / core/acquisitions.py) so a given loan reads
    the same simulated status every time, not fresh noise per call, and always carries
    basis="simulated_payment_status" plus an explicit disclaimer. One real constraint
    layered on top of the simulation: a loan can never be simulated as delinquent
    before its first scheduled payment could plausibly be due -- zero full months
    elapsed since ContractDate always forces "current" -- a small honesty check that
    keeps a loan just funded live through the Deal Desk from reading as impossibly
    already-late.

Employer / personal references: this module does NOT fabricate personal borrower
detail like an employer name or references -- unlike simulated market/pricing data,
that reads too much like fabricated customer PII to responsibly simulate. Where a real
core/credit_app.py CreditApplication exists for this loan's customer (session 104),
its real employer_name/monthly_income/employment_status/housing fields are surfaced
directly. Where none exists (true for the large majority of these historical,
pre-Credit-Application loans), this module says so plainly rather than inventing an
employer. Personal references have no backing data model anywhere in this codebase at
all (not even CreditApplication tracks them) -- an honest, explicit gap.

GPS Status / Starter-Interrupt Status / Collateral custody state are deliberately left
out of the loan detail entirely rather than half-built here -- Sam scoped GPS & Device
Management, Starter Interrupt Management, and Repossessions as their own dedicated
future Finance menu items in this same message, and defining that data shape here
first would risk preempting or duplicating that slice's own design. Collateral status
in THIS module is simply loan_status itself (active/paid_off/repossessed/charged_off).
"""

import hashlib
from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger
from core.entity_types import FINANCE_CONTRACT, CUSTOMER, VEHICLE, LENDER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

SIMULATED_BASIS = "simulated_payment_status"

_DISCLAIMER_PAYMENT_STATUS = (
    "SIMULATED payment/delinquency status -- no real payment ledger exists in this "
    "system yet (see the upcoming Payments module). Deterministically generated from "
    "this loan's own id, so the same loan always reads the same simulated status "
    "rather than fresh random noise on every call. A loan with zero full months "
    "elapsed since its contract date is always forced to 'current' regardless of the "
    "simulation, since it cannot plausibly be delinquent yet."
)

LOAN_STATUSES = ("active", "paid_off", "repossessed", "charged_off")

DELINQUENCY_BUCKETS = ("current", "30_day", "60_day", "90_day", "repossessed", "charged_off")

# Realistic-ish BHPH portfolio distribution: mostly current, a shrinking tail of
# delinquency severity, a small sliver of repo/charge-off. Weights sum to 100.
_BUCKET_WEIGHTS = [
    ("current", 68),
    ("30_day", 14),
    ("60_day", 8),
    ("90_day", 5),
    ("repossessed", 3),
    ("charged_off", 2),
]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _months_elapsed(start, end):
    """Whole calendar months elapsed from start to end, floored at 0. Doesn't count a
    partial month started this same calendar day as a full month."""

    if not start or not end or end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(0, months)


def _seeded_int(seed_str, low, high):
    """Deterministic pseudo-random int in [low, high] -- same convention as
    core/pricing_desk.py / core/acquisitions.py's _seeded_int()."""

    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest, 16) % span)


def _all_loans():
    return [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT]


def _get_loan(loan_id):
    e = ledger.get_entity(loan_id)
    if not e or e.entity_type != FINANCE_CONTRACT:
        return None
    return e


def _linked_customer_id(loan):
    for r in ledger.get_relationships():
        if r.target_id == loan.id and r.relationship_type == "FINANCED_BY":
            return r.source_id
    return None


def _linked_vehicle_id(loan):
    for r in ledger.get_relationships():
        if r.source_id == loan.id and r.relationship_type == "COVERS":
            return r.target_id
    return None


def _linked_lender_id(loan):
    for r in ledger.get_relationships():
        if r.source_id == loan.id and r.relationship_type == "FUNDED_BY":
            return r.target_id
    return None


# ---------------------------------------------------------------------------
# Amortization engine -- real math over real contract terms
# ---------------------------------------------------------------------------

def compute_amortization_schedule(principal, apr, term_months):
    """Standard fixed-rate monthly amortization schedule. Returns a list of
    {period, payment, principal_portion, interest_portion, balance} dicts, period 1
    through term_months. Real math, no simulation -- the same formula
    core/deals.py's monthly-payment estimation already relies on for desking."""

    principal = _safe_float(principal)
    apr = _safe_float(apr)
    term_months = _safe_int(term_months)

    if principal <= 0 or term_months <= 0:
        return []

    monthly_rate = (apr / 100.0) / 12.0

    if monthly_rate == 0:
        payment = round(principal / term_months, 2)
    else:
        payment = round(
            principal * (monthly_rate * (1 + monthly_rate) ** term_months)
            / ((1 + monthly_rate) ** term_months - 1),
            2,
        )

    schedule = []
    balance = principal
    for period in range(1, term_months + 1):
        interest_portion = round(balance * monthly_rate, 2)
        principal_portion = round(payment - interest_portion, 2)
        if period == term_months:
            # Final payment absorbs any rounding drift so balance lands exactly on 0.
            principal_portion = round(balance, 2)
            payment_this_period = round(principal_portion + interest_portion, 2)
        else:
            payment_this_period = payment
        balance = round(balance - principal_portion, 2)
        if balance < 0:
            balance = 0.0
        schedule.append({
            "period": period,
            "payment": payment_this_period,
            "principal_portion": principal_portion,
            "interest_portion": interest_portion,
            "balance": balance,
        })

    return schedule


def _schedule_position(loan):
    """Returns (elapsed_months, schedule, current_row_or_None) for a loan, based on
    real ContractDate/AmountFinanced/APR/TermMonths and elapsed real time since then."""

    principal = _safe_float(loan.attributes.get("AmountFinanced"))
    apr = _safe_float(loan.attributes.get("APR"))
    term_months = _safe_int(loan.attributes.get("TermMonths"))
    contract_date = _parse_date(loan.attributes.get("ContractDate"))

    schedule = compute_amortization_schedule(principal, apr, term_months)
    if not schedule or not contract_date:
        return 0, schedule, None

    elapsed = _months_elapsed(contract_date, _today())
    elapsed = min(elapsed, term_months)

    current_row = schedule[elapsed - 1] if elapsed > 0 else None
    return elapsed, schedule, current_row


def get_loan_financials(loan_id):
    """Original amount, schedule-implied current balance, terms remaining, and the
    full payment schedule -- all real math over this loan's own real contract terms.
    HEURISTIC in one honest sense: it assumes on-schedule payment history, since no
    real payment ledger exists yet."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    principal = _safe_float(loan.attributes.get("AmountFinanced"))
    apr = _safe_float(loan.attributes.get("APR"))
    term_months = _safe_int(loan.attributes.get("TermMonths"))
    monthly_payment = _safe_float(loan.attributes.get("MonthlyPayment"))
    contract_date = loan.attributes.get("ContractDate")

    elapsed, schedule, current_row = _schedule_position(loan)
    balance = current_row["balance"] if current_row else (schedule[0]["balance"] if schedule and elapsed == 0 else principal)
    if elapsed == 0 and schedule:
        balance = principal

    terms_remaining = max(0, term_months - elapsed)

    from core.payments import get_real_payment_summary

    real_summary = get_real_payment_summary(loan_id)

    return {
        "loan_id": loan_id,
        "original_amount": principal,
        "apr": apr,
        "term_months": term_months,
        "monthly_payment": monthly_payment,
        "contract_date": contract_date,
        "months_elapsed": elapsed,
        "terms_remaining": terms_remaining,
        "schedule_implied_balance": balance,
        "schedule_implied_paid_off": terms_remaining == 0 and bool(schedule),
        "real_balance": real_summary["real_balance"] if real_summary else None,
        "current_balance": real_summary["real_balance"] if real_summary else balance,
        "current_balance_basis": "real_payment_ledger" if real_summary else "schedule_implied_estimate",
        "note": (
            "schedule_implied_balance/terms_remaining assume on-schedule payments -- "
            "no real payment ledger exists yet (see the upcoming Payments module). "
            "real_balance/current_balance is the real, payment-ledger-derived figure "
            "once real payments exist for this loan (current_balance_basis tells you "
            "which one current_balance actually is). original_amount/apr/term_months/"
            "monthly_payment are the loan's real contract terms as funded."
        ),
        "payment_schedule": schedule,
    }


# ---------------------------------------------------------------------------
# loan_status -- computed default, then a real stored value
# ---------------------------------------------------------------------------

def get_loan_status(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    stored = loan.attributes.get("loan_status")
    if stored in LOAN_STATUSES:
        return stored

    elapsed, schedule, _ = _schedule_position(loan)
    term_months = _safe_int(loan.attributes.get("TermMonths"))
    if schedule and elapsed >= term_months and term_months > 0:
        return "paid_off"
    return "active"


def set_loan_status(loan_id, status, set_by, reason=""):
    """Real mutation, reserved for future modules (Repossessions marking a loan
    repossessed, Payments marking one charged off/paid) -- exposed here now so this
    module's own API surface is complete, even though nothing calls it yet."""

    if status not in LOAN_STATUSES:
        return {"error": f"status must be one of {LOAN_STATUSES}"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    loan.attributes["loan_status"] = status
    history = loan.attributes.setdefault("loan_status_history", [])
    history.append({"status": status, "set_by": set_by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return loan


# ---------------------------------------------------------------------------
# SIMULATED payment / delinquency status
# ---------------------------------------------------------------------------

def get_simulated_payment_status(loan_id):
    """Despite the name (kept for backward compatibility with every existing
    caller/frontend type), this now prefers REAL data the moment it exists: if
    core/payments.py has real approved Payment records for this loan, that real,
    payment-ledger-derived bucket/days-past-due/amount-past-due is returned instead
    of the simulated estimate below -- see core/payments.py's get_real_payment_summary()."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    from core.payments import get_real_payment_summary

    real_summary = get_real_payment_summary(loan_id)
    if real_summary:
        return {
            "loan_id": loan_id,
            "bucket": real_summary["bucket"],
            "days_past_due": real_summary["days_past_due"],
            "amount_past_due": real_summary["amount_past_due"],
            "last_payment_date": real_summary["last_payment_date"],
            "basis": real_summary["basis"],
            "disclaimer": real_summary["disclaimer"],
        }

    elapsed, _, _ = _schedule_position(loan)
    # Honor granted deferrals/extensions here too, so a fully-deferred loan reads "current".
    from core.payments import _deferred_months
    elapsed = max(0, elapsed - _deferred_months(loan))
    monthly_payment = _safe_float(loan.attributes.get("MonthlyPayment"))

    stored_status = loan.attributes.get("loan_status")
    if stored_status in ("repossessed", "charged_off", "paid_off"):
        bucket = stored_status if stored_status != "paid_off" else "current"
    elif elapsed == 0:
        bucket = "current"
    else:
        roll = _seeded_int(f"{loan_id}|bucket", 1, 100)
        cumulative = 0
        bucket = "current"
        for name, weight in _BUCKET_WEIGHTS:
            cumulative += weight
            if roll <= cumulative:
                bucket = name
                break

    days_past_due = {
        "current": 0,
        "30_day": _seeded_int(f"{loan_id}|dpd30", 1, 29),
        "60_day": _seeded_int(f"{loan_id}|dpd60", 30, 59),
        "90_day": _seeded_int(f"{loan_id}|dpd90", 60, 120),
        "repossessed": _seeded_int(f"{loan_id}|dpdrepo", 60, 150),
        "charged_off": _seeded_int(f"{loan_id}|dpdco", 90, 210),
    }[bucket]

    amount_past_due = round(monthly_payment * (days_past_due / 30.0), 2) if bucket != "current" else 0.0

    last_payment_date = (_today() - timedelta(days=days_past_due)).isoformat() if days_past_due else _today().isoformat()

    return {
        "loan_id": loan_id,
        "bucket": bucket,
        "days_past_due": days_past_due,
        "amount_past_due": amount_past_due,
        "last_payment_date": last_payment_date,
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_PAYMENT_STATUS,
    }


# ---------------------------------------------------------------------------
# Borrower / Vehicle / Loan Timeline composition
# ---------------------------------------------------------------------------

def _customer_brief(customer_id):
    if not customer_id:
        return None
    c = ledger.get_entity(customer_id)
    if not c or c.entity_type != CUSTOMER:
        return None
    return {
        "id": c.id,
        "name": f"{c.attributes.get('FirstName', '')} {c.attributes.get('LastName', '')}".strip(),
        "email": c.attributes.get("Email"),
        "phone": c.attributes.get("Phone"),
        "address": c.attributes.get("Address"),
        "city": c.attributes.get("City"),
        "state": c.attributes.get("State"),
        "zip": c.attributes.get("Zip"),
        "credit_score": c.attributes.get("CreditScore"),
    }


def _borrower_employment(customer_id):
    """Real employer/income data if a core/credit_app.py CreditApplication exists for
    this customer; an honest 'not on file' state otherwise. See module docstring for
    why this is never fabricated."""

    if not customer_id:
        return {"on_file": False, "note": "No customer linked to this loan."}

    from core.credit_app import list_credit_applications

    apps = list_credit_applications(customer_id=customer_id)
    if not apps:
        return {
            "on_file": False,
            "note": "No credit application on file for this customer -- this loan predates "
                    "or bypassed the Credit Application workflow, so no real employer/income "
                    "data exists for it. Not fabricated.",
        }

    latest = apps[0]
    applicant = latest.attributes.get("applicant") or {}
    return {
        "on_file": True,
        "source_credit_application_id": latest.id,
        "employment_status": applicant.get("employment_status"),
        "employer_name": applicant.get("employer_name"),
        "years_at_employer": applicant.get("years_at_employer"),
        "monthly_income": applicant.get("monthly_income"),
        "housing_status": applicant.get("housing_status"),
        "monthly_housing_payment": applicant.get("monthly_housing_payment"),
    }


def _vehicle_brief(vehicle_id):
    if not vehicle_id:
        return None
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return {
        "id": v.id,
        "vin": v.attributes.get("VIN"),
        "stock_number": v.attributes.get("StockNumber"),
        "year": v.attributes.get("Year"),
        "make": v.attributes.get("Make"),
        "model": v.attributes.get("Model"),
        "trim": v.attributes.get("Trim"),
        "color": v.attributes.get("Color"),
        "mileage": v.attributes.get("Mileage"),
    }


def _lender_brief(lender_id):
    if not lender_id:
        return None
    l = ledger.get_entity(lender_id)
    if not l or l.entity_type != LENDER:
        return None
    return {"id": l.id, "name": l.attributes.get("Name")}


def get_loan_timeline(loan_id):
    """Real events this data model actually has (Originated + Funded, both equal to
    ContractDate here since desking-to-funding is same-day) plus honest, clearly
    labeled empty slots for the three event types future slices will populate."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    contract_date = loan.attributes.get("ContractDate")
    events = []
    if contract_date:
        events.append({"type": "originated", "at": contract_date, "note": "Contract originated."})
        events.append({"type": "funded", "at": contract_date, "note": "Loan funded."})

    status_history = loan.attributes.get("loan_status_history") or []
    for h in status_history:
        events.append({"type": "status_change", "at": h.get("at"), "note": f"Status set to '{h.get('status')}' by {h.get('set_by')}" + (f" -- {h.get('reason')}" if h.get("reason") else "")})

    from core.payments import list_payments_for_loan
    from core.repossessions import get_case_history_for_loan

    payments = list_payments_for_loan(loan_id, include_declined=False)
    payment_entries = [
        {
            "at": p.attributes.get("payment_date"),
            "note": f"Payment of ${_safe_float(p.attributes.get('amount')):,.2f} via {p.attributes.get('method')} recorded by {p.attributes.get('recorded_by')}.",
        }
        for p in payments
    ]

    repossession_entries = get_case_history_for_loan(loan_id)

    events.sort(key=lambda e: e.get("at") or "")

    return {
        "loan_id": loan_id,
        "events": events,
        "payment_history": {
            "entries": payment_entries,
            "note": "Real recorded payments (core/payments.py). Empty means no real "
                    "payments have been recorded for this loan yet -- it may still be "
                    "on Portfolio's own SIMULATED delinquency estimate.",
        },
        "collection_activity": {
            "entries": [],
            "note": "Real Call/Text/Email contact log entries live on Collections' own "
                    "Agent Workspace (core/collections.py's get_contact_history()) -- "
                    "fetch that directly for this loan's real contact history rather "
                    "than duplicating it here.",
        },
        "repossession_events": {
            "entries": repossession_entries,
            "note": "Real repossession case stage transitions (core/repossessions.py). "
                    "Empty means this loan has never had a repossession case.",
        },
    }


def get_loan_detail(loan_id):
    """The full composed loan record -- Borrower / Vehicle / Contract / Timeline, per
    Sam's own spec for the Loan Management screen."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    customer_id = _linked_customer_id(loan)
    vehicle_id = _linked_vehicle_id(loan)
    lender_id = _linked_lender_id(loan)

    financials = get_loan_financials(loan_id)
    payment_status = get_simulated_payment_status(loan_id)
    timeline = get_loan_timeline(loan_id)

    return {
        "loan_id": loan_id,
        "finance_number": loan.attributes.get("FinanceNumber"),
        "loan_status": get_loan_status(loan_id),
        "borrower": {
            "customer": _customer_brief(customer_id),
            "employment": _borrower_employment(customer_id),
            "references": {
                "on_file": False,
                "note": "No personal-reference data model exists anywhere in this codebase "
                        "yet -- an honest gap, not simulated.",
            },
        },
        "vehicle": {
            "vehicle": _vehicle_brief(vehicle_id),
            "collateral_status": get_loan_status(loan_id),
        },
        "lender": _lender_brief(lender_id),
        "contract": financials,
        "payment_status": payment_status,
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Portfolio Dashboard
# ---------------------------------------------------------------------------

def _loan_brief(loan):
    customer_id = _linked_customer_id(loan)
    vehicle_id = _linked_vehicle_id(loan)
    status = get_simulated_payment_status(loan.id)
    return {
        "id": loan.id,
        "finance_number": loan.attributes.get("FinanceNumber"),
        "customer": _customer_brief(customer_id),
        "vehicle": _vehicle_brief(vehicle_id),
        "amount_financed": _safe_float(loan.attributes.get("AmountFinanced")),
        "monthly_payment": _safe_float(loan.attributes.get("MonthlyPayment")),
        "apr": _safe_float(loan.attributes.get("APR")),
        "loan_status": get_loan_status(loan.id),
        "bucket": status.get("bucket") if isinstance(status, dict) else None,
        "days_past_due": status.get("days_past_due") if isinstance(status, dict) else None,
    }


def get_portfolio_dashboard(bucket=None, limit=100):
    """Sam's own headline Portfolio Dashboard buckets: Active Loans, Current, 30/60/90
    Day Delinquencies, Charge-Offs, Repossessions, Payoffs. Active/Current/etc. are
    real counts over real loan_status; the delinquency-severity split
    (current/30/60/90/repossessed/charged_off) is the SIMULATED payment-status layer
    -- see module docstring."""

    loans = _all_loans()

    all_rows = [(loan, get_simulated_payment_status(loan.id)) for loan in loans]

    counts = {b: 0 for b in DELINQUENCY_BUCKETS}
    total_past_due = 0.0
    for _loan, status in all_rows:
        if isinstance(status, dict):
            b = status.get("bucket", "current")
            counts[b] = counts.get(b, 0) + 1
            total_past_due += status.get("amount_past_due") or 0.0

    rows = all_rows
    if bucket:
        rows = [(l, s) for (l, s) in all_rows if isinstance(s, dict) and s.get("bucket") == bucket]

    payoffs = [l for l in loans if get_loan_status(l.id) == "paid_off"]
    active = [l for l in loans if get_loan_status(l.id) == "active"]

    total_outstanding = sum(get_loan_financials(l.id).get("current_balance") or 0.0 for l in active)

    return {
        "total_loans": len(loans),
        "active_loans": len(active),
        "payoffs": len(payoffs),
        "delinquency_buckets": counts,
        "total_amount_past_due": round(total_past_due, 2),
        "total_outstanding_balance": round(total_outstanding, 2),
        "basis": SIMULATED_BASIS,
        "disclaimer": _DISCLAIMER_PAYMENT_STATUS,
        "loans": [_loan_brief(l) for (l, _s) in rows[:limit]],
        "loans_count": len(rows),
    }
