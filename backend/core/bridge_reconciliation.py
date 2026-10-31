"""Deterministic import reconciliation; no financial posting or source-side writes."""
from collections import Counter
from decimal import Decimal, localcontext
from core.bridge_contracts import MONEY, decimal_value


def expectations(value=None):
    if value is None:
        return {"row_count": None, "totals": []}
    if not isinstance(value, dict) or set(value) - {"row_count", "totals", "balanced_journals"}:
        raise ValueError("Unknown reconciliation expectations")
    balanced = value.get("balanced_journals", False)
    if type(balanced) is not bool:
        raise ValueError("Balanced journals expectation must be boolean")
    count = value.get("row_count")
    if count is not None and (type(count) is not int or not 0 <= count <= 1000):
        raise ValueError("Expected row count must be between zero and 1000")
    totals = value.get("totals", [])
    if not isinstance(totals, list) or len(totals) > 30:
        raise ValueError("At most 30 expected totals are supported")
    cleaned, seen = [], set()
    for total in totals:
        if not isinstance(total, dict) or set(total) != {"field", "currency", "amount"}:
            raise ValueError("Each source total needs field, currency and amount")
        field, currency = total["field"], total["currency"]
        if field not in MONEY or not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("Known monetary field and currency required")
        currency = currency.upper()
        if (field, currency) in seen:
            raise ValueError("Duplicate expected currency/field total")
        seen.add((field, currency))
        # A bounded 1,000-row export may total three digits more than one row.
        cleaned.append({"field": field, "currency": currency, "amount": decimal_value(total["amount"], max_integer_digits=27)})
    # Preserve the old normalized shape when this opt-in check is not requested.
    return {"row_count": count, "totals": cleaned, **({"balanced_journals": True} if balanced else {})}



def mapping_expectations(mapping, expected=None):
    """Share the exact financial expectation contract across import and fixtures."""
    expected = expectations(expected)
    if expected.get("balanced_journals") and (mapping["kind"] != "JournalEntry" or not {"journal_id", "entry_side"} <= mapping["fields"].keys()):
        raise ValueError("Balanced journal checks require JournalEntry mapping with journal identity and side")
    if any(total["field"] not in mapping["fields"] for total in expected["totals"]):
        raise ValueError("Expected total refers to an unmapped monetary field")
    return expected


def reconcile(rows, expected=None):
    expected = expectations(expected)
    counts = Counter(row["status"] for row in rows)
    values, missing_currency = {}, 0
    with localcontext() as context:
        context.prec = 64
        for row in rows:
            if row["status"] == "quarantined":
                continue
            attributes = row.get("values", {})
            currency = attributes.get("currency", "UNSPECIFIED")
            monetary = [(field, attributes[field]) for field in MONEY if field in attributes]
            if monetary and currency == "UNSPECIFIED":
                missing_currency += 1
            for field, amount in monetary:
                key = (field, currency)
                current = values.setdefault(key, {"amount": Decimal(0), "rows": 0})
                current["amount"] += Decimal(decimal_value(amount))
                current["rows"] += 1
        totals = [{"field": field, "currency": currency, "amount": format(value["amount"], "f"), "rows": value["rows"]}
                  for (field, currency), value in sorted(values.items())]
        checks = []
        if expected["row_count"] is not None:
            checks.append({"check": "row_count", "expected": expected["row_count"], "actual": len(rows),
                           "matched": expected["row_count"] == len(rows)})
        for total in expected["totals"]:
            actual = values.get((total["field"], total["currency"]))
            checks.append({"check": "monetary_total", "field": total["field"], "currency": total["currency"],
                           "expected": total["amount"], "actual": format(actual["amount"], "f") if actual else None,
                           "matched": actual is not None and actual["amount"] == Decimal(total["amount"])})
        if expected.get("balanced_journals"):
            checks.extend(journal_checks(rows))
    incomplete = counts["quarantined"] > 0
    status = "incomplete" if incomplete else "not_requested" if not checks else "matched" if all(c["matched"] for c in checks) else "mismatch"
    return {"status": status, "source_rows": len(rows), "counts": dict(sorted(counts.items())), "totals": totals,
            "checks": checks, "rows_missing_currency": missing_currency,
            "review_advisory_rows": sum(bool(row.get("review_advisories")) for row in rows),
            "note": "Totals describe the mapped export, including duplicate/history rows; they do not post money or certify source accounting."}


def journal_checks(rows):
    """Caller explicitly attests the export contains complete journal groups.

    Never net currencies or infer debit/credit from vendor-specific sign rules.
    This only checks the supplied page, not a source general ledger or period.
    """
    groups, missing = {}, 0
    with localcontext() as context:
        context.prec = 64
        for row in rows:
            if row["status"] == "quarantined":
                continue
            value = row.get("values", {})
            if not value.get("journal_id") or value.get("entry_side") not in {"debit", "credit"} or not value.get("currency"):
                missing += 1
                continue
            group = groups.setdefault((value["journal_id"], value["currency"]), {"debit": Decimal(0), "credit": Decimal(0)})
            group[value["entry_side"]] += Decimal(decimal_value(value["amount"]))
        checks = [{"check": "journal_balance", "journal_id": journal, "currency": currency,
                   "expected": format(amounts["debit"], "f"), "actual": format(amounts["credit"], "f"),
                   "matched": amounts["debit"] == amounts["credit"]}
                  for (journal, currency), amounts in sorted(groups.items())]
    checks.append({"check": "journal_metadata", "expected": 0, "actual": missing, "matched": missing == 0 and bool(groups)})
    return checks
