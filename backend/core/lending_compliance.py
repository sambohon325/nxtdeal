"""
core/lending_compliance.py -- OFAC/SDN Screening + IRS Form 8300 Cash Reporting
(2026-07-17, session 112 follow-up), closing the exact two gaps
core/finance_menu.py's compliance() has flagged by name since session 64: "OFAC
Verification and IRS Form 8300 have NO backing rule or data model in this codebase --
confirmed absent from core/compliance_rules.py's 7-rule catalog, a genuine gap, not
omitted by oversight." This is the seventh slice of Sam's "Retail Automotive Lending
Platform" expansion, and the first to extend core/compliance_rules.py's catalog itself
rather than building a standalone module.

Same scoping reality core/compliance_rules.py's own module docstring already commits
to: there is no live OFAC SDN-list connection and no live IRS e-filing integration in
this sandbox. Rather than fabricate either (this is a LEGAL compliance surface, not a
market/business-data one -- the standing "simulate when blocked" policy from session
110 was scoped to business data like market pricing/GPS telemetry, not to legal
screening outcomes), both features follow this module's own established pattern: a
SMALL, REAL, CHECKABLE precondition captured by an actual human action, same shape as
_check_red_flags_identity's "identity fields must be on file" proxy.

OFAC / SDN Screening -- Bank Secrecy Act / Executive Order 13224, enforced via
Treasury's Office of Foreign Assets Control. A creditor may not transact with a person
or entity on OFAC's Specially Designated Nationals list. NXTDeal can't check a live
SDN feed, but it CAN require -- and now, for the first time, actually let someone
record -- that a real screening was performed and cleared before a deal funds. Additive
`Deal.attributes["ofac_screening"]`:
    {screened: bool, cleared: bool, screened_by, screened_at, notes}
Wired into core/compliance_rules.py's RULE_CATALOG as a real, blocking `deal_fund` rule
(matching _check_red_flags_identity's precedent exactly) -- a deal cannot fund without
an on-file screening that came back cleared.

IRS Form 8300 -- 26 U.S.C. 6050I / 31 U.S.C. 5331, a dealer receiving more than $10,000
in cash in one transaction (or two or more related transactions) must file Form 8300
with the IRS within 15 days of receipt. NXTDeal has no payment-method field on Deal at
all today, so record_cash_payment() is the first thing to capture one -- an additive
`Deal.attributes["cash_payments"]` list, `{amount, payment_date, recorded_by,
recorded_at}`. Deliberately NOT wired into enforce_gate()'s deal_fund block the way OFAC
is: the real-world obligation is to FILE within 15 days of RECEIPT, not to file before
completing the sale, so gating funding on it would misrepresent the actual legal
timing. Instead this module computes a real, honestly-labeled obligation status
(none / pending / overdue / filed) off the real elapsed days since the first
qualifying cash payment, surfaced as a tracked queue rather than a block -- the same
"track and surface, don't fabricate a false gate" instinct this codebase applies
whenever a real signal exists but blocking on it wouldn't match reality.

Honest scope limit, stated plainly rather than silently ignored: the IRS "two or more
related transactions" aggregation rule (cash received across MULTIPLE deals from the
same buyer within a 12-month period can also trigger the $10,000 threshold) is NOT
modeled here -- this module aggregates cash payments PER DEAL only. Detecting related
transactions across deals would need a much more sophisticated buyer-identity linkage
this sandbox doesn't have a reliable way to build honestly; flagged rather than
guessed at.
"""

from datetime import datetime, timezone, date

from core.deals import get_deal, list_deals
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


CASH_REPORTING_THRESHOLD = 10000.0
FILING_WINDOW_DAYS = 15


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


# ---------------------------------------------------------------------------
# OFAC / SDN Screening
# ---------------------------------------------------------------------------

def get_ofac_screening_status(deal_id):
    """Computed-default-then-real-value, same convention as loan_status/ro_stage/
    lifecycle_status elsewhere in this codebase -- a deal with no screening on file
    reads as an honest "not_screened", not silently treated as cleared."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": f"Deal '{deal_id}' not found"}

    screening = (deal.attributes or {}).get("ofac_screening")

    if not screening:
        return {
            "deal_id": deal_id,
            "status": "not_screened",
            "cleared": False,
            "screened_by": None,
            "screened_at": None,
            "notes": None,
        }

    return {
        "deal_id": deal_id,
        "status": "cleared" if screening.get("cleared") else "potential_match",
        "cleared": bool(screening.get("cleared")),
        "screened_by": screening.get("screened_by"),
        "screened_at": screening.get("screened_at"),
        "notes": screening.get("notes"),
    }


def record_ofac_screening(deal_id, cleared, screened_by, notes=""):
    """The real capture action -- nothing in this codebase could previously record an
    OFAC screening result at all. `cleared=False` is a real, legitimate outcome (a
    potential match was found and the deal should NOT proceed) -- this function
    doesn't reject that, it just records it honestly, and the compliance rule below
    will correctly keep blocking deal_fund until a screening with `cleared=True`
    replaces it."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": f"Deal '{deal_id}' not found"}

    if deal.attributes.get("status") == "funded":
        return {"error": "This deal has already funded -- OFAC screening applies before funding, not after."}

    deal.attributes["ofac_screening"] = {
        "screened": True,
        "cleared": bool(cleared),
        "screened_by": screened_by,
        "screened_at": _now(),
        "notes": notes or "",
    }
    deal.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return get_ofac_screening_status(deal_id)


