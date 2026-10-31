"""Financial reconciliation uses exact decimal arithmetic and source-scope totals."""
import pytest
from core.bridge_reconciliation import expectations, reconcile
from core.bridge_contracts import decimal_value


def row(amount, currency="USD", status="ready"):
    return {"status": status, "values": {"amount": amount, **({"currency": currency} if currency else {})}}


def test_exact_decimal_totals_never_mix_currencies():
    report = reconcile([row("0.10"), row("0.20"), row("10.10", "CAD")],
                       {"row_count": 3, "totals": [{"field": "amount", "currency": "USD", "amount": "0.30"}]})
    assert report["status"] == "matched"
    assert {t["currency"]: t["amount"] for t in report["totals"]} == {"CAD": "10.10", "USD": "0.30"}


def test_source_snapshot_includes_duplicates_history_but_not_quarantine():
    report = reconcile([row("1"), row("2", status="duplicate"), row("3", status="history"), row("100", status="quarantined")])
    assert report["status"] == "incomplete" and report["totals"][0]["amount"] == "6"
    assert sum(report["counts"].values()) == 4


def test_incomplete_currency_does_not_masquerade_as_expected_currency():
    report = reconcile([row("10", None)], {"totals": [{"field": "amount", "currency": "USD", "amount": "10"}]})
    assert report["status"] == "mismatch" and report["rows_missing_currency"] == 1
    assert report["checks"][0]["actual"] is None


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e10000", "1e-10000", "1.0000001", True, 0.1])
def test_unbounded_or_ambiguous_money_rejected(value):
    with pytest.raises(ValueError): decimal_value(value)


def test_large_but_supported_totals_do_not_round():
    value = "99999999999999999999999.999999"
    report = reconcile([row(value)] * 1000)
    assert report["totals"][0]["amount"] == "99999999999999999999999999.999000"
    checked = reconcile([row(value)] * 1000, {"row_count": 1000, "totals": [{"field": "amount", "currency": "USD", "amount": report["totals"][0]["amount"]}]})
    assert checked["status"] == "matched"


def test_expected_checks_are_strict_and_cannot_duplicate():
    for bad in ({"row_count": True}, {"row_count": -1}, {"totals": [{"field": "email", "currency": "USD", "amount": "1"}]}, {"ignored": 1}):
        with pytest.raises(ValueError): expectations(bad)
    total = {"field": "balance", "currency": "USD", "amount": "10"}
    with pytest.raises(ValueError): expectations({"totals": [total, total]})
