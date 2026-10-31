"""
Phase 4/7 data (2026-08-03): My Garage verify-token-scoped customer endpoints. A verified
session resolves to the real Customer (match-and-verify) and returns THEIR vehicles/equity/
service/messages; an unverified session or a no-match verified session gets an honest error,
never another customer's data. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.relationship_types import OWNS, AUTHORIZED
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, VERIFICATION
from core import garage


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield
    ledger.reset()


def _customer(cid="CUST-1", email="jane@doe.com", **attrs):
    a = {"FirstName": "Jane", "LastName": "Doe", "Email": email, "CustomerID": cid}
    a.update(attrs)
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes=a))
    return cid


def _owned_vehicle(cid, vid="VEH-1"):
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"Year": 2022, "Make": "Ford", "Model": "F-150", "VIN": f"VIN{vid}"}))
    ledger.add_relationship(Relationship(source_id=cid, target_id=vid, relationship_type=OWNS))


def _service(cid, sid="SRV-1"):
    ledger.add_entity(Entity(id=sid, entity_type=SERVICE_RECORD, attributes={"ServiceDate": "2026-06-01", "Description": "Oil change", "Cost": "89.99"}))
    ledger.add_relationship(Relationship(source_id=cid, target_id=sid, relationship_type=AUTHORIZED))


def _session(token="tok-1", tier="verified_human", email="jane@doe.com", phone=None, linked=None):
    ledger.add_entity(Entity(id=f"VERF-{token}", entity_type=VERIFICATION, attributes={
        "session_token": token, "tier": tier, "email": email, "email_verified": tier != "anonymous",
        "phone": phone, "phone_verified": False, "linked_entity_id": linked,
        "identity": {}, "credit": {}, "history": [], "challenges": {},
    }))
    return token


# --- resolution + gating ---

def test_unverified_session_is_denied():
    _customer(email="jane@doe.com")
    tok = _session(tier="anonymous")
    r = garage.get_my_vehicles(tok)
    assert r.get("reason") == "unverified"


def test_bad_token_denied():
    assert garage.get_my_vehicles("nope")["reason"] == "token"


def test_verified_no_matching_customer():
    tok = _session(email="stranger@nowhere.com")  # no customer with this email
    r = garage.get_my_vehicles(tok)
    assert r.get("reason") == "no_match"


def test_verified_matches_and_returns_own_vehicles():
    cid = _customer(email="jane@doe.com", estimated_value=25000, estimated_payoff=15000)
    _owned_vehicle(cid)
    _service(cid)
    tok = _session(email="jane@doe.com")
    r = garage.get_my_vehicles(tok)
    assert r["customer"]["id"] == cid
    assert r["vehicle_count"] == 1
    assert r["equity"]["equity_amount"] == 10000
    assert r["service_summary"]["count"] == 1


def test_match_links_session_for_next_call():
    cid = _customer(email="jane@doe.com")
    tok = _session(email="jane@doe.com")
    garage.get_my_vehicles(tok)
    # session is now linked to the customer
    sess = ledger.get_entity(f"VERF-{tok}")
    assert sess.attributes["linked_entity_id"] == cid


def test_existing_link_is_honored_over_email():
    _customer("CUST-A", email="a@x.com")
    _customer("CUST-B", email="b@x.com")
    # session verified as a@x.com but explicitly linked to CUST-B -> link wins
    tok = _session(email="a@x.com", linked="CUST-B")
    r = garage.get_my_vehicles(tok)
    assert r["customer"]["id"] == "CUST-B"


def test_phone_match_when_no_email():
    cid = _customer(email="", Phone="5551112222")
    tok = _session(email=None, phone="(555) 111-2222")
    r = garage.get_my_vehicles(tok)
    assert r["customer"]["id"] == cid


# --- service + messages ---

def test_service_history_endpoint():
    cid = _customer(email="jane@doe.com")
    _service(cid)
    tok = _session(email="jane@doe.com")
    r = garage.get_my_service_history(tok)
    assert r["count"] == 1 and len(r["records"]) == 1


def test_messages_endpoint_returns_timeline():
    _customer(email="jane@doe.com")
    tok = _session(email="jane@doe.com")
    r = garage.get_my_messages(tok)
    assert "timeline" in r  # empty is fine — no fabricated messages
    assert isinstance(r["timeline"]["events"], list)


def test_no_leak_across_customers():
    _customer("CUST-A", email="a@x.com")
    cb = _customer("CUST-B", email="b@x.com")
    _owned_vehicle(cb, "VEH-B")
    # session verified as a@x.com must NOT see CUST-B's vehicle
    tok = _session(email="a@x.com")
    r = garage.get_my_vehicles(tok)
    assert r["customer"]["id"] == "CUST-A"
    assert r["vehicle_count"] == 0


# --- approvals + pay + status ---

def _ro(cid, ro_id="SRV-1", status="Open"):
    ledger.add_entity(Entity(id=ro_id, entity_type=SERVICE_RECORD, attributes={
        "ServiceNumber": ro_id, "CustomerID": cid, "VIN": "VINX",
        "Description": "Brake job", "Status": status,
    }))
    ledger.add_relationship(Relationship(source_id=cid, target_id=ro_id, relationship_type=AUTHORIZED))
    return ro_id


def test_approvals_lists_pending_estimate():
    from core import repair_orders
    cid = _customer(email="jane@doe.com")
    ro = _ro(cid)
    repair_orders.send_estimate(ro, 450.0, "EMP-1")  # pending estimate
    tok = _session(email="jane@doe.com")
    r = garage.get_my_approvals(tok)
    assert r["count"] == 1
    assert r["approvals"][0]["ro_id"] == ro
    assert r["approvals"][0]["estimate_amount"] == 450.0
    assert r["approvals"][0]["estimate_status"] == "pending"


def test_approve_then_pay_flow():
    from core import repair_orders
    import core.integrations_registry as ir
    ir._ADAPTERS.clear()
    cid = _customer(email="jane@doe.com")
    ro = _ro(cid)
    repair_orders.send_estimate(ro, 450.0, "EMP-1")
    tok = _session(email="jane@doe.com")

    # approve
    resp = garage.respond_to_approval(tok, ro, True)
    assert resp["ok"] is True
    assert ledger.get_entity(ro).attributes["estimate"]["approved"] is True

    # now it shows as approved-unpaid
    appr = garage.get_my_approvals(tok)
    assert appr["approvals"][0]["estimate_status"] == "approved" and appr["approvals"][0]["paid"] is False

    # pay (simulated, no payments provider)
    pay = garage.pay_my_ro(tok, ro)
    assert pay["ok"] is True and pay["mode"] == "simulated" and pay["amount"] == 450.0
    assert ledger.get_entity(ro).attributes["payment"]["paid"] is True

    # paying again is rejected; and it drops out of the approvals queue
    assert "error" in garage.pay_my_ro(tok, ro)
    assert garage.get_my_approvals(tok)["count"] == 0


def test_cannot_act_on_someone_elses_ro():
    from core import repair_orders
    _customer("CUST-A", email="a@x.com")
    cb = _customer("CUST-B", email="b@x.com")
    ro = _ro(cb, "SRV-B")
    repair_orders.send_estimate(ro, 100.0, "EMP-1")
    tok = _session(email="a@x.com")  # verified as A, RO belongs to B
    assert "error" in garage.respond_to_approval(tok, ro, True)
    assert "error" in garage.pay_my_ro(tok, ro)


def test_pay_requires_approval():
    from core import repair_orders
    cid = _customer(email="jane@doe.com")
    ro = _ro(cid)
    repair_orders.send_estimate(ro, 300.0, "EMP-1")  # pending, not approved
    tok = _session(email="jane@doe.com")
    assert "error" in garage.pay_my_ro(tok, ro)


def test_status_lists_active_ros_with_stage():
    cid = _customer(email="jane@doe.com")
    _ro(cid, "SRV-ACTIVE", status="Open")
    tok = _session(email="jane@doe.com")
    r = garage.get_my_status(tok)
    assert r["count"] == 1
    ro_view = r["active_ros"][0]
    assert ro_view["ro_id"] == "SRV-ACTIVE"
    assert ro_view["stage"]  # has a lifecycle stage
    assert isinstance(ro_view["workflow_checklist"], list)

@pytest.mark.parametrize("dispatch", [
    {"error": "private processor detail", "status": "collected", "simulated": False},
    {"ok": False, "status": "collected", "simulated": False},
    {"status": "declined", "simulated": False},
    {"status": "pending", "simulated": False},
    {"status": "collected"},
    {"status": "collected", "simulated": "false"},
    {}, None,
])
def test_unconfirmed_payment_does_not_mark_ro_paid(monkeypatch, dispatch):
    from core import repair_orders, integrations_registry
    cid = _customer()
    ro = _ro(cid)
    repair_orders.send_estimate(ro, 450.0, "EMP-1")
    tok = _session()
    garage.respond_to_approval(tok, ro, True)
    monkeypatch.setattr(integrations_registry, "charge_deposit", lambda *a, **kw: dispatch)
    saves = []
    monkeypatch.setattr(garage, "save_graph", lambda *a: saves.append(a))
    result = garage.pay_my_ro(tok, ro)
    assert "could not be confirmed" in result["error"]
    assert "private processor" not in result["error"]
    assert "payment" not in ledger.get_entity(ro).attributes
    assert not saves
    assert garage.get_my_approvals(tok)["count"] == 1


def test_confirmed_live_payment_preserves_provider_evidence(monkeypatch):
    from core import repair_orders, integrations_registry
    cid = _customer()
    ro = _ro(cid)
    repair_orders.send_estimate(ro, 450.0, "EMP-1")
    tok = _session()
    garage.respond_to_approval(tok, ro, True)
    monkeypatch.setattr(integrations_registry, "charge_deposit", lambda *a, **kw: {
        "status": "collected", "simulated": False, "reference": "fixture-receipt", "provider": "fixture",
    })
    result = garage.pay_my_ro(tok, ro)
    assert result["mode"] == "live"
    payment = ledger.get_entity(ro).attributes["payment"]
    assert payment["paid"] is True and payment["simulated"] is False
    assert payment["reference"] == "fixture-receipt"


def test_legacy_verified_token_cannot_reveal_customer_in_production(monkeypatch):
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    _customer()
    _owned_vehicle("CUST-1")
    token = _session(tier="credit_verified", linked="CUST-1")
    assert garage.get_my_vehicles(token).get("reason") == "unverified"
