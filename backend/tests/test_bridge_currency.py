"""Every priced canonical domain can preserve an explicit source currency."""
import pytest

from core import dealer_bridge as b
from core.dealeros import ledger
from core.bridge_contracts import SourceRecord, SyncPage, transform, storage_kind
from core.bridge_sync import page_csv
from tests.test_dealer_bridge import A, B, isolated  # noqa: F401


@pytest.mark.parametrize("kind,amount_field", [("Vehicle", "price"), ("Deal", "amount"), ("ServiceOperation", "amount")])
def test_source_currency_can_be_mapped_and_reconciled_without_conversion(kind, amount_field):
    system = b.connect(A, "CSV", "Authorized synthetic export")["id"]
    fields = {amount_field: {"source": "value", "transform": "decimal"},
              "currency": {"source": "unit", "transform": "text"}}
    if kind == "Vehicle":
        fields["vin"] = {"source": "vin", "transform": "text"}
    mapping = b.propose_mapping(A, system, kind, "source_records", fields)["id"]
    b.approve_mapping(B, mapping)
    content = "external_id,modified_at,value,unit,vin\n1,2026-01-01T00:00:00Z,100.25,cad,1HGCM82633A004352\n"
    job = b.stage(A, mapping, content, {"totals": [{"field": amount_field, "currency": "CAD", "amount": "100.25"}]})["id"]
    preview = b.validate(A, job)
    assert preview[0]["values"]["currency"] == "CAD"
    assert b.get(job, "BridgeJob")["reconciliation"]["status"] == "matched"
    b.activate(B, job)
    entity = next(record for record in ledger.get_all().values() if record.entity_type == storage_kind(kind))
    assert entity.attributes[amount_field] == "100.25" and entity.attributes["currency"] == "CAD"


def test_legacy_mapping_without_currency_stays_unspecified():
    system = b.connect(A, "CSV", "Legacy price-only source")["id"]
    mapping = b.propose_mapping(A, system, "Deal", "deals", {"amount": {"source": "value", "transform": "text"}})["id"]
    job = b.stage(A, mapping, "external_id,modified_at,value\n1,2026-01-01T00:00:00Z,25.00\n")["id"]
    b.validate(A, job)
    report = b.get(job, "BridgeJob")["reconciliation"]
    assert report["totals"][0]["currency"] == "UNSPECIFIED"
    assert report["rows_missing_currency"] == 1


@pytest.mark.parametrize("value", [0.1, 100.25, float("nan"), float("inf"), True, False])
def test_adapter_money_cannot_hide_float_or_boolean_coercion(value):
    fields = {"amount": {"source": "vendor_total", "transform": "text"}}
    mapping = {"object_type": "deals", "fields": fields}
    page = SyncPage((SourceRecord("deals", "one", "2026-01-01T00:00:00Z", {"vendor_total": value}),), None, True)
    with pytest.raises(ValueError, match="preserve monetary"):
        page_csv(page, mapping)
    with pytest.raises(ValueError, match="decimal string"):
        transform("Deal", fields, {"vendor_total": value})


def test_adapter_decimal_strings_and_integers_keep_exact_values():
    mapping = {"object_type": "deals", "fields": {"amount": {"source": "total", "transform": "text"}}}
    for value in ("123456789012345678.123456", 123):
        page = SyncPage((SourceRecord("deals", "one", "2026-01-01T00:00:00Z", {"total": value}),), None, True)
        assert str(value) in page_csv(page, mapping)
