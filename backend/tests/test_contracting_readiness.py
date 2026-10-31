"""Production negative tests and isolated-demo regression for the worksheet boundary."""

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import deals, digital_retail, esignature, esignature_api, integrations_registry
from core.contracting_readiness import contracting_readiness, execution_block
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, DEAL, SIGNATURE_REQUEST
from core.permissions import ADMIN


@pytest.fixture(autouse=True)
def isolated_production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.setattr(integrations_registry, "_ADAPTERS", {})
    ledger.reset()
    yield
    ledger.reset()


def ready_worksheet():
    ledger.add_entity(Entity("CUST-1", CUSTOMER, {"FirstName": "Sample", "LastName": "Buyer"}))
    ledger.add_entity(Entity("VEH-1", VEHICLE, {"VIN": "SAMPLE", "Year": "2026"}))
    deal = deals.create_deal("CUST-1", "VEH-1", "EMP-1")
    deals.add_scenario(deal.id, "Sample", 20000, 2000, 36)
    deals.select_scenario(deal.id, deal.attributes["scenarios"][0]["id"])
    deals.choose_in_house_financing(deal.id)
    return deals.generate_contract(deal.id)


def old_envelope(status):
    req = Entity("SIGN-OLD", SIGNATURE_REQUEST, {
        "status": status,
        "contract_snapshot": {"amount_financed": 1000},
        "signers": [{"name": "Sample Buyer", "role": "customer", "status": "pending",
                     "esign_consent": True}],
    })
    ledger.add_entity(req)
    return req


@pytest.mark.parametrize("flag", [None, "", "0", "false", "production", "unexpected"])
def test_missing_or_non_demo_configuration_blocks_execution(monkeypatch, flag):
    if flag is not None:
        monkeypatch.setenv("DEALEROS_DEMO", flag)
    assert execution_block("deal_fund")["blocked"] is True
    assert contracting_readiness()["production_enabled"] is False
    assert contracting_readiness()["enabled_jurisdictions"] == []


def test_worksheet_remains_available_but_cannot_fund_or_create_signature():
    deal = ready_worksheet()
    assert deal.attributes["contract"]["document_kind"] == "estimate_worksheet"
    assert deal.attributes["contract"]["executable"] is False
    before = deepcopy(ledger.get_all())
    assert deals.fund_deal(deal.id)["code"] == "contract_execution_not_ready"
    result = esignature_api.create_signature_request_api(
        ADMIN, "EMP-1", deal.id, [{"name": "Sample Buyer", "role": "customer"}])
    assert result["blocked"] is True
    assert list(ledger.get_all()) == list(before)
    assert deal.attributes == before[deal.id].attributes
    assert ledger.get_entity("VEH-1").attributes == before["VEH-1"].attributes


def test_forged_form_approval_does_not_enable_execution():
    deal = ready_worksheet()
    deal.attributes.update({"state": "TX", "form_approved": True, "compliance_override": True})
    deal.attributes["contract"].update({"executable": True, "document_kind": "approved_contract"})
    assert deals.fund_deal(deal.id)["blocked"] is True


@pytest.mark.parametrize("action,status", [
    (lambda r: esignature.send_signature_request(r), "draft"),
    (lambda r: esignature.capture_signer_consent(r, 0), "sent"),
    (lambda r: esignature.sign(r, 0, "Sample Buyer"), "sent"),
])
def test_existing_envelopes_cannot_bypass_gate(action, status):
    req = old_envelope(status)
    before = deepcopy(req.attributes)
    assert action(req.id)["blocked"] is True
    assert req.attributes == before


@pytest.mark.parametrize("demo", [False, True])
def test_registered_signature_adapter_never_receives_unreviewed_packet(monkeypatch, demo):
    if demo:
        monkeypatch.setenv("DEALEROS_DEMO", "1")
    calls = []
    integrations_registry.register_adapter("esignature", lambda packet: calls.append(packet))
    req = old_envelope("draft")
    assert integrations_registry.send_signature({"envelope_id": req.id})["blocked"] is True
    assert esignature.send_signature_request(req.id)["blocked"] is True
    assert req.attributes["status"] == "draft"
    assert not calls


@pytest.mark.parametrize("existing_contract", [False, True])
def test_customer_flow_blocks_before_mutation(monkeypatch, existing_contract):
    deal = Entity("DEAL-1", DEAL, {"status": "financing", "contract": {} if not existing_contract else {"amount": 1}})
    ledger.add_entity(deal)
    monkeypatch.setattr(digital_retail, "_gate", lambda *args: ({"id": "VERIFY-1"}, None))
    monkeypatch.setattr(digital_retail, "_owns", lambda *args: True)
    before = deepcopy(deal.attributes)
    assert digital_retail.sign("token", deal.id, "Sample Buyer")["blocked"] is True
    assert deal.attributes == before
    assert list(ledger.get_all()) == [deal.id]


def test_demo_signature_and_funding_remain_simulated_with_independent_snapshot(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    deal = ready_worksheet()
    deal.attributes["contract"]["fi_products"] = [{"name": "Original sample"}]
    req = esignature.create_signature_request(deal.id, "EMP-1", [{"name": "Sample Buyer", "role": "customer"}])
    deal.attributes["contract"]["fi_products"][0]["name"] = "Changed sample"
    assert req.attributes["contract_snapshot"]["fi_products"][0]["name"] == "Original sample"
    assert req.attributes["execution_mode"] == "sample_only"
    assert esignature.send_signature_request(req.id).attributes["send_mode"] == "simulated"
    esignature.capture_signer_consent(req.id, 0)
    assert esignature.sign(req.id, 0, "Sample Buyer").attributes["status"] == "completed"
    assert deals.fund_deal(deal.id).attributes["status"] == "funded"
    assert contracting_readiness()["production_enabled"] is False


def test_demo_customer_flow_propagates_dispatch_rejection(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    deal = ready_worksheet()
    ledger.add_entity(Entity("VERIFY-1", "Verification", {"email": "sample@example.invalid"}))
    monkeypatch.setattr(digital_retail, "_gate", lambda *args: ({"id": "VERIFY-1"}, None))
    monkeypatch.setattr(digital_retail, "_owns", lambda *args: True)
    integrations_registry.register_adapter("esignature", lambda *args: pytest.fail("Must not dispatch"))
    result = digital_retail.sign("token", deal.id, "Customer")
    assert result["code"] == "contract_execution_not_ready"
    req = esignature.list_signature_requests(linked_deal_id=deal.id)[0]
    assert req.attributes["status"] == "draft"
    assert req.attributes["signers"][0]["esign_consent"] is False
