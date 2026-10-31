"""
core/bank_reconciliation.py -- Bank Reconciliation (2026-07-17, session 112
follow-up). Same instruction as core/general_ledger.py's module docstring: Sam's
direct "lets keep going, simply create the fake data that is needed to build them."

No real bank account/transaction feed exists anywhere in this codebase (no Plaid/
bank-API integration). SIMULATED_BANK_ACCOUNT is a fixed, clearly-fake account
(named "(Simulated)" in its own bank name so it can never be mistaken for a real
credential or read as real financial data at a glance). generate_simulated_bank_feed()
creates BankTransaction rows deterministically off real GlEntry cash postings
(core/general_ledger.py) -- most bank deposits mirror a real/simulated GL cash entry
with a small, realistic 0-2 business day clearing delay (a real bank doesn't post the
instant a payment is taken), plus a handful of bank-only items (a monthly service fee,
occasional interest earned) that exist ONLY on the simulated bank side, exactly the
kind of item a real reconciliation exists to catch.

get_reconciliation_status() is the one genuinely real piece of computation in this
module: a real matching algorithm (amount + date-proximity) pairing bank transactions
against GL cash entries, distinct unmatched-on-each-side lists, and a real book-vs-
bank balance comparison. The matching LOGIC is real; only the transaction DATA it
operates on is simulated.
"""

import hashlib
from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import BANK_TRANSACTION, GL_ENTRY
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.loan_servicing import _safe_float


SIMULATED_BANK_ACCOUNT = {
    "name": "NXTDeal Operating Account (Simulated)",
    "bank": "First Dealer Bank (Simulated -- no real bank connection exists)",
    "account_last4": "4821",
    "starting_balance": 50000.0,
}

SIMULATED_BASIS = "simulated_bank_transaction"
_DISCLAIMER = (
    "SIMULATED bank transaction -- no real bank account/transaction feed (e.g. "
    "Plaid) is connected in this system. Deposits are deterministically generated "
    "from real/simulated GL cash entries with a realistic clearing delay; fee/"
    "interest items exist only on the simulated bank side, same as a real bank "
    "statement would carry items your books don't yet reflect."
)

STATUSES = ("unmatched", "matched", "reviewed")
_MATCH_AMOUNT_TOLERANCE = 0.01
_MATCH_DATE_WINDOW_DAYS = 4


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


def _seeded_int(seed_str, low, high):
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest, 16) % span)


def _all_transactions():
    return [e for e in ledger.get_all().values() if e.entity_type == BANK_TRANSACTION]


def _all_gl_entries():
    return [e for e in ledger.get_all().values() if e.entity_type == GL_ENTRY]


def _cash_amount(entry):
    """Net cash movement for one GlEntry's Cash (1000) line -- positive for a debit
    (money in), negative for a credit (money out)."""

    net = 0.0
    for line in entry.attributes.get("lines", []):
        if line.get("account") != "1000":
            continue
        net += _safe_float(line.get("debit")) - _safe_float(line.get("credit"))
    return round(net, 2)


def _existing_bank_source_refs():
    return {t.attributes.get("source_reference") for t in _all_transactions() if t.attributes.get("source_reference")}


