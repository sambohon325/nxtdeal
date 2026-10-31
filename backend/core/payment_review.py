"""Read-only triage of receipt provenance; never a balance correction or bank reconciliation."""
from collections import Counter
from decimal import Decimal, InvalidOperation

from core.entity_types import PAYMENT, FINANCE_CONTRACT
from core.permissions import ADMIN, OPERATIONS, FINANCE


def _amount(value):
    try:
        number = Decimal(str(value))
        if (not number.is_finite() or number <= 0 or number.adjusted() > 12
                or number.as_tuple().exponent < -6):
            return None
        return number
    except (InvalidOperation, ValueError, TypeError):
        return None


def build_payment_review(entities, offset=0, limit=100):
    """Inspect a caller-supplied snapshot. Do not load/save storage or contact providers."""
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 200:
        return {"error": "offset must be nonnegative and limit must be between 1 and 200."}
    loans = {item.id for item in entities if item.entity_type == FINANCE_CONTRACT}
    rows = []
    counts = Counter()
    total = Decimal(0)
    scanned = 0
    for item in sorted(entities, key=lambda entity: str(entity.id)):
        if item.entity_type != PAYMENT:
            continue
        scanned += 1
        attrs = item.attributes
        reasons = []
        actor = attrs.get("recorded_by")
        manual_cash = (attrs.get("method") == "cash" and isinstance(actor, str) and bool(actor.strip())
                       and actor != "customer_via_payment_portal" and not actor.startswith("auto_draft:"))
        basis = attrs.get("basis")
        if basis == "simulated_payment_gateway":
            reasons.append("legacy_cash_provenance" if manual_cash else "simulated_payment")
        elif basis != "staff_recorded_cash":
            reasons.append("unreviewed_payment_basis")
        if basis == "staff_recorded_cash" and not manual_cash:
            reasons.append("inconsistent_cash_provenance")
        if attrs.get("loan_id") not in loans:
            reasons.append("missing_finance_contract")
        amount = _amount(attrs.get("amount"))
        if amount is None:
            reasons.append("invalid_amount")
        if attrs.get("status") not in ("approved", "declined"):
            reasons.append("unreviewed_payment_status")
        if not reasons:
            continue
        counts.update(reasons)
        approved = attrs.get("status") == "approved"
        if approved and amount is not None:
            total += amount
        # Deliberate allowlist: no customer names, contacts, portal tokens, notes,
        # provider responses, credentials or arbitrary attribute dictionaries.
        rows.append({"payment_id": item.id, "loan_id": attrs.get("loan_id"),
                     "amount": str(amount) if amount is not None else None,
                     "approved": approved, "posted": attrs.get("posting_status") == "posted",
                     "reasons": reasons})
    return {"read_only": True, "reconciled": False, "scanned_payments": scanned,
            "flagged_payments": len(rows), "reason_counts": dict(sorted(counts.items())),
            "flagged_approved_receipt_total": str(total),
            "notice": "Review queue only. Amounts are recorded receipt values, not proven settlement or a proposed balance adjustment. Match original receipts and bank records before any correction.",
            "offset": offset, "limit": limit, "has_more": offset + limit < len(rows),
            "records": rows[offset:offset + limit]}


def payment_review_api(role, offset=0, limit=100):
    if role not in (ADMIN, OPERATIONS, FINANCE):
        return {"error": "Admin, Operations or Finance role required."}
    from copy import deepcopy
    from core.dealeros import ledger
    with ledger.persistence_guard():
        snapshot = deepcopy([item for item in ledger.get_all().values()
                             if item.entity_type in (PAYMENT, FINANCE_CONTRACT)])
    return build_payment_review(snapshot, offset, limit)
