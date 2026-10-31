"""Tests for the customer side of Communications (core/customer_comms.py, 2026-07-24)."""

import pytest

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import EMPLOYEE, CUSTOMER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import customer_comms as cc
from core import integrations_registry


@pytest.fixture
def actor_and_customer():
    emp = Entity(id=id_generator.generate("EMP"), entity_type=EMPLOYEE,
                 attributes={"name": "Rep One", "department": "Sales"})
    cust = Entity(id=id_generator.generate("CUST"), entity_type=CUSTOMER,
                  attributes={"name": "Jane Buyer", "phone": "555-0100", "email": "jane@example.com"})
    ledger.add_entity(emp)
    ledger.add_entity(cust)
    save_graph(GRAPH_PATH)
    return emp.id, cust.id


def test_provider_status_simulated_by_default():
    s = cc.provider_status()
    assert s["capability"] == "notifications"
    assert s["live"] is False
    assert s["marketplace_category"] == "communications"


def test_search_only_returns_contactable_people(actor_and_customer):
    _, cust_id = actor_and_customer
    res = cc.search_customers("Jane")
    assert res["count"] >= 1
    assert any(r["id"] == cust_id and r["type"] == CUSTOMER for r in res["results"])


def test_place_call_connects(actor_and_customer):
    emp_id, cust_id = actor_and_customer
    r = cc.place_call(emp_id, customer_id=cust_id)
    assert "error" not in r
    assert r["call"]["status"] == "connected"
    assert r["provider"]["live"] is False


def test_end_call_produces_recording_and_ai(actor_and_customer):
    emp_id, cust_id = actor_and_customer
    placed = cc.place_call(emp_id, customer_id=cust_id)
    ended = cc.end_call(placed["call"]["id"], emp_id, notes="Discussed trade-in value.")
    assert "error" not in ended
    assert ended["communication"] is not None
    assert ended["intelligence"] is not None
    assert "sentiment" in ended["intelligence"]


def test_send_text_logs_comm_and_dispatches_simulated(actor_and_customer):
    emp_id, cust_id = actor_and_customer
    r = cc.send_text(emp_id, "Your quote is ready!", customer_id=cust_id)
    assert "error" not in r
    assert r["communication"]["channel"] == "text"
    assert r["dispatch"]["simulated"] is True


def test_place_call_requires_a_number(actor_and_customer):
    emp_id, _ = actor_and_customer
    no_phone = Entity(id=id_generator.generate("CUST"), entity_type=CUSTOMER,
                      attributes={"name": "No Phone"})
    ledger.add_entity(no_phone)
    r = cc.place_call(emp_id, customer_id=no_phone.id)
    assert "error" in r


def test_save_contact_creates_customer(actor_and_customer):
    emp_id, _ = actor_and_customer
    r = cc.save_contact("555-0199", "Walk-in Bob", emp_id)
    assert r["type"] == CUSTOMER
    assert r["phone"] == "555-0199"
    # searchable afterward
    assert any(x["id"] == r["id"] for x in cc.search_customers("Bob")["results"])


def test_conversation_and_recent(actor_and_customer):
    emp_id, cust_id = actor_and_customer
    cc.send_text(emp_id, "Hi there", customer_id=cust_id)
    conv = cc.get_conversation(cust_id)
    assert "error" not in conv
    assert conv["timeline"]["event_count"] >= 1
    assert cc.recent_activity()["count"] >= 1


def test_text_goes_live_when_adapter_registered(actor_and_customer):
    emp_id, cust_id = actor_and_customer
    integrations_registry.register_adapter("notifications", lambda *a, **k: {"delivered": True})
    try:
        assert cc.provider_status()["live"] is True
    finally:
        integrations_registry._ADAPTERS.pop("notifications", None)