def generate_simulated_bank_feed(generated_by, start_date=None, end_date=None):
    """Generates one simulated deposit/withdrawal per real/simulated GL cash entry
    within range (idempotent by source_reference), plus a handful of bank-only items
    -- a monthly service fee and occasional interest earned, deterministically seeded
    per month so they don't duplicate on re-run."""
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("financial_simulation")
    if blocked:
        return blocked


    start = _parse_date(start_date)
    end = _parse_date(end_date)

    existing = _existing_bank_source_refs()
    created = []

    cash_entries = [e for e in _all_gl_entries() if _cash_amount(e) != 0]

    for entry in cash_entries:

        entry_date = _parse_date(entry.attributes.get("entry_date"))
        if not entry_date:
            continue
        if start and entry_date < start:
            continue
        if end and entry_date > end:
            continue

        source_reference = f"gl:{entry.id}"
        if source_reference in existing:
            continue

        delay_days = _seeded_int(f"{entry.id}|clearing_delay", 0, 2)
        posted_date = entry_date + timedelta(days=delay_days)

        amount = _cash_amount(entry)

        txn = Entity(
            id=id_generator.generate("BTXN"),
            entity_type=BANK_TRANSACTION,
            attributes={
                "posted_date": posted_date.isoformat(),
                "amount": amount,
                "type": "deposit" if amount >= 0 else "withdrawal",
                "description": entry.attributes.get("description", "Bank transaction"),
                "source_reference": source_reference,
                "matched_gl_entry_id": None,
                "status": "unmatched",
                "created_by": generated_by,
                "created_at": _now(),
                "basis": SIMULATED_BASIS,
                "disclaimer": _DISCLAIMER,
            },
        )
        ledger.add_entity(txn)
        created.append(txn.id)

    # Bank-only items -- a monthly service fee + occasional interest earned, one per
    # real calendar month present among the GL entries just processed (or the
    # requested range), deterministically seeded so re-running doesn't duplicate.
    months = sorted({_parse_date(e.attributes.get("entry_date")).strftime("%Y-%m") for e in cash_entries if _parse_date(e.attributes.get("entry_date"))})

    for month_key in months:

        fee_ref = f"bank_fee:{month_key}"
        if fee_ref not in existing:
            fee_amount = -round(15 + _seeded_int(f"{month_key}|fee", 0, 20), 2)
            year, month = (int(x) for x in month_key.split("-"))
            fee_date = date(year, month, min(28, 28))
            txn = Entity(
                id=id_generator.generate("BTXN"),
                entity_type=BANK_TRANSACTION,
                attributes={
                    "posted_date": fee_date.isoformat(),
                    "amount": fee_amount,
                    "type": "withdrawal",
                    "description": f"Monthly service fee, {month_key} (SIMULATED, bank-only item)",
                    "source_reference": fee_ref,
                    "matched_gl_entry_id": None,
                    "status": "unmatched",
                    "created_by": generated_by,
                    "created_at": _now(),
                    "basis": SIMULATED_BASIS,
                    "disclaimer": _DISCLAIMER,
                },
            )
            ledger.add_entity(txn)
            created.append(txn.id)

        interest_ref = f"bank_interest:{month_key}"
        if interest_ref not in existing and _seeded_int(f"{month_key}|has_interest", 0, 1) == 1:
            interest_amount = round(5 + _seeded_int(f"{month_key}|interest", 0, 40), 2)
            year, month = (int(x) for x in month_key.split("-"))
            interest_date = date(year, month, min(28, 28))
            txn = Entity(
                id=id_generator.generate("BTXN"),
                entity_type=BANK_TRANSACTION,
                attributes={
                    "posted_date": interest_date.isoformat(),
                    "amount": interest_amount,
                    "type": "deposit",
                    "description": f"Interest earned, {month_key} (SIMULATED, bank-only item)",
                    "source_reference": interest_ref,
                    "matched_gl_entry_id": None,
                    "status": "unmatched",
                    "created_by": generated_by,
                    "created_at": _now(),
                    "basis": SIMULATED_BASIS,
                    "disclaimer": _DISCLAIMER,
                },
            )
            ledger.add_entity(txn)
            created.append(txn.id)

    if created:
        save_graph(GRAPH_PATH)

    return {"generated_count": len(created), "generated_transaction_ids": created}


def _auto_match(transactions, gl_entries):
    """Real matching algorithm: exact amount match within a real date-proximity
    window, closest date wins on a tie. Bank-only items (fees/interest, no
    corresponding GlEntry) are correctly never matched."""

    unmatched_gl = list(gl_entries)
    matches = []

    for txn in transactions:

        if txn.attributes.get("matched_gl_entry_id"):
            continue

        txn_date = _parse_date(txn.attributes.get("posted_date"))
        txn_amount = _safe_float(txn.attributes.get("amount"))

        candidates = []
        for entry in unmatched_gl:
            entry_date = _parse_date(entry.attributes.get("entry_date"))
            if not entry_date or not txn_date:
                continue
            if abs(_cash_amount(entry) - txn_amount) > _MATCH_AMOUNT_TOLERANCE:
                continue
            days_apart = abs((txn_date - entry_date).days)
            if days_apart > _MATCH_DATE_WINDOW_DAYS:
                continue
            candidates.append((days_apart, entry))

        if candidates:
            candidates.sort(key=lambda c: c[0])
            _days, best = candidates[0]
            matches.append((txn, best))
            unmatched_gl.remove(best)

    return matches


