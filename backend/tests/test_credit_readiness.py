"""Production decisions cannot be inferred from sample data or adapter registration."""
from copy import deepcopy
import pytest
from core import credit_app, integrations_registry
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    ledger.reset()
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setattr(integrations_registry, "_ADAPTERS", {})
    monkeypatch.setattr(credit_app, "save_graph", lambda *a: None)
    yield
    ledger.reset()


def draft():
    customer = Entity("CUST-SYN", CUSTOMER, {"CreditScore": "750"})
    ledger.add_entity(customer)
    app = credit_app.create_credit_application(customer.id, "EMP-SYN")
    credit_app.give_fcra_consent(app.id)
    credit_app.update_applicant(app.id, applicant_patch={"monthly_income": 5000})
    return app, customer


def test_production_draft_can_be_prepared_but_not_decisioned(monkeypatch):
    app, customer = draft()
    before = deepcopy(app.attributes)
    monkeypatch.setattr(credit_app, "save_graph", lambda *a: pytest.fail("No decision persistence allowed"))
    assert credit_app.submit_credit_application(app.id)["blocked"]
    assert credit_app._decide(app, customer)["blocked"]
    assert app.attributes == before


@pytest.mark.parametrize("demo", [False, True])
def test_registered_bureau_does_not_authorize_pull_or_decision(monkeypatch, demo):
    monkeypatch.setenv("DEALEROS_DEMO", "1" if demo else "0")
    integrations_registry.register_adapter("credit_bureau", lambda *a: pytest.fail("No external credit pull"))
    app, _ = draft()
    before = deepcopy(app.attributes)
    assert integrations_registry.pull_credit({"customer_id": "CUST-SYN"})["blocked"]
    assert credit_app.submit_credit_application(app.id)["blocked"]
    assert app.attributes == before


def test_unregistered_production_pull_fails_closed():
    assert integrations_registry.pull_credit({})["blocked"]
