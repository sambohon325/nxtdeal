"""No accounting operation may turn sample evidence into production records."""
from copy import deepcopy
import pytest
from core import general_ledger as gl, bank_reconciliation as bank
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import PAYMENT, BANK_TRANSACTION, GL_ENTRY


@pytest.fixture(autouse=True)
def production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    ledger.reset()
    ledger.add_entity(Entity("PMT-OLD", PAYMENT, {"status": "approved", "posting_status": "posted", "basis": "simulated_payment_gateway"}))
    ledger.add_entity(Entity("BANK-OLD", BANK_TRANSACTION, {"status": "unmatched", "basis": "simulated_bank_transaction"}))
    ledger.add_entity(Entity("GL-OLD", GL_ENTRY, {"basis": "simulated_gl_entry"}))
    def unexpected_save(*args):
        raise AssertionError("A blocked operation attempted to persist data")
    monkeypatch.setattr(gl, "save_graph", unexpected_save)
    monkeypatch.setattr(bank, "save_graph", unexpected_save)
    yield
    ledger.reset()


@pytest.mark.parametrize("action,scope", [
    (lambda: gl.sync_real_entries("EMP-1"), "accounting_sync"),
    (lambda: gl.generate_simulated_entries(2026, 10, "EMP-1"), "financial_simulation"),
    (lambda: bank.generate_simulated_bank_feed("EMP-1"), "financial_simulation"),
    (lambda: bank.confirm_match("BANK-OLD", "GL-OLD", "EMP-1"), "bank_reconciliation"),
    (lambda: bank.mark_transaction_reviewed("BANK-OLD", "EMP-1"), "bank_reconciliation"),
])
def test_financial_actions_block_before_mutation_or_persistence(action, scope):
    before = deepcopy(ledger.get_all())
    result = action()
    assert result["blocked"] is True and result["workflow"] == scope
    assert ledger.get_all() == before
