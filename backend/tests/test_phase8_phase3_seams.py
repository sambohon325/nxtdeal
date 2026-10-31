"""
Phase 8 (telephony) + Phase 3 (e-signature) seam wiring (2026-07-25): outbound calls and
signature-envelope sends now route through the provider seam (simulated fallback, live when
an adapter is registered). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, CUSTOMER, VEHICLE
from core import integrations_registry as ir
from core import call_center


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    ir._ADAPTERS.clear()
    yield
    ledger.reset()
    ir._ADAPTERS.clear()


# --- telephony ---

def test_place_call_dispatcher_simulated():
    r = ir.place_call("5551112222")
    assert r["simulated"] is True and r["placed"] is False


def test_outbound_call_stamps_simulated_mode():
    ledger.add_entity(Entity(id="EMP-1", entity_type=EMPLOYEE, attributes={"Department": "sales"}))
    call, err = call_center.place_outbound_call("sales", "5551112222", "EMP-1")
    assert err is None
    entity = ledger.get_entity(call["id"])
    assert entity.attributes["telephony_mode"] == "simulated"


def test_outbound_call_live_when_adapter_registered():
    ir.register_adapter("telephony", lambda to, frm, ctx: {"call_sid": "CA123", "status": "queued"})
    ledger.add_entity(Entity(id="EMP-1", entity_type=EMPLOYEE, attributes={"Department": "sales"}))
    call, err = call_center.place_outbound_call("sales", "5551112222", "EMP-1")
    entity = ledger.get_entity(call["id"])
    assert entity.attributes["telephony_mode"] == "live"
    assert entity.attributes["provider_call_sid"] == "CA123"


# --- e-signature ---

def test_send_signature_dispatcher_simulated():
    r = ir.send_signature({"envelope_id": "SIGN-1"})
    assert r["simulated"] is True and r["sent"] is False


def test_esign_send_stamps_mode():
    from core import esignature, deals
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"FirstName": "A", "LastName": "B"}))
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={"VIN": "V1"}))
    deal = deals.create_deal("CUST-1", "VEH-1", "EMP-1")
    # esignature.create_signature_request requires a generated contract; give the deal one.
    deal.attributes["contract"] = {"sale_price": 20000}
    req = esignature.create_signature_request(deal.id, "EMP-1", [{"name": "A B", "role": "customer", "email": "a@b.com"}])
    assert not isinstance(req, dict)
    sent = esignature.send_signature_request(req.id)
    assert sent.attributes["send_mode"] == "simulated"

    # An adapter cannot authorize delivery of an unreviewed worksheet.
    ir.register_adapter("esignature", lambda env: {"envelope_id": env["envelope_id"], "status": "sent"})
    deal2 = deals.create_deal("CUST-1", "VEH-1", "EMP-1")
    deal2.attributes["contract"] = {"sale_price": 21000}
    req2 = esignature.create_signature_request(deal2.id, "EMP-1", [{"name": "A B", "role": "customer", "email": "a@b.com"}])
    sent2 = esignature.send_signature_request(req2.id)
    assert sent2["code"] == "contract_execution_not_ready"
    assert req2.attributes["status"] == "draft"


def test_new_capabilities_registered():
    assert "telephony" in ir.CAPABILITIES and "esignature" in ir.CAPABILITIES