def get_reconciliation_status(start_date=None, end_date=None):

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    def _in_range(d):
        if not d:
            return True
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    transactions = [t for t in _all_transactions() if _in_range(_parse_date(t.attributes.get("posted_date")))]
    cash_entries = [e for e in _all_gl_entries() if _cash_amount(e) != 0 and _in_range(_parse_date(e.attributes.get("entry_date")))]

    already_matched_gl_ids = {t.attributes.get("matched_gl_entry_id") for t in transactions if t.attributes.get("matched_gl_entry_id")}
    unmatched_gl_entries = [e for e in cash_entries if e.id not in already_matched_gl_ids]
    unmatched_transactions = [t for t in transactions if not t.attributes.get("matched_gl_entry_id")]

    auto_matches = _auto_match(unmatched_transactions, unmatched_gl_entries)
    auto_matched_txn_ids = {t.id for t, _e in auto_matches}
    auto_matched_gl_ids = {e.id for _t, e in auto_matches}

    still_unmatched_transactions = [t for t in unmatched_transactions if t.id not in auto_matched_txn_ids]
    still_unmatched_gl_entries = [e for e in unmatched_gl_entries if e.id not in auto_matched_gl_ids]

    book_balance = round(SIMULATED_BANK_ACCOUNT["starting_balance"] + sum(_cash_amount(e) for e in _all_gl_entries()), 2)
    bank_balance = round(SIMULATED_BANK_ACCOUNT["starting_balance"] + sum(_safe_float(t.attributes.get("amount")) for t in _all_transactions()), 2)

    return {
        "bank_account": SIMULATED_BANK_ACCOUNT,
        "book_balance": book_balance,
        "bank_balance": bank_balance,
        "difference": round(book_balance - bank_balance, 2),
        "auto_matched_count": len(auto_matches),
        "auto_matches": [{"transaction_id": t.id, "gl_entry_id": e.id, "amount": _safe_float(t.attributes.get("amount"))} for t, e in auto_matches],
        "unmatched_transactions": [
            {"id": t.id, **t.attributes} for t in still_unmatched_transactions
        ],
        "unmatched_gl_entries": [
            {"id": e.id, "entry_date": e.attributes.get("entry_date"), "description": e.attributes.get("description"), "amount": _cash_amount(e)}
            for e in still_unmatched_gl_entries
        ],
        "already_reconciled_count": len([t for t in transactions if t.attributes.get("status") == "reviewed"]),
    }


def confirm_match(transaction_id, gl_entry_id, confirmed_by):

    from core.workflow_readiness import simulation_block
    blocked = simulation_block("bank_reconciliation")
    if blocked:
        return blocked

    txn = ledger.get_entity(transaction_id)
    entry = ledger.get_entity(gl_entry_id)

    if not txn or txn.entity_type != BANK_TRANSACTION:
        return {"error": f"Bank transaction '{transaction_id}' not found"}

    if not entry or entry.entity_type != GL_ENTRY:
        return {"error": f"GL entry '{gl_entry_id}' not found"}

    if txn.attributes.get("matched_gl_entry_id"):
        return {"error": f"Transaction '{transaction_id}' is already matched."}

    if abs(_cash_amount(entry) - _safe_float(txn.attributes.get("amount"))) > _MATCH_AMOUNT_TOLERANCE:
        return {"error": f"Amounts don't match: transaction is {txn.attributes.get('amount')}, GL entry cash movement is {_cash_amount(entry)}."}

    txn.attributes["matched_gl_entry_id"] = gl_entry_id
    txn.attributes["status"] = "matched"
    txn.attributes["matched_by"] = confirmed_by
    txn.attributes["matched_at"] = _now()

    save_graph(GRAPH_PATH)

    return {"id": txn.id, **txn.attributes}


def mark_transaction_reviewed(transaction_id, reviewed_by, note=""):

    from core.workflow_readiness import simulation_block
    blocked = simulation_block("bank_reconciliation")
    if blocked:
        return blocked

    txn = ledger.get_entity(transaction_id)

    if not txn or txn.entity_type != BANK_TRANSACTION:
        return {"error": f"Bank transaction '{transaction_id}' not found"}

    txn.attributes["status"] = "reviewed"
    txn.attributes["reviewed_by"] = reviewed_by
    txn.attributes["reviewed_at"] = _now()
    txn.attributes["review_note"] = note

    save_graph(GRAPH_PATH)

    return {"id": txn.id, **txn.attributes}


def list_transactions(status=None, start_date=None, end_date=None):

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    transactions = _all_transactions()

    if status:
        transactions = [t for t in transactions if t.attributes.get("status") == status]

    def _in_range(t):
        d = _parse_date(t.attributes.get("posted_date"))
        if not d:
            return True
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    transactions = [t for t in transactions if _in_range(t)]
    transactions.sort(key=lambda t: t.attributes.get("posted_date") or "")

    return [{"id": t.id, **t.attributes} for t in transactions]
