"""
core/loan_accounting.py -- Loan Accounting (2026-07-17, session 112 follow-up), the
eighth slice of Sam's "Retail Automotive Lending Platform" expansion, closing the
"loan accounting" item from the "broader Compliance/Accounting/Commissions/Reporting
extensions" line in Sam's original message. finance_menu.py's accounting() has
carried an honest not_yet_tracked note for deal_posting_queue/posted_today/
unposted_deals/general_ledger/bank_reconciliation/schedule_audits/month_end_close
since session 64 -- this module closes the pieces that are genuinely computable from
data this codebase already has for real, and leaves the rest honestly flagged.

A real cash-basis sub-ledger, built entirely from core/payments.py's own real Payment
records (each approved Payment already carries a real principal_portion/
interest_portion split, computed at record_payment() time). No new payment data is
invented here -- this module just aggregates and posts what already exists.

Scope, decided deliberately rather than guessed at:
- Loan accounting summary (Interest Income Recognized / Principal Reduction / Cash
  Collected) -- REAL, 100% derived from approved Payment records.
- A daily ledger (one simple double-entry row per approved payment: Debit Cash,
  Credit Interest Income, Credit Loan Principal Receivable) with a real posting
  workflow -- this is the loan-specific, honest analog to Sam's
  deal_posting_queue/posted_today/unposted_deals ask, reframed around what this
  codebase actually models (loan payments, not vehicle-sale deal postings -- Deal
  itself has no accounting-posting concept and still doesn't after this module).
- Month-end close -- a real AccountingPeriod entity locking a calendar month once
  every payment in it has been posted; closing with unposted payments still in the
  period is rejected (a standard, real accounting control), and posting to an already
  -closed period is rejected too.

Deliberately NOT simulated, despite session 110's standing "simulate when blocked"
policy: General Ledger (a full dealership-wide chart of accounts covering every
transaction type, not just loans) and Bank Reconciliation (matching real bank
transactions against posted entries) both require a real bank-account/transaction
feed and a real chart of accounts that don't exist anywhere in this codebase --
fabricating either would misrepresent this dealership's actual cash position, the
same reasoning core/lending_compliance.py's own module docstring already applied to
OFAC/Form 8300 (a legal/financial-accuracy surface, not a market/business-data one).
Both stay honestly not_yet_tracked. Schedule Audits is also left untouched this pass
-- closely related to core/collections.py's own real delinquency signal (days past
due derived from real cumulative payments vs. the contractual schedule); building a
second, narrower "payment misallocation" audit on top was judged out of scope for
this slice rather than force-fit in to check a box.
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import ACCOUNTING_PERIOD, PAYMENT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.payments import _all_payments, list_payments_for_loan
from core.loan_servicing import _safe_float
from core.audit import audit_log


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return date.today()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _period_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def _approved_payments(start_date=None, end_date=None):

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    payments = [p for p in _all_payments() if p.attributes.get("status") == "approved"]

    if start or end:
        filtered = []
        for p in payments:
            pd = _parse_date(p.attributes.get("payment_date"))
            if not pd:
                continue
            if start and pd < start:
                continue
            if end and pd > end:
                continue
            filtered.append(p)
        payments = filtered

    payments.sort(key=lambda p: (p.attributes.get("payment_date") or "", p.id))

    return payments


# ---------------------------------------------------------------------------
# Accounting periods (month-end close)
# ---------------------------------------------------------------------------

def _all_periods():
    return [e for e in ledger.get_all().values() if e.entity_type == ACCOUNTING_PERIOD]


def get_period(period_key):
    for period in _all_periods():
        if period.attributes.get("period_key") == period_key:
            return period
    return None


def is_period_closed(payment_date):

    parsed = _parse_date(payment_date)
    if not parsed:
        return False

    period = get_period(_period_key(parsed))

    return bool(period and period.attributes.get("status") == "closed")


def list_periods():
    periods = _all_periods()
    periods.sort(key=lambda p: p.attributes.get("period_key", ""), reverse=True)
    return periods


def close_accounting_period(year, month, closed_by):

    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        return {"error": "year and month must be integers"}

    if not (1 <= month <= 12):
        return {"error": "month must be between 1 and 12"}

    period_key = f"{year:04d}-{month:02d}"

    existing = get_period(period_key)
    if existing and existing.attributes.get("status") == "closed":
        return {"error": f"Period '{period_key}' is already closed."}

    unposted = [
        p for p in _approved_payments()
        if _period_key(_parse_date(p.attributes.get("payment_date"))) == period_key
        and p.attributes.get("posting_status") != "posted"
    ]

    if unposted:
        return {
            "error": f"Cannot close '{period_key}' -- {len(unposted)} approved payment(s) in this period are still unposted.",
            "unposted_payment_ids": [p.id for p in unposted],
        }

    if existing:
        existing.attributes["status"] = "closed"
        existing.attributes["closed_by"] = closed_by
        existing.attributes["closed_at"] = _now()
        period = existing
    else:
        period = Entity(
            id=id_generator.generate("ACCT"),
            entity_type=ACCOUNTING_PERIOD,
            attributes={
                "period_key": period_key,
                "status": "closed",
                "closed_by": closed_by,
                "closed_at": _now(),
                "created_at": _now(),
            },
        )
        ledger.add_entity(period)

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="accounting_period_closed",
        summary=f"Accounting period {period_key} closed by {closed_by}",
        entity_id=period.id,
        actor=closed_by,
        details={"period_key": period_key},
    )

    return {"period_key": period_key, "status": "closed", "closed_by": closed_by, "closed_at": period.attributes["closed_at"]}


def reopen_accounting_period(year, month, reopened_by):
    """A deliberate, audited escape hatch -- closing is a real control, but a genuine
    correction (a misposted payment discovered after close) needs a real way back
    rather than being permanently locked out."""

    period_key = f"{int(year):04d}-{int(month):02d}"
    period = get_period(period_key)

    if not period or period.attributes.get("status") != "closed":
        return {"error": f"Period '{period_key}' is not currently closed."}

    period.attributes["status"] = "open"
    period.attributes["reopened_by"] = reopened_by
    period.attributes["reopened_at"] = _now()

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="accounting_period_reopened",
        summary=f"Accounting period {period_key} reopened by {reopened_by}",
        entity_id=period.id,
        actor=reopened_by,
        details={"period_key": period_key},
    )

    return {"period_key": period_key, "status": "open"}


# ---------------------------------------------------------------------------
# Summary + daily ledger
# ---------------------------------------------------------------------------

def get_loan_accounting_summary(start_date=None, end_date=None):

    payments = _approved_payments(start_date, end_date)

    interest_income = round(sum(_safe_float(p.attributes.get("interest_portion")) for p in payments), 2)
    principal_reduction = round(sum(_safe_float(p.attributes.get("principal_portion")) for p in payments), 2)
    cash_collected = round(sum(_safe_float(p.attributes.get("amount")) for p in payments), 2)
    posted = [p for p in payments if p.attributes.get("posting_status") == "posted"]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "payment_count": len(payments),
        "interest_income_recognized": interest_income,
        "principal_reduction": principal_reduction,
        "cash_collected": cash_collected,
        "posted_count": len(posted),
        "unposted_count": len(payments) - len(posted),
        "note": "Real, computed entirely from approved Payment records (core/payments.py) -- cash-basis, not accrual.",
    }


def _ledger_entry(payment):
    return {
        "payment_id": payment.id,
        "loan_id": payment.attributes.get("loan_id"),
        "payment_date": payment.attributes.get("payment_date"),
        "method": payment.attributes.get("method"),
        "posting_status": payment.attributes.get("posting_status", "unposted"),
        "lines": [
            {"account": "Cash", "debit": payment.attributes.get("amount"), "credit": 0},
            {"account": "Interest Income", "debit": 0, "credit": payment.attributes.get("interest_portion")},
            {"account": "Loan Principal Receivable", "debit": 0, "credit": payment.attributes.get("principal_portion")},
        ],
    }


def get_daily_ledger(payment_date):

    parsed = _parse_date(payment_date)
    if not parsed:
        return {"error": "payment_date must be an ISO date (YYYY-MM-DD)"}

    payments = [p for p in _approved_payments() if p.attributes.get("payment_date") == payment_date]

    return {
        "date": payment_date,
        "period_closed": is_period_closed(payment_date),
        "entries": [_ledger_entry(p) for p in payments],
        "totals": {
            "cash": round(sum(_safe_float(p.attributes.get("amount")) for p in payments), 2),
            "interest_income": round(sum(_safe_float(p.attributes.get("interest_portion")) for p in payments), 2),
            "principal_reduction": round(sum(_safe_float(p.attributes.get("principal_portion")) for p in payments), 2),
        },
    }


def get_unposted_payments():

    unposted = [p for p in _approved_payments() if p.attributes.get("posting_status") != "posted"]
    unposted.sort(key=lambda p: p.attributes.get("payment_date") or "")

    return [_ledger_entry(p) for p in unposted]


def _simulation_posting_block(payment):
    from core.workflow_readiness import simulation_block
    attrs = payment.attributes
    if attrs.get("basis") == "simulated_payment_gateway" and (
        attrs.get("method") != "cash" or attrs.get("recorded_by") == "customer_via_payment_portal"
        or str(attrs.get("recorded_by", "")).startswith("auto_draft:")
    ):
        return simulation_block("electronic_payments")
    return None


def post_payment_to_ledger(payment_id, posted_by):

    payment = ledger.get_entity(payment_id)

    if not payment or payment.entity_type != PAYMENT:
        return {"error": f"Payment '{payment_id}' not found"}

    blocked = _simulation_posting_block(payment)
    if blocked:
        return blocked

    if payment.attributes.get("status") != "approved":
        return {"error": f"Payment '{payment_id}' is '{payment.attributes.get('status')}', not approved -- only approved payments can be posted."}

    if payment.attributes.get("posting_status") == "posted":
        return {"error": f"Payment '{payment_id}' is already posted."}

    if is_period_closed(payment.attributes.get("payment_date")):
        return {"error": f"The accounting period for {payment.attributes.get('payment_date')} is closed -- reopen it before posting."}

    payment.attributes["posting_status"] = "posted"
    payment.attributes["posted_by"] = posted_by
    payment.attributes["posted_at"] = _now()

    save_graph(GRAPH_PATH)

    return _ledger_entry(payment)


def post_all_due(payment_date, posted_by):
    """Bulk-post every unposted, approved payment for one day -- the real "close out
    today's cash" action a controller actually performs, rather than clicking Post on
    each payment individually."""

    parsed = _parse_date(payment_date)
    if not parsed:
        return {"error": "payment_date must be an ISO date (YYYY-MM-DD)"}

    if is_period_closed(payment_date):
        return {"error": f"The accounting period for {payment_date} is closed."}

    payments = [
        p for p in _approved_payments()
        if p.attributes.get("payment_date") == payment_date and p.attributes.get("posting_status") != "posted"
    ]

    for payment in payments:
        blocked = _simulation_posting_block(payment)
        if blocked:
            return {**blocked, "payment_id": payment.id}

    posted_ids = []

    for payment in payments:
        payment.attributes["posting_status"] = "posted"
        payment.attributes["posted_by"] = posted_by
        payment.attributes["posted_at"] = _now()
        posted_ids.append(payment.id)

    if posted_ids:
        save_graph(GRAPH_PATH)

    return {"date": payment_date, "posted_count": len(posted_ids), "posted_payment_ids": posted_ids}
