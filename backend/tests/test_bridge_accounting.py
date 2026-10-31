"""Optional whole-journal checks preserve observations without posting money."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_bridge as b
from core.bridge_contracts import transform
from core.bridge_reconciliation import expectations, reconcile
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import GL_ENTRY, BANK_TRANSACTION
from api.routers.dealer_bridge import router, admin
from tests.test_dealer_bridge import A, B, setup, isolated  # noqa: F401

FIELDS = ("account_code", "journal_id", "entry_side", "amount", "currency", "occurred_at")
HEADER = "external_id,modified_at," + ",".join(FIELDS) + "\n"
CSV = HEADER + "line-1,2026-01-02T00:00:00Z,1000,journal-1,debit,0.30,USD,2026-01-01T00:00:00Z\n" + \
    "line-2,2026-01-02T00:00:00Z,2000,journal-1,credit,0.10,USD,2026-01-01T00:00:00Z\n" + \
    "line-3,2026-01-02T00:00:00Z,2000,journal-1,credit,0.20,USD,2026-01-01T00:00:00Z\n"


def configured():
    system, _ = setup()
    mapping = b.propose_mapping(A, system, "JournalEntry", "journal_lines", {
        field: {"source": field, "transform": "text"} for field in FIELDS})["id"]
    b.approve_mapping(B, mapping)
    return mapping


def test_balanced_journals_activate_only_as_imported_observations():
    mapping = configured()
    expected = {"balanced_journals": True, "row_count": 3}
    simulation = b.simulate_mapping(A, mapping, CSV, expected)
    assert simulation["reconciliation"]["status"] == "matched"
    job = b.stage(A, mapping, CSV, expected)["id"]
    b.validate(A, job); b.activate(B, job)
    rows = [entity for entity in ledger.get_all().values() if entity.entity_type == "JournalEntry"]
    assert len(rows) == 3
    assert {entity.attributes["entry_side"] for entity in rows} == {"debit", "credit"}
    assert not any(entity.entity_type in {GL_ENTRY, BANK_TRANSACTION, "Payment", "AccountingPeriod"} for entity in ledger.get_all().values())


@pytest.mark.parametrize("content", [CSV.replace("credit,0.20", "credit,0.21"),
                                    CSV.replace("2000,journal-1,credit,0.20,USD", "2000,journal-1,credit,0.20,CAD"),
                                    CSV.replace("2000,journal-1,credit,0.20", "2000,journal-2,credit,0.20"),
                                    CSV.replace("journal-1,debit", ",debit"),
                                    CSV.replace("journal-1,debit", "journal-1,")])
def test_unbalanced_or_incomplete_journal_metadata_blocks_activation(content):
    mapping = configured()
    job = b.stage(A, mapping, content, {"balanced_journals": True})["id"]
    b.validate(A, job)
    assert b.get(job, "BridgeJob")["status"] == "blocked"
    with pytest.raises(ValueError): b.activate(B, job)
    assert not any(entity.entity_type == "JournalEntry" for entity in ledger.get_all().values())


def test_partial_journal_is_allowed_when_balance_check_not_requested():
    mapping = configured()
    partial = "\n".join(CSV.splitlines()[:2]) + "\n"
    result = b.simulate_mapping(A, mapping, partial)
    assert result["reconciliation"]["status"] == "not_requested"
    assert result["rows"][0]["status"] == "ready"


def test_legacy_expectation_shape_is_preserved():
    assert expectations({"balanced_journals": False}) == {"row_count": None, "totals": []}
    assert expectations() == expectations({})
    for value in ["true", 1, None]:
        with pytest.raises(ValueError): expectations({"balanced_journals": value})


def test_balance_check_requires_explicit_journal_mapping():
    _, customer = setup()
    with pytest.raises(ValueError, match="JournalEntry"):
        b.simulate_mapping(A, customer, "unused", {"balanced_journals": True})
    mapping = configured()
    spec = b.get(mapping, "BridgeMapping")
    del spec["fields"]["entry_side"]
    spec["hash"] = b.mapping_digest(spec)
    with pytest.raises(ValueError, match="journal identity and side"):
        b.stage(A, mapping, CSV, {"balanced_journals": True})


@pytest.mark.parametrize("side, amount", [("unknown", "10"), ("debit", "-1"), ("credit", "-0.01")])
def test_sided_lines_do_not_guess_vendor_sign_conventions(side, amount):
    fields = {field: {"source": field, "transform": "text"} for field in FIELDS}
    values = {"account_code": "1000", "journal_id": "j1", "entry_side": side, "amount": amount,
              "currency": "USD", "occurred_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(ValueError): transform("JournalEntry", fields, values)
    del fields["entry_side"]
    assert transform("JournalEntry", fields, values)["amount"] == amount


def test_account_reference_checks_code_and_optional_currency():
    mapping = configured()
    spec = b.get(mapping, "BridgeMapping")
    spec["fields"]["ledger_account_id"] = {"source": "ledger_account_id", "transform": "text"}
    spec["hash"] = b.mapping_digest(spec)
    account = Entity("ACCOUNT-1", "AccountingAccount", {"account_code": "1000", "currency": "USD"})
    ledger.add_entity(account)
    content = HEADER.rstrip() + ",ledger_account_id\nline-1,2026-01-02T00:00:00Z,1000,j1,debit,10,USD,2026-01-01T00:00:00Z,ACCOUNT-1\n"
    assert b.simulate_mapping(A, mapping, content)["rows"][0]["status"] == "ready"
    account.attributes["account_code"] = "other"
    assert b.simulate_mapping(A, mapping, content)["rows"][0]["status"] == "quarantined"
    account.attributes.update(account_code="1000", currency="CAD")
    assert b.simulate_mapping(A, mapping, content)["rows"][0]["status"] == "quarantined"


def test_journal_expectation_api_requires_boolean():
    mapping = configured()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[admin] = lambda: A
    client = TestClient(app)
    path = f"/dealer-bridge/mappings/{mapping}/test"
    assert client.post(path, json={"content": CSV, "expectations": {"balanced_journals": True}}).json()["reconciliation"]["status"] == "matched"
    assert client.post(path, json={"content": CSV, "expectations": {"balanced_journals": "true"}}).status_code == 422