# ---------------------------------------------------------------------------
# IRS Form 8300 -- cash-payment tracking + filing
# ---------------------------------------------------------------------------

def record_cash_payment(deal_id, amount, payment_date, recorded_by):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": f"Deal '{deal_id}' not found"}

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be a number"}

    if amount <= 0:
        return {"error": "amount must be positive"}

    payment_date = payment_date or _today().isoformat()

    if not _parse_date(payment_date):
        return {"error": "payment_date must be an ISO date (YYYY-MM-DD)"}

    payments = deal.attributes.setdefault("cash_payments", [])
    payments.append({
        "amount": round(amount, 2),
        "payment_date": payment_date,
        "recorded_by": recorded_by,
        "recorded_at": _now(),
    })
    deal.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return get_form_8300_status(deal_id)


def _total_cash(deal):
    return round(sum(float(p.get("amount") or 0) for p in (deal.attributes or {}).get("cash_payments") or []), 2)


def _first_qualifying_payment_date(deal, threshold_total):
    """The date the running cash total for this deal first crossed the reporting
    threshold -- the real IRS-meaningful clock-start, not just the first payment's own
    date (a deal could take several smaller cash payments before crossing $10,000)."""

    running = 0.0

    for payment in sorted((deal.attributes or {}).get("cash_payments") or [], key=lambda p: p.get("payment_date", "")):

        running += float(payment.get("amount") or 0)

        if running >= threshold_total:
            return payment.get("payment_date")

    return None


def get_form_8300_status(deal_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": f"Deal '{deal_id}' not found"}

    total_cash = _total_cash(deal)
    filing = (deal.attributes or {}).get("form_8300")
    obligation = total_cash >= CASH_REPORTING_THRESHOLD

    result = {
        "deal_id": deal_id,
        "total_cash_received": total_cash,
        "threshold": CASH_REPORTING_THRESHOLD,
        "obligation": obligation,
        "filed": bool(filing),
        "filing": filing,
    }

    if not obligation:
        result["status"] = "none"
        result["note"] = "Total recorded cash on this deal is below the $10,000 reporting threshold."
        return result

    if filing:
        result["status"] = "filed"
        return result

    trigger_date = _parse_date(_first_qualifying_payment_date(deal, CASH_REPORTING_THRESHOLD))

    if not trigger_date:
        result["status"] = "pending"
        result["days_remaining"] = FILING_WINDOW_DAYS
        return result

    days_elapsed = (_today() - trigger_date).days
    days_remaining = FILING_WINDOW_DAYS - days_elapsed

    result["trigger_date"] = trigger_date.isoformat()
    result["days_elapsed"] = days_elapsed

    if days_remaining < 0:
        result["status"] = "overdue"
        result["days_overdue"] = -days_remaining
    else:
        result["status"] = "pending"
        result["days_remaining"] = days_remaining

    return result


def file_form_8300(deal_id, filed_by, filing_date=None):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": f"Deal '{deal_id}' not found"}

    if deal.attributes.get("form_8300"):
        return {"error": "A Form 8300 filing is already on record for this deal."}

    total_cash = _total_cash(deal)

    if total_cash < CASH_REPORTING_THRESHOLD:
        return {"error": f"Total recorded cash (${total_cash:,.2f}) is below the ${CASH_REPORTING_THRESHOLD:,.2f} reporting threshold -- no filing is required."}

    deal.attributes["form_8300"] = {
        "filed": True,
        "filed_by": filed_by,
        "filed_at": _now(),
        "filing_date": filing_date or _today().isoformat(),
        "amount": total_cash,
    }
    deal.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return get_form_8300_status(deal_id)


def get_form_8300_obligations(status=None):
    """Every deal with real recorded cash payments -- the real, honest queue a
    compliance officer actually works from, filtered by computed obligation status
    (pending / overdue / filed) when requested."""

    obligations = []

    for deal in list_deals():

        if not (deal.attributes or {}).get("cash_payments"):
            continue

        result = get_form_8300_status(deal.id)

        if result.get("status") == "none":
            continue

        if status and result.get("status") != status:
            continue

        obligations.append(result)

    obligations.sort(key=lambda r: r.get("days_overdue", 0) if r.get("status") == "overdue" else -1, reverse=True)

    return obligations


def get_lending_compliance_dashboard():

    ofac_pending = []

    for deal in list_deals():

        if deal.attributes.get("status") == "funded":
            continue

        screening = get_ofac_screening_status(deal.id)

        if screening.get("status") != "cleared":
            ofac_pending.append(screening)

    obligations = get_form_8300_obligations()
    overdue = [o for o in obligations if o["status"] == "overdue"]
    pending = [o for o in obligations if o["status"] == "pending"]
    filed = [o for o in obligations if o["status"] == "filed"]

    return {
        "ofac": {
            "unscreened_or_potential_match_count": len(ofac_pending),
            "deals": ofac_pending[:50],
        },
        "form_8300": {
            "overdue_count": len(overdue),
            "pending_count": len(pending),
            "filed_count": len(filed),
            "overdue": overdue,
            "pending": pending,
        },
        "note": (
            "OFAC screening is a real, checkable precondition (screened + cleared "
            "on file) -- this sandbox has no live SDN-list connection, so a "
            "screening result is human-recorded, not automatically verified. Form "
            "8300 obligations are computed per-deal only; the IRS 'related "
            "transactions across multiple deals' aggregation rule is not modeled. "
            "Neither feature is legal advice -- see compliance/rules for the full "
            "notice."
        ),
    }
